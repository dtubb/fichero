"""
Settings API Routes

Endpoints for managing app-wide settings like default AI models.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Literal, Optional

from pydantic import BaseModel, Field

from fichero_server.api.routes.auth.accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
)
from fichero_server.knowledge.wikidata_enrich import DEFAULT_WIKIDATA_SPARQL_ENDPOINT
from fichero_server.llm.model_profiles import (
    ModelProfile,
    ModelProfileCreate,
    ModelProfileListResponse,
    ModelProfilePrivacyError,
    ModelProfileUpdate,
    enforce_model_profile_privacy,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class StatusOkResponse(BaseModel):
    status: str


class AIDefaults(BaseModel):
    """Default AI model configuration per category."""

    vision_provider: str = ""
    vision_model: str = ""
    text_provider: str = ""
    text_model: str = ""
    audio_provider: str = ""
    audio_model: str = ""
    video_provider: str = ""
    video_model: str = ""
    embeddings_provider: str = ""
    embeddings_model: str = ""
    # Capability-tier defaults — referenced by workflow nodes via the
    # $small / $medium / $large model aliases so presets stay portable across users
    # with different configured providers (#810).
    small_provider: str = ""
    small_model: str = ""
    medium_provider: str = ""
    medium_model: str = ""
    large_provider: str = ""
    large_model: str = ""
    # Vision capability-tier defaults — referenced by workflow nodes via the
    # $vision_small / $vision_medium / $vision_large aliases (#2200).
    vision_small_provider: str = ""
    vision_small_model: str = ""
    vision_medium_provider: str = ""
    vision_medium_model: str = ""
    vision_large_provider: str = ""
    vision_large_model: str = ""
    primary_language: str = ""
    # Advanced
    temperature: str = ""
    max_tokens: str = ""
    prompt_prefix: str = ""
    #: The model this Mac's local model server loads when a step names none (#5520). Settings'
    #: choice when set; otherwise the vision model chosen for this Mac from what it runs and has
    #: installed. A step that names its own local model is always served that one instead.
    local_model: str = ""
    #: Why each default holds the value it does, keyed by field name (`local_model`,
    #: `text_provider`, ...): chosen in Settings, or chosen for this Mac and build, and why.
    chosen_because: dict[str, str] = Field(default_factory=dict)


class AIDefaultsUpdate(BaseModel):
    """Partial update for default AI model configuration."""

    vision_provider: str | None = None
    vision_model: str | None = None
    text_provider: str | None = None
    text_model: str | None = None
    audio_provider: str | None = None
    audio_model: str | None = None
    video_provider: str | None = None
    video_model: str | None = None
    embeddings_provider: str | None = None
    embeddings_model: str | None = None
    small_provider: str | None = None
    small_model: str | None = None
    medium_provider: str | None = None
    medium_model: str | None = None
    large_provider: str | None = None
    large_model: str | None = None
    vision_small_provider: str | None = None
    vision_small_model: str | None = None
    vision_medium_provider: str | None = None
    vision_medium_model: str | None = None
    vision_large_provider: str | None = None
    vision_large_model: str | None = None
    primary_language: str | None = None
    temperature: str | None = None
    max_tokens: str | None = None
    prompt_prefix: str | None = None
    #: Settings › AI's local model; "" returns it to the model chosen for this Mac. Refused (422)
    #: when it is not a local catalogue model or this Mac cannot run it.
    local_model: str | None = None


_AI_DEFAULT_FIELDS: tuple[tuple[str, str], ...] = (
    ("vision_provider", "default_vision_provider"),
    ("vision_model", "default_vision_model"),
    ("text_provider", "default_text_provider"),
    ("text_model", "default_text_model"),
    ("audio_provider", "default_audio_provider"),
    ("audio_model", "default_audio_model"),
    ("video_provider", "default_video_provider"),
    ("video_model", "default_video_model"),
    ("embeddings_provider", "default_embeddings_provider"),
    ("embeddings_model", "default_embeddings_model"),
    ("small_provider", "default_small_provider"),
    ("small_model", "default_small_model"),
    ("medium_provider", "default_medium_provider"),
    ("medium_model", "default_medium_model"),
    ("large_provider", "default_large_provider"),
    ("large_model", "default_large_model"),
    ("vision_small_provider", "default_vision_small_provider"),
    ("vision_small_model", "default_vision_small_model"),
    ("vision_medium_provider", "default_vision_medium_provider"),
    ("vision_medium_model", "default_vision_medium_model"),
    ("vision_large_provider", "default_vision_large_provider"),
    ("vision_large_model", "default_vision_large_model"),
    ("primary_language", "default_primary_language"),
    ("temperature", "default_temperature"),
    ("max_tokens", "default_max_tokens"),
    ("prompt_prefix", "default_prompt_prefix"),
    ("local_model", "default_local_model"),
)

_TIER_SETTING_KEYS = {
    "default_small_provider", "default_small_model",
    "default_medium_provider", "default_medium_model",
    "default_large_provider", "default_large_model",
    "default_vision_small_provider", "default_vision_small_model",
    "default_vision_medium_provider", "default_vision_medium_model",
    "default_vision_large_provider", "default_vision_large_model",
}


def _validate_provider_updates(body: AIDefaultsUpdate) -> None:
    from fichero_server.llm.providers import get_provider_info

    for field_name in body.model_fields_set:
        if not field_name.endswith("_provider"):
            continue
        value = getattr(body, field_name)
        if value in (None, ""):
            continue
        if get_provider_info(value) is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown AI default provider for {field_name}: {value}",
            )


def _validate_local_model(name: str) -> str:
    """Settings' local model must be one this Mac's local server can run (#5520): a catalogue or
    trained model whose card fits this Mac's memory. It need not be installed yet: a run then says
    to install it. Returns the catalogue id, whether it was named by that or by its Hub repo."""
    from fichero_server.llm.local_model_choice import local_model_problem
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    problem = local_model_problem(name, "vision")
    if problem is not None and problem.kind != "not-installed":
        raise HTTPException(status_code=422, detail=f"Local model refused: {problem}")
    return get_mlx_model_store().canonical_id(name) or name


def _validate_profile(profile: ModelProfile) -> None:
    from fichero_server.llm.providers import get_provider_info

    if not profile.name:
        raise HTTPException(status_code=422, detail="Model profile name is required")
    if not profile.provider:
        raise HTTPException(status_code=422, detail="Model profile provider is required")
    if not profile.model:
        raise HTTPException(status_code=422, detail="Model profile model is required")
    if get_provider_info(profile.provider) is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown model profile provider: {profile.provider}",
        )
    try:
        enforce_model_profile_privacy(profile)
    except ModelProfilePrivacyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_profile_or_404(db, profile_id: str) -> ModelProfile:
    profile = db.get_model_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return profile


@router.get("/model-profiles", response_model=ModelProfileListResponse)
def list_model_profiles(request: Request) -> ModelProfileListResponse:
    """List named AI model/provider profiles."""
    _require_authenticated_or_bootstrap(request)

    from fichero_server.db.app import get_app_db

    return ModelProfileListResponse(items=get_app_db().list_model_profiles())


@router.post("/model-profiles", response_model=ModelProfile, status_code=201)
def create_model_profile(
    body: ModelProfileCreate,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> ModelProfile:
    """Create a named AI model/provider profile."""
    from duckdb import ConstraintException
    from fichero_server.db.app import get_app_db

    profile = body.to_profile()
    _validate_profile(profile)
    try:
        return get_app_db().save_model_profile(profile)
    except ConstraintException as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Model profile already exists: {profile.name}",
        ) from exc


@router.get("/model-profiles/{profile_id}", response_model=ModelProfile)
def get_model_profile(profile_id: str, request: Request) -> ModelProfile:
    """Get a named AI model/provider profile."""
    _require_authenticated_or_bootstrap(request)

    from fichero_server.db.app import get_app_db

    return _get_profile_or_404(get_app_db(), profile_id)


@router.put("/model-profiles/{profile_id}", response_model=ModelProfile)
def update_model_profile(
    profile_id: str,
    body: ModelProfileUpdate,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> ModelProfile:
    """Update a named AI model/provider profile."""
    from duckdb import ConstraintException
    from fichero_server.db.app import get_app_db

    db = get_app_db()
    current = _get_profile_or_404(db, profile_id)
    updates = {
        field_name: getattr(body, field_name)
        for field_name in body.model_fields_set
        if getattr(body, field_name) is not None
    }
    profile = current.model_copy(update=updates)
    _validate_profile(profile)
    try:
        return db.save_model_profile(profile)
    except ConstraintException as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Model profile already exists: {profile.name}",
        ) from exc


@router.delete("/model-profiles/{profile_id}", response_model=StatusOkResponse)
def delete_model_profile(
    profile_id: str,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Delete a named AI model/provider profile."""
    from fichero_server.db.app import get_app_db

    deleted = get_app_db().delete_model_profile(profile_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return StatusOkResponse(status="ok")


@router.get("/ai-defaults", response_model=AIDefaults)
def get_ai_defaults(request: Request) -> AIDefaults:
    """Get default AI models for each category."""
    _require_authenticated_or_bootstrap(request)

    from fichero_server.db.app import get_app_db

    from fichero_server.llm.local_model_choice import default_local_model

    db = get_app_db()
    defaults = db.get_ai_defaults()
    local = default_local_model()
    chosen_because = _chosen_because(db, defaults, local)
    return AIDefaults(
        vision_provider=defaults.get("default_vision_provider", ""),
        vision_model=defaults.get("default_vision_model", ""),
        text_provider=defaults.get("default_text_provider", ""),
        text_model=defaults.get("default_text_model", ""),
        audio_provider=defaults.get("default_audio_provider", ""),
        audio_model=defaults.get("default_audio_model", ""),
        video_provider=defaults.get("default_video_provider", ""),
        video_model=defaults.get("default_video_model", ""),
        embeddings_provider=defaults.get("default_embeddings_provider", ""),
        embeddings_model=defaults.get("default_embeddings_model", ""),
        small_provider=defaults.get("default_small_provider", ""),
        small_model=defaults.get("default_small_model", ""),
        medium_provider=defaults.get("default_medium_provider", ""),
        medium_model=defaults.get("default_medium_model", ""),
        large_provider=defaults.get("default_large_provider", ""),
        large_model=defaults.get("default_large_model", ""),
        vision_small_provider=defaults.get("default_vision_small_provider", ""),
        vision_small_model=defaults.get("default_vision_small_model", ""),
        vision_medium_provider=defaults.get("default_vision_medium_provider", ""),
        vision_medium_model=defaults.get("default_vision_medium_model", ""),
        vision_large_provider=defaults.get("default_vision_large_provider", ""),
        vision_large_model=defaults.get("default_vision_large_model", ""),
        primary_language=defaults.get("default_primary_language", ""),
        temperature=defaults.get("default_temperature", ""),
        max_tokens=defaults.get("default_max_tokens", ""),
        prompt_prefix=defaults.get("default_prompt_prefix", ""),
        local_model=local.model_id or "",
        chosen_because=chosen_because,
    )


def _chosen_because(db, defaults: dict[str, str], local) -> dict[str, str]:
    """Why each default is what it is, by field name: the seed's recorded reasons, for values
    the seed still holds, and the local model's reason."""
    from fichero_server.llm.local_model_choice import read_chosen_because

    out = {}
    recorded = read_chosen_because(db)
    for field_name, key in _AI_DEFAULT_FIELDS:
        why = recorded.get(key)
        if why and defaults.get(key):
            out[field_name] = why
    out["local_model"] = local.reason
    return out


@router.put("/ai-defaults", response_model=StatusOkResponse)
def set_ai_defaults(
    body: AIDefaultsUpdate,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Set default AI models for each category."""
    from fichero_server.db.app import get_app_db

    _validate_provider_updates(body)
    if body.local_model:
        body.local_model = _validate_local_model(body.local_model)

    from fichero_server.llm.local_model_choice import read_chosen_because, record_chosen_because

    db = get_app_db()
    changed: set[str] = set()
    # Tier-alias keys ($small/$medium/$large and vision variants) must never be
    # deleted mid-session — workflows silently lose their fallback target
    # (#1057, #2200). Skip empty values for these; explicit reset goes through
    # DELETE /ai-defaults.
    for field_name, key in _AI_DEFAULT_FIELDS:
        if field_name not in body.model_fields_set:
            continue
        value = getattr(body, field_name)
        if value is None:
            continue
        if value:
            db.set_setting(key, value)
        elif key not in _TIER_SETTING_KEYS:
            db.delete_setting(key)
        changed.add(key.removesuffix("_provider").removesuffix("_model"))
    # A value the person chose is no longer the seed's: the seed's reason for it goes too.
    recorded = read_chosen_because(db)
    kept = {k: v for k, v in recorded.items()
            if k.removesuffix("_provider").removesuffix("_model") not in changed}
    if kept != recorded:
        record_chosen_because(db, kept)
    return StatusOkResponse(status="ok")


@router.post("/ai-defaults/repair")
def repair_ai_defaults(
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Re-seed any missing tier-alias defaults to factory models.

    Safe to call on an existing library — only fills gaps, never overwrites
    values the user has already set. Fixes libraries created before the
    factory-defaults seed was added (#1057).
    """
    from fichero_server.api.main import _ensure_default_ai_defaults
    from fichero_server.db.app import get_app_db

    # The same seed as first launch (#5520): this Mac's and this build's defaults, gaps only.
    _ensure_default_ai_defaults(get_app_db(), "")
    return StatusOkResponse(status="ok")


@router.delete("/ai-defaults")
def reset_ai_defaults(
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Reset all AI default settings to empty."""
    from fichero_server.db.app import get_app_db

    db = get_app_db()
    db.reset_ai_defaults()
    return StatusOkResponse(status="ok")


# ---------------------------------------------------------------------------
# SPARQL endpoints — the knowledge-authority endpoints the Wikidata enrichment
# (Enrich from Wikidata) queries. App-wide (get_app_db setting), like the AI
# defaults above: one default (Wikidata) plus any user-added custom endpoints.
# ---------------------------------------------------------------------------

_SPARQL_ENDPOINTS_SETTING_KEY = "sparql_endpoints"
_WIKIDATA_ENDPOINT_NAME = "Wikidata"


class SparqlEndpoint(BaseModel):
    """One named SPARQL endpoint the enrichment can query."""

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)


class SparqlEndpointsConfig(BaseModel):
    """The full SPARQL-endpoints configuration persisted app-wide."""

    endpoints: list[SparqlEndpoint] = Field(default_factory=list)
    selected_url: str = Field(
        default=DEFAULT_WIKIDATA_SPARQL_ENDPOINT,
        description="URL of the endpoint the enrichment uses by default.",
    )


def _default_sparql_config() -> SparqlEndpointsConfig:
    return SparqlEndpointsConfig(
        endpoints=[
            SparqlEndpoint(name=_WIKIDATA_ENDPOINT_NAME, url=DEFAULT_WIKIDATA_SPARQL_ENDPOINT)
        ],
        selected_url=DEFAULT_WIKIDATA_SPARQL_ENDPOINT,
    )


def load_sparql_endpoints(db) -> SparqlEndpointsConfig:
    """Read the persisted config, falling back to the Wikidata default.

    Shared with the enrichment route so both read the SAME source of truth.
    A malformed stored value is treated as unset (never a silent half-config).
    """
    raw = db.get_setting(_SPARQL_ENDPOINTS_SETTING_KEY)
    if not raw:
        return _default_sparql_config()
    try:
        return SparqlEndpointsConfig.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError):
        return _default_sparql_config()


def resolve_selected_endpoint(db) -> str:
    """The endpoint URL the enrichment should query. Never empty."""
    config = load_sparql_endpoints(db)
    if config.selected_url:
        return config.selected_url
    if config.endpoints:
        return config.endpoints[0].url
    return DEFAULT_WIKIDATA_SPARQL_ENDPOINT


@router.get("/sparql-endpoints", response_model=SparqlEndpointsConfig)
def get_sparql_endpoints(request: Request) -> SparqlEndpointsConfig:
    """Read the configured SPARQL endpoints + which one is selected."""
    _require_authenticated_or_bootstrap(request)

    from fichero_server.db.app import get_app_db

    return load_sparql_endpoints(get_app_db())


@router.put("/sparql-endpoints", response_model=SparqlEndpointsConfig)
def set_sparql_endpoints(
    body: SparqlEndpointsConfig,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> SparqlEndpointsConfig:
    """Persist the SPARQL endpoints. The Wikidata default is always kept.

    Keeping the default present means the enrichment can never be left with no
    endpoint to query — a user can add/select custom endpoints, not delete the
    ground truth out from under the feature.
    """
    endpoints = [SparqlEndpoint(name=e.name.strip(), url=e.url.strip()) for e in body.endpoints]
    endpoints = [e for e in endpoints if e.name and e.url]
    if not any(e.url == DEFAULT_WIKIDATA_SPARQL_ENDPOINT for e in endpoints):
        endpoints.insert(
            0, SparqlEndpoint(name=_WIKIDATA_ENDPOINT_NAME, url=DEFAULT_WIKIDATA_SPARQL_ENDPOINT)
        )
    known_urls = {e.url for e in endpoints}
    selected = body.selected_url.strip() if body.selected_url.strip() in known_urls else DEFAULT_WIKIDATA_SPARQL_ENDPOINT
    config = SparqlEndpointsConfig(endpoints=endpoints, selected_url=selected)

    from fichero_server.db.app import get_app_db

    get_app_db().set_setting(_SPARQL_ENDPOINTS_SETTING_KEY, config.model_dump_json())
    return config


# =============================================================================
# Compute preferences: how hard local model work may push this Mac, and where.
# =============================================================================


class ComputePreferences(BaseModel):
    """`priority`: balanced (default; the Mac stays usable), fast (no throttle, every core), or
    background (yields to everything). `device`: auto (Apple's GPU when available), cpu or gpu.
    `effective` is what applies now: an environment override (FICHERO_COMPUTE_PRIORITY /
    FICHERO_COMPUTE_DEVICE, for test runs) wins over the saved choice."""

    priority: Literal["fast", "balanced", "background"] = "balanced"
    device: Literal["auto", "cpu", "gpu"] = "auto"
    effective: Optional[dict[str, str]] = None


@router.get("/compute", response_model=ComputePreferences)
def get_compute_preferences(request: Request) -> ComputePreferences:
    """The saved compute preferences and what applies now."""
    _require_authenticated_or_bootstrap(request)
    from fichero_server.core.compute_preferences import compute_preferences, stored_preferences

    return ComputePreferences(**stored_preferences(), effective=compute_preferences())


@router.put("/compute", response_model=ComputePreferences)
def set_compute_preferences(
    body: ComputePreferences,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> ComputePreferences:
    """Save the compute preferences (owner only). Local model work reads them on its next page."""
    from fichero_server.core.compute_preferences import compute_preferences, save_preferences

    saved = save_preferences(body.priority, body.device)
    return ComputePreferences(**saved, effective=compute_preferences())
