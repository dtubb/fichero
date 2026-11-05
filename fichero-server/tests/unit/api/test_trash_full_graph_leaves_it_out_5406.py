"""`safety.trash.every-read-leaves-it-out` (#5406, #5243): the full-library graphs leave a trashed page's knowledge out.

WHY: the claims list, the entities list, the neighbourhood and the knowledge search used the Trash seam, but
`build_full_graph` / `build_full_cooccurrence` (read by about eighteen graph endpoints) read every row, and their cache
key ignored the Trash, so a deleted page's statements still drew in the graph and a Put Back could not change a cached answer.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.documents  # noqa: F401  (registers the actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.knowledge.graph import build_full_cooccurrence, build_full_graph
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(
        "fichero_server.api.routes.document.documents.auto_snapshot_before_risky_operation", lambda *_a, **_k: None
    )


def _ctx() -> ActionContext:
    return ActionContext(actor="tester", library_path="/tmp/library.fichero")


def _page(db, name):
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _knowledge(db):
    page, other = _page(db, "trashed.jpg"), _page(db, "live.jpg")
    zebra = KnowledgeEntity(canonical_name="Zebra", source_document_ids=[page.id])
    giraffe = KnowledgeEntity(canonical_name="Giraffe", source_document_ids=[other.id])
    for entity in (zebra, giraffe):
        db.save(entity)
    db.save(KnowledgeClaim(text="zebra rests here",
                           source_document_id=page.id, entity_ids=[zebra.id]))
    db.save(KnowledgeClaim(text="giraffe stands",
                           source_document_id=other.id, entity_ids=[giraffe.id]))
    return page, zebra, giraffe


def test_a_trashed_page_leaves_both_full_graphs_and_put_back_returns_it(db):
    page, zebra, giraffe = _knowledge(db)
    assert {zebra.id, giraffe.id} <= set(build_full_graph(db).nodes)  # warms the cache

    registry.invoke(db, "document.delete", {"doc_id": page.id}, _ctx())
    for graph in (build_full_graph(db), build_full_cooccurrence(db)):
        assert zebra.id not in graph.nodes, "a trashed page's entity must leave the graph (cache keyed on the Trash)"
        assert giraffe.id in graph.nodes

    registry.invoke(db, "document.restore", {"doc_id": page.id}, _ctx())
    for graph in (build_full_graph(db), build_full_cooccurrence(db)):
        assert {zebra.id, giraffe.id} <= set(graph.nodes)
