"""End to end: quit with running, paused, waiting, automatic and new-material work → open → nothing picked → the alert lists it
all → Continue two → only those two run (#6584, `activity.launch.nothing-starts-one-alert`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. The lane is real (a fresh scheduler, background work on); the kinds
record what ran. The 10-pages-failed-after-6 → 4 calls half lives in `test_continue_makes_only_the_missing_calls_6584.py`.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from fichero_server import sync_folder
from fichero_server.execution import jobs

KIND, AUTO = "t-e2e-run", "t-e2e-thumb"


@pytest.fixture
def engine(db, monkeypatch):
    ran: list[str] = []
    lock = threading.Lock()

    def run(db, subject):
        with lock:
            ran.append(subject)

    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=run, model=None, name="Run the recipe"))
    monkeypatch.setitem(jobs.KINDS, AUTO, jobs.Kind(run=run, model=None, lane="images", name="Make thumbnails", first=True))
    monkeypatch.setattr(sync_folder, "_watch", lambda db, folder: None)
    jobs.set_paused(True)
    db.ran = ran
    yield db
    jobs.set_paused(False)


def _wait(predicate, seconds=20.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_the_open_starts_nothing_lists_everything_and_continue_runs_only_the_chosen(engine, client, tmp_path, monkeypatch):
    db = engine
    running = jobs.enqueue(db, KIND, "r:running")
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [running])
    paused = jobs.enqueue(db, KIND, "r:paused")
    db.execute("UPDATE jobs SET state = 'paused', reason = ? WHERE id = ?", [jobs.PAUSED_REASON, paused])
    waiting = jobs.enqueue(db, KIND, "r:waiting")
    automatic = [jobs.enqueue(db, AUTO, f"page-{i}") for i in range(3)]
    sync_folder._ensure(db)
    (tmp_path / "inbox").mkdir()
    db.execute("INSERT INTO sync_folders (id, path, formats, created_at, intake) VALUES ('f1', ?, ?, now(), TRUE)",
               [str(tmp_path / "inbox"), json.dumps([])])

    # The relaunch: a fresh engine opens the library (what db/manager does: resume, then the held rescan), work on.
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.resume(db)
    sync_folder.rescan(db, hold=True)
    jobs.set_paused(False)
    time.sleep(0.5)

    assert db.ran == [], "nothing picked"
    listed = client.get("/api/activity/stopped-at-quit").json()
    ids = {i["id"] for i in listed["items"]}
    assert {running, waiting, *automatic} <= ids, "what was running, queued and automatic"
    assert paused not in ids, "a pause the person asked for is theirs, not the quit's"
    assert any(i["kind"] == sync_folder.READ_KIND for i in listed["items"]), "the folder's new material"
    assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [paused]) == ("paused", jobs.PAUSED_REASON)

    r = client.post("/api/activity/stopped-at-quit/continue", json={"ids": [running, automatic[0]]})

    assert sorted(r.json()["continued_ids"]) == sorted([running, automatic[0]])
    assert _wait(lambda: sorted(db.ran) == ["page-0", "r:running"]), db.ran
    time.sleep(0.5)
    assert sorted(db.ran) == ["page-0", "r:running"], "only the two chosen ran"
    left = {i["id"] for i in client.get("/api/activity/stopped-at-quit").json()["items"]}
    assert waiting in left and automatic[1] in left and running not in left
