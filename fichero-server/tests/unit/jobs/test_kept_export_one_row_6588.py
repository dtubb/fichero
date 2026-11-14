"""A kept export is ONE row per export (#6588, decision 28, `activity.kept-export.one-row-per-export`).

Spec: `docs/contributor_manual/specs/ui/activity-pane.md`. The work changing asks the export's one job to rewrite the pages
it touched; while it waits, more changes join it. A folder that is gone PAUSES that row ("The export folder is gone") and
the edits meanwhile join it; Continue writes them once the folder is back. WHY: the owner saw 20 identical failed rows, one
per edited page, for one export whose folder was unplugged, and deleting them did not stop more coming.
Driven through the public surface (`POST /api/export/kept`) and the real scheduler; folders are pytest tmp folders.
"""
from __future__ import annotations

import shutil
import time

import pytest

from fichero_server import kept_export
from fichero_server.execution import jobs

from tests.unit.jobs.test_kept_exports import _keep, _wait_for, _written
from tests.unit.jobs.test_kept_exports import page as page  # noqa: F401 -- the fixture, by its name


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(kept_export, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _rows(db, export_id, states=("waiting", "running", "paused", "failed")):
    marks = ", ".join("?" for _ in states)
    return db.execute_fetchall(
        f"SELECT id, subject, state, reason FROM jobs WHERE kind = ? AND subject LIKE ? AND state IN ({marks}) "
        "AND cleared_at IS NULL ORDER BY created_at", [kept_export.KIND, export_id + "%", *states])


def test_ten_page_edits_queue_one_row_naming_ten_pages(client, db, page, tmp_path, monkeypatch):
    folder = tmp_path / "Letters"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    monkeypatch.setattr(kept_export, "QUIET_SECONDS", 600.0)  # the row waits while it is looked at
    others = [f"page-{n}" for n in range(9)]
    for edited in [page.id, *others]:
        kept_export.queue_rewrites(db, [edited])
    rows = _rows(db, export_id)
    assert len(rows) == 1 and rows[0][1] == export_id, rows
    assert jobs.tree(db, rows[0][0])["display_name"] == "Update kept export · Letters · 10 pages"


def test_a_gone_folder_pauses_the_one_row_and_more_edits_add_none(client, db, page, tmp_path):
    folder = tmp_path / "Unplugged"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    shutil.rmtree(folder)
    kept_export.queue_rewrites(db, [page.id])
    assert _wait_for(lambda: [r[2:] for r in _rows(db, export_id)] == [("paused", "The export folder is gone")])
    for _ in range(10):
        kept_export.queue_rewrites(db, [page.id])
    time.sleep(1.0)  # past the quiet period: nothing new runs, nothing new is queued
    rows = _rows(db, export_id)
    assert [r[2:] for r in rows] == [("paused", "The export folder is gone")], rows
    # the path is for Copy Details only, never the row
    assert str(folder) not in (rows[0][3] or "")

    folder.mkdir()  # the drive is back: Continue writes what waited
    (job_id,) = [r[0] for r in rows]
    jobs.pause_job(db, job_id, False)
    assert _wait_for(lambda: (folder / "book-p1.txt").exists())
    assert _wait_for(lambda: _rows(db, export_id) == [])


def test_write_now_joins_the_waiting_row_and_writes_at_once(client, db, page, tmp_path, monkeypatch):
    folder = tmp_path / "Now"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    (folder / "book-p1.txt").unlink()
    monkeypatch.setattr(kept_export, "QUIET_SECONDS", 600.0)
    kept_export.queue_rewrites(db, [page.id])
    r = client.post(f"/api/export/kept/{export_id}/write")
    assert r.status_code == 200, r.text
    assert _wait_for(lambda: (folder / "book-p1.txt").exists(), seconds=10)
    assert _rows(db, export_id) == []
