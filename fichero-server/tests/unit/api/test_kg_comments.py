"""kg.interact.comment: a human comment on a claim or an entity, its own threaded record, never a claim (#4643)."""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity


@pytest.fixture(autouse=True)
def _no_embedding(monkeypatch):
    # saving an entity would load the embedding model; these tests are about comments
    from fichero_server.db.embeddings import DatabaseEmbeddingMixin

    monkeypatch.setattr(DatabaseEmbeddingMixin, "_schedule_embedding_task", lambda *a, **k: None)


def _invoke(client, name: str, params: dict):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _entity(db) -> KnowledgeEntity:
    e = KnowledgeEntity(canonical_name="Ana Mora", entity_type=EntityType.person)
    db.save(e, auto_embed=False)
    return e


def test_a_comment_is_authored_dated_threaded_and_never_a_claim(db, client):
    entity = _entity(db)
    claims_before = len(db.all(KnowledgeClaim))
    first = _invoke(client, "kg.comment.add", {"anchor_kind": "entity", "anchor_id": entity.id, "body": "check the spelling"})
    assert first.status_code == 200, first.text
    first_id = first.json()["result"]["comment_id"]
    reply = _invoke(client, "kg.comment.add", {"anchor_kind": "entity", "anchor_id": entity.id,
                                               "body": "agreed", "parent_id": first_id})
    assert reply.status_code == 200, reply.text

    listed = client.get("/api/kg/comments", params={"anchor_id": entity.id}).json()
    assert [c["body"] for c in listed["items"]] == ["check the spelling", "agreed"]
    top, child = listed["items"]
    assert child["parent_id"] == first_id and top["parent_id"] is None
    assert top["created_by"] and top["created_at"] and top["provenance_kind"]
    assert len(db.all(KnowledgeClaim)) == claims_before  # a comment is never stored as a claim


def test_a_comment_needs_a_real_anchor_and_a_parent_on_the_same_anchor(db, client):
    entity, other = _entity(db), _entity(db)
    assert _invoke(client, "kg.comment.add", {"anchor_kind": "claim", "anchor_id": "nope", "body": "x"}).status_code == 404
    on_other = _invoke(client, "kg.comment.add", {"anchor_kind": "entity", "anchor_id": other.id, "body": "x"}).json()["result"]["comment_id"]
    wrong = _invoke(client, "kg.comment.add", {"anchor_kind": "entity", "anchor_id": entity.id, "body": "x", "parent_id": on_other})
    assert wrong.status_code == 422


def test_undo_withdraws_a_comment_and_the_list_leaves_it_out(db, client):
    entity = _entity(db)
    added = _invoke(client, "kg.comment.add", {"anchor_kind": "entity", "anchor_id": entity.id, "body": "note"})
    assert client.post(f"/api/actions/audit/{added.json()['audit_id']}/undo").status_code == 200
    assert client.get("/api/kg/comments", params={"anchor_id": entity.id}).json()["items"] == []


def test_the_agent_tool_exists_for_comments():
    from fichero_mcp import openapi_tools_generated as generated

    assert hasattr(generated, "fichero_knowledge_graph_list_comments")
