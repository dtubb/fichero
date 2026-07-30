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
