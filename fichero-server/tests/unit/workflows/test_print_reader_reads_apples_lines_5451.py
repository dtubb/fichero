"""`source.recipe.print-reader-reads-apples-lines` (#5451, ruled 2026-10-17, Q4): the reader after Apple's lines reads them.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: on print a recipe finds lines with Apple (lines only, no text)
and then runs a Kraken reader; if the reader found lines of its own, Apple's step did work nothing used. Driven through the real
Detect Segments tool (Apple stubbed, `keep_text` off) and the real Transcribe tool (Kraken's reader stubbed): the readings land on Apple's
lines, on the page's one line pass.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.db.manager import db_manager

WIDTH, HEIGHT = 400, 300
READS = ["imprenta de la viuda", "de don josef", "año de mil setecientos"]
VB = "fichero_server.workflows.tools.vision_base."


@pytest.fixture
async def page(test_package, tmp_path, monkeypatch):
    from PIL import Image

    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.detect_regions import detect_regions
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.vision_base import VisionOCRBox, VisionOCRResult

    library = str(test_package)
    db = db_manager.get_database(library)
    path = tmp_path / "imprenta_p1.png"
    Image.new("RGB", (WIDTH, HEIGHT), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    lines = [VisionOCRBox(text="XQz", bbox=[0.05, y, 0.9, 0.12]) for y in (0.1, 0.35, 0.7)]
    apple = VisionOCRResult(text="XQz\nXQz\nXQz", line_boxes=lines, word_boxes=[])
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=LLMConfig(provider="", model=""))
    with patch(VB + "apple_vision_ocr_with_geometry_async", new=AsyncMock(return_value=apple)):
        found = await detect_regions(
            inputs={"files": src["files"], "documents": src["documents"], "provider": "apple", "keep_text": False},
            state={"library_path": library, "task_id": None}, llm_config=LLMConfig(provider="apple", model="apple-vision"))
    assert not found.get("error"), found.get("error")
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    monkeypatch.setattr(kraken_runtime, "read_given_lines", lambda image_path, model_path, lines, **kw: READS)
    return {"library": library, "db": db, "doc": doc, "src": src}


@pytest.mark.asyncio
async def test_the_kraken_reader_reads_apples_lines_onto_the_one_line_pass(page):
    """source.recipe.print-reader-reads-apples-lines: "puts its readings on those same lines and makes no second pass"."""
    from fichero_server.api.routes.document.segment_readings import counting_texts
    from fichero_server.llm import LLMConfig
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.models.segments import SegmentPass
    from fichero_server.workflows.tools.transcribe import transcribe

    before = working_lines(page["db"], page["doc"].id)
    assert before is not None and len(before.lines) == 3, "Apple's lines-only pass is the page's lines"
    passes_before = {p.id for p in page["db"].query(SegmentPass, document_id=page["doc"].id)}

    done = await transcribe(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"], "vision_mode": "kraken",
                "kraken_model": "kraken-mccatmus", "regions_first": False},
        state={"library_path": page["library"], "task_id": None}, llm_config=LLMConfig(provider="", model=""))

    assert not done.get("error"), done.get("error")
    after = working_lines(page["db"], page["doc"].id)
    assert [r.id for r in after.lines] == [r.id for r in before.lines], "the same lines, not new ones"
    assert {p.id for p in page["db"].query(SegmentPass, document_id=page["doc"].id)} == passes_before
    texts = counting_texts(page["db"], after.lines)
    assert [texts.get(r.id, "") for r in after.lines] == READS
