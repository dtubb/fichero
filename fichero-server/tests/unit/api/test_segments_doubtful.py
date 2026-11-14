"""The low-confidence lens: a page's lines by confidence, lowest first, with the reasons.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.low-confidence-lens` (the page's lines by
confidence, lowest first: the segmenter's line confidence, a cut's confidence, and the validator's findings; the
head's Next Doubtful steps through them). Reads, writes nothing.
"""
from __future__ import annotations

import pytest

from fichero_server.models.segments import Segment
from tests.unit.api.test_segments_validate import _box, _page, _segment

pytestmark = pytest.mark.source_model


def _line(client, doc, pass_id, y, *, confidence=None, baseline=True):
    sid = _segment(client, doc, pass_id, polygon=_box(0.1, y, 0.8, 0.05),
                   baseline=[[0.1, y + 0.04], [0.9, y + 0.04]] if baseline else None)
    return sid, confidence


def _lens(client, doc):
    response = client.get(f"/api/segments/document/{doc.id}/doubtful")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_lines_come_lowest_confidence_first_a_finding_before_any(db, client):
    doc, pass_id = _page(db, client)
    sure, _ = _line(client, doc, pass_id, 0.1)
    unsure, _ = _line(client, doc, pass_id, 0.2)
    unknown, _ = _line(client, doc, pass_id, 0.3)
    broken, _ = _line(client, doc, pass_id, 0.4, baseline=False)
    for sid, value in ((sure, 0.9), (unsure, 0.4), (broken, 0.95)):
        row = db.get(Segment, sid)
        row.confidence = value
        db.save(row)

    lens = _lens(client, doc)
    assert [line["segment_id"] for line in lens["lines"]] == [broken, unsure, sure, unknown]
    by_id = {line["segment_id"]: line for line in lens["lines"]}
    assert "no-baseline" in by_id[broken]["reasons"]
    assert by_id[unsure]["confidence"] == pytest.approx(0.4)
    assert by_id[unknown]["confidence"] is None and by_id[unknown]["reasons"] == []


def test_a_word_cut_with_low_confidence_lowers_its_line(db, client):
    doc, pass_id = _page(db, client)
    line, _ = _line(client, doc, pass_id, 0.1)
    other, _ = _line(client, doc, pass_id, 0.2)
    db_line = db.get(Segment, other)
    db_line.confidence = 0.8
    db.save(db_line)
    word = _segment(client, doc, pass_id, kind="word", rect=[0.1, 0.1, 0.1, 0.05], parent=line)
    row = db.get(Segment, word)
    row.metadata = {**(row.metadata or {}), "cut_confidence": 0.3}
    db.save(row)

    lens = _lens(client, doc)
    assert [entry["segment_id"] for entry in lens["lines"]][:2] == [line, other]
    assert any("cut" in reason for reason in lens["lines"][0]["reasons"])


def test_reading_it_writes_nothing(db, client):
    doc, pass_id = _page(db, client)
    line, _ = _line(client, doc, pass_id, 0.1)
    version = db.get(Segment, line).version
    _lens(client, doc)
    assert db.get(Segment, line).version == version
