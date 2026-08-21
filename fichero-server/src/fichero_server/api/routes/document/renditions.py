"""A node's renditions — alternative pixels of one page (2026-08-20 bbox review).

Read-only for now. Renditions are WRITTEN by ingest (from the staging
sidecar) and by the image workflows; nothing should be creating them by hand
through the API, so there is deliberately no POST here yet. When one is
needed it belongs in the audited action layer like every other mutation, not
as a bare route.

The response is ORDERED by the engine (primary first, then
``RENDITION_ROLE_PREFERENCE``) so every client agrees what "next" means on the
up/down flip. See ``media/rendition_order.py`` for why that decision cannot
live in the clients.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.media.rendition_order import order_renditions
from fichero_server.models import Document, Rendition, RenditionListResponse

router = APIRouter(prefix="/documents")


@router.get("/{document_id}/renditions", response_model=RenditionListResponse)
async def list_renditions(
    document_id: str,
    db: Database = Depends(get_library_database),
) -> RenditionListResponse:
    """Every rendition of one node, in display order.

    404s on a missing document rather than returning an empty list: "this node
    has no renditions" and "this node does not exist" are different answers,
    and a client that cannot tell them apart will render an empty flip strip
    for a typo'd id and call it a page with one image.

    An existing node with no renditions is a legitimate empty list — folders
    have none, and neither does a node whose bytes were never materialised.
    """
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    items = order_renditions(db.query(Rendition, document_id=document_id))
    return RenditionListResponse(items=items, count=len(items))
