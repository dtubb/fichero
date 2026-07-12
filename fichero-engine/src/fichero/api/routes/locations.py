"""Typed, read-only resolution of document navigation anchors (#3576)."""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import DocType, Document

router = APIRouter(prefix="/locations", tags=["locations"])


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
    document_id: str = Field(alias="documentId", min_length=1)
    page: int | None = Field(default=None, ge=1)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    char_range: CharacterRange | None = Field(default=None, alias="charRange")
    claim_id: str | None = Field(default=None, alias="claimId")
    entity_id: str | None = Field(default=None, alias="entityId")
    surface: LocationSurface = LocationSurface.both

    @model_validator(mode="after")
    def valid_bbox(self):
        if self.bbox and (any(v < 0 or v > 1 for v in self.bbox) or self.bbox[0] + self.bbox[2] > 1 or self.bbox[1] + self.bbox[3] > 1):
            raise ValueError("bbox must be normalized [x,y,w,h] within 0..1")
        return self


class ResolvedLocation(Location):
    resolved_document_id: str = Field(alias="resolvedDocumentId")
    resolved_page: int | None = Field(default=None, alias="resolvedPage")


@router.post("/resolve", response_model=ResolvedLocation)
async def resolve_location(location: Location, db: Database = Depends(get_library_database)) -> ResolvedLocation:
    """Resolve a page-child anchor once, for every UI/MCP caller."""
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
    return ResolvedLocation(**location.model_dump(by_alias=False), resolvedDocumentId=parent.id, resolvedPage=page)
