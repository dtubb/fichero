"""#7091: a Kraken read (lines found and read together) writes each word as a word segment under its line.

Driven through the real `save_artifact`, as `test_a_new_result_is_a_pass_at_once.py` is. A reader that gives only line
text (no character positions) makes no words.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, Status

TEXT = "peticion hecha"
W, H = 2000, 3000


def _page(db):
    doc = Document(name="folio 1", doc_type=DocType.file, file_type=FileType.image, path="/p/folio 1.jpg",
                   status=Status.completed, metadata={"width": W, "height": H})
    db.save(doc)
    return doc


def _line(positions):
    return OCRGeometryBox(
        text=TEXT, bbox=[0.1, 0.1, 0.5, 0.04], level="line", provider="kraken", source="kraken-htr",
        char_start=0, char_end=len(TEXT),
        metadata={"polygon_px": [[200, 300], [1200, 300], [1200, 420], [200, 420]],
                  "baseline_px": [[200, 400], [1200, 400]], "pixel_frame": {"width": W, "height": H},
                  **({"char_positions": positions} if positions else {})})


def _save(db, doc, geometry):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.llm_base import save_artifact
    from fichero_server.workflows.tools.vision_base import VisionToolConfig

    tool_config = VisionToolConfig(artifact_type="transcription", update_page_content=True, trigger_embedding=False,
                                   skip_if_artifact_exists=False)
    with patch("fichero_server.db.db_manager.get_database", return_value=db):
        return asyncio.run(save_artifact(
            document_id=doc.id, file_path=None, content=geometry.text, data=None, library_path="/tmp/test.fichero",
            llm_config=LLMConfig(provider="kraken", model="mccatmus"), task_id="run-1",
            tool_config=tool_config, ocr_geometry=geometry))


def _words(db, doc):
    return sorted((s for s in db.query(Segment, document_id=doc.id) if s.kind == "word" and s.deleted_at is None),
                  key=lambda s: s.metadata["reading_span"][0])


def test_a_two_word_line_writes_two_word_segments_under_the_line(db):
    doc = _page(db)
    positions = [i * 0.07 for i in range(len(TEXT))]
    _save(db, doc, OCRGeometryResult(provider="kraken", text=TEXT, source="kraken-htr", boxes=[_line(positions)]))

    line = next(s for s in db.query(Segment, document_id=doc.id) if s.kind == "line")
    words = _words(db, doc)
    assert [w.parent_segment_id for w in words] == [line.id, line.id]
    reading = next(r for r in db.query(ContentRepresentation, segment_id=line.id))
    assert [reading.content[a:b] for a, b in (w.metadata["reading_span"] for w in words)] == ["peticion", "hecha"]


def test_a_line_read_without_positions_makes_no_words(db):
    doc = _page(db)
    _save(db, doc, OCRGeometryResult(provider="kraken", text=TEXT, source="kraken-htr", boxes=[_line(None)]))
    assert _words(db, doc) == []
