"""PDF ingestion: page-by-page extraction with OCR fallback.

Design notes
------------
* Detection is **heuristic**, not cryptographic: we sample a configurable
  number of pages and measure the ratio of extracted characters to
  rendered page area. Pages falling below
  ``pdf_image_text_ratio_threshold`` are classified as image pages.
* Extraction is always per-page. Upstream code consumes the iterator
  and feeds each page to the MDF agent individually — this keeps token
  budgets bounded and makes progress observable.
* OCR is invoked automatically per-page when native extraction yields
  no usable text. If the tesseract binary is unavailable we degrade to
  returning the empty page + a warning; we never silently skip.
* The module is runnable in isolation (``python -m services.pdf_extractor
  path/to/file.pdf``), which requires that it bootstraps environment
  configuration via ``core.sync.bootstrap`` on demand.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pymupdf  # PyMuPDF

from core.config import get_settings
from core.sync import bootstrap, get_capabilities

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Value objects
# ----------------------------------------------------------------------
class PDFType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    MIXED = "mixed"


class ExtractionMethod(str, Enum):
    NATIVE = "native"
    OCR = "ocr"
    EMPTY = "empty"  # page had nothing we could extract


@dataclass(frozen=True)
class DetectionReport:
    """Outcome of ``detect_pdf_type``."""

    type: PDFType
    pages_analyzed: int
    confidence: float
    text_pages: int
    image_pages: int
    total_pages: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "pages_analyzed": self.pages_analyzed,
            "confidence": round(self.confidence, 4),
            "text_pages": self.text_pages,
            "image_pages": self.image_pages,
            "total_pages": self.total_pages,
        }


@dataclass(frozen=True)
class PageExtraction:
    """Result of extracting a single page."""

    page_number: int  # 1-based
    text_blocks: list[str]
    extraction_method: ExtractionMethod
    warnings: list[str]

    @property
    def raw_text(self) -> str:
        return "\n\n".join(self.text_blocks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "text_blocks": self.text_blocks,
            "extraction_method": self.extraction_method.value,
            "warnings": self.warnings,
        }


# ----------------------------------------------------------------------
# Detection
# ----------------------------------------------------------------------
def _classify_page_as_image(page: pymupdf.Page, threshold: float) -> bool:
    """Return True if the page looks image-based using char/area density."""
    text = page.get_text("text") or ""
    area = max(page.rect.width * page.rect.height, 1.0)
    density = len(text.strip()) / area
    return density < threshold


def detect_pdf_type(source: str | Path | bytes) -> DetectionReport:
    """Sample pages to decide whether the document is text, image, or mixed.

    Parameters
    ----------
    source
        File path or in-memory bytes. Useful to accept both CLI usage
        and uploaded ``SpooledTemporaryFile`` buffers.
    """
    settings = get_settings()
    doc = _open_doc(source)
    try:
        total_pages = doc.page_count
        if total_pages == 0:
            return DetectionReport(PDFType.TEXT, 0, 0.0, 0, 0, 0)

        sample_size = min(settings.pdf_page_sample_size, total_pages)
        # Evenly spaced sample across the document so we don't over-weight
        # cover pages or appendices.
        step = max(total_pages // sample_size, 1)
        indices = list(range(0, total_pages, step))[:sample_size]

        text_pages = 0
        image_pages = 0
        for idx in indices:
            page = doc.load_page(idx)
            if _classify_page_as_image(page, settings.pdf_image_text_ratio_threshold):
                image_pages += 1
            else:
                text_pages += 1

        if text_pages == sample_size:
            pdf_type = PDFType.TEXT
            confidence = 1.0
        elif image_pages == sample_size:
            pdf_type = PDFType.IMAGE
            confidence = 1.0
        else:
            pdf_type = PDFType.MIXED
            # Confidence = how lopsided the split is (1.0 = unanimous).
            dominant = max(text_pages, image_pages)
            confidence = dominant / sample_size

        return DetectionReport(
            type=pdf_type,
            pages_analyzed=sample_size,
            confidence=confidence,
            text_pages=text_pages,
            image_pages=image_pages,
            total_pages=total_pages,
        )
    finally:
        doc.close()


# ----------------------------------------------------------------------
# Page extraction
# ----------------------------------------------------------------------
def _native_blocks(page: pymupdf.Page) -> list[str]:
    """Return text blocks preserving reading order as PyMuPDF reports them."""
    raw_blocks = page.get_text("blocks") or []
    # PyMuPDF returns tuples: (x0, y0, x1, y1, text, block_no, block_type).
    # block_type == 0 means text; non-zero are images. Keep text blocks only
    # and sort by (y0, x0) to enforce left-to-right, top-to-bottom order.
    text_blocks = [b for b in raw_blocks if len(b) >= 7 and b[6] == 0 and b[4]]
    text_blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
    return [str(b[4]).strip() for b in text_blocks if str(b[4]).strip()]


def _ocr_page(page: pymupdf.Page) -> tuple[list[str], list[str]]:
    """Rasterize the page and run tesseract. Returns (blocks, warnings)."""
    caps = get_capabilities()
    warnings: list[str] = []
    if not caps.ocr_available:
        warnings.append(
            f"OCR fallback requested but unavailable: {caps.ocr_error or 'unknown error'}"
        )
        return [], warnings

    # Deferred imports so the module loads even without Pillow/pytesseract
    # installed when OCR is not needed.
    import pytesseract
    from PIL import Image

    settings = get_settings()
    pixmap = page.get_pixmap(dpi=settings.ocr_dpi, alpha=False)
    img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    try:
        text = pytesseract.image_to_string(img, lang=settings.ocr_languages)
    except pytesseract.TesseractError as exc:
        warnings.append(f"tesseract failed: {exc}")
        return [], warnings

    # Split on blank lines to approximate blocks.
    blocks = [blk.strip() for blk in text.split("\n\n") if blk.strip()]
    return blocks, warnings


def extract_page(doc: pymupdf.Document, page_index: int) -> PageExtraction:
    """Extract a single page (native first, OCR fallback)."""
    settings = get_settings()
    page = doc.load_page(page_index)
    warnings: list[str] = []

    blocks = _native_blocks(page)
    if blocks:
        return PageExtraction(
            page_number=page_index + 1,
            text_blocks=blocks,
            extraction_method=ExtractionMethod.NATIVE,
            warnings=warnings,
        )

    # Native failed — try OCR.
    log.info(
        "Page %s has no native text (threshold=%.4f); falling back to OCR.",
        page_index + 1,
        settings.pdf_image_text_ratio_threshold,
    )
    ocr_blocks, ocr_warnings = _ocr_page(page)
    warnings.extend(ocr_warnings)
    if ocr_blocks:
        return PageExtraction(
            page_number=page_index + 1,
            text_blocks=ocr_blocks,
            extraction_method=ExtractionMethod.OCR,
            warnings=warnings,
        )

    warnings.append("page yielded no text from either native extraction or OCR")
    return PageExtraction(
        page_number=page_index + 1,
        text_blocks=[],
        extraction_method=ExtractionMethod.EMPTY,
        warnings=warnings,
    )


def iter_pages(
    source: str | Path | bytes,
    *,
    max_pages: int | None = None,
) -> Iterator[PageExtraction]:
    """Yield :class:`PageExtraction` objects one page at a time.

    The generator owns the lifetime of the underlying PyMuPDF document:
    callers can stop iterating early (e.g. on a budget cap) without
    leaking handles.
    """
    doc = _open_doc(source)
    try:
        total = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
        for i in range(total):
            yield extract_page(doc, i)
    finally:
        doc.close()


def extract_all(
    source: str | Path | bytes, *, max_pages: int | None = None
) -> list[PageExtraction]:
    """Eagerly materialize every page. Use the iterator for large PDFs."""
    return list(iter_pages(source, max_pages=max_pages))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _open_doc(source: str | Path | bytes) -> pymupdf.Document:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"PDF not found: {path}")
        return pymupdf.open(path)
    if isinstance(source, (bytes, bytearray)):
        return pymupdf.open(stream=io.BytesIO(source), filetype="pdf")
    raise TypeError(f"Unsupported PDF source type: {type(source).__name__}")


# ----------------------------------------------------------------------
# CLI entry point for isolated testing:
#     python -m services.pdf_extractor sample.pdf
# ----------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json
    import sys

    bootstrap()  # standalone mode: load .env if main.py wasn't the entry.

    parser = argparse.ArgumentParser(description="Inspect a PDF's extraction profile.")
    parser.add_argument("pdf", help="Path to the PDF file.")
    parser.add_argument(
        "--max-pages", type=int, default=3, help="Maximum pages to print (default: 3)."
    )
    args = parser.parse_args()

    report = detect_pdf_type(args.pdf)
    print(json.dumps({"detection": report.as_dict()}, indent=2, ensure_ascii=False))

    for page in iter_pages(args.pdf, max_pages=args.max_pages):
        print(json.dumps(page.as_dict(), indent=2, ensure_ascii=False), file=sys.stdout)
