"""#2359: image-to-KG provenance regression — source survives + rerun is idempotent.

Focused slice of the capture provenance suite: a captured image becomes
entities/claims without losing the link back to its source document, and
re-running the pipeline on the same source does NOT duplicate entities. Uses the
deterministic SequenceMatcher path (embeddings stubbed) — no model calls.
"""

from __future__ import annotations

import pytest

from fichero.knowledge_models import EntityType, KnowledgeEntity
from fichero.models import DocType, Document, FileType


@pytest.fixture
def _no_embeddings(monkeypatch):
    """Deterministic exact/fuzzy matching without the embedding model."""
    from fichero.kg import entity_vectors

    monkeypatch.setattr(entity_vectors, "find_similar", lambda **_: [])
    monkeypatch.setattr(entity_vectors, "index_entity", lambda **_: None)


def _image_source(db, doc_id: str, name: str) -> str:
    doc = Document(
        id=doc_id, name=name, doc_type=DocType.file, file_type=FileType.image
    )
    db.save(doc)
    return doc.id


def test_entity_carries_source_document_provenance(db, _no_embeddings):
    from fichero.workflows.tools._entity_writer import upsert_entity

    src = _image_source(db, "img-1", "scan-001.jpg")
    eid = upsert_entity(
        db, canonical_name="María Angel", entity_type=EntityType.person,
        source_document_id=src,
    )
    ent = db.get(KnowledgeEntity, eid)
    assert src in (ent.source_document_ids or []), "entity must link back to its image"


def test_rerun_same_source_does_not_duplicate_entity(db, _no_embeddings):
    from fichero.workflows.tools._entity_writer import upsert_entity

    src = _image_source(db, "img-2", "scan-002.jpg")
    id1 = upsert_entity(
        db, canonical_name="Juan Pérez", entity_type=EntityType.person,
        source_document_id=src,
    )
    id2 = upsert_entity(
        db, canonical_name="Juan Pérez", entity_type=EntityType.person,
        source_document_id=src,
    )
    assert id1 == id2
    rows = db.query(KnowledgeEntity, canonical_name="Juan Pérez", entity_type=EntityType.person)
    assert len(rows) == 1, "rerun on the same source must not duplicate the entity"
    # And the source id is recorded once, not appended twice.
    assert (rows[0].source_document_ids or []).count(src) == 1


def test_provenance_accumulates_across_distinct_sources(db, _no_embeddings):
    from fichero.workflows.tools._entity_writer import upsert_entity

    a = _image_source(db, "img-3a", "page-3a.jpg")
    b = _image_source(db, "img-3b", "page-3b.jpg")
    id_a = upsert_entity(
        db, canonical_name="Bogotá", entity_type=EntityType.location, source_document_id=a
    )
    id_b = upsert_entity(
        db, canonical_name="Bogotá", entity_type=EntityType.location, source_document_id=b
    )
    assert id_a == id_b  # one entity...
    ent = db.get(KnowledgeEntity, id_a)
    # ...that knows it appears on both source images.
    assert set(ent.source_document_ids or []) >= {a, b}


def test_source_provenance_survives_model_dump(db, _no_embeddings):
    from fichero.workflows.tools._entity_writer import upsert_entity

    src = _image_source(db, "img-4", "scan-004.jpg")
    eid = upsert_entity(
        db, canonical_name="Cartagena", entity_type=EntityType.location,
        source_document_id=src,
    )
    dumped = db.get(KnowledgeEntity, eid).model_dump(mode="json")
    assert src in dumped["source_document_ids"], "provenance must survive serialization"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
