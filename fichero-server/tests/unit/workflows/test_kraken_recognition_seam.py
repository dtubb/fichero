"""Kraken RECOGNITION through the shared vision seam (#4671 — "kraken for text").

Option A: the vision_mode="kraken" seam reads each line with a recognition model
when one is configured, and reuses ALL of process_vision's persistence — so the
transcript lands in page_content and the per-line baseline geometry rides on the
transcription artifact's ocr_geometry. With NO recognition model the seam stays
segment-only (baselines, empty text), byte-for-byte as before. Both are pinned
here; the Kraken runtime is mocked (no ~1 GB venv, no model download).
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


def _recognized_geometry():
    """What recognize_to_geometry returns: text tied to each baseline."""
    from fichero_server.media.ocr_geometry import (
        OCRGeometryBox,
        OCRGeometryLevel,
        OCRGeometryResult,
    )

    text = "vecino de la ciudad\nde Santa Fe"
    lines = text.split("\n")
    boxes = []
    cursor = 0
    for i, line in enumerate(lines):
        start = cursor
        cursor += len(line)
        boxes.append(
            OCRGeometryBox(
                text=line,
                bbox=[0.1, 0.1 + 0.1 * i, 0.8, 0.05],
                level=OCRGeometryLevel.LINE,
                provider="kraken",
                model="kraken-mccatmus",
                source="kraken-htr",
                char_start=start,
                char_end=cursor,
                metadata={"baseline_px": [[100.0, 300.0 + 100 * i], [900.0, 300.0 + 100 * i]]},
            )
        )
        cursor += 1  # the "\n"
    return OCRGeometryResult(
        text=text, provider="kraken", model="kraken-mccatmus",
        boxes=boxes, source="kraken-htr",
    )


def _segment_only_geometry():
    from fichero_server.media.ocr_geometry import (
        OCRGeometryBox,
        OCRGeometryLevel,
        OCRGeometryResult,
    )

    return OCRGeometryResult(
        text="", provider="kraken", model="blla", source="kraken-blla",
        boxes=[
            OCRGeometryBox(
                text="", bbox=[0.1, 0.1, 0.8, 0.05], level=OCRGeometryLevel.LINE,
                provider="kraken", model="blla", source="kraken-blla",
                metadata={"baseline_px": [[100.0, 300.0], [900.0, 300.0]]},
            )
        ],
    )


async def _run_transcribe(library_path, doc, extra_config):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    src = await files_tool(
        inputs={},
        state={"selected_doc_ids": [doc.id], "library_path": library_path},
        llm_config=LLMConfig(provider="", model=""),
    )
    return await transcribe(
        inputs={
            "files": src["files"],
            "documents": src["documents"],
            "vision_mode": "kraken",
            "regions_first": False,
            **extra_config,
        },
        state={"library_path": library_path, "task_id": None},
        llm_config=LLMConfig(provider="", model=""),
    )


@pytest.mark.asyncio
async def test_recognition_saves_transcript_tied_to_baselines(temp_library, tmp_path):
    from fichero_server.models import Artifact, Document, DocType, FileType
    import fichero_server.llm.kraken_runtime as kraken_runtime

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)
    png = tmp_path / "hand.png"
    _make_png(png)
    doc = Document(name="hand.png", doc_type=DocType.file, file_type=FileType.image, path=str(png))
    db.save(doc)

    seen = {}

    def _fake_recognize(image_path, model_path, *, model_id=None, rendition_id=None, home=None):
        seen["path"] = image_path
        seen["model_id"] = model_id
        return _recognized_geometry()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(kraken_runtime, "recognize_to_geometry", _fake_recognize)
        mp.setattr(kraken_runtime, "resolve_recognition_model",
                   lambda ref: ("/models/mccatmus.mlmodel", "kraken-mccatmus"))
        result = await _run_transcribe(library_path, doc, {"kraken_model": "kraken-mccatmus"})

    assert not result.get("error"), result.get("error")
    assert seen.get("path"), "kraken recogniser was not called"
    assert seen.get("model_id") == "kraken-mccatmus"

    # The transcript became the page's content.
    reloaded = db.get(Document, doc.id)
    assert reloaded.page_content == "vecino de la ciudad\nde Santa Fe"

    # And it is tied to baselines on the transcription artifact's geometry.
    arts = db.query(Artifact, document_id=doc.id, artifact_type="transcription")
    assert len(arts) == 1, "kraken recognition did not persist a transcription artifact"
    geometry = arts[0].ocr_geometry
    assert geometry is not None and geometry.source == "kraken-htr"
    assert [b.text for b in geometry.boxes] == ["vecino de la ciudad", "de Santa Fe"]
    assert geometry.boxes[0].metadata["baseline_px"] == [[100.0, 300.0], [900.0, 300.0]]
    # char spans slice the saved transcript back to each line, exactly.
    for box in geometry.boxes:
        assert geometry.text[box.char_start:box.char_end] == box.text


@pytest.mark.asyncio
async def test_no_recognition_model_stays_segment_only(temp_library, tmp_path):
    """The guard: with no recognition model the kraken seam is unchanged —
    segment_to_geometry (not recognize), empty transcript."""
    from fichero_server.models import Document, DocType, FileType
    import fichero_server.llm.kraken_runtime as kraken_runtime

    library_path, db_manager = temp_library
    db = db_manager.get_database(library_path)
    png = tmp_path / "hand.png"
    _make_png(png)
    doc = Document(name="hand.png", doc_type=DocType.file, file_type=FileType.image, path=str(png))
    db.save(doc)

    calls = {"segment": 0, "recognize": 0}

    def _fake_segment(image_path, rendition_id=None, home=None):
        calls["segment"] += 1
        return _segment_only_geometry()

    def _fake_recognize(*a, **k):
        calls["recognize"] += 1
        return _recognized_geometry()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(kraken_runtime, "segment_to_geometry", _fake_segment)
        mp.setattr(kraken_runtime, "recognize_to_geometry", _fake_recognize)
        # No kraken_model in config → segment-only.
        result = await _run_transcribe(library_path, doc, {})

    assert not result.get("error"), result.get("error")
    assert calls["segment"] == 1, "segment-only path must still call segment_to_geometry"
    assert calls["recognize"] == 0, "no recognition model must NOT trigger recognition"
