"""Batched metadata columns for a page of library items (#3700)."""

from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database_for_write
from fichero.db import Database
from fichero.models.knowledge import Annotation, KnowledgeClaim, KnowledgeEntity, Note
from fichero.models import Document

router = APIRouter(prefix="/library-items", tags=["library-items"])


class LibraryItemColumnsRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list, max_length=200)
    include_descendants: bool = False


class ColumnEntity(BaseModel):
    id: str
    name: str
    type: str


class ColumnAnnotation(BaseModel):
    id: str
    kind: str
    bbox: list[float] | None = None


class ColumnNote(BaseModel):
    id: str
    title: str | None = None


class BBoxCounts(BaseModel):
    node_regions: int = 0
    annotations: int = 0
    claims: int = 0


class LibraryItemColumnsRow(BaseModel):
    item_id: str
    entities: list[ColumnEntity] = Field(default_factory=list)
    annotations: list[ColumnAnnotation] = Field(default_factory=list)
    notes: list[ColumnNote] = Field(default_factory=list)
    bbox_counts: BBoxCounts = Field(default_factory=BBoxCounts)


class LibraryItemColumnsResponse(BaseModel):
    items: list[LibraryItemColumnsRow]


def _scopes(item_ids: list[str], documents: list[Document], descendants: bool) -> dict[str, set[str]]:
    """Use the same parent tree semantics as document/claim descendant views."""
    scopes = {item_id: {item_id} for item_id in item_ids}
    if not descendants:
        return scopes
    children: dict[str, list[str]] = defaultdict(list)
    for document in documents:
        if document.parent_id:
            children[document.parent_id].append(document.id)
    for item_id, scope in scopes.items():
        frontier = [item_id]
        while frontier:
            frontier = [child for parent in frontier for child in children.get(parent, []) if child not in scope]
            scope.update(frontier)
    return scopes


@router.post(
    "/columns",
    response_model=LibraryItemColumnsResponse,
    summary="Batch library-item column metadata",
    description="Read-only set-based item metadata for library list and column-browser pages.",
)
async def library_item_columns(
    request: LibraryItemColumnsRequest,
    db: Database = Depends(get_library_database_for_write),
) -> LibraryItemColumnsResponse:
    item_ids = list(dict.fromkeys(request.item_ids))
    if not item_ids:
        return LibraryItemColumnsResponse(items=[])

    # One hierarchy read, then fixed bulk reads below: never call item routes.
    documents = db.all(Document)
    scopes = _scopes(item_ids, documents, request.include_descendants)
    scope_ids = set().union(*scopes.values())
    claims = db.query_in(KnowledgeClaim, "source_document_id", scope_ids)
    annotations = [
        annotation
        for field in ("document_id", "page_id", "folder_id")
        for annotation in db.query_in(Annotation, field, scope_ids)
    ]
    notes = [
        *db.query_in(Note, "page_id", scope_ids),
        *db.query_in(Note, "folder_id", scope_ids),
        *db.query_json_list_intersects(Note, "linked_document_ids", scope_ids),
    ]
    entity_ids = {entity_id for claim in claims for entity_id in claim.entity_ids}
    entities = [
        *db.query_in(KnowledgeEntity, "id", entity_ids),
        *db.query_json_list_intersects(KnowledgeEntity, "source_document_ids", scope_ids),
    ]

    rows = {item_id: LibraryItemColumnsRow(item_id=item_id) for item_id in item_ids}
    owners: dict[str, set[str]] = defaultdict(set)
    for item_id, scope in scopes.items():
        for document_id in scope:
            owners[document_id].add(item_id)
    row_entity_ids: dict[str, set[str]] = defaultdict(set)
    seen_annotations: dict[str, set[str]] = defaultdict(set)
    seen_notes: dict[str, set[str]] = defaultdict(set)

    # One grouping pass over each fixed bulk result; no per-item DB work.
    for document in documents:
        if document.bbox is not None:
            for item_id in owners.get(document.id, ()):
                rows[item_id].bbox_counts.node_regions += 1
    for claim in claims:
        for item_id in owners.get(claim.source_document_id, ()):
            row_entity_ids[item_id].update(claim.entity_ids)
            if claim.source_bbox is not None:
                rows[item_id].bbox_counts.claims += 1
    for annotation in annotations:
        for item_id in set().union(
            *(owners.get(document_id, set()) for document_id in (
                annotation.document_id, annotation.page_id, annotation.folder_id
            ))
        ):
            if annotation.id in seen_annotations[item_id]:
                continue
            seen_annotations[item_id].add(annotation.id)
            rows[item_id].annotations.append(ColumnAnnotation(
                id=annotation.id, kind=annotation.kind.value, bbox=annotation.bbox
            ))
            if annotation.bbox is not None:
                rows[item_id].bbox_counts.annotations += 1
    for note in notes:
        for item_id in set().union(
            *(owners.get(document_id, set()) for document_id in (
                note.page_id, note.folder_id, *(note.linked_document_ids or [])
            ))
        ):
            if note.id not in seen_notes[item_id]:
                seen_notes[item_id].add(note.id)
                rows[item_id].notes.append(ColumnNote(id=note.id, title=note.title))
    for entity in entities:
        for item_id in set().union(
            *(owners.get(document_id, set()) for document_id in entity.source_document_ids)
        ):
            row_entity_ids[item_id].add(entity.id)
    entities_by_id = {entity.id: entity for entity in entities}
    for item_id, entity_ids in row_entity_ids.items():
        rows[item_id].entities = [
            ColumnEntity(id=entity.id, name=entity.canonical_name, type=entity.entity_type.value)
            for entity_id in entity_ids
            if (entity := entities_by_id.get(entity_id)) is not None
        ]
    return LibraryItemColumnsResponse(items=[rows[item_id] for item_id in item_ids])
