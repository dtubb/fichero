"""A rescan at open records nothing and starts no recipe run: the synced folder's read is held for the launch alert (#6584).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.launch.nothing-starts-one-alert` (new material at open is one
more line of the alert). WHY (owner 2026-11-13): a recipe appeared to restart at every open; a tied intake folder's rescan queued
a read "as though seen live", which imported and started a recipe run.
"""
from __future__ import annotations

import json

import pytest

from fichero_server import sync_folder
from fichero_server.execution import jobs


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setattr(sync_folder, "_watch", lambda db, folder: None)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _tie_intake_folder(db, tmp_path):
    sync_folder._ensure(db)
    folder = tmp_path / "inbox"
    folder.mkdir()
    db.execute("INSERT INTO sync_folders (id, path, formats, created_at, intake) VALUES (?, ?, ?, now(), TRUE)",
               ["f-inbox", str(folder), json.dumps([])])
    return "f-inbox"


def _read_rows(db):
    return db.execute_fetchall("SELECT id, state, reason FROM jobs WHERE kind = ?", [sync_folder.READ_KIND])


def test_the_opens_rescan_holds_the_folders_read_and_the_alert_lists_it(held, tmp_path, client):
    _tie_intake_folder(held, tmp_path)

    sync_folder.rescan(held, hold=True)  # what the library open does

    [(job_id, state, reason)] = _read_rows(held)
    assert (state, reason) == ("paused", jobs.NEW_MATERIAL_REASON)
    listed = client.get("/api/activity/stopped-at-quit").json()["items"]
    assert [i["id"] for i in listed] == [job_id] and listed[0]["kind"] == sync_folder.READ_KIND
    assert client.post("/api/activity/stopped-at-quit/continue", json={"ids": [job_id]}).json()["continued_ids"] == [job_id]
    assert _read_rows(held)[0][1] == "waiting", "Continue brings the files in"


def test_a_rescan_while_the_app_runs_still_reads_the_folder_at_once(held, tmp_path):
    _tie_intake_folder(held, tmp_path)

    sync_folder.rescan(held)  # not the open: a live rescan

    [(_, state, _reason)] = _read_rows(held)
    assert state == "waiting"
