"""Service bootstrap and capability detection.

This module performs one-time initialization for services that share
state across requests (logging, OCR binary path, LLM router instance).
It is imported by ``main.py`` at startup and by services that need a
consistent view of the configured runtime.

``load_dotenv`` is invoked here **only if it has not been called
already**, and only when the module is executed outside the FastAPI
process (e.g. running ``services/*.py`` directly for ad-hoc tests).
``main.py`` is still the canonical entry point — this fallback exists
solely to satisfy the "each service can run in isolation" requirement.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache

from core.config import LLMProvider, Settings, get_settings

_DOTENV_LOADED_FLAG = "_MDF_DOTENV_LOADED"


def _ensure_dotenv_loaded() -> None:
    """Load .env if and only if main.py did not already load it.

    main.py sets ``os.environ["_MDF_DOTENV_LOADED"] = "1"`` after it
    calls ``load_dotenv``. When services are executed standalone
    (``python -m services.pdf_extractor``) that flag is absent and we
    load .env here so the module can still be used in isolation.
    """
    if os.environ.get(_DOTENV_LOADED_FLAG) == "1":
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv()
    os.environ[_DOTENV_LOADED_FLAG] = "1"


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Static snapshot of what the process can do at startup."""

    llm_providers: tuple[LLMProvider, ...]
    ocr_available: bool
    ocr_binary: str | None
    ocr_error: str | None


def _detect_ocr() -> tuple[bool, str | None, str | None]:
    """Check whether pytesseract + tesseract binary are both usable."""
    settings = get_settings()
    try:
        import pytesseract
    except ImportError as exc:
        return False, None, f"pytesseract not installed: {exc}"

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # noqa: BLE001 - we want any failure here
        return (
            False,
            settings.tesseract_cmd,
            f"tesseract binary not callable: {exc}",
        )
    return True, settings.tesseract_cmd or f"tesseract@{version}", None


def _configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.app_log_level, logging.INFO)
    # Idempotent: only configure if no handlers exist yet.
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            stream=sys.stdout,
        )
    else:
        root.setLevel(level)


@lru_cache(maxsize=1)
def bootstrap() -> RuntimeCapabilities:
    """Idempotent startup. Safe to call from main.py and from tests."""
    _ensure_dotenv_loaded()
    settings = get_settings()
    _configure_logging(settings)

    ocr_ok, ocr_bin, ocr_err = _detect_ocr()

    caps = RuntimeCapabilities(
        llm_providers=tuple(settings.available_providers()),
        ocr_available=ocr_ok,
        ocr_binary=ocr_bin,
        ocr_error=ocr_err,
    )

    log = logging.getLogger(__name__)
    log.info(
        "Runtime bootstrap complete. providers=%s ocr_available=%s",
        [p.value for p in caps.llm_providers],
        caps.ocr_available,
    )
    if not caps.ocr_available:
        log.warning("OCR fallback disabled: %s", caps.ocr_error)

    return caps


def get_capabilities() -> RuntimeCapabilities:
    """Return the cached :class:`RuntimeCapabilities`, bootstrapping if needed."""
    return bootstrap()
