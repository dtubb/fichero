"""
Document Routes

CRUD operations for Document model.
"""

import asyncio
import logging
import tempfile
from fichero_server.core.timeutil import utc_now
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import emit_change
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.ingest.iiif import build_document_annotation_page
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    Annotation,
    ClassificationDimension,
    ClassificationValue,
    DocumentCitation,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
    MutationOperationType,
    Note,
)
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models import (
    DocumentListResponse,
    DocumentNote,
    RelatedDocumentListResponse,
    RelatedDocumentsResponse,
)
from fichero_server.security.path_security import validate_stored_document_path
from fichero_server.core.perf import perf_span
from fichero_server.db.storage import auto_snapshot_before_risky_operation
from fichero_server.db.storage import settings as storage_settings
from fichero_server.actions.registry import registry

logger = logging.getLogger(__name__)
router = APIRouter()


def _emit_document_change_ctx(
    ctx: "ActionContext",
    *,
    event_type: str,
    document_ids: list[str],
) -> None:
    if not ctx.library_path or not document_ids:
        return
    emit_change(
        ctx.library_path,
        type=event_type,
        document_ids=document_ids,
        actor=ctx.actor,
        origin_window=ctx.origin_window,
        origin_user=ctx.actor,
    )


def _emit_document_change_spec(ctx: "ActionContext", spec: "ChangeSpec") -> None:
    if spec.emit_type is None:
        return
    _emit_document_change_ctx(
        ctx,
        event_type=spec.emit_type,
        document_ids=list(spec.document_ids),
    )


# Bounded retry for DuckDB's optimistic-concurrency write conflicts (#4285/
# #4286): a content-pane save racing a workflow's document writes used to
# escape as an unclassified 500 — the client rendered it as "Unexpected
# response from the server" and the pasted edit was silently lost. The
# action-registry transaction rolls back cleanly on conflict, so replaying the
# whole invoke is safe; after the retries are exhausted the caller gets a
# typed 409 that names the operation and tells the client to retry.
_WRITE_CONFLICT_RETRIES = 3
_WRITE_CONFLICT_BACKOFF_SECONDS = 0.05


async def _run_document_write(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run synchronous document DB mutations off the FastAPI event loop.

    Retries transient DuckDB transaction conflicts (concurrent writer — e.g.
    a workflow saving artifacts while the user saves page content) and maps a
    persistent conflict to HTTP 409 instead of an unclassified 500.
    """
    import duckdb

    last_exc: Exception | None = None
    for attempt in range(_WRITE_CONFLICT_RETRIES):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except duckdb.TransactionException as exc:
            last_exc = exc
            logger.warning(
                "document write hit a transaction conflict (attempt %d/%d): %s",
                attempt + 1,
                _WRITE_CONFLICT_RETRIES,
                exc,
            )
            await asyncio.sleep(_WRITE_CONFLICT_BACKOFF_SECONDS * (2**attempt))
    raise HTTPException(
        status_code=409,
        detail=(
            "The document write conflicted with another writer (a workflow or "
            f"another window) and was rolled back after {_WRITE_CONFLICT_RETRIES} "
            f"attempts — nothing was saved; retry the save. ({last_exc})"
        ),
    )


# Request/Response models


class ReorderResponse(BaseModel):
    status: str
    count: int


class OrphanCleanupResponse(BaseModel):
    orphaned_documents_deleted: int
    artifacts_deleted: int


# RelatedDocumentsResponse moved to fichero_server.models (#4120) so the
# RelatedDocumentListResponse envelope is fully typed in the OpenAPI spec.


class WorkflowRunProvenanceResponse(BaseModel):
    """One recorded workflow run against a document."""

    thread_id: str | None = None
    batch_id: str | None = None
    item_index: int | None = None
    workflow_id: str
    workflow_name: str | None = None
    provider: str | None = None
    model: str | None = None
    result: dict[str, Any] | str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class WorkflowRunProvenanceListResponse(BaseModel):
    """Response for a document's workflow provenance history."""

    document_id: str
    items: list[WorkflowRunProvenanceResponse]
    count: int


class PdfBackfillResponse(BaseModel):
    """Result of /pdfs/backfill-pages — how many PDFs needed pages
    created and how many pages were created in total.
    """

    pdfs_scanned: int
    pdfs_backfilled: int
    pages_created: int
    skipped: int


class DocumentCreate(BaseModel):
    """Request model for creating a document."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    parent_id: Optional[str] = None
    node_kind: Optional[str] = None
    doc_type: DocType = DocType.file
    file_type: Optional[FileType] = None
    path: Optional[str] = None
    page_content: Optional[str] = None
    metadata: dict = {}
    prototype_key: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_z: Optional[float] = None
    scale: Optional[float] = None
    z_index: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Request model for updating a document."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    parent_id: Optional[str] = None
    node_kind: Optional[str] = None
    doc_type: Optional[DocType] = None
    file_type: Optional[FileType] = None
    path: Optional[str] = None
    page_content: Optional[str] = None
    status: Optional[Status] = None
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    is_flagged: Optional[bool] = None
    exclude_from_processing: Optional[bool] = None
    metadata: Optional[dict] = None
    prototype_key: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    rotation_z: Optional[float] = None
    scale: Optional[float] = None
    z_index: Optional[int] = None


class DocumentBatchExcludeRequest(BaseModel):
    document_ids: list[str]
    excluded: bool
    reason: str | None = None


class DocumentBatchExcludeResponse(BaseModel):
    updated: int
    document_ids: list[str]


class PrototypeAssignRequest(BaseModel):
    prototype_key: str
    include_descendants: bool = False
    page_start: int | None = None
    page_end: int | None = None


class PrototypeAssignResponse(BaseModel):
    source_document_id: str
    prototype_key: str
    updated_count: int


class PageRangeItem(BaseModel):
    id: str | None = None
    name: str
    page_start: int
    page_end: int
    prototype_key: str | None = None


class PageRangeUpsertRequest(BaseModel):
    items: list[PageRangeItem]


class PageRangeListResponse(BaseModel):
    items: list[PageRangeItem]
    count: int


class DocumentNoteUpsert(BaseModel):
    """Request body for per-document note upsert."""

    content: str


class WorkspaceCuratedItem(BaseModel):
    id: str
    target_type: str
    target_id: str
    role: str | None = None
    added_at: str | None = None
    x: float | None = None
    y: float | None = None
    notes: str | None = None
    node_class: str | None = None


class WorkspacePatchRequest(BaseModel):
    add: list[WorkspaceCuratedItem] = []
    remove_ids: list[str] = []
    reorder_ids: list[str] | None = None


class WorkspaceItemsResponse(BaseModel):
    document_id: str
    items: list[dict[str, Any]]
    count: int


def _normalize_document_id(doc_id: str) -> str:
    """Accept both bare ids and ``doc:``-prefixed sidebar ids."""
    return doc_id.removeprefix("doc:")


def _is_document_deleted(doc: Document | None) -> bool:
    return bool(doc and doc.deleted_at is not None)


def _filter_document_visibility(
    docs: list[Document],
    *,
    include_deleted: bool = False,
    only_deleted: bool = False,
) -> list[Document]:
    if only_deleted:
        return [doc for doc in docs if _is_document_deleted(doc)]
    if include_deleted:
        return docs
    return [doc for doc in docs if not _is_document_deleted(doc)]


def _list_documents_raw(db: Database, **filters: Any) -> list[Document]:
    return list(db.query(Document, **filters)) if filters else list(db.all(Document))


def _list_documents(
    db: Database,
    *,
    include_deleted: bool = False,
    only_deleted: bool = False,
    **filters: Any,
) -> list[Document]:
    return _filter_document_visibility(
        _list_documents_raw(db, **filters),
        include_deleted=include_deleted,
        only_deleted=only_deleted,
    )


def _get_document_row(
    db: Database, doc_id: str, *, include_deleted: bool = False
) -> Document | None:
    normalized_id = _normalize_document_id(doc_id)
    doc = db.get(Document, normalized_id)
    if doc is None:
        return None
    if not include_deleted and _is_document_deleted(doc):
        return None
    return doc


def _document_or_404(
    db: Database, doc_id: str, *, include_deleted: bool = False
) -> Document:
    doc = _get_document_row(db, doc_id, include_deleted=include_deleted)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


def _filter_resolvable_documents(
    db: Database,
    docs: list[Document],
    *,
    parent_id: str | None = None,
) -> list[Document]:
    """Drop rows that no longer round-trip through ``GET /documents/{id}``.

    Browsing does a child-list fetch and then follows up with single-document
    and media requests. If a child id no longer resolves, omit it from the
    list response so the client never gets an id that immediately 404s.
    """
    if not docs:
        return []

    resolved = _filter_document_visibility(
        db.query_in(Document, "id", [doc.id for doc in docs])
    )
    resolved_ids = {doc.id for doc in resolved}
    resolvable: list[Document] = []
    skipped_ids: list[str] = []
    for doc in docs:
        if doc.id not in resolved_ids:
            skipped_ids.append(doc.id)
            continue
        resolvable.append(doc)
    if skipped_ids:
        logger.warning(
            "Skipping %d unresolvable child document(s) under %s: %s",
            len(skipped_ids),
            parent_id or "<unknown>",
            ", ".join(skipped_ids),
        )
    return resolvable


def _workspace_doc_or_404(db: Database, doc_id: str) -> Document:
    doc = _document_or_404(db, doc_id)
    if doc.doc_type != DocType.folder:
        raise HTTPException(status_code=400, detail="Document is not a folder")
    return doc


def _descendant_document_ids(
    db: Database, root_id: str, *, include_deleted: bool = True
) -> list[str]:
    stack = [root_id]
    descendants: list[str] = []
    while stack:
        current_id = stack.pop()
        descendants.append(current_id)
        children = _list_documents(
            db,
            parent_id=current_id,
            include_deleted=include_deleted,
        )
        stack.extend(child.id for child in children)
    return descendants


def _ordered_by_sort_order(docs: list[Document]) -> list[Document]:
    """Order documents by ``sort_order`` ASC, then ``name`` ASC (#572).

    The drag-drop reorder endpoint persists ``sort_order`` per document; list
    endpoints sort by it so the client doesn't have to re-sort and a dragged
    position survives a refresh. Reorder-unaware siblings tie at 0 and fall
    through to case-insensitive name order, preserving the old default.
    """
    return sorted(docs, key=lambda d: (d.sort_order, (d.name or "").lower()))


def _normalize_curated_items(items: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            logger.warning("workspace curated item is not an object: %r", item)
            continue
        item_id = str(item.get("id") or "").strip()
        target_type = str(item.get("target_type") or "").strip()
        target_id = str(item.get("target_id") or "").strip()
        if not item_id or not target_type or not target_id:
            logger.warning("workspace curated item missing required fields: %r", item)
            continue
        normalized.append(
            {
                "id": item_id,
                "target_type": target_type,
                "target_id": target_id,
                "role": item.get("role"),
                "added_at": item.get("added_at"),
                "x": item.get("x"),
                "y": item.get("y"),
                "notes": item.get("notes"),
                "node_class": item.get("node_class"),
            }
        )
    return normalized


def _resolve_workspace_item_target(db: Database, item: dict[str, Any]) -> Any:
    target_type = str(item.get("target_type") or "").strip().lower()
    target_id = str(item.get("target_id") or "").strip()
    if not target_id:
        return None
    model_by_type = {
        "document": Document,
        "entity": KnowledgeEntity,
        "claim": KnowledgeClaim,
        "note": Note,
        "annotation": Annotation,
        "citation": DocumentCitation,
    }
    model = model_by_type.get(target_type)
    if model is None:
        return None
    target = (
        _get_document_row(db, target_id)
        if model is Document
        else db.get(model, target_id)
    )
    return target.model_dump() if target is not None else None


# Routes


@router.get("")
async def list_documents(
    parent_id: Optional[str] = Query(None, description="Filter by parent ID"),
    doc_type: Optional[DocType] = Query(None, description="Filter by document type"),
    node_kind: Optional[str] = Query(None, description="Filter by node kind"),
    file_type: Optional[FileType] = Query(None, description="Filter by file type"),
    status: Optional[Status] = Query(None, description="Filter by status"),
    include_deleted: bool = Query(
        False, description="Include soft-deleted rows in the response"
    ),
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List documents with optional filters from the current library."""
    with perf_span(
        "library.list_documents",
        logger=logger,
        parent_id=parent_id,
        doc_type=doc_type.value if doc_type else None,
        node_kind=node_kind,
        file_type=file_type.value if file_type else None,
        status=status.value if status else None,
        limit=limit,
        offset=offset,
    ) as perf:
        filters = {}
        normalized_parent_id: str | None = None
        if parent_id is not None:
            normalized_parent_id = _normalize_document_id(parent_id)
            filters["parent_id"] = normalized_parent_id
        if doc_type is not None:
            filters["doc_type"] = doc_type
        if node_kind is not None:
            filters["node_kind"] = node_kind
        if file_type is not None:
            filters["file_type"] = file_type
        if status is not None:
            filters["status"] = status

        docs = _list_documents(db, include_deleted=include_deleted, **filters)

        if normalized_parent_id is not None:
            docs = _filter_resolvable_documents(
                db, docs, parent_id=normalized_parent_id
            )

        # Order by user-defined sort_order before paginating so drag-drop
        # positions survive a refresh and clients don't re-sort (#572).
        docs = _ordered_by_sort_order(docs)

        if limit is not None:
            items = docs[offset : offset + limit]
        else:
            items = docs[offset:]

        perf["matched_rows"] = len(docs)
        perf["returned_rows"] = len(items)
        perf["filters"] = ",".join(sorted(filters.keys())) or "none"
        return DocumentListResponse(items=items, count=len(items))


@router.get("/collections")
async def list_collections(
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List all root-level items (documents without parents)."""
    items = _ordered_by_sort_order(_list_documents(db, parent_id=None))
    return DocumentListResponse(items=items, count=len(items))


def _apply_listing_sort(
    items: list, sort_by: str | None, sort_direction: str
) -> list:
    """Optional server-side ordering for listing routes (#3322).

    Absent ``sort_by`` = exactly the pre-existing behaviour (sort_order),
    zero added work on the hot path. The ONLY server-side value is
    ``document_date``: its precision tie-breaking and created_at->JDN
    fallback live in ``histdate.document_date_sort_key`` — the same key
    Database.search uses, so search and the library can never order the
    same corpus differently. Client-computable orderings (name, size,
    import date) deliberately stay client-side; accepting them here would
    duplicate what the app already does. A wrong value is a loud 400, not
    a silent insertion-order list.
    """
    if sort_by is None:
        return items
    if sort_by != "document_date":
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid sort_by. Listing routes support only "
                "'document_date' (server-side historical-date ordering); "
                "other orderings are client-side."
            ),
        )
    if sort_direction not in ("asc", "desc"):
        raise HTTPException(
            status_code=400, detail="Invalid sort_direction. Must be 'asc' or 'desc'"
        )
    from fichero_server.histdate import document_date_sort_key

    # Stable sort: within equal (jdn, precision) keys the incoming
    # sort_order arrangement is preserved.
    return sorted(
        items, key=document_date_sort_key, reverse=(sort_direction == "desc")
    )


@router.get("/roots")
async def list_roots(
    db: Database = Depends(get_library_database),
    sort_by: Optional[str] = Query(
        None, description="Optional server-side ordering; only 'document_date'."
    ),
    sort_direction: str = Query("asc", description="'asc' or 'desc'"),
) -> DocumentListResponse:
    """List root documents (no parent)."""
    items = _ordered_by_sort_order(_list_documents(db, parent_id=None))
    items = _apply_listing_sort(items, sort_by, sort_direction)
    return DocumentListResponse(items=items, count=len(items))


@router.get("/workspaces")
async def list_workspaces(
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List document workspaces, excluding agent-session workspaces.

    Surfaces curated-items workspaces so the UI can show a "Workspaces" section
    and let the user open / create them (#1617). Declared before the `/{doc_id}`
    route so the literal path isn't captured as a document id.
    """
    items = _ordered_by_sort_order(
        document
        for document in _list_documents(db, is_workspace=True)
        if not isinstance(document.metadata, dict)
        or document.metadata.get("workspace_kind") != "agent"
    )
    return DocumentListResponse(items=items, count=len(items))


@router.get("/trash")
async def list_deleted_documents(
    db: Database = Depends(get_library_database),
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> DocumentListResponse:
    """List soft-deleted documents for the future Trash view."""
    docs = _ordered_by_sort_order(_list_documents(db, only_deleted=True))
    items = docs[offset : offset + limit] if limit is not None else docs[offset:]
    return DocumentListResponse(items=items, count=len(items))


@router.get("/{doc_id}")
async def get_document(
    doc_id: str, db: Database = Depends(get_library_database)
) -> Document:
    """Get a single document by ID."""
    return _document_or_404(db, doc_id)


class DocGeoPoint(BaseModel):
    """One geocoded point contributing to a document's map/globe view (#2266)."""

    lat: float
    lon: float
    place_name: str | None = None
    precision_m: float | None = None
    source: str  # "metadata" | "claim" | "place_value"


class DocGeoResponse(BaseModel):
    document_id: str
    points: list[DocGeoPoint]
    count: int


def _points_from_metadata(metadata: dict | None, *, place_default: str | None = None) -> list[DocGeoPoint]:
    """Pull geo points out of a document's metadata (geo_points list or flat lat/lon)."""
    points: list[DocGeoPoint] = []
    if not isinstance(metadata, dict):
        return points
    raw = metadata.get("geo_points")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                logger.warning("document geo_points entry is not an object: %r", item)
                continue
            lat, lon = item.get("lat"), item.get("lon")
            if lat is None or lon is None:
                logger.warning("document geo_points entry missing lat/lon: %r", item)
                continue
            try:
                points.append(
                    DocGeoPoint(
                        lat=float(lat),
                        lon=float(lon),
                        place_name=item.get("place_name") or place_default,
                        precision_m=item.get("precision_m"),
                        source="metadata",
                    )
                )
            except (TypeError, ValueError):
                logger.warning("document geo_points entry has invalid lat/lon: %r", item)
    # Legacy flat lat/lon (latitude/longitude or lat/lon) — one point per doc.
    lat = metadata.get("latitude", metadata.get("lat"))
    lon = metadata.get("longitude", metadata.get("lon"))
    if lat is not None and lon is not None:
        try:
            points.append(
                DocGeoPoint(
                    lat=float(lat),
                    lon=float(lon),
                    place_name=place_default,
                    source="metadata",
                )
            )
        except (TypeError, ValueError):
            logger.warning(
                "document legacy geo metadata has invalid lat/lon: %r",
                {"latitude": lat, "longitude": lon},
            )
    return points


@router.get(
    "/{doc_id}/geo",
    response_model=DocGeoResponse,
    summary="List geocoded points for a document",
)
async def list_document_geo(
    doc_id: str, db: Database = Depends(get_library_database)
) -> DocGeoResponse:
    """Aggregate a document's geo points for the world-map / globe representations.

    Sources, in order: the document's own ``metadata['geo_points']`` (written by
    the ``extract_geo`` tool #2266), its page children's metadata, and the
    ``claim_geo`` / ``place_values`` of knowledge claims sourced from this
    document. Duplicate coordinates collapse to one point.
    """
    doc = _document_or_404(db, doc_id)

    points: list[DocGeoPoint] = []
    points.extend(_points_from_metadata(doc.metadata, place_default=doc.name))
    points.extend(_points_from_metadata(doc.source_metadata, place_default=doc.name))

    for child in db.query(Document, parent_id=doc_id):
        points.extend(_points_from_metadata(child.metadata, place_default=child.name))

    for claim in db.query(KnowledgeClaim, source_document_id=doc_id):
        if claim.claim_geo is not None:
            points.append(
                DocGeoPoint(
                    lat=claim.claim_geo.lat,
                    lon=claim.claim_geo.lon,
                    place_name=claim.claim_geo.place_name or claim.claim_location,
                    precision_m=claim.claim_geo.precision_m,
                    source="claim",
                )
            )
        for place in claim.place_values:
            if place.lat is not None and place.lon is not None:
                points.append(
                    DocGeoPoint(
                        lat=place.lat,
                        lon=place.lon,
                        place_name=place.label,
                        precision_m=place.precision_m,
                        source="place_value",
                    )
                )

    # Collapse points that land on the same coordinate (6dp ≈ 0.1m).
    seen: set[tuple[float, float]] = set()
    unique: list[DocGeoPoint] = []
    for p in points:
        key = (round(p.lat, 6), round(p.lon, 6))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    return DocGeoResponse(document_id=doc_id, points=unique, count=len(unique))


@router.get(
    "/{doc_id}/workflow-runs",
    response_model=WorkflowRunProvenanceListResponse,
    summary="Get workflow provenance for a document",
)
async def get_document_workflow_runs(
    doc_id: str, db: Database = Depends(get_library_database)
) -> WorkflowRunProvenanceListResponse:
    """Return the recorded workflow runs for a single document."""
    doc = _document_or_404(db, doc_id)

    items: list[WorkflowRunProvenanceResponse] = []
    for index, run in enumerate(doc.workflow_runs):
        try:
            items.append(WorkflowRunProvenanceResponse.model_validate(run))
        except ValidationError as exc:
            logger.warning(
                "Skipping malformed workflow_runs[%d] for document %s: %s",
                index,
                doc_id,
                exc,
            )
    return WorkflowRunProvenanceListResponse(
        document_id=doc_id,
        items=items,
        count=len(items),
    )


@router.get("/{doc_id}/notes")
async def get_document_note(
    doc_id: str, db: Database = Depends(get_library_database)
) -> DocumentNote:
    """Get the user note for a document."""
    normalized_id = _normalize_document_id(doc_id)
    _document_or_404(db, normalized_id)

    notes = list(db.query(DocumentNote, document_id=normalized_id))
    if not notes:
        raise HTTPException(
            status_code=404, detail=f"Document note not found: {doc_id}"
        )
    return notes[0]


def put_document_note_impl(
    db: Database, doc_id: str, request: "DocumentNoteUpsert"
) -> DocumentNote:
    """Create or replace a document note using the synchronous DB layer."""
    normalized_id = _normalize_document_id(doc_id)
    _document_or_404(db, normalized_id)

    notes = list(db.query(DocumentNote, document_id=normalized_id))
    if notes:
        note = notes[0]
        note.content = request.content
        note.updated_at = utc_now()
    else:
        note = DocumentNote(document_id=normalized_id, content=request.content)

    db.save(note)
    return note


@router.put("/{doc_id}/notes")
async def put_document_note(
    doc_id: str,
    request: DocumentNoteUpsert,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> DocumentNote:
    """Create or replace a document's user note."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.note_upsert",
        {"doc_id": doc_id, "request": request.model_dump(mode="json")},
        ctx,
    )
    return DocumentNote.model_validate(result.result)


def delete_document_note_impl(db: Database, doc_id: str) -> str:
    """Delete a document note and return the normalized document id."""
    normalized_id = _normalize_document_id(doc_id)
    _document_or_404(db, normalized_id)

    notes = list(db.query(DocumentNote, document_id=normalized_id))
    if not notes:
        raise HTTPException(
            status_code=404, detail=f"Document note not found: {doc_id}"
        )
    db.delete(notes[0])
    return normalized_id


@router.delete("/{doc_id}/notes", status_code=204)
async def delete_document_note(
    doc_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> None:
    """Delete the user note for a document."""
    await _run_document_write(
        registry.invoke,
        db,
        "document.note_delete",
        {"doc_id": doc_id},
        ctx,
    )


@router.patch("/{doc_id}/workspace", response_model=WorkspaceItemsResponse)
async def patch_workspace_items(
    doc_id: str,
    request: WorkspacePatchRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> WorkspaceItemsResponse:
    """Atomically add/remove/reorder workspace curated items."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.patch_workspace",
        {"doc_id": doc_id, "patch": request.model_dump(mode="json")},
        ctx,
    )
    return WorkspaceItemsResponse.model_validate(result.result)


@router.get("/{doc_id}/workspace/items", response_model=WorkspaceItemsResponse)
async def get_workspace_items(
    doc_id: str,
    db: Database = Depends(get_library_database),
) -> WorkspaceItemsResponse:
    """List curated workspace items with alias resolution to full targets."""
    doc = _workspace_doc_or_404(db, doc_id)
    items = _normalize_curated_items(doc.curated_items)
    resolved = []
    for item in items:
        resolved.append(
            {
                **item,
                "target": _resolve_workspace_item_target(db, item),
            }
        )
    return WorkspaceItemsResponse(
        document_id=doc.id, items=resolved, count=len(resolved)
    )


@router.get("/{doc_id}/children")
async def get_children(
    doc_id: str,
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    sort_by: Optional[str] = Query(
        None, description="Optional server-side ordering; only 'document_date'."
    ),
    sort_direction: str = Query("asc", description="'asc' or 'desc'"),
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """Get child documents."""
    with perf_span(
        "library.get_children",
        logger=logger,
        doc_id=doc_id,
        limit=limit,
    ) as perf:
        # Callers (e.g. the catalogue workflow) sometimes pass a doc:-prefixed id
        # (e.g. "doc:abc123"). Documents are stored with bare hex ids, so strip
        # the prefix before every DB lookup so both forms resolve correctly (#1345).
        normalized_id = _normalize_document_id(doc_id)
        children = _filter_resolvable_documents(
            db,
            _list_documents(db, parent_id=normalized_id),
            parent_id=normalized_id,
        )
        children = _ordered_by_sort_order(children)
        children = _apply_listing_sort(children, sort_by, sort_direction)
        perf["normalized_id"] = normalized_id
        perf["matched_rows"] = len(children)

        if not children:
            # Verify parent exists only when there are no children to return.
            # During long-running workflows, a transient parent lookup miss can
            # race with reads; if children exist, prefer returning them over 404.
            parent = _get_document_row(db, normalized_id)
            perf["parent_found"] = parent is not None
            if not parent:
                raise HTTPException(
                    status_code=404, detail=f"Document not found: {doc_id}"
                )
        if limit is not None:
            children = children[:limit]
        perf["returned_rows"] = len(children)
        return DocumentListResponse(items=children, count=len(children))


@router.get("/{doc_id}/ancestors")
async def get_ancestors(
    doc_id: str, db: Database = Depends(get_library_database)
) -> DocumentListResponse:
    """Get all ancestors (parent chain) of a document."""
    ancestors = []
    current = _get_document_row(db, doc_id)

    if not current:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    while current and current.parent_id:
        parent = _get_document_row(db, current.parent_id)
        if parent:
            ancestors.append(parent)
            current = parent
        else:
            break

    return DocumentListResponse(items=ancestors, count=len(ancestors))


@router.get("/{doc_id}/parent")
async def get_document_parent(
    doc_id: str, db: Database = Depends(get_library_database)
) -> Document:
    """Get the immediate parent of a document."""
    doc = _get_document_row(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    if not doc.parent_id:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} has no parent")

    parent = _get_document_row(db, doc.parent_id)
    if not parent:
        raise HTTPException(
            status_code=404, detail=f"Parent document not found: {doc.parent_id}"
        )

    return parent


@router.post("", status_code=201)
async def create_document(
    doc: DocumentCreate,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Document:
    """Create a new document."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.create",
        doc.model_dump(mode="json"),
        ctx,
    )
    new_doc = Document.model_validate(result.result)
    logger.info(f"Created document: {new_doc.id} ({new_doc.name})")
    return new_doc


@router.put("/{doc_id}")
async def update_document(
    doc_id: str,
    update: DocumentUpdate,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Document:
    """Update an existing document."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.update",
        {"doc_id": doc_id, "update": update.model_dump(mode="json", exclude_unset=True)},
        ctx,
    )
    doc = Document.model_validate(result.result)
    logger.info(f"Updated document: {doc_id}")
    return doc


@router.get(
    "/{doc_id}/annotations.jsonld",
    summary="Export a document's annotations as W3C AnnotationPage",
)
async def export_document_annotations_jsonld(
    doc_id: str,
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    doc = _get_document_row(db, doc_id)
    return build_document_annotation_page(db, doc)


@router.patch("/batch-exclude", response_model=DocumentBatchExcludeResponse)
async def batch_exclude_documents(
    request: DocumentBatchExcludeRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> DocumentBatchExcludeResponse:
    """Toggle exclude-from-processing on multiple documents with audit logging."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.batch_exclude",
        request.model_dump(mode="json"),
        ctx,
    )
    return DocumentBatchExcludeResponse.model_validate(result.result)


def assign_document_prototype_impl(
    db: Database, doc_id: str, request: "PrototypeAssignRequest"
) -> tuple[PrototypeAssignResponse, list[str]]:
    """Assign a prototype key to a document scope using the synchronous DB layer."""
    _document_or_404(db, doc_id)
    if (
        request.page_start is not None
        and request.page_end is not None
        and request.page_start > request.page_end
    ):
        raise HTTPException(status_code=422, detail="page_start must be <= page_end")

    known_values = {
        v.key
        for v in db.query(ClassificationValue)
        if v.dimension
        in {
            ClassificationDimension.document_prototype,
            ClassificationDimension.node_class,
        }
    }
    if known_values and request.prototype_key not in known_values:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prototype key: {request.prototype_key}",
        )

    scoped_ids: set[str] = {doc_id}
    if request.include_descendants:
        frontier = [doc_id]
        while frontier:
            next_frontier: list[str] = []
            for parent_id in frontier:
                children = _list_documents(db, parent_id=parent_id) or []
                for child in children:
                    if child.id not in scoped_ids:
                        scoped_ids.add(child.id)
                        next_frontier.append(child.id)
            frontier = next_frontier

    updated = 0
    for candidate in _list_documents(db):
        if candidate.id not in scoped_ids:
            continue
        if request.page_start is not None or request.page_end is not None:
            if candidate.doc_type != DocType.page or candidate.sequence is None:
                continue
            if (
                request.page_start is not None
                and candidate.sequence < request.page_start
            ):
                continue
            if request.page_end is not None and candidate.sequence > request.page_end:
                continue
        candidate.prototype_key = request.prototype_key
        candidate.updated_at = utc_now()
        db.save(candidate)
        updated += 1

    return (
        PrototypeAssignResponse(
            source_document_id=doc_id,
            prototype_key=request.prototype_key,
            updated_count=updated,
        ),
        sorted(scoped_ids),
    )


@router.put("/{doc_id}/prototype", response_model=PrototypeAssignResponse)
async def assign_document_prototype(
    doc_id: str,
    request: PrototypeAssignRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PrototypeAssignResponse:
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.assign_prototype",
        {"doc_id": doc_id, "request": request.model_dump(mode="json")},
        ctx,
    )
    return PrototypeAssignResponse.model_validate(result.result)


@router.get("/{doc_id}/page-ranges", response_model=PageRangeListResponse)
async def list_page_ranges(
    doc_id: str, db: Database = Depends(get_library_database)
) -> PageRangeListResponse:
    doc = _document_or_404(db, doc_id)
    ranges = [PageRangeItem(**item) for item in (doc.structure or [])]
    return PageRangeListResponse(items=ranges, count=len(ranges))


def upsert_page_ranges_impl(
    db: Database, doc_id: str, request: "PageRangeUpsertRequest"
) -> PageRangeListResponse:
    """Persist document page ranges using the synchronous DB layer."""
    doc = _document_or_404(db, doc_id)
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(request.items):
        if item.page_start > item.page_end:
            raise HTTPException(
                status_code=422, detail="page_start must be <= page_end"
            )
        row = item.model_dump()
        row["id"] = row.get("id") or f"range-{idx + 1}"
        normalized.append(row)
    doc.structure = normalized
    doc.updated_at = utc_now()
    db.save(doc)
    return PageRangeListResponse(
        items=[PageRangeItem(**row) for row in normalized],
        count=len(normalized),
    )


@router.put("/{doc_id}/page-ranges", response_model=PageRangeListResponse)
async def upsert_page_ranges(
    doc_id: str,
    request: PageRangeUpsertRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PageRangeListResponse:
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.upsert_page_ranges",
        {"doc_id": doc_id, "request": request.model_dump(mode="json")},
        ctx,
    )
    return PageRangeListResponse.model_validate(result.result)


@router.get("/{doc_id}/page-ranges/at/{page}", response_model=PageRangeItem)
async def page_range_for_page(
    doc_id: str,
    page: int,
    db: Database = Depends(get_library_database),
) -> PageRangeItem:
    doc = _document_or_404(db, doc_id)
    for item in doc.structure or []:
        start = int(item.get("page_start", 0))
        end = int(item.get("page_end", 0))
        if start <= page <= end:
            return PageRangeItem(**item)
    raise HTTPException(status_code=404, detail=f"No page-range for page {page}")


def _cascade_delete_kg_rows(db: Database, doc_ids: set[str]) -> tuple[int, int]:
    """Delete KG claims sourced from any of ``doc_ids`` and prune entities
    left with no remaining claims.

    Without this, deleting a source document leaves orphaned
    ``KnowledgeClaim`` rows pointing at a ``source_document_id`` that
    404s, and ``KnowledgeEntity`` rows with nothing behind them (#1021).

    Every deletion is recorded as a ``MutationLog`` ``delete`` entry
    (``before_state`` = the full row), so it's reversible via the
    existing ``POST /api/kg/mutations/{id}/undo`` path.

    Returns ``(claims_deleted, entities_pruned)``.
    """
    from fichero_server.models.knowledge import (
        KnowledgeClaim,
        KnowledgeEntity,
        MutationLog,
        MutationOperationType,
    )

    all_claims = db.query(KnowledgeClaim)
    orphaned = [
        c
        for c in all_claims
        if c.source_document_id in doc_ids
        or any(sid in doc_ids for sid in (c.source_ids or []))
    ]
    if not orphaned:
        return (0, 0)

    orphaned_ids = {c.id for c in orphaned}
    touched_entity_ids: set[str] = set()
    for claim in orphaned:
        touched_entity_ids.update(claim.entity_ids or [])
        db.save(
            MutationLog(
                entity_type="KnowledgeClaim",
                entity_id=claim.id,
                operation=MutationOperationType.delete,
                before_state=claim.model_dump(mode="json"),
                after_state=None,
                created_by="cascade_delete_document",
            )
        )
        db.delete(claim)

    # Prune entities whose only claims were the ones we just deleted.
    # An entity referenced by a claim sourced from a *different* document
    # survives — we only drop the genuinely-orphaned ones.
    remaining_entity_ids: set[str] = set()
    for claim in all_claims:
        if claim.id in orphaned_ids:
            continue
        remaining_entity_ids.update(claim.entity_ids or [])

    entities_pruned = 0
    for entity_id in touched_entity_ids - remaining_entity_ids:
        entity = db.get(KnowledgeEntity, entity_id)
        if entity is None:
            continue
        db.save(
            MutationLog(
                entity_type="KnowledgeEntity",
                entity_id=entity.id,
                operation=MutationOperationType.delete,
                before_state=entity.model_dump(mode="json"),
                after_state=None,
                created_by="cascade_delete_document",
            )
        )
        db.delete(entity)
        entities_pruned += 1

    return (len(orphaned), entities_pruned)


def restore_document_subtree_impl(db: Database, doc_id: str) -> list[str]:
    """Restore a soft-deleted document subtree using the synchronous DB layer."""
    target = _document_or_404(db, doc_id, include_deleted=True)
    to_restore_ids = _descendant_document_ids(db, target.id, include_deleted=True)
    return restore_documents_impl(db, doc_ids=to_restore_ids)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
):
    """Soft-delete a document and all descendants."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.delete",
        {"doc_id": doc_id},
        ctx,
    )
    to_delete_ids = result.result["deleted_document_ids"]

    logger.info(
        "Soft-deleted document subtree: root=%s total=%s actor=%s",
        doc_id,
        len(to_delete_ids),
        ctx.actor,
    )


@router.post("/{doc_id}/restore", status_code=204)
async def restore_document(
    doc_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
):
    """Restore a soft-deleted document subtree."""
    await _run_document_write(
        registry.invoke,
        db,
        "document.restore",
        {"doc_id": doc_id},
        ctx,
    )


@router.delete("/{doc_id}/purge", status_code=204)
async def purge_document(
    doc_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
):
    """Permanently delete a document subtree."""
    to_delete_ids, claims_deleted, entities_pruned, _docs, _arts = (
        await _run_document_write(
            purge_document_impl, db, doc_id, library_path=ctx.library_path
        )
    )
    logger.info(
        "Purged document subtree: root=%s total=%s kg_claims_deleted=%s kg_entities_pruned=%s",
        doc_id,
        len(to_delete_ids),
        claims_deleted,
        entities_pruned,
    )
    _emit_document_change_ctx(
        ctx,
        event_type="document.deleted",
        document_ids=to_delete_ids,
    )


@router.get("/{doc_id}/related", response_model=RelatedDocumentListResponse)
async def related_documents(
    doc_id: str,
    limit: int = 20,
    db: Database = Depends(get_library_database),
) -> RelatedDocumentListResponse:
    """Documents related to this one, via two merged legs (#4120).

    Entity leg: aggregates entities across this doc's claims, then asks
    which OTHER docs have claims involving any of those same entities.
    Semantic leg: embedding neighbors of the doc's own stored vectors —
    works even before any knowledge extraction has run.

    Powers the 'Related' tab on the document inspector — useful for
    field notes and archival research where the user wants to follow
    a name or place across documents without manual searching.
    """
    _document_or_404(db, doc_id)

    import json as _json
    from collections import Counter

    # Step 1: gather distinct entity_ids from this doc's claims.
    try:
        raw_entity_id_values = db.knowledge_claim_entity_id_values(
            source_document_id=doc_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("related-documents claim lookup failed: %s", exc)
        raw_entity_id_values = []

    seed_entity_ids: set[str] = set()
    for raw in raw_entity_id_values:
        if not raw:
            continue
        try:
            ids = _json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            logger.warning(
                "related-documents malformed entity_ids payload for %s: %r",
                doc_id,
                raw,
            )
            continue
        if isinstance(ids, list):
            for eid in ids:
                if isinstance(eid, str) and eid:
                    seed_entity_ids.add(eid)

    # Step 2: find docs whose claims reference ANY of those entities.
    # JSON-LIKE per-id is fine at this scale; for large entity sets we
    # could batch into a single regex but that's premature.
    counter: Counter[str] = Counter()
    sample_per_doc: dict[str, set[str]] = {}
    for entity_id in seed_entity_ids:
        try:
            related_doc_ids = db.knowledge_claim_source_document_ids_for_entity(
                entity_id
            )
        except Exception:
            continue
        seen_ids_for_entity: set[str] = set()
        for other_doc_id in related_doc_ids:
            if (
                not other_doc_id
                or other_doc_id == doc_id
                or other_doc_id in seen_ids_for_entity
            ):
                continue
            seen_ids_for_entity.add(other_doc_id)
            counter[other_doc_id] += 1
            sample_per_doc.setdefault(other_doc_id, set()).add(entity_id)

    # Step 3: semantic neighbors from the doc's own stored embeddings —
    # the leg that works before any claims exist. Failure degrades to the
    # entity leg (logged), never a 500: relatedness is best-effort context.
    similarity_by_doc: dict[str, float] = {}
    try:
        similarity_by_doc = dict(db.semantic_related_documents(doc_id, limit=limit))
    except Exception as exc:  # noqa: BLE001
        logger.warning("related-documents semantic lookup failed: %s", exc)

    if not counter and not similarity_by_doc:
        return RelatedDocumentListResponse(items=[], count=0)

    # Merge: cosine similarity is [0, 1]; each shared entity adds 0.05
    # (capped at 5) so both signals stack without either drowning the
    # other. ponytail: heuristic weights — tune when #4119 calibration lands.
    def _combined(other_id: str) -> float:
        return similarity_by_doc.get(other_id, 0.0) + 0.05 * min(
            counter.get(other_id, 0), 5
        )

    candidate_ids = set(counter) | set(similarity_by_doc)
    top_ids = sorted(candidate_ids, key=_combined, reverse=True)[:limit]
    out: list[RelatedDocumentsResponse] = []
    for other_id in top_ids:
        overlap_count = counter.get(other_id, 0)
        other = _get_document_row(db, other_id)
        if other is None:
            continue
        # Resolve up to 3 sample entity names per related doc.
        sample_names: list[str] = []
        for sample_eid in list(sample_per_doc.get(other_id, set()))[:3]:
            try:
                name = db.knowledge_entity_canonical_name(sample_eid)
            except Exception:
                name = None
            if name:
                sample_names.append(name)
        doc_type_str = (
            other.doc_type.value
            if hasattr(other.doc_type, "value")
            else (str(other.doc_type) if other.doc_type else None)
        )
        file_type_str = (
            other.file_type.value
            if hasattr(other.file_type, "value") and other.file_type
            else (str(other.file_type) if other.file_type else None)
        )
        out.append(
            RelatedDocumentsResponse(
                document_id=other_id,
                name=other.name,
                doc_type=doc_type_str,
                file_type=file_type_str,
                shared_entities=overlap_count,
                sample_entity_names=sample_names,
                similarity=similarity_by_doc.get(other_id),
            )
        )
    return RelatedDocumentListResponse(items=out, count=len(out))


def backfill_pdf_pages_impl(db: Database) -> tuple[PdfBackfillResponse, list[str]]:
    """Create missing PDF page documents using the synchronous ingest helpers."""
    from fichero_server.importers.ingest import _create_pdf_page_children

    pdfs = _list_documents(db, file_type=FileType.pdf)
    pdfs_scanned = len(pdfs)
    pdfs_backfilled = 0
    pages_created = 0
    skipped = 0
    created_page_ids: list[str] = []

    for pdf in pdfs:
        if not pdf.path:
            skipped += 1
            continue
        try:
            existing_pages = _list_documents(db, parent_id=pdf.id, doc_type=DocType.page)
        except Exception:
            existing_pages = []
        if existing_pages:
            continue
        path = Path(pdf.path)
        if not path.exists():
            skipped += 1
            continue
        try:
            new_pages = _create_pdf_page_children(pdf, path, db, auto_embed=True)
            if new_pages:
                pdfs_backfilled += 1
                pages_created += len(new_pages)
                created_page_ids.extend([page.id for page in new_pages if page.id])
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF backfill failed for %s: %s", pdf.id, exc)
            skipped += 1

    return (
        PdfBackfillResponse(
            pdfs_scanned=pdfs_scanned,
            pdfs_backfilled=pdfs_backfilled,
            pages_created=pages_created,
            skipped=skipped,
        ),
        created_page_ids,
    )


@router.post("/pdfs/backfill-pages")
async def backfill_pdf_pages(
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> PdfBackfillResponse:
    """Find PDFs without page children and create the page Documents.

    This affects PDFs ingested before _create_pdf_page_children
    landed (or where Kreuzberg silently failed at ingest time): the
    sidebar shows the PDF as a leaf with no expandable child pages.

    For each PDF in the library, check whether it already has child
    documents with doc_type=page. If not, run the same _create_pdf_page_children
    helper that ingest uses now. Idempotent — re-running on a fully
    backfilled library is a no-op.
    """
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.backfill_pdf_pages",
        {},
        ctx,
    )
    return PdfBackfillResponse.model_validate(result.result)


@router.post("/reorder")
async def reorder_documents(
    doc_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> ReorderResponse:
    """Reorder documents within a folder."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.reorder",
        {"doc_ids": doc_ids, "folder_path": folder_path},
        ctx,
    )
    return ReorderResponse.model_validate(result.result)


def import_uploaded_file_impl(
    db: Database,
    file_path: Path,
    *,
    original_filename: str | None = None,
    parent_id: str | None = None,
) -> Document:
    """Ingest a file already on disk (COPY mode) and create a Document.

    Extracted from the ``POST /import`` route so the route and the
    ``import.upload_file`` action share the SAME ingest + filename-preservation
    logic (iterate-not-replace, EPIC #1848 / #2014). The caller owns the file's
    lifecycle — the route writes+cleans a multipart temp file; the action is
    handed a server-side path it does not delete.
    """
    from fichero_server.importers.ingest import ingest_file, IngestMode

    # Get library package path from database path.
    # db.path is like /path/to/Library.fichero/fichero.duckdb
    # package_path should be /path/to/Library.fichero
    package_path = Path(db.path).parent

    # Ingest the file (copies to library storage and saves to database).
    # original_filename rides INTO ingest (#4471), not as a post-hoc rename:
    # the old #1104 fixup renamed only the parent AFTER page children were
    # created, so every page kept "fichero_upload_<random>.pdf - Page N" and
    # metadata recorded the server temp dir as source_path — provenance loss
    # on an archival corpus. Inside ingest, the real name lands before pages
    # are named and the temp path is never recorded as a source.
    doc = ingest_file(
        path=file_path,
        mode=IngestMode.COPY,  # Copy file into library
        parent_id=parent_id,
        extract_metadata=True,  # Extract file metadata
        extract_text=True,  # Extract text for search
        save=True,  # Save to database
        db=db,  # Database instance
        package_path=package_path,  # Library package path
        original_filename=original_filename,
    )

    logger.info(f"Imported document: {doc.id} ({doc.name})")
    return doc


@router.post("/import")
async def import_file(
    request: Request,
    file: UploadFile,
    parent_id: Optional[str] = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Document:
    """Import a file and create a document."""
    from fichero_server.db.storage import UploadTooLargeError, save_uploaded_file

    temp_path: Path | None = None

    try:
        # Save the uploaded file to temp location
        temp_path = await save_uploaded_file(
            file,
            content_length=request.headers.get("content-length"),
        )
        result = await asyncio.to_thread(
            registry.invoke,
            db,
            "import.upload_file",
            {
                "path": str(temp_path),
                "original_filename": file.filename,
                "parent_id": parent_id,
            },
            ctx,
        )
        return Document.model_validate(result.result)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    finally:
        # Clean up temp file
        if temp_path is not None:
            try:
                temp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_path}: {e}")


@router.put("/{doc_id}/move")
async def move_document(
    doc_id: str,
    parent_id: Optional[str] = Query(None),
    request: Request = None,
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Document:
    """Move a document to a new parent location.

    Accepts parent_id as either a query parameter or in the request body for flexibility.
    """
    if request is not None:
        unexpected_query_keys = sorted(set(request.query_params.keys()) - {"parent_id"})
        if unexpected_query_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Unexpected query parameter(s): {', '.join(unexpected_query_keys)}",
            )
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.move",
        {"doc_id": doc_id, "parent_id": parent_id},
        ctx,
    )
    doc = Document.model_validate(result.result)
    logger.info(f"Moved document: {doc_id} to parent: {parent_id}")

    return doc


@router.post("/{doc_id}/duplicate")
async def duplicate_document(
    doc_id: str,
    parent_id: Optional[str] = Query(None),
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> Document:
    """Deep-copy a document (subtree included) — beside the original, or
    into ``parent_id`` when given (Option-drag copy)."""
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.duplicate",
        {"doc_id": doc_id, "parent_id": parent_id},
        ctx,
    )
    doc = Document.model_validate(result.result)
    logger.info(f"Duplicated document: {doc_id} -> {doc.id}")
    return doc


def cleanup_orphan_documents_impl(
    db: Database, *, library_path: str
) -> tuple[OrphanCleanupResponse, list[str]]:
    """Remove unreachable document rows using the synchronous DB layer."""
    all_docs = _list_documents(db)
    if not all_docs:
        return OrphanCleanupResponse(orphaned_documents_deleted=0, artifacts_deleted=0), []

    docs_by_parent: dict[str | None, list[Document]] = {}
    for item in all_docs:
        docs_by_parent.setdefault(item.parent_id, []).append(item)

    reachable: set[str] = set()
    stack = [item.id for item in docs_by_parent.get(None, [])]

    while stack:
        doc_id = stack.pop()
        if doc_id in reachable:
            continue
        reachable.add(doc_id)
        for child in docs_by_parent.get(doc_id, []):
            stack.append(child.id)

    orphaned = [item for item in all_docs if item.id not in reachable]
    artifacts_deleted = 0

    if orphaned:
        auto_snapshot_before_risky_operation(
            library_path,
            reason=f"Before cleanup of {len(orphaned)} orphan document(s)",
        )

    for orphan in orphaned:
        artifacts = db.query(Artifact, document_id=orphan.id)
        artifacts_deleted += len(artifacts)
        for artifact in artifacts:
            db.delete(artifact)
        db.delete_embedding(orphan.id)
        db.delete(orphan)

    if orphaned:
        logger.info(
            "Cleanup removed %s orphan documents and %s artifacts",
            len(orphaned),
            artifacts_deleted,
        )

    return (
        OrphanCleanupResponse(
            orphaned_documents_deleted=len(orphaned),
            artifacts_deleted=artifacts_deleted,
        ),
        [item.id for item in orphaned],
    )


@router.post("/cleanup-orphans")
async def cleanup_orphan_documents(
    db: Database = Depends(get_library_database_for_write),
    ctx: "ActionContext" = Depends(action_context),
) -> OrphanCleanupResponse:
    """Remove unreachable/orphan document rows.

    A document is considered orphaned when it is not reachable from any root
    document (parent_id is None). This catches records left behind by past
    non-cascading deletes and malformed parent chains.
    """
    result = await _run_document_write(
        registry.invoke,
        db,
        "document.cleanup_orphans",
        {},
        ctx,
    )
    return OrphanCleanupResponse.model_validate(result.result)


# =============================================================================
# Document mutation impls — the proven business logic, extracted so BOTH the
# route handler and the audited action (EPIC #1848 / #2014) drive the SAME code
# (iterate-not-replace: wrapped, never re-derived). Emission to the observable
# layer stays with the caller (route OR registry.invoke). Each raises
# HTTPException on bad input exactly as the route did.
# =============================================================================


def create_document_impl(db: Database, doc: "DocumentCreate") -> Document:
    """Create + persist a new document (validating the parent if specified)."""
    try:
        validate_stored_document_path(
            doc.path,
            Path(db.path).parent,
            storage_base=storage_settings.base_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    new_doc = Document(
        name=doc.name,
        parent_id=doc.parent_id,
        node_kind=doc.node_kind,
        doc_type=doc.doc_type,
        file_type=doc.file_type,
        path=doc.path,
        page_content=doc.page_content,
        metadata=doc.metadata,
        prototype_key=doc.prototype_key,
        position_x=doc.position_x,
        position_y=doc.position_y,
        position_z=doc.position_z,
        rotation_z=doc.rotation_z,
        scale=doc.scale,
        z_index=doc.z_index or 0,
    )
    if doc.parent_id:
        parent = _get_document_row(db, doc.parent_id)
        if not parent:
            raise HTTPException(
                status_code=400, detail=f"Parent not found: {doc.parent_id}"
            )
    db.save(new_doc)
    return new_doc


def update_document_impl(
    db: Database, doc_id: str, update: "DocumentUpdate"
) -> tuple[Document, dict[str, Any], list[str]]:
    """Apply a partial update to a document.

    Returns ``(doc, before_snapshot, changed_fields)``. ``before_snapshot`` is
    the full pre-mutation row — the undo payload the action inverts to
    ``document.restore``.
    """
    doc = _document_or_404(db, doc_id)
    _reject_if_document_read_only(doc, "edited")

    before = doc.model_dump(mode="json")

    # Apply updates
    # exclude_unset filters fields the client didn't provide. exclude_none
    # ALSO filters fields the client sent as JSON null. The Swift OpenAPI
    # client serializes every optional argument as a JSON null when the
    # caller omits it — so a routine page_content edit arrives here as
    # `{page_content: "...", name: null, parent_id: null, ...}`. Without
    # exclude_none, those nulls would clobber existing values. Combined,
    # the only fields that mutate are ones the client explicitly set to a
    # non-null value. (#774 + audit on 2026-05-03.)
    update_data = update.model_dump(exclude_unset=True, exclude_none=True)
    if "path" in update_data:
        try:
            validate_stored_document_path(
                update_data.get("path"),
                Path(db.path).parent,
                storage_base=storage_settings.base_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # parent_id is NEVER mutated by this endpoint even if the client sends
    # a non-null value — reparenting must go through the dedicated
    # PUT /api/documents/{doc_id}/move endpoint to keep hierarchy mutations
    # explicit and auditable.
    update_data.pop("parent_id", None)

    # Mark user edits to page_content BEFORE applying field updates, so
    # downstream workflows (transcription, etc.) can detect and avoid
    # silently overwriting what the user typed. Stored in metadata so no
    # schema migration is needed. See issue #672.
    if "page_content" in update_data:
        existing_metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
        incoming_metadata = update_data.get("metadata")
        if isinstance(incoming_metadata, dict):
            merged_metadata = {**existing_metadata, **incoming_metadata}
        else:
            merged_metadata = dict(existing_metadata)
        merged_metadata["page_content_user_edited_at"] = utc_now().isoformat()
        update_data["metadata"] = merged_metadata

    for field, value in update_data.items():
        setattr(doc, field, value)

    # Update timestamp
    doc.updated_at = utc_now()

    db.save(doc)

    # Re-embed when page_content changed so search reflects the user's
    # edit immediately. Without this, the stale embedding from before the
    # edit stays in LanceDB until a manual reindex — and search returns
    # the *old* content as if the edit never happened. (#481 follow-up)
    if "page_content" in update_data and doc.page_content:
        try:
            db.embed(doc)
            logger.info(f"Re-embedded {doc_id} after page_content edit")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Re-embed after edit failed for {doc_id}: {exc}")

    return doc, before, list(update_data.keys())


def _reject_if_document_read_only(doc: Document, operation: str) -> None:
    """Raise 403 when ``doc`` is a locked node (#11 Phase 1 enforcement).

    The Default Workflows container and its preset mirrors carry
    ``attributes.read_only=True`` (see ``Database._save_workflow_document``).
    The workflow routes already enforce this via ``_reject_if_read_only``;
    this closes the document-tree side, where move/rename/delete previously
    succeeded — a moved container even persisted across reopens. Seeding
    itself uses ``db.save`` directly, so re-seeds are unaffected.
    """
    attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
    if attrs.get("read_only"):
        raise HTTPException(
            status_code=403,
            detail=f"{doc.name or doc.id} is read-only and cannot be {operation}",
        )


def _move_would_create_cycle(db: Database, doc_id: str, parent_id: str) -> bool:
    """True when re-parenting ``doc_id`` under ``parent_id`` forms a cycle.

    Walks the target parent's ancestor chain; if ``doc_id`` appears, the target
    sits inside the document being moved and the move would detach the subtree
    from the root — after which orphan cleanup would silently delete it. The
    walk is bounded so a pre-existing malformed (cyclic) chain terminates.
    """
    current: str | None = parent_id
    guard = 0
    while current is not None and guard <= 10_000:
        if current == doc_id:
            return True
        row = _get_document_row(db, current)
        current = row.parent_id if row is not None else None
        guard += 1
    return False


def move_document_impl(
    db: Database, doc_id: str, parent_id: str | None
) -> tuple[Document, dict[str, Any]]:
    """Re-parent a document. Returns ``(doc, before_snapshot)``."""
    doc = _document_or_404(db, doc_id)
    _reject_if_document_read_only(doc, "moved")

    # Verify new parent exists if specified
    if parent_id:
        parent = _get_document_row(db, parent_id)
        if not parent:
            raise HTTPException(
                status_code=400, detail=f"Parent not found: {parent_id}"
            )
        # Locked containers don't accept new children either — nothing may
        # be filed into Default Workflows except the seeder (db.save path).
        _reject_if_document_read_only(parent, "added to")
        # Reject self/descendant parents: the UI's SidebarMovePolicy guards
        # its own drags, but the API must hold the no-cycle invariant for
        # every client — a cycled subtree becomes unreachable and orphan
        # cleanup then deletes it.
        if _move_would_create_cycle(db, doc_id, parent_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot move {doc_id} into itself or its own descendant "
                    f"({parent_id})"
                ),
            )

    before = doc.model_dump(mode="json")
    doc.parent_id = parent_id
    doc.updated_at = utc_now()
    db.save(doc)
    return doc, before


def duplicate_document_impl(
    db: Database,
    doc_id: str,
    parent_id: str | None = None,
    to_root: bool = False,
) -> tuple[Document, list[str]]:
    """Deep-copy a document subtree. Returns ``(root copy, all new ids)``.

    Finder semantics: with no ``parent_id`` the root copy lands beside the
    original named "<name> copy"; with a ``parent_id`` (Option-drag copy) it
    lands in that folder keeping its name — Finder only suffixes same-folder
    copies. Descendants keep their names. Copies get fresh ids and
    timestamps; ``page_content``/metadata/attributes ride along, but derived
    artifact rows are NOT copied (they regenerate on demand) and copies are
    not re-embedded here — a reindex covers search. Locked nodes (Default
    Workflows container/mirrors) refuse — duplicate the workflow via the
    workflow route instead — and locked targets accept no copies.
    """
    src = _document_or_404(db, doc_id)
    _reject_if_document_read_only(src, "duplicated")

    if parent_id is not None:
        parent = _get_document_row(db, parent_id)
        if not parent:
            raise HTTPException(
                status_code=400, detail=f"Parent not found: {parent_id}"
            )
        _reject_if_document_read_only(parent, "added to")
        # A target inside the source subtree would make the recursion copy
        # its own output (runaway growth) — same ancestor walk as move.
        if _move_would_create_cycle(db, doc_id, parent_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot copy {doc_id} into itself or its own descendant "
                    f"({parent_id})"
                ),
            )

    # ``parent_id=None`` is ambiguous between "beside the original" and
    # "into the library root" — ``to_root`` disambiguates (Option-drop on a
    # root insertion line copies to root explicitly).
    if to_root:
        target_parent_id: str | None = None
    elif parent_id is not None:
        target_parent_id = parent_id
    else:
        target_parent_id = src.parent_id
    lands_beside_original = target_parent_id == src.parent_id
    root_name = f"{src.name} copy" if lands_beside_original else src.name

    new_ids: list[str] = []

    def copy_one(node: Document, parent_id: str | None, name: str | None) -> Document:
        data = node.model_dump(mode="json")
        for field in ("id", "created_at", "updated_at"):
            data.pop(field, None)
        dup = Document(**data)
        dup.parent_id = parent_id
        if name is not None:
            dup.name = name
        now = utc_now()
        dup.created_at = now
        dup.updated_at = now
        db.save(dup)
        new_ids.append(dup.id)
        return dup

    # Iterative walk (explicit stack): a pathologically deep tree must not
    # blow Python's recursion limit mid-copy and strand partial rows
    # (review suggestion). Order within a level doesn't matter — children
    # keep their own sort_order values.
    root_copy = copy_one(src, target_parent_id, root_name)
    stack: list[tuple[str, str]] = [(src.id, root_copy.id)]
    while stack:
        source_id, copy_parent_id = stack.pop()
        for child in _list_documents(db, parent_id=source_id, include_deleted=False):
            child_copy = copy_one(child, copy_parent_id, None)
            stack.append((child.id, child_copy.id))
    return root_copy, new_ids


def reorder_documents_impl(
    db: Database, doc_ids: list[str], folder_path: str = "/"
) -> list[dict[str, Any]]:
    """Persist ``sort_order`` per document by list position.

    Returns the pre-mutation snapshots (in input order) so undo can restore the
    exact prior ``sort_order`` values — re-running reorder with the old list is
    NOT a faithful inverse because it re-bases every value to ``0..n-1`` and
    loses any prior non-contiguous ordering.
    """
    before_snapshots: list[dict[str, Any]] = []
    for i, doc_id in enumerate(doc_ids):
        doc = _document_or_404(db, doc_id)

        # For now, only update documents in the specified folder path
        # In a more complex system, we'd verify the document is in the right folder
        before_snapshots.append(doc.model_dump(mode="json"))
        doc.sort_order = i
        db.save(doc)
    return before_snapshots


def patch_workspace_items_impl(
    db: Database, doc_id: str, request: "WorkspacePatchRequest"
) -> tuple[Document, dict[str, Any]]:
    """Atomically add/remove/reorder workspace curated items.

    Returns ``(doc, before_snapshot)``. The before-snapshot is the full
    pre-mutation document so undo restores the prior ``curated_items`` exactly.
    """
    doc = _workspace_doc_or_404(db, doc_id)
    before = doc.model_dump(mode="json")
    current_items = _normalize_curated_items(doc.curated_items)
    by_id = {item["id"]: item for item in current_items}

    for remove_id in request.remove_ids:
        by_id.pop(remove_id, None)

    now_iso = utc_now().isoformat()
    for incoming in request.add:
        payload = incoming.model_dump()
        payload["added_at"] = payload.get("added_at") or now_iso
        by_id[payload["id"]] = payload

    ordered_ids: list[str]
    if request.reorder_ids is not None:
        seen = set()
        ordered_ids = []
        for item_id in request.reorder_ids:
            if item_id in by_id and item_id not in seen:
                ordered_ids.append(item_id)
                seen.add(item_id)
        for item in current_items:
            item_id = item["id"]
            if item_id in by_id and item_id not in seen:
                ordered_ids.append(item_id)
                seen.add(item_id)
        for item_id in by_id:
            if item_id not in seen:
                ordered_ids.append(item_id)
                seen.add(item_id)
    else:
        ordered_ids = [item["id"] for item in current_items if item["id"] in by_id]
        for item_id in by_id:
            if item_id not in ordered_ids:
                ordered_ids.append(item_id)

    doc.is_workspace = True
    doc.curated_items = [by_id[item_id] for item_id in ordered_ids]
    doc.updated_at = utc_now()
    db.save(doc)
    return doc, before


def batch_exclude_documents_impl(
    db: Database, request: "DocumentBatchExcludeRequest"
) -> tuple[list[str], list[dict[str, Any]]]:
    """Toggle exclude-from-processing on multiple documents.

    Returns ``(updated_ids, before_snapshots)``. De-duplicates input ids; raises
    404 on the first unknown id (matching the route). Writes a per-document
    ``MutationLog`` row as before, and returns before-snapshots for action undo.
    """
    seen: set[str] = set()
    updated_ids: list[str] = []
    before_snapshots: list[dict[str, Any]] = []
    for document_id in request.document_ids:
        normalized_id = str(document_id).strip()
        if not normalized_id or normalized_id in seen:
            continue
        seen.add(normalized_id)

        doc = _document_or_404(db, normalized_id)

        before = doc.model_dump(mode="json")
        before_snapshots.append(before)
        doc.exclude_from_processing = request.excluded
        doc.updated_at = utc_now()
        db.save(doc)
        db.save(
            MutationLog(
                entity_type="Document",
                entity_id=doc.id,
                operation=MutationOperationType.update,
                before_state=before,
                after_state=doc.model_dump(mode="json"),
                changed_fields=["exclude_from_processing"],
                created_by=request.reason or "batch_exclude_documents",
            )
        )
        updated_ids.append(doc.id)
    return updated_ids, before_snapshots


def delete_document_impl(
    db: Database, doc_id: str, *, actor: str
) -> tuple[list[str], list[dict[str, Any]]]:
    """Soft-delete a document subtree, preserving rows for trash / restore."""
    doc = _document_or_404(db, doc_id)
    # 403 (not a silent skip): a delete aimed at a locked node — the Default
    # Workflows container or a preset mirror — must fail loudly. Deleting the
    # container would soft-delete every mirror inside it in one call.
    _reject_if_document_read_only(doc, "deleted")
    to_delete_ids = _descendant_document_ids(db, doc.id, include_deleted=True)

    deleted_at = utc_now()
    before_snapshots: list[dict[str, Any]] = []
    for current_id in to_delete_ids:
        current_doc = _get_document_row(db, current_id, include_deleted=True)
        if current_doc is None:
            continue
        before_snapshots.append(current_doc.model_dump(mode="json"))
        current_doc.deleted_at = deleted_at
        current_doc.deleted_by = actor
        current_doc.updated_at = deleted_at
        db.save(current_doc)

    return to_delete_ids, before_snapshots


def purge_document_impl(
    db: Database, doc_id: str, *, library_path: str | None = None
) -> tuple[list[str], int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Hard-delete a document + all descendants, returning everything undo needs.

    Returns ``(to_delete_ids, claims_deleted, entities_pruned, document_snapshots,
    artifact_snapshots)``. The document + artifact snapshots are captured BEFORE
    deletion so the audited action can invert to ``document.restore``. The KG
    cascade keeps its own ``MutationLog`` reversal (``POST /api/kg/mutations/
    {id}/undo``) — ``document.restore`` deliberately restores only the document
    + artifact rows, leaving the (separately-reversible) KG cascade alone so the
    two undo mechanisms never double-restore.
    """
    doc = _document_or_404(db, doc_id, include_deleted=True)
    to_delete_ids = _descendant_document_ids(db, doc.id, include_deleted=True)

    if library_path:
        auto_snapshot_before_risky_operation(
            library_path,
            reason=(
                f"Before deleting document subtree {doc_id} "
                f"({len(to_delete_ids)} document(s))"
            ),
        )

    # Snapshot documents BEFORE deletion so undo can restore them verbatim.
    document_snapshots: list[dict[str, Any]] = []
    for current_id in to_delete_ids:
        snap_doc = _get_document_row(db, current_id, include_deleted=True)
        if snap_doc is not None:
            document_snapshots.append(snap_doc.model_dump(mode="json"))

    artifact_snapshots: list[dict[str, Any]] = []
    for current_id in to_delete_ids:
        artifacts = db.query(Artifact, document_id=current_id)
        for artifact in artifacts:
            artifact_snapshots.append(artifact.model_dump(mode="json"))
            db.delete(artifact)
        db.delete_embedding(current_id)

    # Cascade KG cleanup before the documents go — claims reference docs
    # by id string, so order doesn't matter, but doing it here keeps the
    # teardown in one place.
    claims_deleted, entities_pruned = _cascade_delete_kg_rows(db, set(to_delete_ids))

    # Delete children first for clean hierarchical teardown.
    for current_id in reversed(to_delete_ids):
        current_doc = _get_document_row(db, current_id, include_deleted=True)
        if current_doc:
            db.delete(current_doc)

    return (
        to_delete_ids,
        claims_deleted,
        entities_pruned,
        document_snapshots,
        artifact_snapshots,
    )


def restore_documents_impl(
    db: Database,
    *,
    doc_ids: list[str] | None = None,
    documents: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Restore soft-deleted docs by id, or re-create rows from snapshots.

    The single inverse used by every undoable document action: it reuses the
    proven ``model_validate`` round-trip so undo restores the exact pre-mutation
    rows rather than re-deriving a field diff.
    """
    restored_ids: list[str] = []
    seen_doc_ids: set[str] = set()

    for document_id in doc_ids or []:
        doc = _get_document_row(db, document_id, include_deleted=True)
        if doc is None:
            continue
        doc.deleted_at = None
        doc.deleted_by = None
        doc.updated_at = utc_now()
        db.save(doc)
        restored_ids.append(doc.id)
        seen_doc_ids.add(doc.id)

    for snapshot in documents or []:
        restored = Document.model_validate(snapshot)
        db.save(restored)
        if restored.id not in seen_doc_ids:
            restored_ids.append(restored.id)
            seen_doc_ids.add(restored.id)
    for snapshot in artifacts or []:
        db.save(Artifact.model_validate(snapshot))
    return restored_ids


# =============================================================================
# Action layer registration (EPIC #1848 / #2014) — DOCUMENT domain sweep
# =============================================================================
#
# Each action WRAPS the proven ``*_impl`` above (iterate-not-replace) and routes
# through ``registry.invoke`` so chat tools / App Intents / tests / the audit
# log all drive the SAME code the UI routes do (the routes call the same
# ``*_impl`` directly and emit), matching the entity.merge / claim.* pattern.
#
# Undo is data, not code: ``ChangeSpec.before/after`` becomes the ActionAudit
# undo payload, and every undoable verb inverts to ``document.restore`` (or
# ``document.delete`` for create). The inverse chain:
#   * document.create          -> document.delete
#   * document.update          -> document.restore (before snapshot)
#   * document.move            -> document.restore (before snapshot)
#   * document.reorder         -> document.restore (prior sort_order snapshots)
#   * document.patch_workspace -> document.restore (before snapshot)
#   * document.batch_exclude   -> document.restore (before snapshots)
#   * document.delete          -> document.restore (doc + artifact snapshots)

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


class DocumentUpdateActionParams(BaseModel):
    """Params for document.update — the path doc_id + the partial update body.

    ``update`` is a nested :class:`DocumentUpdate` so the registry's
    ``model_validate`` preserves exclude-unset semantics: only fields actually
    present are applied.
    """

    doc_id: str = Field(description="Document id to update")
    update: DocumentUpdate = Field(description="Partial document update")


class DocumentDeleteParams(BaseModel):
    """Params for document.delete — also the inverse of document.create."""

    doc_id: str = Field(description="Document id to delete (cascades to subtree)")


class DocumentMoveParams(BaseModel):
    """Params for document.move."""

    doc_id: str = Field(description="Document id to re-parent")
    parent_id: str | None = Field(
        default=None, description="New parent id (None moves to root)"
    )


class DocumentDuplicateParams(BaseModel):
    """Params for document.duplicate."""

    doc_id: str = Field(description="Document id to deep-copy (subtree included)")
    parent_id: str | None = Field(
        default=None,
        description=(
            "Folder the copy lands in (Option-drag copy). Omitted: beside "
            "the original with a ' copy' name suffix."
        ),
    )
    to_root: bool = Field(
        default=False,
        description=(
            "Copy to the library root (Option-drop on a root insertion "
            "line) — disambiguates from the beside-the-original default."
        ),
    )


class DocumentReorderParams(BaseModel):
    """Params for document.reorder."""

    doc_ids: list[str] = Field(description="Document ids in their new order")
    folder_path: str = Field(default="/", description="Folder path scope")


class WorkspacePatchActionParams(BaseModel):
    """Params for document.patch_workspace — the path doc_id + the patch body."""

    doc_id: str = Field(description="Workspace (folder) document id")
    patch: WorkspacePatchRequest = Field(description="Add/remove/reorder spec")


class DocumentNoteUpsertActionParams(BaseModel):
    doc_id: str = Field(description="Document id that owns the note")
    request: DocumentNoteUpsert = Field(description="Replacement note body")


class DocumentNoteDeleteParams(BaseModel):
    doc_id: str = Field(description="Document id that owns the note")


class PrototypeAssignActionParams(BaseModel):
    doc_id: str = Field(description="Document id to assign a prototype to")
    request: PrototypeAssignRequest = Field(description="Prototype assignment spec")


class PageRangeUpsertActionParams(BaseModel):
    doc_id: str = Field(description="Document id whose page ranges are being replaced")
    request: PageRangeUpsertRequest = Field(description="Full page-range replacement")


class PdfBackfillActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentCleanupOrphansParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentRestoreParams(BaseModel):
    """Params for document.restore.

    Supports BOTH user-facing undelete-by-id and audit undo-by-snapshot.
    """

    doc_id: str | None = Field(
        default=None,
        description="Single document id to restore (restores its subtree).",
    )
    doc_ids: list[str] = Field(
        default_factory=list,
        description="Explicit document ids to restore.",
    )

    documents: list[dict[str, Any]] = Field(
        default_factory=list, description="Document.model_dump snapshots"
    )
    artifacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Artifact snapshots deleted alongside the documents.",
    )


class DocumentTrashListParams(BaseModel):
    limit: int | None = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0)


def _invert_create_document(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    document_id = after.get("document_id")
    if not document_id:
        return None
    return ("document.delete", {"doc_id": document_id})


def _invert_restore_from_snapshot(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse for update / move / patch_workspace: ``before`` is a single full
    document snapshot, restored verbatim."""
    if not before:
        return None
    return ("document.restore", {"documents": [before]})


def _invert_reorder_documents(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("document.restore", {"documents": before.get("documents", [])})


def _invert_batch_exclude(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("document.restore", {"documents": before.get("documents", [])})


def _invert_document_note_snapshot(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if before:
        return ("document.note_upsert", before)
    if after:
        return ("document.note_delete", {"doc_id": after.get("document_id")})
    return None


def _invert_document_prototype_snapshot(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("document.restore", {"documents": before.get("documents", [])})


def _invert_delete_document(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return (
        "document.restore",
        {
            "doc_ids": [snapshot["id"] for snapshot in before.get("documents", []) if snapshot.get("id")],
            "documents": before.get("documents", []),
            "artifacts": before.get("artifacts", []),
        },
    )


@action(
    "document.create",
    DocumentCreate,
    domains=["document"],
    undoable=True,
    invert=_invert_create_document,
)
def _action_create_document(
    db: Database, params: DocumentCreate, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    new_doc = create_document_impl(db, params)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[new_doc.id],
        after={"document_id": new_doc.id},
        emit_type="document.created",
        document_ids=[new_doc.id],
        emit_fn=_emit_document_change_spec,
    )
    return new_doc.model_dump(mode="json"), spec


@action(
    "document.update",
    DocumentUpdateActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_restore_from_snapshot,
)
def _action_update_document(
    db: Database, params: DocumentUpdateActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc, before, _changed = update_document_impl(db, params.doc_id, params.update)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        before=before,
        after=doc.model_dump(mode="json"),
        emit_type="document.updated",
        document_ids=[doc.id],
    )
    return doc.model_dump(mode="json"), spec


class DocumentSetDateParams(BaseModel):
    """Params for document.set_date — the user's date override (#3322).

    ``date_original`` is parsed through ``histdate``; unparseable input is a
    422, never a silent store of half a date. ``explicitly_undated`` records
    the archival fact "this document says n.d." — distinct from clearing.
    ``date_original=None`` with ``explicitly_undated=False`` clears the date
    entirely (back to never-extracted).
    """

    doc_id: str = Field(description="Document id to date")
    date_original: str | None = Field(
        default=None, description="The date as written, e.g. '17 de abril de 1893'."
    )
    explicitly_undated: bool = Field(
        default=False, description="The document itself says it is undated (n.d./s.f.)."
    )
    year_start_march: bool = Field(
        default=False, description="Old Style parsing: pre-1752 English double years."
    )
    assume_julian: bool = Field(
        default=False, description="Treat plain dates as Julian-calendar dates."
    )


@action(
    "document.set_date",
    DocumentSetDateParams,
    domains=["document"],
    undoable=True,
    invert=_invert_restore_from_snapshot,
)
def _action_set_document_date(
    db: Database, params: DocumentSetDateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """User curation of a document's historical date — audited + undoable.

    Persistent like other curation: ``source: user`` on the row IS the rule.
    ``date_extract`` consults it and may not overwrite — it still runs, and a
    disagreeing new extraction is RECORDED as ``date_meta.extraction_conflict``
    (candidate preserved, nothing silently discarded). Re-asserting here
    clears any recorded conflict by construction (fresh meta dict).
    """
    from fichero_server.core.timeutil import utc_now as _utc_now
    from fichero_server.histdate import (
        STATUS_UNDATED_EXPLICIT,
        parse_historical_date,
    )

    doc = db.get(Document, params.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {params.doc_id}")
    before = doc.model_dump(mode="json")

    if params.explicitly_undated:
        doc.date_original = None
        doc.date_jdn = None
        doc.date_jdn_end = None
        doc.date_meta = {
            "status": STATUS_UNDATED_EXPLICIT,
            "source": "user",
            "set_at": _utc_now().isoformat(),
        }
    elif params.date_original is None:
        doc.date_original = None
        doc.date_jdn = None
        doc.date_jdn_end = None
        doc.date_meta = None
    else:
        parsed = parse_historical_date(
            params.date_original,
            year_start_march=params.year_start_march,
            assume_julian=params.assume_julian,
        )
        if parsed is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Could not parse date: {params.date_original!r}. "
                    "Supported forms include '17 de abril de 1893', "
                    "'March 1791', '1791', '12 Thermidor An II', "
                    "'10 Feb 1723/4' (with year_start_march)."
                ),
            )
        doc.date_original = parsed.original
        doc.date_jdn = parsed.jdn
        doc.date_jdn_end = parsed.jdn_end
        meta = parsed.as_meta()
        meta["source"] = "user"
        meta["confidence"] = 1.0
        doc.date_meta = meta

    doc.updated_at = _utc_now()
    db.save(doc)

    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        before=before,
        after=doc.model_dump(mode="json"),
        emit_type="document.updated",
        document_ids=[doc.id],
    )
    return doc.model_dump(mode="json"), spec


@action(
    "document.move",
    DocumentMoveParams,
    domains=["document"],
    undoable=True,
    invert=_invert_restore_from_snapshot,
)
def _action_move_document(
    db: Database, params: DocumentMoveParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc, before = move_document_impl(db, params.doc_id, params.parent_id)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        before=before,
        after=doc.model_dump(mode="json"),
        emit_type="document.updated",
        document_ids=[doc.id],
        emit_fn=_emit_document_change_spec,
    )
    return doc.model_dump(mode="json"), spec


def _invert_duplicate_document(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    # Undo of a duplicate deletes the root copy — document.delete cascades
    # to the copied subtree.
    if not after:
        return None
    root_id = after.get("document_id")
    if not root_id:
        return None
    return ("document.delete", {"doc_id": root_id})


@action(
    "document.duplicate",
    DocumentDuplicateParams,
    domains=["document"],
    undoable=True,
    invert=_invert_duplicate_document,
)
def _action_duplicate_document(
    db: Database, params: DocumentDuplicateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    root_copy, new_ids = duplicate_document_impl(
        db, params.doc_id, parent_id=params.parent_id, to_root=params.to_root
    )
    spec = ChangeSpec(
        domains=["document"],
        target_ids=new_ids,
        after={"document_id": root_copy.id, "duplicated_ids": new_ids},
        emit_type="document.created",
        document_ids=new_ids,
        emit_fn=_emit_document_change_spec,
    )
    return root_copy.model_dump(mode="json"), spec


@action(
    "document.reorder",
    DocumentReorderParams,
    domains=["document"],
    undoable=True,
    invert=_invert_reorder_documents,
)
def _action_reorder_documents(
    db: Database, params: DocumentReorderParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_snapshots = reorder_documents_impl(db, params.doc_ids, params.folder_path)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=list(params.doc_ids),
        before={"documents": before_snapshots},
        after=None,
        emit_type="document.updated" if params.doc_ids else None,
        document_ids=list(params.doc_ids),
    )
    return {"status": "reordered", "count": len(params.doc_ids)}, spec


@action(
    "document.patch_workspace",
    WorkspacePatchActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_restore_from_snapshot,
)
def _action_patch_workspace(
    db: Database, params: WorkspacePatchActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc, before = patch_workspace_items_impl(db, params.doc_id, params.patch)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        before=before,
        after=doc.model_dump(mode="json"),
        emit_type="document.updated",
        document_ids=[doc.id],
    )
    return {
        "document_id": doc.id,
        "items": doc.curated_items,
        "count": len(doc.curated_items),
    }, spec


@action(
    "document.note_upsert",
    DocumentNoteUpsertActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_document_note_snapshot,
)
def _action_document_note_upsert(
    db: Database, params: DocumentNoteUpsertActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    normalized_id = _normalize_document_id(params.doc_id)
    existing = list(db.query(DocumentNote, document_id=normalized_id))
    before = (
        {
            "doc_id": normalized_id,
            "request": {"content": existing[0].content},
        }
        if existing
        else None
    )
    note = put_document_note_impl(db, params.doc_id, params.request)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[note.document_id],
        before=before,
        after={"document_id": note.document_id},
        emit_type="document.updated",
        document_ids=[note.document_id],
    )
    return note.model_dump(mode="json"), spec


@action(
    "document.note_delete",
    DocumentNoteDeleteParams,
    domains=["document"],
    undoable=True,
    invert=_invert_document_note_snapshot,
)
def _action_document_note_delete(
    db: Database, params: DocumentNoteDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    normalized_id = _normalize_document_id(params.doc_id)
    existing = list(db.query(DocumentNote, document_id=normalized_id))
    before = (
        {
            "doc_id": normalized_id,
            "request": {"content": existing[0].content},
        }
        if existing
        else None
    )
    deleted_id = delete_document_note_impl(db, params.doc_id)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[deleted_id],
        before=before,
        after={"document_id": deleted_id},
        emit_type="document.updated",
        document_ids=[deleted_id],
    )
    return {"document_id": deleted_id}, spec


@action(
    "document.batch_exclude",
    DocumentBatchExcludeRequest,
    domains=["document"],
    undoable=True,
    invert=_invert_batch_exclude,
)
def _action_batch_exclude(
    db: Database, params: DocumentBatchExcludeRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    updated_ids, before_snapshots = batch_exclude_documents_impl(db, params)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=updated_ids,
        before={"documents": before_snapshots},
        after={"document_ids": updated_ids},
        emit_type="document.updated" if updated_ids else None,
        document_ids=updated_ids,
    )
    return {"updated": len(updated_ids), "document_ids": updated_ids}, spec


@action(
    "document.assign_prototype",
    PrototypeAssignActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_document_prototype_snapshot,
)
def _action_assign_document_prototype(
    db: Database, params: PrototypeAssignActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    before_by_id = {
        candidate.id: candidate.model_dump(mode="json")
        for candidate in _list_documents(db, include_deleted=True)
    }
    response, scoped_ids = assign_document_prototype_impl(db, params.doc_id, params.request)
    before_docs = [before_by_id[candidate_id] for candidate_id in scoped_ids if candidate_id in before_by_id]
    spec = ChangeSpec(
        domains=["document"],
        target_ids=scoped_ids,
        before={"documents": before_docs},
        after={"document_ids": scoped_ids},
        emit_type="document.updated" if response.updated_count > 0 else None,
        document_ids=scoped_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "document.delete",
    DocumentDeleteParams,
    domains=["document"],
    undoable=True,
    invert=_invert_delete_document,
)
def _action_delete_document(
    db: Database, params: DocumentDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    to_delete_ids, document_snapshots = delete_document_impl(
        db, params.doc_id, actor=ctx.actor
    )
    spec = ChangeSpec(
        domains=["document"],
        target_ids=to_delete_ids,
        before={"documents": document_snapshots},
        after={"document_ids": to_delete_ids},
        emit_type="document.deleted",
        document_ids=to_delete_ids,
        emit_fn=_emit_document_change_spec,
    )
    return {
        "deleted_document_ids": to_delete_ids,
    }, spec


@action(
    "document.upsert_page_ranges",
    PageRangeUpsertActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_restore_from_snapshot,
)
def _action_upsert_page_ranges(
    db: Database, params: PageRangeUpsertActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc = _document_or_404(db, params.doc_id)
    before = doc.model_dump(mode="json")
    response = upsert_page_ranges_impl(db, params.doc_id, params.request)
    updated = _document_or_404(db, params.doc_id)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[params.doc_id],
        before=before,
        after=updated.model_dump(mode="json"),
        emit_type="document.updated",
        document_ids=[params.doc_id],
    )
    return response.model_dump(mode="json"), spec


@action(
    "document.restore",
    DocumentRestoreParams,
    domains=["document"],
    undoable=False,
)
def _action_restore_documents(
    db: Database, params: DocumentRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    doc_ids = list(params.doc_ids)
    if params.doc_id:
        doc_ids.extend(
            _descendant_document_ids(db, params.doc_id, include_deleted=True)
        )
    restored_ids = restore_documents_impl(
        db,
        doc_ids=doc_ids,
        documents=params.documents,
        artifacts=params.artifacts,
    )
    spec = ChangeSpec(
        domains=["document"],
        target_ids=restored_ids,
        after={"document_ids": restored_ids},
        emit_type="document.updated",
        document_ids=restored_ids,
    )
    return {"restored_document_ids": restored_ids}, spec


@action(
    "document.backfill_pdf_pages",
    PdfBackfillActionParams,
    domains=["document"],
    undoable=False,
)
def _action_backfill_pdf_pages(
    db: Database, params: PdfBackfillActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, created_page_ids = backfill_pdf_pages_impl(db)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=created_page_ids,
        after={"document_ids": created_page_ids},
        emit_type="document.created" if created_page_ids else None,
        document_ids=created_page_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "document.purge",
    DocumentDeleteParams,
    domains=["document"],
    undoable=False,
)
def _action_purge_document(
    db: Database, params: DocumentDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    (
        to_delete_ids,
        claims_deleted,
        entities_pruned,
        _document_snapshots,
        _artifact_snapshots,
    ) = purge_document_impl(db, params.doc_id, library_path=ctx.library_path)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=to_delete_ids,
        after={"document_ids": to_delete_ids},
        emit_type="document.deleted",
        document_ids=to_delete_ids,
    )
    return {
        "deleted_document_ids": to_delete_ids,
        "kg_claims_deleted": claims_deleted,
        "kg_entities_pruned": entities_pruned,
    }, spec


@action(
    "document.cleanup_orphans",
    DocumentCleanupOrphansParams,
    domains=["document"],
    undoable=False,
)
def _action_cleanup_orphans(
    db: Database, params: DocumentCleanupOrphansParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response, orphaned_ids = cleanup_orphan_documents_impl(
        db,
        library_path=ctx.library_path or Path(db.path).parent.as_posix(),
    )
    spec = ChangeSpec(
        domains=["document"],
        target_ids=orphaned_ids,
        after={"document_ids": orphaned_ids},
        emit_type="document.deleted" if orphaned_ids else None,
        document_ids=orphaned_ids,
    )
    return response.model_dump(mode="json"), spec


@action(
    "document.list_trash",
    DocumentTrashListParams,
    domains=["document"],
    undoable=False,
)
def _action_list_document_trash(
    db: Database, params: DocumentTrashListParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    docs = _ordered_by_sort_order(_list_documents(db, only_deleted=True))
    items = (
        docs[params.offset : params.offset + params.limit]
        if params.limit is not None
        else docs[params.offset :]
    )
    return {
        "items": [doc.model_dump(mode="json") for doc in items],
        "count": len(items),
    }, ChangeSpec(domains=["document"])


# ---------------------------------------------------------------------------
# import.upload_file (EPIC #1848 / #2014) — the IMPORT-domain action for the
# multipart ``POST /import`` route. The file/folder/xlsx import actions live in
# ``api/routes/ingest.py``; this one lives here because it wraps the upload
# route's ``import_uploaded_file_impl``. Creates ONE document, so — like
# ``document.create`` and ``import.file`` — it inverts to ``document.delete``.


class UploadFileImportParams(BaseModel):
    """Params for import.upload_file — a server-accessible path to ingest.

    Unlike the route (which is handed a multipart upload it saves to a temp
    file), the action receives a path the engine can already read and does NOT
    delete it — the caller owns the file's lifecycle.
    """

    path: str = Field(description="Server-accessible path of the file to import")
    parent_id: str | None = Field(
        default=None, description="Parent collection id (None imports to root)"
    )
    original_filename: str | None = Field(
        default=None,
        description="Display name to preserve (overrides the on-disk filename).",
    )


def _invert_import_upload_to_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not after:
        return None
    document_id = after.get("document_id")
    if not document_id:
        return None
    return ("document.delete", {"doc_id": document_id})


@action(
    "import.upload_file",
    UploadFileImportParams,
    domains=["document"],
    undoable=True,
    invert=_invert_import_upload_to_delete,
)
def _action_import_upload_file(
    db: Database, params: UploadFileImportParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    library_root = (Path(ctx.library_path) if ctx.library_path else Path(db.path).parent).resolve()
    file_path = Path(params.path).expanduser()
    if not file_path.is_absolute():
        file_path = library_root / file_path
    try:
        file_path = file_path.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"File not found: {params.path}") from exc
    if not file_path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {params.path}")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {params.path}")
    temp_root = Path(tempfile.gettempdir()).resolve()
    is_route_upload_temp = (
        file_path.parent == temp_root and file_path.name.startswith("fichero_upload_")
    )
    try:
        file_path.relative_to(library_root)
    except ValueError as exc:
        if not is_route_upload_temp:
            raise HTTPException(
                status_code=400,
                detail="Upload path must stay inside the library package",
            ) from exc
    doc = import_uploaded_file_impl(
        db,
        file_path,
        original_filename=params.original_filename,
        parent_id=params.parent_id,
    )
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        after={"document_id": doc.id},
        emit_type="document.created",
        document_ids=[doc.id],
    )
    return doc.model_dump(mode="json"), spec


class DocumentGroupRequest(BaseModel):
    name: str = Field(min_length=1)
    child_ids: list[str] = Field(min_length=2)


@router.post("/groups", response_model=Document)
async def create_document_group(
    payload: DocumentGroupRequest,
    db: Database = Depends(get_library_database_for_write),
) -> Document:
    """Create a reversible logical stack without modifying source children."""
    child_ids = list(dict.fromkeys(payload.child_ids))
    if len(child_ids) < 2:
        raise HTTPException(status_code=422, detail="A group requires two distinct children")
    children = [db.get(Document, child_id) for child_id in child_ids]
    if any(child is None for child in children):
        raise HTTPException(status_code=404, detail="One or more group children were not found")
    group = Document(
        name=payload.name,
        doc_type=DocType.group,
        node_kind="group",
        metadata={
            "group_members": [
                {"id": child.id, "parent_id": child.parent_id, "sort_order": child.sort_order}
                for child in children
            ]
        },
    )
    db.save(group)
    for child in children:
        child.parent_id = group.id
        db.save(child)
    emit_change(
        str(db.path.parent),
        type="document.updated",
        document_ids=[group.id, *child_ids],
    )
    return group


@router.post("/groups/{group_id}/ungroup", response_model=list[Document])
async def ungroup_document(
    group_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> list[Document]:
    """Restore every stack member to its original parent and order."""
    group = db.get(Document, group_id)
    if group is None or group.doc_type != DocType.group:
        raise HTTPException(status_code=404, detail=f"Document group not found: {group_id}")
    members = (group.metadata or {}).get("group_members") or []
    restored: list[Document] = []
    for member in members:
        child = db.get(Document, member.get("id"))
        if child is None:
            continue
        child.parent_id = member.get("parent_id")
        child.sort_order = member.get("sort_order", child.sort_order)
        db.save(child)
        restored.append(child)
    db.delete(group)
    emit_change(
        str(db.path.parent),
        type="document.updated",
        document_ids=[group.id, *(child.id for child in restored)],
    )
    return restored
