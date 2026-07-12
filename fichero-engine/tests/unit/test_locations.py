from fichero.api.routes.locations import Location, LocationSurface, resolve_location
from fichero.models import DocType, Document
import asyncio
import pytest
from fastapi import HTTPException


def test_resolves_document_and_semantic_anchors(db):
    doc = Document(name="source")
    db.save(doc)
    result = asyncio.run(resolve_location(Location(documentId=doc.id, claimId="c", entityId="e", surface=LocationSurface.preview), db))
    assert (result.resolved_document_id, result.claim_id, result.entity_id) == (doc.id, "c", "e")


def test_page_child_resolves_parent_page(db):
    parent = Document(name="pdf")
    child = Document(name="page", parent_id=parent.id, doc_type=DocType.page, sequence=1)
    db.save(parent)
    db.save(child)
    result = asyncio.run(resolve_location(Location(documentId=child.id), db))
    assert (result.resolved_document_id, result.resolved_page) == (parent.id, 1)


def test_rejects_invalid_document_page_and_bbox(db):
    with pytest.raises(HTTPException, match="Document not found"):
        asyncio.run(resolve_location(Location(documentId="missing"), db))
    with pytest.raises(ValueError, match="bbox"):
        Location(documentId="x", bbox=[0, 0, 2, 1])


@pytest.mark.parametrize("surface", list(LocationSurface))
def test_location_preserves_valid_anchors_without_writes(db, surface):
    doc = Document(name="source")
    db.save(doc)
    before = len(db.all(Document))
    location = Location(
        documentId=doc.id, bbox=[0.1, 0.2, 0.3, 0.4],
        charRange={"start": 1, "end": 3}, claimId="claim", entityId="entity", surface=surface,
    )
    result = asyncio.run(resolve_location(location, db))
    assert result.model_dump(by_alias=True)["resolvedDocumentId"] == doc.id
    assert result.bbox == location.bbox and result.char_range.start == 1
    assert len(db.all(Document)) == before


def test_page_range_and_derived_child_are_sane(db):
    parent = Document(name="parent")
    page = Document(name="page", parent_id=parent.id, doc_type=DocType.page, sequence=1)
    child = Document(name="crop", parent_id=parent.id, metadata={"derived_from": parent.id})
    db.save(parent)
    db.save(page)
    db.save(child)
    with pytest.raises(HTTPException, match="outside"):
        asyncio.run(resolve_location(Location(documentId=parent.id, page=2), db))
    assert asyncio.run(resolve_location(Location(documentId=child.id), db)).resolved_document_id == child.id
