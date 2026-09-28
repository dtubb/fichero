"""Out of reach of the engine the Reader's text is read-only and says why; words typed but not taken
are kept, marked, and sent -- with their version check -- when the engine is back (slice 13b,
`source.textedit.stale-keeps-your-words`, last clause, ruled 2026-09-20; the served page's half).

WHY: the engine is a separate process; it restarts, it is on another machine, a laptop sleeps. An
editor that kept taking keystrokes while nothing could receive them would lose them, or post them
blind into a void; one that simply refused would throw away what was already typed. So: the page
stops taking edits and says so in one line, holds what the person typed on the line where they
typed it, and when the engine is back sends each held edit as it was -- still based on the reading
it corrected, so a line someone else changed meanwhile comes back STALE (keep mine / take theirs),
never overwritten. If this regresses, typing during an outage is lost, or a held edit silently
overwrites a correction made while it waited.

The page's rules (`engineLink`, `engineBannerText`) are cut from the SERVED HTML and run in node on a
real imported page; the resend goes through the app's route to the engine.
"""

from __future__ import annotations

import json
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_reader_typing import _page, _run

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _edits(page, html):
    """Two real line edits the page would post: its own `readingEditMessage` on lines 2 and 3."""
    text, lines = page["content"], page["lines"]
    out = []
    for line in lines[1:3]:
        now = text[:line["char_end"]] + " (typed)" + text[line["char_end"]:]
        out.append(_run(html, f"""
console.log(JSON.stringify(readingEditMessage({json.dumps(text)}, {json.dumps(now)}, {json.dumps(lines)}, "p", {json.dumps(line["segment_id"])}).message));
"""))
    return out


def test_out_of_reach_the_page_holds_every_edit_and_posts_nothing(db, client):
    _, page, html = _page(db, client)
    sent, typed_after = _edits(page, html)
    got = _run(html, f"""
const link = engineLink();
const first = link.edit({json.dumps(sent)});                         // posted while in reach
link.lost("the engine stopped", {{ pageId: "p", segmentId: {json.dumps(sent["segmentId"])} }});   // ...and never answered
const second = link.edit({json.dumps(typed_after)});                  // typed as it dropped
console.log(JSON.stringify({{ first, second, reachable: link.reachable, reason: link.reason, held: link.unsent() }}));
""")
    assert got["first"] == sent                                       # it went out
    assert got["second"] is None                                      # this one is HELD, not posted
    assert got["reachable"] is False and got["reason"] == "the engine stopped"
    assert got["held"] == [sent, typed_after]                          # both kept: the words are not lost


def test_back_in_reach_every_held_edit_is_sent_again_with_its_version_check(db, client):
    _, page, html = _page(db, client)
    sent, typed_after = _edits(page, html)
    got = _run(html, f"""
const link = engineLink();
link.edit({json.dumps(sent)});
link.lost(null, {{ pageId: "p", segmentId: {json.dumps(sent["segmentId"])} }});
link.edit({json.dumps(typed_after)});
const resend = link.back();
console.log(JSON.stringify({{ resend, reachable: link.reachable, held: link.unsent(), next: link.edit({json.dumps(sent)}) }}));
""")
    assert got["resend"] == [sent, typed_after]                        # in order, as typed
    assert all(message["basedOn"] for message in got["resend"])        # each still names what it corrected
    assert got["reachable"] is True and got["held"] == [] and got["next"] == sent


def test_a_held_edit_whose_line_moved_on_meanwhile_comes_back_stale(db, client):
    """End to end: the engine is back, the held edit is sent as the app sends every readingEdit
    (basedOn -> expected_counting_id), and someone else's correction made during the outage is not
    overwritten -- the engine refuses it as stale (archive's 24c16562b), and the page's stale flow
    takes over."""
    doc_id, page, html = _page(db, client)
    held, _ = _edits(page, html)
    theirs = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": held["segmentId"], "kind": "transcription",
        "content": held["previous"] + " (corrected during the outage)", "corrects_representation_id": held["basedOn"]}})
    assert theirs.status_code == 200, theirs.text
    resent = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": held["segmentId"], "kind": "transcription", "content": held["text"],
        "corrects_representation_id": held["basedOn"], "expected_counting_id": held["basedOn"]}})
    assert resent.status_code == 409 and resent.json()["detail"]["reason"] == "stale"


def test_the_line_at_the_top_says_why_and_what_happens_to_the_words(db, client):
    _, _, html = _page(db, client)
    got = _run(html, """
console.log(JSON.stringify([engineBannerText("connection refused", 2), engineBannerText(null, 1), engineBannerText(null, 0)]));
""")
    assert got[0] == ("The library can't be reached (connection refused), so the text is read-only. "
                      "2 unsent edits are kept and will be sent when it is back.")
    assert got[1].endswith("1 unsent edit is kept and will be sent when it is back.")
    assert got[2] == "The library can't be reached, so the text is read-only."


def test_through_the_page_s_own_bridge_nothing_is_posted_out_of_reach_and_the_resend_is_the_same_body(db, client):
    """The joint's harness (`test_imported_page_draws_its_boxes.py`): the served page's OWN `notify`
    posting into a stand-in `ficheroBridge`. In reach, an edit reaches the bridge; out of reach, the
    next one does not; back in reach, the held one reaches it byte for byte as it would have -- so
    the app's existing parse of `readingEdit` takes it unchanged, version check included."""
    from tests.unit.api.test_reader_directions import _page_functions
    from tests.unit.api.test_reader_line_map import _node

    _, page, html = _page(db, client)
    before, during = _edits(page, html)
    start = html.index("function notify(kind, payload)")
    notify = html[start:html.index("\n}\n", start) + 3]
    posted = _node(_page_functions(html) + notify + f"""
const posts = [];
window.webkit = {{ messageHandlers: {{ ficheroBridge: {{ postMessage: (body) => posts.push(body) }} }} }};
const link = engineLink();
const send = (m) => {{ const out = link.edit(m); if (out) notify("readingEdit", out); }};
send({json.dumps(before)});
const inReach = posts.length;
link.lost("connection refused");
send({json.dumps(during)});
const outOfReach = posts.length;
for (const m of link.back()) send(m);
console.log(JSON.stringify({{ inReach, outOfReach, posts }}));
""")
    assert posted["inReach"] == 1 and posted["outOfReach"] == 1           # nothing posted while out of reach
    assert posted["posts"] == [{"kind": "readingEdit", **before}, {"kind": "readingEdit", **during}]
