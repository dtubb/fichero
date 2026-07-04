"""Typed API surface for app-managed local inference providers."""

from __future__ import annotations

import os
import shlex
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from fichero.local_inference import (
    ExternalLocalInferenceProcess,
    LocalInferenceRuntimeMissingError,
    LocalInferenceServiceManager,
    LocalInferenceServiceStatus,
    LocalInferenceValidationError,
    LocalModelCatalogEntry,
    LocalModelSource,
    LocalProviderProfile,
    ManagedLocalInferenceProcess,
)

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


def _configured_omlx_profile() -> LocalProviderProfile:
    """Build the default app-managed oMLX profile from env/defaults."""
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
        python_executable=os.environ.get("FICHERO_OMLX_PYTHON"),
        command=command,
    )


def _local_profiles() -> list[LocalProviderProfile]:
    return [_configured_omlx_profile()]


def _local_catalog_entries() -> list[LocalModelCatalogEntry]:
    profile = _configured_omlx_profile()
    return [
        LocalModelCatalogEntry(
            provider_type=profile.provider_type,
            model_id=profile.model_id,
            display_name=profile.model_id,
            capabilities=["text", "vision"],
            installed=False,
            memory_class="unified-memory",
            license_label="user-managed",
            source=LocalModelSource.user_configured,
        )
    ]


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


def _profile_by_id(profile_id: str) -> LocalProviderProfile:
    for profile in _local_profiles():
        if profile.id == profile_id:
            return profile
    raise HTTPException(status_code=404, detail=f"Local inference profile not found: {profile_id}")


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
