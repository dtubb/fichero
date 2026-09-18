"""Tests for GET /api/kg/entities/{entity_id}/readable — the entry composer route
(#4832, #4838). Read-only: no LLM, no action-registry write (nothing to invoke),
served straight from `knowledge.readable.render_entry`.
"""

from __future__ import annotations

from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


def _entity(db, canonical_name: str, **kw) -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name=canonical_name, **kw)
    db.save(entity)
    return entity


def _svo_claim(db, subject_entity, verb, obj, **kw) -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=f"{subject_entity.canonical_name} {verb} {obj}",
        svo_subject=subject_entity.canonical_name,
        svo_verb=verb,
        svo_object=obj,
        subject_entity_id=subject_entity.id,
        entity_ids=[subject_entity.id],
        **kw,
    )
    db.save(claim)
    return claim


class TestGetEntityReadable:
    def test_404_for_unknown_entity(self, client):
        r = client.get("/api/kg/entities/does-not-exist/readable")
        assert r.status_code == 404

    def test_returns_the_shape(self, client, db):
        ana = _entity(db, "Ana")
        claim = _svo_claim(db, ana, "nació en", "Quibdó", source_languages=["es"])

        r = client.get(f"/api/kg/entities/{ana.id}/readable")
        assert r.status_code == 200
        body = r.json()
        assert body["entity_id"] == ana.id
        assert body["paragraph"] == "Ana nació en Quibdó."
        assert len(body["sentences"]) == 1
        sentence = body["sentences"][0]
        assert sentence["text"] == "Ana nació en Quibdó."
        assert sentence["claim_ids"] == [claim.id]
        assert sentence["role"] == "subject"
        assert sentence["revoiced"] is False
        assert sentence["language"] == "es"

    def test_offsets_slice_into_the_paragraph(self, client, db):
        ana = _entity(db, "Ana")
        _svo_claim(db, ana, "nació en", "Quibdó", time_start="1780-01-01")
        _svo_claim(db, ana, "murió en", "Nóvita", time_start="1799-01-01")

        body = client.get(f"/api/kg/entities/{ana.id}/readable").json()
        paragraph = body["paragraph"]
        for sentence in body["sentences"]:
            assert paragraph[sentence["start"] : sentence["end"]] == sentence["text"]

    def test_null_language_round_trips(self, client, db):
        ana = _entity(db, "Ana")
        _svo_claim(db, ana, "nació en", "Quibdó")  # no source_languages set

        body = client.get(f"/api/kg/entities/{ana.id}/readable").json()
        assert body["sentences"][0]["language"] is None

    def test_a_claim_belonging_to_another_entity_is_not_returned(self, client, db):
        ana = _entity(db, "Ana")
        other = _entity(db, "Pedro")
        _svo_claim(db, other, "vivió en", "Nóvita")  # Pedro's claim only

        body = client.get(f"/api/kg/entities/{ana.id}/readable").json()
        assert body["sentences"] == []
        assert body["paragraph"] == ""
