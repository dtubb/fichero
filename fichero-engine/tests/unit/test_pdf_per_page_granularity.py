"""#2430 — PDF per-page PROCESSING GRANULARITY (split-on-import + guards).

The DB-race half of #2430 (artifacts mis-routed to the parent under concurrency)
is covered by test_per_page_artifact_placement / test_per_page_fanout_concurrency.
This file covers the *other* root cause: a multi-page PDF that reaches a per-page
tool with NO page children gets transcribed whole-doc and the combined
``--- Page N ---`` blob lands on the PARENT.

Daniel's rule: ONE page at a time, page-level FIRST, never whole-doc onto the
parent (docs up to 500 pages). These tests use REAL multi-page PDFs (built with
fitz) and a REAL temp DuckDB library, and assert GRANULARITY (per-page child
docs + per-page artifact targets), NOT transcription content — the model call is
stubbed so no LLM / API key is needed.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, n_pages: int, *, with_text: bool = True) -> None:
    """Write a real ``n_pages``-page PDF to ``path`` using fitz (PyMuPDF)."""
    import fitz

    doc = fitz.open()
    try:
        for i in range(n_pages):
            page = doc.new_page()
            if with_text:
                page.insert_text((72, 72), f"Page {i + 1} body text.")
        doc.save(str(path))
    finally:
        doc.close()


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    """A real .fichero package backed by a real DuckDB file."""
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero.db.manager import db_manager

    lib = tmp_path / "Granularity.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _make_tool_config():
    from fichero.workflows.tools.vision_base import VisionToolConfig

    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=False,
        skip_if_artifact_exists=False,
    )


def _llm_config():
    from fichero.llm import LLMConfig

    return LLMConfig(provider="openai", model="gpt-4o")


# ---------------------------------------------------------------------------
# A. Split on import — a multi-page PDF becomes one page-child per page.
# ---------------------------------------------------------------------------

class TestSplitOnImport:

    def test_multipage_pdf_creates_one_child_per_page(self, temp_library, tmp_path):
        from fichero.ingest import _create_pdf_page_children
        from fichero.models import Document, DocType

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 5)

        parent = Document(name="scan.pdf", doc_type=DocType.file, path=str(pdf))
        db.save(parent)

        pages = _create_pdf_page_children(parent, pdf, db)

        assert len(pages) == 5, "split must produce one page child per page"
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 5
        assert sorted(p.sequence for p in children) == [1, 2, 3, 4, 5]

    def test_kreuzberg_failure_falls_back_to_fitz_no_silent_unsplit(
        self, temp_library, tmp_path, monkeypatch
    ):
        """If Kreuzberg silently yields nothing, fitz must still split the PDF —
        a multi-page PDF is never left unsplit (#2430, no-silent-fallback)."""
        import fichero.ingest as ingest
        from fichero.models import Document, DocType

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 4)

        # Simulate Kreuzberg returning no pages (the silent-failure case).
        monkeypatch.setattr(ingest, "_kreuzberg_pdf_pages", lambda _p: [])

        parent = Document(name="scan.pdf", doc_type=DocType.file, path=str(pdf))
        db.save(parent)

        pages = ingest._create_pdf_page_children(parent, pdf, db)

        assert len(pages) == 4, "fitz fallback must split when Kreuzberg fails"
        assert "pdf_page_split_failed" not in (parent.metadata or {})

    def test_kreuzberg_missing_dependency_logs_real_fallback_reason(
        self, temp_library, tmp_path, monkeypatch, caplog
    ):
        import fichero.ingest as ingest
        from fichero.models import Document, DocType

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 2)

        def _missing(_path):
            raise ingest._KreuzbergUnavailableError("No module named 'kreuzberg'")

        monkeypatch.setattr(ingest, "_kreuzberg_pdf_pages", _missing)

        parent = Document(name="scan.pdf", doc_type=DocType.file, path=str(pdf))
        db.save(parent)

        with caplog.at_level("WARNING"):
            pages = ingest._create_pdf_page_children(parent, pdf, db)

        assert len(pages) == 2
        assert "dependency missing" in caplog.text
        assert "No module named 'kreuzberg'" in caplog.text

    def test_kreuzberg_extraction_failure_logs_real_fallback_reason(
        self, temp_library, tmp_path, monkeypatch, caplog
    ):
        import fichero.ingest as ingest
        from fichero.models import Document, DocType

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 2)

        def _failed(_path):
            raise ingest._KreuzbergExtractionError("pdfium blew up")

        monkeypatch.setattr(ingest, "_kreuzberg_pdf_pages", _failed)

        parent = Document(name="scan.pdf", doc_type=DocType.file, path=str(pdf))
        db.save(parent)

        with caplog.at_level("WARNING"):
            pages = ingest._create_pdf_page_children(parent, pdf, db)

        assert len(pages) == 2
        assert "extraction failed" in caplog.text
        assert "pdfium blew up" in caplog.text

    def test_both_splitters_fail_stamps_parent_and_logs_loud(
        self, temp_library, tmp_path, monkeypatch, caplog
    ):
        """When BOTH splitters fail on a PDF, fail LOUD + stamp the parent —
        never silently return as if the PDF had no pages (#2430)."""
        import fitz

        import fichero.ingest as ingest
        from fichero.models import Document, DocType

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 3)

        monkeypatch.setattr(ingest, "_kreuzberg_pdf_pages", lambda _p: [])

        def _boom(*_a, **_k):
            raise RuntimeError("fitz cannot open")

        monkeypatch.setattr(fitz, "open", _boom)

        parent = Document(name="scan.pdf", doc_type=DocType.file, path=str(pdf))
        db.save(parent)

        with caplog.at_level("ERROR"):
            pages = ingest._create_pdf_page_children(parent, pdf, db)

        assert pages == []
        assert parent.metadata.get("pdf_page_split_failed") is True
        assert any(
            "page-splitting FAILED" in r.message for r in caplog.records
        ), "a total split failure must be surfaced loudly"


# ---------------------------------------------------------------------------
# B. files_tool — an unsplit PDF is split on the spot so the workflow fans
#    out per-page (auto-backfill of PDFs imported before splitting).
# ---------------------------------------------------------------------------

class TestFilesToolOnTheSpotSplit:

    @pytest.mark.asyncio
    async def test_unsplit_pdf_expands_to_one_entry_per_page(
        self, temp_library, tmp_path
    ):
        from fichero.models import Document, DocType, FileType
        from fichero.workflows.tools.sources import files_tool

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 3)

        parent = Document(
            name="scan.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        # Precondition: no page children yet (the unsplit state).
        assert (
            db.query(Document, parent_id=parent.id, doc_type=DocType.page) == []
        )

        result = await files_tool(
            inputs={},
            state={"selected_doc_ids": [parent.id], "library_path": library_path},
            llm_config=_llm_config(),
        )

        # One entry per page, each pointing at a page-child document.
        assert result["count"] == 3
        assert all(d["doc_type"] == "page" for d in result["documents"])
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 3, "files_tool must split the PDF on the spot"


# ---------------------------------------------------------------------------
# C. The guard — a whole multi-page PDF (no children) reaching process_vision
#    must NEVER write a combined transcript onto the parent.
# ---------------------------------------------------------------------------

class TestWholePdfGuard:

    @pytest.mark.asyncio
    async def test_no_children_routes_per_page_never_combined_to_parent(
        self, temp_library, tmp_path
    ):
        """A multi-page PDF with NO page children, processed whole by
        process_vision, must be split on the spot and yield per-page artifacts —
        the parent PDF gets NO transcription artifact (no ``--- Page N ---``
        blob). This is Daniel's exact symptom (#2430)."""
        from fichero.models import Artifact, Document, DocType, FileType
        from fichero.workflows.tools.vision_base import process_vision

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 3, with_text=False)  # blank pages → forces vision path

        parent = Document(
            name="scan.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        with (
            patch(
                "fichero.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero.llm.vision",
                new=AsyncMock(return_value="Transcribed page text."),
            ),
        ):
            await process_vision(
                files=[str(pdf)],
                documents=[parent.model_dump()],
                prompt="Transcribe.",
                llm_config=_llm_config(),
                library_path=library_path,
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        # The parent PDF must NOT carry a combined transcript artifact.
        parent_arts = db.query(
            Artifact, document_id=parent.id, artifact_type="transcription"
        )
        assert parent_arts == [], (
            f"#2430: combined transcript routed to parent PDF: {parent_arts}"
        )

        # Page children were created on the spot, each with its OWN artifact.
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 3, "guard must split the PDF into page children"
        for child in children:
            arts = db.query(
                Artifact, document_id=child.id, artifact_type="transcription"
            )
            assert len(arts) == 1, (
                f"page {child.sequence} must have exactly one per-page artifact, "
                f"got {len(arts)}"
            )

    @pytest.mark.asyncio
    async def test_unsplittable_multipage_fails_loud_not_combined_to_parent(
        self, temp_library, tmp_path, monkeypatch
    ):
        """If a multi-page PDF cannot be split even on the spot, the per-page
        guard must FAIL LOUD (the file errors) rather than write a combined blob
        onto the parent (#2430, no-silent-fallback)."""
        import fichero.ingest as ingest
        from fichero.models import Artifact, Document, DocType, FileType
        from fichero.workflows.tools.vision_base import process_vision

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 3, with_text=False)

        parent = Document(
            name="scan.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        # Make the on-the-spot split impossible so the guard must fail loud.
        monkeypatch.setattr(
            ingest, "_create_pdf_page_children", lambda *_a, **_k: []
        )

        with (
            patch(
                "fichero.workflows.tools.vision_base._pdf_page_to_data_uri",
                return_value="data:image/png;base64,FAKE",
            ),
            patch(
                "fichero.llm.vision",
                new=AsyncMock(return_value="Transcribed page text."),
            ),
        ):
            result = await process_vision(
                files=[str(pdf)],
                documents=[parent.model_dump()],
                prompt="Transcribe.",
                llm_config=_llm_config(),
                library_path=library_path,
                task_id=None,
                tool_config=_make_tool_config(),
                vision_mode="llm",
                save_to_db=True,
            )

        # The file must be reported as an error (loud failure), and NOTHING may
        # be written onto the parent PDF.
        file_results = result.get("results", []) if isinstance(result, dict) else []
        assert any(
            r.get("error") for r in file_results
        ), f"unsplittable multi-page PDF must surface an error: {file_results}"
        assert (
            db.query(Artifact, document_id=parent.id, artifact_type="transcription")
            == []
        ), "#2430: no combined transcript may land on the parent on failure"
