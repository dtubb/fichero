"""What is said about a segment (#4932; `source.statement.on-segment`, `both-ways`): the claims and
mentions whose anchor names it, from `GET /api/segments/{id}/statements`, on the imported Syriac page.

What breaks without these: a claim about one line shown on every line of its page (the page is not
the segment), a claim that names the line only through a supporting source left out, a merged entity
mentioned twice, or a provisional id answered with a 500.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity, SourceSupport
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _lines(client, doc_id):
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                  key=lambda s: s["anchor"]["rect"])


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_a_line_answers_the_claims_and_mentions_whose_anchor_names_it_and_no_others(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _lines(client, doc_id)[:2]
    # A claim, anchored to the first line through the calls the app makes (create, then patch its anchor).
    created = _ok(client.post("/api/actions/invoke", json={"name": "claim.create", "params": {
        "text": "Abraham begat Isaac", "source_document_id": doc_id, "source_excerpt": "ܐܒܪܗܡ ܐܘܠܕ"}}))
    claim_id = created["result"]["id"]
    _ok(client.post("/api/actions/invoke", json={"name": "claim.patch", "params": {
        "claim_id": claim_id,
        "patch": {"source_anchor": {"document_id": doc_id, "segment_id": first["id"], "rect": first["anchor"]["rect"]}},
    }}))
    # A claim of the same PAGE that names no segment: not about the first line.
    _ok(client.post("/api/actions/invoke", json={"name": "claim.create", "params": {
        "text": "The page is a genealogy", "source_document_id": doc_id}}))
    # A claim whose SUPPORTING source names the first line.
    db.save(KnowledgeClaim(text="Isaac begat Jacob", source_document_id=doc_id, source_supports=[
        SourceSupport(source_document_id=doc_id, source_excerpt="ܐܝܣܚܩ",
                      source_anchor=SourceAnchor(document_id=doc_id, segment_id=first["id"]))]))
    # Mentions: Abraham on the first line; Jacob on the second; a merged duplicate of Abraham.
    def mention(name, segment_id, merged_into=None):
        entity = KnowledgeEntity(
            canonical_name=name, entity_type=EntityType.person, source_document_ids=[doc_id],
            merged_into_id=merged_into, source_supports=[SourceSupport(
                source_document_id=doc_id, source_excerpt=name,
                source_anchor=SourceAnchor(document_id=doc_id, segment_id=segment_id))])
        db.save(entity)
        return entity
    abraham = mention("Abraham", first["id"])
    mention("Jacob", second["id"])
    mention("Abraham (duplicate)", first["id"], merged_into=abraham.id)

    said = _ok(client.get(f"/api/segments/{first['id']}/statements"))
    assert [(c["text"], c["via"]) for c in said["claims"]] == [
        ("Abraham begat Isaac", "anchor"), ("Isaac begat Jacob", "support")]
    assert said["claims"][0]["claim_id"] == claim_id
    assert [(m["name"], m["entity_type"]) for m in said["mentions"]] == [("Abraham", "person")]
    assert [m["name"] for m in _ok(client.get(f"/api/segments/{second['id']}/statements"))["mentions"]] == ["Jacob"]


def test_a_provisional_or_unknown_segment_is_refused_by_name(db, client):
    assert client.get("/api/segments/legacy:a1:0/statements").status_code == 422
    assert client.get("/api/segments/not-a-segment/statements").status_code == 404
