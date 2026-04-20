"""Unit tests for schemas/parser.py and schemas/endpoints.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.endpoints import (
    ExtractionOrder,
    ExtractionRequest,
    ModelQuoteRequest,
)
from schemas.parser import (
    LexicalEntry,
    MDFDictionary,
    MDFField,
    PageError,
    PDFMetadata,
)


# ----------------------------------------------------------------------
# MDFField
# ----------------------------------------------------------------------
def test_mdffield_literal_factory_sets_flag_false() -> None:
    field = MDFField.literal("balam")
    assert field.value == "balam"
    assert field.ai_generated is False


def test_mdffield_inferred_factory_sets_flag_true() -> None:
    field = MDFField.inferred("jaguar")
    assert field.value == "jaguar"
    assert field.ai_generated is True


def test_mdffield_inferred_with_none_stays_literal() -> None:
    field = MDFField.inferred(None)
    assert field.value is None
    assert field.ai_generated is False


def test_mdffield_rejects_null_with_ai_flag() -> None:
    with pytest.raises(ValidationError):
        MDFField(value=None, ai_generated=True)


def test_mdffield_blank_string_normalizes_to_none() -> None:
    field = MDFField(value="   ")
    assert field.value is None


# ----------------------------------------------------------------------
# LexicalEntry
# ----------------------------------------------------------------------
def test_lexical_entry_requires_non_empty_lexeme() -> None:
    with pytest.raises(ValidationError):
        LexicalEntry(lexeme=MDFField())  # null value


def test_lexical_entry_default_fields_are_null() -> None:
    entry = LexicalEntry(lexeme=MDFField.literal("balam"))
    assert entry.definition_es.value is None
    assert entry.definition_es.ai_generated is False


def test_lexical_entry_round_trip_via_mdf_markers() -> None:
    entry = LexicalEntry.from_mdf_markers(
        {"\\lx": "balam", "\\ps": "n", "\\dn": "jaguar"},
        source_page=3,
    )
    assert entry.lexeme.value == "balam"
    assert entry.part_of_speech.value == "n"
    assert entry.definition_es.value == "jaguar"
    assert entry.source_page == 3

    rendered = entry.to_mdf_markers()
    assert "\\lx balam" in rendered
    assert "\\ps n" in rendered
    assert "\\dn jaguar" in rendered


def test_lexical_entry_marks_ai_generated_tags() -> None:
    entry = LexicalEntry.from_mdf_markers(
        {"\\lx": "balam", "\\dn": "jaguar"},
        ai_generated_tags={"\\dn"},
    )
    assert entry.lexeme.ai_generated is False
    assert entry.definition_es.ai_generated is True


# ----------------------------------------------------------------------
# MDFDictionary
# ----------------------------------------------------------------------
def _dummy_metadata() -> PDFMetadata:
    return PDFMetadata(
        source_file="test.pdf",
        total_pages=1,
        pdf_type="text",
        model_used="openai:gpt-4o-mini",
        estimated_cost_usd=0.0,
    )


def test_mdfdictionary_auto_counts_entries() -> None:
    entries = [LexicalEntry(lexeme=MDFField.literal("balam"))]
    dic = MDFDictionary(metadata=_dummy_metadata(), entries=entries)
    assert dic.total_entries_extracted == 1


def test_mdfdictionary_rejects_mismatched_count() -> None:
    with pytest.raises(ValidationError):
        MDFDictionary(
            metadata=_dummy_metadata(),
            entries=[LexicalEntry(lexeme=MDFField.literal("x"))],
            total_entries_extracted=5,
        )


def test_mdfdictionary_sort_alphabetical_preserves_metadata_marker() -> None:
    entries = [
        LexicalEntry(lexeme=MDFField.literal("zorro"), source_page=1),
        LexicalEntry(lexeme=MDFField.literal("balam"), source_page=2),
    ]
    dic = MDFDictionary(metadata=_dummy_metadata(), entries=entries)
    sorted_dic = dic.sort_alphabetical()
    assert [e.lexeme.value for e in sorted_dic.entries] == ["balam", "zorro"]
    assert sorted_dic.metadata.extraction_order == "alphabetical"


def test_page_error_is_serializable() -> None:
    err = PageError(page_number=4, error_type="agent_failure", message="llm timeout")
    assert err.model_dump() == {
        "page_number": 4,
        "error_type": "agent_failure",
        "message": "llm timeout",
    }


# ----------------------------------------------------------------------
# Endpoint contracts
# ----------------------------------------------------------------------
def test_extraction_request_defaults() -> None:
    req = ExtractionRequest(model="openai:gpt-4o")
    assert req.allow_ai_generation is False
    assert req.order == ExtractionOrder.DOCUMENT
    assert req.language_hint is None


def test_extraction_request_rejects_bad_max_pages() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(model="openai:gpt-4o", max_pages=0)


def test_model_quote_request_rejects_empty_sample() -> None:
    with pytest.raises(ValidationError):
        ModelQuoteRequest(text_sample="")
