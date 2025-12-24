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
    # Startup: initialize database connection
    logger.info("Fichero API starting up...")
    from fichero.db import db
    logger.info(f"Database connected: {db.path}")
    yield
    # Shutdown
    logger.info("Fichero API shutting down...")


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


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from fichero.db import db
    from fichero.models import Document

    try:
        # Quick database check - count documents
        doc_count = db.count(Document)
        return {
            "status": "healthy",
            "database": str(db.path),
            "document_count": doc_count,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@app.get("/api/stats")
async def get_stats():
    """Get library statistics."""
    from fichero.db import db
    from fichero.models import Document, Artifact

    return {
        "documents": db.count(Document),
        "artifacts": db.count(Artifact),
        "embedding_stats": db.embedding_stats(),
    }


# Include route modules
from fichero.api.routes import documents, search, ingest, storage, chat, providers, workflows, models

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
