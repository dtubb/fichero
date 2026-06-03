"""Document export routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.export_service import export_markdown_folder, export_word_docx

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


@router.post("/markdown-folder", response_model=MarkdownFolderExportResponse)
async def export_markdown_folder_route(
    request: MarkdownFolderExportRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path"),
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
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path"),
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
