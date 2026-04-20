"""LangGraph agent that maps PDF page text to MDF lexical entries.

Contract
--------
* **Never invents.** When ``allow_ai_generation`` is ``False`` the agent
  must set every non-literal field to ``null``.
* **Literal orthography.** No normalization of indigenous-language
  orthography — grafías are copied byte-for-byte.
* **Structured output.** We use LangChain's ``with_structured_output``
  so the LLM is constrained to the Pydantic schema. Schema validation
  failures trigger a retry loop bounded by ``AGENT_MAX_RETRIES``.
* **AI-generated flag.** The LLM itself must tag each inferred field
  with ``ai_generated=True``. A post-validator sanity-checks the flag
  and, when AI generation is disabled, scrubs inferred values.

Graph
-----
    parse_page ─▶ classify_fields ─▶ validate_output ─▶ END
                        ▲                  │
                        │                  ├── retry ──┐
                        └──────────────────┘           │
                                           │           │
                                           └── fail ─▶ record_failure ─▶ END

The retry edge is bounded by ``max_retries``; on exhaustion the router
dispatches to ``record_failure`` which materializes a ``PageError``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.config import get_settings
from schemas.parser import LexicalEntry, MDFField, PageError

log = logging.getLogger(__name__)


UNKNOWN_LANGUAGE = "Unknown Language"


# ----------------------------------------------------------------------
# LLM output schema
# ----------------------------------------------------------------------
class AgentPageOutput(BaseModel):
    """What the LLM must return per page."""

    # ``extra="ignore"``: some providers echo context fields (e.g. a
    # ``source_page`` lifted from the nested LexicalEntry schema or from
    # the user message) at the top level. We want to tolerate that noise
    # rather than fail the whole page.
    model_config = ConfigDict(extra="ignore")

    detected_language: str | None = Field(
        default=None,
        description=(
            "Best guess at the indigenous target language (e.g. 'maya', "
            "'nahuatl'). Return null if the text is insufficient to decide."
        ),
    )
    entries: list[LexicalEntry] = Field(
        default_factory=list,
        description="Lexical entries found on this page, in the order they appear.",
    )


# ----------------------------------------------------------------------
# System prompt
# ----------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an expert linguist specialized in indigenous Latin American \
dictionaries (Mayan, Popoluca, Iskonawa, Zapotec, Nahuatl, and related \
families).

Your job is to read one page of a printed dictionary and structure \
every lexical entry it contains according to the MDF (Machine-Readable \
Dictionary Format) tag set supplied as the output schema.

{extraction_policy}

ABSOLUTE RULES — VIOLATION IS A FAILURE:

1. PRESERVE ORIGINAL ORTHOGRAPHY. When copying a value verbatim, do \
   not normalize accents, diacritics, apostrophes, glottal stops, or \
   any indigenous-language spelling. Copy grafías byte-for-byte.
2. VERBATIM FIELDS ARE LANGUAGE-SPECIFIC. When copying content from \
   the source, place it in the field that matches its language \
   (Spanish definitions → ``definition_es``, English → \
   ``definition_en``, etc.). Never silently translate a source value \
   into the wrong-language field.
3. AI-GENERATED FLAG. Every ``MDFField`` has an ``ai_generated`` flag. \
   Set it to ``true`` ONLY for values you inferred that are not \
   literally in the source text. Verbatim copies keep \
   ``ai_generated=false``. A null ``value`` must have \
   ``ai_generated=false``.
4. ORDER. Keep entries in the order they appear on the page.
5. LEXEME IS REQUIRED AND NEVER INFERRED. Every entry must have a \
   non-empty ``lexeme`` copied verbatim from the source. Omit entries \
   whose headword is unreadable — do not fabricate one.
6. SCHEMA FIDELITY. Return only the fields declared in \
   ``AgentPageOutput`` (``detected_language`` and ``entries``) at the \
   top level. Do not add sibling fields like ``source_page``, \
   ``page_number``, or ``notes``.

Structural cues to look for on a dictionary page:
- Bold / capitalized headwords separate entries.
- Roman-numeral or Arabic sense numbers (I., II., 1., 2.) open new senses.
- Italic or small-caps tags often indicate part of speech.
- Examples are typically preceded by cues like "Ej.", "Ex.", or quoted text.
- Phonetic transcriptions usually sit in square brackets [..] or slashes /../.

If the page has no lexical entries (front matter, index, blank, running \
header only) return an empty ``entries`` list.

Output only valid JSON matching the supplied schema.
"""

_EXTRACTION_POLICY_STRICT = """\
EXTRACTION POLICY — STRICT (AI generation DISABLED):
- Extract ONLY what is explicitly present in the page text.
- If a field is not in the text, leave its ``value`` null with \
  ``ai_generated=false``.
- Every ``ai_generated`` flag in your output MUST be ``false``.
"""

_EXTRACTION_POLICY_INFER = """\
EXTRACTION POLICY — INFERENCE ALLOWED (AI generation ENABLED):

STEP 1 — Literal extraction. Copy every field that is literally \
present; these fields stay ``ai_generated=false``.

STEP 2 — Active inference. For every entry, you SHOULD then try to \
fill in high-confidence missing fields as inferences with \
``ai_generated=true``. Do not leave a field null when it is plainly \
implied by the entry — that is a failure. Target especially:

  * ``part_of_speech`` — deduce from morphology, example sentences, or \
    dictionary conventions when the source omits a ``\\ps`` marker.
  * Cross-language glosses/definitions. If the source gives only \
    ``definition_es`` you MAY produce a faithful ``definition_en`` (and \
    vice-versa), and likewise for ``gloss_es``/``gloss_en`` and \
    ``example_translation_es``/``example_translation_en``. Inferred \
    translations go in the target-language field with \
    ``ai_generated=true``; the original source-language field keeps \
    its verbatim value and ``ai_generated=false``.
  * ``gloss_es``/``gloss_en`` — short equivalents when only a longer \
    definition is present.
  * ``etymology``, ``scientific_name`` — only if strongly suggested by \
    context (e.g. a parenthetical Latin name next to a plant entry).

HARD LIMITS:
- NEVER infer the ``lexeme``. Headwords are copied verbatim only.
- NEVER fabricate example sentences. ``example_vernacular`` and \
  ``example_source`` are verbatim-only.
- When evidence is weak or ambiguous, prefer ``null`` over a guess.
"""


def _render_system_prompt(allow_ai_generation: bool) -> str:
    policy = (
        _EXTRACTION_POLICY_INFER if allow_ai_generation else _EXTRACTION_POLICY_STRICT
    )
    return SYSTEM_PROMPT.format(extraction_policy=policy)


# ----------------------------------------------------------------------
# Graph state
# ----------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    # Inputs
    page_number: int
    page_text: str
    language_hint: str | None
    allow_ai_generation: bool

    # Working state
    retries: int
    last_error: str | None

    # Outputs
    entries: list[LexicalEntry]
    detected_language: str | None
    page_error: PageError | None


@dataclass
class PageAgentResult:
    """Public result envelope for one page."""

    page_number: int
    entries: list[LexicalEntry]
    detected_language: str | None
    error: PageError | None

    @property
    def ok(self) -> bool:
        return self.error is None


# ----------------------------------------------------------------------
# Agent implementation
# ----------------------------------------------------------------------
class MDFPageAgent:
    """LangGraph agent that processes one PDF page at a time."""

    def __init__(self, llm: Any, *, max_retries: int | None = None) -> None:
        """Build the compiled graph.

        ``llm`` is any LangChain ``BaseChatModel`` instance produced by
        :func:`services.llm_router.build_chat_model`.
        """
        settings = get_settings()
        self._llm = llm
        self._structured = llm.with_structured_output(AgentPageOutput)
        self._max_retries = (
            settings.agent_max_retries if max_retries is None else max_retries
        )
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        *,
        page_number: int,
        page_text: str,
        language_hint: str | None = None,
        allow_ai_generation: bool = False,
    ) -> PageAgentResult:
        """Synchronously process a single page."""
        initial: AgentState = {
            "page_number": page_number,
            "page_text": page_text,
            "language_hint": language_hint,
            "allow_ai_generation": allow_ai_generation,
            "retries": 0,
            "last_error": None,
            "entries": [],
            "detected_language": None,
            "page_error": None,
        }
        final: AgentState = self._graph.invoke(initial)
        return PageAgentResult(
            page_number=page_number,
            entries=final.get("entries", []),
            detected_language=final.get("detected_language"),
            error=final.get("page_error"),
        )

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------
    def _build_graph(self):  # type: ignore[no-untyped-def]
        graph: StateGraph = StateGraph(AgentState)
        graph.add_node("parse_page", self._parse_page)
        graph.add_node("classify_fields", self._classify_fields)
        graph.add_node("validate_output", self._validate_output)
        graph.add_node("record_failure", self._record_failure)

        graph.add_edge(START, "parse_page")
        graph.add_edge("parse_page", "classify_fields")
        graph.add_edge("classify_fields", "validate_output")
        graph.add_conditional_edges(
            "validate_output",
            self._route_after_validation,
            {
                "retry": "classify_fields",
                "fail": "record_failure",
                "done": END,
            },
        )
        graph.add_edge("record_failure", END)
        return graph.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_page(state: AgentState) -> AgentState:
        """Pre-flight: short-circuit on empty pages."""
        text = (state.get("page_text") or "").strip()
        if not text:
            return {
                **state,
                "entries": [],
                "detected_language": None,
                "page_error": None,
                "last_error": "empty page text",
            }
        return state

    def _classify_fields(self, state: AgentState) -> AgentState:
        """Call the LLM with structured output."""
        # If parse_page already flagged this page as empty, bail out now.
        if state.get("last_error") == "empty page text":
            return state

        system = _render_system_prompt(bool(state.get("allow_ai_generation")))
        user = self._render_user_message(state)

        try:
            result: AgentPageOutput = self._structured.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
            # Clear the retry error on success.
            return {
                **state,
                "entries": list(result.entries),
                "detected_language": result.detected_language,
                "last_error": None,
            }
        except ValidationError as exc:
            return {**state, "last_error": f"schema validation failed: {exc}"}
        except Exception as exc:  # noqa: BLE001 - LLM errors vary wildly
            return {**state, "last_error": f"LLM invocation failed: {exc}"}

    def _validate_output(self, state: AgentState) -> AgentState:
        """Finalize entries on success; bump retry counter on LLM failure.

        The routing decision (retry / fail / done) happens in
        :meth:`_route_after_validation`. This node only produces state
        updates — LangGraph does not persist mutations made inside a
        conditional edge function.
        """
        err = state.get("last_error")
        if err == "empty page text":
            # Not a real error — just an empty page. Materialize the
            # empty result so the router can finish cleanly.
            hint = state.get("language_hint")
            return {
                **state,
                "entries": [],
                "detected_language": (
                    state.get("detected_language") or hint or UNKNOWN_LANGUAGE
                ),
                "page_error": None,
            }
        if err:
            # LLM failed; the router decides whether we retry or fail.
            return {**state, "retries": int(state.get("retries", 0)) + 1}

        page_number = int(state.get("page_number", 0))
        allow_ai = bool(state.get("allow_ai_generation"))
        hint = state.get("language_hint")

        cleaned: list[LexicalEntry] = []
        for entry in state.get("entries", []):
            entry_with_page = entry.model_copy(update={"source_page": page_number})
            if not allow_ai:
                entry_with_page = _scrub_inferred_fields(entry_with_page)
            cleaned.append(entry_with_page)

        detected = state.get("detected_language")
        if not detected and hint:
            detected = hint
        if not detected:
            detected = UNKNOWN_LANGUAGE

        return {
            **state,
            "entries": cleaned,
            "detected_language": detected,
            "page_error": None,
        }

    def _record_failure(self, state: AgentState) -> AgentState:
        """Terminal node: convert ``last_error`` into a ``PageError``."""
        err = state.get("last_error") or "unknown agent failure"
        return {
            **state,
            "entries": [],
            "detected_language": state.get("detected_language") or UNKNOWN_LANGUAGE,
            "page_error": PageError(
                page_number=int(state.get("page_number", 0)),
                error_type="agent_failure",
                message=err,
            ),
        }

    # ------------------------------------------------------------------
    # Retry policy
    # ------------------------------------------------------------------
    def _route_after_validation(
        self, state: AgentState
    ) -> Literal["retry", "fail", "done"]:
        err = state.get("last_error")
        if not err or err == "empty page text":
            return "done"
        retries = int(state.get("retries", 0))
        # ``retries`` counts failures observed so far (incremented in
        # ``_validate_output``). We allow up to ``max_retries`` re-runs
        # on top of the initial attempt, for a total of
        # ``max_retries + 1`` LLM invocations.
        if retries <= self._max_retries:
            log.warning(
                "Page %s retrying (%d/%d): %s",
                state.get("page_number"),
                retries,
                self._max_retries,
                err,
            )
            return "retry"
        return "fail"

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------
    @staticmethod
    def _render_user_message(state: AgentState) -> str:
        hint = state.get("language_hint")
        hint_line = (
            f"Language hint (use only if confirmed by the text): {hint}\n"
            if hint
            else "Language hint: none — infer from the text if possible.\n"
        )
        # NOTE: we deliberately do NOT include the page number here — some
        # models (e.g. Claude Haiku) will echo it back as a top-level
        # ``source_page`` field on ``AgentPageOutput``, polluting the output.
        # The page number is stamped server-side in ``_validate_output``.
        return (
            f"{hint_line}"
            "Page text follows between <page> tags. Return AgentPageOutput "
            "JSON only — the only allowed top-level keys are "
            "``detected_language`` and ``entries``.\n"
            f"<page>\n{state.get('page_text', '')}\n</page>"
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _scrub_inferred_fields(entry: LexicalEntry) -> LexicalEntry:
    """Replace any ``ai_generated=True`` field with an empty field."""
    updates: dict[str, MDFField] = {}
    for attr in LexicalEntry.MDF_TAGS.values():
        field: MDFField = getattr(entry, attr)
        if field.ai_generated:
            updates[attr] = MDFField()  # null value, ai_generated=False
    if not updates:
        return entry
    # lexeme must remain non-null; if the LLM marked it as inferred we
    # must fail — but we've already required allow_ai=False here, so we
    # preserve the literal content from the LLM by forcing ai_generated=False.
    if "lexeme" in updates:
        raise ValueError(
            "Model returned lexeme as ai_generated=True while AI generation is disabled."
        )
    return entry.model_copy(update=updates)


# ----------------------------------------------------------------------
# CLI entry point:
#     python -m services.mdf_agent --text-file page.txt --model openai:gpt-4o-mini
# ----------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json
    from pathlib import Path

    from core.sync import bootstrap
    from services.llm_router import build_chat_model

    bootstrap()

    parser = argparse.ArgumentParser(description="Run the MDF agent on a single page text file.")
    parser.add_argument("--text-file", required=True, help="Path to a plain-text file.")
    parser.add_argument("--model", required=True, help="Fully-qualified model id.")
    parser.add_argument("--language-hint", default=None)
    parser.add_argument("--allow-ai", action="store_true")
    parser.add_argument("--page-number", type=int, default=1)
    args = parser.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8")
    agent = MDFPageAgent(build_chat_model(args.model))
    result = agent.run(
        page_number=args.page_number,
        page_text=text,
        language_hint=args.language_hint,
        allow_ai_generation=args.allow_ai,
    )
    print(
        json.dumps(
            {
                "page_number": result.page_number,
                "detected_language": result.detected_language,
                "entries": [e.model_dump() for e in result.entries],
                "error": result.error.model_dump() if result.error else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
