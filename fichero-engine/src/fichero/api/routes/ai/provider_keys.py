"""
Provider API key management and connection testing routes.

Included by providers.py via router.include_router().
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.routes.auth.accounts import _require_owner_or_bootstrap
from fichero.providers import get_provider_info
from fichero.security.keychain import (
    get_api_key,
    set_api_key,
    delete_api_key,
    has_api_key,
    is_available as keychain_available,
)
from fichero.provider_validation import (
    validate_provider_config,
    ProviderValidationError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class APIKeyStoredResponse(BaseModel):
    status: str  # "stored"


class APIKeyDeletedResponse(BaseModel):
    status: str  # "deleted"


class APIKeyStatusResponse(BaseModel):
    provider_type: str
    has_api_key: bool
    is_local: bool
    keychain_available: bool


# =============================================================================
# API Key Management
# =============================================================================


class APIKeyRequest(BaseModel):
    """Request body for setting API key."""

    api_key: str


def set_provider_api_key_impl(provider_type: str, api_key: str) -> None:
    """Validate + store an API key in the keychain.

    Extracted from the ``set_provider_api_key`` route so the route and the
    ``provider.set_api_key`` action share the exact same guards + keychain write
    (iterate-not-replace). Raises ``HTTPException`` exactly as the route did.
    """
    if not keychain_available():
        raise HTTPException(status_code=503, detail="Keychain not available")

    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(
            status_code=404, detail=f"Provider type not found: {provider_type}"
        )

    if info.is_local:
        raise HTTPException(
            status_code=400, detail="Local providers don't need API keys"
        )

    # Validate API key format before storing
    try:
        validate_provider_config(
            provider_type=provider_type,
            api_key=api_key,
        )
    except ProviderValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(f"Saving API key for {provider_type}")
    success = set_api_key(provider_type, api_key)
    if not success:
        logger.error(f"Failed to store API key for {provider_type}")
        raise HTTPException(status_code=500, detail="Failed to store API key")

    logger.info(f"Successfully stored API key for {provider_type}")


def delete_provider_api_key_impl(provider_type: str) -> None:
    """Delete an API key from the keychain.

    Extracted from the ``delete_provider_api_key`` route so route + the
    ``provider.delete_api_key`` action share the same guard + keychain delete.
    """
    if not keychain_available():
        raise HTTPException(status_code=503, detail="Keychain not available")

    delete_api_key(provider_type)


@router.post("/{provider_type}/api-key")
async def set_provider_api_key(
    provider_type: str,
    request: APIKeyRequest,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> APIKeyStoredResponse:
    """Store API key for a provider type in keychain."""
    set_provider_api_key_impl(provider_type, request.api_key)
    return APIKeyStoredResponse(status="stored")


@router.delete("/{provider_type}/api-key")
async def delete_provider_api_key(
    provider_type: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> APIKeyDeletedResponse:
    """Delete API key for a provider type from keychain."""
    delete_provider_api_key_impl(provider_type)
    return APIKeyDeletedResponse(status="deleted")


@router.get("/{provider_type}/api-key/status")
async def check_api_key_status(provider_type: str) -> APIKeyStatusResponse:
    """Check if API key exists for a provider type."""
    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(
            status_code=404, detail=f"Provider type not found: {provider_type}"
        )

    return APIKeyStatusResponse(
        provider_type=provider_type,
        has_api_key=has_api_key(provider_type) if not info.is_local else True,
        is_local=info.is_local,
        keychain_available=keychain_available(),
    )


# =============================================================================
# Connection Testing
# =============================================================================


class ConnectionTestResponse(BaseModel):
    """Result of a provider connection test."""

    success: bool
    provider_type: str
    message: str
    latency_ms: Optional[float] = None
    model_tested: Optional[str] = None


@router.post("/{provider_type}/test")
async def test_provider_connection(
    provider_type: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> ConnectionTestResponse:
    """
    Test connection to a provider.

    Makes a minimal API call to verify:
    - Network connectivity
    - API key validity (for cloud providers)
    - Server availability (for local providers)
    """
    import httpx  # lazy (#3985): keep off the engine boot path

    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(
            status_code=404, detail=f"Provider type not found: {provider_type}"
        )

    start_time = time.time()

    try:
        if provider_type == "apple_vision":
            return ConnectionTestResponse(
                success=True,
                provider_type=provider_type,
                message="Apple Vision Framework is available",
                latency_ms=0,
            )

        elif provider_type == "apple_intelligence":
            import platform

            version = platform.mac_ver()[0]
            major = int(version.split(".")[0]) if version else 0
            if major >= 15:
                return ConnectionTestResponse(
                    success=True,
                    provider_type=provider_type,
                    message=f"Apple Intelligence available (macOS {version})",
                    latency_ms=0,
                )
            else:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message=f"Apple Intelligence requires macOS 15+ (current: {version})",
                )

        elif provider_type == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:11434/api/tags", timeout=5.0
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("models", []))
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message=f"Ollama running with {model_count} models",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"Ollama returned status {response.status_code}",
                        latency_ms=latency,
                    )

        elif provider_type == "lmstudio":
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:1234/v1/models", timeout=5.0
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("data", []))
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message=f"LM Studio running with {model_count} models loaded",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"LM Studio returned status {response.status_code}",
                        latency_ms=latency,
                    )

        elif provider_type == "openai":
            api_key = get_api_key("openai")
            if not api_key:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message="OpenAI API connected",
                        latency_ms=latency,
                    )
                elif response.status_code == 401:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message="Invalid API key",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"API returned status {response.status_code}",
                        latency_ms=latency,
                    )

        elif provider_type == "anthropic":
            api_key = get_api_key("anthropic")
            if not api_key:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )
            if api_key.startswith("sk-ant-"):
                latency = (time.time() - start_time) * 1000
                return ConnectionTestResponse(
                    success=True,
                    provider_type=provider_type,
                    message="API key configured (format valid)",
                    latency_ms=latency,
                )
            else:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="API key format appears invalid",
                )

        elif provider_type == "huggingface":
            api_key = get_api_key("huggingface")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://huggingface.co/api/whoami-v2",
                    headers=headers,
                    timeout=10.0,
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    data = response.json()
                    username = data.get("name", "anonymous")
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message=f"Connected as {username}",
                        latency_ms=latency,
                    )
                elif response.status_code == 401:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message="Invalid API key",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"API returned status {response.status_code}",
                        latency_ms=latency,
                    )

        elif provider_type == "google":
            api_key = get_api_key("google")
            if not api_key:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1/models?key={api_key}",
                    timeout=10.0,
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("models", []))
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message=f"Google AI connected ({model_count} models)",
                        latency_ms=latency,
                    )
                elif response.status_code == 400:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message="Invalid API key",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"API returned status {response.status_code}",
                        latency_ms=latency,
                    )

        elif provider_type == "groq":
            api_key = get_api_key("groq")
            if not api_key:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                latency = (time.time() - start_time) * 1000
                if response.status_code == 200:
                    return ConnectionTestResponse(
                        success=True,
                        provider_type=provider_type,
                        message="Groq API connected",
                        latency_ms=latency,
                    )
                elif response.status_code == 401:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message="Invalid API key",
                        latency_ms=latency,
                    )
                else:
                    return ConnectionTestResponse(
                        success=False,
                        provider_type=provider_type,
                        message=f"API returned status {response.status_code}",
                        latency_ms=latency,
                    )

        else:
            api_key = get_api_key(provider_type)
            if api_key or info.is_local:
                return ConnectionTestResponse(
                    success=True,
                    provider_type=provider_type,
                    message="Configuration valid (connection not tested)",
                    latency_ms=(time.time() - start_time) * 1000,
                )
            else:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )

    except httpx.ConnectError:
        return ConnectionTestResponse(
            success=False,
            provider_type=provider_type,
            message="Connection failed - server not reachable",
            latency_ms=(time.time() - start_time) * 1000,
        )
    except httpx.TimeoutException:
        return ConnectionTestResponse(
            success=False,
            provider_type=provider_type,
            message="Connection timed out",
            latency_ms=(time.time() - start_time) * 1000,
        )
    except Exception as e:
        logger.error(f"Connection test failed for {provider_type}: {e}")
        return ConnectionTestResponse(
            success=False,
            provider_type=provider_type,
            message=f"Error: {str(e)}",
            latency_ms=(time.time() - start_time) * 1000,
        )


# =============================================================================
# Action layer registration (EPIC #1848 / sweep #2014) — PROVIDER api-key ops
# =============================================================================
#
# API-key ops are NON-undoable by design (undoable=False): the keychain stores a
# secret we never snapshot, so there is no before/after to reverse to. Critically,
# ``registry.invoke`` dumps ``params.model_dump()`` into the ActionAudit row, so
# the key field is ``Field(exclude=True)`` — present as an attribute inside
# ``execute`` but NEVER serialized into the audit (no plaintext secret at rest).

from pydantic import Field  # noqa: E402

from fichero.actions.registry import action, ActionContext, ChangeSpec  # noqa: E402


class SetApiKeyParams(BaseModel):
    """provider.set_api_key params. ``api_key`` is secret → excluded from audit."""

    provider_type: str
    api_key: str = Field(exclude=True)


class DeleteApiKeyParams(BaseModel):
    provider_type: str


@action(
    "provider.set_api_key",
    SetApiKeyParams,
    domains=["provider"],
    undoable=False,
)
def _action_set_api_key(
    db, params: SetApiKeyParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    set_provider_api_key_impl(params.provider_type, params.api_key)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[params.provider_type],
        # No secret in before/after — only the fact that a key now exists.
        after={"provider_type": params.provider_type, "has_api_key": True},
        emit_type="provider.api_key_set",
    )
    return {"status": "stored", "provider_type": params.provider_type}, spec


@action(
    "provider.delete_api_key",
    DeleteApiKeyParams,
    domains=["provider"],
    undoable=False,
)
def _action_delete_api_key(
    db, params: DeleteApiKeyParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    delete_provider_api_key_impl(params.provider_type)
    spec = ChangeSpec(
        domains=["provider"],
        target_ids=[params.provider_type],
        after={"provider_type": params.provider_type, "has_api_key": False},
        emit_type="provider.api_key_deleted",
    )
    return {"status": "deleted", "provider_type": params.provider_type}, spec
