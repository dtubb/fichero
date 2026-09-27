"""⌘Z and ⇧⌘Z on a region edit, as the app sends them (#4941, `source.editor.system-undo`).

The Swift side (`ActionUndoTests`) drives a real `UndoManager` against a FAKE engine,
so it cannot see what the engine does with the ids it is handed. This is the other
half: the exact requests the app makes -- `PUT /api/artifacts/{id}/regions`, then
`POST /api/actions/audit/{audit_id}/undo` with the edit's `audit_id`, then the same
with the UNDO's own `audit_id` for the redo -- against the real engine.

It exists because one reading of the code said redo could not work: the inverse of a
region edit is `artifact.restore`, declared `undoable=False`. It does work -- a redo
replays the original forward action rather than inverting the restore -- and this pins
that, so a change to either side shows up here rather than as a ⇧⌘Z that does nothing.
"""

from __future__ import annotations

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status

pytestmark = pytest.mark.source_model

MOVED = [0.5, 0.5, 0.1, 0.1]


def _make_doc(db) -> Document:
    doc = Document(
        name="page.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/page.jpg", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc) -> Artifact:
    artifact = Artifact(
        document_id=doc.id, artifact_type="transcription", provider="qwen",
        ocr_geometry=OCRGeometryResult(
            provider="qwen", text="w0 w1 w2",
            boxes=[
                OCRGeometryBox(text=f"w{i}", bbox=[0.1, 0.1 + i * 0.1, 0.2, 0.05])
                for i in range(3)
            ],
        ),
    )
    db.save(artifact)
    return artifact


def _box(client, artifact_id: str, index: int) -> list[float]:
    body = client.get(f"/api/artifacts/{artifact_id}").json()
    return body["ocr_geometry"]["boxes"][index]["bbox"]


def test_undo_restores_and_redo_reapplies_by_the_ids_each_step_answers(db, client):
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    original = _box(client, artifact.id, 1)

    edit = client.put(
        f"/api/artifacts/{artifact.id}/regions",
        json={"op": "move", "indices": [1], "bbox": MOVED},
    )
    assert edit.status_code == 200, edit.text
    assert _box(client, artifact.id, 1) == MOVED

    undo = client.post(f"/api/actions/audit/{edit.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert _box(client, artifact.id, 1) == original

    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 200, redo.text
    assert _box(client, artifact.id, 1) == MOVED


def test_the_same_undo_twice_is_refused_rather_than_applied_twice(db, client):
    """A second ⌘Z on the same row -- two windows, one library -- must not invert twice."""
    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    edit = client.put(
        f"/api/artifacts/{artifact.id}/regions",
        json={"op": "move", "indices": [1], "bbox": MOVED},
    )
    audit_id = edit.json()["audit_id"]
    assert client.post(f"/api/actions/audit/{audit_id}/undo").status_code == 200
    assert client.post(f"/api/actions/audit/{audit_id}/undo").status_code == 409
