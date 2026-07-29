"""
Tests for Kreuzberg extractor → Artifact preservation (issue #885).

Verifies that structured outputs from the Kreuzberg-based loaders (tables,
slide text, image descriptions, audio/video transcripts) are persisted as
``Artifact`` rows attached to the ingested document, instead of being
silently discarded after the primary text is saved.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fichero_server.importers.ingest import IngestMode, ingest_file
from fichero_server.loaders.base import MediaContent
from fichero_server.loaders.kreuzberg_artifacts import (
    KREUZBERG_IMAGE_DESCRIPTION,
    KREUZBERG_KEYWORDS,
    KREUZBERG_SLIDE_TEXT,
    KREUZBERG_TABLE,
    KREUZBERG_TRANSCRIPT,
    extract_artifact_payloads,
)
from fichero_server.models import Artifact


# ---------------------------------------------------------------------------
# extract_artifact_payloads — pure unit tests (no DB, no loader)
# ---------------------------------------------------------------------------


class _FakeTable:
    def __init__(self, markdown="| a | b |\n|---|---|\n| 1 | 2 |", page_number=1):
        self.cells = [["a", "b"], ["1", "2"]]
        self.markdown = markdown
        self.page_number = page_number


class _FakeKeyword:
    def __init__(self, text, score=0.5):
        self.text = text
        self.score = score


class _FakeAnnotation:
    def __init__(self, annotation_type="highlight", content="note", page_number=2):
        self.annotation_type = annotation_type
        self.content = content
        self.page_number = page_number


def _make_result(**overrides):
    """Build a fake ExtractionResult-shaped object."""
    base = dict(
        content="primary text",
        mime_type="text/plain",
        metadata={"format_type": "text"},
        tables=[],
        images=None,
        pages=None,
        extracted_keywords=None,
        annotations=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_extracts_table_artifacts():
    result = _make_result(tables=[_FakeTable(), _FakeTable(page_number=3)])
    payloads = extract_artifact_payloads(result)
    types = [p["artifact_type"] for p in payloads]
    assert types.count(KREUZBERG_TABLE) == 2
    first = next(p for p in payloads if p["artifact_type"] == KREUZBERG_TABLE)
    assert first["data"]["cells"] == [["a", "b"], ["1", "2"]]
    assert first["content"].startswith("| a | b |")


def test_extracts_slide_text_for_pptx():
    pages = [
        {"page_number": 1, "content": "Slide 1 body"},
        {"page_number": 2, "content": "Slide 2 body"},
        {"page_number": 3, "content": "   "},  # blank → skipped
    ]
    result = _make_result(pages=pages, metadata={"format_type": "pptx"})
    payloads = extract_artifact_payloads(result)
    slides = [p for p in payloads if p["artifact_type"] == KREUZBERG_SLIDE_TEXT]
    assert len(slides) == 2
    assert slides[0]["content"] == "Slide 1 body"
    assert slides[0]["data"]["slide_number"] == 1


def test_pages_without_pptx_format_do_not_produce_slide_text():
    # Pages on a PDF result must NOT be turned into slide_text artifacts —
    # they already become page Documents via _create_pdf_page_children.
    pages = [{"page_number": 1, "content": "page 1"}]
    result = _make_result(pages=pages, metadata={"format_type": "pdf"})
    payloads = extract_artifact_payloads(result)
    assert not any(p["artifact_type"] == KREUZBERG_SLIDE_TEXT for p in payloads)


def test_extracts_transcript_for_audio_format():
    result = _make_result(
        content="Hello world. This is a transcript.",
        metadata={"format_type": "audio"},
    )
    payloads = extract_artifact_payloads(result)
    transcripts = [p for p in payloads if p["artifact_type"] == KREUZBERG_TRANSCRIPT]
    assert len(transcripts) == 1
    assert "transcript" in transcripts[0]["content"]


def test_extracts_image_description_and_ocr():
    ocr_result = SimpleNamespace(content="OCR'd text from image")
    images = [
        {
            "description": "A black cat on a chair",
            "ocr_result": ocr_result,
            "page_number": 4,
        },
        {"description": None, "ocr_result": None},  # skipped
    ]
    result = _make_result(images=images)
    payloads = extract_artifact_payloads(result)
    descs = [
        p for p in payloads if p["artifact_type"] == KREUZBERG_IMAGE_DESCRIPTION
    ]
    assert len(descs) == 1
    assert "black cat" in descs[0]["content"]
    assert "OCR'd text" in descs[0]["content"]
    assert descs[0]["data"]["page_number"] == 4


def test_extracts_keywords_as_single_artifact():
    result = _make_result(
        extracted_keywords=[_FakeKeyword("fichero", 0.9), _FakeKeyword("docs", 0.7)]
    )
    payloads = extract_artifact_payloads(result)
    kw = [p for p in payloads if p["artifact_type"] == KREUZBERG_KEYWORDS]
    assert len(kw) == 1
    assert "fichero" in kw[0]["content"]
    assert len(kw[0]["data"]["keywords"]) == 2


def test_returns_empty_for_none_result():
    assert extract_artifact_payloads(None) == []


def test_returns_empty_when_no_structured_outputs():
    result = _make_result()  # only primary text, no tables/images/etc.
    assert extract_artifact_payloads(result) == []


# ---------------------------------------------------------------------------
# Integration: ingest_file persists artifacts after loader returns them
# ---------------------------------------------------------------------------


@pytest.fixture
def text_file(tmp_path):
    path = tmp_path / "report.docx"
    path.write_text("placeholder bytes — the loader is mocked")
    return path


def test_ingest_persists_kreuzberg_artifacts_on_document(db, text_file):
    """End-to-end: a loader returning structured outputs results in
    Artifact rows on the saved document."""

    payloads = [
        {
            "artifact_type": KREUZBERG_TABLE,
            "content": "| a | b |",
            "data": {"cells": [["a", "b"]], "page_number": 1},
        },
        {
            "artifact_type": KREUZBERG_TRANSCRIPT,
            "content": "spoken words",
            "data": {"format_type": "audio"},
        },
        {
            "artifact_type": KREUZBERG_IMAGE_DESCRIPTION,
            "content": "A diagram showing the architecture",
            "data": {"image_index": 0},
        },
    ]

    async def fake_load_media(path):
        return MediaContent(
            source=str(path),
            text="primary text body",
            metadata={"_kreuzberg_artifacts": payloads},
            mime_type="text/plain",
            needs_vlm=False,
        )

    with patch("fichero_server.loaders.load_media", side_effect=fake_load_media):
        doc = ingest_file(
            text_file,
            mode=IngestMode.LINK,
            extract_text=True,
            save=True,
            db=db,
        )

    # Primary text is still saved (additive contract).
    assert doc.page_content == "primary text body"

    # The artifacts are persisted and attached to this document.
    artifacts = db.query(Artifact, document_id=doc.id)
    types = sorted(a.artifact_type for a in artifacts)
    assert types == sorted(
        [KREUZBERG_TABLE, KREUZBERG_TRANSCRIPT, KREUZBERG_IMAGE_DESCRIPTION]
    )

    by_type = {a.artifact_type: a for a in artifacts}
    assert by_type[KREUZBERG_TABLE].content == "| a | b |"
    assert by_type[KREUZBERG_TABLE].data["cells"] == [["a", "b"]]
    assert by_type[KREUZBERG_TRANSCRIPT].content == "spoken words"
    assert all(a.provider == "kreuzberg" for a in artifacts)

    # The transient payload list MUST be cleared off the document metadata
    # so it doesn't leak into the persisted Document row.
    assert "_pending_artifacts" not in doc.metadata


def test_ingest_with_no_structured_outputs_creates_no_artifacts(db, text_file):
    """If the loader returns nothing structured, no artifact rows appear."""

    async def fake_load_media(path):
        return MediaContent(
            source=str(path),
            text="just primary text",
            metadata={},
            mime_type="text/plain",
            needs_vlm=False,
        )

    with patch("fichero_server.loaders.load_media", side_effect=fake_load_media):
        doc = ingest_file(
            text_file,
            mode=IngestMode.LINK,
            extract_text=True,
            save=True,
            db=db,
        )

    artifacts = db.query(Artifact, document_id=doc.id)
    assert artifacts == []
    assert doc.page_content == "just primary text"
