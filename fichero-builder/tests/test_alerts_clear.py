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
