"""segment.kraken.segments-a-pdf-page (#4892): Kraken segments a PDF page by
rendering it through the SAME shared page-render seam Apple Vision / the LLM
branch already use for a PDF page, instead of refusing every `.pdf` path.

Reproduces the maintainer's exact shape: a PDF PAGE CHILD document (which
resolves to its PARENT PDF's file path, per `files_tool`/
`_resolve_selection_pairs`) run through the real `detect_regions` tool with
`provider="kraken"`. Only `kraken_runtime.segment_to_geometry` is stubbed —
the lowest seam, matching `test_kraken_segmenter_node.py`'s own convention —
so the real PDF render (`_render_pdf_page_to_temp_png` -> the shared Quartz
batch render) and the real `process_vision`/`complete_run_documents` paths
all run for real, on a real small PDF built with `fitz` (the same PDF-writing
library `test_transcribe_pdf_text_layer.py::_make_pdf_with_text` already
uses; note this is unrelated to the pypdfium2 RENDER-path migration — tests
still WRITE test PDFs with fitz/PyMuPDF).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# process_vision renders PDF pages via Quartz (macOS-only); on non-macOS CI
# the render fails before the stubbed segmenter is ever reached. Same guard
# test_transcribe_pdf_text_layer.py uses.
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Kraken's PDF-page render goes through Quartz (macOS-only)",
)


def _make_pdf_with_text(path: Path, pages: list[str]) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    doc.save(str(path))
    doc.close()


def _kraken_geometry():
    from fichero_server.media.ocr_geometry import (
        OCRGeometryBox,
        OCRGeometryLevel,
        OCRGeometryResult,
    )

    return OCRGeometryResult(
        text="",
        provider="kraken",
        model="blla",
        source="kraken-blla",
        boxes=[
            OCRGeometryBox(
                text="",
                bbox=[0.1, 0.1, 0.8, 0.05],
                level=OCRGeometryLevel.LINE,
                provider="kraken",
                model="blla",
                source="kraken-blla",
                metadata={"baseline_px": [[100.0, 300.0], [900.0, 300.0]]},
            )
        ],
    )


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import db_manager

    lib = tmp_path / "KrakenPDF.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_kraken_segments_a_pdf_page_child_in_the_right_frame(
    temp_library, tmp_path, monkeypatch
):
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Artifact, Document, DocType, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.detect_regions import detect_regions

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)

    pdf_path = tmp_path / "deed.pdf"
    _make_pdf_with_text(pdf_path, ["Antonio Asprilla signed the deed."])

    parent = Document(
        name="deed.pdf", doc_type=DocType.file, file_type=FileType.pdf,
        path=str(pdf_path),
    )
    db.save(parent)
    page = Document(
        name="deed.pdf p.1", doc_type=DocType.page, parent_id=parent.id,
        sequence=1,  # 1-indexed -> requested_page_index == 0
    )
    db.save(page)

    src = await files_tool(
        inputs={},
        state={"selected_doc_ids": [page.id], "library_path": library_path},
        llm_config=LLMConfig(provider="", model=""),
    )
    # The maintainer's exact shape: the page child resolves to the PARENT
    # PDF's own file path (existing, working plumbing -- not what was broken).
    assert src["files"] == [str(pdf_path)]

    import fichero_server.llm.kraken_runtime as kraken_runtime

    seen_paths: list[str] = []

    def _fake_segment(image_path, rendition_id=None, home=None):
        seen_paths.append(image_path)
        return _kraken_geometry()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(kraken_runtime, "segment_to_geometry", _fake_segment)
        result = await detect_regions(
            inputs={
                "files": src["files"],
                "documents": src["documents"],
                "provider": "kraken",
            },
            state={"library_path": library_path, "task_id": None},
            llm_config=LLMConfig(provider="", model=""),
        )

    assert not result.get("error"), result.get("error")
    assert len(seen_paths) == 1, "kraken segmenter was not called exactly once"
    # #4892: no manual split step -- the PDF path itself was never handed to
    # Kraken. It was rendered through the shared seam to a real image file.
    assert seen_paths[0] != str(pdf_path)
    assert seen_paths[0].lower().endswith(".png")
    assert Path(seen_paths[0]).exists() is False, (
        "the rendered temp file must be cleaned up after segmentation"
    )

    # The regions artifact lands on the PAGE, not the parent PDF.
    page_arts = db.query(Artifact, document_id=page.id, artifact_type="regions")
    assert len(page_arts) == 1, "no regions artifact was saved for the page"
    parent_arts = db.query(Artifact, document_id=parent.id, artifact_type="regions")
    assert len(parent_arts) == 0, "the artifact must not land on the parent PDF"

    geometry = page_arts[0].ocr_geometry
    assert geometry is not None
    assert geometry.provider == "kraken"
    box = geometry.boxes[0]
    # The RIGHT frame: normalized [0,1], top-left origin -- the same shared
    # OCRGeometryBox.bbox contract Apple's PDF-page path already writes into,
    # unaffected by the render's own pixel dimensions or DPI (#4892).
    assert box.bbox == [0.1, 0.1, 0.8, 0.05]
    assert all(0.0 <= v <= 1.0 for v in box.bbox)
    assert box.coordinate_space == "normalized"
    # Provenance: the render's page index and resolution are named, not
    # silently assumed (#4892's "provenance records the render").
    assert box.page_index == 0
    assert geometry.metadata["pdf_page_render"] == {"page_index": 0, "dpi": 300}


@pytest.mark.asyncio
async def test_kraken_pdf_page_emits_artifact_updated_naming_it(
    temp_library, tmp_path, monkeypatch
):
    """segment.overlay.refreshes-when-segmentation-finishes (#4890) must
    cover this path too: the real runner boundary still learns of the
    artifact this Kraken PDF-page run created."""
    from fichero_server.api import change_stream
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Artifact, Document, DocType, FileType
    from fichero_server.workflows.completion import (
        collect_created_artifact_ids,
        complete_run_documents,
    )
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.detect_regions import detect_regions

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)

    pdf_path = tmp_path / "deed2.pdf"
    _make_pdf_with_text(pdf_path, ["Marta Escobar sold the mine."])
    parent = Document(
        name="deed2.pdf", doc_type=DocType.file, file_type=FileType.pdf,
        path=str(pdf_path),
    )
    db.save(parent)
    page = Document(name="deed2.pdf p.1", doc_type=DocType.page, parent_id=parent.id, sequence=1)
    db.save(page)

    src = await files_tool(
        inputs={},
        state={"selected_doc_ids": [page.id], "library_path": library_path},
        llm_config=LLMConfig(provider="", model=""),
    )

    import fichero_server.llm.kraken_runtime as kraken_runtime

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(kraken_runtime, "segment_to_geometry", lambda *a, **k: _kraken_geometry())
        result = await detect_regions(
            inputs={"files": src["files"], "documents": src["documents"], "provider": "kraken"},
            state={"library_path": library_path, "task_id": None},
            llm_config=LLMConfig(provider="", model=""),
        )
    assert not result.get("error"), result.get("error")

    art = db.query(Artifact, document_id=page.id, artifact_type="regions")[0]

    captured = []
    monkeypatch.setattr(
        change_stream._change_hub, "emit", lambda library_path, event: captured.append(event)
    )
    run_artifact_ids = collect_created_artifact_ids(result)
    assert art.id in run_artifact_ids
    complete_run_documents(db, {page.id}, artifact_ids=run_artifact_ids)

    artifact_events = [e for e in captured if e.type == "artifact.updated"]
    assert len(artifact_events) == 1
    assert art.id in artifact_events[0].artifact_ids
    assert page.id in artifact_events[0].document_ids
