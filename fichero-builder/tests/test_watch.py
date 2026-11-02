"""dev-workflows.tool.watch: `builder watch` serves one page from the journal: runs, checks, lands, newest first."""
from __future__ import annotations

import json
import threading
import urllib.request

from fichero_builder import __main__ as cli
from fichero_builder import journal, watch

ROWS = [
    {"ts": "2026-11-01T10:00:00", "event": "worker", "task": "lane-a", "model": "sonnet", "worktree": "/w/a", "generation": 1},
    {"ts": "2026-11-01T10:20:00", "event": "cost", "task": "lane-a", "usd": 1.25, "turns": 40, "end": "done"},
    {"ts": "2026-11-01T10:30:00", "event": "check", "repo": "/e", "since": "a" * 40, "head": "b" * 40, "ok": False, "failed": "pytest"},
    {"ts": "2026-11-01T10:40:00", "event": "landed", "sha": "c" * 40, "step": "verdict", "ok": True, "detail": "READY"},
    {"ts": "2026-11-01T10:41:00", "event": "landed", "sha": "c" * 40, "step": "done", "ok": True, "detail": "landed", "branch": "integration", "pushed": False},
    {"ts": "2026-11-01T10:50:00", "event": "worker", "task": "lane-b", "model": "sonnet", "worktree": "/w/b", "generation": 1},
]


def test_the_page_shows_every_run_check_and_land_newest_first_with_status_and_cost():
    html = watch.render(ROWS)
    assert "lane-a" in html and "lane-b" in html and "aaaaaaaaa..bbbbbbbbb" in html and "ccccccccc" in html
    assert html.index("lane-b") < html.index("lane-a"), "newest first"
    assert "1.25" in html and "40" in html and ">done<" in html and ">running<" in html, "cost, turns, the end word, no end = running"
    assert ">red<" in html and "pytest" in html, "a red check names the failed rung"
    assert ">done<" in html and "integration" in html
    assert "<script" not in html and 'http-equiv="refresh"' in html, "no JS: a meta refresh"


def test_watch_serves_the_journal_page_on_the_loopback_only(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path)
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS[:3]))
    srv = watch.server("127.0.0.1", 0)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    body = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/", timeout=5).read().decode()
    assert "lane-a" in body and "aaaaaaaaa..bbbbbbbbb" in body
    assert srv.server_address[0] == "127.0.0.1"


def test_the_watch_verb_is_wired_and_serves_on_the_loopback(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(watch, "server", lambda host, port: (seen.update(host=host, port=port), _Stub())[1])
    assert cli.main(["watch", "--port", "9999", "--state", str(tmp_path)]) == 0
    assert seen == {"host": "127.0.0.1", "port": 9999} and journal.STATE == tmp_path


class _Stub:
    server_address = ("127.0.0.1", 9999)

    def serve_forever(self):
        raise KeyboardInterrupt


def test_the_page_reads_the_owners_journal_and_the_workers_shared_one(tmp_path, monkeypatch):
    """`builder run` writes runs under the shared state; check and landed rows stay in the owner's, so a worker cannot forge them.
    One file alone shows half the page."""
    owner, wr = tmp_path / "owner", tmp_path / "wr"
    owner.mkdir(), (wr / "state").mkdir(parents=True)
    (tmp_path / "harness.toml").write_text(f'[jail]\nuser = "w"\nworkroot = "{wr}"\n')
    (owner / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS[2:5]))
    (wr / "state" / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS[:2]))
    monkeypatch.setattr(journal, "STATE", owner)
    html = watch.render(watch.rows_of(tmp_path))
    assert "lane-a" in html and "aaaaaaaaa..bbbbbbbbb" in html and "ccccccccc" in html, "runs from one file, checks and lands from the other"
    monkeypatch.setattr(journal, "STATE", wr / "state")
    assert len(watch.rows_of(tmp_path)) == 2, "the same file is not read twice"
    assert len(watch.rows_of(tmp_path / "no-rules-here")) == 2, "no rules file: the one journal"


def test_a_run_that_handed_off_shows_running_once_its_next_generation_starts():
    rows = [{"ts": "1", "event": "worker", "task": "a", "generation": 1}, {"ts": "2", "event": "cost", "task": "a", "usd": 1, "turns": 2, "end": "handoff"}]
    assert ">handoff<" in watch.render(rows)
    assert ">handoff<" not in watch.render([*rows, {"ts": "3", "event": "worker", "task": "a", "generation": 2}]) and ">running<" in watch.render([*rows, {"ts": "3", "event": "worker", "task": "a", "generation": 2}])
