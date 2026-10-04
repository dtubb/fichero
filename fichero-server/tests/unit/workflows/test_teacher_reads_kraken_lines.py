"""The teacher reads the lines Kraken found (`distill.collect.teacher-reads-the-lines`).

Spec (compute/distillation.md): "Transcribe in Kraken mode with `lines_read_by: "model"` has Kraken
find each line and the run's vision model read each line's crop, a few per call; the pass keeps
Kraken's geometry ...; a line the teacher says holds no writing is dropped and counted; a batch answer
that does not match line for line is re-asked one line at a time."

WHY: these pairs (Kraken's line picture, the teacher's text) are what a small reader is trained on.
A line given its neighbour's text, or a ruler given invented words, teaches the student to misread.
Driven through the real Transcribe tool; only Kraken's line finder and the model's answers are faked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

TEACHER = ("openrouter", "google/gemini-3-flash-preview")


def _found_lines(n: int) -> OCRGeometryResult:
    """Kraken's segmenter output: n lines with polygons and baselines, no text."""
    return OCRGeometryResult(text="", provider="kraken", model="blla", source="kraken-blla", boxes=[
        OCRGeometryBox(text="", bbox=[0.05, 0.1 + 0.08 * i, 0.9, 0.06], level=OCRGeometryLevel.LINE,
                       provider="kraken", model="blla", source="kraken-blla",
                       metadata={"line_index": i,
                                 "polygon_px": [[10, 20 + 40 * i], [190, 20 + 40 * i], [190, 45 + 40 * i], [10, 45 + 40 * i]],
                                 "baseline_px": [[10, 40 + 40 * i], [190, 40 + 40 * i]],
                                 "pixel_frame": {"width": 200, "height": 400}})
        for i in range(n)])


async def _run(library, doc):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=LLMConfig(provider="", model=""))
    return await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                "lines_read_by": "model", "regions_first": False},
        state={"library_path": library}, llm_config=LLMConfig(provider=TEACHER[0], model=TEACHER[1]))


def _page(db, tmp_path):
    from PIL import Image
    from fichero_server.models import DocType, Document, FileType

    path = tmp_path / "SM_NPQ_C01_005.png"
    Image.new("RGB", (200, 400), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def _saved(db, doc):
    from fichero_server.models import Artifact

    arts = [a for a in db.query(Artifact, document_id=doc.id) if a.artifact_type == "transcription"]
    assert len(arts) == 1, arts
    return arts[0]


@pytest.mark.asyncio
async def test_the_saved_reading_keeps_krakens_lines_and_the_teachers_words(test_package, tmp_path, monkeypatch):
    import fichero_server.llm as llm
    import fichero_server.llm.kraken_runtime as kraken_runtime

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, rendition_id=None: _found_lines(3))
    words = iter(["el engaño de lo que se compra", None, "por la mitad mas o menos"])

    async def teacher(images, prompt, config, **_):
        return "[" + ", ".join('"%s"' % w if w else "null" for w in (next(words) for _ in images)) + "]"

    monkeypatch.setattr(llm, "vision", teacher)
    result = await _run(library, doc)
    assert not result.get("error"), result.get("error")

    art = _saved(db, doc)
    lines = art.ocr_geometry.boxes
    assert (art.provider, art.model) == TEACHER  # the reading is the teacher's, not Kraken's
    assert [b.text for b in lines] == ["el engaño de lo que se compra", "por la mitad mas o menos"]
    # Kraken's own geometry for the lines kept: the first and third found lines, the middle one dropped.
    assert [b.metadata["line_index"] for b in lines] == [0, 2]
    assert all(b.metadata["baseline_px"] for b in lines)
    assert art.ocr_geometry.metadata["lines_without_writing"] == 1


@pytest.mark.asyncio
async def test_an_answer_that_does_not_match_line_for_line_is_asked_again_one_line_at_a_time(
        test_package, tmp_path, monkeypatch):
    import fichero_server.llm as llm
    import fichero_server.llm.kraken_runtime as kraken_runtime

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, rendition_id=None: _found_lines(3))
    asked = []

    async def teacher(images, prompt, config, **_):
        asked.append(len(images))
        if len(images) > 1:
            return '["only two", "answers"]'  # three pictures, two answers: which is which?
        return '["line %d"]' % len(asked)

    monkeypatch.setattr(llm, "vision", teacher)
    result = await _run(library, doc)
    assert not result.get("error"), result.get("error")

    assert asked[0] == 3 and sorted(asked[1:]) == [1, 1, 1]
    texts = [b.text for b in _saved(db, doc).ocr_geometry.boxes]
    assert "only two" not in texts and len(texts) == 3
