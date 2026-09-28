"""A line typed against a reading that no longer counts keeps the typed words, marked, with Keep
Mine, Take Theirs and Compare -- and nothing is sent until the person chooses (slice 13b,
`source.textedit.stale-keeps-your-words`, ruled 2026-09-28; the served page's half).

WHY: the engine refuses a reading typed against one that no longer counts (409, naming what counts:
archive's 24c16562b). On the page, the two easy answers are both wrong. Re-reading the page puts
their words over the person's, so what they typed is gone. Re-sending hits the same 409 on every
pause, a loop; re-sending against THEIRS quietly chooses Keep Mine for them. So the words stay on
the line through any re-read, commits of that line are HELD, and only the person's choice sends.
If this regresses, a person's typing vanishes under someone else's correction, or overwrites it
unasked.

End to end through the app's own route (`/api/actions/invoke`, `representation.create` with
`expected_counting_id` = the page's `basedOn`) on a real imported page; the page's functions are
cut from the SERVED HTML and run in node.
"""

from __future__ import annotations

import json
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from tests.unit.api.test_reader_line_map import _view
from tests.unit.api.test_reader_typing import _page, _run

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _stale(db, client):
    """The page's edit of line 3, somebody else's correction landing first, and the app's refusal
    turned into the `lineCommitted` answer the ruling names."""
    doc_id, page, html = _page(db, client)
    text, lines = page["content"], page["lines"]
    third = lines[2]
    now = text[:third["char_end"]] + " (mine)" + text[third["char_end"]:]
    edit = _run(html, f"""
console.log(JSON.stringify(readingEditMessage({json.dumps(text)}, {json.dumps(now)}, {json.dumps(lines)}, "p", {json.dumps(third["segment_id"])})));
""")["message"]
    counted = next(s for s in document_text(db, doc_id).spans if s.segment_id == third["segment_id"])
    reading_kind = "transcription"
    theirs = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": third["segment_id"], "kind": reading_kind,
        "content": edit["previous"] + " (theirs)", "corrects_representation_id": edit["basedOn"]})
    assert theirs.status_code == 200, theirs.text
    refused = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": third["segment_id"], "kind": reading_kind, "content": edit["text"],
        "corrects_representation_id": edit["basedOn"], "expected_counting_id": edit["basedOn"]})
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    answer = {"pageId": "p", "segmentId": third["segment_id"], "ok": False, "stale": True,
              "reason": detail["reason"], "mine": edit["text"],
              "theirs": {"representationId": detail["counting_representation_id"], "text": detail["counting_text"]}}
    assert counted.representation_id == edit["basedOn"]            # the page based it on what counted
    return doc_id, page, html, edit, answer


def test_keep_mine_sends_the_same_words_against_what_counts_now_and_it_lands(db, client):
    doc_id, _page_, html, edit, answer = _stale(db, client)
    message = _run(html, f"""
console.log(JSON.stringify(keepMineMessage("p", {json.dumps(answer["segmentId"])}, {json.dumps(answer)})));
""")
    assert message == {"pageId": "p", "segmentId": answer["segmentId"], "text": edit["text"],
                       "previous": answer["theirs"]["text"], "basedOn": answer["theirs"]["representationId"]}
    # The app sends it as it sends every readingEdit: basedOn is the correction target and the token.
    kept = _invoke(client, "representation.create", {
        "document_id": doc_id, "segment_id": message["segmentId"], "kind": "transcription",
        "content": message["text"], "corrects_representation_id": message["basedOn"],
        "expected_counting_id": message["basedOn"]})
    assert kept.status_code == 200, kept.text
    after = _view(client, doc_id)[0]["pages"][0]
    line = next(item for item in after["lines"] if item["segment_id"] == message["segmentId"])
    assert after["content"][line["char_start"]:line["char_end"]] == edit["text"]


def test_a_stale_line_is_held_never_re_sent(db, client):
    """No auto-commit loop: however many pauses, a stale line's edit is held; a line that is not
    stale is sent; an edit reaching two lines is refused either way."""
    _, _, html, _, _ = _stale(db, client)
    got = _run(html, """
const edit = { message: {}, delta: 1 };
console.log(JSON.stringify([commitDecision(edit, {mine: "x"}), commitDecision(edit, undefined),
    commitDecision({ refused: "the edit reached another line" }, {mine: "x"}), commitDecision(null, undefined)]));
""")
    assert got == ["hold", "send", "refuse", "nothing"]


def test_a_re_read_keeps_the_stale_words_on_their_line(db, client):
    """Their correction is in the library's page now; the person's words stay on the line until
    they choose, and an edit on ANOTHER line is still measured exactly against what is shown."""
    doc_id, page, html, edit, answer = _stale(db, client)
    fresh = _view(client, doc_id)[0]["pages"][0]
    first = fresh["lines"][0]
    got = _run(html, f"""
const shown = overlayLines({json.dumps(fresh)}, [{{ segmentId: {json.dumps(answer["segmentId"])}, text: {json.dumps(answer["mine"])} }}]);
const line = shown.lines.find((l) => l.segment_id === {json.dumps(answer["segmentId"])});
const typed = shown.content.slice(0, {first["char_end"]}) + "!" + shown.content.slice({first["char_end"]});
const other = readingEditMessage(shown.content, typed, shown.lines, "p", {json.dumps(first["segment_id"])});
console.log(JSON.stringify({{ stale: shown.content.slice(line.char_start, line.char_end), other }}));
""")
    assert got["stale"] == answer["mine"]
    first_text = fresh["content"][first["char_start"]:first["char_end"]]
    assert got["other"]["message"]["text"] == first_text + "!"
    assert got["other"]["message"]["previous"] == first_text


def test_compare_shows_theirs_struck_against_mine_and_the_bar_offers_three_choices(db, client):
    _, _, html, _, answer = _stale(db, client)
    got = _run(html, f"""
console.log(JSON.stringify({{
  diff: wordDiff("anno domini mcccc", "anno domini mccccx"),
  bar: staleBarMarkup("seg<1>", {json.dumps(answer)}, false),
  comparing: staleBarMarkup("seg1", {{ mine: "a <b>", theirs: {{ text: "a c", representationId: "r" }} }}, true),
}}));
""")
    assert got["diff"] == [{"op": "same", "text": "anno domini"}, {"op": "del", "text": "mcccc"},
                           {"op": "ins", "text": "mccccx"}]
    for action in ('data-stale-action="mine"', 'data-stale-action="theirs"', 'data-stale-action="compare"'):
        assert action in got["bar"]
    assert 'data-segment-id="seg&lt;1&gt;"' in got["bar"]                       # escaped
    assert "<del>c</del>" in got["comparing"] and "<ins>&lt;b&gt;</ins>" in got["comparing"]


def test_when_nothing_counts_keep_mine_sends_with_no_basis(db, client):
    """Archive's app half (c28a10f86): `theirs.*` is null when no reading counts now. Keep Mine then
    carries no basis -- the app sends no token, so it lands -- and Compare shows mine as all new."""
    _, _, html, _, _ = _stale(db, client)
    got = _run(html, """
const stale = { mine: "anno domini", theirs: { representationId: null, text: null } };
console.log(JSON.stringify({ message: keepMineMessage("p", "s", stale), diff: wordDiff(stale.theirs.text, stale.mine),
                             bar: staleBarMarkup("s", stale, true).includes("<ins>anno domini</ins>") }));
""")
    assert got["message"] == {"pageId": "p", "segmentId": "s", "text": "anno domini", "previous": None, "basedOn": None}
    assert got["diff"] == [{"op": "ins", "text": "anno domini"}] and got["bar"] is True
