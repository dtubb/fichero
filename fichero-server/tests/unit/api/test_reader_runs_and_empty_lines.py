"""A run of typing is one reading, ended by a pause, Save, leaving the line, a structural key or
blur; words still being typed survive the page being re-read; and a line whose words were all
deleted stays on the page as an empty line (slice 13b: `a-run-of-keys-is-one-action`,
`deleting-words-keeps-ink`; the served page's half).

WHY: per keystroke would make every letter a reading, an audit row and a ⌘Z step. Never ending a
run while the caret stays put would leave a morning's work unsent until the line is left. Worse,
the app re-reads the page after every commit, and before this the re-read replaced the body and
dropped `pendingEdit`: words typed in the moment between a commit and its re-read were silently
lost. And a line emptied of words vanished into two adjacent spaces, so nothing on the page said
the line was still there to type into again. If this regresses, typing is lost or a line
disappears.

The page's functions are cut from the SERVED HTML and run in node, on a real imported page whose
line texts come from the file (`test_reader_typing`'s page); the library's side goes through
`representation.create`, the action the app calls.
"""

from __future__ import annotations

import json
import re
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import ContentRepresentation
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_typing import _page, _run

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _clock() -> str:
    """A test clock for `pauseCommitter`: `at(ms)` fires every timer due by then."""
    return """
let now = 0, timers = [], commits = [];
const setT = (f, ms) => { const t = { f, due: now + ms }; timers.push(t); return t; };
const clearT = (t) => { timers = timers.filter((x) => x !== t); };
const at = (ms) => { now = ms; for (const t of timers.filter((x) => x.due <= now)) { clearT(t); t.f(); } };
"""


def test_a_pause_of_two_seconds_ends_the_run_and_the_next_key_starts_another(db, client):
    _, _, html = _page(db, client)
    got = _run(html, _clock() + """
const run = pauseCommitter(() => commits.push(now), setT, clearT);
run.touch(); at(500); run.touch(); at(1900); run.touch(); at(3000);   // keys 0.5 s and 1.4 s apart
const typing = commits.length;                                        // still one run
at(3900);                                                             // 2 s after the last key
const paused = commits.slice();
run.touch(); at(5000); run.cancel(); at(9000);                        // a new run, ended by leaving
console.log(JSON.stringify({ typing, paused, after: commits }));
""")
    assert got == {"typing": 0, "paused": [3900], "after": [3900]}


def _kind(db, segment_id):
    return next(r.kind for r in db.all(ContentRepresentation) if r.segment_id == segment_id)


def test_words_being_typed_survive_the_page_being_re_read(db, client):
    """The re-read after one commit lands while the next run is typed: the library's page comes
    in (another line changed there too), and the unsent words stay on their line -- then commit
    as exactly that line's edit, based on the reading the library now counts."""
    from fichero_server.api.routes.document.segment_readings import document_text
    from tests.unit.api.test_reader_line_map import _view

    doc_id, page, html = _page(db, client)
    lines, text = page["lines"], page["content"]
    first, third = lines[0], lines[2]
    typing = text[:third["char_end"]] + " und so" + text[third["char_end"]:]      # unsent, on line 3
    registry.invoke(db, "representation.create", {                              # meanwhile, line 1
        "document_id": doc_id, "segment_id": first["segment_id"], "kind": _kind(db, first["segment_id"]),
        "content": "EDITED ELSEWHERE"}, BOOT)
    fresh = _view(client, doc_id)[0]["pages"][0]
    got = _run(html, f"""
const kept = keepUnsent({json.dumps(fresh)}, {json.dumps(text)}, {json.dumps(typing)}, {json.dumps(lines)}, {json.dumps(third["segment_id"])});
const edit = readingEditMessage(kept.text, kept.shown, kept.lines, "p", {json.dumps(third["segment_id"])});
console.log(JSON.stringify({{ kept, edit }}));
""")
    assert got["kept"]["text"] == fresh["content"] and got["kept"]["shown"].startswith("EDITED ELSEWHERE")
    line_text = text[third["char_start"]:third["char_end"]]
    assert got["edit"]["message"]["text"] == line_text + " und so"
    assert got["edit"]["message"]["previous"] == line_text
    counted = {s.segment_id: s.representation_id for s in document_text(db, doc_id).spans}
    assert got["edit"]["message"]["basedOn"] == counted[third["segment_id"]]


def test_nothing_unsent_means_the_library_page_as_it_is(db, client):
    _, page, html = _page(db, client)
    text, lines = page["content"], page["lines"]
    got = _run(html, f"""
console.log(JSON.stringify(keepUnsent({json.dumps(page)}, {json.dumps(text)}, {json.dumps(text)}, {json.dumps(lines)}, {json.dumps(lines[0]["segment_id"])})));
""")
    assert got is None


def test_the_next_run_is_based_on_the_reading_the_last_one_made(db, client):
    """`lineCommitted` names the reading a commit made; the next run on that line corrects IT, not
    the one before (which would be a stale basis before the page is even re-read)."""
    _, page, html = _page(db, client)
    text, lines = page["content"], page["lines"]
    third = lines[2]
    now = text[:third["char_end"]] + "!" + text[third["char_end"]:]
    got = _run(html, f"""
const map = withReading({json.dumps(lines)}, {json.dumps(third["segment_id"])}, "rep-just-made");
console.log(JSON.stringify(readingEditMessage({json.dumps(text)}, {json.dumps(now)}, map, "p", {json.dumps(third["segment_id"])})));
""")
    assert got["message"]["basedOn"] == "rep-just-made"


def test_a_line_whose_words_are_all_deleted_stays_on_the_page(db, client):
    """Deleting a line's words is a NEW, empty reading (`representation.create`, never a segment
    delete); the page still shows the line, in its place, under its segment, with the page text and
    its offsets exactly the library's."""
    from tests.unit.api.test_reader_line_map import _view

    doc_id, page, html = _page(db, client)
    second = page["lines"][1]
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": second["segment_id"], "kind": _kind(db, second["segment_id"]),
        "content": ""}, BOOT)
    after = _view(client, doc_id)[0]["pages"][0]
    emptied = next(line for line in after["lines"] if line["segment_id"] == second["segment_id"])
    assert emptied["char_start"] == emptied["char_end"]                         # still in the map
    markup = _run(html, f"""
console.log(JSON.stringify(pageBodyMarkup({json.dumps({"content": after["content"], "lines": after["lines"]})})));
""")
    marker = f'<span class="line-empty" data-segment-id="{second["segment_id"]}"></span>'
    assert markup.count(marker) == 1
    text_only = re.sub(r"<[^>]+>", "", markup)
    import html as html_lib
    assert html_lib.unescape(text_only) == after["content"]                   # no offset moved
    before_marker = html_lib.unescape(re.sub(r"<[^>]+>", "", markup[:markup.index(marker)]))
    assert len(before_marker) == emptied["char_start"]                         # in its own place
    at = _run(html, f"""
console.log(JSON.stringify(segmentAtOffset({json.dumps(after["lines"])}, {emptied["char_start"]})));
""")
    assert at == second["segment_id"]                                          # typing there is that line
