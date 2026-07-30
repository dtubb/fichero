"""
Provider Routes

API endpoints for managing LLM providers and models.
"""

import logging
from datetime import datetime
from fichero_server.core.timeutil import utc_now

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from fichero_server.db import Database
from fichero_server.db.app import get_app_db, AppDatabase
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.auth.accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
)
from fichero_server.models import Model, Provider, ProviderRef, ProviderType
from fichero_server.models import AppleIntelligenceProbeResponse
from fichero_server.llm.providers import (
    get_provider_info,
    list_providers as list_catalog_providers,
)
from fichero_server.security.keychain import (
    set_api_key,
    delete_api_key,
    has_api_key,
)
from fichero_server.llm.provider_validation import (
    validate_provider_config,
    ProviderValidationError,
)
from fichero_server.api.routes.ai.provider_models import (  # noqa: F401 (re-exported for tests)
    ProviderCatalogResponse,
    ProviderCatalogListResponse,
    ProviderResponse,
    ProviderListResponse,
    ModelResponse,
    ModelListResponse,
    UserModelResponse,
    UserModelListResponse,
    ProviderCreate,
    ProviderUpdate,
    ModelCreate,
    router as models_router,
    generate_model_description,
)
from fichero_server.api.routes.ai.provider_keys import router as keys_router
# NOTE: fichero_server.llm is imported inside the one handler that probes the
# Apple Intelligence bridge (#3950) — it pulls langchain_core at startup.

logger = logging.getLogger(__name__)
# Passthrough wrappers, NOT deferred imports at the call sites (#3950).
#
# These names are part of this module's TEST SURFACE — tests patch
# `fichero_server.api.routes.ai.providers.<name>`. Two things must both hold:
#   1. the name exists as a module attribute, or mock.patch raises
#      AttributeError ("module has no attribute ...");
#   2. the call site resolves it as a module GLOBAL, so the patch takes effect.
# A function-local import at the call site satisfies NEITHER: it removes the
# attribute AND binds a local that shadows any patch — letting a test pass
# while silently exercising the real implementation. A module-level __getattr__
# (PEP 562) fixes (1) but not (2), because LOAD_GLOBAL inside this module never
# consults it. The wrapper satisfies both and still keeps fichero_server.llm
# (langchain_core) off the engine startup path.


def probe_apple_intelligence_bridge(*args, **kwargs):
    """Passthrough to fichero_server.llm.probe_apple_intelligence_bridge; imports it on first call (#3950)."""
    from fichero_server.llm import probe_apple_intelligence_bridge as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


router = APIRouter(dependencies=[Depends(_require_authenticated_or_bootstrap)])

# Include sub-routers
router.include_router(models_router)
router.include_router(keys_router)


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else current time."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else utc_now().isoformat()
    )


# =============================================================================
# Apple Intelligence availability probe
# =============================================================================


@router.get("/apple/availability", response_model=AppleIntelligenceProbeResponse)
@router.get("/apple-intelligence/probe", response_model=AppleIntelligenceProbeResponse)
async def probe_apple_intelligence() -> AppleIntelligenceProbeResponse:
    """Quick check: is Apple Intelligence usable on this device?

    Used by the onboarding wizard so the user doesn't pick "Apple Intelligence"
    and then hit `kind: unavailable` later when they run a workflow. Runs fm-bridge
    in `--probe` mode (availability check only — no generation, no model warm-up).
    """
    available, reason = await probe_apple_intelligence_bridge()
    return AppleIntelligenceProbeResponse(
        available=available,
        reason=reason,
    )


# =============================================================================
# Dependencies
# =============================================================================


def get_app_database() -> AppDatabase:
    return get_app_db()


# =============================================================================
# Catalog Routes (read-only info about available providers)
# =============================================================================


@router.get("/catalog", response_model=ProviderCatalogListResponse)
async def list_provider_catalog() -> ProviderCatalogListResponse:
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
    return ProviderCatalogListResponse(items=result, count=len(result))


@router.get(
    "/catalog/{provider_type}",
    response_model=ProviderCatalogResponse,
)
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


@router.get("", response_model=ProviderListResponse)
async def list_providers(
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderListResponse:
    """List user's configured providers (app-wide)."""
    providers = app_db.list_providers()
    items = [
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
    return ProviderListResponse(items=items, count=len(items))


def create_provider_impl(
    app_db: AppDatabase, request: ProviderCreate
) -> tuple[Provider, bool]:
    """Create-or-upsert a provider (app-wide). Returns ``(provider, created)``.

    Extracted verbatim from the ``create_provider`` route so BOTH the route and
    the ``provider.create`` action (EPIC #1848) drive the *same* validation +
    upsert (iterate-not-replace: the algorithm is wrapped, never re-derived).
    ``created`` is True only when a NEW provider row was inserted (vs an existing
    ``(name, provider_type)`` row being updated, see #704) — the
    ``provider.create`` undo uses it to know whether deleting the row is a safe
    inverse. Raises ``HTTPException`` on bad input exactly as the route did.
    """
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

    # Validate configuration at save time
    try:
        validate_provider_config(
            provider_type=request.provider_type,
            api_key=request.api_key,
            api_base=request.api_base,
        )
    except ProviderValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    target_name = request.name or info.name

    # #704: upsert on (name, provider_type) instead of creating a fresh row
    # each time. The previous behaviour generated a new UUID per POST, and
    # since save_provider's ON CONFLICT clause is keyed on `id`, duplicates
    # accumulated — this created identical 'My OpenAI' entries during
    # 0.0.2 testing.
    existing = next(
        (
            p for p in app_db.list_providers()
            if p.provider_type == ptype and p.name == target_name
        ),
        None,
    )
    if existing is not None:
        existing.api_base = request.api_base
        existing.enabled = True
        app_db.save_provider(existing)
        provider = existing
        created = False
    else:
        provider = Provider(
            name=target_name,
            provider_type=ptype,
            api_base=request.api_base,
            enabled=True,
        )
        app_db.save_provider(provider)
        created = True

    if request.api_key:
        set_api_key(request.provider_type, request.api_key)

    return provider, created


def _broadcast_provider_change(verb: str) -> None:
    """Fan a provider mutation out to EVERY library's change stream (#4276).

    Providers are app-wide but the change stream is library-keyed, so a
    provider/key/model change fans out to all live subscribers. Windows drop
    their provider-derived caches (Run Workflow submenu's provider list) on
    ``provider.*`` events — without this, a provider added from another
    window / device / the CLI never reached this app's menus.
    """
    from fichero_server.api.change_stream import emit_change_all_libraries

    emit_change_all_libraries(type=f"provider.{verb}")


@router.post("")
async def create_provider(
    request: ProviderCreate,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderResponse:
    """Create a new provider configuration (app-wide)."""
    provider, _created = create_provider_impl(app_db, request)
    _broadcast_provider_change("created")

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


class ProviderRefListResponse(BaseModel):
    """Envelope for a list of library provider references."""

    items: list[ProviderRefResponse]
    count: int


@router.get("/refs", response_model=ProviderRefListResponse)
async def list_library_provider_refs(
    db: Database = Depends(get_library_database),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderRefListResponse:
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

    return ProviderRefListResponse(items=response, count=len(response))


@router.post("/refs")
async def add_provider_ref(
    request: ProviderRefCreate,
    db: Database = Depends(get_library_database_for_write),
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
    _broadcast_provider_change("updated")

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


def update_provider_ref_impl(
    db: Database, ref_id: str, request: ProviderRefUpdate
) -> ProviderRef:
    """Apply a library provider-reference update. Returns the saved ref.

    Extracted from the route so route + ``provider.update_ref`` action share the
    same field-merge (iterate-not-replace). ProviderRef is a *library* model, so
    this operates on the library ``db`` (not app_db). Raises 404 if missing.
    """
    ref = db.get(ProviderRef, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Provider reference not found")

    if request.enabled is not None:
        ref.enabled = request.enabled
    if request.sort_order is not None:
        ref.sort_order = request.sort_order

    ref.updated_at = utc_now()
    db.save(ref)
    return ref


@router.patch("/refs/{ref_id}")
async def update_provider_ref(
    ref_id: str,
    request: ProviderRefUpdate,
    db: Database = Depends(get_library_database_for_write),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderRefResponse:
    """Update a provider reference."""
    ref = update_provider_ref_impl(db, ref_id, request)
    _broadcast_provider_change("updated")

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


def delete_provider_ref_impl(db: Database, ref_id: str) -> ProviderRef:
    """Remove a library provider reference. Returns the deleted ref.

    Returns the ref so the ``provider.delete_ref`` action can snapshot it for
    undo. Extracted from the route (iterate-not-replace). Raises 404 if missing.
    """
    ref = db.get(ProviderRef, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Provider reference not found")

    db.delete(ref)
    return ref


@router.delete("/refs/{ref_id}")
async def delete_provider_ref(
    ref_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> DeletedResponse:
    """Remove a provider reference from this library."""
    delete_provider_ref_impl(db, ref_id)
    _broadcast_provider_change("updated")
    return DeletedResponse(status="deleted")


@router.get("/{provider_id}", response_model=ProviderResponse)
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


def update_provider_impl(
    app_db: AppDatabase, provider_id: str, request: ProviderUpdate
) -> Provider:
    """Apply a provider config update (app-wide). Returns the saved provider.

    Extracted from the ``update_provider`` route so the route and the
    ``provider.update`` action share the exact same field-merge + keychain
    side-effect (iterate-not-replace). PATCH semantics: a ``None`` field means
    "leave unchanged". Raises 404 if the provider doesn't exist.
    """
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

    return provider


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    request: ProviderUpdate,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> ProviderResponse:
    """Update a provider configuration (app-wide)."""
    provider = update_provider_impl(app_db, provider_id, request)
    _broadcast_provider_change("updated")

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


def delete_provider_impl(app_db: AppDatabase, provider_id: str) -> Provider:
    """Delete a provider + cascade-delete its models (app-wide).

    Returns the provider that was deleted (so the ``provider.delete`` action can
    snapshot it for undo). Extracted from the route so route + action share the
    same delete (iterate-not-replace). Raises 404 if it doesn't exist.
    """
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    app_db.delete_provider(provider_id)
    return provider


@router.delete("/{provider_id}", response_model=DeletedResponse)
async def delete_provider(
    provider_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> DeletedResponse:
    """Delete a provider (app-wide). Models are cascade deleted."""
    delete_provider_impl(app_db, provider_id)
    _broadcast_provider_change("deleted")
    return DeletedResponse(status="deleted")


# =============================================================================
# User Model Configuration
# =============================================================================


@router.get("/{provider_id}/models", response_model=UserModelListResponse)
async def list_provider_models(
    provider_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> UserModelListResponse:
    """List user's configured models for a provider."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    models = app_db.list_models(provider_id)
    items = [
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
    return UserModelListResponse(items=items, count=len(items))


# Canonical capability map for built-in Apple model_ids. Kept in
# lockstep with the seed list in main.py — both write the same caps
# so the seeded row and a re-added row carry identical metadata.
# Adding a new built-in: extend here AND in main.py's builtins list.
_CANONICAL_APPLE_CAPABILITIES: dict[str, list[str]] = {
    "apple-intelligence": ["text"],
    "apple-vision": ["vision"],
    "apple-speech": ["audio", "transcription"],
}


def _canonical_capabilities_for_model_id(model_id: str) -> list[str]:
    r"""Return the canonical capability list for a known built-in
    model_id, or an empty list when the id is user-defined / unknown.

    Used by the +Add Model endpoint to preserve capability badges
    when a user deletes a built-in Apple model row and adds it back —
    without this lookup, the re-added row had `capabilities=[]` so
    inspector badges disappeared (#939) and Defaults capability
    filtering (#940) had nothing to filter on.
    """
    return list(_CANONICAL_APPLE_CAPABILITIES.get(model_id, []))


def _derive_capabilities_from_registry(provider_type: str, model_id: str) -> list[str]:
    r"""Derive a capability list for a cloud model from LiteLLM's registry.

    The +Add Model request carries only a `model_id`, so before #1290
    every cloud model was saved with `capabilities=[]` (the canonical
    lookup only knows the built-in Apple ids). With no capability
    metadata, the Defaults capability filter couldn't tell which tier a
    model fits, so saved cloud models surfaced as
    "(saved — wrong capability)" in the Settings → Defaults pickers.

    Read the capabilities from the registry instead of hardcoding them —
    mirror the flags LiteLLM already exposes (`mode`, `supports_vision`,
    `supports_audio_input`, `supports_function_calling`). The strings
    emitted here match the tier vocabulary the Defaults picker filters
    on: ``text``/``vision``/``audio``/``transcription``/``tools``.
    Returns ``[]`` when the model is unknown to the registry.
    """
    if provider_type == "omlx":
        model_lower = model_id.lower()
        caps = ["text"]
        if any(
            token in model_lower
            for token in ("vl", "vision", "ocr", "nanonets", "chandra")
        ):
            caps.append("vision")
        return caps

    try:
        from fichero_server.llm import list_models_for_provider as llm_list_models

        registry = {m["model_id"]: m for m in llm_list_models(provider_type)}
    except Exception as exc:  # pragma: no cover - registry lookup is best-effort
        logger.warning("Capability derivation failed for %s: %s", model_id, exc)
        return []

    info = registry.get(model_id)
    if not info:
        return []

    caps: list[str] = []
    mode = str(info.get("mode") or "chat").lower()

    if mode in ("chat", "completion", "responses"):
        caps.append("text")
    if mode == "audio_transcription" or info.get("supports_audio_input"):
        caps.extend(["audio", "transcription"])
    if info.get("supports_vision"):
        caps.append("vision")
    if info.get("supports_function_calling"):
        caps.append("tools")
    if mode == "embedding":
        caps.append("embedding")

    # De-duplicate while preserving first-seen order.
    seen: set[str] = set()
    return [c for c in caps if not (c in seen or seen.add(c))]


@router.post("/{provider_id}/models")
async def add_model_to_provider(
    provider_id: str,
    request: ModelCreate,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> UserModelResponse:
    """Add a model configuration to a provider."""
    provider = app_db.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    from fichero_server.llm import get_model_cost

    cost_info = get_model_cost(f"{provider.provider_type.value}/{request.model_id}")

    # Look up canonical capabilities for built-in model_ids (#939). When
    # the user adds a known Apple model via the +Add Model button, the
    # incoming request doesn't carry a capabilities list — but the model
    # has fixed known capabilities ("apple-vision" is vision-only,
    # "apple-speech" is audio/transcription, "apple-intelligence" is
    # text). Without this lookup, the saved row had \\\`capabilities=[]\\\`
    # so the inspector lost the capability badges and the Defaults
    # picker couldn't filter (#940 hard-blocked).
    #
    # Cloud models aren't in that built-in map, so derive their
    # capabilities from the LiteLLM registry instead of saving them
    # capability-less (#1290) — otherwise the Defaults pickers can't
    # tell which slot a cloud model fits and reject the saved choice
    # as "(saved — wrong capability)".
    capabilities = _canonical_capabilities_for_model_id(request.model_id)
    if not capabilities:
        capabilities = _derive_capabilities_from_registry(
            provider.provider_type.value, request.model_id
        )

    model = Model(
        provider_id=provider_id,
        name=request.name or request.model_id,
        model_id=request.model_id,
        capabilities=capabilities,
        is_default=request.is_default,
        input_cost=cost_info.get("input_cost_per_token") * 1_000_000
        if cost_info
        else None,
        output_cost=cost_info.get("output_cost_per_token") * 1_000_000
        if cost_info
        else None,
    )
    app_db.save_model(model)
    _broadcast_provider_change("updated")

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


def remove_model_impl(app_db: AppDatabase, provider_id: str, model_id: str) -> Model:
    """Remove a model from a provider. Returns the deleted model.

    Returns the model (so the ``provider.remove_model`` action can snapshot it
    for undo). Extracted from the route (iterate-not-replace). The 404 is keyed
    on the model belonging to ``provider_id`` exactly as the route did. Raises
    404 if the model isn't found under that provider.
    """
    models = app_db.list_models(provider_id)
    model = next((m for m in models if m.id == model_id), None)

    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    app_db.delete_model(model_id)
    return model


@router.delete("/{provider_id}/models/{model_id}")
async def remove_model_from_provider(
    provider_id: str,
    model_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
    app_db: AppDatabase = Depends(get_app_database),
) -> DeletedResponse:
    """Remove a model from a provider."""
    remove_model_impl(app_db, provider_id, model_id)
    _broadcast_provider_change("updated")
    return DeletedResponse(status="deleted")


# =============================================================================
# Action layer registration (EPIC #1848 / sweep #2014) — PROVIDER domain
# =============================================================================
#
# Every mutating provider route above gets ONE registered action that WRAPS its
# proven ``*_impl`` (iterate-not-replace) and routes through ``registry.invoke``,
# which writes the generic ActionAudit + emits a change event. The original typed
# routes still call the same ``*_impl`` directly and stay green; the action is the
# *additional* uniform path that chat tools / App Intents / tests drive via
# POST /api/actions/invoke (mirrors the entity.merge pilot).
#
# Two domain-specific wrinkles drive the shapes below:
#   * Provider/Model are *app-wide* (AppDatabase), so each ``execute`` reaches
#     ``get_app_db()`` for the mutation; the library ``db`` handed to ``invoke``
#     only carries the ActionAudit row. ProviderRef is a *library* model, so its
#     actions use ``db`` directly.
#   * ``registry.invoke`` dumps ``params.model_dump()`` into the audit row, so any
#     secret (``api_key``) MUST be ``Field(exclude=True)`` on the params model —
#     readable as an attribute in ``execute`` but never serialized into the audit.

from pydantic import ConfigDict, Field  # noqa: E402

from fichero_server.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


# -- params models -----------------------------------------------------------


class ProviderCreateParams(ProviderCreate):
    """provider.create params. ``api_key`` is secret → excluded from the audit."""

    api_key: str | None = Field(default=None, exclude=True)


class ProviderUpdateParams(ProviderUpdate):
    """provider.update params — the PATCH body plus the target id.

    ``api_key`` is secret → excluded from the audit serialization.
    """

    provider_id: str
    api_key: str | None = Field(default=None, exclude=True)


class ProviderDeleteParams(BaseModel):
    provider_id: str


class RemoveModelParams(BaseModel):
    provider_id: str
    model_id: str


class UpdateProviderRefParams(BaseModel):
    ref_id: str
    enabled: bool | None = None
    sort_order: int | None = None


class DeleteProviderRefParams(BaseModel):
    ref_id: str


class RestoreProviderParams(BaseModel):
    """Inverse of provider.delete — re-create the provider + its models."""

    provider: dict
    models: list[dict] = Field(default_factory=list)


class RestoreModelParams(BaseModel):
    """Inverse of provider.remove_model — re-create the model row."""

    model_config = ConfigDict(protected_namespaces=())
    model: dict


class RestoreProviderRefParams(BaseModel):
    """Inverse of provider.delete_ref — re-create the library ProviderRef."""

    ref: dict


def _provider_public_dict(provider: Provider) -> dict:
    """Non-secret provider fields for an action's ``result`` payload."""
    return {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider.provider_type.value,
        "api_base": provider.api_base,
        "enabled": provider.enabled,
        "sort_order": provider.sort_order,
    }


# -- provider.create ---------------------------------------------------------


def _invert_create_provider(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    # Only a genuinely-inserted row is safe to undo by deletion. An upsert that
    # UPDATED a pre-existing (name, provider_type) row must NOT be undone by
    # deleting that row — return None so the undo endpoint reports "no inverse".
    if not after or not after.get("created"):
        return None
    pid = after.get("provider_id")
    return ("provider.delete", {"provider_id": pid}) if pid else None


@action(
    "provider.create",
    ProviderCreateParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_create_provider,
)
def _action_create_provider(
    db, params: ProviderCreateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    provider, created = create_provider_impl(app_db, params)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[provider.id],
        before=None,
        after={"provider_id": provider.id, "created": created},
        emit_type="provider.created",
    )
    return _provider_public_dict(provider), spec


# -- provider.update ---------------------------------------------------------


def _invert_update_provider(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or not before.get("provider_id"):
        return None
    # Restore the prior config fields. api_key=None means "leave the key alone"
    # (secrets are never snapshotted, so they can't be reversed). PATCH semantics
    # mean a field that was originally None can't be reset to None by the inverse
    # — documented limitation; the common name/enabled/api_base(str) cases reverse
    # faithfully.
    return (
        "provider.update",
        {
            "provider_id": before["provider_id"],
            "name": before.get("name"),
            "api_base": before.get("api_base"),
            "enabled": before.get("enabled"),
            "api_key": None,
        },
    )


@action(
    "provider.update",
    ProviderUpdateParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_update_provider,
)
def _action_update_provider(
    db, params: ProviderUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    existing = app_db.get_provider(params.provider_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Provider not found: {params.provider_id}"
        )
    before = {
        "provider_id": existing.id,
        "name": existing.name,
        "api_base": existing.api_base,
        "enabled": existing.enabled,
    }
    update_req = ProviderUpdate(
        name=params.name,
        api_base=params.api_base,
        enabled=params.enabled,
        api_key=params.api_key,
    )
    provider = update_provider_impl(app_db, params.provider_id, update_req)
    after = {
        "provider_id": provider.id,
        "name": provider.name,
        "api_base": provider.api_base,
        "enabled": provider.enabled,
    }
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[provider.id],
        before=before,
        after=after,
        emit_type="provider.updated",
    )
    return _provider_public_dict(provider), spec


# -- provider.delete + provider.restore --------------------------------------


def _invert_delete_provider(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or not before.get("provider"):
        return None
    return (
        "provider.restore",
        {"provider": before["provider"], "models": before.get("models", [])},
    )


@action(
    "provider.delete",
    ProviderDeleteParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_delete_provider,
)
def _action_delete_provider(
    db, params: ProviderDeleteParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    existing = app_db.get_provider(params.provider_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Provider not found: {params.provider_id}"
        )
    # Snapshot the provider + its (cascade-deleted) models BEFORE deletion so the
    # inverse (provider.restore) can re-create the whole set. The keychain API key
    # is intentionally NOT snapshotted (secret) — restore brings back config, not
    # the key.
    models = app_db.list_models(params.provider_id)
    before = {
        "provider": existing.model_dump(mode="json"),
        "models": [m.model_dump(mode="json") for m in models],
    }
    delete_provider_impl(app_db, params.provider_id)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[params.provider_id],
        before=before,
        after={"provider_id": params.provider_id, "deleted": True},
        emit_type="provider.deleted",
    )
    return {"status": "deleted", "provider_id": params.provider_id}, spec


@action(
    "provider.restore",
    RestoreProviderParams,
    domains=["provider"],
    undoable=False,
)
def _action_restore_provider(
    db, params: RestoreProviderParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    provider = Provider.model_validate(params.provider)
    app_db.save_provider(provider)  # ON CONFLICT(id) -> restores the same row
    restored_models: list[str] = []
    for raw in params.models:
        model = Model.model_validate(raw)
        app_db.save_model(model)
        restored_models.append(model.id)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[provider.id],
        after={"provider_id": provider.id, "model_ids": restored_models},
        emit_type="provider.created",
    )
    return _provider_public_dict(provider), spec


# -- provider.remove_model + provider.restore_model --------------------------


def _invert_remove_model(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or not before.get("model"):
        return None
    return ("provider.restore_model", {"model": before["model"]})


@action(
    "provider.remove_model",
    RemoveModelParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_remove_model,
)
def _action_remove_model(
    db, params: RemoveModelParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    models = app_db.list_models(params.provider_id)
    model = next((m for m in models if m.id == params.model_id), None)
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"Model not found: {params.model_id}"
        )
    before = {"model": model.model_dump(mode="json")}
    remove_model_impl(app_db, params.provider_id, params.model_id)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[params.model_id],
        before=before,
        after={"model_id": params.model_id, "removed": True},
        emit_type="provider.model_removed",
    )
    return {"status": "deleted", "model_id": params.model_id}, spec


@action(
    "provider.restore_model",
    RestoreModelParams,
    domains=["provider"],
    undoable=False,
)
def _action_restore_model(
    db, params: RestoreModelParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    app_db = get_app_db()
    model = Model.model_validate(params.model)
    app_db.save_model(model)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[model.id],
        after={"model_id": model.id},
        emit_type="provider.model_added",
    )
    return {"model_id": model.id}, spec


# -- provider.update_ref (library ProviderRef) -------------------------------


def _invert_update_ref(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or not before.get("ref_id"):
        return None
    # enabled + sort_order are always captured (non-null), so this round-trips
    # exactly — unlike provider.update there's no null-reset gap here.
    return (
        "provider.update_ref",
        {
            "ref_id": before["ref_id"],
            "enabled": before.get("enabled"),
            "sort_order": before.get("sort_order"),
        },
    )


@action(
    "provider.update_ref",
    UpdateProviderRefParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_update_ref,
)
def _action_update_ref(
    db, params: UpdateProviderRefParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(ProviderRef, params.ref_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Provider reference not found: {params.ref_id}"
        )
    before = {
        "ref_id": existing.id,
        "enabled": existing.enabled,
        "sort_order": existing.sort_order,
    }
    req = ProviderRefUpdate(enabled=params.enabled, sort_order=params.sort_order)
    ref = update_provider_ref_impl(db, params.ref_id, req)
    after = {"ref_id": ref.id, "enabled": ref.enabled, "sort_order": ref.sort_order}
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[ref.id],
        before=before,
        after=after,
        emit_type="provider.ref_updated",
    )
    return ref.model_dump(mode="json"), spec


# -- provider.delete_ref + provider.restore_ref ------------------------------


def _invert_delete_ref(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or not before.get("ref"):
        return None
    return ("provider.restore_ref", {"ref": before["ref"]})


@action(
    "provider.delete_ref",
    DeleteProviderRefParams,
    domains=["provider"],
    undoable=True,
    invert=_invert_delete_ref,
)
def _action_delete_ref(
    db, params: DeleteProviderRefParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(ProviderRef, params.ref_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Provider reference not found: {params.ref_id}"
        )
    before = {"ref": existing.model_dump(mode="json")}
    delete_provider_ref_impl(db, params.ref_id)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[params.ref_id],
        before=before,
        after={"ref_id": params.ref_id, "deleted": True},
        emit_type="provider.ref_deleted",
    )
    return {"status": "deleted", "ref_id": params.ref_id}, spec


@action(
    "provider.restore_ref",
    RestoreProviderRefParams,
    domains=["provider"],
    undoable=False,
)
def _action_restore_ref(
    db, params: RestoreProviderRefParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    ref = ProviderRef.model_validate(params.ref)
    db.save(ref)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[ref.id],
        after={"ref_id": ref.id},
        emit_type="provider.ref_added",
    )
    return ref.model_dump(mode="json"), spec
