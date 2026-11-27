"""The owner's review list as a console page (#6589, `dev-workflows.run.loop-status` Review page): the review file in the state dir, GET /review,
GET and POST /api/review, and `builder review add|set|list`. Nothing here touches the real state dir."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import console, journal, review_page

ITEM = {"id": "activity-started-by", "title": "Activity: who started a run", "area": "Mac · Activity", "build": "2026.11.24 (43)",
        "how": ["Run a recipe step.", "Open the Activity window."], "why": "Stage 8.", "issue": "https://example.test/issues/5960",
        "status": "to-test", "note": "", "order": 90, "added": "2026-11-23"}


class GH:
    calls: list = []

    @staticmethod
    def call(*a):
        GH.calls.append(a)
        return 0, ""


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(review_page, "_gh", GH.call)  # never the real gh: a verdict comments on its issue
    GH.calls.clear()
    review_page.path().write_text(json.dumps({"items": [ITEM, {**ITEM, "id": "b", "title": "B", "order": 209, "status": "works"}, {**ITEM, "id": "c", "title": "C", "order": 10}]}))
    return tmp_path


@pytest.fixture
def live(state, monkeypatch):
    monkeypatch.setattr(console, "ROOT", state)
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, body, token=None, host=None):
    req = urllib.request.Request(url + "/api/review", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Builder-Token": token} if token else {}), **({"Host": host} if host else {})})
    try:
        r = urllib.request.urlopen(req, timeout=5)  # nosec B310 -- the URL is the test's own console server on 127.0.0.1 (#7100)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_add_refuses_a_duplicate_a_missing_title_and_an_unknown_status_and_defaults_the_rest(state):
    new = review_page.add("n1", title="New", how=["one"], now="2026-11-24T10:00:00")
    assert new["status"] == "to-test" and new["order"] == 210 and new["added"] == "2026-11-24" and new["note"] == "" and new["how"] == ["one"]
    assert [i["id"] for i in review_page.load()["items"]] == ["activity-started-by", "b", "c", "n1"]
    for ident, kw, why in (("n1", {"title": "x"}, "already"), ("n2", {"title": ""}, "title"), ("n3", {"title": "x", "status": "meh"}, "status"), ("Bad Id", {"title": "x"}, "id")):
        with pytest.raises(ValueError, match=why):
            review_page.add(ident, **kw)


def test_set_changes_status_and_note_stamps_updated_and_refuses_unknown_ids_and_statuses(state):
    item = review_page.set_item("c", status="bug", note="crashes", now="2026-11-24T11:00:00")
    assert item["status"] == "bug" and item["note"] == "crashes" and item["updatedAt"] == "2026-11-24T11:00:00"
    assert review_page.set_item("c", note="again", now="2026-11-24T11:05:00")["status"] == "bug", "a note alone keeps the status"
    with pytest.raises(ValueError, match="no review item"):
        review_page.set_item("zz", status="works")
    with pytest.raises(ValueError, match="status"):
        review_page.set_item("c", status="done")
    assert review_page.load()["items"][2]["note"] == "again"


def test_listing_filters_by_changed_since_and_orders_to_test_first_highest_order_first(state):
    review_page.set_item("c", status="polish", note="n", now="2026-11-24T11:00:00")
    assert [i["id"] for i in review_page.listing()] == ["activity-started-by", "b", "c"], "to-test first, then the other statuses; highest order first within one"
    assert [i["id"] for i in review_page.listing(changed_since="2026-11-24T10:00:00")] == ["c"]
    assert review_page.listing(changed_since="2026-11-24T12:00:00") == []


def test_a_missing_file_is_an_empty_list_and_a_broken_one_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    assert review_page.load() == {"items": []}
    review_page.path().write_text("{not json")
    with pytest.raises(ValueError, match="review"):
        review_page.load()


def test_the_cli_adds_sets_and_lists_and_the_old_review_actions_still_parse(state, capsys):
    assert cli.main(["review", "add", "n1", "--title", "T", "--where", "Mac", "--build", "43", "--how", "a", "--how", "b", "--why", "w", "--issue", "https://x.test/1",
                     "--order", "300", "--state", str(state)]) == 0
    n1 = next(i for i in review_page.load()["items"] if i["id"] == "n1")
    assert n1["how"] == ["a", "b"] and n1["area"] == "Mac" and n1["order"] == 300 and n1["issue"] == "https://x.test/1"
    assert cli.main(["review", "set", "n1", "--status", "works", "--note", "fine", "--state", str(state)]) == 0
    assert cli.main(["review", "set", "nope", "--status", "works", "--state", str(state)]) == 1
    capsys.readouterr()
    assert cli.main(["review", "list", "--changed-since", "2000-01-01T00:00:00", "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "n1" in out and "works" in out and "fine" in out and "activity-started-by" not in out
    assert cli.main(["review", "list", "--state", str(state)]) == 0 and "activity-started-by" in capsys.readouterr().out
    assert cli.main(["review", "add", "--title", "T", "--state", str(state)]) == 1, "an add without an id is refused"
    assert cli.main(["review", "check", "--state", str(state)]) == 1, "the old actions still need their area"


def test_get_review_serves_the_page_with_the_token_and_the_review_tab_and_api_review_the_json(live, state):
    page = urllib.request.urlopen(live + "/review", timeout=5).read().decode()  # nosec B310 -- live is the fixture's http://127.0.0.1 console server (#7100)
    assert console.TOKEN in page and "__TOKEN__" not in page and "__TAB__" not in page and 'location.hash.slice(1) || "review"' in page
    assert "max-width" in page and "Works" in page and "Polish" in page and "N/A" in page and "Bug" in page, "phone width, and the four verdict buttons"
    home = urllib.request.urlopen(live + "/", timeout=5).read().decode()  # nosec B310 -- live is the fixture's http://127.0.0.1 console server, read at its root page (#7100)
    assert 'location.hash.slice(1) || "lanes"' in home
    got = json.loads(urllib.request.urlopen(live + "/api/review", timeout=5).read())  # nosec B310 -- live is the fixture's http://127.0.0.1 console server, read at its review JSON (#7100)
    assert [i["id"] for i in got["items"]] == ["activity-started-by", "b", "c"] and got["items"][0]["how"] == ITEM["how"]


def test_post_review_needs_the_token_and_a_loopback_host_updates_one_item_and_writes_one_console_row(live, state):
    assert _post(live, {"id": "c", "status": "works"})[0] == 403
    assert _post(live, {"id": "c", "status": "works"}, token=console.TOKEN, host="evil.test")[0] == 403
    assert review_page.load()["items"][2]["status"] == "to-test"
    code, body = _post(live, {"id": "c", "status": "works", "note": "good"}, token=console.TOKEN)
    assert code == 200 and body["ok"] and body["item"]["status"] == "works" and body["item"]["updatedAt"]
    c = review_page.load()["items"][2]
    assert c["status"] == "works" and c["note"] == "good" and c["updatedAt"] == body["item"]["updatedAt"]
    (row,) = [r for r in journal.read() if r["event"] == "console" and r.get("verb") == "review c works"]
    assert row["ok"] is True and row["state"] == "ended"
    assert _post(live, {"id": "c", "status": "nope"}, token=console.TOKEN)[0] == 400
    assert _post(live, {"id": "zz", "status": "works"}, token=console.TOKEN)[0] == 404
    assert _post(live, {"status": "works"}, token=console.TOKEN)[0] == 400


def test_a_broken_verdict_or_a_note_reaches_the_issue_the_journal_and_the_manager(state):
    """2026-11-27: a note only sat in review.json. Marked broken: the note as a comment on its issue and the issue reopened; a note
    alone: the comment; each one `review-verdict` row and one alert carrying the note. Setting the same note again does nothing."""
    review_page.set_item("activity-started-by", "bug", "the started-by line is empty")
    url = ITEM["issue"]
    assert GH.calls == [("issue", "comment", url, "--body", "Owner, on the review list (activity-started-by, build 2026.11.24 (43)): marked broken. "
                         "the started-by line is empty"), ("issue", "reopen", url)]
    review_page.set_item("b", None, "the icon is a bit small")
    assert GH.calls[-1][:3] == ("issue", "comment", url) and len(GH.calls) == 3
    review_page.set_item("b", "polish", "the icon is a bit small")
    assert len(GH.calls) == 3, "the same note and no break: nothing new"
    rows = journal.read()
    verdicts = [r for r in rows if r.get("event") == "review-verdict"]
    alerts = [r for r in rows if r.get("event") == "alert"]
    assert [v["item"] for v in verdicts] == ["activity-started-by", "b"] and "reopened" in verdicts[0]["detail"]
    assert len(alerts) == 2 and "the started-by line is empty" in json.dumps(alerts[0])
