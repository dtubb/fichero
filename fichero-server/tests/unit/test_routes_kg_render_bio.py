"""Tests for POST /api/kg/entities/{entity_id}/bio (LLM biography generation).

#1361 — wraps assemble_entity_biography + LLM narration, persists
entity.description.  The LLM call is mocked so no provider required.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity, EntityType
from fichero_server.models import ActionAudit, Document, DocType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(db, name: str = "Marie Curie") -> KnowledgeEntity:
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=EntityType.person,
        aliases=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


def _make_doc(db, name: str = "Source") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_claim(db, entity: KnowledgeEntity, doc: Document, text: str) -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[entity.id],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


_MOCK_BIO = "Marie Curie was a pioneering physicist and chemist, famous for her research on radioactivity."


# ---------------------------------------------------------------------------
# POST /api/kg/entities/{entity_id}/bio
# ---------------------------------------------------------------------------


class TestGenerateEntityBio:
    def test_404_for_missing_entity(self, client):
        r = client.post("/api/kg/entities/does-not-exist/bio", json={})
        assert r.status_code == 404

    def test_generates_bio_and_persists(self, client, db):
        entity = _make_entity(db)
        doc = _make_doc(db)
        _make_claim(db, entity, doc, "Marie Curie discovered polonium.")
        _make_claim(db, entity, doc, "Marie Curie won two Nobel Prizes.")

        with patch(
            "fichero_server.api.routes.kg_render.chat", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = _MOCK_BIO
            r = client.post(f"/api/kg/entities/{entity.id}/bio", json={})

        assert r.status_code == 200
        body = r.json()
        assert body["biography"] == _MOCK_BIO
        assert body["entity_id"] == entity.id

        # Persisted to DB
        refreshed = db.get(KnowledgeEntity, entity.id)
        assert refreshed is not None
        assert refreshed.description == _MOCK_BIO
        # LLM was called once
        mock_chat.assert_called_once()

    def test_preserves_existing_human_description(self, client, db):
        entity = _make_entity(db)
        entity.description = "Old description."
        db.save(entity)

        new_bio = "Updated biography after regeneration."
        with patch(
            "fichero_server.api.routes.kg_render.chat", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = new_bio
            r = client.post(f"/api/kg/entities/{entity.id}/bio", json={})

        assert r.status_code == 200
        assert r.json()["biography"] == new_bio
        refreshed = db.get(KnowledgeEntity, entity.id)
        assert refreshed.description == "Old description."
        assert refreshed.metadata["ai_biography"] == new_bio
        assert refreshed.metadata["biography_provenance"]["claim_ids"] == []
        assert any(a.action_name == "entity.update" for a in db.all(ActionAudit))

    def test_no_claims_still_calls_llm(self, client, db):
        entity = _make_entity(db, "Unknown Person")

        with patch(
            "fichero_server.api.routes.kg_render.chat", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "Minimal bio."
            r = client.post(f"/api/kg/entities/{entity.id}/bio", json={})

        assert r.status_code == 200
        mock_chat.assert_called_once()
        # Prompt should still mention entity name even without claims
        call_args = mock_chat.call_args
        prompt_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
        assert "Unknown Person" in prompt_arg

    def test_llm_error_returns_500(self, client, db):
        entity = _make_entity(db)

        with patch(
            "fichero_server.api.routes.kg_render.chat", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM unavailable")
            r = client.post(f"/api/kg/entities/{entity.id}/bio", json={})

        assert r.status_code == 500

    def test_prompt_includes_svo_claims(self, client, db):
        entity = _make_entity(db, "Ada Lovelace")
        doc = _make_doc(db)
        _make_claim(db, entity, doc, "Ada Lovelace wrote the first algorithm.")

        captured_prompt: list[str] = []

        async def capture(prompt, config, **kwargs):
            captured_prompt.append(prompt)
            return "Bio text."

        with patch("fichero_server.api.routes.kg_render.chat", side_effect=capture):
            r = client.post(f"/api/kg/entities/{entity.id}/bio", json={})

        assert r.status_code == 200
        assert captured_prompt
        assert "Ada Lovelace" in captured_prompt[0]
        assert "wrote the first algorithm" in captured_prompt[0]
