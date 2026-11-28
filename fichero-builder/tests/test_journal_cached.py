"""2026-11-28: the console parsed the 102 MB journal on every request (/api/activity 11.7 s, /api/landing 21 s)."""
from __future__ import annotations

import json
import threading
import time

from fichero_builder import console, journal


def test_a_big_journal_is_parsed_once_and_then_only_its_new_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    line = json.dumps({"ts": "2026-11-28T09:00:00", "event": "check", "detail": "x" * 400}) + "\n"
    journal.path().write_text(line * 200_000)  # ~90 MB
    assert len(journal.read_cached()) == 200_000
    journal.append("queue", lane="l", step="1", state="landed")
    t = time.time()
    rows = journal.read_cached()
    assert time.time() - t < 1.0, "a warm read parses only the appended line"
    assert len(rows) == 200_001 and rows[-1]["state"] == "landed"
    with journal.path().open("a") as f:
        f.write('{"ts": "2026-11-28T09:01:00", "event": "half')  # a line still being written
    assert len(journal.read_cached()) == 200_001
    with journal.path().open("a") as f:
        f.write('"}\n')
    assert journal.read_cached()[-1]["event"] == "half"


def test_a_journal_replaced_or_rewritten_is_read_again_from_the_start(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    journal.append("check", state="a")
    journal.append("check", state="b")
    assert [r["state"] for r in journal.read_cached()] == ["a", "b"]
    journal.path().write_text(json.dumps({"ts": "t", "event": "check", "state": "c"}) + "\n")  # rewritten in place, shorter
    assert [r["state"] for r in journal.read_cached()] == ["c"]
    journal.path().write_text("".join(json.dumps({"ts": "t", "event": "check", "state": s, "pad": "p" * 300}) + "\n" for s in "defg"))
    assert [r["state"] for r in journal.read_cached()] == list("defg"), "rewritten, longer: its first bytes changed"
    journal.path().unlink()
    assert journal.read_cached() == []


def test_the_landing_view_answers_at_once_and_is_worked_out_in_the_background(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(journal, "STATE", tmp_path)
    monkeypatch.setattr(console, "ROOT", tmp_path)
    monkeypatch.setattr(console, "_LANDING", {})
    monkeypatch.setattr(console.queue, "load", lambda: [])
    gate = threading.Event()
    monkeypatch.setattr(console, "landing", lambda root, lanes: gate.wait(5) and {"ts": "now", "branches": [{"name": "b"}]})
    srv = console.server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        t = time.time()
        first = json.loads(urllib.request.urlopen(url + "/api/landing", timeout=5).read())
        assert time.time() - t < 1.0 and first["computing"] is True, "the slow read never holds the request"
        assert json.loads(urllib.request.urlopen(url + "/api/activity", timeout=5).read()) is not None, "nor another endpoint"
        gate.set()
        for _ in range(100):
            if console._LANDING.get("data"):
                break
            time.sleep(0.02)
        assert json.loads(urllib.request.urlopen(url + "/api/landing", timeout=5).read())["branches"] == [{"name": "b"}]
    finally:
        gate.set()
        srv.shutdown()
