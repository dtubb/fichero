"""dev-workflows.run.loop-alerts, owner 2026-11-04: alerts never hang around. An informational alert clears itself when its condition
clears (the loop ticks again), any alert can be dismissed, and the console lists the open ones and, collapsed, the last 7 days' resolved."""
from __future__ import annotations

import time

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import console, journal, queue


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    return tmp_path


def _answers():
    return [(r["id"], r["action"]) for r in journal.read() if r["event"] == "alert-answer"]


def test_a_heartbeat_alert_is_answered_when_the_loop_ticks_again(state):
    journal.append("loop", state="tick")
    aid = queue.heartbeat_check(30, 3, now=time.time() + 200)
    assert aid and queue.heartbeat_check(30, 3, now=time.time() + 300) is None, "one alert per silence"
    journal.append("loop", state="tick")
    assert queue.heartbeat_check(30, 3) is None
    assert _answers() == [(aid, "loop-back")]
    assert queue.heartbeat_check(30, 3) is None and _answers() == [(aid, "loop-back")], "answered once"


def test_any_alert_can_be_dismissed_and_nothing_else_changes(state, capsys):
    queue.add("ext", "/w/ext", "1.1", str(state / "b"), [7], kind="external")
    aid = queue.alert("ext", "1.1", "a question", "/e", ["approve", "send-back"])
    before = queue.load()
    assert cli.main(["alert", aid, "dismiss", "--state", str(journal.STATE)]) == 0
    assert _answers() == [(aid, "dismiss")] and queue.load() == before, "dismissed, the step untouched"
    assert cli.main(["alert", "no-such", "dismiss", "--state", str(journal.STATE)]) == 1, "an unknown id is still refused"


def test_the_console_lists_open_alerts_and_the_last_seven_days_resolved_newest_first(state):
    day = time.strftime("%Y-%m-%d")
    old = time.strftime("%Y-%m-%d", time.localtime(time.time() - 9 * 86400))
    rows = [{"ts": f"{old}T10:00:00", "event": "alert", "id": "x-1", "what": "old"},
            {"ts": f"{old}T10:01:00", "event": "alert-answer", "id": "x-1", "action": "retry", "ok": True},
            {"ts": f"{day}T09:00:00", "event": "alert", "id": "x-2", "what": "runner down"},
            {"ts": f"{day}T09:05:00", "event": "alert-answer", "id": "x-2", "action": "runner-back", "ok": True},
            {"ts": f"{day}T09:10:00", "event": "alert", "id": "x-3", "what": "a question", "actions": ["approve"]},
            {"ts": f"{day}T09:20:00", "event": "alert", "id": "x-4", "what": "noise"},
            {"ts": f"{day}T09:21:00", "event": "alert-answer", "id": "x-4", "action": "dismiss", "ok": True}]
    st = console.status(rows, [], today=day)
    assert [a["id"] for a in st["open_alerts"]] == ["x-3"]
    assert [(a["id"], a["answer"]) for a in st["resolved_alerts"]] == [("x-4", "dismiss"), ("x-2", "runner-back")], "7 days, newest first"


def test_dismiss_through_the_console_clears_every_open_alert_of_the_same_kind_and_no_other(state, monkeypatch):
    """Owner 2026-11-05: Dismiss "did nothing": 75 identical runner alerts were open, and each click only showed the next. End to end through
    the console's own /api/action and the real `builder alert` it runs: one Dismiss answers every open alert of that kind; another kind stays."""
    import json
    import threading
    import urllib.request
    monkeypatch.setattr(console, "ROOT", state)
    ids = [queue.alert("check", "remote", f"the check runner imac:~/fichero-gate is unreachable; trying air: ssh port {22 + n}", "imac", [])
           for n in range(3)]
    other = queue.alert("check", "remote", "the check runner air:~/fichero-gate is unreachable; the tests ran here", "air", [])
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        req = urllib.request.Request(url + "/api/action", data=json.dumps({"verb": "alert", "args": {"id": ids[1], "action": "dismiss"}}).encode(),
                                     method="POST", headers={"Content-Type": "application/json", "X-Builder-Token": console.TOKEN})
        assert json.loads(urllib.request.urlopen(req, timeout=60).read())["ok"]
        for _ in range(300):  # the verb runs in the console's thread: wait for it, as a person's refresh does
            st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=10).read())
            if len(st["open_alerts"]) <= 1:
                break
            time.sleep(0.1)
        assert [a["id"] for a in st["open_alerts"]] == [other], "every imac alert answered by one click; the Air's stays"
    finally:
        srv.shutdown()
    assert sorted(i for i, act in _answers() if act == "dismiss") == sorted(ids)
