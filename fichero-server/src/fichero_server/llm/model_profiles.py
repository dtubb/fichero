"""Typed AI model/provider profile contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _new_id() -> str:
    return uuid.uuid4().hex


class ModelProfileRole(str, Enum):
    """Intended use/capability for a named model profile."""

    general = "general"
    text = "text"
    vision = "vision"
    audio = "audio"
    video = "video"
    embeddings = "embeddings"


class ModelProfilePrivacy(str, Enum):
    """Privacy policy attached to a named model profile."""

    standard = "standard"
    local_only = "local_only"
    private = "private"


class ModelProfileParams(BaseModel):
    """LLM parameters supported by the current LLMConfig surface."""

    temperature: float | None = None
    max_tokens: int | None = None
    timeout: int | None = None
    reasoning_effort: str | None = None


class ModelProfile(BaseModel):
    """Named bundle of provider/model/params/privacy for workflow resolution."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_id)
    name: str
    provider: str
    model: str
    role: ModelProfileRole = ModelProfileRole.text
    params: ModelProfileParams = Field(default_factory=ModelProfileParams)
    privacy: ModelProfilePrivacy = ModelProfilePrivacy.standard
    local_only: bool = False
    api_base: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("id", "name", "provider", "model", mode="before")
    @classmethod
    def _strip_required_strings(cls, value: Any) -> str:
        return str(value or "").strip()

    @property
    def requires_local_provider(self) -> bool:
        return self.local_only or self.privacy in {
            ModelProfilePrivacy.local_only,
            ModelProfilePrivacy.private,
        }


class ModelProfileCreate(BaseModel):
    """Request to create a named model profile."""

    id: str | None = None
    name: str
    provider: str
    model: str
    role: ModelProfileRole = ModelProfileRole.text
    params: ModelProfileParams = Field(default_factory=ModelProfileParams)
    privacy: ModelProfilePrivacy = ModelProfilePrivacy.standard
    local_only: bool = False
    api_base: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_profile(self) -> ModelProfile:
        data = self.model_dump(exclude_none=True)
        return ModelProfile(**data)


class ModelProfileUpdate(BaseModel):
    """Partial update for a named model profile."""

    name: str | None = None
    provider: str | None = None
    model: str | None = None
    role: ModelProfileRole | None = None
    params: ModelProfileParams | None = None
    privacy: ModelProfilePrivacy | None = None
    local_only: bool | None = None
    api_base: str | None = None
    extra: dict[str, Any] | None = None


class ModelProfileListResponse(BaseModel):
    """Envelope for model profile list endpoints."""

    items: list[ModelProfile]


class ModelProfilePrivacyError(RuntimeError):
    """Raised when a local/private profile points at a cloud provider."""

    def __init__(self, profile: ModelProfile):
        self.profile = profile
        super().__init__(
            f"Model profile '{profile.name}' is {profile.privacy.value}"
            f"{' and local_only' if profile.local_only else ''}; refusing "
            f"cloud provider {profile.provider}/{profile.model}."
        )


class ModelProfileNotFoundError(RuntimeError):
    """Raised when a profile reference cannot be found."""

    def __init__(self, profile_ref: str):
        self.profile_ref = profile_ref
        super().__init__(f"Model profile not found: {profile_ref}")


def provider_is_local_or_builtin(provider: str) -> bool:
    """Return whether a provider is local/on-device/builtin."""
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info((provider or "").strip().lower())
    return bool(info and (info.is_local or info.is_builtin))


def enforce_model_profile_privacy(profile: ModelProfile) -> None:
    """Reject private/local-only profiles that would execute in the cloud."""
    if profile.requires_local_provider and not provider_is_local_or_builtin(
        profile.provider
    ):
        raise ModelProfilePrivacyError(profile)


def llm_config_from_profile(profile: ModelProfile, base_config: Any | None = None) -> Any:
    """Build an LLMConfig from a profile, preserving base params as fallback."""
    from fichero_server.llm import LLMConfig

    base = base_config or LLMConfig(provider="", model="")
    params = profile.params
    return LLMConfig(
        provider=profile.provider,
        model=profile.model,
        temperature=(
            params.temperature
            if params.temperature is not None
            else getattr(base, "temperature", 0.7)
        ),
        max_tokens=(
            params.max_tokens
            if params.max_tokens is not None
            else getattr(base, "max_tokens", 2048)
        ),
        api_key=getattr(base, "api_key", None),
        api_base=profile.api_base or getattr(base, "api_base", None),
        timeout=(
            params.timeout
            if params.timeout is not None
            else getattr(base, "timeout", 60)
        ),
        extra={**getattr(base, "extra", {}), **profile.extra},
        reasoning_effort=(
            params.reasoning_effort
            if params.reasoning_effort is not None
            else getattr(base, "reasoning_effort", None)
        ),
    )
