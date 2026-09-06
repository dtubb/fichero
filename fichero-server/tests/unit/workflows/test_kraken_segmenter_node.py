"""Detect Regions can run Kraken's segmenter (#4671 — "kraken for baselines").

detect_regions gained a `kraken` provider → process_vision vision_mode="kraken",
which swaps kraken's segment_to_geometry in at the apple-geometry seam and
reuses ALL the existing per-page persistence (Option A, no duplication). This
pins that a kraken run persists the bbox/baseline geometry onto the page's
`regions` artifact — the segmenter is mocked (no ~1 GB runtime), the artifact is
read back through the typed DB layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import db_manager

    lib = tmp_path / "Kraken.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _kraken_geometry():
    from fichero_server.media.ocr_geometry import (
        OCRGeometryBox,
        OCRGeometryLevel,
        OCRGeometryResult,
    )

    return OCRGeometryResult(
        text="",  # kraken reads nothing
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


@pytest.mark.asyncio
async def test_detect_regions_kraken_persists_baseline_geometry(temp_library, tmp_path):
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Artifact, Document, DocType, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.detect_regions import detect_regions

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)
    png = tmp_path / "hand.png"
    _make_png(png)

    doc = Document(
        name="hand.png",
        doc_type=DocType.file,
        file_type=FileType.image,
        path=str(png),
    )
    db.save(doc)

    src = await files_tool(
        inputs={},
        state={"selected_doc_ids": [doc.id], "library_path": library_path},
        llm_config=LLMConfig(provider="", model=""),
    )

    import fichero_server.llm.kraken_runtime as kraken_runtime

    seen = {}

    def _fake_segment(image_path, rendition_id=None, home=None):
        seen["path"] = image_path
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
    assert seen.get("path"), "kraken segmenter was not called"

    arts = db.query(Artifact, document_id=doc.id, artifact_type="regions")
    assert len(arts) == 1, "kraken run did not persist a regions artifact"
    geometry = arts[0].ocr_geometry
    assert geometry is not None, "kraken geometry was dropped"
    assert geometry.provider == "kraken"
    assert arts[0].provider == "kraken"
    line = geometry.boxes[0]
    assert line.level.value == "line"
    # The baseline is Kraken's alone — it must survive onto the record.
    assert line.metadata["baseline_px"] == [[100.0, 300.0], [900.0, 300.0]]


@pytest.mark.asyncio
async def test_detect_regions_kraken_rejects_a_pdf(temp_library, tmp_path):
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Document, DocType, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.detect_regions import detect_regions

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    doc = Document(name="scan.pdf", doc_type=DocType.file, file_type=FileType.pdf, path=str(pdf))
    db.save(doc)

    src = await files_tool(
        inputs={},
        state={"selected_doc_ids": [doc.id], "library_path": library_path},
        llm_config=LLMConfig(provider="", model=""),
    )

    result = await detect_regions(
        inputs={"files": src["files"], "documents": src["documents"], "provider": "kraken"},
        state={"library_path": library_path, "task_id": None},
        llm_config=LLMConfig(provider="", model=""),
    )

    # A PDF has no page image for kraken; the run reports the gap per file
    # rather than silently producing empty geometry.
    assert result.get("error") or (result.get("results") and result["results"][0].get("error"))
