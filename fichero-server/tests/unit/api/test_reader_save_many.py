"""A Reader edit across lines is ONE audited step, and a line deleted entirely is left out, not deleted.

WHY: typing in the Reader saved one reading per call, and a change that reached two lines was
refused on the page. `representation.create_many` writes the readings and marks the emptied lines
`is_furniture` (they drop out of the Reader text) under one audit id, so one undo reverses it all;
a line's segment is never deleted. If this regresses, a Reader edit is several undo steps, or
deleting a line's words deletes its box.

Through `format.import` of a real page and the real HTTP routes.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import Segment
from tests.unit.api.test_reader_directions import ARABIC, _import, _line_texts
from tests.unit.api.test_reader_line_map import _view


def _lines(client, doc_id):
    return _view(client, doc_id)[0]["pages"][0]["lines"]


def _batch(client, doc_id, lines):
    return client.post("/api/content-representations/batch", json={
        "readings": [{"document_id": doc_id, "segment_id": lines[0]["segment_id"], "kind": "transcription",
                      "content": "edited first", "corrects_representation_id": lines[0]["representation_id"]}],
        "left_out": [{"segment_id": lines[1]["segment_id"], "expected_version": 1}],
    })


def test_one_edit_is_one_step_and_the_emptied_line_is_left_out_not_deleted(db, client):
    doc_id = _import(db, ARABIC)
    lines = _lines(client, doc_id)
    emptied = lines[1]
    gone = [t for t in _line_texts(ARABIC) if t][1]
    before_text = document_text(db, doc_id).text
    assert gone in before_text
    answer = _batch(client, doc_id, lines)
    assert answer.status_code == 200, answer.text
    row = db.get(Segment, emptied["segment_id"])
    assert row.deleted_at is None and row.is_furniture is True
    text = document_text(db, doc_id).text
    assert "edited first" in text and gone not in text

    undone = client.post(f"/api/actions/audit/{answer.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    assert db.get(Segment, emptied["segment_id"]).is_furniture is False
    assert document_text(db, doc_id).text == before_text

    redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
    assert redone.status_code == 200, redone.text
    assert db.get(Segment, emptied["segment_id"]).is_furniture is True
    assert "edited first" in document_text(db, doc_id).text


def test_one_stale_line_refuses_the_whole_edit(db, client):
    doc_id = _import(db, ARABIC)
    lines = _lines(client, doc_id)
    answer = client.post("/api/content-representations/batch", json={
        "readings": [{"document_id": doc_id, "segment_id": lines[0]["segment_id"], "kind": "transcription",
                      "content": "must not be written"}],
        "left_out": [{"segment_id": lines[1]["segment_id"], "expected_version": 99}],
    })
    assert answer.status_code == 409
    assert "must not be written" not in document_text(db, doc_id).text
    assert db.get(Segment, lines[1]["segment_id"]).is_furniture is False


def test_an_empty_batch_is_refused(client):
    assert client.post("/api/content-representations/batch", json={}).status_code == 422
