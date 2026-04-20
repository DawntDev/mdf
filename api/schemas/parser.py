"""Pydantic schemas for the Machine-Readable Dictionary Format (MDF).

Every textual field is wrapped in :class:`MDFField` which attaches a
boolean ``ai_generated`` flag. The flag is set to ``True`` only when the
content was inferred by the LLM and not copied verbatim from the source
document. This makes the provenance of every value auditable.

Only ``\\lx`` (lexeme) is required — the MDF standard allows every
other field to be absent for an entry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MDFField(BaseModel):
    """A single MDF value with a provenance flag.

    ``value`` holds the extracted text (or ``None`` if absent).
    ``ai_generated`` is ``True`` only when the value was produced by the
    LLM without literal support in the source text.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    value: str | None = None
    ai_generated: bool = False

    @field_validator("value", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _null_cannot_be_ai(self) -> MDFField:
        # A null value cannot carry ai_generated=True; that would be meaningless.
        if self.value is None and self.ai_generated:
            raise ValueError("ai_generated=True is not valid when value is None")
        return self

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------
    @classmethod
    def literal(cls, value: str | None) -> MDFField:
        """Build a field whose value was copied verbatim from the source."""
        return cls(value=value, ai_generated=False)

    @classmethod
    def inferred(cls, value: str | None) -> MDFField:
        """Build a field whose value was inferred by the LLM."""
        if value is None:
            return cls(value=None, ai_generated=False)
        return cls(value=value, ai_generated=True)


class LexicalEntry(BaseModel):
    """A single lexical entry, mapped to the full MDF tag set.

    Field order mirrors the MDF standard. Python attribute names use
    descriptive identifiers; the ``MDF_TAGS`` class variable maps the
    raw backslash markers back to attribute names for serialization.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # \id - entry identifier
    id: MDFField = Field(default_factory=MDFField)
    # \lx - lexeme (headword) — the only truly required field
    lexeme: MDFField
    # \ps - part of speech
    part_of_speech: MDFField = Field(default_factory=MDFField)
    # \sn - sense number
    sense_number: MDFField = Field(default_factory=MDFField)
    # \se - subentry
    subentry: MDFField = Field(default_factory=MDFField)
    # \ph - phonetic transcription
    phonetic_transcription: MDFField = Field(default_factory=MDFField)
    # \mr - morphological representation
    morphological_representation: MDFField = Field(default_factory=MDFField)
    # \de - definition in English
    definition_en: MDFField = Field(default_factory=MDFField)
    # \dn - definition in Spanish
    definition_es: MDFField = Field(default_factory=MDFField)
    # \ge - gloss in English
    gloss_en: MDFField = Field(default_factory=MDFField)
    # \gn - gloss in Spanish
    gloss_es: MDFField = Field(default_factory=MDFField)
    # \xv - example in the vernacular (target language)
    example_vernacular: MDFField = Field(default_factory=MDFField)
    # \xe - example translation into English
    example_translation_en: MDFField = Field(default_factory=MDFField)
    # \xn - example translation into Spanish
    example_translation_es: MDFField = Field(default_factory=MDFField)
    # \rf - source / reference for the example
    example_source: MDFField = Field(default_factory=MDFField)
    # \cf - cross-reference to another entry
    cross_reference: MDFField = Field(default_factory=MDFField)
    # \lf - lexical function label
    lexical_function: MDFField = Field(default_factory=MDFField)
    # \lv - related lexeme for the lexical function
    related_lexeme: MDFField = Field(default_factory=MDFField)
    # \wv - audio file reference
    audio_file: MDFField = Field(default_factory=MDFField)
    # \vd - video file reference
    video_file: MDFField = Field(default_factory=MDFField)
    # \nt - general notes
    general_notes: MDFField = Field(default_factory=MDFField)
    # \et - etymology
    etymology: MDFField = Field(default_factory=MDFField)
    # \sc - scientific name
    scientific_name: MDFField = Field(default_factory=MDFField)
    # \lo - location
    location: MDFField = Field(default_factory=MDFField)
    # \pc - image file reference
    image_file: MDFField = Field(default_factory=MDFField)

    # Provenance metadata (not part of MDF itself, but essential for UX)
    source_page: int | None = Field(
        default=None,
        ge=1,
        description="1-based page number of the source PDF where this entry was found.",
    )

    # ------------------------------------------------------------------
    # Class-level marker registry
    # ------------------------------------------------------------------
    MDF_TAGS: ClassVar[dict[str, str]] = {
        "\\id": "id",
        "\\lx": "lexeme",
        "\\ps": "part_of_speech",
        "\\sn": "sense_number",
        "\\se": "subentry",
        "\\ph": "phonetic_transcription",
        "\\mr": "morphological_representation",
        "\\de": "definition_en",
        "\\dn": "definition_es",
        "\\ge": "gloss_en",
        "\\gn": "gloss_es",
        "\\xv": "example_vernacular",
        "\\xe": "example_translation_en",
        "\\xn": "example_translation_es",
        "\\rf": "example_source",
        "\\cf": "cross_reference",
        "\\lf": "lexical_function",
        "\\lv": "related_lexeme",
        "\\wv": "audio_file",
        "\\vd": "video_file",
        "\\nt": "general_notes",
        "\\et": "etymology",
        "\\sc": "scientific_name",
        "\\lo": "location",
        "\\pc": "image_file",
    }

    # ------------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _lexeme_required(self) -> LexicalEntry:
        if not self.lexeme or not self.lexeme.value:
            raise ValueError("LexicalEntry.lexeme.value is required and cannot be empty")
        return self

    # ------------------------------------------------------------------
    # Interop helpers
    # ------------------------------------------------------------------
    def to_mdf_markers(self) -> str:
        """Serialize back to raw MDF marker format (e.g. ``\\lx foo``)."""
        lines: list[str] = []
        for marker, attr in self.MDF_TAGS.items():
            field: MDFField = getattr(self, attr)
            if field.value:
                lines.append(f"{marker} {field.value}")
        return "\n".join(lines)

    @classmethod
    def from_mdf_markers(
        cls,
        markers: dict[str, str],
        *,
        ai_generated_tags: set[str] | None = None,
        source_page: int | None = None,
    ) -> LexicalEntry:
        """Build an entry from a dict keyed by MDF backslash markers.

        ``ai_generated_tags`` contains the set of markers whose values
        were inferred by the LLM (vs copied from source).
        """
        ai_tags = ai_generated_tags or set()
        fields: dict[str, MDFField] = {}
        for marker, attr in cls.MDF_TAGS.items():
            raw = markers.get(marker)
            if raw is None:
                fields[attr] = MDFField()
            elif marker in ai_tags:
                fields[attr] = MDFField.inferred(raw)
            else:
                fields[attr] = MDFField.literal(raw)
        return cls(**fields, source_page=source_page)


class PDFMetadata(BaseModel):
    """Metadata attached to a :class:`MDFDictionary` response."""

    model_config = ConfigDict(extra="forbid")

    source_file: str
    total_pages: int = Field(ge=0)
    pdf_type: str  # "text" | "image" | "mixed"
    language: str | None = None
    model_used: str
    estimated_cost_usd: float = Field(ge=0.0)
    extraction_order: str = "document_order"  # or "alphabetical"
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PageError(BaseModel):
    """Captures a page that failed extraction after all retries."""

    model_config = ConfigDict(extra="forbid")

    page_number: int
    error_type: str
    message: str


class MDFDictionary(BaseModel):
    """Root response body for a full extraction."""

    model_config = ConfigDict(extra="forbid")

    metadata: PDFMetadata
    entries: list[LexicalEntry]
    pages_with_errors: list[PageError] = Field(default_factory=list)
    total_entries_extracted: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _count_matches_list(self) -> MDFDictionary:
        # Keep total_entries_extracted consistent with the list length.
        if self.total_entries_extracted == 0 and self.entries:
            self.total_entries_extracted = len(self.entries)
        elif self.total_entries_extracted != len(self.entries):
            raise ValueError(
                "total_entries_extracted does not match entries list length: "
                f"{self.total_entries_extracted} vs {len(self.entries)}"
            )
        return self

    def sort_alphabetical(self) -> MDFDictionary:
        """Return a copy whose entries are sorted by lexeme (case-insensitive)."""
        sorted_entries = sorted(
            self.entries,
            key=lambda e: (e.lexeme.value or "").casefold(),
        )
        updated_meta = self.metadata.model_copy(update={"extraction_order": "alphabetical"})
        return self.model_copy(update={"metadata": updated_meta, "entries": sorted_entries})
