"""Request and response contracts for the FastAPI layer.

These are kept strictly separate from the MDF data model
(``schemas/parser.py``). Endpoints consume and produce wrappers defined
here; internal services use the MDF models directly.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from schemas.parser import MDFDictionary


class ExtractionOrder(str, Enum):
    DOCUMENT = "document_order"
    ALPHABETICAL = "alphabetical"


# ----------------------------------------------------------------------
# /api/v1/extract
# ----------------------------------------------------------------------
class ExtractionRequest(BaseModel):
    """Parameters accompanying a PDF upload to ``/extract``.

    The PDF file itself travels as a multipart form field, not inside
    this model — FastAPI binds it separately.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        description="LLM identifier in the form ``provider:model`` (e.g. ``openai:gpt-4o``)."
    )
    language_hint: str | None = Field(
        default=None,
        description=(
            "Optional hint about the indigenous language of the dictionary "
            "(e.g. 'maya', 'nahuatl'). When omitted, the agent detects the "
            "language from content. If detection fails the metadata reports "
            "Unknown Language."
        ),
    )
    order: ExtractionOrder = Field(
        default=ExtractionOrder.DOCUMENT,
        description="Ordering of entries in the response.",
    )
    allow_ai_generation: bool = Field(
        default=False,
        description=(
            "If True, the agent may infer missing MDF fields. Inferred "
            "values are always tagged with ``ai_generated=True``. If "
            "False (default) missing fields are returned as null."
        ),
    )
    max_pages: int | None = Field(
        default=None,
        ge=1,
        description="Optional hard cap on pages to process (useful for demos).",
    )


class ExtractionResponse(BaseModel):
    """Top-level response of ``/extract``."""

    model_config = ConfigDict(extra="forbid")

    dictionary: MDFDictionary
    warnings: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------
# /api/v1/models
# ----------------------------------------------------------------------
class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Fully-qualified identifier, e.g. ``openai:gpt-4o``.")
    provider: str
    model_name: str
    input_price_usd_per_mtok: float = Field(
        ge=0.0, description="USD per 1,000,000 input tokens."
    )
    output_price_usd_per_mtok: float = Field(
        ge=0.0, description="USD per 1,000,000 output tokens."
    )
    context_window: int | None = Field(default=None, ge=0)
    supports_structured_output: bool = True
    pricing_last_updated: str = Field(description="ISO date of the pricing table entry.")


class ModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelInfo]


# ----------------------------------------------------------------------
# /api/v1/quote
# ----------------------------------------------------------------------
class ModelQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_sample: str = Field(
        min_length=1,
        description="Representative text chunk used to estimate token volume.",
    )
    models: list[str] = Field(
        default_factory=list,
        description=(
            "Fully-qualified model IDs to compare. Empty means quote every "
            "available model for which an API key is configured."
        ),
    )
    expected_pages: int = Field(
        default=1,
        ge=1,
        description="Number of pages the sample is representative of.",
    )
    output_token_multiplier: float = Field(
        default=0.5,
        ge=0.0,
        le=5.0,
        description=(
            "Heuristic ratio of output tokens to input tokens. The "
            "default (0.5) is a conservative estimate for structured "
            "extraction where the output is usually shorter than the "
            "page text."
        ),
    )


class ModelQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)
    input_price_usd_per_mtok: float = Field(ge=0.0)
    output_price_usd_per_mtok: float = Field(ge=0.0)


class ModelQuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotes: list[ModelQuote]  # sorted ascending by estimated_cost_usd
    cheapest_model_id: str | None = None
    pricing_last_updated: str


# ----------------------------------------------------------------------
# /api/v1/health
# ----------------------------------------------------------------------
class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    enabled: bool


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    app_env: str
    providers: list[ProviderHealth]
    ocr_available: bool
    ocr_error: str | None = None
