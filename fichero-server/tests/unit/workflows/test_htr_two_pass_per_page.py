"""#2523 — HTR two-pass (transcribe → review) must save PER-PAGE, never the parent.

Symptom: HTR quality is great, but the corrected transcription saves to the
PDF/folder level instead of per-page. Root cause traced:

  * ``files_tool`` (sources.py) emits per-page page-children on BOTH its
    ``files`` and ``documents`` output ports. The per-page Document records
    (parent_id + sequence) live on the ``documents`` port.
  * ``transcribe_htr.json`` wired only ``files → files`` into both transcribe
    passes; the ``documents`` port was NEVER wired. ``documents`` reaches a
    downstream node ONLY via a wired edge (top-level ``state['documents']`` is
    never populated), so both passes ran with ``documents=[]``.
  * With ``documents=[]`` the per-page mapping in ``process_vision`` is empty,
    so the whole-PDF guard (#2430) cannot resolve the parent via the path map
    and the combined transcript falls through to ``save_artifact`` keyed on the
    parent PDF path → artifact + page_content land on the PARENT.

A folder of images already works because each image path is DISTINCT and
self-identifies via ``resolve_path_to_doc``; a PDF's pages all share the parent
path, so without ``documents`` they collapse onto the parent.

Two fixes, both covered here:
  1. Preset wiring — ``files-source.documents → transcribe(_review).documents``
     (guardrail tests over the shipped JSON).
  2. process_vision backstop — when the per-page document port was NOT wired,
     resolve the parent from the DB by path so the existing #2430 whole-PDF
     guard fires (split per-page / fail loud), never combined onto the parent
     (behavioural test).

Tests assert GRANULARITY (per-page child docs + per-page artifact targets), NOT
transcription content — the model call is stubbed so no LLM / API key is needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, n_pages: int, *, with_text: bool = False) -> None:
    """Write a real ``n_pages``-page PDF using fitz (PyMuPDF)."""
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


def _make_png(path: Path) -> None:
    """Write a tiny real PNG (the non-PDF vision path needs a decodable image)."""
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import db_manager

    lib = tmp_path / "HTR.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _llm_config():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider="openai", model="gpt-4o")


def _gemini_llm_config():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider="google", model="gemini-2.5-flash")


def _preset_path(name: str) -> Path:
    from fichero_server.workflows.default_workflows import _PRESETS_DIR

    return _PRESETS_DIR / name


def _load_preset(name: str) -> dict:
    return json.loads(_preset_path(name).read_text(encoding="utf-8"))


def _stub_vision():
    """Patch the per-page raster + the vision model so no GPU/API/macOS is hit."""
    return (
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value="data:image/png;base64,FAKE",
        ),
        patch(
            "fichero_server.llm.vision",
            new=AsyncMock(return_value="Transcribed page text."),
        ),
    )


def _stub_vision_with_boxes():
    """Return Gemini-style JSON boxes on each per-page vision call."""
    payload = (
        '{"text":"Transcribed page text.","boxes":['
        '{"text":"Transcribed page text.","bbox":[0.1,0.2,0.5,0.1],"level":"line"}'
        "]}"
    )
    return (
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value="data:image/png;base64,FAKE",
        ),
        patch(
            "fichero_server.llm.vision",
            new=AsyncMock(return_value=payload),
        ),
    )


# ---------------------------------------------------------------------------
# A. Preset wiring guardrails — the documents port MUST reach every per-page
#    vision pass. (RED on current JSON, GREEN once the edges are added.)
# ---------------------------------------------------------------------------

_PER_PAGE_VISION_TOOLS = {"transcribe", "transcribe_review"}


def _missing_documents_edges(preset: dict) -> list[str]:
    """Return node-ids of per-page vision nodes that receive a ``files`` edge
    from a source node but NOT a sibling ``documents`` edge from the same
    source. Those nodes will run with documents=[] → save-to-parent on a PDF.
    """
    nodes_by_id = {n["id"]: n for n in preset.get("nodes", [])}
    edges = preset.get("edges", [])
    missing: list[str] = []
    for node_id, node in nodes_by_id.items():
        if node.get("tool") not in _PER_PAGE_VISION_TOOLS:
            continue
        files_sources = {
            e["source"]
            for e in edges
            if e.get("target") == node_id and e.get("target_port") == "files"
        }
        for src in files_sources:
            has_docs = any(
                e.get("source") == src
                and e.get("target") == node_id
                and e.get("target_port") == "documents"
                for e in edges
            )
            if not has_docs:
                missing.append(node_id)
    return missing


class TestPresetWiring:

    def test_htr_preset_wires_documents_into_both_passes(self):
        preset = _load_preset("transcribe_htr.json")
        missing = _missing_documents_edges(preset)
        assert missing == [], (
            "#2523: transcribe_htr nodes receive files but not the per-page "
            f"documents port → they save to the parent PDF: {missing}"
        )

    def test_paleography_preset_wires_documents_into_both_passes(self):
        preset = _load_preset("transcribe_paleography.json")
        missing = _missing_documents_edges(preset)
        assert missing == [], (
            f"#2523 sibling: transcribe_paleography per-page nodes unwired: {missing}"
        )

    @pytest.mark.parametrize(
        "preset_name",
        ["transcribe_cloud.json", "transcribe_manuscript.json", "transcribe_typescript.json"],
    )
    def test_single_pass_transcribe_presets_wire_documents(self, preset_name):
        preset = _load_preset(preset_name)
        missing = _missing_documents_edges(preset)
        assert missing == [], (
            f"#2523 sibling: {preset_name} per-page node unwired: {missing}"
        )


# ---------------------------------------------------------------------------
# B. Behavioural — the full two-pass over a real multi-page PDF, with the
#    documents port wired (as the fixed preset does). Each page child gets BOTH
#    artifacts + page_content; the parent PDF gets NOTHING.
# ---------------------------------------------------------------------------

class TestTwoPassPerPage:

    @pytest.mark.asyncio
    async def test_seven_page_pdf_two_pass_saves_per_page_not_parent(
        self, temp_library, tmp_path
    ):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe
        from fichero_server.workflows.tools.transcribe_review import transcribe_review

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "manuscript.pdf"
        _make_pdf(pdf, 7)

        parent = Document(
            name="manuscript.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        state = {"selected_doc_ids": [parent.id], "library_path": library_path}

        # files_tool expands the PDF into 7 page children on BOTH ports — this
        # is exactly what the wired `documents` edge carries downstream.
        src = await files_tool(inputs={}, state=state, llm_config=_llm_config())
        assert src["count"] == 7
        files, documents = src["files"], src["documents"]
        assert all(d["doc_type"] == "page" for d in documents)

        page_uri, vision = _stub_vision()
        with page_uri, vision:
            # Pass 1 — draft (update_page_content disabled by the preset).
            await transcribe(
                inputs={
                    "files": files,
                    "documents": documents,
                    "vision_mode": "llm",
                    "update_page_content": False,
                    "prompt": "Draft transcription.",
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )
            # Pass 2 — review (writes the corrected text to page_content).
            await transcribe_review(
                inputs={
                    "files": files,
                    "documents": documents,
                    "vision_mode": "llm",
                    "update_page_content": True,
                    "context": "Prior draft.",
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )

        # Parent PDF carries NEITHER artifact and NO page_content.
        assert db.query(Artifact, document_id=parent.id, artifact_type="transcription") == []
        assert (
            db.query(Artifact, document_id=parent.id, artifact_type="transcription_review")
            == []
        )
        parent_live = db.get(Document, parent.id)
        assert not (parent_live.page_content or "").strip(), (
            "#2523: corrected transcript leaked onto the parent PDF page_content"
        )

        # Every one of the 7 page children carries BOTH artifacts + page_content.
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 7
        for child in children:
            draft = db.query(Artifact, document_id=child.id, artifact_type="transcription")
            review = db.query(
                Artifact, document_id=child.id, artifact_type="transcription_review"
            )
            assert len(draft) == 1, f"page {child.sequence} missing draft artifact"
            assert len(review) == 1, f"page {child.sequence} missing review artifact"
            live = db.get(Document, child.id)
            assert (live.page_content or "").strip(), (
                f"page {child.sequence} has no page_content after review"
            )

    @pytest.mark.asyncio
    async def test_gemini_return_boxes_persist_on_each_page_child(
        self, temp_library, tmp_path
    ):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "manuscript.pdf"
        _make_pdf(pdf, 3)

        parent = Document(
            name="manuscript.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        src = await files_tool(
            inputs={},
            state={"selected_doc_ids": [parent.id], "library_path": library_path},
            llm_config=_gemini_llm_config(),
        )

        page_uri, vision = _stub_vision_with_boxes()
        with page_uri, vision:
            await transcribe(
                inputs={
                    "files": src["files"],
                    "documents": src["documents"],
                    "vision_mode": "llm",
                    "return_boxes": True,
                    "update_page_content": True,
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_gemini_llm_config(),
            )

        assert db.query(Artifact, document_id=parent.id, artifact_type="transcription") == []
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 3
        for child in children:
            arts = db.query(Artifact, document_id=child.id, artifact_type="transcription")
            assert len(arts) == 1, f"page {child.sequence} missing transcription artifact"
            geometry = arts[0].ocr_geometry
            assert geometry is not None, f"page {child.sequence} missing typed OCR geometry"
            assert geometry.text == "Transcribed page text."
            assert len(geometry.boxes) == 1
            assert geometry.boxes[0].page_index == child.sequence - 1


# ---------------------------------------------------------------------------
# C. Backstop — even when the documents port is NOT wired (editor-built chain
#    or an un-swept preset), a multi-page PDF must NEVER save combined to the
#    parent. The #2430 whole-PDF guard fires off the DB-resolved parent.
# ---------------------------------------------------------------------------

class TestUnwiredBackstop:

    @pytest.mark.asyncio
    async def test_documents_unwired_pdf_review_never_saves_to_parent(
        self, temp_library, tmp_path
    ):
        """Review pass with documents=[] (the #2523 repro) on a split PDF must
        route per-page to the page children, never the parent."""
        from fichero_server.importers.ingest import _create_pdf_page_children
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.transcribe_review import transcribe_review

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "manuscript.pdf"
        _make_pdf(pdf, 5)

        parent = Document(
            name="manuscript.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)
        pages = _create_pdf_page_children(parent, pdf, db)
        assert len(pages) == 5

        page_uri, vision = _stub_vision()
        with page_uri, vision:
            await transcribe_review(
                inputs={
                    # NB: documents intentionally OMITTED — the unwired graph.
                    "files": [str(pdf)],
                    "vision_mode": "llm",
                    "update_page_content": True,
                    "context": "Prior draft.",
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )

        # The parent PDF must carry NO review artifact and NO page_content.
        assert (
            db.query(Artifact, document_id=parent.id, artifact_type="transcription_review")
            == []
        ), "#2523: unwired review leaked a combined transcript onto the parent PDF"
        parent_live = db.get(Document, parent.id)
        assert not (parent_live.page_content or "").strip()

        # The page children received the per-page review artifacts instead.
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        review_arts = sum(
            len(db.query(Artifact, document_id=c.id, artifact_type="transcription_review"))
            for c in children
        )
        assert review_arts == 5, (
            f"backstop must propagate review per-page; got {review_arts} artifacts"
        )


# ---------------------------------------------------------------------------
# D. Parity — a folder of 3 images transcribes per-image (the path that already
#    worked, kept as a regression lock).
# ---------------------------------------------------------------------------

class TestFolderOfImagesParity:

    @pytest.mark.asyncio
    async def test_folder_of_images_saves_per_image(self, temp_library, tmp_path):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)

        folder = Document(name="scans", doc_type=DocType.folder)
        db.save(folder)
        images = []
        for i in range(3):
            png = tmp_path / f"scan_{i}.png"
            _make_png(png)
            img = Document(
                name=png.name,
                doc_type=DocType.file,
                file_type=FileType.image,
                path=str(png),
                parent_id=folder.id,
            )
            db.save(img)
            images.append(img)

        src = await files_tool(
            inputs={},
            state={"selected_doc_ids": [folder.id], "library_path": library_path},
            llm_config=_llm_config(),
        )
        assert src["count"] == 3

        page_uri, vision = _stub_vision()
        with page_uri, vision:
            await transcribe(
                inputs={
                    "files": src["files"],
                    "documents": src["documents"],
                    "vision_mode": "llm",
                    "update_page_content": True,
                    "prompt": "Transcribe.",
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )

        # The folder carries no artifact; each image carries exactly one.
        assert db.query(Artifact, document_id=folder.id, artifact_type="transcription") == []
        for img in images:
            arts = db.query(Artifact, document_id=img.id, artifact_type="transcription")
            assert len(arts) == 1, f"image {img.name} must have its own artifact"


# ---------------------------------------------------------------------------
# E. The Reference Corpus Search node returns documents downstream and writes
#    NOTHING onto any document (no parent artifact, no page_content mutation).
# ---------------------------------------------------------------------------

class TestSearchNoParentWrite:

    @pytest.mark.asyncio
    async def test_search_tool_creates_no_artifact(self, temp_library, tmp_path):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import search_tool

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "corpus.pdf"
        _make_pdf(pdf, 2, with_text=True)
        doc = Document(
            name="corpus.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
            page_content="reference body",
        )
        db.save(doc)

        result = await search_tool(
            inputs={"query": "reference", "limit": 5},
            state={"library_path": library_path},
            llm_config=_llm_config(),
        )

        # Whatever it returns, search is read-only: no artifact on any document.
        assert "documents" in result
        all_arts = db.all(Artifact)
        assert list(all_arts) == [], (
            f"#2523: search tool must not write artifacts, found {list(all_arts)}"
        )
