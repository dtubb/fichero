"""A kept export's folder can be chosen again, and its automatic rewrite switched off (#6588, decision 28,
`activity.kept-export.one-row-per-export`).

Spec: `docs/contributor_manual/specs/ui/activity-pane.md`. When the folder is gone the row is PAUSED with **Choose Folder…**
as its fix; choosing a folder (`PATCH /api/export/kept/{id}`) moves the export there and lets the paused row write. A
per-export **Keep up to date** switch (on by default) turns the automatic rewrite off; Write Now still writes. WHY: the
owner's export folder was unplugged and the only way back was to remove the export and set it up again.
Driven through the public surface and the real scheduler; folders are pytest tmp folders.
"""
from __future__ import annotations

import shutil

import pytest

from fichero_server import kept_export
from fichero_server.execution import jobs
from fichero_server.llm import failure

from tests.unit.jobs.test_kept_exports import _keep, _wait_for, _written
from tests.unit.jobs.test_kept_exports import page as page  # noqa: F401 -- the fixture, by its name
from tests.unit.jobs.test_kept_export_one_row_6588 import _rows


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(kept_export, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _listed(client, export_id):
    exports = client.get("/api/export/kept").json()["exports"]
    return next(e for e in exports if e["id"] == export_id)


def test_the_gone_folder_row_offers_choose_folder_then_continue():
    built = failure.classify(kept_export.ExportFolderGone("/Volumes/Gone/Letters is not there any more"))
    assert [a.kind for a in built.actions] == ["choose-folder", "resume"]


def test_choosing_a_folder_moves_the_export_and_the_paused_row_writes_there(client, db, page, tmp_path):
    gone = tmp_path / "Unplugged"
    gone.mkdir()
    export_id = _keep(client, gone, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    shutil.rmtree(gone)
    kept_export.queue_rewrites(db, [page.id])
    assert _wait_for(lambda: [r[2:] for r in _rows(db, export_id)] == [("paused", "The export folder is gone")])

    chosen = tmp_path / "Chosen"
    chosen.mkdir()
    answer = client.patch(f"/api/export/kept/{export_id}", json={"folder": str(chosen)})
    assert answer.status_code == 200, answer.text
    assert answer.json()["folder"] == str(chosen.resolve())
    assert _wait_for(lambda: (chosen / "book-p1.txt").exists()), "the paused row wrote into the chosen folder"
    assert _wait_for(lambda: _rows(db, export_id) == [])


def test_a_folder_that_cannot_be_kept_is_refused_in_words_and_nothing_changes(client, db, page, tmp_path):
    folder = tmp_path / "Kept"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    answer = client.patch(f"/api/export/kept/{export_id}", json={"folder": str(tmp_path / "Nowhere")})
    assert answer.status_code == 422 and answer.json()["detail"]
    assert _listed(client, export_id)["folder"] == str(folder.resolve())


def test_keep_up_to_date_off_queues_nothing_on_an_edit_and_write_now_still_writes(client, db, page, tmp_path):
    folder = tmp_path / "Quiet"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    assert _wait_for(lambda: _rows(db, export_id) == [])
    assert _listed(client, export_id)["keep_up_to_date"] is True, "on by default"

    answer = client.patch(f"/api/export/kept/{export_id}", json={"keep_up_to_date": False})
    assert answer.status_code == 200 and answer.json()["keep_up_to_date"] is False
    for _ in range(5):
        kept_export.queue_rewrites(db, [page.id])
    assert _rows(db, export_id) == [], "no automatic rewrite while it is off"

    (folder / "book-p1.txt").unlink()
    assert client.post(f"/api/export/kept/{export_id}/write").status_code == 200
    assert _wait_for(lambda: (folder / "book-p1.txt").exists()), "Write Now still writes"

    client.patch(f"/api/export/kept/{export_id}", json={"keep_up_to_date": True})
    kept_export.queue_rewrites(db, [page.id])
    assert jobs.count_jobs(db, kept_export.KIND, subject_prefix=export_id) >= 1, "on again, an edit queues its rewrite"


def test_the_listed_paused_row_carries_its_fix_naming_the_export(client, db, page, tmp_path):
    """The app's row offers Choose Folder… from the engine's own failure: the listed paused row carries it, the
    choose-folder action naming the export it is for (the row has no subject of its own)."""
    gone = tmp_path / "Unplugged"
    gone.mkdir()
    export_id = _keep(client, gone, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    shutil.rmtree(gone)
    kept_export.queue_rewrites(db, [page.id])
    assert _wait_for(lambda: [r[2:] for r in _rows(db, export_id)] == [("paused", "The export folder is gone")])
    (job_id,) = [r[0] for r in _rows(db, export_id)]

    listed = client.get("/api/activity/jobs").json()["jobs"]
    row = next(j for j in listed if j["id"] == job_id)
    assert row["failure"]["kind"] == "export-folder-gone"
    assert [(a["kind"], a.get("control")) for a in row["failure"]["actions"]] == [("choose-folder", export_id), ("resume", None)]
    assert str(gone) not in row["failure"]["words"], "no path in the row's words"
