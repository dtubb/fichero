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


# --- a reader whose pages differ (multi-user): a comment is as readable as the node it is on ---

from fichero_server.models.kg_comments import CommentAnchorKind, KgComment  # noqa: E402
from tests.unit.api.test_segments_multiuser_access import (  # noqa: E402,F401  (fixtures)
    _grant_role, _make_doc, _make_pass, _make_segment, _override, multiuser_client, users,
)


def _comment(db, kind, anchor_id, body="private"):
    db.save(KgComment(anchor_kind=kind, anchor_id=anchor_id, body=body, created_by="owner"))


def test_a_denied_page_hides_the_comments_on_its_source_segment_and_entity(multiuser_client, app_db, users, db):  # noqa: F811  (fixtures imported above)
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied, allowed = _make_doc(db, "denied.jpg"), _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    seg = _make_segment(db, document_id=denied.id, pass_id=_make_pass(db, denied.id).id, rect=[0.1, 0.1, 0.1, 0.1])
    hidden = KnowledgeEntity(canonical_name="Hidden", entity_type=EntityType.person, source_document_ids=[denied.id])
    db.save(hidden, auto_embed=False)
    open_seg = _make_segment(db, document_id=allowed.id, pass_id=_make_pass(db, allowed.id).id, rect=[0.2, 0.2, 0.1, 0.1])
    for kind, anchor in ((CommentAnchorKind.source, denied.id), (CommentAnchorKind.segment, seg.id),
                         (CommentAnchorKind.entity, hidden.id), (CommentAnchorKind.segment, open_seg.id)):
        _comment(db, kind, anchor)

    def read(anchor):
        r = client.get("/api/kg/comments", params={"anchor_id": anchor}, headers=login("editor"))
        return [] if r.status_code == 403 else r.json()["items"]  # refused outright or listed empty: either hides it

    assert read(denied.id) == [] and read(seg.id) == [] and read(hidden.id) == []
    assert [c["body"] for c in read(open_seg.id)] == ["private"]  # a page the editor may read stays readable


def test_a_denied_page_refuses_a_comment_on_it(multiuser_client, app_db, users, db):  # noqa: F811  (fixtures imported above)
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied = _make_doc(db, "denied.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    seg = _make_segment(db, document_id=denied.id, pass_id=_make_pass(db, denied.id).id, rect=[0.1, 0.1, 0.1, 0.1])
    for kind, anchor in (("source", denied.id), ("segment", seg.id)):
        refused = client.post("/api/actions/invoke", headers=login("editor"), json={
            "name": "kg.comment.add", "params": {"anchor_kind": kind, "anchor_id": anchor, "body": "x"}})
        assert refused.status_code == 403, (kind, refused.text)
