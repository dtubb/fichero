"""
Ingest Routes

File and folder ingestion endpoints.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel

from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database_for_write, db_manager
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
    # `mode` is the full three-way choice (link/copy/move). `copy_mode` is the
    # legacy boolean that could only express link-vs-copy — MOVE was unreachable
    # through it and silently degraded to LINK (#2869 B1). When `mode` is set it
    # wins; `copy_mode` stays for older callers.
    mode: Optional[str] = None
    copy_mode: bool = False  # Legacy: Link (default) or copy into library
    extract_text: bool = True
    auto_embed: bool = True


class IngestFolderRequest(BaseModel):
    """Request model for folder ingestion."""

    path: str
    parent_id: Optional[str] = None
    mode: Optional[str] = None
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


def _resolve_ingest_mode(mode: Optional[str], copy_mode: bool):
    """Resolve request mode → IngestMode, failing loudly on a bad value.

    `mode` (link/copy/move) wins when present; otherwise fall back to the legacy
    `copy_mode` boolean. An unrecognized `mode` raises 400 rather than silently
    degrading to LINK — the exact class of bug this field fixes (#2869 B1,
    prefer-raise-over-silent-fallback).
    """
    from fichero.ingest import IngestMode

    if mode is not None:
        try:
            return IngestMode(mode.strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in IngestMode)
            raise HTTPException(
                status_code=400,
                detail=f"invalid ingest mode: {mode!r} (expected one of: {valid})",
            )
    return IngestMode.COPY if copy_mode else IngestMode.LINK


# Shared mutation logic (the proven algorithm wrapped by both the route and the
# audited action — iterate-not-replace, EPIC #1848 / #2014). Validation raises
# HTTPException(400) before any ingest work; ingest failures wrap to 500 — the
# exact behavior the routes had before the extraction.


def import_file_impl(
    db: Database,
    request: IngestFileRequest,
    package_path: Path,
) -> Document:
    """Validate + ingest a single file. Returns the created Document.

    Extracted verbatim from the ``POST /file`` route so the route handler and
    the ``import.file`` action drive the SAME code.
    """
    from fichero.ingest import ingest_file as do_ingest

    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    mode = _resolve_ingest_mode(request.mode, request.copy_mode)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingest failed: {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def import_folder_impl(
    db: Database,
    request: IngestFolderRequest,
    package_path: Path,
    on_progress=None,
) -> list[Document]:
    """Validate + synchronously ingest a folder. Returns the created Documents.

    The ``POST /folder`` route runs this in a BackgroundTask (returning a
    task_id); the ``import.folder`` action runs it synchronously so it can audit
    the created doc ids. Both share this one validated ingest.
    """
    from fichero.ingest import ingest_folder as do_ingest

    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {request.path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    mode = _resolve_ingest_mode(request.mode, request.copy_mode)
    return do_ingest(
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


# Routes


@router.post("/file")
async def ingest_file(
    request: IngestFileRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> Document:
    """
    Ingest a single file into the library.

    Returns the created Document immediately.
    """
    return await asyncio.to_thread(
        import_file_impl, db, request, Path(x_fichero_library_path)
    )


@router.post("/folder")
async def ingest_folder(
    request: IngestFolderRequest,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> IngestTaskResponse:
    """
    Ingest a folder into the library.

    Returns immediately with a task_id. Use /status/{task_id} to check progress.
    """
    from fichero.ingest import count_files

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
        # Use a fresh database handle for the background thread instead of
        # reusing the request-scoped object. This avoids stale/contended
        # connection state on long-running folder ingests (#1216).
        bg_db = db_manager.get_database(x_fichero_library_path)

        def on_progress(current: int, total: int):
            _tasks[task_id]["processed"] = current
            _tasks[task_id]["progress"] = current / total if total > 0 else 1.0

        try:
            _tasks[task_id]["status"] = "running"
            # Route through the shared impl so the background task and the
            # audited ``import.folder`` action ingest via the SAME code path.
            docs = import_folder_impl(
                bg_db, request, package_path, on_progress=on_progress
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


class XlsxIngestRequest(BaseModel):
    """Request model for XLSX spreadsheet import."""

    path: str
    column_map: Optional[dict[str, str]] = None
    sheet_index: int = 0
    parent_id: Optional[str] = None
    dry_run: bool = True


class XlsxIngestResponse(BaseModel):
    """Response for XLSX import — preview or created documents."""

    records: list[dict] = []
    document_ids: list[str] = []
    count: int
    errors: list[str] = []
    dry_run: bool


def import_xlsx_impl(db: Database, request: XlsxIngestRequest) -> XlsxIngestResponse:
    """Read an .xlsx spreadsheet; on ``dry_run=False`` create one Document per row.

    Extracted from the ``POST /xlsx`` route so the route and the ``import.xlsx``
    action share the SAME parse-and-create logic. A ``dry_run`` call mutates
    nothing — it only returns the parsed records for inspection.
    """
    from fichero.loaders.xlsx_reader import read_xlsx_records
    from fichero.models import DocType, FileType, Status

    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")
    if path.suffix.lower() not in {".xlsx", ".xls", ".ods"}:
        raise HTTPException(status_code=400, detail=f"Not a spreadsheet file: {path.name}")

    try:
        records = read_xlsx_records(
            path,
            column_map=request.column_map,
            sheet_index=request.sheet_index,
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if request.dry_run:
        return XlsxIngestResponse(
            records=records,
            count=len(records),
            dry_run=True,
        )

    # Non-dry-run: create one Document per row
    from fichero.models import Document
    errors: list[str] = []
    doc_ids: list[str] = []

    for i, rec in enumerate(records):
        # Derive a name: prefer mapped "name" field, else first non-underscore value
        name = rec.get("name") or rec.get("titulo") or rec.get("title") or rec.get("nombre")
        if not name:
            name = next((v for k, v in rec.items() if not k.startswith("_") and v), None)
        if not name:
            errors.append(f"Row {i + 1}: could not determine a name; skipped")
            continue

        doc = Document(
            name=str(name),
            doc_type=DocType.file,
            file_type=FileType.spreadsheet,
            parent_id=request.parent_id,
            metadata={**rec, "xlsx_source": path.name, "xlsx_sheet_index": request.sheet_index},
            status=Status.completed,
        )
        try:
            db.save(doc)
            doc_ids.append(doc.id)
        except Exception as exc:
            errors.append(f"Row {i + 1} ({name!r}): {exc}")

    return XlsxIngestResponse(
        records=records,
        document_ids=doc_ids,
        count=len(doc_ids),
        errors=errors,
        dry_run=False,
    )


@router.post("/xlsx")
async def ingest_xlsx(
    request: XlsxIngestRequest,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> XlsxIngestResponse:
    """
    Read an .xlsx spreadsheet and return its rows as structured records.

    Each data row becomes a dict keyed by column header (or by *column_map*
    when supplied).  Columns without a mapping go into ``_unmapped``.

    With ``dry_run=true`` (default) the records are returned for inspection
    and nothing is written to the library.  With ``dry_run=false``, one
    Document is created per row; the ``name`` field (or the first mapped
    field) is used as the document name.
    """
    return import_xlsx_impl(db, request)


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


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / #2014) — IMPORT domain
# ---------------------------------------------------------------------------
#
# Each action WRAPS the proven ``import_*_impl`` above (iterate-not-replace) and
# routes through ``registry.invoke`` — the single audited write path that writes
# the generic ActionAudit + emits the change event. The typed routes above are
# untouched and stay green; the actions are the *additional* uniform path that
# chat tools / App Intents / tests drive via ``POST /api/actions/invoke``.
#
# Undo semantics:
#   * import.file  — creates ONE document, so it inverts to ``document.delete``
#     (the document-domain action) just like ``document.create``. Reversible.
#   * import.folder / import.xlsx — create MANY documents (and, for a folder,
#     possibly a synthesized collection root). There is no single existing
#     action that deletes the whole set, and a folder ingested under an existing
#     parent has no root to cascade-delete, so these are ``undoable=False`` —
#     the audit still records the created ids for forensics / manual cleanup.

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


def _invert_import_to_delete(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse for single-document imports: delete the created document.

    Mirrors ``document.create``'s inverse — the created id lives in ``after``.
    """
    if not after:
        return None
    document_id = after.get("document_id")
    if not document_id:
        return None
    return ("document.delete", {"doc_id": document_id})


@action(
    "import.file",
    IngestFileRequest,
    domains=["document"],
    undoable=True,
    invert=_invert_import_to_delete,
)
def _action_import_file(
    db: Database, params: IngestFileRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    package_path = Path(ctx.library_path) if ctx.library_path else Path(db.path).parent
    doc = import_file_impl(db, params, package_path)
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[doc.id],
        after={"document_id": doc.id},
        emit_type="document.created",
        document_ids=[doc.id],
    )
    return doc.model_dump(mode="json"), spec


@action(
    "import.folder",
    IngestFolderRequest,
    domains=["document"],
    undoable=False,
)
def _action_import_folder(
    db: Database, params: IngestFolderRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    # The route ingests in a BackgroundTask; the action ingests SYNCHRONOUSLY so
    # the audit can record the created doc ids in ``after``.
    package_path = Path(ctx.library_path) if ctx.library_path else Path(db.path).parent
    docs = import_folder_impl(db, params, package_path)
    doc_ids = [d.id for d in docs]
    spec = ChangeSpec(
        domains=["document"],
        target_ids=doc_ids,
        after={"document_ids": doc_ids},
        emit_type="document.created" if doc_ids else None,
        document_ids=doc_ids,
    )
    return {"document_ids": doc_ids, "count": len(doc_ids)}, spec


@action(
    "import.xlsx",
    XlsxIngestRequest,
    domains=["document"],
    undoable=False,
)
def _action_import_xlsx(
    db: Database, params: XlsxIngestRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    response = import_xlsx_impl(db, params)
    doc_ids = list(response.document_ids)
    # A dry_run mutates nothing → no created ids, no change event.
    spec = ChangeSpec(
        domains=["document"],
        target_ids=doc_ids,
        after={"document_ids": doc_ids} if doc_ids else None,
        emit_type="document.created" if doc_ids else None,
        document_ids=doc_ids,
    )
    return response.model_dump(mode="json"), spec
