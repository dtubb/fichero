"""`safety.trash.dependants-go-with-their-source` (#5406, #5243): the library-wide artifact list leaves a trashed document's artifacts out.

The leaving-out runs in the same WHERE as the count and the page, so `count` stays the true total of what is shown.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Artifact, DocType, Document

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


def _listed(client):
    body = client.get("/api/artifacts/").json()
    return {a["id"] for a in body["items"]}, body["count"]


def test_a_trashed_documents_artifacts_leave_the_list_and_the_count_and_come_back(db, client):
    trashed, live = _page(db, "trashed.jpg"), _page(db, "live.jpg")
    gone = Artifact(document_id=trashed.id, artifact_type="ocr")
    kept = Artifact(document_id=live.id, artifact_type="ocr")
    for row in (gone, kept):
        db.save(row)
    before = _listed(client)
    assert before == ({gone.id, kept.id}, 2)

    registry.invoke(db, "document.delete", {"doc_id": trashed.id}, CTX)
    assert _listed(client) == ({kept.id}, 1)

    registry.invoke(db, "document.restore", {"doc_id": trashed.id}, CTX)
    assert _listed(client) == before
