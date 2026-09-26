"""`GET /api/segments/{segment_id}/picture` -- a segment's picture (slice 7, #4925).

Spec: `build-notes-shapes-and-anchor.md`, "A segment's picture, cut to its
shape". Behaviour `source.segment.picture-by-shape`.

Its own module rather than another block in `segments.py` for the reason that
file's own header gives about length, and because everything here is about
IMAGES: the cutting is in `media/segment_pictures.py`, beside the region
cropper it extends, and this file is only the seam.

WHY IT ANSWERS BYTES. The spec says a storage reference and "never a local
path (the engine may be remote)". The storage routes address a DOCUMENT, not
one of its renditions by role, so there is no reference to hand back that a
client could fetch -- and inventing an addressing scheme for derived images is
a bigger decision than this slice. PNG bytes satisfy the rule the wording
exists to protect, and match the route the app already fetches a cropped
region from (`GET /api/annotations/{id}/crop`, #2105).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.media.region_crops import RegionCropUnavailable
from fichero_server.media.segment_pictures import (
    SIZE_LIMIT,
    SegmentPictureOptions,
    segment_picture,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/segments")

#: The one refusal, said the same way every time. `422` rather than `404`: the
#: segment is there and the request is well formed -- the picture cannot be
#: made honestly, which is a different fact from "no such segment" and the
#: caller must be able to tell them apart.
_PICTURE_RESPONSES = {
    200: {"content": {"image/png": {}}, "description": "The segment's picture, cut to its shape"},
    422: {"description": "The picture cannot be made honestly; the reason says why"},
}


@router.get(
    "/{segment_id}/picture",
    summary="A segment's picture, cut to its shape",
    description=(
        "PNG bytes of the segment's own area, cropped to its derived box plus "
        "`margin`, masked outside its polygon when `mask` is set, and levelled "
        "along its baseline when `straighten` is set. A worked-out thing, never "
        "a record: cached per segment version and remade when the segment "
        "changes. Refuses rather than returning a picture of the wrong place "
        "when the segment was measured on an image that is not the one here. (#4925)"
    ),
    responses=_PICTURE_RESPONSES,
)
async def get_segment_picture(
    segment_id: str,
    size: int | None = Query(
        default=None, ge=1, le=SIZE_LIMIT,
        description="Largest edge in pixels; the default is bounded, not unlimited",
    ),
    margin: float = Query(
        default=0.0, ge=0.0, le=1.0,
        description="Extra room around the shape, as a fraction of its own size",
    ),
    straighten: bool = Query(
        default=False, description="Level the line along its baseline"
    ),
    mask: bool = Query(
        default=False, description="Make everything outside the polygon transparent"
    ),
    db: Database = Depends(get_library_database),
):
    try:
        options = SegmentPictureOptions(
            size=size, margin=margin, straighten=straighten, mask=mask
        )
        rendition = segment_picture(db, segment_id, options=options)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RegionCropUnavailable as exc:
        # Absent, not faked. The reason travels, because "no picture" and
        # "a picture of the wrong page" are the two outcomes here and the
        # caller is entitled to know it got the first one.
        raise HTTPException(422, str(exc)) from exc
    return FileResponse(rendition.path, media_type="image/png")
