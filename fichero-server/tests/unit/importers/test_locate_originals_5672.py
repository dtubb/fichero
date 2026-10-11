"""Locate Originals: reconnect pages to files that moved (#5672).

WHY: the maintainer moved EAP 1740's originals off iCloud into another folder, and the project still pointed at the
old paths, so every step failed page by page. The project must say once that its originals are missing, match each
page to its file in the folder picked by the path below the old root (never by a bare name when two files share it),
show the plan first, then repoint the pages and their folder in one audited, undoable action.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from fichero_server.models import ActionAudit, DocType, Document, FileType


def _file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _linked(db, path: Path, *, parent=None, checksum=False) -> Document:
    meta = {"ingest_mode": "link", "source_path": str(path), "source_folder": str(path.parent),
            "file_size": path.stat().st_size}
    if checksum:
        meta["checksum"] = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   parent_id=parent.id if parent else None, metadata=meta)
    db.save(doc)
    return doc


@pytest.fixture
def moved(db, tmp_path):
    """EAP 1740 imported by link from iCloud, then moved by hand to another folder and its root renamed."""
    old = tmp_path / "iCloud" / "EAP 1740"
    folder = Document(name="EAP 1740", doc_type=DocType.folder, path=str(old))
    db.save(folder)
    pages = {
        "box1": _linked(db, _file(old / "Box 1" / "f001.jpg", b"one" * 100), parent=folder),
        "box2": _linked(db, _file(old / "Box 2" / "f001.jpg", b"two" * 120), parent=folder),  # same name, other box
        "f002": _linked(db, _file(old / "Box 1" / "f002.jpg", b"three" * 50), parent=folder),
    }
    new = tmp_path / "Fichero Test Corpus" / "Colombia"
    new.parent.mkdir(parents=True)
    shutil.move(str(old), str(new / "EAP_1740"))  # moved and its root renamed
    return folder, pages, new


def test_a_project_with_missing_originals_says_so_once(client, moved):
    said = client.get("/api/documents/missing-originals").json()
    assert said["pages"] == 3 and "Locate Originals" in said["sentence"]
    assert any(f.endswith("EAP 1740/Box 1") for f in said["folders"])


def test_the_plan_matches_by_the_path_below_the_old_root_and_moves_the_folder(client, db, moved):
    folder, pages, new = moved
    plan = client.post("/api/documents/relink-originals/plan", json={"new_root": str(new)})
    assert plan.status_code == 200, plan.text
    body = plan.json()
    to = {m["id"]: m["to"] for m in body["matched"]}
    assert to[pages["box1"].id].endswith("EAP_1740/Box 1/f001.jpg")
    assert to[pages["box2"].id].endswith("EAP_1740/Box 2/f001.jpg")  # same name, told apart by its box
    assert body["not_found"] == [] and body["ambiguous"] == []
    assert [f["to"] for f in body["folders"]] == [str(new / "EAP_1740")]
    assert body["sentence"] == "3 matched, 0 not found, 0 ambiguous; 1 folder moves with them."
    assert db.get(Document, pages["box1"].id).path == pages["box1"].path  # a plan writes nothing


def test_relinking_repoints_pages_and_folder_and_undo_puts_them_back(client, db, moved):
    folder, pages, new = moved
    done = client.post("/api/documents/relink-originals", json={"new_root": str(new)})
    assert done.status_code == 200, done.text
    for key, doc in pages.items():
        now = db.get(Document, doc.id)
        assert Path(now.path).is_file() and now.path.startswith(str(new))
        assert now.metadata["source_path"] == now.path and now.metadata["source_folder"] == str(Path(now.path).parent)
    assert db.get(Document, folder.id).path == str(new / "EAP_1740")
    assert client.get("/api/documents/missing-originals").json() is None

    audit = next(a for a in db.query(ActionAudit) if a.action_name == "document.relink_originals")
    assert client.post(f"/api/actions/audit/{audit.id}/undo").status_code == 200
    for doc in pages.values():
        back = db.get(Document, doc.id)
        assert back.path == doc.path and back.metadata["source_path"] == doc.path
    assert db.get(Document, folder.id).path == folder.path


def test_ambiguous_names_are_listed_never_chosen_and_a_checksum_settles_them(client, db, tmp_path):
    gone = tmp_path / "gone"
    twin = _linked(db, _file(gone / "loose" / "dup.jpg", b"same" * 10))
    settled = _linked(db, _file(gone / "loose2" / "dup2.jpg", b"same2" * 10), checksum=True)
    other = _linked(db, _file(gone / "x" / "lonely.jpg", b"a" * 10))
    missing = _linked(db, _file(gone / "x" / "nowhere.jpg", b"b" * 10))
    shutil.rmtree(gone)
    new = tmp_path / "found"
    _file(new / "a" / "dup.jpg", b"same" * 10)
    _file(new / "b" / "dup.jpg", b"SAME" * 10)  # same name and size, other bytes
    _file(new / "a" / "dup2.jpg", b"same2" * 10)
    _file(new / "b" / "dup2.jpg", b"SAME2" * 10)
    _file(new / "c" / "lonely.jpg", b"a" * 99)  # the right name, another size

    body = client.post("/api/documents/relink-originals/plan", json={"new_root": str(new)}).json()

    (amb,) = body["ambiguous"]
    assert amb["id"] == twin.id and len(amb["candidates"]) == 2 and "name alone" in amb["why"]
    (m,) = body["matched"]
    assert m["id"] == settled.id and m["to"].endswith("a/dup2.jpg")  # its checksum told the twins apart
    why = {n["id"]: n["why"] for n in body["not_found"]}
    assert "another size" in why[other.id] and why[missing.id] == "no file of that name under the folder"


def test_a_folder_that_is_not_one_is_refused(client, tmp_path):
    f = _file(tmp_path / "a.txt", b"x")
    assert client.post("/api/documents/relink-originals/plan", json={"new_root": str(f)}).status_code == 400
