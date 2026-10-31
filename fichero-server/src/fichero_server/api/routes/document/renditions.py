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

import asyncio
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.db.storage import settings as storage_settings
from fichero_server.media.rendition_order import order_renditions
from fichero_server.models import Document, Rendition, RenditionListResponse
from fichero_server.security.path_security import resolve_document_source_path
from fichero_server.api.errors import ErrorDetail as _RefusalBody

router = APIRouter(prefix="/documents")
#: The page's image chain lives under /pages (`wide.chain.served-by-the-engine`).
pages_router = APIRouter(prefix="/pages")

# Explicit suffix→type map, NEVER the mimetypes module: mimetypes' first-use
# initializer reads system files (/etc/apache2/mime.types), which the
# sandboxed engine is denied — every flip 500ed with PermissionError while
# the tests, unsandboxed, stayed green (live repro 2026-08-21). Mirrors the
# storage routes' map; renditions are images by construction.
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
}


@router.get(
    "/{document_id}/renditions",
    response_model=RenditionListResponse,
    # The 404 is DECLARED, not merely raised. FastAPI documents 200 and 422 by
    # default, so an undeclared 404 reaches the generated Swift client as an
    # `.undocumented(404, _)` it cannot name — and the whole point of this
    # route is that "no renditions" and "no such document" are different
    # answers. A distinction the contract does not state is one clients cannot
    # be expected to honour.
    responses={404: {"model": _RefusalBody, "description": "No document with this id exists"}},
)
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


@router.get(
    "/{document_id}/renditions/{rendition_id}/content",
    response_class=FileResponse,
    responses={
        200: {"content": {"image/*": {}}, "description": "The rendition's bytes"},
        404: {
            "model": _RefusalBody,
            "description": (
                "No such document or rendition, the rendition belongs to a "
                "different document, its bytes were never materialised, or its "
                "recorded path resolves outside the permitted roots"
            )
        },
    },
)
async def get_rendition_content(
    document_id: str,
    rendition_id: str,
    db: Database = Depends(get_library_database),
) -> FileResponse:
    """Serve one rendition's pixels.

    Without this a client can list a page's renditions and name them but never
    SHOW one, because `Rendition.path` is a server-side path and the standing
    rule is that visuals travel over storage endpoints — the engine may be on
    another machine, so a path is not something a client can open.

    Every failure is a 404 on purpose, and the reasons are deliberately not
    distinguished to the caller: separating "no such rendition" from "belongs
    to another document" from "outside the permitted roots" would let a caller
    probe for the existence of ids and paths it has no grant for. The
    distinction that IS meaningful to a client — no such document versus a
    document with no renditions — is already answered by the list route above.

    The path is confined by `resolve_document_source_path`, the same authority
    the IIIF image route uses. Its contract is that the path comes from a
    RECORD reached by id and never from the caller, which is exactly the case
    here: `rendition_id` selects a row, and only that row's stored path is
    resolved. The client never supplies a path.
    """
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    rendition = db.get(Rendition, rendition_id)
    # The ownership check is load-bearing, not defensive tidiness: without it a
    # valid rendition id from ANY document would serve through any other
    # document's URL, making the document segment decorative.
    if rendition is None or rendition.document_id != document_id:
        raise HTTPException(
            status_code=404,
            detail=f"Rendition not found for this document: {rendition_id}",
        )

    if not rendition.materialized:
        # A knowable absent state, recorded at import: the row references bytes
        # that were never written. Better a 404 than a path that fails deeper
        # in the stack with a less honest error.
        raise HTTPException(
            status_code=404,
            detail=f"Rendition {rendition_id} is recorded but its bytes were never materialised",
        )

    library_root = Path(db.path).parent
    resolved = resolve_document_source_path(
        rendition.path, library_root, storage_base=storage_settings.base_path
    )
    if resolved is None or not resolved.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Rendition {rendition_id} has no readable file",
        )
    return FileResponse(
        resolved,
        media_type=IMAGE_MEDIA_TYPES.get(
            resolved.suffix.lower(), "application/octet-stream"
        ),
    )


class ImageChainStep(BaseModel):
    """The photograph, or one rendition a step wrote of the page, in the order made."""

    kind: Literal["photograph", "rendition"]
    rendition_id: Optional[str] = Field(default=None, description="null for the photograph; the id the content route serves")
    role: str
    operation: str = Field(description="the operation's name in the Set Up rows: Crop to the paper, Straighten, Clarity")
    figure: str = Field(description="what it did, in words from the rendition's transform and note")
    note: Optional[str] = None
    reads_this: bool = Field(description="true on the one image every later step reads (`current_page_image`)")
    passed_over: Optional[str] = Field(default=None, description="why this rendition could not be read or followed, else null")
    derived_from: Optional[str] = Field(default=None, description="the rendition it was cut from; null: the photograph")
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None


class ImageChainPassedOver(BaseModel):
    rendition_id: str
    role: str
    why: str


class ImageChain(BaseModel):
    """What the page's pictures are and which one is read (`wide.chain.served-by-the-engine`)."""

    page_id: str
    read_from: Literal["original", "edited", "rendition"] = Field(description="what every later step reads")
    why: str = Field(description="why it is that image, in words")
    steps: list[ImageChainStep] = Field(description="the photograph, then each rendition in the order made")
    passed_over: list[ImageChainPassedOver]
    axis: list[str] = Field(description="the renditions' ids in Preview's up/down order (`order_renditions`)")


@pages_router.get("/{page_id}/image-chain", response_model=ImageChain,
                  responses={404: {"model": _RefusalBody, "description": "No page with this id exists"}})
async def get_image_chain(page_id: str, db: Database = Depends(get_library_database)) -> ImageChain:
    """The page's image chain: the photograph, each rendition in the order made with its operation and figure in words, which
    one every later step reads and each one passed over with its reason."""
    from fichero_server.media.image_chain import image_chain

    doc = db.get(Document, page_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {page_id}")
    return ImageChain(**await asyncio.to_thread(image_chain, db, doc))
