"""Typed, read-only resolution of document navigation anchors (#3576).

Source-model slice 4 (#4922) extends this SAME resolver with an optional
`segmentId` rather than adding a second one (`source.segment.citable`'s
ruling: a citable reference resolves through the EXISTING
`/api/locations/resolve`, never a new path). A segment id is followed
through `resolve_segment` (merges/splits/deletes), and the live result's
own document/anchor feed straight into the resolver's existing
page-resolution logic below -- unchanged for every other caller.
"""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import DocType, Document, Segment
from fichero_server.models.segments import (
    ProvisionalSegmentIdError,
    SegmentForwarding,
    assert_not_provisional,
    primary_live_segment_id,
    resolve_segment,
)

router = APIRouter(prefix="/locations", tags=["locations"])


class ReferenceFromAnotherLibrary(ValueError):
    """The citable string's own library part does not name THIS library."""


class ReferenceDocumentMismatch(ValueError):
    """The caller named a `documentId` that disagrees with what
    `segmentId` resolves to (or with the citable string's own embedded
    document part) -- refused rather than letting the segment's silently
    win (#4922 third look)."""


def _segment_reference_parts(value: str) -> tuple[str, str | None, str | None]:
    """`(raw_segment_id, embedded_library_uuid, embedded_document_id)` --
    accepts either a bare segment id (both `None`) or the citable string
    form (`fichero:segment/<library_uuid>/<document_id>/<segment_id>`) --
    `source.segment.citable`: "accepts the string form". The library and
    document parts are no longer ignored (#4922 third look): the caller
    checks both against what the id actually resolves to."""
    if value.startswith("fichero:segment/"):
        parts = value.split("/")
        if len(parts) != 4:
            raise ValueError(f"malformed citable reference: {value!r}")
        _prefix, library_uuid, document_id, segment_id = parts
        return segment_id, library_uuid, document_id
    return value, None, None


class LocationSurface(str, Enum):
    preview = "preview"
    reader = "reader"
    inspector = "inspector"
    both = "both"


class CharacterRange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class Location(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    #: Required for every OTHER caller; a `segment_id` resolves its own
    #: document, so this becomes optional and is filled in from the
    #: segment when omitted (see `valid_bbox`/`resolve_location` below).
    document_id: str | None = Field(default=None, alias="documentId", min_length=1)
    page: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    char_range: CharacterRange | None = Field(default=None, alias="charRange")
    claim_id: str | None = Field(default=None, alias="claimId")
    entity_id: str | None = Field(default=None, alias="entityId")
    #: Source-model slice 4 (#4922). A bare segment id or the citable
    #: string form -- `source.segment.citable`: resolved through THIS
    #: route, never a second resolver.
    segment_id: str | None = Field(default=None, alias="segmentId")
    surface: LocationSurface = LocationSurface.both

    @model_validator(mode="after")
    def valid_bbox(self):
        if self.bbox and (any(v < 0 or v > 1 for v in self.bbox) or self.bbox[2] <= 0 or self.bbox[3] <= 0 or self.bbox[0] + self.bbox[2] > 1 or self.bbox[1] + self.bbox[3] > 1):
            raise ValueError("bbox must be normalized [x,y,w,h] within 0..1")
        return self

    @model_validator(mode="after")
    def document_id_or_segment_id(self):
        if not self.document_id and not self.segment_id:
            raise ValueError("either documentId or segmentId is required")
        return self


class ResolvedLocation(Location):
    resolved_document_id: str = Field(alias="resolvedDocumentId")
    resolved_page: int | None = Field(default=None, alias="resolvedPage")
    #: Set only when `segmentId` was given. `resolved_segment_id` is the
    #: PRIMARY live id (the part that kept the requested id, else the
    #: first one found) -- for a caller that wants exactly one.
    #: `live_segment_ids` names EVERY live part (#4922 third look: a split
    #: line has two, and a reference must never silently pick one and say
    #: nothing about the rest). `segment_forwarding` is the trail of notes
    #: followed to get there (empty when it wasn't forwarded at all).
    resolved_segment_id: str | None = Field(default=None, alias="resolvedSegmentId")
    live_segment_ids: list[str] = Field(default_factory=list, alias="liveSegmentIds")
    segment_forwarding: list[SegmentForwarding] = Field(default_factory=list, alias="segmentForwarding")
    segment_deleted: bool = Field(default=False, alias="segmentDeleted")


@router.post("/resolve", response_model=ResolvedLocation)
async def resolve_location(location: Location, db: Database = Depends(get_library_database)) -> ResolvedLocation:
    """Resolve a page-child anchor once, for every UI/MCP caller.

    Source-model slice 4 (#4922): a `segmentId` is followed through
    `resolve_segment` FIRST (merges/splits/deletes), and the PRIMARY live
    result's document + anchor feed the SAME page-resolution logic below
    that every other caller already uses -- one resolver, not two.
    """
    resolved_segment_id: str | None = None
    live_segment_ids: list[str] = []
    segment_forwarding: list[SegmentForwarding] = []
    segment_deleted = False
    if location.segment_id:
        requested_document_id = location.document_id  # before any override below
        try:
            raw_id, ref_library_uuid, ref_document_id = _segment_reference_parts(location.segment_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            assert_not_provisional(raw_id, what="segmentId")
        except ProvisionalSegmentIdError as exc:
            raise HTTPException(422, str(exc)) from exc

        if ref_library_uuid is not None:
            current_uuid = db.library_uuid()
            if current_uuid and ref_library_uuid != current_uuid:
                raise HTTPException(422, str(ReferenceFromAnotherLibrary(
                    f"this reference belongs to another library ({ref_library_uuid!r}), "
                    f"not this one ({current_uuid!r})"
                )))

        resolved = resolve_segment(db, raw_id)
        segment_forwarding = resolved.trail
        segment_deleted = resolved.ended_in_delete
        live_segment_ids = resolved.live_segment_ids
        if live_segment_ids:
            resolved_segment_id = primary_live_segment_id(resolved)
            seg_row = db.get(Segment, resolved_segment_id)
            if seg_row is None:
                raise HTTPException(404, f"Segment not found: {resolved_segment_id}")
            resolved_document_id = seg_row.document_id
            for named, source in (("segmentId's document", ref_document_id), ("documentId", requested_document_id)):
                if source and source != resolved_document_id:
                    raise HTTPException(422, str(ReferenceDocumentMismatch(
                        f"{named} ({source!r}) does not match segment {resolved_segment_id!r}'s "
                        f"current document ({resolved_document_id!r})"
                    )))
            location = location.model_copy(update={
                "document_id": resolved_document_id,
                "bbox": list(seg_row.anchor.rect) if seg_row.anchor.rect else location.bbox,
            })
        else:
            # Ended in a delete: no live id to draw a location for, but the
            # ORIGINAL row (soft-deleted, never removed) still names its
            # document, so a caller still learns WHERE it used to be.
            resolved_segment_id = None
            original = db.get(Segment, raw_id)
            if original is None:
                raise HTTPException(404, f"Segment not found: {raw_id}")
            location = location.model_copy(update={"document_id": original.document_id})

    if not location.document_id:
        raise HTTPException(422, "segmentId resolved to no document")

    document = db.get(Document, location.document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    parent = document
    page = location.page
    if document.doc_type == DocType.page and document.parent_id:
        parent = db.get(Document, document.parent_id)
        if parent is None:
            raise HTTPException(422, "Page parent not found")
        page = document.sequence or page
    if page is not None:
        pages = list(db.query(Document, parent_id=parent.id, doc_type=DocType.page))
        if pages and not 1 <= page <= len(pages):
            raise HTTPException(422, "Page is outside document range")
    return ResolvedLocation(
        **location.model_dump(by_alias=False),
        resolvedDocumentId=parent.id,
        resolvedPage=page,
        resolvedSegmentId=resolved_segment_id,
        liveSegmentIds=live_segment_ids,
        segmentForwarding=segment_forwarding,
        segmentDeleted=segment_deleted,
    )
