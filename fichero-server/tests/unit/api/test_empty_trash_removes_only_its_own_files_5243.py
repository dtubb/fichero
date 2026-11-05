"""`safety.trash.empty-removes-everything-and-only-that` (#5243): Empty Trash removes the trashed items' own stored files, and nothing else.

The guards, each a case below: a linked original (the user's own file, outside the library), a file a live document also uses,
a symlink out of the library, and a live document's file are all left; the preview's counts are what then goes.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import Note

CTX = ActionContext(actor="tester", library_path="/tmp/library.fichero")


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    for target in (
        "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation",
        "fichero_server.api.routes.document.trash.auto_snapshot_before_risky_operation",
    ):
        monkeypatch.setattr(target, lambda *_a, **_k: None, raising=False)


def _doc(db, name, path):
    doc = Document(name=name, doc_type=DocType.file, path=path)
    db.save(doc)
    return doc


def test_only_the_trashed_items_own_files_are_removed(db, client, tmp_path):
    root = db.path.parent
    (root / "files").mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "users_own_file.jpg"
    outside.write_bytes(b"linked original")
    elsewhere = tmp_path / "symlink_target.jpg"
    elsewhere.write_bytes(b"not ours")
    for name in ("gone.jpg", "kept.jpg", "shared.jpg"):
        (root / "files" / name).write_bytes(b"x" * 100)
    (root / "files" / "escape.jpg").symlink_to(elsewhere)

    gone = _doc(db, "gone", "files/gone.jpg")
    kept = _doc(db, "kept", "files/kept.jpg")
    shared_trashed = _doc(db, "shared-trashed", "files/shared.jpg")
    _doc(db, "shared-live", "files/shared.jpg")
    linked = _doc(db, "linked", str(outside))
    escaping = _doc(db, "escaping", "files/escape.jpg")
    thumb_dir = root / "storage" / "thumbnails" / gone.id[:2].lower()
    thumb_dir.mkdir(parents=True)
    (thumb_dir / f"{gone.id}.jpg").write_bytes(b"t" * 10)
    note_only_here = Note(body="only here", linked_document_ids=[gone.id])
    note_shared = Note(body="two places", linked_document_ids=[gone.id, kept.id])
    db.save(note_only_here), db.save(note_shared)

    for doc in (gone, shared_trashed, linked, escaping):
        registry.invoke(db, "document.delete", {"doc_id": doc.id}, CTX)

    preview = client.get("/api/documents/trash/empty").json()
    assert preview["stored_files"] == 2, preview  # gone.jpg and its thumbnail, nothing else
    assert preview["stored_bytes"] == 110
    assert preview["notes"] == 1
    assert "2 stored files" in preview["detail"] and "1 note" in preview["detail"]

    result = client.post("/api/documents/trash/empty")
    assert result.status_code == 200, result.text
    body = result.json()
    assert (body["files_removed"], body["bytes_freed"], body["notes_removed"]) == (2, 110, 1)

    assert not (root / "files" / "gone.jpg").exists()
    assert not (thumb_dir / f"{gone.id}.jpg").exists()
    for survivor in (root / "files" / "kept.jpg", root / "files" / "shared.jpg", outside, elsewhere):
        assert survivor.exists(), f"{survivor.name} must not be touched"
    assert (root / "files" / "escape.jpg").is_symlink()
    assert db.get(Note, note_only_here.id) is None
    assert db.get(Note, note_shared.id) is not None
    assert db.get(Document, kept.id) is not None
