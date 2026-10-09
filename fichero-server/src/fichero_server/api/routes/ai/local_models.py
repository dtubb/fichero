"""
Local Models API Routes

Endpoints for managing locally-downloaded AI models (Whisper, embeddings, spaCy).
Models are stored in ~/Library/Application Support/Fichero/models/
"""

from fastapi import APIRouter, HTTPException, Request

from fichero_server.actions.registry import ChangeSpec, action
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


#: The readers installed on this Mac, by the `model_type` this list gives them: the local catalogue's
#: provider and the capability that makes one a reader (`source.find.installed-readers-listed`, #5584).
_READERS = {"mlx": ("omlx", "vision"), "kraken": ("kraken", "recognition")}


def installed_readers(model_type: str) -> list[LocalModelInfoResponse]:
    """The readers of one runtime installed on this Mac, read from the one local catalogue Settings lists
    (`local_inference.installed_local_model_entries`): MLX vision models, or Kraken readers downloaded or
    trained. Only installed ones: a reader not yet here is a download a Start plan or Settings offers."""
    from fichero_server.api.routes.ai.local_inference import installed_local_model_entries

    provider, capability = _READERS[model_type]
    return [
        LocalModelInfoResponse(
            model_id=e.model_id, model_type=model_type, display_name=e.display_name,
            size_bytes=e.disk_usage_bytes or 0, is_downloaded=True,
            expected_size_mb=round((e.download_size_bytes or 0) / 1_000_000), path=None,
            metadata={"capabilities": list(e.capabilities), "tested_status": e.tested_status,
                      "license": e.license_label},
            note=e.note, available=e.supported, unavailable_reason=e.unsupported_reason,
            download_state="installed",
        )
        for e in installed_local_model_entries(provider)
        if capability in e.capabilities
    ]


@router.get("", response_model=LocalModelListResponse)
def list_local_models(model_type: str | None = None) -> LocalModelListResponse:
    """List the local models, optionally of one type: whisper, embeddings, spacy, mlx or kraken.

    Whisper, embeddings and spaCy list every model, downloaded or not. mlx and kraken list the readers
    installed on this Mac: every complete MLX vision model in the model store, and every Kraken reader
    downloaded or trained (`source.find.installed-readers-listed`). Omitted, all of them.
    """
    from fichero_server.llm.local_models import LocalModelManager

    mgr = LocalModelManager()

    if model_type == "whisper":
        models = mgr.list_whisper_models()
    elif model_type == "embeddings":
        models = mgr.list_embeddings_models()
    elif model_type == "spacy":
        models = mgr.list_spacy_models()
    elif model_type in _READERS:
        return LocalModelListResponse(models=installed_readers(model_type))
    else:
        models = mgr.list_all()

    rows = [LocalModelInfoResponse(**m.to_dict()) for m in models]
    if model_type is None:
        rows += [row for kind in _READERS for row in installed_readers(kind)]
    return LocalModelListResponse(models=rows)


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
    request: Request,
) -> DownloadStartedResponse:
    """Start downloading a model in the background.

    Args:
        model_type: "whisper" or "embeddings"
        model_id: Model identifier (e.g., "base" for Whisper, "intfloat/multilingual-e5-large" for embeddings)
    """
    from fichero_server.llm.local_models import (
        WHISPER_MODELS,
        EMBEDDINGS_MODELS,
    )

    if model_type == "whisper":
        if model_id not in WHISPER_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown Whisper model: {model_id}. Available: {', '.join(WHISPER_MODELS.keys())}",
            )
        # Refuse NOW rather than queueing work that cannot run: a runtime with no transcriber used to
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
    elif model_type not in ("spacy", "mlx"):
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    # Every download is a `download-model` job on the network lane of the open library, shown in
    # Activity (#5359; Whisper and embeddings models used to download on FastAPI's BackgroundTasks,
    # where nobody saw them), an MLX model too (`source.find.one-download-path`, #5620).
    from pathlib import Path as _Path

    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.api.auth import request_actor
    from fichero_server.api.library_header import require_library_path
    from fichero_server.api.main import get_library_database_for_write

    # The header as every route reads it, percent-decoded (#5620: a project whose path had a space was
    # refused with a bare 404 when it was read raw here, so Download did nothing).
    db = get_library_database_for_write(request, require_library_path(request))
    ctx = ActionContext(actor=request_actor(request), library_path=str(_Path(db.path).parent))
    try:
        result = registry.invoke(db, "model.download", {"runtime": model_type, "model": model_id}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DownloadStartedResponse(status="queued", model_type=model_type, model_id=model_id,
                                   job_id=result.result["job_id"])


@router.delete("/{model_type}/{model_id:path}", response_model=DeleteModelResponse)
def delete_model(model_type: str, model_id: str) -> DeleteModelResponse:
    """Delete a downloaded model.

    Args:
        model_type: "whisper" or "embeddings"
        model_id: Model identifier
    """
    from fichero_server.llm.local_models import LocalModelManager

    if model_type not in ("whisper", "embeddings", "spacy"):
        raise HTTPException(status_code=400, detail=f"Unknown model type: {model_type}")

    mgr = LocalModelManager()
    from fichero_server.llm.local_models import BundledModel

    try:
        freed = mgr.delete_model(model_type, model_id)
    except BundledModel as exc:  # a bundled spaCy pipeline ships in the app
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return DeleteModelResponse(status="ok", freed_bytes=freed)



class ModelDownloadParams(BaseModel):
    """``model.download`` params: which runtime's model to download."""

    runtime: str
    model: str


@action("model.download", ModelDownloadParams, domains=["models"], undoable=False)
def _action_model_download(db, params: ModelDownloadParams, ctx):
    """Queue a `download-model` job on the network lane (`runtime.spacy.pipelines-download-as-data`) for every
    runtime, an MLX model included: Activity lists it, its reason says how far it has got and a failure says why
    (`source.find.one-download-path`, #5620). A model this Mac cannot run is refused here, never queued."""
    from fichero_server.llm.local_models import enqueue_download

    job_id = enqueue_download(db, params.runtime, params.model, started_by=ctx.actor or "owner")
    return {"job_id": job_id, "runtime": params.runtime, "model": params.model}, ChangeSpec(
        domains=["models"], target_ids=[job_id], after={"job_id": job_id})
