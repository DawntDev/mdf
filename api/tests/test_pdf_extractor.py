"""Unit tests for services/pdf_extractor.py.

We synthesize PDFs in memory with PyMuPDF — no test fixtures on disk.
OCR codepaths are covered only indirectly (no tesseract in CI); the
classification heuristic is what this file exercises rigorously.
"""

from __future__ import annotations

import io

import pymupdf
import pytest

from services.pdf_extractor import (
    ExtractionMethod,
    PDFType,
    detect_pdf_type,
    extract_all,
    iter_pages,
)


# ----------------------------------------------------------------------
# Synthetic PDF builders
# ----------------------------------------------------------------------
def _make_text_pdf(pages_text: list[str]) -> bytes:
    """Build a PDF whose every page has dense native text.

    ``pdf_image_text_ratio_threshold`` defaults to 0.02, which on a
    letter page requires ~10k chars. PyMuPDF's ``insert_text`` silently
    clips anything that overruns the page width, so we pad each input
    to a fixed line length and tile the full page at a small fontsize.
    """
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        filler = (text + " ") * max(1, 140 // (len(text) + 1) + 1)
        line = filler[:140]
        y = 50.0
        while y < 790.0:
            page.insert_text((30, y), line, fontsize=4)
            y += 5.0
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_blank_pdf(num_pages: int = 1) -> bytes:
    """Build a PDF whose pages have no text at all (proxy for scanned image)."""
    doc = pymupdf.open()
    for _ in range(num_pages):
        doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ----------------------------------------------------------------------
# detect_pdf_type
# ----------------------------------------------------------------------
def test_detect_pdf_type_text_only() -> None:
    pdf = _make_text_pdf(["a" * 500] * 3)
    report = detect_pdf_type(pdf)
    assert report.type == PDFType.TEXT
    assert report.total_pages == 3
    assert report.image_pages == 0


def test_detect_pdf_type_image_only() -> None:
    pdf = _make_blank_pdf(3)
    report = detect_pdf_type(pdf)
    assert report.type == PDFType.IMAGE
    assert report.text_pages == 0


# Note: zero-page detection is not covered here — PyMuPDF refuses to
# serialize a Document with ``page_count == 0``, so we cannot build a
# valid empty-PDF fixture in memory. The behavior is exercised by the
# explicit ``total_pages == 0`` branch in ``detect_pdf_type``.


# ----------------------------------------------------------------------
# Page extraction
# ----------------------------------------------------------------------
def test_iter_pages_native_extraction_preserves_content() -> None:
    pdf = _make_text_pdf(["hola mundo", "balam jaguar"])
    pages = list(iter_pages(pdf))
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].extraction_method == ExtractionMethod.NATIVE
    # PyMuPDF may wrap the text in multiple blocks; check the flattened form.
    assert "hola" in pages[0].raw_text
    assert "balam" in pages[1].raw_text


def test_iter_pages_respects_max_pages() -> None:
    pdf = _make_text_pdf(["one", "two", "three", "four"])
    pages = extract_all(pdf, max_pages=2)
    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 2]


def test_open_doc_rejects_unknown_source_type() -> None:
    from services.pdf_extractor import _open_doc

    with pytest.raises(TypeError):
        _open_doc(12345)  # type: ignore[arg-type]


def test_open_doc_missing_file_raises() -> None:
    from services.pdf_extractor import _open_doc

    with pytest.raises(FileNotFoundError):
        _open_doc("c:/definitely/not/a/real/path.pdf")
