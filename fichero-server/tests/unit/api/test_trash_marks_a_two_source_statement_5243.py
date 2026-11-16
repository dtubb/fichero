"""`safety.trash.dependants-go-with-their-source` (#5243): a statement resting on a live source and one in the Trash stays, and the list says
which of its sources is in the Trash. A statement with no source in the Trash carries no mark; Put Back clears it.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import KnowledgeClaim

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


def test_a_two_source_statement_names_the_source_in_the_trash(db, client):
    trashed, live = _page(db, "trashed.jpg"), _page(db, "live.jpg")
    two = KnowledgeClaim(text="on two pages", source_document_id=trashed.id, source_ids=[live.id])
    only_live = KnowledgeClaim(text="on one page", source_document_id=live.id)
    only_trashed = KnowledgeClaim(text="on the gone page", source_document_id=trashed.id)
    for claim in (two, only_live, only_trashed):
        db.save(claim)

    assert client.get("/api/claims").json()["sources_in_trash"] == {}

    registry.invoke(db, "document.delete", {"doc_id": trashed.id}, CTX)
    body = client.get("/api/claims").json()
    assert {c["id"] for c in body["items"]} == {two.id, only_live.id}, "a statement on a live source stays"
    assert body["sources_in_trash"] == {two.id: [trashed.id]}

    registry.invoke(db, "document.restore", {"doc_id": trashed.id}, CTX)
    assert client.get("/api/claims").json()["sources_in_trash"] == {}
