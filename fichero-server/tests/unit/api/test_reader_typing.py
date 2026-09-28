"""Typing in the Reader is a new reading of ONE line; Return splits the caret's line; Backspace at
a line's start joins it to the line before (#5154, the served page's half).

WHY: the engine could record a correction, split and join, and nobody could reach any of it from
the Reader -- the page had no editing at all. The page decides WHICH line an edit is, where in that
line Return fell, and which two lines Backspace joins; Swift turns those three messages into
`representation.create`, `segment.split` and `segment.merge`. If the page names the wrong line, a
correction lands on the neighbour -- silently, since both are plausible text. If it guesses an
edit that crossed two lines, it writes one line's words into another. So: an edit is exactly one
line's or it is refused, and the offsets are the line's own.

The page's functions are cut from the SERVED HTML and run in node, on a real imported page; the
line texts they are checked against are read from the file with plain lxml.
"""

from __future__ import annotations

import json
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import ContentRepresentation
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import ARABIC, _import, _line_texts, _page_functions
from tests.unit.api.test_reader_line_map import _node, _view

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _run(html: str, body: str) -> object:
    return _node(_page_functions(html) + body)


def _page(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    return doc_id, payload["pages"][0], html


def test_the_map_is_the_files_lines(db, client):
    """The premise: each mapped line's text is that line's own text in the file."""
    _, page, _ = _page(db, client)
    shown = [page["content"][line["char_start"]:line["char_end"]] for line in page["lines"]]
    assert shown == [t for t in _line_texts(ARABIC) if t]


def test_typing_in_a_line_is_that_line_and_nothing_else(db, client):
    _, page, html = _page(db, client)
    lines, text = page["lines"], page["content"]
    third = lines[2]
    cut = (third["char_start"] + third["char_end"]) // 2
    now = text[:cut] + "XYZ" + text[cut:]
    got = _run(html, f"""
const lines = {json.dumps(lines)};
const before = {json.dumps(text)}, now = {json.dumps(now)};
const edit = editedLine(before, now, lines, {json.dumps(third["segment_id"])});
const shifted = shiftLines(lines, edit.segmentId, edit.delta);
console.log(JSON.stringify({{ edit, shifted }}));
""")
    file_line = [t for t in _line_texts(ARABIC) if t][2]
    assert got["edit"]["segmentId"] == third["segment_id"]
    assert got["edit"]["previous"] == file_line
    assert got["edit"]["text"] == file_line[:cut - third["char_start"]] + "XYZ" + file_line[cut - third["char_start"]:]
    # after the edit, every line of the map still names its own text in the edited page
    for line in got["shifted"]:
        before_line = next(item for item in lines if item["segment_id"] == line["segment_id"])
        expected = text[before_line["char_start"]:before_line["char_end"]]
        if line["segment_id"] == third["segment_id"]:
            expected = got["edit"]["text"]
        assert now[line["char_start"]:line["char_end"]] == expected


def test_an_edit_across_two_lines_is_refused(db, client):
    _, page, html = _page(db, client)
    lines, text = page["lines"], page["content"]
    a, b = lines[1], lines[2]
    now = text[:a["char_end"] - 2] + text[b["char_start"] + 2:]   # a deletion across the separator
    got = _run(html, f"""
console.log(JSON.stringify(editedLine({json.dumps(text)}, {json.dumps(now)}, {json.dumps(lines)}, {json.dumps(a["segment_id"])})));
""")
    assert got == {"refused": "the edit reached another line"}


def test_return_splits_at_the_caret_in_the_lines_own_text(db, client):
    _, page, html = _page(db, client)
    lines = page["lines"]
    third = lines[2]
    got = _run(html, f"""
const lines = {json.dumps(lines)};
console.log(JSON.stringify([
    lineSplitMessage(lines, "p", {third["char_start"] + 4}),
    lineSplitMessage(lines, "p", {third["char_end"]}),
]));
""")
    assert got == [{"pageId": "p", "segmentId": third["segment_id"], "offset": 4},
                   {"pageId": "p", "segmentId": third["segment_id"], "offset": third["char_end"] - third["char_start"]}]


def test_backspace_joins_only_at_a_lines_start_and_never_the_first(db, client):
    _, page, html = _page(db, client)
    lines = page["lines"]
    got = _run(html, f"""
const lines = {json.dumps(lines)};
console.log(JSON.stringify([
    lineJoinMessage(lines, "p", {lines[3]["char_start"]}),
    lineJoinMessage(lines, "p", {lines[3]["char_start"] + 1}),
    lineJoinMessage(lines, "p", {lines[0]["char_start"]}),
]));
""")
    assert got[0] == {"pageId": "p", "segmentId": lines[3]["segment_id"], "intoSegmentId": lines[2]["segment_id"]}
    assert got[1] is None and got[2] is None


def test_the_edit_message_is_enough_for_the_call_swift_makes(db, client):
    """End to end on the real page: the page's `readingEdit` fields, as `representation.create`
    takes them, give a page whose text shows the correction on that line and no other."""
    doc_id, page, html = _page(db, client)
    lines, text = page["lines"], page["content"]
    third = lines[2]
    now = text[:third["char_end"]] + "!" + text[third["char_end"]:]
    edit = _run(html, f"""
console.log(JSON.stringify(editedLine({json.dumps(text)}, {json.dumps(now)}, {json.dumps(lines)}, {json.dumps(third["segment_id"])})));
""")
    kind = next(r.kind for r in db.all(ContentRepresentation) if r.segment_id == third["segment_id"])
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": edit["segmentId"], "kind": kind, "content": edit["text"],
    }, BOOT)
    after = _view(client, doc_id)[0]["pages"][0]
    assert after["content"] == now
    moved = next(line for line in after["lines"] if line["segment_id"] == third["segment_id"])
    assert after["content"][moved["char_start"]:moved["char_end"]] == edit["text"]
