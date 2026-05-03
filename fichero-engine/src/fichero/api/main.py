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

# Disable tokenizers parallelism to avoid fork() warnings when using multiprocessing
# This must be set before any imports that use transformers/tokenizers
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

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

logger = logging.getLogger(__name__)


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
    """Ensure Apple (on-device) provider exists — no API key, always available on macOS."""
    try:
        from fichero.app_db import get_app_db
        from fichero.models import Provider, ProviderType

        app_db = get_app_db()
        existing = {p.provider_type for p in app_db.list_providers()}
        if ProviderType.apple not in existing:
            provider = Provider(
                name="Apple",
                provider_type=ProviderType.apple,
                enabled=True,
            )
            app_db.save_provider(provider)
            logger.info("Seeded built-in Apple provider (Vision + Transcribe)")
    except Exception as exc:
        logger.warning("Could not seed built-in providers: %s", exc)


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
                app_db.conn.execute(
                    "UPDATE models SET provider_id = ? WHERE id = ?",
                    [canonical_id, model_id],
                )
            for dup in duplicates:
                app_db.delete_provider(dup.id)
            app_db.conn.commit()
            logger.info(
                "Collapsed %d duplicate %s providers named %r into %s (reparented %d models)",
                len(duplicates), key[0].value if hasattr(key[0], "value") else key[0],
                key[1], canonical.id, len(reparent_pairs),
            )
    except Exception as exc:
        logger.warning("Provider duplicate collapse failed: %s", exc)


def _prewarm_embeddings() -> None:
    """Download + initialise the embeddings model so it's ready before first use."""
    try:
        from fastembed import TextEmbedding
        from fichero.db import DEFAULT_MODEL
        from fichero.local_models import MODELS_BASE

        cache_dir = MODELS_BASE / "embeddings"
        cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Pre-warming embeddings model: %s", DEFAULT_MODEL)
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*multilingual-e5-large.*pooling.*")
            TextEmbedding(model_name=DEFAULT_MODEL, cache_dir=str(cache_dir))
        logger.info("Embeddings model ready")
    except Exception as exc:
        logger.warning("Embeddings pre-warm failed (will retry on first use): %s", exc)


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
    logger.info("DatabaseManager initialized")

    # Seed built-in providers (Apple Vision/Transcribe) on first run
    _seed_builtin_providers()

    # One-time cleanup: collapse any duplicate provider rows left over
    # from the pre-fix POST /providers behaviour (#704).
    _collapse_duplicate_providers()

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
    - ~/Dropbox
    - ~/Library/Application Support
    - test temp dirs under /var/folders and /private/var/folders
    """
    try:
        resolved = Path(library_path).expanduser().resolve()
    except Exception:
        return False

    if resolved.suffix != ".fichero":
        return False

    home = Path.home().resolve()
    allowed_roots = [
        home / "Documents",
        home / "Dropbox",
        home / "Library" / "Application Support",
        Path("/var/folders"),
        Path("/private/var/folders"),
    ]

    return any(resolved.is_relative_to(root) for root in allowed_roots)


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
@app.get("/api/health")
async def health_check(
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path"),
):
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
            return {
                "status": "healthy",
                "library_path": x_fichero_library_path,
                "database": str(db.path),
                "document_count": doc_count,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "library_path": x_fichero_library_path,
                "error": str(e),
            }
    else:
        # General backend health
        return {
            "status": "healthy",
            "backend_version": "0.1.0",
            "active_libraries": db_manager.active_count,
        }


@app.get("/api/stats")
async def get_stats(db: Database = Depends(get_library_database)):
    """Get library statistics for the current library."""
    from fichero.models import Document, Artifact

    return {
        "documents": db.count(Document),
        "artifacts": db.count(Artifact),
        "embedding_stats": db.embedding_stats(),
    }


# Include route modules
from fichero.api.routes import (  # noqa: E402
    actions,
    activity,
    artifacts,
    batch,
    chains,
    chat,
    claim_links,
    claims,
    documents,
    entities,
    folders,
    graph_exploration,
    graph_reasoning,
    hermeneutics,
    iiif,
    ingest,
    integrations,
    interpretations,
    knowledge_graph,
    local_models,
    mcp_servers,
    mcp_tools,
    migrations,
    mind_palace,
    model_comparison,
    models,
    multilingual,
    orchestration,
    predictions,
    providers,
    research_agents,
    review_queue,
    schedules,
    search,
    search_explain,
    settings,
    sources,
    storage,
    tasks,
    triggers,
    workflow_execution,
    workflows,
)

RouteSpec = tuple[object, str, list[str]]

_CORE_ROUTE_SPECS: list[RouteSpec] = [
    (activity.router, "/api", ["activity"]),
    (artifacts.router, "/api/artifacts", ["artifacts"]),
    (batch.router, "/api", ["batches"]),
    (chat.router, "/api/chat", ["chat"]),
    (claim_links.router, "/api", ["claim-links"]),
    (claims.router, "/api", ["claims"]),
    (documents.router, "/api/documents", ["documents"]),
    (entities.router, "/api", ["entities"]),
    (folders.router, "/api/folders", ["folders"]),
    (ingest.router, "/api/ingest", ["ingest"]),
    (migrations.router, "/api/migrations", ["migrations"]),
    (mcp_tools.router, "/api/mcp/tools", ["mcp"]),
    (multilingual.router, "/api", ["multilingual"]),
    (providers.router, "/api/providers", ["providers"]),
    (search.router, "/api/search", ["search"]),
    (settings.router, "", ["settings"]),
    (sources.router, "/api/sources", ["sources"]),
    (models.router, "/api/models", ["models"]),
    (review_queue.router, "/api", ["review-queue"]),
    (storage.router, "/api/storage", ["storage"]),
    (tasks.router, "/api/tasks", ["tasks"]),
    (workflow_execution.router, "/api/workflow-execution", ["workflow-execution"]),
    (workflows.router, "/api/workflows", ["workflows"]),
]

_DEV_ROUTE_SPECS: list[RouteSpec] = [
    # Originally dev-tier
    (knowledge_graph.router, "/api/knowledge-graph", ["knowledge-graph"]),
    (search_explain.router, "/api", ["search-explanation"]),
    (hermeneutics.router, "/api/hermeneutics", ["hermeneutics"]),
    (interpretations.router, "/api", ["interpretations"]),
    (graph_exploration.router, "/api", ["graph-exploration"]),
    (mind_palace.router, "/api/mind-palace", ["mind-palace"]),
    (research_agents.router, "/api/research", ["research"]),
    (iiif.router, "/api/iiif", ["iiif"]),
    # Staged routes — feature-gated behind dev tier
    (actions.router, "/api", ["actions"]),
    (chains.router, "/api", ["chains"]),
    (graph_reasoning.router, "", ["graph-reasoning"]),
    (integrations.router, "/api", ["integrations"]),
    (local_models.router, "/api", ["local-models"]),
    (mcp_servers.router, "/api", ["mcp-servers"]),
    (model_comparison.router, "/api", ["model-comparison"]),
    (orchestration.router, "", ["orchestration"]),
    (predictions.router, "", ["predictions"]),
    (schedules.router, "/api", ["schedules"]),
    (triggers.router, "/api", ["triggers"]),
]


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
