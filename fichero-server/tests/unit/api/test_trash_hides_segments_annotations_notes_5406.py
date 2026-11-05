"""`safety.trash.dependants-go-with-their-source` (#5406, #5243): a trashed document's segments, annotations and notes are out of view.

A note that also links a live document stays. Put Back returns every one, row for row, since nothing is rewritten.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import Annotation, AnnotationKind, Note
from tests.unit.api.test_page_text_follows_the_file import BOOT

CTX = ActionContext(actor="tester", library_path="/tmp/library.fichero")


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(
        "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation", lambda *_a, **_k: None
    )


def _page(db, name):
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _segment(db, doc):
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": f"p {doc.name}"}, BOOT).result["id"]
    return registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "region",
        "anchor": {"document_id": doc.id, "shapes": [{"kind": "point", "points": [[0.5, 0.5]]}]}}, BOOT).result["segment_ids"][0]


def _seen(db, client, trashed, live):
    segments = client.get("/api/segments", params={"document_ids": f"{trashed.id},{live.id}"}).json()["items"]
    annotations = client.get("/api/annotations").json()["items"]
    notes = client.get("/api/notes").json()["items"]
    return (
        {s["document_id"] for s in segments},
        {a["id"] for a in annotations},
        {n["id"] for n in notes},
    )


def test_a_trashed_documents_segments_annotations_and_notes_leave_and_come_back(db, client):
    trashed, live = _page(db, "trashed.jpg"), _page(db, "live.jpg")
    _segment(db, trashed), _segment(db, live)
    gone_ann = Annotation(document_id=trashed.id, kind=AnnotationKind.bookmark)
    kept_ann = Annotation(document_id=live.id, kind=AnnotationKind.bookmark)
    gone_note = Note(body="only here", linked_document_ids=[trashed.id])
    both_note = Note(body="two places", linked_document_ids=[trashed.id, live.id])
    loose_note = Note(body="no document")
    for row in (gone_ann, kept_ann, gone_note, both_note, loose_note):
        db.save(row)

    before = _seen(db, client, trashed, live)
    assert before[0] == {trashed.id, live.id}
    assert before[1] == {gone_ann.id, kept_ann.id}
    assert before[2] == {gone_note.id, both_note.id, loose_note.id}

    registry.invoke(db, "document.delete", {"doc_id": trashed.id}, CTX)
    segments, annotations, notes = _seen(db, client, trashed, live)
    assert segments == {live.id}
    assert annotations == {kept_ann.id}
    assert notes == {both_note.id, loose_note.id}

    registry.invoke(db, "document.restore", {"doc_id": trashed.id}, CTX)
    assert _seen(db, client, trashed, live) == before
