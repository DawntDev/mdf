"""Unit tests for the LangGraph MDF agent.

We avoid hitting any real LLM provider: ``_FakeStructuredLLM`` mimics
the surface area of ``BaseChatModel.with_structured_output`` by returning
pre-recorded :class:`AgentPageOutput` objects. This keeps tests fast and
reproducible while still exercising the graph (parse → classify →
validate → retry loop).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from schemas.parser import LexicalEntry, MDFField
from services.mdf_agent import (
    UNKNOWN_LANGUAGE,
    AgentPageOutput,
    MDFPageAgent,
)


# ----------------------------------------------------------------------
# Fake LLM infrastructure
# ----------------------------------------------------------------------
class _FakeStructured:
    """Substitute for ``llm.with_structured_output(AgentPageOutput)``."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def invoke(self, _messages: Any) -> AgentPageOutput:
        self.calls += 1
        if not self._responses:
            raise RuntimeError("Fake LLM exhausted")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@dataclass
class _FakeLLM:
    """Mimics the minimal BaseChatModel surface used by MDFPageAgent."""

    structured: _FakeStructured

    def with_structured_output(self, _schema: Any) -> _FakeStructured:
        return self.structured


def _make_agent(responses: list[Any], *, max_retries: int = 2) -> tuple[MDFPageAgent, _FakeStructured]:
    structured = _FakeStructured(responses)
    agent = MDFPageAgent(_FakeLLM(structured), max_retries=max_retries)
    return agent, structured


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------
def test_agent_returns_literal_entries_on_success() -> None:
    output = AgentPageOutput(
        detected_language="maya",
        entries=[
            LexicalEntry(
                lexeme=MDFField.literal("balam"),
                definition_es=MDFField.literal("jaguar"),
            )
        ],
    )
    agent, fake = _make_agent([output])
    result = agent.run(
        page_number=3,
        page_text="balam — jaguar",
        allow_ai_generation=False,
    )

    assert result.ok
    assert result.detected_language == "maya"
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.lexeme.value == "balam"
    assert entry.definition_es.value == "jaguar"
    assert entry.source_page == 3
    assert fake.calls == 1


def test_agent_scrubs_inferred_fields_when_ai_disabled() -> None:
    output = AgentPageOutput(
        detected_language="nahuatl",
        entries=[
            LexicalEntry(
                lexeme=MDFField.literal("ocelotl"),
                definition_es=MDFField.inferred("jaguar (inferido)"),
            )
        ],
    )
    agent, _ = _make_agent([output])
    result = agent.run(
        page_number=1,
        page_text="ocelotl",
        allow_ai_generation=False,
    )
    assert result.ok
    entry = result.entries[0]
    assert entry.lexeme.value == "ocelotl"
    # Inferred field must be erased when AI generation is disabled.
    assert entry.definition_es.value is None
    assert entry.definition_es.ai_generated is False


def test_agent_preserves_inferred_fields_when_ai_enabled() -> None:
    output = AgentPageOutput(
        detected_language="nahuatl",
        entries=[
            LexicalEntry(
                lexeme=MDFField.literal("ocelotl"),
                definition_es=MDFField.inferred("jaguar (inferido)"),
            )
        ],
    )
    agent, _ = _make_agent([output])
    result = agent.run(
        page_number=1,
        page_text="ocelotl",
        allow_ai_generation=True,
    )
    assert result.ok
    entry = result.entries[0]
    assert entry.definition_es.value == "jaguar (inferido)"
    assert entry.definition_es.ai_generated is True


# ----------------------------------------------------------------------
# Retry policy
# ----------------------------------------------------------------------
def test_agent_retries_on_llm_exception_then_succeeds() -> None:
    recovery = AgentPageOutput(
        detected_language="maya",
        entries=[LexicalEntry(lexeme=MDFField.literal("balam"))],
    )
    agent, fake = _make_agent(
        [RuntimeError("transient timeout"), recovery], max_retries=2
    )
    result = agent.run(page_number=1, page_text="balam")
    assert result.ok
    assert result.entries[0].lexeme.value == "balam"
    assert fake.calls == 2  # one failed + one recovery


def test_agent_gives_up_after_max_retries() -> None:
    agent, fake = _make_agent(
        [RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")],
        max_retries=2,
    )
    result = agent.run(page_number=7, page_text="some text")
    assert not result.ok
    assert result.error is not None
    assert result.error.page_number == 7
    assert result.error.error_type == "agent_failure"
    # Initial call + 2 retries = 3 attempts total.
    assert fake.calls == 3


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------
def test_agent_short_circuits_on_empty_text() -> None:
    agent, fake = _make_agent([])  # LLM should never be called
    result = agent.run(page_number=1, page_text="   ")
    assert result.ok
    assert result.entries == []
    assert fake.calls == 0


def test_agent_falls_back_to_unknown_language_when_not_detected() -> None:
    output = AgentPageOutput(
        detected_language=None,
        entries=[LexicalEntry(lexeme=MDFField.literal("foo"))],
    )
    agent, _ = _make_agent([output])
    result = agent.run(page_number=1, page_text="foo")
    assert result.detected_language == UNKNOWN_LANGUAGE


def test_agent_uses_language_hint_when_llm_returns_none() -> None:
    output = AgentPageOutput(
        detected_language=None,
        entries=[LexicalEntry(lexeme=MDFField.literal("foo"))],
    )
    agent, _ = _make_agent([output])
    result = agent.run(page_number=1, page_text="foo", language_hint="zapoteco")
    assert result.detected_language == "zapoteco"
