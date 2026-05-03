"""
Document Routes

CRUD operations for Document model.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Artifact, DocType, Document, FileType, Status

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response models


class ReorderResponse(BaseModel):
    status: str
    count: int


class OrphanCleanupResponse(BaseModel):
    orphaned_documents_deleted: int
    artifacts_deleted: int


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
) -> list[Document]:
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
        return docs[offset : offset + limit]
    else:
        return docs[offset:]


@router.get("/collections")
async def list_collections(
    db: Database = Depends(get_library_database),
) -> list[Document]:
    """List all root-level items (documents without parents)."""
    return list(db.query(Document, parent_id=None))


@router.get("/roots")
async def list_roots(db: Database = Depends(get_library_database)) -> list[Document]:
    """List root documents (no parent)."""
    return list(db.query(Document, parent_id=None))


@router.get("/{doc_id}")
async def get_document(
    doc_id: str, db: Database = Depends(get_library_database)
) -> Document:
    """Get a single document by ID."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


@router.get("/{doc_id}/children")
async def get_children(
    doc_id: str,
    limit: Optional[int] = Query(
        None, ge=1, description="Max results (no limit if not specified)"
    ),
    db: Database = Depends(get_library_database),
) -> list[Document]:
    """Get child documents."""
    # Verify parent exists
    parent = db.get(Document, doc_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    children = list(db.query(Document, parent_id=doc_id))
    if limit is not None:
        return children[:limit]
    else:
        return children


@router.get("/{doc_id}/ancestors")
async def get_ancestors(
    doc_id: str, db: Database = Depends(get_library_database)
) -> list[Document]:
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

    return ancestors


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
    logger.info(f"Updated document: {doc_id}")
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: Database = Depends(get_library_database)):
    """Delete a document and all descendants.

    Cleanup includes:
    - Descendant documents in the hierarchy
    - Artifacts attached to any deleted document
    - Vector embeddings for deleted documents
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

    # Delete children first for clean hierarchical teardown.
    for current_id in reversed(to_delete_ids):
        current_doc = db.get(Document, current_id)
        if current_doc:
            db.delete(current_doc)

    logger.info(f"Deleted document subtree: root={doc_id}, total={len(to_delete_ids)}")


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
