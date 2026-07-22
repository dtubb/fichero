"""Typed API surface for app-managed local inference providers."""

from __future__ import annotations

import os
import shlex
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from fichero.llm.local_inference import (
    ExternalLocalInferenceProcess,
    LocalInferenceCapabilities,
    LocalModelHardwareError,
    LocalModelNotInstalledError,
    LocalInferenceRuntimeMissingError,
    LocalInferenceServiceManager,
    LocalInferenceServiceStatus,
    LocalInferenceValidationError,
    LocalModelCatalogEntry,
    LocalProviderProfile,
    ManagedLocalInferenceProcess,
    get_local_inference_capabilities,
)
from fichero.llm.mlx_model_store import get_mlx_model_store
from fichero.llm.mlx_runtime import get_mlx_runtime

router = APIRouter(prefix="/local-inference")

DEFAULT_OMLX_PROFILE_ID = "app-omlx"
DEFAULT_OMLX_MODEL_ID = "mlx-community/Qwen3-VL-8B"
DEFAULT_OMLX_BASE_URL = "http://localhost:8000/v1"

_MANAGERS: dict[str, LocalInferenceServiceManager] = {}


class LocalInferenceProfileListResponse(BaseModel):
    """Envelope for app-managed local inference provider profiles."""

    items: list[LocalProviderProfile]
    count: int


class LocalInferenceCatalogResponse(BaseModel):
    """Envelope for local model catalog entries."""

    items: list[LocalModelCatalogEntry]
    count: int


class LocalInferenceStartRequest(BaseModel):
    """Request body for starting or warming a local inference profile."""

    timeout_seconds: float | None = Field(default=None, ge=0)


class LocalInferenceValidationResponse(BaseModel):
    """Result of profile validation."""

    valid: bool
    profile: LocalProviderProfile


class LocalInferenceRuntimeJobResponse(BaseModel):
    job_id: str
    state: str
    current: int
    total: int
    percent: float
    message: str
    error: str | None = None


class LocalInferenceRuntimeStatusResponse(BaseModel):
    provisioned: bool
    mlx_lm_version: str | None = None
    disk_usage_bytes: int = Field(default=0, ge=0)
    python_path: str | None = None
    runtime_dir: str
    job: LocalInferenceRuntimeJobResponse | None = None


class LocalInferenceCapabilitiesResponse(BaseModel):
    system: str
    machine: str
    is_apple_silicon: bool
    subprocess_capable: bool
    physical_memory_bytes: int | None = None
    macos_version: str | None = None


class LocalInferenceModelDownloadJobResponse(BaseModel):
    job_id: str
    model_id: str
    state: str
    current: int
    total: int
    percent: float
    message: str
    error: str | None = None


class LocalInferenceModelDeleteResponse(BaseModel):
    status: str
    freed_bytes: int


def _configured_omlx_profile() -> LocalProviderProfile:
    """Build the default app-managed oMLX profile from env/defaults."""
    capabilities = get_local_inference_capabilities()
    base_url = (
        os.environ.get("FICHERO_OMLX_BASE_URL")
        or os.environ.get("FICHERO_OMLX_API_BASE")
        or DEFAULT_OMLX_BASE_URL
    )
    model_id = os.environ.get("FICHERO_OMLX_MODEL") or DEFAULT_OMLX_MODEL_ID
    healthcheck_path = os.environ.get("FICHERO_OMLX_HEALTHCHECK_PATH") or "/health"
    command = shlex.split(os.environ["FICHERO_OMLX_COMMAND"]) if os.environ.get("FICHERO_OMLX_COMMAND") else []
    return LocalProviderProfile(
        id=DEFAULT_OMLX_PROFILE_ID,
        name="App-managed oMLX",
        provider_type="omlx",
        model_id=model_id,
        base_url=base_url,
        local_only=True,
        allows_paid_fallbacks=False,
        managed_by_app=True,
        healthcheck_path=healthcheck_path,
        timeout_seconds=float(os.environ.get("FICHERO_OMLX_TIMEOUT_SECONDS", "5.0")),
        max_concurrency=int(os.environ.get("FICHERO_OMLX_MAX_CONCURRENCY", "1")),
        visible_in_ui=True,
        supported=capabilities.subprocess_capable,
        unsupported_reason=None if capabilities.subprocess_capable else "not available on this device",
        python_executable=os.environ.get("FICHERO_OMLX_PYTHON"),
        command=command,
    )


def _local_profiles() -> list[LocalProviderProfile]:
    return [_configured_omlx_profile()]


def _local_catalog_entries() -> list[LocalModelCatalogEntry]:
    return get_mlx_model_store().list_catalog_entries()


def _manager_for_profile(profile_id: str) -> LocalInferenceServiceManager:
    profile = _profile_by_id(profile_id)
    existing = _MANAGERS.get(profile_id)
    if existing is not None and existing.profile == profile:
        return existing
    process = (
        ManagedLocalInferenceProcess(profile)
        if profile.managed_by_app
        else ExternalLocalInferenceProcess()
    )
    manager = LocalInferenceServiceManager(
        profile,
        process,
    )
    _MANAGERS[profile_id] = manager
    return manager


async def shutdown_managed_local_inference_services() -> None:
    for manager in list(_MANAGERS.values()):
        if manager.profile.managed_by_app:
            await manager.stop()


def _profile_by_id(profile_id: str) -> LocalProviderProfile:
    for profile in _local_profiles():
        if profile.id == profile_id:
            return profile
    raise HTTPException(status_code=404, detail=f"Local inference profile not found: {profile_id}")


def _runtime_status_response() -> LocalInferenceRuntimeStatusResponse:
    payload = get_mlx_runtime().status()
    job = payload.get("job")
    return LocalInferenceRuntimeStatusResponse(
        provisioned=bool(payload["provisioned"]),
        mlx_lm_version=payload.get("mlx_lm_version"),
        disk_usage_bytes=int(payload.get("disk_usage_bytes", 0)),
        python_path=payload.get("python_path"),
        runtime_dir=str(payload["runtime_dir"]),
        job=LocalInferenceRuntimeJobResponse(**job) if isinstance(job, dict) else None,
    )


def _download_job_response(job_id: str) -> LocalInferenceModelDownloadJobResponse:
    job = get_mlx_model_store().job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Model download job not found: {job_id}")
    return LocalInferenceModelDownloadJobResponse(**job.to_dict())


def _capabilities_response() -> LocalInferenceCapabilitiesResponse:
    payload: LocalInferenceCapabilities = get_local_inference_capabilities()
    return LocalInferenceCapabilitiesResponse(**payload.model_dump())


@router.get("/profiles", response_model=LocalInferenceProfileListResponse)
async def list_local_inference_profiles() -> LocalInferenceProfileListResponse:
    """List app-managed local inference profiles available to the app."""
    profiles = _local_profiles()
    return LocalInferenceProfileListResponse(items=profiles, count=len(profiles))


@router.get("/catalog", response_model=LocalInferenceCatalogResponse)
async def list_local_inference_catalog() -> LocalInferenceCatalogResponse:
    """List local inference model catalog entries for configured profiles."""
    entries = _local_catalog_entries()
    return LocalInferenceCatalogResponse(items=entries, count=len(entries))


@router.get("/capabilities", response_model=LocalInferenceCapabilitiesResponse)
async def get_local_inference_capabilities_route() -> LocalInferenceCapabilitiesResponse:
    """Return cached machine facts for local-model support gating."""
    return _capabilities_response()


@router.post("/profiles/validate", response_model=LocalInferenceValidationResponse)
async def validate_local_inference_profile(
    profile: LocalProviderProfile,
) -> LocalInferenceValidationResponse:
    """Validate a local provider profile against no-cloud invariants."""
    return LocalInferenceValidationResponse(valid=True, profile=profile)


@router.get(
    "/profiles/{profile_id}/status",
    response_model=LocalInferenceServiceStatus,
)
async def get_local_inference_status(
    profile_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceServiceStatus:
    """Return current lifecycle status for an app-managed local provider."""
    manager = _manager_for_profile(profile_id)
    return manager.status()


@router.post(
    "/profiles/{profile_id}/health",
    response_model=LocalInferenceServiceStatus,
)
async def check_local_inference_health(
    profile_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceServiceStatus:
    """Poll health for an app-managed local provider."""
    manager = _manager_for_profile(profile_id)
    return await manager.health()


@router.post(
    "/profiles/{profile_id}/start",
    response_model=LocalInferenceServiceStatus,
)
async def start_local_inference_profile(
    profile_id: Annotated[str, Path(min_length=1)],
    request: LocalInferenceStartRequest | None = None,
) -> LocalInferenceServiceStatus:
    """Start or warm an app-managed local provider and wait for health."""
    manager = _manager_for_profile(profile_id)
    try:
        return await manager.start(
            timeout_seconds=request.timeout_seconds if request is not None else None
        )
    except LocalInferenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LocalInferenceRuntimeMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LocalModelHardwareError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LocalModelNotInstalledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/profiles/{profile_id}/stop",
    response_model=LocalInferenceServiceStatus,
)
async def stop_local_inference_profile(
    profile_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceServiceStatus:
    """Mark an app-managed local provider stopped."""
    manager = _manager_for_profile(profile_id)
    return await manager.stop()


@router.get("/runtime", response_model=LocalInferenceRuntimeStatusResponse)
async def get_local_inference_runtime_status() -> LocalInferenceRuntimeStatusResponse:
    """Return MLX runtime provisioning status for the managed oMLX sidecar."""
    return _runtime_status_response()


@router.post("/runtime/provision", response_model=LocalInferenceRuntimeStatusResponse)
async def provision_local_inference_runtime() -> LocalInferenceRuntimeStatusResponse:
    """Start or reuse the coalesced MLX runtime provisioning job."""
    await get_mlx_runtime().start_provision()
    return _runtime_status_response()


@router.delete("/runtime", response_model=LocalInferenceRuntimeStatusResponse)
async def remove_local_inference_runtime() -> LocalInferenceRuntimeStatusResponse:
    """Remove the dedicated MLX runtime venv when it is not provisioning."""
    try:
        get_mlx_runtime().remove()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _runtime_status_response()


@router.post(
    "/models/{model_id:path}/download",
    response_model=LocalInferenceModelDownloadJobResponse,
)
async def download_local_inference_model(
    model_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceModelDownloadJobResponse:
    """Start or reuse a managed MLX model download job."""
    try:
        job = await get_mlx_model_store().start_download(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LocalModelHardwareError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return LocalInferenceModelDownloadJobResponse(**job.to_dict())


@router.get(
    "/models/downloads/{job_id}",
    response_model=LocalInferenceModelDownloadJobResponse,
)
async def get_local_inference_model_download(
    job_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceModelDownloadJobResponse:
    """Return progress for a managed MLX model download job."""
    return _download_job_response(job_id)


@router.post(
    "/models/downloads/{job_id}/cancel",
    response_model=LocalInferenceModelDownloadJobResponse,
)
async def cancel_local_inference_model_download(
    job_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceModelDownloadJobResponse:
    """Cancel a managed MLX model download job."""
    job = get_mlx_model_store().job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Model download job not found: {job_id}")
    if job.state not in {"queued", "running"}:
        return LocalInferenceModelDownloadJobResponse(**job.to_dict())
    await get_mlx_model_store().cancel(job_id)
    return _download_job_response(job_id)


@router.delete(
    "/models/{model_id:path}",
    response_model=LocalInferenceModelDeleteResponse,
)
def delete_local_inference_model(
    model_id: Annotated[str, Path(min_length=1)],
) -> LocalInferenceModelDeleteResponse:
    """Delete one managed MLX model from the local store."""
    try:
        freed = get_mlx_model_store().delete(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocalInferenceModelDeleteResponse(status="ok", freed_bytes=freed)
