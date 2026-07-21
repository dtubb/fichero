"""Document export routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.api.library_header import optional_library_path
from fichero.api.main import get_library_database_for_write
from fichero.db import Database
from fichero.export_service import (
    export_eleventy_site,
    export_excel_xlsx,
    export_markdown_folder,
    export_word_docx,
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


class WordExportResponse(BaseModel):
    output_path: str
    document_count: int
    bytes_written: int


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
    """Export a library, folder, or document as a Word .docx file."""
    try:
        result = export_word_docx(
            db=db,
            output_path=Path(request.output_path),
            target_id=request.target_id,
            recursive=request.recursive,
            overwrite=request.overwrite,
            package_path=x_fichero_library_path,
            include_knowledge_graph=request.include_knowledge_graph,
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
