"""
Settings API Routes

Endpoints for managing app-wide settings like default AI models.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from fichero.api.routes.auth_accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
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
    from fichero.providers import get_provider_info

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


@router.get("/ai-defaults", response_model=AIDefaults)
def get_ai_defaults(request: Request) -> AIDefaults:
    """Get default AI models for each category."""
    _require_authenticated_or_bootstrap(request)

    from fichero.app_db import get_app_db

    db = get_app_db()
    defaults = db.get_ai_defaults()
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
    )


@router.put("/ai-defaults", response_model=StatusOkResponse)
def set_ai_defaults(
    body: AIDefaultsUpdate,
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Set default AI models for each category."""
    from fichero.app_db import get_app_db

    _validate_provider_updates(body)

    db = get_app_db()
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
    from fichero.app_db import get_app_db

    db = get_app_db()
    apple = "apple"
    seeds = {
        "default_small_provider": apple, "default_small_model": "apple-intelligence",
        "default_medium_provider": "openrouter", "default_medium_model": "openai/gpt-4o-mini",
        "default_large_provider": apple, "default_large_model": "apple-intelligence",
        "default_vision_small_provider": apple, "default_vision_small_model": "apple-vision",
        "default_vision_medium_provider": apple, "default_vision_medium_model": "apple-vision",
        "default_vision_large_provider": apple, "default_vision_large_model": "apple-vision",
        "default_text_provider": apple, "default_text_model": "apple-intelligence",
        "default_vision_provider": apple, "default_vision_model": "apple-vision",
        "default_audio_provider": apple, "default_audio_model": "apple-speech",
    }
    for key, value in seeds.items():
        if not db.get_setting(key):
            db.set_setting(key, value)
    return StatusOkResponse(status="ok")


@router.delete("/ai-defaults")
def reset_ai_defaults(
    request: Request,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> StatusOkResponse:
    """Reset all AI default settings to empty."""
    from fichero.app_db import get_app_db

    db = get_app_db()
    db.reset_ai_defaults()
    return StatusOkResponse(status="ok")
