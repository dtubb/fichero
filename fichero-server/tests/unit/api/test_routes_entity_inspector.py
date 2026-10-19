"""Coverage for entity-inspector summary composition."""

from __future__ import annotations

from fichero_server.api.routes.entity import inspector
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.models import Document


def test_summary_describes_type_claims_documents_and_aliases():
    entity = KnowledgeEntity(
        id="e1",
        canonical_name="Alice",
        entity_type=EntityType.person,
        aliases=["A.", "Ally", "Alicia", "extra"],
    )
    claims = [KnowledgeClaim(text="one"), KnowledgeClaim(text="two")]
    documents = [Document(name="one"), Document(name="two")]

    assert inspector._compose_entity_summary(entity, claims, documents) == (
        "Person · 2 claims across 2 documents · also known as A., Ally, Alicia…"
    )


def test_summary_handles_no_claims_and_unknown_type():
    entity = KnowledgeEntity(id="e1", canonical_name="Thing", entity_type=EntityType.other)

    assert inspector._compose_entity_summary(entity, [], []) == "Entity · no claims yet"


def test_summary_uses_singular_claim_label_for_one_claim():
    entity = KnowledgeEntity(id="e1", canonical_name="Place", entity_type=EntityType.location)

    assert inspector._compose_entity_summary(entity, [KnowledgeClaim(text="claim")], []) == (
        "Place · 1 claim"
    )


def test_stale_reason_is_the_vector_reason_or_none():
    """#5360: the Inspector response carries why the stored vector is out of date."""
    from unittest.mock import MagicMock

    entity = KnowledgeEntity(id="e1", canonical_name="Alice", entity_type=EntityType.person)
    db = MagicMock()
    db.entity_embedding_text.return_value = "Alice"
    db.stale_reasons.return_value = {"e1": "text-changed"}
    assert inspector._stale_reason(db, entity) == "text-changed"
    db.stale_reasons.return_value = {}
    assert inspector._stale_reason(db, entity) is None
    assert "stale_reason" in inspector.EntityInspectorResponse.model_fields


def test_a_fresh_entity_reads_not_embedded_on_a_real_db(db, monkeypatch):
    """Review 121: through the real db, so a renamed helper on it fails here.

    `Database.save` of an entity schedules its embedding off-thread (`schedule_entity_embedding`); once an earlier
    test in the run has warmed the embedder that finishes before the assertion and the vector is current. The test
    holds that one hook still so the entity is genuinely fresh, whatever ran before it."""
    monkeypatch.setattr(db, "schedule_entity_embedding", lambda entity: None)
    entity = KnowledgeEntity(canonical_name="Alice", entity_type=EntityType.person)
    db.save(entity)

    assert inspector._stale_reason(db, entity) == "not-embedded"
