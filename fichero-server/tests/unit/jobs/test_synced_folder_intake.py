"""The synced folder, the read-back half: edits made in the folder come in (#4952).

Spec: docs/contributor_manual/specs/source/synced-folder.md, "In, as they arrive" and "Conflicts are
shown, not settled silently". Written from the spec's behaviours before the code, and driven
through the public surface: folders are tied with `POST /api/sync-folders` or adopted by an Index
import (`import.folder`), intake is switched on with `PUT /api/sync-folders/{id}/intake` after its
preview, the folder is followed with `GET /api/sync-folders`, and the engine is stopped and started
as the app does. Edits in Fichero go through the audited action layer. Passes are read from the
database: no route lists a page's passes yet.

Not covered here because not built yet: new images and new files arriving (intake reads back
only files Fichero wrote or adopted), live watching (the folder is read when the engine starts,
when intake is switched on, and when a write finds a file changed), and the Inspector.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from tests.unit.jobs.test_adopted_folder import LAYOUT, _correct, _import, _page_id, kept_folder  # noqa: F401
from tests.unit.jobs.test_synced_folder import _status, _tie, _wait_for, _written, page  # noqa: F401


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _passes(db, document_id):
    from fichero_server.models.segments import SegmentPass

    return [p for p in db.all(SegmentPass) if p.document_id == document_id]


def _restart(test_package, monkeypatch):
    """The engine stops and starts again, as the app does; the reopened library."""
    db_manager.close_database(test_package)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    return db_manager.get_database(test_package)


def _edit_outside(path: Path, old: str, new: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert old in text
    edited = text.replace(old, new)
    path.write_text(edited, encoding="utf-8")
    return edited


def test_source_sync_intake_is_opt_in__nothing_comes_in_until_switched_on_after_its_preview(
        client, db, page, test_package, tmp_path, monkeypatch):
    """Behaviour `source.sync.intake-is-opt-in`: "taking files in from the folder is switched on for
    each project and shows what it will bring in (counts by kind) before its first run." A made
    folder starts with intake off: an edit there brings nothing in; the preview counts it; switched
    on, it comes in."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["pagexml"])
    assert _written(client, folder_id, 1)
    assert _status(client, folder_id)["intake"] is False
    before = len(_passes(db, page.id))
    path = folder / "pagexml" / f"book-p1--{page.id}.page.xml"
    _edit_outside(path, "</PcGts>", "<!-- edited in Oxygen --></PcGts>")

    db = _restart(test_package, monkeypatch)
    time.sleep(0.5)
    assert len(_passes(db, page.id)) == before  # off: nothing came in
    preview = client.get(f"/api/sync-folders/{folder_id}/intake")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"on": False, "would_bring_in": {"pagexml": 1}}

    r = client.put(f"/api/sync-folders/{folder_id}/intake", json={"on": True})
    assert r.status_code == 200, r.text
    assert _wait_for(lambda: len(_passes(db, page.id)) == before + 1)
    assert _status(client, folder_id)["intake"] is True


def test_source_sync_outside_edits_are_passes__an_edit_in_the_folder_is_a_new_pass_and_overwrites_nothing(
        client, db, kept_folder, test_package, monkeypatch):
    """Behaviour `source.sync.outside-edits-are-passes`: "a changed or new read-back file comes in as
    a new pass with provenance ('edited outside Fichero', the file's time) and overwrites nothing."
    And `source.sync.rescan-after-downtime`: the edit was made while the engine was off, and is
    handled as though seen live. The working pass is still Fichero's, and the person's file is left
    as they left it."""
    page_id = _page_id(db, _import(db, kept_folder, "index"))  # adopting turns intake on
    working = client.get(f"/api/documents/{page_id}/export/pagexml").json()["content"]
    [adopted_pass] = _passes(db, page_id)
    db_manager.close_database(test_package)
    path = kept_folder / LAYOUT
    edited = _edit_outside(path, "A simple test for eScriptorium", "A simple test, corrected in Oxygen")
    db = _restart(test_package, monkeypatch)

    assert _wait_for(lambda: len(_passes(db, page_id)) == 2)
    [outside] = [p for p in _passes(db, page_id) if p.id != adopted_pass.id]
    assert outside.actor == "edited outside Fichero"
    file_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    assert file_time in outside.name and "M_Otterskirchen_012_0002.xml" in outside.name
    time.sleep(1.0)  # past the quiet period
    assert client.get(f"/api/documents/{page_id}/export/pagexml").json()["content"] == working
    assert path.read_text(encoding="utf-8") == edited


def test_source_sync_conflicts_kept_both__project_and_file_both_changed_are_two_passes_and_shown(client, db, kept_folder):
    """Behaviour `source.sync.conflicts-kept-both`: "when project and file both changed since Fichero
    last wrote it, both are kept as passes and the conflict is shown." A correction in Fichero and
    an edit in the folder meet while background work is paused: the folder's edit comes in as a
    pass beside the corrected one, the file is not overwritten, and the folder lists the conflict."""
    page_id = _page_id(db, _import(db, kept_folder, "index"))
    folder_id = client.get("/api/sync-folders").json()["folders"][0]["id"]
    client.put("/api/activity/jobs/paused", json={"paused": True})
    try:
        _correct(db, page_id, "Otterskirchen, im Jahr des Herrn")
        edited = _edit_outside(kept_folder / LAYOUT, "A simple test for eScriptorium",
                               "A simple test, corrected in Oxygen")
    finally:
        client.put("/api/activity/jobs/paused", json={"paused": False})
    assert _wait_for(lambda: _status(client, folder_id)["conflicts"] == [LAYOUT])
    assert len(_passes(db, page_id)) == 2
    assert "im Jahr des Herrn" in client.get(f"/api/documents/{page_id}/export/pagexml").json()["content"]
    time.sleep(1.0)
    assert (kept_folder / LAYOUT).read_text(encoding="utf-8") == edited


def test_source_sync_deleted_outside__a_deleted_file_deletes_nothing_and_is_written_again(client, db, kept_folder):
    """Behaviour `source.sync.deleted-outside`: "a file deleted in the folder deletes nothing in the
    project; it is listed, and written again on the next change to its source." In an adopted
    folder, the deleted file comes back, in its own place, on the next correction."""
    from fichero_server.models import Document

    page_id = _page_id(db, _import(db, kept_folder, "index"))
    folder_id = client.get("/api/sync-folders").json()["folders"][0]["id"]
    (kept_folder / LAYOUT).unlink()
    r = client.put(f"/api/sync-folders/{folder_id}/intake", json={"on": True})  # read the folder now
    assert r.status_code == 200, r.text
    assert _wait_for(lambda: _status(client, folder_id)["deleted_outside"] == [LAYOUT])
    assert db.get(Document, page_id) is not None and len(_passes(db, page_id)) == 1
    _correct(db, page_id, "Otterskirchen, im Jahr des Herrn")
    assert _wait_for(lambda: (kept_folder / LAYOUT).exists()
                     and "im Jahr des Herrn" in (kept_folder / LAYOUT).read_text(encoding="utf-8"))
    assert _status(client, folder_id)["deleted_outside"] == []
