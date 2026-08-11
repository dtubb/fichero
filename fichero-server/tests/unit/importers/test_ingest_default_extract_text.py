"""Regression test for #881 — text-bearing files (.md, .txt, .docx)
must have their text extracted to Document.page_content at ingest
time so they're immediately searchable.

Pre-fix, ingest_file's \\\`extract_text\\\` defaulted to False, so .md
files in a fresh library had no page_content and didn't appear in
full-text or semantic search results. Post-fix, the default flipped
to True. Image-only files still correctly skip the extractor because
_TEXT_EXTRACTABLE gates the call.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.importers.ingest import ingest_file, ingest_folder, IngestMode
from fichero_server.models import FileType


@pytest.fixture
def markdown_file(tmp_path: Path) -> Path:
    path = tmp_path / "notes.md"
    path.write_text(
        "# Field notes — 2026-05\n\n"
        "Davidson signed the deed on the third of March nineteen thirty one.\n"
        "Antonio Asprilla filed the complaint with the alcalde mayor.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def text_file(tmp_path: Path) -> Path:
    path = tmp_path / "raw_transcript.txt"
    path.write_text(
        "Plain text content suitable for full-text search. " * 5,
        encoding="utf-8",
    )
    return path


class TestIngestDefaultExtractText:
    def test_markdown_gets_page_content_by_default(self, markdown_file):
        # save=False keeps the test off-DB so we don't need a fixture DB
        doc = ingest_file(
            markdown_file, mode=IngestMode.LINK, save=False,
        )
        assert doc.file_type == FileType.text
        assert doc.page_content is not None
        assert "Davidson" in doc.page_content
        assert "Asprilla" in doc.page_content

    def test_txt_gets_page_content_by_default(self, text_file):
        doc = ingest_file(text_file, mode=IngestMode.LINK, save=False)
        assert doc.file_type == FileType.text
        assert doc.page_content
        assert "search" in doc.page_content

    def test_extract_text_false_still_supported(self, markdown_file):
        """Callers that explicitly defer extraction (batch import, where
        a workflow handles text later) can still pass extract_text=False.
        """
        doc = ingest_file(
            markdown_file, mode=IngestMode.LINK,
            extract_text=False, save=False,
        )
        # No content extracted — exactly what the caller asked for
        assert not doc.page_content

    def test_image_file_skips_text_extraction(self, tmp_path):
        """Image files aren't in _TEXT_EXTRACTABLE, so even with the
        new default of extract_text=True, the loader isn't invoked
        (no .jpg → .txt fallback). Transcribe / OCR workflow handles
        these explicitly. Sanity-check: doc still ingests OK, just
        without page_content.
        """
        img = tmp_path / "scan.jpg"
        # Minimal valid JPEG header so detect_file_type picks .jpg
        img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        doc = ingest_file(img, mode=IngestMode.LINK, save=False)
        assert doc.file_type == FileType.image
        assert not doc.page_content

    @patch("fichero_server.bookmarks.create_bookmark", return_value=None)
    def test_folder_ingest_extracts_text_by_default(self, _mock_bookmark, tmp_path):
        md = tmp_path / "notes.md"
        md.write_text("Folder import should extract this sentence.", encoding="utf-8")
        fake_db = MagicMock()
        saved_docs = []

        def _save(doc, auto_embed=False):
            if not getattr(doc, "id", None):
                doc.id = f"doc-{len(saved_docs)+1}"
            saved_docs.append(doc)

        fake_db.save.side_effect = _save
        docs = ingest_folder(tmp_path, db=fake_db, create_collection=False)
        assert len(docs) == 1
        assert docs[0].page_content is not None
        assert "extract this sentence" in docs[0].page_content

    @patch("fichero_server.bookmarks.create_bookmark", return_value=None)
    def test_folder_ingest_skips_unchanged_files_by_hash(self, _mock_bookmark, tmp_path):
        md = tmp_path / "stable.md"
        md.write_text("Stable payload for resumable ingest.", encoding="utf-8")
        fake_db = MagicMock()
        saved_docs = {}

        def _save(doc, auto_embed=False):
            if not getattr(doc, "id", None):
                doc.id = f"doc-{len(saved_docs)+1}"
            saved_docs[doc.id] = doc

        fake_db.save.side_effect = _save
        fake_db.all.side_effect = lambda model: list(saved_docs.values())
        # Prescan seam (2026-08-09): the skip-set now comes from one targeted
        # SELECT, Database.ingest_dedup_keys(); mirror its contract here.
        fake_db.ingest_dedup_keys.side_effect = lambda: {
            (
                (doc.metadata or {}).get("source_path") or doc.path,
                (doc.metadata or {}).get("checksum"),
            )
            for doc in saved_docs.values()
            if (doc.metadata or {}).get("checksum")
        }

        first = ingest_folder(tmp_path, db=fake_db, create_collection=False)
        second = ingest_folder(tmp_path, db=fake_db, create_collection=False)

        assert len(first) == 1
        assert len(second) == 0
