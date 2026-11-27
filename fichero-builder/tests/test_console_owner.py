"""Section H of the console's spec (owner 2026-11-27, after using the Builder Console): one test per `builder-console.*` line there."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from fichero_builder import console, journal, work


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(console, "ROOT", tmp_path)
    monkeypatch.setattr(console, "_STATUS", {"at": 0.0, "data": None})
    return tmp_path


def _wait(pred):
    for _ in range(200):
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_a_ladder_wait_names_what_holds_each_busy_slot_and_the_console_fills_an_old_question_mark(state, monkeypatch):
    """builder-console.lock.holder-named: 'held by ?' in the ladder-lock waiting line."""
    monkeypatch.setattr(journal.Lock, "WARN_S", 0.05)
    with journal.Lock("ladder", what="the check of ie"):
        (state / "ladder.files").write_text(json.dumps({"name": "ie", "files": ["a.py"]}))
        t = threading.Thread(target=lambda: work.ladder_slot("seg", ["b.py"], 1, sleep=lambda s: time.sleep(0.02), by_file=False).__enter__(), daemon=True)
        t.start()
        assert _wait(lambda: any(r["event"] == "lock" and r["state"] == "waiting" for r in journal.read()))
        (w,) = [r for r in journal.read() if r["event"] == "lock"]
        assert w["holder"] == f"{os.getpid()} the check of ie", "the slot's lock file says who: never ?"
        journal.append("lock", state="waiting", name="ladder", holder="?", what="the check of old", pid=os.getpid(), detail="all 1 ladder slot(s) are busy")
        waits = console.api_status(journal.read(), [])["lock_waits"]
        assert [x["holder"] for x in waits] == [f"{os.getpid()} the check of ie"] * 2, "a row written before the fix reads the lock files now"
    t.join(5)


def _get(url, path):
    import urllib.request
    return json.loads(urllib.request.urlopen(url + path, timeout=5).read())


def _post(url, path, body, token=None):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Builder-Token": token} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=5)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture
def live(state, monkeypatch):
    """A console on an ephemeral loopback port over the state dir; verbs go to a fake runner."""
    monkeypatch.setattr(console.queue, "load", lambda: [])
    ran = []
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (0, "ok"))
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", ran
    srv.shutdown()


def _page() -> str:
    return console.PAGE.read_text()


def _at(now: float, hours_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - hours_ago * 3600))


def test_alerts_are_a_badge_count_and_a_page_grouped_by_kind_with_old_ones_folded_and_the_owners_marked(live):
    """builder-console.alerts.badge-and-page: 68 alerts up to 11 days old took over the top of every page."""
    url, _ran = live
    now = time.time()
    al = lambda h, i, lane, what, actions: journal.append("alert", id=i, lane=lane, step="s", what=what, actions=actions) | {"ts": _at(now, h)}  # noqa: E731
    rows = [al(200, "a-s-1", "a", "runner m4 unreachable; load 31", ["retry", "park"]),
            al(30, "a-s-2", "a", "runner m4 unreachable; load 12", ["retry", "park"]),
            al(3, "a-s-3", "a", "red at pytest 14 failed", ["retry", "park", "ask-owner"]),
            al(2, "b-s-4", "b", "red at pytest 2 failed", ["retry", "park", "ask-owner"]),
            al(1, "review-x-q-5", "review-x", "Owner question 1 of the x review: keep the old name?", ["ask-owner", "park"]),
            al(5, "c-s-6", "c", "a question", ["retry", "ask-owner"]),
            al(4, "c-s-7", "c", "answered", ["retry"]),
            {"ts": _at(now, 4), "event": "alert-answer", "id": "c-s-6", "action": "ask-owner", "ok": True},
            {"ts": _at(now, 3), "event": "alert-answer", "id": "c-s-7", "action": "retry", "ok": True}]
    (journal.STATE / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    v = console.alerts_view(journal.read(), now=now)
    assert (v["count"], v["owner_count"], v["older_count"]) == (3, 1, 2), "the badge counts the open alerts under a day old; the owner's apart"
    assert [(g["kind"], g["n"], g["owner"]) for g in v["groups"]] == [("Owner question N of the x review: keep the old name?", 1, True), ("red at pytest N failed", 2, False)]
    assert [x["id"] for x in v["groups"][1]["alerts"]] == ["b-s-4", "a-s-3"], "one kind across lanes, newest first"
    assert [(g["kind"], g["n"]) for g in v["older"]] == [("runner mN unreachable", 2)], "over a day old: folded, grouped the same way"
    assert [a["id"] for a in v["asked_owner"]] == ["c-s-6"], "what the manager handed to the owner"
    assert _get(url, "/api/alerts")["count"] == 3
    st = _get(url, "/api/status")
    assert st["alerts"] == {"count": 3, "owner_count": 1}
    page = _page()
    assert '["alerts", "Alerts"]' in page and "st.alerts.count" in page, "a tab and a badge"
    app = page[page.index("function App()"):]
    assert "<${Alerts}" not in app.replace("alerts: Alerts", "") and "Resolved" not in app, "no page opens with the alert cards"


def _lane(i, steps, **kw):
    return {"id": i, "worktree": "/nonexistent/" + i, "cursor": 0, "paused": False, "kind": "worker",
            "steps": [{"step": s, "state": st, "issues": [7], "why": "", "brief": "/nonexistent/brief", "entered_at": 0.0} for s, st in steps], **kw}


def test_a_lanes_last_action_sits_in_its_row_and_the_action_log_is_one_page(live, monkeypatch):
    """builder-console.actions.beside-what-they-act-on: the console actions sat at the bottom of every page."""
    url, ran = live
    monkeypatch.setattr(console.queue, "load", lambda: [_lane("a", [("s1", "queued")]), _lane("b", [("s2", "queued")])])
    monkeypatch.setattr(console, "run_verb", lambda argv: ran.append(argv) or (1, "first line\nREFUSED: no lane"))
    assert _post(url, "/api/action", {"verb": "pause", "args": {"lane": "a"}}, console.TOKEN)[0] == 200
    assert _wait(lambda: any(r.get("state") == "ended" for r in journal.read()))
    monkeypatch.setattr(console, "_STATUS", {"at": 0.0, "data": None})
    a, b = _get(url, "/api/status")["lanes"]
    assert {k: a["last_action"][k] for k in ("verb", "state", "ok", "rc", "detail")} == {"verb": "pause", "state": "ended", "ok": False, "rc": 1, "detail": "REFUSED: no lane"}
    assert a["last_action"]["ts"] and b["last_action"] is None, "the newest console row whose args name that lane"
    page = _page()
    app, lanes, log = page[page.index("function App()"):], page[page.index("function Lanes("):page.index("function DevBuilds(")], page[page.index("function Log("):page.index("function App()")]
    assert "l.last_action" in lanes, "the result beside the lane's buttons"
    assert "Console actions" in log and "Last events" in log and '["log", "Log"]' in app
    assert "Console actions" not in app and "Last events" not in app, "no other page ends with them"
    assert 'act("build")' in app and 'act("loop-stop")' in app, "the whole-harness actions stay in the toolbar"
