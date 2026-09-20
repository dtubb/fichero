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
# Kraken line-segmentation — BUNDLED at build time (#4959, 2026-09-20)
# =============================================================================
#
# Kraken used to be a runtime-provisioned venv; it ships inside the signed
# engine bundle now (see `kraken_runtime.py`'s module docstring for why: a
# sandboxed app can neither copy its own executable into a venv nor load a
# quarantined native library, and runtime code install is forbidden outright
# on the Mac App Store tier). `GET /kraken/status` answers "bundled,
# installed" from `kraken_runtime.runtime_status()` — a build problem now,
# never something to fix from Settings.
#
# `POST /kraken/install` and `DELETE /kraken` STAY — the MCP server's
# `fichero_kraken_install` tool still POSTs the install route
# (fichero-mcp/src/fichero_mcp/server.py) and the generated CLI surface
# lists both (openapi_surface_generated.py). Breaking the OpenAPI contract
# silently is worse than a route that does nothing: install is now a no-op
# that just reports bundled status (idempotent, no job — there is nothing to
# install), and remove always refuses, honestly, with 409.
#
# `KrakenRuntimeStatusResponse`/`KrakenInstallJobResponse` keep their ORIGINAL
# fields (not trimmed) so the response schema — and anything generated from
# it — does not change shape underneath a caller that reads them.


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
    scipy_override: str | None = None  # #4959: always None — bundled, no override step any more
    runtime_dir: str = ""  # #4959: always "" — bundled inside the app, no separate runtime directory
    disk_usage_bytes: int = 0  # #4959: always 0 — nothing separate on disk to report
    size_note: str = "bundled with the app"
    reason: str | None = None
    job: KrakenInstallJobResponse | None = None  # #4959: always None — no install job runs any more


def _kraken_status_response() -> KrakenRuntimeStatusResponse:
    from fichero_server.llm.kraken_runtime import runtime_status

    payload = runtime_status()
    return KrakenRuntimeStatusResponse(
        installed=bool(payload["installed"]),
        # "available" here means the app can act on this row at all — always
        # true now: Kraken is either bundled or it is a packaging bug, never
        # something the user can install from here.
        available=True,
        kraken_version=payload.get("kraken_version"),
        reason=payload.get("reason"),
    )


@router.get("/kraken/status", response_model=KrakenRuntimeStatusResponse)
async def kraken_status() -> KrakenRuntimeStatusResponse:
    """Report whether Kraken is bundled (importable) in this build."""
    return _kraken_status_response()


@router.post("/kraken/install", response_model=KrakenRuntimeStatusResponse)
async def install_kraken() -> KrakenRuntimeStatusResponse:
    """#4959: nothing to install — Kraken ships inside the signed bundle.

    Kept for the MCP tool and the generated CLI: idempotent, no job, just
    reports whether the bundle actually carries it (a packaging problem if
    not, never something this call can fix)."""
    return _kraken_status_response()


@router.delete("/kraken", response_model=KrakenRuntimeStatusResponse)
async def remove_kraken() -> KrakenRuntimeStatusResponse:
    """#4959: refuses — Kraken is bundled with the app and cannot be removed
    (there is no separate runtime to delete)."""
    raise HTTPException(
        status_code=409, detail="Kraken is bundled with the app and cannot be removed."
    )


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
