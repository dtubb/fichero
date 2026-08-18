"""
Ingest Routes

File and folder ingestion endpoints.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from fichero_server.api.library_header import require_library_path
from fichero_server.api.main import _is_allowed_local_path, db_manager, get_library_database_for_write
from fichero_server.api.auth import actor_from_request
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.security import authz
from fichero_server.db import Database
from fichero_server.importers.derivatives import queue_derivatives
from fichero_server.models import Document, Status

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory task tracking. Terminal tasks are short-lived so a long-running
# embedded engine does not retain every import's document id list indefinitely.
_tasks: dict[str, dict] = {}
_TASK_TTL_SECONDS = 15 * 60
_MAX_TERMINAL_TASKS = 100


def _validate_ingest_path(raw_path: str) -> None:
    if not _is_allowed_local_path(raw_path):
        # Name the path: "not in an allowed location" alone sends the user
        # looking at permissions when the answer is which directory it is in
        # (#4230). This is the ONLY gate — a path that passes here is servable,
        # because ingest and serving now consult the same authority.
        logger.warning("Refusing ingest of a path outside every allowed root: %s", raw_path)
        raise HTTPException(
            status_code=403,
            detail=f"Ingest path is not in an allowed location: {raw_path}",
        )


def _require_ingest_owner(request: Request, library_path: str) -> None:
    if not authz.multiuser_enabled() or getattr(request.state, "bootstrap_auth", False):
        return
    try:
        authz.require_owner(getattr(request.state, "user", None), library_path)
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail="Owner access required for server-path ingest") from exc


def _ingest_action_context(
    request: Request,
    library_path: str,
    *,
    on_progress=None,
    on_document=None,
    should_cancel=None,
) -> ActionContext:
    return ActionContext(
        actor=actor_from_request(request),
        library_path=library_path,
        is_bootstrap=bool(getattr(request.state, "bootstrap_auth", False)),
        on_progress=on_progress,
        on_document=on_document,
        should_cancel=should_cancel,
    )


def _prune_tasks(now: float | None = None) -> None:
    """Discard expired terminal task results and cap the remaining history."""
    now = time.monotonic() if now is None else now
    terminal = [
        (task_id, task)
        for task_id, task in _tasks.items()
        if task["status"] in {"completed", "failed", "cancelled"}
    ]
    for task_id, task in terminal:
        if now - task["finished_at"] >= _TASK_TTL_SECONDS:
            del _tasks[task_id]

    remaining = sorted(
        (
            (task["finished_at"], task_id)
            for task_id, task in _tasks.items()
            if task["status"] in {"completed", "failed", "cancelled"}
        )
    )
    for _, task_id in remaining[:-_MAX_TERMINAL_TASKS]:
        del _tasks[task_id]


# Request/Response models
class IngestFileRequest(BaseModel):
    """Request model for file ingestion."""

    path: str
    parent_id: Optional[str] = None
    copy_mode: bool = False  # Link (default) or copy into library
    mode: Literal["link", "copy", "move"] | None = None
    extract_text: bool = True
    # Deferred by default (2026-08-09): embeddings are produced by the
    # post-ingest derivative stage (importers/derivatives.py), so the import
    # returns as soon as rows land and the document stays `pending` until
    # embedded. Pass true to embed inline (blocking) — tests/CLI only.
    auto_embed: bool = False


class IngestFolderRequest(BaseModel):
    """Request model for folder ingestion."""

    path: str
    parent_id: Optional[str] = None
    copy_mode: bool = False
    mode: Literal["link", "copy", "move"] | None = None
    recursive: bool = True
    extract_text: bool = True
    # Deferred by default (2026-08-09) — see IngestFileRequest.auto_embed.
    # The old inline default made a first import pay the ~19s model load
    # plus per-page compute before the request finished; searchability now
    # arrives moments later via the derivative stage instead.
    auto_embed: bool = False


class IngestTaskResponse(BaseModel):
    """Response for async ingest task."""

    task_id: str
    status: str
    path: str


class IngestTaskStatus(BaseModel):
    """Status of an ingest task."""

    task_id: str
    status: str  # pending, running, cancelling, cancelled, completed, failed
    path: str
    progress: float  # 0.0 to 1.0
    total: int
    processed: int
    error: Optional[str] = None
    document_ids: list[str] = []
    failed: int = 0
    failures: list[dict[str, str]] = []
    files_per_second: float = 0.0


class IngestCancelResponse(BaseModel):
    task_id: str
    status: str


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
    from fichero_server.importers.ingest import ingest_file as do_ingest, IngestMode

    path = Path(request.path)
    _validate_ingest_path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}")
    if path.is_symlink():
        raise HTTPException(status_code=400, detail=f"Refusing to ingest symlinked file: {request.path}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    mode = IngestMode(request.mode) if request.mode else (
        IngestMode.COPY if request.copy_mode else IngestMode.LINK
    )
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
        # Thumbnails happen AFTER the row lands, on their own bounded pool
        # (#4225). Import stays fast; the row gains its thumbnail in place via
        # the document.updated the derivative stage emits.
        queue_derivatives([doc], library_path=package_path, db=db)
        return doc
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ingest failed: {path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class _InProcessManifestClient:
    """``ManifestApiClient`` that calls THIS server's own routes in process.

    The folder-drop UX path (2026-08-17): a dropped folder carrying
    ``manifest.jsonl`` routes through the manifest importer, which speaks the
    same FastAPI routes the app does. In process means a ``TestClient`` bound
    to our own ``app`` object — no network, no self-connect deadlock — and the
    server authorizes itself with its own bootstrap token
    (``initialize_token`` is an idempotent read once the key file exists).
    """

    def __init__(self, library_path: str) -> None:
        from fastapi.testclient import TestClient

        from fichero_server.api.auth import initialize_token
        from fichero_server.api.main import app
        from fichero_server.api.uds_transport import UDS_TRANSPORT_SCOPE_KEY

        # The scope builder auth.py's loopback rule documents: only a
        # server-side transport may stamp `fichero.transport`, and this shim
        # IS one — it exists solely inside this process, wrapping our own app
        # object. Without the stamp the middleware correctly answers
        # "loopback only" (live failure, 2026-08-17 first drop attempt):
        # TestClient's synthetic host is trusted under pytest alone.
        async def _inmemory_app(scope, receive, send):
            if scope.get("type") == "http":
                scope = {**scope, UDS_TRANSPORT_SCOPE_KEY: "inmemory"}
            await app(scope, receive, send)

        self._client = TestClient(_inmemory_app)
        self._headers = {
            "Authorization": f"Bearer {initialize_token()}",
            "X-Fichero-Library-Path": library_path,
        }

    def request(self, method: str, path: str, body=None):
        url = f"/api{path}"
        resp = self._client.request(method, url, json=body, headers=self._headers)
        # Preview-warm GETs are best-effort, mirroring the CLI transport: an
        # unrenderable image is a warning, never an import failure.
        if method == "GET" and path.startswith("/storage/") and resp.status_code >= 400:
            return None
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {url} -> {resp.status_code}: {resp.text[:300]}")
        if resp.content:
            try:
                return resp.json()
            except ValueError:
                return None
        return None


def _is_sidecar_like(path: Path) -> bool:
    """The staging sidecars share the image's stem — never stamp one as the
    document's path."""
    name = path.name.lower()
    return name.endswith((".json", ".txt", ".jsonl", ".xmp"))


def _import_manifest_folder(
    db: Database,
    manifest_path: Path,
    request: "IngestFolderRequest",
    package_path: Path,
    on_progress=None,
    manifest_client=None,
) -> list[Document]:
    """A dropped folder that carries ``manifest.jsonl`` IS a corpus import.

    Runs the same importer as ``fichero import-manifest`` — folders, pages,
    transcripts into ``page_content``, entities, claims — through the app's
    own routes, so change events fire and the sidebar populates live. The
    drop target (``request.parent_id``) becomes the corpus root's parent, and
    the drop's copy/link choice is honoured as the ingest mode.

    ``manifest_client`` is injectable for tests; production builds the
    in-process client above.
    """
    from fichero_server.importers.manifest_import import import_manifest

    client = manifest_client or _InProcessManifestClient(str(package_path))
    ingest_mode = request.mode or ("copy" if request.copy_mode else "link")
    summary = import_manifest(
        client,
        manifest_path,
        str(package_path),
        ingest_mode=ingest_mode,
        root_parent_id=request.parent_id,
        on_progress=on_progress,
    )
    for warning in summary.warnings:
        logger.warning("manifest import: %s", warning)
    # SEEN, not just created: a re-drop of an already-imported corpus must
    # REPAIR it (stamp pathless pages, queue their thumbnails) instead of
    # skipping everything and returning empty (2026-08-17 live: a failed
    # delete + idempotent skip made the second drop a silent no-op).
    docs = [
        doc
        for doc_id in summary.seen_document_ids
        if (doc := db.get(Document, doc_id)) is not None
    ]
    # ENGINE-RECORDED source paths (#4230 contract): the routes rightly
    # refuse client-supplied absolute paths, so linked pages arrive pathless
    # — and pathless means no thumbnails (2026-08-17 first live drop). This
    # is the engine, holding the db, recording a path it verified against
    # the SAME ingest authority plain link-ingest uses — exactly the "path
    # the engine itself wrote at ingest" the serving allowlist trusts.
    from fichero_server.importers.manifest_import import preferred_image
    from fichero_server.security.path_security import is_allowed_ingest_path

    drop_root = Path(request.path).expanduser()
    for doc in docs:
        if doc.path:
            continue
        # FIRST authority: the dropped folder itself. The request already
        # passed _validate_ingest_path for it, and the staging convention
        # puts each page's image (a symlink) right there — so the stamp
        # cannot be defeated by unresolvable security-scoped bookmarks for
        # the EXTERNAL source tree (2026-08-18 live: every bookmark for
        # ~/code/marshall_diaries failed to resolve in the engine process
        # and all 153 stamps declined).
        source: str | None = None
        in_drop = next(
            (c for c in sorted(drop_root.glob(f"{doc.name}.*"))
             if c.is_file() and not _is_sidecar_like(c)),
            None,
        )
        if in_drop is not None:
            source = str(in_drop)
        else:
            image = preferred_image({"images": (doc.metadata or {}).get("images") or []})
            candidate = image.get("source_path") if image else None
            if candidate and Path(str(candidate)).is_file() and is_allowed_ingest_path(candidate):
                source = str(candidate)
        if source:
            doc.path = source
            db.save(doc)
    queue_derivatives(docs, library_path=package_path, db=db)
    logger.info(
        "Manifest folder import: %s -> %d documents, %d entities, %d skipped",
        manifest_path,
        summary.documents_created,
        summary.entities_created,
        summary.documents_skipped,
    )
    return docs


def import_folder_impl(
    db: Database,
    request: IngestFolderRequest,
    package_path: Path,
    on_progress=None,
    on_document=None,
    should_cancel=None,
) -> list[Document]:
    """Validate + synchronously ingest a folder. Returns the created Documents.

    The ``POST /folder`` route runs this in a BackgroundTask (returning a
    task_id); the ``import.folder`` action runs it synchronously so it can audit
    the created doc ids. Both share this one validated ingest.

    ``on_progress(current, total)`` fires after every file (advance a progress
    bar); ``on_document(doc)`` fires once per successfully ingested file so the
    route can emit a per-file ``document.created`` change event and the sidebar
    populates incrementally (#4065 — folder-of-folders no longer shows a
    blocking spinner until the whole import finishes).
    """
    from fichero_server.importers.ingest import ingest_folder as do_ingest, IngestMode

    path = Path(request.path)
    _validate_ingest_path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {request.path}")
    if path.is_symlink():
        raise HTTPException(status_code=400, detail=f"Refusing to ingest symlinked folder: {request.path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    # A folder carrying manifest.jsonl is a CORPUS, not a pile of files —
    # route it through the manifest importer (Daniel 2026-08-17: "is there a
    # way in UX to do it. if not, that's priority"). Same importer as the
    # CLI's import-manifest; a plain folder is untouched by this branch.
    manifest_path = path / "manifest.jsonl"
    if manifest_path.is_file():
        return _import_manifest_folder(
            db, manifest_path, request, package_path, on_progress=on_progress
        )

    mode = IngestMode(request.mode) if request.mode else (
        IngestMode.COPY if request.copy_mode else IngestMode.LINK
    )
    docs = do_ingest(
        path,
        mode=mode,
        parent_id=request.parent_id,
        recursive=request.recursive,
        extract_text=request.extract_text,
        auto_embed=request.auto_embed,
        on_progress=on_progress,
        on_document=on_document,
        should_cancel=should_cancel,
        db=db,
        package_path=package_path,
    )
    # Queued after the whole folder lands rather than per file: the queue is
    # bounded (#4225) and the ingest loop must not block on it.
    queue_derivatives(docs, library_path=package_path, db=db)
    return docs


# Routes


@router.post("/file")
async def ingest_file(
    request: IngestFileRequest,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> Document:
    """
    Ingest a single file into the library.

    Returns the created Document immediately.
    """
    _require_ingest_owner(http_request, x_fichero_library_path)
    result = await asyncio.to_thread(
        registry.invoke,
        db,
        "import.file",
        request.model_dump(mode="json"),
        _ingest_action_context(http_request, x_fichero_library_path),
    )
    return Document.model_validate(result.result)


@router.post("/folder")
async def ingest_folder(
    request: IngestFolderRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
    x_fichero_library_path: str = Depends(require_library_path),
) -> IngestTaskResponse:
    """
    Ingest a folder into the library.

    Returns immediately with a task_id. Use /status/{task_id} to check progress.
    """
    _require_ingest_owner(http_request, x_fichero_library_path)
    path = Path(request.path)
    _validate_ingest_path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {request.path}")
    if path.is_symlink():
        raise HTTPException(status_code=400, detail=f"Refusing to ingest symlinked folder: {request.path}")

    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    # Create task
    task_id = uuid4().hex[:12]
    _tasks[task_id] = {
        "status": "pending",
        "path": str(path),
        "progress": 0.0,
        "total": 0,
        "processed": 0,
        "error": None,
        "document_ids": [],
        "failed": 0,
        "failures": [],
        "files_per_second": 0.0,
        "cancel_requested": False,
        "library_path": x_fichero_library_path,
    }
    _prune_tasks()

    # Background ingest (capture db and package_path for use in background task)
    def do_background_ingest():
        # Everything — INCLUDING the database acquisition — inside the try
        # (2026-08-09 wedge 4.8): `get_database` raises on migration/seed
        # failure, and when it did the task dict froze at "pending" forever
        # while the app polled /status indefinitely. Every exit path now
        # lands in a terminal task state.
        bg_db = None

        def on_progress(current: int, total: int):
            _tasks[task_id]["processed"] = current
            _tasks[task_id]["total"] = total
            _tasks[task_id]["progress"] = current / total if total > 0 else 1.0
            elapsed = time.monotonic() - _tasks[task_id]["started_at"]
            _tasks[task_id]["files_per_second"] = current / elapsed if elapsed > 0 else 0.0

        # Progressive sidebar population (#4065): for each successfully ingested
        # document, accumulate its id in the task's running ``document_ids``
        # (so a status poll returns the growing list, not an empty one until
        # completion) AND emit a per-file ``document.created`` change event so
        # the DocumentStore's change stream patches the sidebar incrementally
        # — the spinner stops being the only signal and items appear as they
        # land. Completion is still signalled explicitly below + by the
        # action's trailing bulk event, so a lost per-file event is recovered
        # at the end (#4067).
        def on_document(doc):
            try:
                _tasks[task_id]["document_ids"].append(doc.id)
            except Exception:  # pragma: no cover - defensive
                pass
            if doc.status == Status.failed:
                metadata = doc.metadata or {}
                error = str(
                    metadata.get("ingest_error")
                    or metadata.get("text_extraction_error")
                    or "Import failed"
                )
                _tasks[task_id]["failed"] += 1
                _tasks[task_id]["failures"].append(
                    {"path": doc.path or doc.name, "error": error, "document_id": doc.id}
                )
            try:
                from fichero_server.api.change_stream import emit_change

                emit_change(
                    x_fichero_library_path,
                    type="document.created",
                    document_ids=[doc.id],
                    # #4205: lets the client skip fetching documents it cannot
                    # be showing. Omitted rather than defaulted when the
                    # document has no parent_id, because absent means
                    # "unknown", and a wrong "root" would file imported files
                    # at the top level.
                    document_parents=({doc.id: doc.parent_id} if doc.parent_id else {}),
                    actor=actor_from_request(http_request),
                    origin_window=getattr(http_request.state, "origin_window", None),
                    origin_user=actor_from_request(http_request),
                )
            except Exception as exc:  # pragma: no cover - best-effort
                logger.debug("per-file emit_change failed (ignored): %s", exc)

        try:
            _tasks[task_id]["started_at"] = time.monotonic()
            # Fresh handle for the background thread, not the request-scoped
            # one — avoids stale/contended connection state on long folder
            # ingests (#1216). Inside the try, see above.
            bg_db = db_manager.get_database(x_fichero_library_path)
            if not _tasks[task_id]["cancel_requested"]:
                _tasks[task_id]["status"] = "running"
                logger.info("ingest.task task_id=%s status=running path=%s", task_id, path)
            # Route through the shared impl so the background task and the
            # audited ``import.folder`` action ingest via the SAME code path.
            result = registry.invoke(
                bg_db,
                "import.folder",
                request.model_dump(mode="json"),
                _ingest_action_context(
                    http_request,
                    x_fichero_library_path,
                    on_progress=on_progress,
                    on_document=on_document,
                    should_cancel=lambda: _tasks[task_id]["cancel_requested"],
                ),
            )
            doc_ids = result.result["document_ids"]
            cancelled = _tasks[task_id]["cancel_requested"]
            _tasks[task_id]["status"] = "cancelled" if cancelled else "completed"
            _tasks[task_id]["finished_at"] = time.monotonic()
            if not cancelled:
                _tasks[task_id]["progress"] = 1.0
            _tasks[task_id]["document_ids"] = list(
                dict.fromkeys(_tasks[task_id]["document_ids"] + doc_ids)
            )
            logger.info(
                "ingest.task task_id=%s status=%s path=%s files=%d",
                task_id, _tasks[task_id]["status"], path, len(doc_ids),
            )
        except BaseException as e:  # noqa: BLE001 — a dying worker THREAD must
            # still leave a terminal, pollable state (2026-08-09 wedge 4.9):
            # `except Exception` let MemoryError/SystemExit escape and the app
            # polled a permanently-"running" task. Re-raise the interpreter's
            # own exits after recording.
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["finished_at"] = time.monotonic()
            _tasks[task_id]["error"] = str(e) or type(e).__name__
            logger.error(f"Folder ingest failed: {path}: {e!r}")
            if not isinstance(e, Exception):
                raise

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
    from fichero_server.loaders.xlsx_reader import read_xlsx_records
    from fichero_server.models import DocType, FileType, Status

    path = Path(request.path)
    _validate_ingest_path(request.path)
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
    from fichero_server.models import Document
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
    http_request: Request,
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
    _require_ingest_owner(http_request, x_fichero_library_path)
    result = registry.invoke(
        db,
        "import.xlsx",
        request.model_dump(mode="json"),
        _ingest_action_context(http_request, x_fichero_library_path),
    )
    return XlsxIngestResponse.model_validate(result.result)


@router.get("/status/{task_id}")
async def get_ingest_status(
    task_id: str,
    x_fichero_library_path: str = Depends(require_library_path),
) -> IngestTaskStatus:
    """Get status of an ingest task."""
    _prune_tasks()
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    task = _tasks[task_id]
    if task["library_path"] != x_fichero_library_path:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return IngestTaskStatus(
        task_id=task_id,
        status=task["status"],
        path=task["path"],
        progress=task["progress"],
        total=task["total"],
        processed=task["processed"],
        error=task.get("error"),
        document_ids=task.get("document_ids", []),
        failed=task.get("failed", 0),
        failures=task.get("failures", []),
        files_per_second=task.get("files_per_second", 0.0),
    )


@router.post("/folder/{task_id}/cancel")
async def cancel_ingest(
    task_id: str,
    http_request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> IngestCancelResponse:
    """Request cancellation between committed files; repeated calls are safe."""
    _require_ingest_owner(http_request, x_fichero_library_path)
    task = _tasks.get(task_id)
    if task is None or task["library_path"] != x_fichero_library_path:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    if task["status"] not in {"completed", "failed", "cancelled"}:
        task["cancel_requested"] = True
        task["status"] = "cancelling"
    return IngestCancelResponse(task_id=task_id, status=task["status"])


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

from fichero_server.actions.registry import ChangeSpec, action  # noqa: E402


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
    # atomic=False (2026-08-09): the default atomic=True wrapped the ENTIRE
    # file ingest — text extraction, both PDF parses, every page save, every
    # page embedding, and (before the pre-warm fix) the 19s model load — in
    # ONE transaction holding the DuckDB gate. Every reader (thumbnails,
    # get_children, the loop itself via the storage routes) queued behind one
    # file for minutes. The folder action has been atomic=False for exactly
    # this reason; ingest_file's own writes commit per-step, and the undo
    # inversion (delete the created doc) does not depend on atomicity.
    atomic=False,
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
        # #4205: the document is in hand here, so the client need not fetch it
        # to learn where it belongs. Omitted when parent_id is None — absent
        # means "unknown", never "root".
        document_parents=({doc.id: doc.parent_id} if doc.parent_id else {}),
    )
    return doc.model_dump(mode="json"), spec


@action(
    "import.folder",
    IngestFolderRequest,
    domains=["document"],
    undoable=False,
    # A folder is a resumable sequence of committed files/batches. Wrapping the
    # whole import hides every row behind one transaction until the last file.
    atomic=False,
)
def _action_import_folder(
    db: Database, params: IngestFolderRequest, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    # The route ingests in a BackgroundTask; the action ingests SYNCHRONOUSLY so
    # the audit can record the created doc ids in ``after``.
    package_path = Path(ctx.library_path) if ctx.library_path else Path(db.path).parent
    # Forward the route's streaming hooks (#4065) so per-file progress + the
    # ``on_document`` callback fire DURING the ingest, not only at completion.
    docs = import_folder_impl(
        db,
        params,
        package_path,
        on_progress=ctx.on_progress,
        on_document=ctx.on_document,
        should_cancel=ctx.should_cancel,
    )
    doc_ids = [d.id for d in docs]
    spec = ChangeSpec(
        domains=["document"],
        target_ids=doc_ids,
        after={"document_ids": doc_ids},
        emit_type="document.created" if doc_ids else None,
        document_ids=doc_ids,
        # #4205: this trailing bulk event repeats every id from the import. If
        # it carried no parents the client would treat all of them as
        # "unknown, fetch it" and re-flood itself with the fetches the
        # per-file events just let it skip — the optimisation would survive
        # the stream and die at the end. The Documents are in hand here, so
        # the parents cost nothing.
        document_parents={d.id: d.parent_id for d in docs if d.parent_id},
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
