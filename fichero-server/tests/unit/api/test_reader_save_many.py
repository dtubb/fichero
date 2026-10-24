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


# ---- the page's half: a multi-line deletion becomes one batch, a refusal is said ----

import json  # noqa: E402
import shutil  # noqa: E402

import pytest  # noqa: E402

from tests.unit.api.test_reader_directions import _page_functions  # noqa: E402
from tests.unit.api.test_reader_line_map import _node  # noqa: E402

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _edited_lines(html, before, now, lines):
    return _node(_page_functions(html) + f"""
console.log(JSON.stringify(editedLines({json.dumps(before)}, {json.dumps(now)}, {json.dumps(lines)})));
""")


@needs_node
def test_a_deletion_across_lines_joins_head_and_tail_and_leaves_the_swallowed_lines_out(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    lines, text = page["lines"], page["content"]
    a, b, c = lines[1], lines[2], lines[3]
    now = text[:a["char_start"] + 2] + text[c["char_start"] + 2:]   # from inside line 1 to inside line 3
    got = _edited_lines(html, text, now, lines)
    head, tail = text[a["char_start"]:a["char_start"] + 2], text[c["char_start"] + 2:c["char_end"]]
    assert got["readings"][0]["segmentId"] == a["segment_id"] and got["readings"][0]["text"] == head + tail
    assert got["leftOut"] == [b["segment_id"], c["segment_id"]]
    for line in got["lines"]:   # the map still names each surviving line's own text in the edited page
        expected = got["readings"][0]["text"] if line["segment_id"] == a["segment_id"] else \
            text[next(i for i in lines if i["segment_id"] == line["segment_id"])["char_start"]:
                 next(i for i in lines if i["segment_id"] == line["segment_id"])["char_end"]]
        assert now[line["char_start"]:line["char_end"]] == expected


@needs_node
def test_a_line_deleted_entirely_is_left_out_with_no_reading(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    lines, text = page["lines"], page["content"]
    a = lines[1]
    now = text[:a["char_start"]] + text[a["char_end"]:]
    got = _edited_lines(html, text, now, lines)
    assert got["readings"] == [] and got["leftOut"] == [a["segment_id"]]


@needs_node
def test_a_paste_of_several_lines_is_refused_and_the_page_says_so(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    lines, text = page["lines"], page["content"]
    a, b = lines[1], lines[2]
    now = text[:a["char_start"] + 1] + "x\ny" + text[b["char_start"] + 1:]
    got = _edited_lines(html, text, now, lines)
    assert "refused" in got
    # the silent revert is gone: the commit's refusal branch shows a notice
    assert 'id="edit-notice"' in html and "showEditNotice(" in html
