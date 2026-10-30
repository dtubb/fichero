"""Document export routes, and the project's kept exports (#5485, `/export/kept`)."""

import base64
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.library_header import optional_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.export_service import (
    export_catalogue_xlsx,
    export_eleventy_site,
    export_excel_xlsx,
    export_jsonl,
    export_parquet,
    export_markdown_folder,
    export_word_docx,
    export_word_transcripts,
)

router = APIRouter(prefix="/export", tags=["export"])


class MarkdownFolderExportRequest(BaseModel):
    """Request body for Markdown folder export."""

    model_config = ConfigDict(extra="allow")

    output_path: str = Field(..., description="Destination folder for export files")
    target_id: str | None = Field(
        default=None,
        description="Optional document/folder id to export; omitted exports library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    include_assets: bool = Field(default=True, description="Copy image assets")
    overwrite: bool = Field(
        default=False, description="Allow writing into non-empty folder"
    )


class ExportedFileResponse(BaseModel):
    path: str
    kind: str
    document_id: str | None = None


class MarkdownFolderExportResponse(BaseModel):
    output_path: str
    files: list[ExportedFileResponse]
    assets: list[ExportedFileResponse]
    document_count: int


class WordExportRequest(BaseModel):
    """Request body for Word export."""

    model_config = ConfigDict(extra="allow")

    output_path: str = Field(..., description="Destination .docx path")
    target_id: str | None = Field(
        default=None,
        description="Optional document/folder id to export; omitted exports library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    overwrite: bool = Field(default=False, description="Overwrite existing .docx")
    include_knowledge_graph: bool = Field(
        default=True,
        description="Append relevant knowledge graph entities and claims",
    )
    include_images: bool = Field(
        default=True,
        description="Off prints neither the image nor the 'image not included' note: a page is its heading and text",
    )
    page_break_per_page: bool = Field(default=False, description="Start each page on a new Word page")
    blank_pages_listed_once: bool = Field(
        default=False,
        description="Print no body for a page sorted blank; end the folder with one line listing them as image ranges",
    )
    per: Literal["document", "folder"] = Field(
        default="document",
        description="'folder' writes a .zip of one transcript .docx per folder of the scope (page by page, no "
        "images, a page break per page, blank pages listed once): the options above are fixed for it",
    )


class WordExportResponse(BaseModel):
    output_path: str
    document_count: int
    bytes_written: int
    files: list[str] = Field(default_factory=list, description="per folder: the .docx names inside the zip")


class ExcelExportRequest(BaseModel):
    """Request body for Excel export."""

    model_config = ConfigDict(extra="allow")

    output_path: str = Field(..., description="Destination .xlsx path")
    target_id: str | None = Field(
        default=None,
        description="Optional document/folder id to export; omitted exports library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    overwrite: bool = Field(default=False, description="Overwrite existing .xlsx")


class ExcelExportResponse(BaseModel):
    output_path: str
    document_count: int
    entity_count: int
    claim_count: int
    bytes_written: int


class JsonlExportRequest(BaseModel):
    """Request body for JSON Lines export."""

    output_path: str = Field(..., description="Destination .jsonl path")
    target_id: str | None = Field(
        default=None,
        description="Optional document/folder id to export; omitted exports library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    overwrite: bool = Field(default=False, description="Overwrite existing .jsonl")


class JsonlExportResponse(BaseModel):
    output_path: str
    document_count: int
    entity_count: int
    claim_count: int
    bytes_written: int


class TrainingExportRequest(BaseModel):
    """Request body for an episode-ledger training export (MLX loop)."""

    output_path: str = Field(..., description="Destination .jsonl path")
    use_case: str | None = Field(
        default=None,
        description="Filter to one workflow step's calls (e.g. 'transcription')",
    )
    gold_only: bool = Field(
        default=False, description="Only human-corrected (gold) pairs"
    )
    overwrite: bool = Field(default=False, description="Overwrite existing .jsonl")


class TrainingExportResponse(BaseModel):
    output_path: str
    sample_count: int
    gold_count: int
    bytes_written: int


class ParquetExportRequest(BaseModel):
    """Request body for a Parquet bundle export."""

    output_path: str = Field(..., description="Destination folder for Parquet files")
    target_id: str | None = Field(
        default=None,
        description="Optional document/folder id to export; omitted exports library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    overwrite: bool = Field(
        default=False, description="Allow writing into a non-empty folder"
    )


class ParquetExportResponse(BaseModel):
    output_path: str
    files: list[str]
    manifest_path: str
    document_count: int
    entity_count: int
    claim_count: int
    bytes_written: int


class EleventySiteExportRequest(BaseModel):
    """Request body for 11ty/Netlify static-site export."""

    model_config = ConfigDict(extra="allow")

    output_path: str = Field(..., description="Destination folder for the site project")
    target_id: str | None = Field(
        default=None,
        description="Optional folder id to publish; omitted exports the library",
    )
    recursive: bool = Field(default=True, description="Include descendants of folders")
    overwrite: bool = Field(
        default=False, description="Allow writing into a non-empty folder"
    )
    site_title: str | None = Field(
        default=None, description="Site title (defaults to the root folder name)"
    )


class EleventySiteExportResponse(BaseModel):
    output_path: str
    document_count: int
    collection_count: int
    files: list[ExportedFileResponse]
    assets: list[ExportedFileResponse]


@router.post("/jsonl", response_model=JsonlExportResponse)
async def export_jsonl_route(
    request: JsonlExportRequest,
    db: Database = Depends(get_library_database_for_write),
) -> JsonlExportResponse:
    """Export canonical records as a JSON Lines file."""
    try:
        result = export_jsonl(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JsonlExportResponse(**result.__dict__)


@router.post("/training", response_model=TrainingExportResponse)
async def export_training_route(
    request: TrainingExportRequest,
    db: Database = Depends(get_library_database_for_write),
) -> TrainingExportResponse:
    """Export chat-format training samples from the episode ledger.

    One sample per recorded model call; the assistant turn is the human
    correction when one exists (gold), otherwise the model output.
    Corrected samples carry `rejected` for DPO pairing. Engine-local
    destination path — a CLI/backend surface like the record-bundle
    exports; same conflict rule (409 unless `overwrite`).
    """
    import json as _json

    from fichero_server.observability import episodes

    library_path = str(Path(str(db.path)).parent)
    samples = episodes.export_training_pairs(
        library_path, use_case=request.use_case, gold_only=request.gold_only
    )
    destination = Path(request.output_path)
    if destination.exists() and not request.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"Destination exists: {destination} (set overwrite to replace)",
        )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            _json.dumps(sample, ensure_ascii=False) + "\n" for sample in samples
        )
        destination.write_text(body, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TrainingExportResponse(
        output_path=str(destination),
        sample_count=len(samples),
        gold_count=sum(1 for sample in samples if sample.get("gold")),
        bytes_written=len(body.encode("utf-8")),
    )


@router.post("/parquet", response_model=ParquetExportResponse)
async def export_parquet_route(
    request: ParquetExportRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ParquetExportResponse:
    """Export canonical records as a typed Parquet bundle."""
    try:
        result = export_parquet(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ParquetExportResponse(**result.__dict__)


@router.post("/eleventy-site", response_model=EleventySiteExportResponse)
async def export_eleventy_site_route(
    request: EleventySiteExportRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
) -> EleventySiteExportResponse:
    """Publish a library, folder, or subfolder as an 11ty/Netlify static site."""
    try:
        result = export_eleventy_site(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
            package_path=x_fichero_library_path,
            site_title=request.site_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return EleventySiteExportResponse(
        output_path=result.output_path,
        document_count=result.document_count,
        collection_count=result.collection_count,
        files=[ExportedFileResponse(**file.__dict__) for file in result.files],
        assets=[ExportedFileResponse(**asset.__dict__) for asset in result.assets],
    )


@router.post("/markdown-folder", response_model=MarkdownFolderExportResponse)
async def export_markdown_folder_route(
    request: MarkdownFolderExportRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
) -> MarkdownFolderExportResponse:
    """Export a library, folder, or document as a Markdown folder."""
    try:
        result = export_markdown_folder(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            include_assets=request.include_assets,
            overwrite=request.overwrite,
            package_path=x_fichero_library_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MarkdownFolderExportResponse(
        output_path=result.output_path,
        files=[ExportedFileResponse(**file.__dict__) for file in result.files],
        assets=[ExportedFileResponse(**asset.__dict__) for asset in result.assets],
        document_count=result.document_count,
    )


@router.post("/word", response_model=WordExportResponse)
async def export_word_route(
    request: WordExportRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str | None = Depends(optional_library_path),
) -> WordExportResponse:
    """Export a library, folder, or document as a Word .docx file (or, per folder, a zip of them)."""
    try:
        if request.per == "folder":
            return WordExportResponse(**export_word_transcripts(
                db=db, output_path=Path(request.output_path), target_id=request.target_id,
                overwrite=request.overwrite, package_path=x_fichero_library_path,
            ).__dict__)
        result = export_word_docx(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
            package_path=x_fichero_library_path,
            include_knowledge_graph=request.include_knowledge_graph,
            include_images=request.include_images,
            page_break_per_page=request.page_break_per_page,
            blank_pages_listed_once=request.blank_pages_listed_once,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return WordExportResponse(**result.__dict__)


@router.post("/excel", response_model=ExcelExportResponse)
async def export_excel_route(
    request: ExcelExportRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ExcelExportResponse:
    """Export a library, folder, or document as an Excel .xlsx workbook."""
    try:
        result = export_excel_xlsx(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ExcelExportResponse(**result.__dict__)


class CatalogueWorkbookRequest(BaseModel):
    """What to write: the catalogue of a folder or project, in its rows' effective prototype's template."""

    target_id: str | None = Field(default=None, description="A folder or project id; omitted writes the whole library")
    format: Literal["xlsx", "csv"] = Field(default="xlsx", description="xlsx: one workbook; csv: a zip of one file per sheet")
    prototype_key: str | None = Field(default=None, description="Write this prototype's columns instead of the rows' own")
    proposals: Literal["marked", "omitted"] = Field(
        default="marked", description="A machine's unanswered proposals are marked, or left out of a delivered sheet")
    kept_export_id: str | None = Field(
        default=None, description="Write into this kept export's folder (queued) instead of returning the file")


class CatalogueWorkbookResponse(BaseModel):
    filename: str = Field(description="The file's name: Catálogo.xlsx or Catálogo.zip")
    media_type: str
    #: ponytail: the file rides in the JSON envelope (base64); a streamed binary body when a workbook outgrows memory.
    content_base64: str | None = Field(default=None, description="The file, base64; none when it was queued into a kept export")
    sheets: list[str] = Field(default_factory=list)
    row_count: int = 0
    job_id: str | None = Field(default=None, description="The queued write, when kept_export_id was given")


_WORKBOOK_TYPES = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "application/zip"}


@router.post("/catalogue-workbook", response_model=CatalogueWorkbookResponse,
             summary="The catalogue workbook of a folder or project, in its archive's template")
async def export_catalogue_workbook_route(
    request: CatalogueWorkbookRequest,
    db: Database = Depends(get_library_database_for_write),
) -> CatalogueWorkbookResponse:
    """The same builder the recipe's last step runs (`catalogue_sheet.workbook`): attributes, pages, the graph and the
    record; never a model. No local path in the request: the file comes back, or is queued into a kept export."""
    from fichero_server import kept_export

    suffix = ".xlsx" if request.format == "xlsx" else ".zip"
    name = f"{kept_export.WORKBOOK_NAME}{suffix}"
    if request.kept_export_id:
        kept = kept_export._export(db, request.kept_export_id)
        if kept is None or kept["format"] != "catalogue-workbook":
            raise HTTPException(status_code=404, detail="No kept catalogue-workbook export with that id.")
        return CatalogueWorkbookResponse(filename=name, media_type=_WORKBOOK_TYPES[request.format],
                                         job_id=kept_export.write_now(db, request.kept_export_id))
    try:
        with tempfile.TemporaryDirectory(prefix="fichero-catalogue-") as scratch:
            result = export_catalogue_xlsx(db, Path(scratch) / f"out{suffix}", request.target_id, request.prototype_key,
                                           overwrite=True, proposals=request.proposals, file_format=request.format)
            data = Path(result.output_path).read_bytes()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CatalogueWorkbookResponse(filename=name, media_type=_WORKBOOK_TYPES[request.format],
                                     content_base64=base64.b64encode(data).decode("ascii"), sheets=result.sheets,
                                     row_count=result.row_count)


# ---------------------------------------------------------------------------------------------------
# Kept exports (#5485, spec models-chains-and-projects section 7b, screen 3): an up-to-date copy of
# the project's work in a folder outside it, written again as the work changes (`kept_export.py`).
# ---------------------------------------------------------------------------------------------------

KeptExportFormat = Literal["word", "markdown", "plain-text", "alto", "pagexml", "tei", "hocr", "catalogue-workbook",
                         "word-transcript"]
KeptExportPer = Literal["page", "document"]


class KeptExportRequest(BaseModel):
    folder: str = Field(description="A full path to a folder on the engine's disk, outside the project")
    format: KeptExportFormat = Field(description="What each file is: Word, Markdown, plain text, ALTO XML, "
                                                 "PAGE XML, TEI or hOCR")
    per: KeptExportPer = Field(description="One file per page, or one per document (the page formats are "
                                           "one per page)")


class KeptExportParams(KeptExportRequest):
    pass


class KeptExportIdParams(BaseModel):
    export_id: str


class KeptExport(BaseModel):
    """One kept export and what it has written."""

    id: str
    folder: str
    format: KeptExportFormat
    per: KeptExportPer
    files: list[str] = Field(description="files this export wrote, relative to the folder: overwritten at "
                                         "each write, a hand edit to one included")
    in_the_way: list[str] = Field(description="files already in the folder that this export did not write: "
                                              "left alone")
    pending: int = Field(description="writes waiting (their jobs are in Activity)")
    last_written: datetime | None = None


class KeptExportList(BaseModel):
    exports: list[KeptExport]


class KeptExportRemoved(BaseModel):
    id: str


class KeptExportWriting(BaseModel):
    id: str
    job_id: str = Field(description="the write's job, in Activity")


@action("export.keep", KeptExportParams, domains=["library"], undoable=False)
def _action_keep(db: Database, params: KeptExportParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import kept_export

    export_id = kept_export.keep(db, params.folder, params.format, params.per)
    return {"id": export_id}, ChangeSpec(domains=["library"], after={"id": export_id, "folder": params.folder,
                                                                     "format": params.format, "per": params.per},
                                         emit_type="export.kept")


@action("export.unkeep", KeptExportIdParams, domains=["library"], undoable=False)
def _action_unkeep(db: Database, params: KeptExportIdParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server import kept_export

    kept_export.remove(db, params.export_id)
    return {"id": params.export_id}, ChangeSpec(domains=["library"], before={"id": params.export_id},
                                                emit_type="export.unkept")


def _kept(db: Database, export_id: str) -> KeptExport:
    from fichero_server import kept_export

    found = next((e for e in kept_export.status(db) if e["id"] == export_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="There is no such kept export.")
    return KeptExport(**found)


@router.get("/kept", response_model=KeptExportList, summary="The project's kept exports and what they wrote")
async def list_kept_exports(db: Database = Depends(get_library_database)) -> KeptExportList:
    from fichero_server import kept_export

    return KeptExportList(exports=[KeptExport(**e) for e in kept_export.status(db)])


@router.post("/kept", response_model=KeptExport,
             summary="Keep an export in a folder, written again as the work changes")
async def keep_export(
    request: KeptExportRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> KeptExport:
    """One-way: Fichero writes the folder and never reads it back. Each write overwrites only the
    files this export wrote (a hand edit to one is overwritten) and leaves every other file alone;
    nothing is deleted. Writing is background work (paused by Pause Background Work). Refused (422),
    in one sentence, for a folder that is not there, a system folder, a folder inside the project,
    or a page format asked for one file per document."""
    from fichero_server.kept_export import KeptExportRefused

    try:
        result = registry.invoke(db, "export.keep", request.model_dump(), ctx)
    except KeptExportRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _kept(db, result.result["id"])


@router.delete("/kept/{export_id}", response_model=KeptExportRemoved,
               summary="Stop keeping an export (the files it wrote stay in the folder)")
async def remove_kept_export(
    export_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> KeptExportRemoved:
    _kept(db, export_id)
    registry.invoke(db, "export.unkeep", {"export_id": export_id}, ctx)
    return KeptExportRemoved(id=export_id)


@router.post("/kept/{export_id}/write", response_model=KeptExportWriting,
             summary="Write a kept export now, as a background job")
async def write_kept_export(
    export_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> KeptExportWriting:
    """Queues one job that writes every file of the export (shown in Activity, paused with background
    work). Files already being written are covered by the same job."""
    from fichero_server import kept_export

    _kept(db, export_id)
    return KeptExportWriting(id=export_id, job_id=kept_export.write_now(db, export_id))
