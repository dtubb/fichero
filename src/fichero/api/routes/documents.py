"""
Document Routes

CRUD operations for Document model.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile
from pydantic import BaseModel

from fichero.db import db
from fichero.models import Document, DocType, FileType, Status

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response models
class DocumentCreate(BaseModel):
    """Request model for creating a document."""
    name: str
    parent_id: Optional[str] = None
    doc_type: DocType = DocType.file
    file_type: Optional[FileType] = None
    path: Optional[str] = None
    page_content: Optional[str] = None
    metadata: dict = {}


class DocumentUpdate(BaseModel):
    """Request model for updating a document."""
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
    limit: Optional[int] = Query(None, ge=1, description="Max results (no limit if not specified)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> list[Document]:
    """List documents with optional filters."""
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
async def list_collections() -> list[Document]:
    """List all root-level items (documents without parents)."""
    return list(db.query(Document, parent_id=None))


@router.get("/roots")
async def list_roots() -> list[Document]:
    """List root documents (no parent)."""
    return list(db.query(Document, parent_id=None))


@router.get("/{doc_id}")
async def get_document(doc_id: str) -> Document:
    """Get a single document by ID."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return doc


@router.get("/{doc_id}/children")
async def get_children(
    doc_id: str,
    limit: Optional[int] = Query(None, ge=1, description="Max results (no limit if not specified)"),
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
async def get_ancestors(doc_id: str) -> list[Document]:
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
async def create_document(doc: DocumentCreate) -> Document:
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
            raise HTTPException(status_code=400, detail=f"Parent not found: {doc.parent_id}")

    db.save(new_doc)
    logger.info(f"Created document: {new_doc.id} ({new_doc.name})")
    return new_doc


@router.put("/{doc_id}")
async def update_document(doc_id: str, update: DocumentUpdate) -> Document:
    """Update an existing document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Apply updates
    update_data = update.model_dump(exclude_unset=True)

    # Validate parent exists if parent_id is being updated to a non-null value
    # Allow parent_id=None to move to root
    if "parent_id" in update_data:
        if update_data["parent_id"] is not None:
            parent = db.get(Document, update_data["parent_id"])
            if not parent:
                raise HTTPException(status_code=400, detail=f"Parent not found: {update_data['parent_id']}")
        # parent_id=None is allowed (moves to root)

    for field, value in update_data.items():
        setattr(doc, field, value)

    # Update timestamp
    from datetime import datetime
    doc.updated_at = datetime.now()

    db.save(doc)
    logger.info(f"Updated document: {doc_id}")
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    """Delete a document."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    db.delete(doc)
    logger.info(f"Deleted document: {doc_id}")


@router.post("/reorder")
async def reorder_documents(doc_ids: list[str], folder_path: str = "/") -> dict:
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

    return {"status": "reordered", "count": len(doc_ids)}


@router.post("/import")
async def import_file(
    file: UploadFile,
    parent_id: Optional[str] = None,
) -> Document:
    """Import a file and create a document."""
    from fichero.ingest import ingest_file
    from fichero.storage import save_uploaded_file
    
    # Save the uploaded file
    file_path = await save_uploaded_file(file)
    
    # Ingest the file to create document content
    doc_data = await ingest_file(file_path, parent_id=parent_id)
    
    # Create document record
    new_doc = Document(
        name=doc_data.name,
        parent_id=parent_id,
        doc_type=doc_data.doc_type,
        file_type=doc_data.file_type,
        path=file_path,
        page_content=doc_data.page_content,
        metadata=doc_data.metadata,
    )
    
    db.save(new_doc)
    logger.info(f"Imported document: {new_doc.id} ({new_doc.name})")
    
    return new_doc


@router.put("/{doc_id}/move")
async def move_document(
    doc_id: str,
    parent_id: Optional[str] = None,
) -> Document:
    """Move a document to a new parent location."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    
    # Verify new parent exists if specified
    if parent_id:
        parent = db.get(Document, parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail=f"Parent not found: {parent_id}")
    
    # Update parent
    doc.parent_id = parent_id
    
    # Update timestamp
    from datetime import datetime
    doc.updated_at = datetime.now()
    
    db.save(doc)
    logger.info(f"Moved document: {doc_id} to parent: {parent_id}")
    
    return doc
