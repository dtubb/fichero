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
