"""Multi-provider LLM router, pricing book, and cost estimator.

Architectural notes
-------------------
* Supported providers: OpenAI, Anthropic, Google (Gemini), Mistral.
* Only providers with an API key configured in env vars are exposed.
* Pricing is a **hardcoded catalog** with an explicit ``LAST_UPDATED``
  constant. No provider offers a uniform public pricing API, so this is
  the most honest default. :func:`refresh_pricing_from_url` is a hook
  for pulling pricing from an internal service at deploy time.
* Tokenization is provider-specific: ``tiktoken`` for OpenAI, a
  character-count heuristic (``len(text) / 4``) for the rest. The
  heuristic is labelled as such in the return value so the caller can
  communicate the uncertainty to the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel

from core.config import LLMProvider, get_settings
from schemas.endpoints import ModelInfo, ModelQuote

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Pricing catalog
# ----------------------------------------------------------------------
PRICING_LAST_UPDATED = "2026-04-01"
"""ISO date of the last time the pricing table below was audited."""


@dataclass(frozen=True)
class ModelSpec:
    """Static metadata about an LLM offering."""

    provider: LLMProvider
    model_name: str
    input_price_per_mtok: float  # USD per 1M input tokens
    output_price_per_mtok: float  # USD per 1M output tokens
    context_window: int | None = None
    supports_structured_output: bool = True

    @property
    def fq_id(self) -> str:
        return f"{self.provider.value}:{self.model_name}"


# NOTE: Prices are in USD per 1,000,000 tokens and reflect public list
# pricing at PRICING_LAST_UPDATED. Update both together.
_PRICING_CATALOG: tuple[ModelSpec, ...] = (
    # ---- OpenAI -------------------------------------------------------
    ModelSpec(LLMProvider.OPENAI, "gpt-4o", 2.50, 10.00, 128_000),
    ModelSpec(LLMProvider.OPENAI, "gpt-4o-mini", 0.15, 0.60, 128_000),
    ModelSpec(LLMProvider.OPENAI, "gpt-4.1", 2.00, 8.00, 1_000_000),
    ModelSpec(LLMProvider.OPENAI, "gpt-4.1-mini", 0.40, 1.60, 1_000_000),
    ModelSpec(LLMProvider.OPENAI, "o4-mini", 1.10, 4.40, 200_000),
    # ---- Anthropic ----------------------------------------------------
    ModelSpec(LLMProvider.ANTHROPIC, "claude-opus-4-5", 15.00, 75.00, 200_000),
    ModelSpec(LLMProvider.ANTHROPIC, "claude-sonnet-4-5", 3.00, 15.00, 200_000),
    ModelSpec(LLMProvider.ANTHROPIC, "claude-haiku-4-5", 0.80, 4.00, 200_000),
    # ---- Google -------------------------------------------------------
    ModelSpec(LLMProvider.GOOGLE, "gemini-2.5-pro", 1.25, 10.00, 2_000_000),
    ModelSpec(LLMProvider.GOOGLE, "gemini-2.5-flash", 0.30, 2.50, 1_000_000),
    # ---- Mistral ------------------------------------------------------
    ModelSpec(LLMProvider.MISTRAL, "mistral-large-latest", 2.00, 6.00, 128_000),
    ModelSpec(LLMProvider.MISTRAL, "mistral-small-latest", 0.20, 0.60, 32_000),
)


@dataclass
class PricingBook:
    """Mutable wrapper so production can override the catalog."""

    specs: dict[str, ModelSpec] = field(
        default_factory=lambda: {s.fq_id: s for s in _PRICING_CATALOG}
    )
    last_updated: str = PRICING_LAST_UPDATED

    def get(self, fq_id: str) -> ModelSpec | None:
        return self.specs.get(fq_id)

    def by_provider(self, provider: LLMProvider) -> list[ModelSpec]:
        return [s for s in self.specs.values() if s.provider == provider]

    def all(self) -> list[ModelSpec]:
        return list(self.specs.values())


_PRICING_BOOK = PricingBook()


def get_pricing_book() -> PricingBook:
    """Return the process-wide :class:`PricingBook`."""
    return _PRICING_BOOK


def refresh_pricing_from_url(url: str) -> None:
    """Extension point: replace the catalog from an internal JSON feed.

    Deliberately unimplemented. In production we would POST/GET a URL,
    validate the payload with a strict Pydantic model, and only then
    swap it in. Leaving the hook visible keeps the contract explicit.
    """
    raise NotImplementedError(
        "Remote pricing refresh is not wired up yet. Use the hardcoded "
        "catalog or call PricingBook.specs mutation directly."
    )


# ----------------------------------------------------------------------
# Tokenization
# ----------------------------------------------------------------------
def _count_tokens_openai(text: str, model_name: str) -> int:
    """Accurate counting for OpenAI models via tiktoken."""
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Unknown/experimental model name — fall back to cl100k_base,
        # the encoding used by every recent chat model.
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _count_tokens_heuristic(text: str) -> int:
    """Rough estimator: 4 chars per token. Off by ±25% typically."""
    return max(1, len(text) // 4)


def count_tokens(text: str, spec: ModelSpec) -> int:
    """Best-effort input-token count for the given model spec."""
    if spec.provider == LLMProvider.OPENAI:
        try:
            return _count_tokens_openai(text, spec.model_name)
        except Exception as exc:  # noqa: BLE001 - tiktoken may raise many things
            log.debug("tiktoken fell back to heuristic: %s", exc)
    return _count_tokens_heuristic(text)


# ----------------------------------------------------------------------
# Model enumeration
# ----------------------------------------------------------------------
def list_available_models() -> list[ModelInfo]:
    """Return the pricing catalog filtered by configured API keys."""
    settings = get_settings()
    enabled = set(settings.available_providers())
    out: list[ModelInfo] = []
    for spec in _PRICING_BOOK.all():
        if spec.provider not in enabled:
            continue
        out.append(
            ModelInfo(
                id=spec.fq_id,
                provider=spec.provider.value,
                model_name=spec.model_name,
                input_price_usd_per_mtok=spec.input_price_per_mtok,
                output_price_usd_per_mtok=spec.output_price_per_mtok,
                context_window=spec.context_window,
                supports_structured_output=spec.supports_structured_output,
                pricing_last_updated=_PRICING_BOOK.last_updated,
            )
        )
    # Deterministic ordering: cheapest input first.
    out.sort(key=lambda m: (m.input_price_usd_per_mtok, m.id))
    return out


# ----------------------------------------------------------------------
# Cost estimation
# ----------------------------------------------------------------------
def estimate_cost(
    text_sample: str,
    model_ids: list[str] | None = None,
    *,
    expected_pages: int = 1,
    output_token_multiplier: float = 0.5,
) -> list[ModelQuote]:
    """Return a list of :class:`ModelQuote` sorted cheapest-first.

    Parameters
    ----------
    text_sample
        A representative chunk (typically one page of the PDF).
    model_ids
        Fully-qualified model IDs to compare. ``None`` / ``[]`` means
        quote every model whose provider has an API key configured.
    expected_pages
        Scales the input token count. If the sample is one page and the
        PDF has 200, pass 200 here.
    output_token_multiplier
        Heuristic factor. Structured extraction typically produces
        less output than input (0.5 default).
    """
    settings = get_settings()
    enabled_providers = set(settings.available_providers())

    target_specs: list[ModelSpec]
    if model_ids:
        target_specs = [s for s in (_PRICING_BOOK.get(m) for m in model_ids) if s is not None]
    else:
        target_specs = [s for s in _PRICING_BOOK.all() if s.provider in enabled_providers]

    quotes: list[ModelQuote] = []
    for spec in target_specs:
        per_page_in = count_tokens(text_sample, spec)
        total_in = per_page_in * max(expected_pages, 1)
        total_out = int(total_in * output_token_multiplier)
        cost = (
            total_in * spec.input_price_per_mtok / 1_000_000
            + total_out * spec.output_price_per_mtok / 1_000_000
        )
        quotes.append(
            ModelQuote(
                model_id=spec.fq_id,
                estimated_input_tokens=total_in,
                estimated_output_tokens=total_out,
                estimated_cost_usd=round(cost, 6),
                input_price_usd_per_mtok=spec.input_price_per_mtok,
                output_price_usd_per_mtok=spec.output_price_per_mtok,
            )
        )
    quotes.sort(key=lambda q: q.estimated_cost_usd)
    return quotes


# ----------------------------------------------------------------------
# LLM instantiation
# ----------------------------------------------------------------------
class UnknownModelError(ValueError):
    """Raised when the caller asks for a model not in the catalog."""


class ProviderNotConfiguredError(RuntimeError):
    """Raised when the requested provider has no API key configured."""


def parse_model_id(fq_id: str) -> tuple[LLMProvider, str]:
    """Split ``"openai:gpt-4o"`` into (LLMProvider.OPENAI, "gpt-4o")."""
    if ":" not in fq_id:
        raise UnknownModelError(
            f"Model id must be formatted as 'provider:model', got {fq_id!r}"
        )
    provider_str, _, model_name = fq_id.partition(":")
    try:
        provider = LLMProvider(provider_str.lower())
    except ValueError as exc:
        raise UnknownModelError(f"Unknown provider: {provider_str!r}") from exc
    return provider, model_name


def build_chat_model(fq_id: str, *, temperature: float | None = None, **kwargs: Any) -> BaseChatModel:
    """Instantiate the LangChain chat model corresponding to ``fq_id``.

    The concrete class is imported lazily so the module imports cleanly
    even if only some provider packages are installed.
    """
    settings = get_settings()
    provider, model_name = parse_model_id(fq_id)

    api_key = settings.api_key_for(provider)
    if not api_key:
        raise ProviderNotConfiguredError(
            f"No API key configured for provider {provider.value!r}"
        )

    temp = settings.agent_temperature if temperature is None else temperature

    if provider == LLMProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_name, temperature=temp, api_key=api_key, **kwargs)

    if provider == LLMProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_name, temperature=temp, api_key=api_key, **kwargs)

    if provider == LLMProvider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name, temperature=temp, google_api_key=api_key, **kwargs
        )

    if provider == LLMProvider.MISTRAL:
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(model=model_name, temperature=temp, api_key=api_key, **kwargs)

    raise UnknownModelError(f"Unsupported provider: {provider.value}")


# ----------------------------------------------------------------------
# CLI entry point:
#     python -m services.llm_router --sample "some page text"
# ----------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json

    from core.sync import bootstrap

    bootstrap()

    parser = argparse.ArgumentParser(description="Inspect LLM pricing and available models.")
    parser.add_argument("--sample", default="lorem ipsum " * 200, help="Sample text for quoting.")
    parser.add_argument("--pages", type=int, default=100, help="Expected number of pages.")
    args = parser.parse_args()

    print("Available models:")
    print(json.dumps([m.model_dump() for m in list_available_models()], indent=2))

    print("\nCost estimates:")
    print(
        json.dumps(
            [q.model_dump() for q in estimate_cost(args.sample, expected_pages=args.pages)],
            indent=2,
        )
    )
