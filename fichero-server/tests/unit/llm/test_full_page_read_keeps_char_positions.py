"""The full-page Kraken read keeps each line's character positions on its reading.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.char-positions-kept` (when Kraken reads a
line, where each character starts along the baseline is kept on the reading as `char_positions`). The full-page read
(segment and recognise in one go) writes its lines through a result's boxes and the conversion of that result into a
pass; both steps carry the positions.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.llm import kraken_runtime
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import ContentRepresentation
from fichero_server.models.segments import converted_segment_id
from tests.unit.workflows.test_a_new_result_is_a_pass_at_once import _page, _save


def test_a_line_box_from_the_full_page_read_carries_its_positions_trimmed_with_its_text(monkeypatch, tmp_path):
    payload = {"width": 200, "height": 100, "regions": [], "lines": [{
        "polygon": [[10, 10], [190, 10], [190, 40], [10, 40]], "baseline": [[10, 35], [190, 35]],
        "text": " abc ", "confidence": 0.9, "char_positions": [0.0, 0.1, 0.4, 0.7, 0.9],
    }]}
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda *args, **kwargs: payload)

    result = kraken_runtime.recognize_to_geometry(tmp_path / "page.png", "model.mlmodel")

    (line,) = [b for b in result.boxes if b.level == "line"]
    assert line.text == "abc"
    assert line.metadata["char_positions"] == [0.1, 0.4, 0.7], "the stripped spaces take their positions with them"


def test_a_line_with_no_positions_has_none_on_its_box(monkeypatch, tmp_path):
    payload = {"width": 200, "height": 100, "regions": [], "lines": [{
        "polygon": [[10, 10], [190, 10], [190, 40], [10, 40]], "baseline": [[10, 35], [190, 35]],
        "text": "abc", "confidence": 0.9, "char_positions": None,
    }]}
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda *args, **kwargs: payload)

    (line,) = [b for b in kraken_runtime.recognize_to_geometry(tmp_path / "page.png", "m").boxes if b.level == "line"]
    assert "char_positions" not in line.metadata


def test_converting_a_read_result_keeps_each_lines_positions_on_its_reading(db):
    doc = _page(db)
    artifact_id = _save(db, doc, OCRGeometryResult(provider="kraken", model="kraken-test", text="abc\nde", boxes=[
        OCRGeometryBox(text="abc", bbox=[0.1, 0.1, 0.8, 0.1], level="line", source="kraken-htr", char_start=0,
                       char_end=3, metadata={"char_positions": [0.0, 0.3, 0.6]}),
        OCRGeometryBox(text="de", bbox=[0.1, 0.3, 0.8, 0.1], level="line", source="kraken-htr", char_start=4,
                       char_end=6, metadata={"char_positions": [0.0, 0.3, 0.6]}),
    ]))

    def reading_of(index):
        segment_id = converted_segment_id(artifact_id, index)
        (reading,) = db.query(ContentRepresentation, segment_id=segment_id)
        return reading

    assert reading_of(0).char_positions == [0.0, 0.3, 0.6]
    assert reading_of(1).char_positions is None, "positions that do not match the text one to one are not kept"
