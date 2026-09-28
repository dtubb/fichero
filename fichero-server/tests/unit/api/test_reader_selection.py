"""One selection across the Source view, the Reader and the Inspector (#5155, the page's half).

WHY: the Reader's caret and the Source view's selection were two unrelated things, so a line
picked in one was not the line shown in the other. The page posts `lineFocused` when the caret
comes onto a different line (once per change: per key would flood the app's selection and its
Inspector reload), and draws the app's selection over the lines the app names, by their offsets in
the line map -- drawn as a highlight over ranges, never by wrapping a line in an element (the
claim highlighter walks the body's text as it is). If this regresses, the Reader lights the wrong
line, or floods the app with a message per keystroke.

The functions are cut from the SERVED page and run in node, over a real imported page's map.
"""

from __future__ import annotations

import json
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_reader_directions import ARABIC, _import, _page_functions
from tests.unit.api.test_reader_line_map import _node, _view

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def test_focus_is_posted_once_per_line_change(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    lines = payload["pages"][0]["lines"]
    a, b = lines[1]["segment_id"], lines[2]["segment_id"]
    got = _node(_page_functions(html) + f"""
const at = (s) => ({{ pageId: "p", segmentId: s }});
console.log(JSON.stringify([
    lineFocusMessage(null, at({json.dumps(a)})),
    lineFocusMessage(at({json.dumps(a)}), at({json.dumps(a)})),
    lineFocusMessage(at({json.dumps(a)}), at({json.dumps(b)})),
    lineFocusMessage(at({json.dumps(a)}), null),
]));
""")
    assert got == [{"pageId": "p", "segmentId": a}, None, {"pageId": "p", "segmentId": b}, None]


def test_the_apps_selection_names_exactly_those_lines_text(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    lines = page["lines"]
    wanted = [lines[4]["segment_id"], lines[1]["segment_id"], "a-line-on-another-page"]
    got = _node(_page_functions(html) + f"""
const maps = new Map([[{json.dumps(page["id"])}, {json.dumps(lines)}]]);
console.log(JSON.stringify([selectedLineSpans(maps, {json.dumps(wanted)}), selectedLineSpans(maps, [])]));
""")
    spans, cleared = got
    assert [page["content"][s["start"]:s["end"]] for s in spans] == [
        page["content"][lines[i]["char_start"]:lines[i]["char_end"]] for i in (1, 4)]   # page order
    assert cleared == []


def test_the_selection_is_drawn_without_touching_the_text(db, client):
    """A highlight over ranges, styled by the system selection colour; never a wrapper element."""
    doc_id = _import(db, ARABIC)
    _, html = _view(client, doc_id)
    assert "::highlight(fichero-selected-lines)" in html and "Highlight 28%" in html
    assert 'CSS.highlights.set("fichero-selected-lines"' in html
