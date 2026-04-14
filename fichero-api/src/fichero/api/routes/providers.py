"""
Provider Routes

API endpoints for managing LLM providers and models.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from fichero.db import Database
from fichero.app_db import get_app_db, AppDatabase
from fichero.api.main import get_library_database
from fichero.models import Model, Provider, ProviderRef, ProviderType
from fichero.providers import (
    get_provider_info,
    list_providers as list_catalog_providers,
)
from fichero.keychain import (
    set_api_key,
    delete_api_key,
    has_api_key,
)
from fichero.api.routes.provider_models import (  # noqa: F401 (re-exported for tests)
    ProviderCatalogResponse,
    ProviderResponse,
    ModelResponse,
    UserModelResponse,
    ProviderCreate,
    ProviderUpdate,
    ModelCreate,
    router as models_router,
    generate_model_description,
)
from fichero.api.routes.provider_keys import router as keys_router

logger = logging.getLogger(__name__)
router = APIRouter()

# Include sub-routers
router.include_router(models_router)
router.include_router(keys_router)


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else current time."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else datetime.now().isoformat()
    )


# =============================================================================
# Dependencies
# =============================================================================


def get_app_database() -> AppDatabase:
    return get_app_db()


# =============================================================================
# Catalog Routes (read-only info about available providers)
# =============================================================================


@router.get("/catalog")
async def list_provider_catalog() -> list[ProviderCatalogResponse]:
    """List all available providers from the catalog, sorted by sort_order."""
    result = []
    for info in list_catalog_providers():
        result.append(
            ProviderCatalogResponse(
                type=info.type.value,
                name=info.name,
                description=info.description,
                api_key_env=info.api_key_env,
                api_key_url=info.api_key_url,
                is_local=info.is_local,
                is_builtin=info.is_builtin,
                supports_vision=info.supports_vision,
                supports_embeddings=info.supports_embeddings,
                supports_streaming=info.supports_streaming,
                default_model=info.default_model,
                has_api_key=has_api_key(info.type.value) if not info.is_local else True,
                icon=info.icon,
                logo_asset=info.logo_asset,
                color=info.color,
                sort_order=info.sort_order,
            )
        )
    result.sort(key=lambda x: x.sort_order)
    return result


@router.get("/catalog/{provider_type}")
async def get_catalog_provider(provider_type: str) -> ProviderCatalogResponse:
    """Get info about a specific provider type."""
    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(
            status_code=404, detail=f"Provider type not found: {provider_type}"
        )

    return ProviderCatalogResponse(
        type=info.type.value,
        name=info.name,
        description=info.description,
        api_key_env=info.api_key_env,
        api_key_url=info.api_key_url,
        is_local=info.is_local,
        is_builtin=info.is_builtin,
        supports_vision=info.supports_vision,
        supports_embeddings=info.supports_embeddings,
        supports_streaming=info.supports_streaming,
        default_model=info.default_model,
        has_api_key=has_api_key(info.type.value) if not info.is_local else True,
        icon=info.icon,
        logo_asset=info.logo_asset,
        color=info.color,
        sort_order=info.sort_order,
    )


# =============================================================================
# User Provider Configuration
# =============================================================================


@router.get("")
async def list_providers(
    app_db: AppDatabase = Depends(get_app_database),
) -> list[ProviderResponse]:
    """List user's configured providers (app-wide)."""
    providers = app_db.list_providers()
    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            provider_type=p.provider_type.value,
            api_base=p.api_base,
            enabled=p.enabled,
            sort_order=p.sort_order,
            has_api_key=has_api_key(p.provider_type.value),
            created_at=p.created_at.isoformat(),
        )
        for p in providers
    ]


@router.post("")
async def create_provider(
    request: ProviderCreate,
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderResponse:
    """Create a new provider configuration (app-wide)."""
    try:
        ptype = ProviderType(request.provider_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid provider type: {request.provider_type}"
        )

    info = get_provider_info(ptype)
    if not info:
        raise HTTPException(
            status_code=400, detail=f"Unknown provider type: {request.provider_type}"
        )

    provider = Provider(
        name=request.name or info.name,
        provider_type=ptype,
        api_base=request.api_base,
        enabled=True,
    )
    app_db.save_provider(provider)

    if request.api_key:
        set_api_key(request.provider_type, request.api_key)

    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type.value,
        api_base=provider.api_base,
        enabled=provider.enabled,
        sort_order=provider.sort_order,
        has_api_key=has_api_key(request.provider_type),
        created_at=_safe_isoformat(getattr(provider, "created_at", None)),
    )


# =============================================================================
# Library Provider References (Library-Specific)
# =============================================================================


class ProviderRefCreate(BaseModel):
    """Request to add a provider reference to a library."""

    provider_id: str


class ProviderRefUpdate(BaseModel):
    """Request to update a provider reference."""

    enabled: bool | None = None
    sort_order: int | None = None


class DeletedResponse(BaseModel):
    status: str


class ProviderRefResponse(BaseModel):
    """Provider reference response with full provider details."""

    id: str
    provider_id: str
    provider_name: str
    provider_type: str
    enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


@router.get("/refs")
async def list_library_provider_refs(
    db: Database = Depends(get_library_database),
    app_db: AppDatabase = Depends(get_app_database),
) -> list[ProviderRefResponse]:
    """List all provider references for this library."""
    refs = db.query(ProviderRef)

    response = []
    for ref in refs:
        provider = app_db.get_provider(ref.provider_id)
        if provider:
            response.append(
                ProviderRefResponse(
                    id=ref.id,
                    provider_id=ref.provider_id,
                    provider_name=provider.name,
                    provider_type=provider.provider_type.value,
                    enabled=ref.enabled,
                    sort_order=ref.sort_order,
                    created_at=ref.created_at,
                    updated_at=ref.updated_at,
                )
            )

    return response


@router.post("/refs")
async def add_provider_ref(
    request: ProviderRefCreate,
    db: Database = Depends(get_library_database),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderRefResponse:
    """Add a provider reference to this library."""
    provider = app_db.get_provider(request.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    existing_refs = db.query(ProviderRef, provider_id=request.provider_id)
    if existing_refs:
        raise HTTPException(
            status_code=400, detail="Provider already referenced by this library"
        )

    ref = ProviderRef(
        provider_id=request.provider_id,
        enabled=True,
        sort_order=0,
    )
    db.save(ref)

    return ProviderRefResponse(
        id=ref.id,
        provider_id=ref.provider_id,
        provider_name=provider.name,
        provider_type=provider.provider_type.value,
        enabled=ref.enabled,
        sort_order=ref.sort_order,
        created_at=ref.created_at,
        updated_at=ref.updated_at,
    )


@router.patch("/refs/{ref_id}")
async def update_provider_ref(
    ref_id: str,
    request: ProviderRefUpdate,
    db: Database = Depends(get_library_database),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderRefResponse:
    """Update a provider reference."""
    ref = db.get(ProviderRef, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Provider reference not found")

    if request.enabled is not None:
        ref.enabled = request.enabled
    if request.sort_order is not None:
        ref.sort_order = request.sort_order

    ref.updated_at = datetime.now()
    db.save(ref)

    provider = app_db.get_provider(ref.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Referenced provider not found")

    return ProviderRefResponse(
        id=ref.id,
        provider_id=ref.provider_id,
        provider_name=provider.name,
        provider_type=provider.provider_type.value,
        enabled=ref.enabled,
        sort_order=ref.sort_order,
        created_at=ref.created_at,
        updated_at=ref.updated_at,
    )


@router.delete("/refs/{ref_id}")
async def delete_provider_ref(
    ref_id: str,
    db: Database = Depends(get_library_database),
) -> DeletedResponse:
    """Remove a provider reference from this library."""
    ref = db.get(ProviderRef, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Provider reference not found")

    db.delete(ref)
    return DeletedResponse(status="deleted")


@router.get("/{provider_id}")
async def get_provider(
    provider_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderResponse:
    """Get a specific provider configuration (app-wide)."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type.value,
        api_base=provider.api_base,
        enabled=provider.enabled,
        sort_order=provider.sort_order,
        has_api_key=has_api_key(provider.provider_type.value),
        created_at=provider.created_at.isoformat(),
    )


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: str,
    request: ProviderUpdate,
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderResponse:
    """Update a provider configuration (app-wide)."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if request.name is not None:
        provider.name = request.name
    if request.api_base is not None:
        provider.api_base = request.api_base
    if request.enabled is not None:
        provider.enabled = request.enabled

    app_db.save_provider(provider)

    if request.api_key is not None:
        if request.api_key:
            set_api_key(provider.provider_type.value, request.api_key)
        else:
            delete_api_key(provider.provider_type.value)

    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type.value,
        api_base=provider.api_base,
        enabled=provider.enabled,
        sort_order=provider.sort_order,
        has_api_key=has_api_key(provider.provider_type.value),
        created_at=provider.created_at.isoformat(),
    )


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> DeletedResponse:
    """Delete a provider (app-wide). Models are cascade deleted."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    app_db.delete_provider(provider_id)
    return DeletedResponse(status="deleted")


# =============================================================================
# User Model Configuration
# =============================================================================


@router.get("/{provider_id}/models")
async def list_provider_models(
    provider_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> list[UserModelResponse]:
    """List user's configured models for a provider."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    models = app_db.list_models(provider_id)
    return [
        UserModelResponse(
            id=m.id,
            provider_id=m.provider_id,
            name=m.name,
            model_id=m.model_id,
            capabilities=m.capabilities,
            is_default=m.is_default,
            enabled=m.enabled,
            input_cost=m.input_cost,
            output_cost=m.output_cost,
        )
        for m in models
    ]


@router.post("/{provider_id}/models")
async def add_model_to_provider(
    provider_id: str,
    request: ModelCreate,
    app_db: AppDatabase = Depends(get_app_database),
) -> UserModelResponse:
    """Add a model configuration to a provider."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    from fichero.llm import get_model_cost

    cost_info = get_model_cost(f"{provider.provider_type.value}/{request.model_id}")

    model = Model(
        provider_id=provider_id,
        name=request.name or request.model_id,
        model_id=request.model_id,
        is_default=request.is_default,
        input_cost=cost_info.get("input_cost_per_token") * 1_000_000
        if cost_info
        else None,
        output_cost=cost_info.get("output_cost_per_token") * 1_000_000
        if cost_info
        else None,
    )
    app_db.save_model(model)

    return UserModelResponse(
        id=model.id,
        provider_id=model.provider_id,
        name=model.name,
        model_id=model.model_id,
        capabilities=model.capabilities,
        is_default=model.is_default,
        enabled=model.enabled,
        input_cost=model.input_cost,
        output_cost=model.output_cost,
    )


@router.delete("/{provider_id}/models/{model_id}")
async def remove_model_from_provider(
    provider_id: str,
    model_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> DeletedResponse:
    """Remove a model from a provider."""
    models = app_db.list_models(provider_id)
    model_exists = any(m.id == model_id for m in models)

    if not model_exists:
        raise HTTPException(status_code=404, detail="Model not found")

    app_db.delete_model(model_id)
    return DeletedResponse(status="deleted")
