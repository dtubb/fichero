"""Per-page entity scope (#1562).

A KnowledgeEntity that appears on multiple pages of the same parent
document should accumulate every page id it was extracted from in its
``source_document_ids`` list — while still being a single deduped row
(the parent aggregates via descendants, the entity records each page).

These tests drive ``upsert_entity`` directly with two different page ids
for the same ``(canonical_name, entity_type)`` and assert the entity is
deduped to one row with BOTH page ids recorded.
"""

from __future__ import annotations

from fichero.models.knowledge import EntityType, KnowledgeEntity
from fichero.models import Document
from fichero.workflows.tools._entity_writer import upsert_entity


def _make_parent_with_two_pages(db) -> tuple[str, str, str]:
    """Create a parent doc with two page children; return (parent, p1, p2)."""
    parent = Document(name="Parent doc", doc_type="file")
    db.save(parent)
    page1 = Document(name="Page 1", doc_type="page", parent_id=parent.id)
    page2 = Document(name="Page 2", doc_type="page", parent_id=parent.id)
    db.save(page1)
    db.save(page2)
    return parent.id, page1.id, page2.id


class TestEntityPageScope:
    def test_entity_accumulates_both_page_ids_and_dedupes(self, db):
        _parent_id, page1_id, page2_id = _make_parent_with_two_pages(db)

        # Same canonical_name + type extracted on two different pages.
        id1 = upsert_entity(
            db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            source_document_id=page1_id,
        )
        id2 = upsert_entity(
            db,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
            source_document_id=page2_id,
        )

        # Deduped to a single entity row.
        assert id1 == id2
        all_people = db.query(
            KnowledgeEntity,
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
        )
        assert len(all_people) == 1

        entity = all_people[0]
        # Both page ids recorded — the per-page scope (#1562).
        assert page1_id in entity.source_document_ids
        assert page2_id in entity.source_document_ids
        assert len(entity.source_document_ids) == 2

    def test_repeat_same_page_does_not_duplicate_id(self, db):
        _parent_id, page1_id, _page2_id = _make_parent_with_two_pages(db)

        upsert_entity(
            db,
            canonical_name="Chocó",
            entity_type=EntityType.location,
            source_document_id=page1_id,
        )
        # Same page again — must not append a duplicate id.
        upsert_entity(
            db,
            canonical_name="Chocó",
            entity_type=EntityType.location,
            source_document_id=page1_id,
        )

        entity = db.query(
            KnowledgeEntity,
            canonical_name="Chocó",
            entity_type=EntityType.location,
        )[0]
        assert entity.source_document_ids == [page1_id]

    def test_omitting_page_id_is_a_no_op(self, db):
        # Back-compat: callers that don't pass a page id still work and
        # leave source_document_ids empty.
        entity_id = upsert_entity(
            db,
            canonical_name="silver",
            entity_type=EntityType.other,
        )
        entity = db.get(KnowledgeEntity, entity_id)
        assert entity.source_document_ids == []
