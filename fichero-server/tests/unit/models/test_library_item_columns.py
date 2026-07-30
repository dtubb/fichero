"""Bulk library-column metadata route coverage (#3700)."""

import pytest

from fichero_server.api.routes.library import items as library_items
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    Annotation,
    AnnotationKind,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
)
from fichero_server.models import DocType, Document


@pytest.mark.asyncio
async def test_columns_are_batched_ordered_and_roll_up_descendants(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "library" / "fichero.duckdb")
    parent = Document(name="Letter", doc_type=DocType.group)
    child = Document(name="Page one", parent_id=parent.id, bbox=(1, 2, 3, 4))
    empty = Document(name="Empty")
    entity = KnowledgeEntity(canonical_name="Rosario", entity_type=EntityType.person)
    db.save(parent)
    db.save(child)
    db.save(empty)
    db.save(entity)
    db.save(KnowledgeClaim(
        text="Rosario wrote the letter", source_document_id=child.id,
        entity_ids=[entity.id], source_bbox=[0.1, 0.1, 0.2, 0.2],
    ))
    db.save(Annotation(
        kind=AnnotationKind.highlight, document_id=child.id,
        bbox=[0.2, 0.2, 0.2, 0.2], text="signature",
    ))
    db.save(Note(title="Context", linked_document_ids=[child.id]))
    calls = 0
    original_all, original_query_in = db.all, db.query_in
    original_json_query = db.query_json_list_intersects

    def counted_all(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_all(*args, **kwargs)

    def counted_query_in(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_query_in(*args, **kwargs)

    def counted_json_query(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_json_query(*args, **kwargs)

    monkeypatch.setattr(db, "all", counted_all)
    monkeypatch.setattr(db, "query_in", counted_query_in)
    monkeypatch.setattr(db, "query_json_list_intersects", counted_json_query)
    try:
        response = await library_items.library_item_columns(
            library_items.LibraryItemColumnsRequest(
                item_ids=[empty.id, parent.id], include_descendants=True
            ), db,
        )
    finally:
        db.conn.close()

    assert [row.item_id for row in response.items] == [empty.id, parent.id]
    assert response.items[0].model_dump(exclude={"item_id"}) == {
        "entities": [], "annotations": [], "notes": [],
        "bbox_counts": {"node_regions": 0, "annotations": 0, "claims": 0},
    }
    parent_row = response.items[1]
    assert [(item.id, item.name) for item in parent_row.entities] == [(entity.id, "Rosario")]
    assert [item.title for item in parent_row.notes] == ["Context"]
    assert parent_row.bbox_counts.model_dump() == {
        "node_regions": 1, "annotations": 1, "claims": 1,
    }
    assert calls == 10  # Fixed bulk loads, not one metadata query per requested item.


@pytest.mark.asyncio
async def test_columns_empty_request_is_empty(tmp_path):
    db = Database(path=tmp_path / "library" / "fichero.duckdb")
    try:
        response = await library_items.library_item_columns(
            library_items.LibraryItemColumnsRequest(), db
        )
        assert response.items == []
    finally:
        db.conn.close()
