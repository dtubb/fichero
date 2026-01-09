"""
Fichero FastAPI Application

REST API backend exposing the Fichero data layer (DuckDB + LanceDB).

Usage:
    # Direct
    uvicorn fichero.api.main:app --reload

    # Via CLI
    fichero serve
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
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
from fastapi import Header, HTTPException, Depends
from fichero.db import Database, db_manager


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
from fichero.api.routes import (
    documents,
    search,
    ingest,
    storage,
    chat,
    providers,
    workflows,
    workflow_execution,
    models,
    folders,
    mcp_servers,
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(workflow_execution.router, prefix="/api/workflow-execution", tags=["workflow-execution"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(folders.router, prefix="/api/folders", tags=["folders"])
app.include_router(mcp_servers.router, prefix="/api", tags=["mcp-servers"])
