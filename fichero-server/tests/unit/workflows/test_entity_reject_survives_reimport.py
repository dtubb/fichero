"""#5072 reject: the rejected entity row is the durable record; a re-import must not
attach new claims to it (nor resurrect it)."""

import fichero_server.api.routes.kg_entity_curation  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models.knowledge import (
    EntityCurationState, EntityType, KnowledgeClaim, KnowledgeEntity,
)
from fichero_server.workflows.tools.extractors import _write_kg_rows


def _import(db, name, doc):
    _write_kg_rows(
        db,
        section={"name": "people", "entity_type": EntityType.person},
        items=[{"name": name, "verb": "signed", "object": "the deed"}],
        container_id=doc, page_label="1", source_excerpt=f"{name} signed the deed.",
    )


class TestRejectedEntityStaysRejectedOnReimport:
    def test_reimport_attaches_no_claim_to_the_rejected_entity(self, db):
        _import(db, "Noise Person", "doc-a")
        (ent,) = db.query(KnowledgeEntity)
        registry.invoke(db, "entity.batch_curation",
                        {"entity_ids": [ent.id], "curation_state": "rejected"},
                        ActionContext(actor="ui", library_path="/lib/test.fichero"))
        assert db.get(KnowledgeEntity, ent.id).curation_state == EntityCurationState.rejected
        _import(db, "Noise Person", "doc-b")
        assert db.get(KnowledgeEntity, ent.id).curation_state == EntityCurationState.rejected
        on_rejected = [c for c in db.query(KnowledgeClaim)
                       if c.source_document_id == "doc-b" and c.subject_entity_id == ent.id]
        assert on_rejected == []
