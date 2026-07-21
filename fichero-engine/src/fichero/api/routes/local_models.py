"""
Local Models API Routes

Endpoints for managing locally-downloaded AI models (Whisper, embeddings, spaCy).
Models are stored in ~/Library/Application Support/Fichero/models/
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from fichero.models import (
    DeleteModelResponse,
    DiskUsageResponse,
    DownloadStartedResponse,
    LocalModelInfoResponse,
    LocalModelListResponse,
)

router = APIRouter(prefix="/local-models")


# =============================================================================
# Routes
# =============================================================================


@router.get("", response_model=LocalModelListResponse)
def list_local_models(model_type: str | None = None) -> LocalModelListResponse:
    """List all local models, optionally filtered by type.

    Query params:
        model_type: "whisper" or "embeddings" (optional, lists all if omitted)
    """
    from fichero.local_models import LocalModelManager

    mgr = LocalModelManager()

    if model_type == "whisper":
        models = mgr.list_whisper_models()
    elif model_type == "embeddings":
        models = mgr.list_embeddings_models()
    else:
        models = mgr.list_all()

    return LocalModelListResponse(
        models=[LocalModelInfoResponse(**m.to_dict()) for m in models]
    )


@router.get("/disk-usage", response_model=DiskUsageResponse)
def disk_usage() -> DiskUsageResponse:
    """Get total disk usage by model type."""
    from fichero.local_models import LocalModelManager

    data = LocalModelManager().total_disk_usage()
    return DiskUsageResponse(**data)


@router.post("/download/{model_type}/{model_id:path}", response_model=DownloadStartedResponse)
def download_model(
    model_type: str,
    model_id: str,
    background_tasks: BackgroundTasks,
) -> DownloadStartedResponse:
    """Start downloading a model in the background.

    Args:
        model_type: "whisper" or "embeddings"
        model_id: Model identifier (e.g., "base" for Whisper, "intfloat/multilingual-e5-large" for embeddings)
    """
    from fichero.local_models import (
        LocalModelManager,
        WHISPER_MODELS,
        EMBEDDINGS_MODELS,
    )

    if model_type == "whisper":
        if model_id not in WHISPER_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown Whisper model: {model_id}. Available: {', '.join(WHISPER_MODELS.keys())}",
            )
    elif model_type == "embeddings":
        if model_id not in EMBEDDINGS_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown embeddings model: {model_id}. Available: {', '.join(EMBEDDINGS_MODELS.keys())}",
            )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    mgr = LocalModelManager()
    background_tasks.add_task(mgr.download_model, model_type, model_id)

    return DownloadStartedResponse(
        status="downloading", model_type=model_type, model_id=model_id
    )


@router.delete("/{model_type}/{model_id:path}", response_model=DeleteModelResponse)
def delete_model(model_type: str, model_id: str) -> DeleteModelResponse:
    """Delete a downloaded model.

    Args:
        model_type: "whisper" or "embeddings"
        model_id: Model identifier
    """
    from fichero.local_models import LocalModelManager

    if model_type not in ("whisper", "embeddings"):
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    mgr = LocalModelManager()
    freed = mgr.delete_model(model_type, model_id)

    return DeleteModelResponse(status="ok", freed_bytes=freed)
