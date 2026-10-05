"""Keep arranged: a synced folder whose files follow the project's folders, and a hand (#5480).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md, section 7b (the ruling of
2026-10-05: "Keep arranged arranges the folder by the project's own structure (its folders) ... A
file a person moves by hand inside the folder stays where they put it, and Fichero's records follow
the move"), `source.onboard.keep-arranged` and `source.onboard.keep-arranged-undoable`; and
`source/synced-folder.md`. Keep arranged is a MODE of the one synced folder (#4952), not a second
sync system.

Driven through the public surface: the folder comes in through the audited `import.folder` action
with `mode: index` (the one import path), is previewed with `GET /api/sync-folders/{id}/arrangement`
(the dry run, before anything moves), switched with `PUT /api/sync-folders/{id}/mode`, and the
project is changed through the document routes the app uses; undo is `POST
/api/actions/audit/{id}/undo`. Arrangements and hand moves are found by jobs on the real scheduler
and the real folder watcher. Every folder is a pytest temp folder: no real library is touched.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from _scan_files import scan_rglob

import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry


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


def _files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in scan_rglob(folder) if p.is_file())


def _doc(db, name):
    from fichero_server.models import Document

    [doc] = [d for d in db.all(Document) if d.name == name and d.deleted_at is None]
    return doc


@pytest.fixture
def archive(client, db, tmp_path):
    """A folder someone keeps, imported with Index: two scans at the top, one in `box1/`. Returns
    (folder, folder id); the folder is kept as Index until a test says yes to keeping it arranged."""
    folder = tmp_path / "archive"
    _image(folder / "a.jpg", "red")
    _image(folder / "b.jpg", "green")
    _image(folder / "box1" / "c.jpg", "blue")
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    registry.invoke(db, "import.folder", {"path": str(folder), "mode": "index"}, ctx)
    [tied] = client.get("/api/sync-folders").json()["folders"]
    assert tied["mode"] == "index"
    return folder.resolve(), tied["id"]


def _keep_arranged(client, folder_id):
    r = client.put(f"/api/sync-folders/{folder_id}/mode", json={"mode": "keep-arranged"})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "keep-arranged"


def _new_folder(client, name, parent_id):
    r = client.post("/api/documents", json={"name": name, "parent_id": parent_id, "doc_type": "folder"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _move(client, doc_id, parent_id):
    r = client.put(f"/api/documents/{doc_id}/move", params={"parent_id": parent_id})
    assert r.status_code == 200, r.text


def test_keep_arranged__moving_a_document_in_the_project_moves_its_file(client, db, archive):
    """Behaviour `source.onboard.keep-arranged`: the folder mirrors the project's folders, and
    "before the first arrangement it shows how many files would move and a sample of the new paths,
    and nothing moves until the person says yes." WHY: the person arranges the project, Fichero
    keeps the disk matching; the dry run must move nothing, the yes must move exactly that."""
    folder, folder_id = archive
    letters = _new_folder(client, "Letters", _doc(db, "archive").id)
    _move(client, _doc(db, "a.jpg").id, letters)
    before = _files(folder)
    preview = client.get(f"/api/sync-folders/{folder_id}/arrangement").json()
    assert preview["refused"] is None and preview["mode"] == "index"
    assert [(m["from_path"], m["to_path"]) for m in preview["moves"]] == [("a.jpg", "Letters/a.jpg")]
    assert _files(folder) == before  # the dry run moved nothing

    _keep_arranged(client, folder_id)
    assert _wait_for(lambda: _files(folder) == ["Letters/a.jpg", "b.jpg", "box1/c.jpg"])
    assert Path(_doc(db, "a.jpg").path) == folder / "Letters" / "a.jpg"


def test_keep_arranged__renaming_a_folder_in_the_project_renames_it_on_disk(client, db, archive):
    """Behaviour `source.onboard.keep-arranged`: a folder renamed in the project is renamed in the
    folder. WHY: the folder reads like the sidebar; the old, emptied folder must not linger (an
    empty folder is removed; one holding anything never is)."""
    folder, folder_id = archive
    _keep_arranged(client, folder_id)
    r = client.put(f"/api/documents/{_doc(db, 'box1').id}", json={"name": "Box One"})
    assert r.status_code == 200, r.text
    assert _wait_for(lambda: _files(folder) == ["Box One/c.jpg", "a.jpg", "b.jpg"]
                     and not (folder / "box1").exists())
    assert Path(_doc(db, "c.jpg").path) == folder / "Box One" / "c.jpg"


def test_keep_arranged__a_file_moved_by_hand_stays_and_the_project_follows(client, db, archive):
    """Ruling 2026-10-05: "A file a person moves by hand inside the folder stays where they put it,
    and Fichero's records follow the move." WHY: Fichero never fights the person; the record, the
    project folder and the hand mark follow, and nothing moves the file back."""
    folder, folder_id = archive
    _keep_arranged(client, folder_id)
    (folder / "b.jpg").rename(folder / "box1" / "b.jpg")  # by hand, as Finder would
    assert _wait_for(lambda: Path(_doc(db, "b.jpg").path) == folder / "box1" / "b.jpg"
                     and _doc(db, "b.jpg").parent_id == _doc(db, "box1").id)
    doc = _doc(db, "b.jpg")
    assert doc.metadata.get("placed_by_hand")
    time.sleep(1.5)  # past the quiet period: an arrangement, had one been queued, has run
    assert _files(folder) == ["a.jpg", "box1/b.jpg", "box1/c.jpg"]


def test_keep_arranged__a_clash_takes_a_numeric_suffix_never_an_overwrite(client, db, archive):
    """Spec open question 11 (taken): "files are renamed only to resolve a clash (`name 2.jpg`)".
    WHY: a file already where another belongs is the person's: it is never overwritten. (An
    adopted folder has intake on, so the other file may itself come in as a document.)"""
    from fichero_server.models import Document

    folder, folder_id = archive
    moved = _doc(db, "a.jpg").id
    stranger = _image(folder / "box1" / "a.jpg", "black")
    kept = stranger.read_bytes()
    _keep_arranged(client, folder_id)
    _move(client, moved, _doc(db, "box1").id)
    assert _wait_for(lambda: (folder / "box1" / "a 2.jpg").exists())
    assert stranger.read_bytes() == kept
    assert Path(db.get(Document, moved).path) == folder / "box1" / "a 2.jpg"
    assert not (folder / "a.jpg").exists()


def test_keep_arranged_undoable__undo_moves_the_file_back(client, db, archive):
    """Behaviour `source.onboard.keep-arranged-undoable`: "each arrangement is one audited, undoable
    action listing every move (old path, new path); undo puts every file back." WHY: a move made
    for the person must be as reversible as one they made."""
    folder, folder_id = archive
    _keep_arranged(client, folder_id)
    letters = _new_folder(client, "Letters", _doc(db, "archive").id)
    _move(client, _doc(db, "a.jpg").id, letters)
    assert _wait_for(lambda: (folder / "Letters" / "a.jpg").exists())
    [audit] = [a for a in client.get("/api/actions/audit").json()["items"] if a["action_name"] == "sync.arrange"]
    assert audit["undoable"] is True
    r = client.post(f"/api/actions/audit/{audit['id']}/undo")
    assert r.status_code == 200, r.text
    assert _files(folder) == ["a.jpg", "b.jpg", "box1/c.jpg"]
    assert Path(_doc(db, "a.jpg").path) == folder / "a.jpg"


def test_keep_arranged__a_folder_that_cannot_be_written_is_refused_in_words(client, db, archive):
    """`source.onboard.keep-arranged`, the refusal: a folder Fichero cannot write to is refused with
    a sentence, and nothing moves. WHY: half an arrangement would leave the folder and the project
    out of step."""
    folder, folder_id = archive
    _move(client, _doc(db, "a.jpg").id, _doc(db, "box1").id)
    os.chmod(folder, 0o555)
    try:
        preview = client.get(f"/api/sync-folders/{folder_id}/arrangement").json()
        assert "cannot write" in preview["refused"]
        r = client.put(f"/api/sync-folders/{folder_id}/mode", json={"mode": "keep-arranged"})
        assert r.status_code == 422 and "cannot write" in r.json()["detail"]
    finally:
        os.chmod(folder, 0o755)
    assert _files(folder) == ["a.jpg", "b.jpg", "box1/c.jpg"]
    assert client.get("/api/sync-folders").json()["folders"][0]["mode"] == "index"


def test_keep_arranged__index_mode_is_unchanged(client, db, archive):
    """`source.sync.four-ways-in`: Index leaves the originals where they are. WHY: keep arranged is
    a mode a person says yes to; a folder kept as Index must never have a file moved."""
    folder, _folder_id = archive
    _move(client, _doc(db, "a.jpg").id, _doc(db, "box1").id)
    time.sleep(1.5)  # past the quiet period
    assert _files(folder) == ["a.jpg", "b.jpg", "box1/c.jpg"]
    assert Path(_doc(db, "a.jpg").path) == folder / "a.jpg"
