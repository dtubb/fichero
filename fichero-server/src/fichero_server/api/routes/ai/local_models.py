"""
Local Models API Routes

Endpoints for managing locally-downloaded AI models (Whisper, embeddings, spaCy).
Models are stored in ~/Library/Application Support/Fichero/models/
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from fichero_server.models import (
    DeleteModelResponse,
    DiskUsageResponse,
    DownloadStartedResponse,
    LocalModelInfoResponse,
    LocalModelListResponse,
)

router = APIRouter(prefix="/local-models")


# =============================================================================
# Kraken line-segmentation runtime (~1 GB, USER-CHOSEN install)
# =============================================================================
#
# Kraken is not a downloadable model file like Whisper or a pip model like
# spaCy — it is a whole venv the app builds on demand (torch + kraken + a
# scipy override). It gets its own install/status pair rather than being forced
# through the model download route, and it NEVER provisions on its own: only a
# POST here starts it, mirroring Daniel's "never automatic" rule.


class KrakenInstallJobResponse(BaseModel):
    job_id: str
    state: str
    current: int
    total: int
    percent: float
    message: str
    error: str | None = None


class KrakenRuntimeStatusResponse(BaseModel):
    installed: bool
    available: bool
    kraken_version: str | None = None
    scipy_override: str | None = None
    runtime_dir: str
    disk_usage_bytes: int = 0
    size_note: str = "~1 GB download"
    reason: str | None = None
    job: KrakenInstallJobResponse | None = None


def _kraken_status_response() -> KrakenRuntimeStatusResponse:
    from fichero_server.llm.kraken_runtime import get_kraken_runtime

    payload = get_kraken_runtime().status()
    job = payload.get("job")
    return KrakenRuntimeStatusResponse(
        installed=bool(payload["installed"]),
        # "available" here means the app can act on this row: it can be
        # installed (or already is). Kraken runs in its own subprocess venv, so
        # there is no host-capability gate the way audio has one.
        available=True,
        kraken_version=payload.get("kraken_version"),
        scipy_override=payload.get("scipy_override"),
        runtime_dir=str(payload["runtime_dir"]),
        disk_usage_bytes=int(payload.get("disk_usage_bytes", 0)),
        reason=payload.get("reason"),
        job=KrakenInstallJobResponse(**job) if isinstance(job, dict) else None,
    )


@router.get("/kraken/status", response_model=KrakenRuntimeStatusResponse)
async def kraken_status() -> KrakenRuntimeStatusResponse:
    """Report whether Kraken is installed, plus any in-flight install job."""
    return _kraken_status_response()


@router.post("/kraken/install", response_model=KrakenRuntimeStatusResponse)
async def install_kraken() -> KrakenRuntimeStatusResponse:
    """Start (or reuse) the coalesced background Kraken install job.

    Returns immediately with the job so the UI can poll ``/kraken/status``.
    Idempotent: a second call while one runs returns the same job, and a call
    when Kraken is already installed completes without rebuilding the venv.
    """
    from fichero_server.llm.kraken_runtime import get_kraken_runtime

    await get_kraken_runtime().start_install()
    return _kraken_status_response()


@router.delete("/kraken", response_model=KrakenRuntimeStatusResponse)
async def remove_kraken() -> KrakenRuntimeStatusResponse:
    """Remove the Kraken venv when no install is running."""
    from fichero_server.llm.kraken_runtime import get_kraken_runtime

    try:
        get_kraken_runtime().remove()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _kraken_status_response()


# =============================================================================
# Routes
# =============================================================================


@router.get("", response_model=LocalModelListResponse)
def list_local_models(model_type: str | None = None) -> LocalModelListResponse:
    """List all local models, optionally filtered by type.

    Query params:
        model_type: "whisper" or "embeddings" (optional, lists all if omitted)
    """
    from fichero_server.llm.local_models import LocalModelManager

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
    from fichero_server.llm.local_models import LocalModelManager

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
    from fichero_server.llm.local_models import (
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
        # Refuse NOW rather than queueing work that cannot run. The download
        # happens in a BackgroundTask, so a runtime with no transcriber used to
        # answer 200 "downloading" and then fail where no one could see it.
        from fichero_server.llm.whisper_runtime import audio_runtime_status

        runtime = audio_runtime_status()
        if not runtime["ready"]:
            raise HTTPException(status_code=409, detail=str(runtime["reason"]))
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
    from fichero_server.llm.local_models import LocalModelManager

    if model_type not in ("whisper", "embeddings"):
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    mgr = LocalModelManager()
    freed = mgr.delete_model(model_type, model_id)

    return DeleteModelResponse(status="ok", freed_bytes=freed)
