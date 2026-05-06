"""
Settings API Routes

Endpoints for managing app-wide settings like default AI models.
"""

from fastapi import APIRouter
from pydantic import BaseModel

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
    # $small / $large model aliases so presets stay portable across users
    # with different configured providers (#810).
    small_provider: str = ""
    small_model: str = ""
    large_provider: str = ""
    large_model: str = ""
    # Advanced
    temperature: str = ""
    max_tokens: str = ""
    prompt_prefix: str = ""


@router.get("/ai-defaults", response_model=AIDefaults)
def get_ai_defaults() -> AIDefaults:
    """Get default AI models for each category."""
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
        large_provider=defaults.get("default_large_provider", ""),
        large_model=defaults.get("default_large_model", ""),
        temperature=defaults.get("default_temperature", ""),
        max_tokens=defaults.get("default_max_tokens", ""),
        prompt_prefix=defaults.get("default_prompt_prefix", ""),
    )


@router.put("/ai-defaults")
def set_ai_defaults(body: AIDefaults) -> StatusOkResponse:
    """Set default AI models for each category."""
    from fichero.app_db import get_app_db

    db = get_app_db()
    mapping = {
        "default_vision_provider": body.vision_provider,
        "default_vision_model": body.vision_model,
        "default_text_provider": body.text_provider,
        "default_text_model": body.text_model,
        "default_audio_provider": body.audio_provider,
        "default_audio_model": body.audio_model,
        "default_video_provider": body.video_provider,
        "default_video_model": body.video_model,
        "default_embeddings_provider": body.embeddings_provider,
        "default_embeddings_model": body.embeddings_model,
        "default_small_provider": body.small_provider,
        "default_small_model": body.small_model,
        "default_large_provider": body.large_provider,
        "default_large_model": body.large_model,
        "default_temperature": body.temperature,
        "default_max_tokens": body.max_tokens,
        "default_prompt_prefix": body.prompt_prefix,
    }
    for key, value in mapping.items():
        if value:
            db.set_setting(key, value)
        else:
            db.delete_setting(key)
    return StatusOkResponse(status="ok")


@router.delete("/ai-defaults")
def reset_ai_defaults() -> StatusOkResponse:
    """Reset all AI default settings to empty."""
    from fichero.app_db import get_app_db

    db = get_app_db()
    db.reset_ai_defaults()
    return StatusOkResponse(status="ok")
