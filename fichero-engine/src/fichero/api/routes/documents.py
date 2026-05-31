"""
Document Routes

CRUD operations for Document model.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Artifact, DocType, Document, FileType, Status
from fichero.models import DocumentListResponse, DocumentNote, RelatedDocumentListResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response models


class ReorderResponse(BaseModel):
    status: str
    count: int


class OrphanCleanupResponse(BaseModel):
    orphaned_documents_deleted: int
    artifacts_deleted: int


class RelatedDocumentsResponse(BaseModel):
    """One row of /documents/{id}/related — another document that shares
    entities with this one via knowledge claims, with the count of
    shared entities and a small excerpt for context.
    """

    document_id: str
    name: str | None = None
    doc_type: str | None = None
    file_type: str | None = None
    shared_entities: int
    sample_entity_names: list[str] = []


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

    model_config = ConfigDict(extra="allow")

    name: str
    parent_id: Optional[str] = None
    doc_type: DocType = DocType.file
    file_type: Optional[FileType] = None
    path: Optional[str] = None
    page_content: Optional[str] = None
    metadata: dict = {}


class DocumentUpdate(BaseModel):
    """Request model for updating a document."""

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    parent_id: Optional[str] = None
    doc_type: Optional[DocType] = None
    file_type: Optional[FileType] = None
    path: Optional[str] = None
    page_content: Optional[str] = None
    status: Optional[Status] = None
    metadata: Optional[dict] = None


class DocumentNoteUpsert(BaseModel):
    """Request body for per-document note upsert."""

    content: str


# Routes


@router.get("")
async def list_documents(
    parent_id: Optional[str] = Query(None, description="Filter by parent ID"),
    doc_type: Optional[DocType] = Query(None, description="Filter by document type"),
    file_type: Optional[FileType] = Query(None, description="Filter by file type"),
    status: Optional[Status] = Query(None, description="Filter by status"),
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List documents with optional filters from the current library."""
    # Build filter kwargs
    filters = {}
    if parent_id is not None:
        filters["parent_id"] = parent_id
    if doc_type is not None:
        filters["doc_type"] = doc_type
    if file_type is not None:
        filters["file_type"] = file_type
    if status is not None:
        filters["status"] = status

    # Query with filters
    if filters:
        docs = list(db.query(Document, **filters))
    else:
        docs = list(db.all(Document))

    # Apply pagination (if limit is specified)
    if limit is not None:
        items = docs[offset : offset + limit]
    else:
        items = docs[offset:]
    return DocumentListResponse(items=items, count=len(items))


@router.get("/collections")
async def list_collections(
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """List all root-level items (documents without parents)."""
    items = list(db.query(Document, parent_id=None))
    return DocumentListResponse(items=items, count=len(items))


@router.get("/roots")
async def list_roots(db: Database = Depends(get_library_database)) -> DocumentListResponse:
    """List root documents (no parent)."""
    items = list(db.query(Document, parent_id=None))
    return DocumentListResponse(items=items, count=len(items))


@router.get("/{doc_id}")
async def get_document(
    doc_id: str, db: Database = Depends(get_library_database)
) -> Document:
    """Get a single document by ID."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


@router.get(
    "/{doc_id}/workflow-runs",
    response_model=WorkflowRunProvenanceListResponse,
    summary="Get workflow provenance for a document",
)
async def get_document_workflow_runs(
    doc_id: str, db: Database = Depends(get_library_database)
) -> WorkflowRunProvenanceListResponse:
    """Return the recorded workflow runs for a single document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

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
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    notes = list(db.query(DocumentNote, document_id=doc_id))
    if not notes:
        raise HTTPException(status_code=404, detail=f"Document note not found: {doc_id}")
    return notes[0]


@router.put("/{doc_id}/notes")
async def put_document_note(
    doc_id: str,
    request: DocumentNoteUpsert,
    db: Database = Depends(get_library_database),
) -> DocumentNote:
    """Create or replace a document's user note."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    notes = list(db.query(DocumentNote, document_id=doc_id))
    if notes:
        note = notes[0]
        note.content = request.content
        note.updated_at = datetime.now()
    else:
        note = DocumentNote(document_id=doc_id, content=request.content)

    db.save(note)
    return note


@router.delete("/{doc_id}/notes", status_code=204)
async def delete_document_note(
    doc_id: str, db: Database = Depends(get_library_database)
) -> None:
    """Delete the user note for a document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    notes = list(db.query(DocumentNote, document_id=doc_id))
    if not notes:
        raise HTTPException(status_code=404, detail=f"Document note not found: {doc_id}")
    db.delete(notes[0])


@router.get("/{doc_id}/children")
async def get_children(
    doc_id: str,
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    db: Database = Depends(get_library_database),
) -> DocumentListResponse:
    """Get child documents."""
    # Verify parent exists
    parent = db.get(Document, doc_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    children = list(db.query(Document, parent_id=doc_id))
    if limit is not None:
        children = children[:limit]
    return DocumentListResponse(items=children, count=len(children))


@router.get("/{doc_id}/ancestors")
async def get_ancestors(
    doc_id: str, db: Database = Depends(get_library_database)
) -> DocumentListResponse:
    """Get all ancestors (parent chain) of a document."""
    ancestors = []
    current = db.get(Document, doc_id)

    if not current:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    while current and current.parent_id:
        parent = db.get(Document, current.parent_id)
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
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    if not doc.parent_id:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} has no parent")

    parent = db.get(Document, doc.parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Parent document not found: {doc.parent_id}")

    return parent


@router.post("", status_code=201)
async def create_document(
    doc: DocumentCreate, db: Database = Depends(get_library_database)
) -> Document:
    """Create a new document."""
    # Create document from request
    new_doc = Document(
        name=doc.name,
        parent_id=doc.parent_id,
        doc_type=doc.doc_type,
        file_type=doc.file_type,
        path=doc.path,
        page_content=doc.page_content,
        metadata=doc.metadata,
    )

    # Verify parent exists if specified
    if doc.parent_id:
        parent = db.get(Document, doc.parent_id)
        if not parent:
            raise HTTPException(
                status_code=400, detail=f"Parent not found: {doc.parent_id}"
            )

    db.save(new_doc)
    logger.info(f"Created document: {new_doc.id} ({new_doc.name})")
    return new_doc


@router.put("/{doc_id}")
async def update_document(
    doc_id: str, update: DocumentUpdate, db: Database = Depends(get_library_database)
) -> Document:
    """Update an existing document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

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
        merged_metadata["page_content_user_edited_at"] = datetime.now().isoformat()
        update_data["metadata"] = merged_metadata

    for field, value in update_data.items():
        setattr(doc, field, value)

    # Update timestamp
    doc.updated_at = datetime.now()

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

    logger.info(f"Updated document: {doc_id}")
    return doc


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
    from fichero.knowledge_models import (
        KnowledgeClaim,
        KnowledgeEntity,
        MutationLog,
        MutationOperationType,
    )

    all_claims = db.query(KnowledgeClaim)
    orphaned = [
        c for c in all_claims
        if c.source_document_id in doc_ids
        or any(sid in doc_ids for sid in (c.source_ids or []))
    ]
    if not orphaned:
        return (0, 0)

    orphaned_ids = {c.id for c in orphaned}
    touched_entity_ids: set[str] = set()
    for claim in orphaned:
        touched_entity_ids.update(claim.entity_ids or [])
        db.save(MutationLog(
            entity_type="KnowledgeClaim",
            entity_id=claim.id,
            operation=MutationOperationType.delete,
            before_state=claim.model_dump(mode="json"),
            after_state=None,
            created_by="cascade_delete_document",
        ))
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
        db.save(MutationLog(
            entity_type="KnowledgeEntity",
            entity_id=entity.id,
            operation=MutationOperationType.delete,
            before_state=entity.model_dump(mode="json"),
            after_state=None,
            created_by="cascade_delete_document",
        ))
        db.delete(entity)
        entities_pruned += 1

    return (len(orphaned), entities_pruned)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: Database = Depends(get_library_database)):
    """Delete a document and all descendants.

    Cleanup includes:
    - Descendant documents in the hierarchy
    - Artifacts attached to any deleted document
    - Vector embeddings for deleted documents
    - KG claims sourced from any deleted document + now-orphaned entities
      (logged to MutationLog so the cascade is reversible — #1021)
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Gather full subtree to avoid leaving orphaned rows that no longer appear
    # in hierarchy views but still remain searchable/queryable.
    stack = [doc_id]
    to_delete_ids: list[str] = []

    while stack:
        current_id = stack.pop()
        to_delete_ids.append(current_id)
        children = db.query(Document, parent_id=current_id)
        stack.extend(child.id for child in children)

    for current_id in to_delete_ids:
        artifacts = db.query(Artifact, document_id=current_id)
        for artifact in artifacts:
            db.delete(artifact)
        db.delete_embedding(current_id)

    # Cascade KG cleanup before the documents go — claims reference docs
    # by id string, so order doesn't matter, but doing it here keeps the
    # teardown in one place.
    claims_deleted, entities_pruned = _cascade_delete_kg_rows(
        db, set(to_delete_ids)
    )

    # Delete children first for clean hierarchical teardown.
    for current_id in reversed(to_delete_ids):
        current_doc = db.get(Document, current_id)
        if current_doc:
            db.delete(current_doc)

    logger.info(
        f"Deleted document subtree: root={doc_id}, total={len(to_delete_ids)}, "
        f"kg_claims_deleted={claims_deleted}, kg_entities_pruned={entities_pruned}"
    )


@router.get("/{doc_id}/related", response_model=RelatedDocumentListResponse)
async def related_documents(
    doc_id: str,
    limit: int = 20,
    db: Database = Depends(get_library_database),
) -> RelatedDocumentListResponse:
    """Documents that share knowledge-graph entities with this one.

    Aggregates entities across this doc's claims, then asks: which
    OTHER docs have claims involving any of those same entities?
    Sorted by overlap count.

    Powers a 'Related' rail on the document inspector — useful for
    field notes and archival research where the user wants to follow
    a name or place across documents without manual searching.
    """
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    import json as _json
    from collections import Counter

    # Step 1: gather distinct entity_ids from this doc's claims.
    try:
        rows = db.conn.execute(
            "SELECT entity_ids FROM knowledgeclaims WHERE source_document_id = $id",
            {"id": doc_id},
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("related-documents claim lookup failed: %s", exc)
        return RelatedDocumentListResponse(items=[], count=0)

    seed_entity_ids: set[str] = set()
    for (raw,) in rows:
        if not raw:
            continue
        try:
            ids = _json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if isinstance(ids, list):
            for eid in ids:
                if isinstance(eid, str) and eid:
                    seed_entity_ids.add(eid)

    if not seed_entity_ids:
        return RelatedDocumentListResponse(items=[], count=0)

    # Step 2: find docs whose claims reference ANY of those entities.
    # JSON-LIKE per-id is fine at this scale; for large entity sets we
    # could batch into a single regex but that's premature.
    counter: Counter[str] = Counter()
    sample_per_doc: dict[str, set[str]] = {}
    for entity_id in seed_entity_ids:
        needle = f'%"{entity_id}"%'
        try:
            related_rows = db.conn.execute(
                "SELECT source_document_id FROM knowledgeclaims WHERE entity_ids LIKE $needle",
                {"needle": needle},
            ).fetchall()
        except Exception:
            continue
        seen_ids_for_entity: set[str] = set()
        for (other_doc_id,) in related_rows:
            if not other_doc_id or other_doc_id == doc_id or other_doc_id in seen_ids_for_entity:
                continue
            seen_ids_for_entity.add(other_doc_id)
            counter[other_doc_id] += 1
            sample_per_doc.setdefault(other_doc_id, set()).add(entity_id)

    if not counter:
        return RelatedDocumentListResponse(items=[], count=0)

    top = counter.most_common(limit)
    out: list[RelatedDocumentsResponse] = []
    for other_id, overlap_count in top:
        other = db.get(Document, other_id)
        if other is None:
            continue
        # Resolve up to 3 sample entity names per related doc.
        sample_names: list[str] = []
        for sample_eid in list(sample_per_doc.get(other_id, set()))[:3]:
            try:
                row = db.conn.execute(
                    "SELECT canonical_name FROM knowledgeentitys WHERE id = $id",
                    {"id": sample_eid},
                ).fetchone()
            except Exception:
                row = None
            if row and row[0]:
                sample_names.append(row[0])
        doc_type_str = other.doc_type.value if hasattr(other.doc_type, "value") else (
            str(other.doc_type) if other.doc_type else None
        )
        file_type_str = other.file_type.value if hasattr(other.file_type, "value") and other.file_type else (
            str(other.file_type) if other.file_type else None
        )
        out.append(
            RelatedDocumentsResponse(
                document_id=other_id,
                name=other.name,
                doc_type=doc_type_str,
                file_type=file_type_str,
                shared_entities=overlap_count,
                sample_entity_names=sample_names,
            )
        )
    return RelatedDocumentListResponse(items=out, count=len(out))


@router.post("/pdfs/backfill-pages")
async def backfill_pdf_pages(
    db: Database = Depends(get_library_database),
) -> PdfBackfillResponse:
    """Find PDFs without page children and create the page Documents.

    Daniel hit this on PDFs ingested before _create_pdf_page_children
    landed (or where Kreuzberg silently failed at ingest time): the
    sidebar shows the PDF as a leaf with no expandable child pages.

    For each PDF in the library, check whether it already has child
    documents with doc_type=page. If not, run the same _create_pdf_page_children
    helper that ingest uses now. Idempotent — re-running on a fully
    backfilled library is a no-op.
    """
    from fichero.ingest import _create_pdf_page_children

    pdfs = db.query(Document, file_type=FileType.pdf)
    pdfs_scanned = len(pdfs)
    pdfs_backfilled = 0
    pages_created = 0
    skipped = 0

    for pdf in pdfs:
        if not pdf.path:
            skipped += 1
            continue
        try:
            existing_pages = db.query(Document, parent_id=pdf.id, doc_type=DocType.page)
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF backfill failed for %s: %s", pdf.id, exc)
            skipped += 1

    return PdfBackfillResponse(
        pdfs_scanned=pdfs_scanned,
        pdfs_backfilled=pdfs_backfilled,
        pages_created=pages_created,
        skipped=skipped,
    )


@router.post("/reorder")
async def reorder_documents(
    doc_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> ReorderResponse:
    """Reorder documents within a folder."""
    # Update sort_order for each document
    for i, doc_id in enumerate(doc_ids):
        doc = db.get(Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

        # For now, only update documents in the specified folder path
        # In a more complex system, we'd verify the document is in the right folder
        doc.sort_order = i
        db.save(doc)

    return ReorderResponse(status="reordered", count=len(doc_ids))


@router.post("/import")
async def import_file(
    file: UploadFile,
    parent_id: Optional[str] = None,
    db: Database = Depends(get_library_database),
) -> Document:
    """Import a file and create a document."""
    from fichero.ingest import ingest_file, IngestMode
    from fichero.storage import save_uploaded_file

    # Save the uploaded file to temp location
    temp_path = await save_uploaded_file(file)

    try:
        # Get library package path from database path
        # db.path is like /path/to/Library.fichero/fichero.duckdb
        # package_path should be /path/to/Library.fichero
        package_path = Path(db.path).parent

        # Ingest the file (copies to library storage and saves to database)
        doc = ingest_file(
            path=temp_path,
            mode=IngestMode.COPY,  # Copy file into library
            parent_id=parent_id,
            extract_metadata=True,  # Extract file metadata
            extract_text=True,  # Extract text for search
            save=True,  # Save to database
            db=db,  # Database instance
            package_path=package_path,  # Library package path
        )

        # Preserve the user's original filename (#1104). save_uploaded_file
        # writes to a temp file named ``fichero_upload_<random><ext>`` and
        # ingest_file derives Document.name from ``path.name`` — without
        # this fixup every imported document shows up as
        # ``fichero_upload_*`` in docs list / sidebar. The hashed storage
        # filename stays on Document.path; only the display name is
        # corrected to the upload's multipart filename.
        if file.filename and doc.name != file.filename:
            doc.name = file.filename
            db.save(doc)

        logger.info(f"Imported document: {doc.id} ({doc.name})")
        return doc

    finally:
        # Clean up temp file
        try:
            temp_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_path}: {e}")


class MoveRequest(BaseModel):
    """Request model for moving a document."""

    model_config = ConfigDict(extra="allow")

    parent_id: Optional[str] = None


@router.put("/{doc_id}/move")
async def move_document(
    doc_id: str,
    parent_id: Optional[str] = Query(None),
    db: Database = Depends(get_library_database),
) -> Document:
    """Move a document to a new parent location.

    Accepts parent_id as either a query parameter or in the request body for flexibility.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Verify new parent exists if specified
    if parent_id:
        parent = db.get(Document, parent_id)
        if not parent:
            raise HTTPException(
                status_code=400, detail=f"Parent not found: {parent_id}"
            )

    # Update parent
    doc.parent_id = parent_id

    # Update timestamp
    doc.updated_at = datetime.now()

    db.save(doc)
    logger.info(f"Moved document: {doc_id} to parent: {parent_id}")

    return doc


@router.post("/cleanup-orphans")
async def cleanup_orphan_documents(
    db: Database = Depends(get_library_database),
) -> OrphanCleanupResponse:
    """Remove unreachable/orphan document rows.

    A document is considered orphaned when it is not reachable from any root
    document (parent_id is None). This catches records left behind by past
    non-cascading deletes and malformed parent chains.
    """
    all_docs = list(db.all(Document))
    if not all_docs:
        return OrphanCleanupResponse(orphaned_documents_deleted=0, artifacts_deleted=0)

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

    return OrphanCleanupResponse(
        orphaned_documents_deleted=len(orphaned),
        artifacts_deleted=artifacts_deleted,
    )
