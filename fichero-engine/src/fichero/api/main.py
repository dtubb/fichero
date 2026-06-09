"""
Fichero FastAPI Application

REST API backend exposing the Fichero data layer (DuckDB + LanceDB).

Usage:
    # Direct
    uvicorn fichero.api.main:app --reload

    # Via CLI
    fichero serve

Environment Variables:
    FICHERO_VALIDATE_MODELS: Set to "1" to validate Python/Swift model sync on startup
    TOKENIZERS_PARALLELISM: Set to "false" to disable tokenizer parallelism (avoids fork warnings)
"""

import os
import sys
import warnings

# Disable tokenizers parallelism so the Rust tokenizer's thread pool
# doesn't deadlock across a fork (subprocess spawns count). Must be set
# before any import that pulls in transformers / tokenizers.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Suppress LangChain's `allowed_objects` PendingDeprecationWarning (#1083).
# It fires at module-import time from langgraph.checkpoint.serde.encrypted's
# `LC_REVIVER = Reviver()` call (no `allowed_objects` argument). The
# JsonPlusSerializer constructor doesn't expose this option, so we cannot
# pass an explicit value through — the only fix is to suppress the warning
# *before* langgraph's checkpoint serde module is first imported. Must run
# before any fichero.* import that transitively pulls in langgraph
# (e.g. fichero.db -> workflows -> langgraph).
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r".*allowed_objects.*",
        category=LangChainPendingDeprecationWarning,
    )
except ImportError:
    # langchain_core not installed in some test/lint environments — skip.
    pass

# Route the kreuzberg extraction cache to ~/Library/Caches/ and run the
# one-time legacy-location migration. Imported here (not lazily via loaders)
# so the side effect fires at engine startup regardless of whether the
# user triggers an extraction this session.
from fichero.loaders import kreuzberg_cache  # noqa: F401, E402

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Sequence

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from fichero.db import Database, db_manager
from fichero.models import (
    EmbeddingStatsResponse,
    HealthResponse,
    LibraryStatsResponse,
)
from fichero.paths import migrate_legacy_engine_state
from fichero.remote_backend import build_remote_backend_status

logger = logging.getLogger(__name__)


def _install_warning_filters() -> None:
    """Suppress lancedb's over-broad fork-safety advisory.

    lancedb registers an ``os.register_at_fork(before=...)`` hook that
    warns "lance is not fork-safe" on EVERY fork. That matters for
    multiprocessing (fork + keep running Python with inherited lancedb
    state) — but the engine uses none: all concurrency is
    ``ThreadPoolExecutor``, and the only forks are subprocess fork+exec
    (fm-bridge, pandoc, etc.) where the child immediately ``exec()``s
    and never touches inherited lancedb state. Without this the
    advisory floods the workflow log on every subprocess spawn. (#1028)
    """
    warnings.filterwarnings(
        "ignore",
        message="lance is not fork-safe",
        category=UserWarning,
    )


# Registered after imports — the filter only needs to be in place
# before a fork, not before lancedb's import.
_install_warning_filters()


class _HealthAccessLogFilter(logging.Filter):
    """Drop uvicorn access-log lines for ``/api/health`` polls.

    The SwiftUI app polls ``/api/health`` continuously; logging every
    poll floods the backend log and buries the lines that matter when
    diagnosing a real problem (#1000). The health endpoint still runs —
    only its access-log noise is suppressed.

    uvicorn's ``uvicorn.access`` records carry the request line in
    ``record.args`` as ``(client, method, path, http_version, status)``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            path = str(args[2])
            if path == "/api/health" or path.startswith("/api/health?"):
                return False
        return True


def _install_access_log_filter() -> None:
    """Attach the health-poll filter to uvicorn's access logger.

    Called from the FastAPI lifespan startup so it runs *after* uvicorn
    has configured ``uvicorn.access`` — the filter is added to the logger
    itself, so it survives regardless of which handlers are attached.
    """
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _HealthAccessLogFilter) for f in access_logger.filters):
        access_logger.addFilter(_HealthAccessLogFilter())


def _validate_model_sync() -> bool:
    """Validate that Python and Swift models are in sync.

    Returns True if sync is valid, False if there are issues.
    """
    try:
        import subprocess

        # Find the validation script
        api_dir = Path(__file__).parent
        project_root = api_dir.parent.parent.parent
        script_path = project_root / "scripts" / "validate_model_sync.py"

        if not script_path.exists():
            logger.warning(f"Model validation script not found: {script_path}")
            return True  # Don't block startup if script is missing

        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )

        if result.returncode != 0:
            logger.error("Model sync validation failed!")
            logger.error(result.stdout)
            if result.stderr:
                logger.error(result.stderr)
            return False

        logger.info("Model sync validation passed")
        return True

    except Exception as e:
        logger.warning(f"Model validation check failed: {e}")
        return True  # Don't block startup on validation errors


def _seed_builtin_providers() -> None:
    """Ensure Apple Intelligence (on-device) provider exists — no API key, always available on macOS."""
    try:
        from fichero.app_db import get_app_db
        from fichero.models import Model, Provider, ProviderType

        app_db = get_app_db()
        existing_providers = app_db.list_providers()
        existing_types = {p.provider_type for p in existing_providers}
        apple_provider: Provider | None = None
        if ProviderType.apple not in existing_types:
            apple_provider = Provider(
                name="Apple Intelligence",
                provider_type=ProviderType.apple,
                enabled=True,
            )
            app_db.save_provider(apple_provider)
            logger.info("Seeded built-in Apple Intelligence provider")
        else:
            # Migrate the legacy "Apple" name → "Apple Intelligence" so users
            # who installed before #761 don't see the duplicate-looking entry
            # next to "Apple Vision (On-Device)" in the workflow picker.
            for p in existing_providers:
                if p.provider_type == ProviderType.apple:
                    apple_provider = p
                    if p.name == "Apple":
                        p.name = "Apple Intelligence"
                        app_db.save_provider(p)
                        logger.info(
                            "Renamed Apple provider to Apple Intelligence (#761)"
                        )
                    break

        # Seed built-in models for the Apple provider so Settings → Defaults
        # has something to pick. Without this, picking Apple as Audio (or
        # any other) provider leaves Model dropdown empty. (#762)
        #
        # Dedup: collapse any pre-existing duplicates by model_id BEFORE
        # seeding. Earlier code shipped two rows with model_id="apple-
        # intelligence" — one with empty capabilities and one with
        # ["text"]. Settings' model picker rendered both as "Apple
        # Intelligence" (#806). Keep the row with the richest capabilities
        # set; delete the others.
        if apple_provider is not None:
            existing = list(app_db.list_models(apple_provider.id))
            from collections import defaultdict

            by_model_id: dict[str, list] = defaultdict(list)
            for m in existing:
                by_model_id[m.model_id].append(m)
            for model_id, rows in by_model_id.items():
                if len(rows) <= 1:
                    continue
                # Pick the row with the most capabilities as canonical;
                # tie-break on earliest created_at for stability.
                rows.sort(key=lambda r: (-len(r.capabilities or []), r.created_at or 0))
                keep = rows[0]
                for dup in rows[1:]:
                    try:
                        app_db.delete_model(dup.id)
                        logger.info(
                            "Collapsed duplicate Apple model %s (%s) — kept %s",
                            dup.name,
                            dup.id,
                            keep.id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Could not delete duplicate model %s: %s", dup.id, exc
                        )

            existing_model_ids = {
                m.model_id for m in app_db.list_models(apple_provider.id)
            }
            # Three distinct Apple rows (#935 / #937): users who delete one
            # row and re-add another deserve clear capability labels — the
            # earlier conflated "Apple Vision Transcribe" with caps
            # [vision, transcription, audio] was ambiguous and caused
            # capability-filter bugs (#940). Split into:
            #   - apple-intelligence — text LLM (Foundation Models)
            #   - apple-vision       — image OCR
            #   - apple-speech       — speech-to-text transcription
            # is_default=True on apple-intelligence so the Defaults pane
            # has a sensible starting pick for $small and text.
            builtins = [
                Model(
                    provider_id=apple_provider.id,
                    name="Apple Intelligence (Foundation Models)",
                    model_id="apple-intelligence",
                    capabilities=["text"],
                    is_default=True,
                ),
                Model(
                    provider_id=apple_provider.id,
                    name="Apple Vision (OCR)",
                    model_id="apple-vision",
                    capabilities=["vision"],
                ),
                Model(
                    provider_id=apple_provider.id,
                    name="Apple Speech (Transcription)",
                    model_id="apple-speech",
                    capabilities=["audio", "transcription"],
                ),
            ]
            for model in builtins:
                if model.model_id not in existing_model_ids:
                    app_db.save_model(model)
                    logger.info(
                        "Seeded built-in Apple model: %s (%s)",
                        model.name,
                        model.model_id,
                    )

            # Ensure AI Defaults are populated so first-run workflows
            # don't blow up at \$small resolution (#932 / #933). Only sets
            # keys that are currently missing — never overwrites a user
            # configuration. Apple Intelligence is the natural pick on
            # macOS 26+ Apple Silicon (free, on-device, always available).
            _ensure_default_ai_defaults(app_db, apple_provider.id)
            _repair_known_bad_ai_defaults(app_db)
    except Exception as exc:
        logger.warning("Could not seed built-in providers: %s", exc)


def _ensure_default_ai_defaults(app_db, apple_provider_id: str) -> None:
    """Populate AI Defaults if missing.

    On a fresh install the `default_*_provider` / `default_*_model`
    settings are unset, so workflows using $small / $medium / $large
    placeholders fail immediately with "no default model configured"
    (#932 first-run blocker).

    This sets sensible defaults:
      - text / small / large → apple-intelligence
      - medium               → openrouter/openai/gpt-4o-mini
      - vision               → apple-vision
      - audio                → apple-speech

    Only writes a key when it is currently unset; user configuration is
    never overwritten. (#933 — Reset Defaults must not erase user choices
    on its own; explicit per-pane Reset buttons handle that case.)
    """
    apple_type = "apple"
    pairs = [
        ("default_text_provider", apple_type),
        ("default_text_model", "apple-intelligence"),
        ("default_small_provider", apple_type),
        ("default_small_model", "apple-intelligence"),
        ("default_medium_provider", "openrouter"),
        ("default_medium_model", "openai/gpt-4o-mini"),
        ("default_large_provider", apple_type),
        ("default_large_model", "apple-intelligence"),
        ("default_vision_provider", apple_type),
        ("default_vision_model", "apple-vision"),
        ("default_audio_provider", apple_type),
        ("default_audio_model", "apple-speech"),
    ]
    written: list[str] = []
    for key, value in pairs:
        if not app_db.get_setting(key):
            app_db.set_setting(key, value)
            written.append(key)
    if written:
        logger.info(
            "Seeded Apple Intelligence as default for %d AI tier keys: %s",
            len(written),
            ", ".join(written),
        )


def _repair_known_bad_ai_defaults(app_db) -> None:
    """Repair stale tier defaults from older broken seeds."""
    large_provider = app_db.get_setting("default_large_provider")
    large_model = app_db.get_setting("default_large_model")
    if large_provider == "openrouter" and large_model == "openrouter/free":
        app_db.set_setting("default_large_provider", "apple")
        app_db.set_setting("default_large_model", "apple-intelligence")
        logger.warning(
            "Repaired stale AI default $large from openrouter/openrouter/free "
            "to apple/apple-intelligence."
        )


def _collapse_duplicate_providers() -> None:
    """One-time cleanup for #704: collapse duplicate provider rows that
    share the same (name, provider_type). Keeps the earliest row (by
    created_at) and re-parents any models attached to duplicates before
    deleting the dupes.
    """
    try:
        from fichero.app_db import get_app_db
        from collections import defaultdict

        app_db = get_app_db()
        providers = app_db.list_providers()
        by_key: dict[tuple, list] = defaultdict(list)
        for p in providers:
            by_key[(p.provider_type, p.name)].append(p)

        for key, rows in by_key.items():
            if len(rows) <= 1:
                continue
            rows.sort(key=lambda r: r.created_at or 0)
            canonical = rows[0]
            duplicates = rows[1:]

            # Collect model IDs to reparent BEFORE issuing any writes.
            # Interleaving list_models() cursors with UPDATE/DELETE on the
            # same DuckDB connection can leave a pending query result and
            # break subsequent fetchone() calls on unrelated endpoints.
            reparent_pairs: list[tuple[str, str]] = []
            for dup in duplicates:
                for model in app_db.list_models(dup.id):
                    reparent_pairs.append((canonical.id, model.id))

            for canonical_id, model_id in reparent_pairs:
                app_db.reparent_model(model_id, canonical_id)
            for dup in duplicates:
                app_db.delete_provider(dup.id)
            app_db.conn.commit()
            logger.info(
                "Collapsed %d duplicate %s providers named %r into %s (reparented %d models)",
                len(duplicates),
                key[0].value if hasattr(key[0], "value") else key[0],
                key[1],
                canonical.id,
                len(reparent_pairs),
            )
    except Exception as exc:
        logger.warning("Provider duplicate collapse failed: %s", exc)


def _prewarm_embeddings() -> None:
    """Download + initialise the embeddings model so it's ready before first use."""
    try:
        from fastembed import TextEmbedding

        # Use the embedder's own canonical default (single source of truth) so
        # pre-warm always loads the same model the real embedder uses (#1524).
        from fichero.db_embeddings import DEFAULT_MODEL
        from fichero.local_models import MODELS_BASE

        # Guard against an unsupported model name (e.g. a stale setting, or a
        # default that fastembed dropped support for): fall back to the
        # canonical default rather than failing the whole pre-warm (#1524).
        model_name = DEFAULT_MODEL
        try:
            supported = {m["model"] for m in TextEmbedding.list_supported_models()}
            if model_name not in supported:
                logger.warning(
                    "Embedding model %s not supported by fastembed; "
                    "falling back to %s",
                    model_name,
                    DEFAULT_MODEL,
                )
                model_name = DEFAULT_MODEL
        except Exception:  # noqa: BLE001 — never let the guard block pre-warm
            pass

        cache_dir = MODELS_BASE / "embeddings"
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Pre-warming embeddings model: %s", model_name)
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message=".*multilingual-e5-large.*pooling.*"
            )
            TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))
        logger.info("Embeddings model ready")
    except Exception as exc:
        logger.warning("Embeddings pre-warm failed (will retry on first use): %s", exc)


def _discover_known_library_paths() -> list[str]:
    """Return known .fichero library roots for startup maintenance."""
    try:
        from fichero.__main__ import _discover_libraries

        return list(_discover_libraries())
    except Exception:
        logger.exception("Could not discover known libraries for startup recovery")
        return []


async def _recover_stale_runs_on_startup(
    library_paths: Sequence[str] | None = None,
) -> int:
    """Recover stale workflow runs in known libraries during engine startup."""
    from fichero.workflows.activity_store import ActivityStore

    recovered_total = 0
    targets = (
        list(library_paths)
        if library_paths is not None
        else _discover_known_library_paths()
    )
    for library_path in targets:
        try:
            package_path = Path(library_path)
            if package_path.suffix != ".fichero":
                continue
            db_path = package_path / "fichero.duckdb"
            if not db_path.exists():
                continue
            recovered = await ActivityStore(str(db_path)).recover_stale_runs()
            recovered_total += recovered
            if recovered:
                logger.info(
                    "Startup stale-run recovery: recovered %d run(s) in %s",
                    recovered,
                    library_path,
                )
        except Exception:
            logger.exception(
                "Startup stale-run recovery failed for %s (continuing)",
                library_path,
            )
    return recovered_total


async def _watch_parent_process() -> None:
    """If FICHERO_PARENT_PID is set, exit when that PID disappears.

    Belt-and-braces with the Swift side's applicationWillTerminate path —
    catches SIGKILL / crash / force-quit cases where the Swift app can't
    cleanly shut us down.
    """
    import asyncio
    import signal

    parent_pid_str = os.environ.get("FICHERO_PARENT_PID")
    if not parent_pid_str:
        return
    try:
        parent_pid = int(parent_pid_str)
    except ValueError:
        return

    while True:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return
        try:
            os.kill(parent_pid, 0)  # signal 0 just probes existence
        except (ProcessLookupError, PermissionError, OSError):
            logger.warning(
                "Parent PID %d gone — engine self-terminating to free port",
                parent_pid,
            )
            os.kill(os.getpid(), signal.SIGTERM)
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    import asyncio

    # Startup: optionally validate model sync
    if os.environ.get("FICHERO_VALIDATE_MODELS") == "1":
        logger.info("Validating Python/Swift model sync...")
        if not _validate_model_sync():
            logger.warning(
                "Model sync issues detected! Run './scripts/sync_openapi_schema.sh' to fix."
            )

    # Startup: initialize database manager
    logger.info("Fichero API starting up...")
    logger.info("Engine binary: %s", sys.executable)
    logger.info("DatabaseManager initialized")
    remote_backend_status = build_remote_backend_status()
    app.state.remote_backend = remote_backend_status
    if remote_backend_status.enabled:
        logger.info(
            "Remote backend mode enabled via %s; token_configured=%s; "
            "library_path_configured=%s",
            remote_backend_status.connection_model,
            remote_backend_status.token_configured,
            remote_backend_status.library_path_configured,
        )
        for warning in remote_backend_status.warnings:
            logger.warning("Remote backend setup: %s", warning)
    migrated_entries = migrate_legacy_engine_state()
    if migrated_entries:
        logger.info(
            "Migrated %d legacy engine-state entries into canonical path",
            migrated_entries,
        )

    # Quiet the /api/health access-log spam now that uvicorn has
    # configured its access logger (#1000).
    _install_access_log_filter()

    # Seed built-in providers (Apple Vision/Transcribe) on first run
    _seed_builtin_providers()

    # One-time cleanup: collapse any duplicate provider rows left over
    # from the pre-fix POST /providers behaviour (#704).
    _collapse_duplicate_providers()

    # Recover stale workflow runs left in 'running' by prior crashes/restarts (#1350).
    await _recover_stale_runs_on_startup()

    # Pre-warm embeddings model in background — avoids 2+ GB download on first search
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _prewarm_embeddings)

    # Watch FICHERO_PARENT_PID (set by EmbeddedBackendService on spawn).
    # If the Swift app dies without a chance to call .stop() (e.g. SIGKILL,
    # crash, force-quit), this self-terminates the engine so it doesn't
    # become an orphan holding port 8765.
    parent_watcher = asyncio.create_task(_watch_parent_process())

    yield
    parent_watcher.cancel()
    # Shutdown: close all database connections
    logger.info("Fichero API shutting down...")
    db_manager.close_all()


app = FastAPI(
    title="Fichero API",
    description="Document processing and search API",
    version="0.1.0",
    lifespan=lifespan,
)


# Local-host shared-secret authentication (#742). Initialized once at module
# import; the token is also written to ~/Library/Application Support/Fichero/.api-key
# (mode 0600) so the Swift app can read it. Tests can disable by setting
# FICHERO_DISABLE_AUTH=1 before importing this module.
if os.environ.get("FICHERO_DISABLE_AUTH", "").lower() not in {"1", "true", "yes"}:
    from fichero.api.auth import attach_auth_middleware, initialize_token

    _api_token = initialize_token()
    attach_auth_middleware(app, _api_token)


# CORS configuration
# Production: Restrict origins to specific domains
# Development: Allow localhost origins
def _get_cors_origins() -> list[str]:
    """Get allowed CORS origins based on environment."""
    env = os.environ.get("FICHERO_ENV", "development").lower().strip()

    if env == "production":
        # Production: Only specific origins (configure via env var)
        allowed = os.environ.get("FICHERO_CORS_ORIGINS", "")
        if allowed:
            return [origin.strip() for origin in allowed.split(",")]
        # Default: no cross-origin in production if not configured
        return []

    # Development: Allow common local development origins
    return [
        "http://localhost:*",
        "http://127.0.0.1:*",
        "https://localhost:*",
        "https://127.0.0.1:*",
        "app://localhost",  # Electron/Tauri apps
    ]


cors_origins = _get_cors_origins()

# Security: Never allow credentials with wildcard origins
# Credentials are only allowed when specific origins are configured
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=len(cors_origins) > 0 and cors_origins != ["*"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Fichero-Library-Path",
        "X-API-Key",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def validate_library_path_header(request: Request, call_next):
    """Validate library header early, even when dependencies are overridden in tests."""
    library_path = request.headers.get("X-Fichero-Library-Path")
    if library_path and not _is_allowed_library_path(library_path):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={
                "detail": "Library path is not in an allowed location or not a .fichero package."
            },
        )
    return await call_next(request)


def _is_allowed_library_path(library_path: str) -> bool:
    """Validate that a library path is in an allowed location.

    Allowed roots:
    - ~/Documents
    - ~/Desktop (iCloud-syncable, natural place for libraries)
    - ~/Fichero
    - ~/Dropbox
    - ~/Library/Application Support
    - ~/Library/CloudStorage (Box/Dropbox/iCloud provider roots)
    - ~/Library/Mobile Documents/com~apple~CloudDocs — iCloud Drive AND
      iCloud-synced Documents/Desktop physically live here
    - test temp dirs under /var/folders and /private/var/folders (macOS)
    - /tmp and /private/tmp — Linux CI and macOS sandbox pytest tmp_path

    Symlink tolerance: when "Desktop & Documents in iCloud" is ON, ~/Documents
    is a symlink into ~/Library/Mobile Documents/com~apple~CloudDocs/Documents.
    Path.resolve() follows that symlink, moving the path outside the literal
    ~/Documents root. We therefore test BOTH the resolved path and the
    un-resolved (expanded) path against the allowed roots and allow if EITHER
    is under an allowed root — so ~/Documents/... passes whether or not it is
    symlinked into iCloud, and the iCloud root catches the resolved form.
    """
    try:
        expanded = Path(library_path).expanduser()
        resolved = expanded.resolve()
    except Exception:
        return False

    # Use the expanded (un-resolved) suffix so a symlinked or not-yet-created
    # .fichero package still reads as a .fichero package.
    if expanded.suffix != ".fichero":
        return False

    home = Path.home().resolve()
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    allowed_roots = [
        home / "Documents",
        home / "Desktop",
        home / "Fichero",
        home / "Dropbox",
        home / "code",  # corpus libraries (e.g. ~/code/marshall_diaries/*.fichero)
        home / "Library" / "Application Support",
        home / "Library" / "CloudStorage",
        icloud,
        Path("/var/folders"),
        Path("/private/var/folders"),
        Path("/tmp"),
        Path("/private/tmp"),
    ]

    candidates = [resolved, expanded]
    return any(
        candidate.is_relative_to(root)
        for candidate in candidates
        for root in allowed_roots
    )


async def get_library_database(
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> Database:
    """FastAPI dependency to get the database for the current library package.

    Extracts library path from X-Fichero-Library-Path header and returns
    the appropriate Database instance.

    Args:
        x_fichero_library_path: Path to .fichero package (e.g., /Users/name/MyLibrary.fichero)

    Returns:
        Database instance for this library

    Raises:
        HTTPException: If library path header is missing or invalid
    """
    if not x_fichero_library_path:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Fichero-Library-Path header. Please open a library document first.",
        )

    if not _is_allowed_library_path(x_fichero_library_path):
        raise HTTPException(
            status_code=403,
            detail="Library path is not in an allowed location or not a .fichero package.",
        )

    try:
        db = db_manager.get_database(x_fichero_library_path)
        logger.debug(f"Using database for library: {x_fichero_library_path}")
        return db
    except Exception as e:
        logger.error(f"Failed to get database for {x_fichero_library_path}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to access library database: {str(e)}"
        )


# Health check endpoint
@app.get("/api/health", response_model=HealthResponse)
async def health_check(
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path"),
) -> HealthResponse:
    """Health check endpoint.

    If library path is provided, returns stats for that library.
    Otherwise, returns general backend health.
    """
    from fichero.models import Document

    if x_fichero_library_path:
        # Library-specific health check
        try:
            db = db_manager.get_database(x_fichero_library_path)
            doc_count = db.count(Document)
            return HealthResponse(
                status="healthy",
                library_path=x_fichero_library_path,
                database=str(db.path),
                document_count=doc_count,
            )
        except Exception as e:
            return HealthResponse(
                status="unhealthy",
                library_path=x_fichero_library_path,
                error=str(e),
            )
    else:
        # General backend health
        return HealthResponse(
            status="healthy",
            backend_version="0.1.0",
            active_libraries=db_manager.active_count,
            remote_backend=build_remote_backend_status().as_dict(),
        )


@app.get("/api/stats", response_model=LibraryStatsResponse)
async def get_stats(db: Database = Depends(get_library_database)):
    """Get library statistics for the current library."""
    from fichero.models import Document, Artifact

    return LibraryStatsResponse(
        documents=db.count(Document),
        artifacts=db.count(Artifact),
        embedding_stats=EmbeddingStatsResponse(**db.embedding_stats()),
    )


# Include route modules
from fichero.api.routes import (  # noqa: E402
    actions,
    activity,
    annotations,
    artifacts,
    batch,
    bibliography,
    chains,
    chat,
    citation_usages,
    citation_rendering,
    citations,
    claim_curation,
    claim_links,
    claims,
    classifications,
    document_inspector,
    documents,
    entities,
    entity_inspector,
    export,
    folders,
    hermeneutics,
    image_editing,
    iiif,
    ingest,
    integrations,
    kg_claim_analysis,
    kg_claim_search,
    kg_curation_rules,
    kg_entity_curation,
    kg_graph,
    changes,
    kg_inclusion,
    kg_mutations,
    kg_render,
    kg_predictions,
    kg_pykeen,
    kg_rebuild,
    kg_review,
    kg_search,
    kg_sparql,
    kg_triangulation,
    library,
    library_entity_types,
    library_registry,
    local_models,
    mcp_servers,
    mcp_tools,
    migrations,
    mind_palace,
    mindpalace_render,
    model_comparison,
    models,
    multilingual,
    notes,
    orchestration,
    references,
    projects,
    providers,
    registries,
    research_agents,
    schedules,
    search,
    search_explain,
    settings,
    sources,
    storage,
    tasks,
    triggers,
    views,
    workflow_execution,
    workflows,
)

RouteSpec = tuple[object, str, list[str]]

_CORE_ROUTE_SPECS: list[RouteSpec] = [
    (activity.router, "/api", ["activity"]),
    # /api/changes/stream — per-library change-event SSE; foundation of the
    # observable data layer (#1863). Core tier: the SwiftUI stores subscribe
    # unconditionally.
    (changes.router, "/api", ["changes"]),
    (annotations.router, "/api", ["annotations"]),
    (notes.router, "/api", ["notes"]),
    (projects.router, "/api", ["projects"]),
    (artifacts.router, "/api/artifacts", ["artifacts"]),
    (bibliography.router, "/api", ["bibliography"]),
    (batch.router, "/api", ["batches"]),
    (chat.router, "/api/chat", ["chat"]),
    (citations.router, "/api", ["citations"]),
    (classifications.router, "/api", ["classifications"]),
    (claim_links.router, "/api", ["claim-links"]),
    (claims.router, "/api", ["claims"]),
    (documents.router, "/api/documents", ["documents"]),
    (references.router, "/api", ["references"]),
    # Inspectors mount under /documents/* and /entities/* — tag with the
    # owning resource so the OpenAPI generator groups operations under
    # the correct Swift service file (was incorrectly tagged
    # "knowledge-graph" pre-2026-05-15 cleanup).
    (document_inspector.router, "/api", ["documents"]),
    (entity_inspector.router, "/api", ["entities"]),
    (kg_search.router, "/api", ["knowledge-graph"]),
    (entities.router, "/api", ["entities"]),
    (export.router, "/api", ["export"]),
    (folders.router, "/api/folders", ["folders"]),
    (ingest.router, "/api/ingest", ["ingest"]),
    (image_editing.router, "/api", ["images"]),
    # /api/library — bootstrap a fresh .fichero package from the CLI
    # without going through SwiftUI's NSDocument flow (#1075 follow-up).
    (library.router, "/api", ["library"]),
    # /api/registry — known library registry persistence (#1131).
    # CLI list/switch uses these endpoints to manage the set of known libraries.
    (library_registry.router, "/api", ["library"]),
    # /api/libraries/{lib}/entity-types — per-library entity type customization (#874).
    (library_entity_types.router, "/api", ["library"]),
    (migrations.router, "/api/migrations", ["migrations"]),
    (mcp_tools.router, "/api/mcp/tools", ["mcp"]),
    (multilingual.router, "/api", ["multilingual"]),
    (providers.router, "/api/providers", ["providers"]),
    # /api/registries/epistemic-statuses and /api/registries/claim-kinds —
    # user-extensible vocabulary for KnowledgeClaim fields (#1102).
    (registries.router, "/api", ["registries"]),
    (search.router, "/api/search", ["search"]),
    (settings.router, "", ["settings"]),
    (sources.router, "/api/sources", ["sources"]),
    (models.router, "/api/models", ["models"]),
    # Model comparison is part of the shipped chat/LLM surface for #1262.
    # It was already implemented but remained dev-tier gated, so release
    # engines returned 404 for /api/model-comparison/*.
    (model_comparison.router, "/api", ["model-comparison"]),
    # claim_curation: KnowledgeClaim curation_state machine
    # (transition / shortlist / curate / reject). Mounts under /api/claims.
    # Renamed from review_queue 2026-05-15 — the file is unrelated to the
    # entity-pair review queue in kg_review.py.
    (claim_curation.router, "/api", ["claim-curation"]),
    (claim_curation.kg_claims_router, "/api", ["knowledge-graph"]),
    (storage.router, "/api/storage", ["storage"]),
    (tasks.router, "/api/tasks", ["tasks"]),
    (workflow_execution.router, "/api/workflow-execution", ["workflow-execution"]),
    (workflows.router, "/api/workflows", ["workflows"]),
    (views.router, "", ["views"]),
    # /api/kg/* — promoted from dev-tier to core 2026-05-12 (#967).
    # The Swift OntologyBrowser + DocumentInspector consume these
    # endpoints unconditionally; gating them behind FICHERO_FEATURE_TIER=dev
    # meant default-tier engines silently 404'd every KG request and
    # the UI degraded to empty state without telling the user. Each of
    # these has a Swift caller and ships in the OpenAPI client; they
    # belong in core.
    (kg_rebuild.router, "/api", ["knowledge-graph"]),
    (kg_triangulation.router, "/api", ["knowledge-graph"]),
    (kg_graph.router, "/api", ["knowledge-graph"]),
    (kg_render.router, "/api", ["knowledge-graph"]),
    (kg_render.bio_router, "/api", ["knowledge-graph"]),
    (kg_entity_curation.kg_entities_router, "/api", ["knowledge-graph"]),
    (kg_pykeen.router, "/api", ["knowledge-graph"]),
    (kg_predictions.router, "/api", ["knowledge-graph"]),
    (kg_review.router, "/api", ["knowledge-graph"]),
    (kg_mutations.router, "/api", ["knowledge-graph"]),
    # citation_rendering: APA / Chicago / MLA / BibTeX string formatting.
    # Renamed from kg_citations 2026-05-15 — it is a renderer, not the
    # citation graph (that lives in citations.py / DocumentCitation #906).
    (citation_rendering.router, "/api", ["citation-rendering"]),
    (kg_claim_search.router, "/api", ["knowledge-graph"]),
    (kg_claim_analysis.router, "/api", ["knowledge-graph"]),
    (kg_curation_rules.router, "/api", ["knowledge-graph"]),
    (kg_entity_curation.router, "/api", ["knowledge-graph"]),
    (kg_sparql.router, "/api", ["knowledge-graph"]),
    (kg_inclusion.router, "/api", ["knowledge-graph"]),
    # Hermeneutics is the interpretation-reading layer on top of KG —
    # PatternInstance + hermeneutic-circle navigation + LLM suggestions
    # share entity/claim ids with KnowledgeEntity/KnowledgeClaim. Promoted
    # to release for 0.0.2 alongside the rest of the KG surface so end-
    # users get the full epistemology layer in shipped builds. (#997)
    (hermeneutics.router, "/api/hermeneutics", ["knowledge-graph"]),
    # Canonical KG URL prefix — same router, different mount point (#1126).
    (hermeneutics.router, "/api/kg/interpretations", ["knowledge-graph"]),
    # Workflow chains: multi-step sequenced pipelines with output mappings.
    # Promoted from dev-tier to core for 0.0.2 (#1151).
    (chains.router, "/api", ["chains"]),
    # ── Promoted dev→release for 0.0.2 (Daniel 2026-05-28): ship ALL gated
    #    features so they're reviewable in release builds; demote individually
    #    if one isn't ready. Safe re #1298 — openapi is exported at dev tier
    #    (core+dev union, invariant under this move) and the NodeDef→Input/
    #    Output Swift fix landed (adb1603e). ──
    (search_explain.router, "/api", ["search-explanation"]),
    (citation_usages.router, "/api", ["citation-usages"]),
    (mind_palace.router, "/api/mind-palace", ["mind-palace"]),
    (mindpalace_render.router, "/api", ["mind-palace"]),
    (research_agents.router, "/api/research", ["research"]),
    (iiif.router, "/api/iiif", ["iiif"]),
    (actions.router, "/api", ["actions"]),
    (integrations.router, "/api", ["integrations"]),
    (local_models.router, "/api", ["local-models"]),
    (mcp_servers.router, "/api", ["mcp-servers"]),
    (orchestration.router, "", ["orchestration"]),
    (schedules.router, "/api", ["schedules"]),
    (triggers.router, "/api", ["triggers"]),
]

# All former dev-tier routers promoted to _CORE for 0.0.2 release review
# (Daniel 2026-05-28). Kept as an empty list so the tier plumbing
# (get_route_specs_for_tier) stays intact; re-add a spec here to demote a
# feature back to dev-only.
_DEV_ROUTE_SPECS: list[RouteSpec] = []


def resolve_feature_tier() -> str:
    """Resolve active API feature tier from env with release-safe default."""
    configured_tier = os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower()
    if configured_tier not in {"release", "dev"}:
        logger.warning(
            "Unknown FICHERO_FEATURE_TIER=%s, defaulting to release", configured_tier
        )
        tier = "release"
    else:
        tier = configured_tier

    logger.info("FICHERO_FEATURE_TIER resolved to: %s", tier)
    return tier


def get_route_specs_for_tier(feature_tier: str) -> Sequence[RouteSpec]:
    """Return routers enabled for the given feature tier."""
    if feature_tier == "dev":
        return [*_CORE_ROUTE_SPECS, *_DEV_ROUTE_SPECS]
    return _CORE_ROUTE_SPECS


def register_tiered_routes(feature_tier: str | None = None) -> str:
    """Register API routers for the selected feature tier."""
    tier = feature_tier or resolve_feature_tier()
    for router, prefix, tags in get_route_specs_for_tier(tier):
        app.include_router(router, prefix=prefix, tags=tags)
    logger.info("Registered API routes for tier: %s", tier)
    return tier


ACTIVE_FEATURE_TIER = register_tiered_routes()
