"""
Ingest Routes

File and folder ingestion endpoints.
"""

import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import Document

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task tracking (simple implementation)
_tasks: dict[str, dict] = {}


# Request/Response models
class IngestFileRequest(BaseModel):
    """Request model for file ingestion."""

    path: str
    parent_id: Optional[str] = None
    copy_mode: bool = False  # Link (default) or copy into library
    extract_text: bool = True
    auto_embed: bool = True


class IngestFolderRequest(BaseModel):
    """Request model for folder ingestion."""

    path: str
    parent_id: Optional[str] = None
    copy_mode: bool = False
    recursive: bool = True
    # Default to True so a freshly-ingested folder is searchable as soon
    # as the documents land — matches the single-file ingest default and
    # avoids the "search returns nothing because nothing is indexed" trap
    # users hit on first run. Image files without extractable text
    # silently skip the embed call (db.embed guards on page_content) and
    # get embedded later when transcribe runs and updates page_content.
    extract_text: bool = True
    auto_embed: bool = True


class IngestTaskResponse(BaseModel):
    """Response for async ingest task."""

    task_id: str
    status: str
    path: str


class IngestTaskStatus(BaseModel):
    """Status of an ingest task."""

    task_id: str
    status: str  # pending, running, completed, failed
    path: str
    progress: float  # 0.0 to 1.0
    total: int
    processed: int
    error: Optional[str] = None
    document_ids: list[str] = []


# Routes


@router.post("/file")
async def ingest_file(
    request: IngestFileRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> Document:
    """
    Ingest a single file into the library.

    Returns the created Document immediately.
    """
    from fichero.ingest import ingest_file as do_ingest, IngestMode

    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}")

    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    mode = IngestMode.COPY if request.copy_mode else IngestMode.LINK
    package_path = Path(x_fichero_library_path)

    try:
        doc = do_ingest(
            path,
            mode=mode,
            parent_id=request.parent_id,
            extract_text=request.extract_text,
            auto_embed=request.auto_embed,
            db=db,
            package_path=package_path,
        )
        logger.info(f"Ingested file: {path.name} -> {doc.id}")
        return doc
    except Exception as e:
        logger.error(f"Ingest failed: {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folder")
async def ingest_folder(
    request: IngestFolderRequest,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> IngestTaskResponse:
    """
    Ingest a folder into the library.

    Returns immediately with a task_id. Use /status/{task_id} to check progress.
    """
    from fichero.ingest import ingest_folder as do_ingest, IngestMode, count_files

    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {request.path}")

    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    # Create task
    task_id = uuid4().hex[:12]
    total = count_files(path, recursive=request.recursive)
    package_path = Path(x_fichero_library_path)

    _tasks[task_id] = {
        "status": "pending",
        "path": str(path),
        "progress": 0.0,
        "total": total,
        "processed": 0,
        "error": None,
        "document_ids": [],
    }

    # Background ingest (capture db and package_path for use in background task)
    def do_background_ingest():
        mode = IngestMode.COPY if request.copy_mode else IngestMode.LINK

        def on_progress(current: int, total: int):
            _tasks[task_id]["processed"] = current
            _tasks[task_id]["progress"] = current / total if total > 0 else 1.0

        try:
            _tasks[task_id]["status"] = "running"
            docs = do_ingest(
                path,
                mode=mode,
                parent_id=request.parent_id,
                recursive=request.recursive,
                extract_text=request.extract_text,
                auto_embed=request.auto_embed,
                on_progress=on_progress,
                db=db,
                package_path=package_path,
            )
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["progress"] = 1.0
            _tasks[task_id]["document_ids"] = [d.id for d in docs]
            logger.info(f"Folder ingest complete: {path} ({len(docs)} files)")
        except Exception as e:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)
            logger.error(f"Folder ingest failed: {path}: {e}")

    background_tasks.add_task(do_background_ingest)

    return IngestTaskResponse(
        task_id=task_id,
        status="pending",
        path=str(path),
    )


@router.get("/status/{task_id}")
async def get_ingest_status(task_id: str) -> IngestTaskStatus:
    """Get status of an ingest task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    task = _tasks[task_id]
    return IngestTaskStatus(
        task_id=task_id,
        status=task["status"],
        path=task["path"],
        progress=task["progress"],
        total=task["total"],
        processed=task["processed"],
        error=task.get("error"),
        document_ids=task.get("document_ids", []),
    )
