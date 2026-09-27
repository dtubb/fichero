"""Export one page as PAGE XML, ALTO or TEI (`source.format.everywhere`, #4943).

Thin over `fichero_server.page_export`: the route adds no second export path. The response carries
the file's text AND the export's choices AND its loss report, so a caller that only shows the file
has visibly dropped something.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.formats import (
    FormatCannotWrite,
    InvalidExport,
    UnknownFormat,
    known_formats,
)
from fichero_server.page_export import ExportRefused, export_page

router = APIRouter()


class LossOut(BaseModel):
    what: str
    count: int
    why: str


class ExportChoicesOut(BaseModel):
    document_id: str
    pass_id: str | None = None
    pass_basis: str | None = None
    pass_name: str | None = None
    order_id: str | None = None
    order_name: str
    reading_kind: str
    segment_count: int
    notes: list[str]


class PageExportResponse(BaseModel):
    format: str
    filename: str
    #: The file, as text (all three formats are XML). Written to disk by the caller.
    content: str
    choices: ExportChoicesOut
    losses: list[LossOut]


class FormatInfo(BaseModel):
    name: str
    extensions: list[str]
    reads: bool
    writes: bool
    validated: bool


class FormatListResponse(BaseModel):
    items: list[FormatInfo]


@router.get("/formats", response_model=FormatListResponse, summary="Interchange formats this build reads and writes")
async def list_formats() -> FormatListResponse:
    return FormatListResponse(
        items=[
            FormatInfo(
                name=spec.name,
                extensions=list(spec.extensions),
                reads=spec.reads,
                writes=spec.writes,
                validated=spec.schema is not None,
            )
            for spec in known_formats()
        ]
    )


@router.get(
    "/documents/{doc_id}/export/{format_name}",
    response_model=PageExportResponse,
    summary="Export one page as PAGE XML, ALTO or TEI",
)
async def export_document_page(
    doc_id: str,
    format_name: str,
    pass_id: str | None = Query(None, description="The pass to export; defaults to the working pass"),
    order_id: str | None = Query(None, description="A named reading order's id; defaults to the order as written"),
    reading_kind: str = Query("transcription", description="Which kind of reading to write"),
    db: Database = Depends(get_library_database),
) -> PageExportResponse:
    try:
        result = export_page(
            db, doc_id, format_name, pass_id=pass_id, order_id=order_id, reading_kind=reading_kind
        )
    except UnknownFormat as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FormatCannotWrite as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExportRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidExport as exc:
        # A file that does not validate is a failure and no file (`source.format.export-validated`).
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PageExportResponse(
        format=result.format,
        filename=result.filename,
        content=result.data.decode("utf-8"),
        choices=ExportChoicesOut(**result.choices.as_dict()),
        losses=[LossOut(what=l.what, count=l.count, why=l.why) for l in result.report.losses],
    )
