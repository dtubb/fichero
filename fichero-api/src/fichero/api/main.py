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

import logging
from contextlib import asynccontextmanager
from typing import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def _validate_model_sync() -> bool:
    """Validate that Python and Swift models are in sync.

    Returns True if sync is valid, False if there are issues.
    """
    try:
        from pathlib import Path
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: optionally validate model sync
    if os.environ.get("FICHERO_VALIDATE_MODELS") == "1":
        logger.info("Validating Python/Swift model sync...")
        if not _validate_model_sync():
            logger.warning(
                "Model sync issues detected! Run './scripts/sync_openapi_schema.sh' to fix."
            )
            # We log a warning but don't block startup

    # Startup: initialize database manager
    logger.info("Fichero API starting up...")
    from fichero.db import db_manager
    logger.info("DatabaseManager initialized")
    yield
    # Shutdown: close all database connections
    logger.info("Fichero API shutting down...")
    db_manager.close_all()


app = FastAPI(
    title="Fichero API",
    description="Document processing and search API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow all for local SwiftUI app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# FastAPI dependency: Get database for current library
from fastapi import Header, HTTPException, Depends  # noqa: E402
from fichero.db import Database, db_manager  # noqa: E402


async def get_library_database(
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path")
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
            detail="Missing X-Fichero-Library-Path header. Please open a library document first."
        )

    try:
        db = db_manager.get_database(x_fichero_library_path)
        logger.debug(f"Using database for library: {x_fichero_library_path}")
        return db
    except Exception as e:
        logger.error(f"Failed to get database for {x_fichero_library_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to access library database: {str(e)}"
        )


# Health check endpoint
@app.get("/api/health")
async def health_check(
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path")
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
            "active_libraries": len(db_manager._databases),
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
    documents,
    search,
    ingest,
    storage,
    providers,
    models,
    folders,
    artifacts,
    workflows,
    workflow_execution,
    batch,
    activity,
    chat,
    settings,
    knowledge_graph,
    hermeneutics,
)

RouteSpec = tuple[object, str, list[str]]

_CORE_ROUTE_SPECS: list[RouteSpec] = [
    (documents.router, "/api/documents", ["documents"]),
    (search.router, "/api/search", ["search"]),
    (ingest.router, "/api/ingest", ["ingest"]),
    (storage.router, "/api/storage", ["storage"]),
    (folders.router, "/api/folders", ["folders"]),
    (artifacts.router, "/api/artifacts", ["artifacts"]),
    (providers.router, "/api/providers", ["providers"]),
    (models.router, "/api/models", ["models"]),
    (workflows.router, "/api/workflows", ["workflows"]),
    (workflow_execution.router, "/api/workflow-execution", ["workflow-execution"]),
    (batch.router, "/api", ["batches"]),
    (activity.router, "/api", ["activity"]),
    (chat.router, "/api/chat", ["chat"]),
    (settings.router, "", ["settings"]),
]

_DEV_ROUTE_SPECS: list[RouteSpec] = [
    (knowledge_graph.router, "/api/knowledge-graph", ["knowledge-graph"]),
    (hermeneutics.router, "/api/hermeneutics", ["hermeneutics"]),
]


def resolve_feature_tier() -> str:
    """Resolve active API feature tier from env with release-safe default."""
    tier = os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower()
    if tier not in {"release", "dev"}:
        logger.warning("Unknown FICHERO_FEATURE_TIER=%s, defaulting to release", tier)
        return "release"
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
