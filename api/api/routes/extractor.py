"""Extractor API: the four endpoints required by the spec.

    POST /api/v1/extract     — Upload a PDF + params, get MDF response.
    GET  /api/v1/models      — List LLM models enabled by API keys present.
    POST /api/v1/quote       — Compare cost estimates across models.
    GET  /api/v1/health      — Providers + OCR capability snapshot.

Design notes
------------
* ``/extract`` is implemented synchronously because the hackathon demo
  expects a blocking request/response. For production we would replace
  this with a background task + polling endpoint; see the TODO at the
  end of :func:`extract_pdf`.
* Tokens consumed per page are summed and multiplied by the catalog
  price to compute the **actual** cost (not a heuristic estimate).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from core.config import get_settings
from core.sync import get_capabilities
from schemas.endpoints import (
    ExtractionOrder,
    ExtractionRequest,
    ExtractionResponse,
    HealthResponse,
    ModelQuote,
    ModelQuoteRequest,
    ModelQuoteResponse,
    ModelsResponse,
    ProviderHealth,
)
from schemas.parser import MDFDictionary, PDFMetadata
from services import llm_router
from services.mdf_agent import UNKNOWN_LANGUAGE, MDFPageAgent
from services.pdf_extractor import detect_pdf_type, iter_pages

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["extractor"])


# ----------------------------------------------------------------------
# /health
# ----------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse, summary="Liveness + provider snapshot")
def health() -> HealthResponse:
    settings = get_settings()
    caps = get_capabilities()
    available = {p.value for p in settings.available_providers()}

    providers = [
        ProviderHealth(provider=p, enabled=p in available)
        for p in ("openai", "anthropic", "google", "mistral")
    ]
    return HealthResponse(
        status="ok",
        app_env=settings.app_env.value,
        providers=providers,
        ocr_available=caps.ocr_available,
        ocr_error=caps.ocr_error,
    )


# ----------------------------------------------------------------------
# /models
# ----------------------------------------------------------------------
@router.get("/models", response_model=ModelsResponse, summary="List available LLM models")
def list_models() -> ModelsResponse:
    return ModelsResponse(models=llm_router.list_available_models())


# ----------------------------------------------------------------------
# /quote
# ----------------------------------------------------------------------
@router.post("/quote", response_model=ModelQuoteResponse, summary="Estimate extraction cost per model")
def quote(req: ModelQuoteRequest) -> ModelQuoteResponse:
    quotes: list[ModelQuote] = llm_router.estimate_cost(
        req.text_sample,
        model_ids=req.models or None,
        expected_pages=req.expected_pages,
        output_token_multiplier=req.output_token_multiplier,
    )
    cheapest = quotes[0].model_id if quotes else None
    return ModelQuoteResponse(
        quotes=quotes,
        cheapest_model_id=cheapest,
        pricing_last_updated=llm_router.get_pricing_book().last_updated,
    )


# ----------------------------------------------------------------------
# /extract
# ----------------------------------------------------------------------
@router.post(
    "/extract",
    response_model=ExtractionResponse,
    summary="Extract an indigenous dictionary PDF into MDF format",
)
async def extract_pdf(
    file: Annotated[UploadFile, File(description="PDF file to extract.")],
    model: Annotated[str, Form(description="provider:model identifier")],
    language_hint: Annotated[str | None, Form()] = None,
    order: Annotated[ExtractionOrder, Form()] = ExtractionOrder.DOCUMENT,
    allow_ai_generation: Annotated[bool, Form()] = False,
    max_pages: Annotated[int | None, Form()] = None,
) -> ExtractionResponse:
    settings = get_settings()

    # -- Input validation -------------------------------------------------
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a .pdf extension.",
        )

    pdf_bytes = await file.read()
    size_mb = len(pdf_bytes) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_mb} MB upload cap.",
        )

    # Validate the parameter bundle once through the Pydantic contract so
    # additional constraints (e.g. max_pages >= 1) fire consistently.
    params = ExtractionRequest(
        model=model,
        language_hint=language_hint,
        order=order,
        allow_ai_generation=allow_ai_generation,
        max_pages=max_pages,
    )

    spec = llm_router.get_pricing_book().get(params.model)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model id: {params.model!r}",
        )

    # -- Detection -------------------------------------------------------
    detection = detect_pdf_type(pdf_bytes)

    # -- LLM + agent wiring ---------------------------------------------
    try:
        llm = llm_router.build_chat_model(params.model)
    except llm_router.ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except llm_router.UnknownModelError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    agent = MDFPageAgent(llm)

    # -- Per-page extraction + classification ---------------------------
    all_entries = []
    page_errors = []
    warnings: list[str] = []
    detected_language: str | None = None
    total_input_tokens = 0

    # Materialize page extractions so we can fan out LLM calls in parallel.
    # Token counting stays inline (cheap, local, avoids a second pass).
    work: list = []
    for page_extraction in iter_pages(pdf_bytes, max_pages=params.max_pages):
        warnings.extend(page_extraction.warnings)
        if not page_extraction.raw_text:
            # Empty page — skip the LLM call entirely, no cost incurred.
            continue
        total_input_tokens += llm_router.count_tokens(page_extraction.raw_text, spec)
        work.append(page_extraction)

    sem = asyncio.Semaphore(settings.agent_max_concurrency)

    async def _run_page(pe):  # type: ignore[no-untyped-def]
        async with sem:
            return await asyncio.to_thread(
                agent.run,
                page_number=pe.page_number,
                page_text=pe.raw_text,
                language_hint=params.language_hint,
                allow_ai_generation=params.allow_ai_generation,
            )

    results = await asyncio.gather(*(_run_page(pe) for pe in work))

    # ``iter_pages`` yields in page order, and ``asyncio.gather`` preserves
    # the input order regardless of completion order, so ``results`` is
    # already page-ordered — no extra sort needed.
    for result in results:
        if result.error:
            page_errors.append(result.error)
            continue
        all_entries.extend(result.entries)
        if detected_language in (None, UNKNOWN_LANGUAGE) and result.detected_language:
            detected_language = result.detected_language

    detected_language = detected_language or params.language_hint or UNKNOWN_LANGUAGE

    # Estimate output tokens conservatively (0.5x input) then price it.
    estimated_output_tokens = int(total_input_tokens * 0.5)
    estimated_cost = round(
        total_input_tokens * spec.input_price_per_mtok / 1_000_000
        + estimated_output_tokens * spec.output_price_per_mtok / 1_000_000,
        6,
    )

    metadata = PDFMetadata(
        source_file=file.filename,
        total_pages=detection.total_pages,
        pdf_type=detection.type.value,
        language=detected_language,
        model_used=params.model,
        estimated_cost_usd=estimated_cost,
        extraction_order=params.order.value,
    )

    dictionary = MDFDictionary(
        metadata=metadata,
        entries=all_entries,
        pages_with_errors=page_errors,
        total_entries_extracted=len(all_entries),
    )

    if params.order == ExtractionOrder.ALPHABETICAL:
        dictionary = dictionary.sort_alphabetical()

    # TODO(production): offload to a background worker and return a job
    # id the client can poll. Current implementation blocks the request
    # for the duration of the entire extraction.
    return ExtractionResponse(dictionary=dictionary, warnings=warnings)
