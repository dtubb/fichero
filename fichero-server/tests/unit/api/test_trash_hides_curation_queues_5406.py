"""`safety.trash.every-read-leaves-it-out` (#5406): the four curation queues leave out statements resting only on the Trash.

A statement on a live page and one in the Trash sit in the same state; the queue and its total show only the live one,
and Put Back returns the other.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim

CTX = ActionContext(actor="tester", library_path="/tmp/library.fichero")
STATES = ["unreviewed", "shortlisted", "curated", "rejected"]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(
        "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation", lambda *_a, **_k: None
    )


def _queue(client, state):
    body = client.get(f"/api/claims/queues/{state}").json()
    return {c["claim_id"] for c in body["claims"]}, body["total"]


@pytest.mark.parametrize("state", STATES)
def test_a_trashed_pages_statement_leaves_the_queue_and_its_total_and_comes_back(db, client, state):
    trashed = Document(name="trashed.jpg", doc_type=DocType.file)
    live = Document(name="live.jpg", doc_type=DocType.file)
    for d in (trashed, live):
        db.save(d)
    gone = KnowledgeClaim(text="on the gone page", source_document_id=trashed.id,
                          curation_state=ClaimCurationState(state))
    kept = KnowledgeClaim(text="on the live page", source_document_id=live.id,
                          curation_state=ClaimCurationState(state))
    for c in (gone, kept):
        db.save(c)
    before = _queue(client, state)
    assert before == ({gone.id, kept.id}, 2)

    registry.invoke(db, "document.delete", {"doc_id": trashed.id}, CTX)
    assert _queue(client, state) == ({kept.id}, 1)

    registry.invoke(db, "document.restore", {"doc_id": trashed.id}, CTX)
    assert _queue(client, state) == before
