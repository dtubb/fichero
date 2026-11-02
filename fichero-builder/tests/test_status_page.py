"""dev-workflows.run.loop-status: `builder status` (= `builder watch`) shows lanes, the last check and landing, issues closed
today, spend today and open alerts, from the journal and the queue only; the same as JSON at /status.json."""
from __future__ import annotations

import json
import threading
import urllib.request

from fichero_builder import __main__ as cli
from fichero_builder import journal, watch

DAY = "2026-11-02"
ROWS = [
    {"ts": "2026-11-01T23:00:00", "event": "cost", "task": "a", "usd": 9.0},
    {"ts": "2026-11-01T23:10:00", "event": "landed", "sha": "e" * 40, "step": "done", "ok": True, "branch": "integration", "pushed": True, "issues": [1], "left_open": []},
    {"ts": f"{DAY}T09:00:00", "event": "cost", "task": "a", "usd": 1.25},
    {"ts": f"{DAY}T09:30:00", "event": "cost", "task": "b", "usd": 0.5},
    {"ts": f"{DAY}T10:00:00", "event": "check", "since": "a" * 40, "head": "b" * 40, "ok": True, "failed": None},
    {"ts": f"{DAY}T10:30:00", "event": "landed", "sha": "c" * 40, "step": "done", "ok": True, "branch": "integration", "pushed": True, "issues": [7, 8], "left_open": [8]},
    {"ts": f"{DAY}T11:00:00", "event": "alert", "id": "a-s1-1", "lane": "a", "step": "s1", "what": "red at pytest", "actions": ["retry", "park"]},
    {"ts": f"{DAY}T11:05:00", "event": "alert", "id": "b-s2-2", "lane": "b", "step": "s2", "what": "a question", "actions": ["ask-owner"]},
    {"ts": f"{DAY}T11:10:00", "event": "alert-answer", "id": "a-s1-1", "action": "retry", "ok": True},
    {"ts": f"{DAY}T11:11:00", "event": "alert-answer", "id": "b-s2-2", "action": "retry", "ok": False},
]
LANES = [
    {"id": "a", "cursor": 1, "paused": False, "kind": "worker", "steps": [{"step": "s0", "state": "landed"}, {"step": "s1", "state": "running"}]},
    {"id": "b", "cursor": 1, "paused": True, "kind": "external", "steps": [{"step": "s2", "state": "landed"}]},
]


def test_a_journal_of_fixed_rows_gives_that_status_and_that_page():
    st = watch.status(ROWS, LANES, today=DAY)
    assert st["lanes"] == [{"lane": "a", "kind": "worker", "paused": False, "done": False, "step": "s1", "state": "running"},
                           {"lane": "b", "kind": "external", "paused": True, "done": True, "step": "-", "state": "done"}]
    assert st["last_check"]["head"] == "b" * 40 and st["last_check"]["ok"] is True
    assert st["last_land"] == {"ts": f"{DAY}T10:30:00", "sha": "c" * 40, "branch": "integration", "pushed": True}
    assert st["issues_closed_today"] == [7], "yesterday's #1 and the left-open #8 are not closed today"
    assert st["spend_today_usd"] == 1.75, "yesterday's cost is not today's"
    assert [a["id"] for a in st["open_alerts"]] == ["b-s2-2"], "an alert stays open until an answer that took"
    page = watch.render(ROWS, LANES)
    assert "Open alerts" in page and "b-s2-2" in page and "a question" in page and "(paused)" in page


def test_status_json_is_served_on_the_loopback(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    monkeypatch.setattr(watch, "_lanes", lambda: LANES)
    srv = watch.server("127.0.0.1", 0)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    resp = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/status.json", timeout=5)
    assert resp.headers["Content-Type"] == "application/json"
    st = json.loads(resp.read())
    assert [x["lane"] for x in st["lanes"]] == ["a", "b"] and [a["id"] for a in st["open_alerts"]] == ["b-s2-2"]


def test_the_status_verb_is_the_watch_page(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(watch, "server", lambda host, port: (seen.update(host=host, port=port), _Stub())[1])
    assert cli.main(["status", "--port", "9998", "--state", str(tmp_path)]) == 0
    assert seen == {"host": "127.0.0.1", "port": 9998}


class _Stub:
    server_address = ("127.0.0.1", 9998)

    def serve_forever(self):
        pass
