"""The synced folder across a restart: nothing already in the project comes in again (#5495).

Spec: docs/contributor_manual/specs/source/synced-folder.md, `source.sync.rescan-after-downtime`,
`source.sync.new-images-come-in` and `source.sync.duplicates-repair`. Driven through the real
paths: the folder comes in through the audited `import.folder` action with `mode: index` (the one
import path the route, CLI and MCP share); the engine stops and starts as the lifespan does it
(`db_manager.close_database`, a fresh job scheduler, `db_manager.get_database`, which reads the
folder on open); the folder is followed with `GET /api/sync-folders`, the repair through
`GET /api/sync-folders/duplicates` (the dry run) and `POST /api/sync-folders/duplicates/remove`,
undone with `POST /api/actions/audit/{id}/undo`.

WHY: Index is for people's real archives. Before #5495 every restart took each indexed file in
again as a NEW document at the project's root, and auto-run spent compute on the copies.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _image(path: Path, colour: str) -> Path:
    """An image of its own colour: each file has its own checksum, as real scans do."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), colour).save(path)
    return path


def _wait_for(predicate, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _ctx(db):
    return ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)


def _live(db):
    from fichero_server.models import Document

    return [d for d in db.all(Document) if d.deleted_at is None and d.doc_type != "folder"]


def _named(db, name):
    return [d for d in _live(db) if d.name == name]


def _parent_name(db, doc):
    from fichero_server.models import Document

    return db.get(Document, doc.parent_id).name if doc.parent_id else None


def _reads_done(client):
    return _wait_for(lambda: not any(j["task_type"] == "read-from-folder"
                                     for j in client.get("/api/activity/jobs").json()["jobs"]))


@pytest.fixture
def notebook(client, db, tmp_path):
    """A notebook someone keeps, imported with Index (as the overnight repro did): two scans at the
    top, two in `letters/`. Returns (folder, folder id)."""
    folder = tmp_path / "Notebook 1"
    _image(folder / "a.jpg", "red")
    _image(folder / "b.jpg", "green")
    _image(folder / "letters" / "c.jpg", "blue")
    _image(folder / "letters" / "d.jpg", "yellow")
    registry.invoke(db, "import.folder", {"path": str(folder), "mode": "index"}, _ctx(db))
    [tied] = client.get("/api/sync-folders").json()["folders"]
    assert tied["intake"] is True  # adopting turns intake on: the restart reads the folder
    return folder.resolve(), tied["id"]


def _restart(client, test_package, monkeypatch, while_off=None):
    """The engine stops, (something happens to the folder,) and starts again: the library opens and
    its synced folders are read, as on any start."""
    db_manager.close_database(test_package)
    if while_off is not None:
        while_off()
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db = db_manager.get_database(test_package)
    assert _reads_done(client)
    return db


def test_rescan_after_downtime__a_restart_takes_in_nothing_already_in_the_project(
        client, db, notebook, test_package, monkeypatch):
    """Behaviour `source.sync.rescan-after-downtime` (#5495): an Index folder's own files are the
    project's already; a restart (and a second one) brings none of them in again, and each stays in
    its folder."""
    folder, folder_id = notebook
    before = sorted((d.id, d.parent_id) for d in _live(db))
    assert len(before) == 4
    for _ in range(2):
        db = _restart(client, test_package, monkeypatch)
        assert sorted((d.id, d.parent_id) for d in _live(db)) == before
    status = next(f for f in client.get("/api/sync-folders").json()["folders"] if f["id"] == folder_id)
    assert status["taken_in"] == []
    assert client.get(f"/api/sync-folders/{folder_id}/intake").json()["would_bring_in"] == {}
    assert _parent_name(db, _named(db, "c.jpg")[0]) == "letters"


def test_rescan_after_downtime__a_document_in_the_trash_does_not_come_back(
        client, db, notebook, test_package, monkeypatch):
    """A file whose document the person put in the trash is the project's still: the restart does
    not bring it back as a new document."""
    [doc] = _named(db, "a.jpg")
    registry.invoke(db, "document.delete", {"doc_id": doc.id}, _ctx(db))
    db = _restart(client, test_package, monkeypatch)
    assert _named(db, "a.jpg") == []


def test_new_images_come_in__a_file_added_while_off_comes_in_once_in_its_folder(
        client, db, notebook, test_package, monkeypatch):
    """Behaviour `source.sync.new-images-come-in` (#5495): a file that arrived while the engine was off
    is taken in once, in the project folder of the folder it was put in (not at the project's
    root); a new subfolder is made as a folder import would make it."""
    folder, folder_id = notebook

    def arrive():
        _image(folder / "letters" / "e.jpg", "purple")
        _image(folder / "f.jpg", "orange")
        _image(folder / "later" / "g.jpg", "pink")

    db = _restart(client, test_package, monkeypatch, arrive)
    db = _restart(client, test_package, monkeypatch)
    assert len(_live(db)) == 7
    assert _parent_name(db, _named(db, "e.jpg")[0]) == "letters"
    assert _parent_name(db, _named(db, "f.jpg")[0]) == "Notebook 1"
    [g] = _named(db, "g.jpg")
    assert _parent_name(db, g) == "later"
    from fichero_server.models import Document

    assert db.get(Document, db.get(Document, g.parent_id).parent_id).name == "Notebook 1"
    status = next(f for f in client.get("/api/sync-folders").json()["folders"] if f["id"] == folder_id)
    assert sorted(status["taken_in"]) == ["f.jpg", "later/g.jpg", "letters/e.jpg"]


def _seed_duplicate(db, folder, name):
    """What #5495 did: the same file taken in again, as a new document at the project's root."""
    result = registry.invoke(db, "import.file", {"path": str(folder / name), "mode": "link"}, _ctx(db)).result
    return result["id"]


def test_duplicates_repair__the_dry_run_reports_a_seeded_duplicate_and_changes_nothing(client, db, notebook):
    """Behaviour `source.sync.duplicates-repair` (#5495): documents of the same file in a synced
    folder are found and listed (the one kept: the first, in its folder; the ones that would go to
    the trash), and looking changes nothing."""
    folder, _folder_id = notebook
    [original] = _named(db, "c.jpg")
    copy = _seed_duplicate(db, folder, "letters/c.jpg")
    r = client.get("/api/sync-folders/duplicates")
    assert r.status_code == 200, r.text
    [group] = r.json()["groups"]
    assert group["path"] == str(folder / "letters" / "c.jpg")
    assert group["keep"]["id"] == original.id
    assert [d["id"] for d in group["remove"]] == [copy]
    assert len(_named(db, "c.jpg")) == 2  # a dry run: nothing changed


def test_duplicates_repair__removing_sends_them_to_the_trash_and_undo_brings_them_back(client, db, notebook):
    """Behaviour `source.sync.duplicates-repair` (#5495): the repair is one audited, undoable action
    that moves only the listed copies to the trash (never the kept document, never deleting
    anything for good); undo restores them."""
    folder, _folder_id = notebook
    [original] = _named(db, "c.jpg")
    copy = _seed_duplicate(db, folder, "letters/c.jpg")
    refused = client.post("/api/sync-folders/duplicates/remove", json={"document_ids": [original.id]})
    assert refused.status_code == 409, refused.text  # the kept one is never removed
    r = client.post("/api/sync-folders/duplicates/remove", json={"document_ids": [copy]})
    assert r.status_code == 200, r.text
    assert r.json()["removed"] == [copy]
    assert [d.id for d in _named(db, "c.jpg")] == [original.id]
    assert client.get("/api/sync-folders/duplicates").json()["groups"] == []
    [audit] = [a for a in client.get("/api/actions/audit").json()["items"]
               if a["action_name"] == "sync.remove_duplicates"]
    assert audit["undoable"] is True
    assert client.post(f"/api/actions/audit/{audit['id']}/undo").status_code == 200
    assert sorted(d.id for d in _named(db, "c.jpg")) == sorted([original.id, copy])
