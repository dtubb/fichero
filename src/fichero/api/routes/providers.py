"""
Provider Routes

API endpoints for managing LLM providers and models.
"""

import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fichero.db import db
from fichero.models import Provider as ProviderModel, Model as ModelModel, ProviderType
from fichero.providers import PROVIDERS, get_provider_info, list_providers as list_catalog_providers
from fichero.keychain import get_api_key, set_api_key, delete_api_key, has_api_key, is_available as keychain_available

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Description Generator (from capabilities - no custom marketing text)
# =============================================================================

def generate_model_description(model_data: dict) -> str:
    """Generate a factual description from model capabilities.

    This creates descriptions based on what the model actually does,
    derived from LiteLLM's capability flags and pricing data.
    """
    parts = []

    # Context window
    max_input = model_data.get("max_input_tokens")
    if max_input:
        if max_input >= 1_000_000:
            parts.append(f"{max_input // 1_000_000}M token context")
        elif max_input >= 100_000:
            parts.append(f"{max_input // 1_000}K token context")

    # Key capabilities
    caps = []
    if model_data.get("supports_vision"):
        caps.append("vision")
    if model_data.get("supports_reasoning"):
        caps.append("reasoning")
    if model_data.get("supports_function_calling"):
        caps.append("tool use")
    if model_data.get("supports_audio_input"):
        caps.append("audio")
    if model_data.get("supports_pdf_input"):
        caps.append("PDF")
    if model_data.get("supports_web_search"):
        caps.append("web search")
    if model_data.get("supports_batch_api"):
        caps.append("batch API")

    if caps:
        parts.append(", ".join(caps))

    # Pricing - just indicate free for local models, no judgments on cost
    input_cost = model_data.get("input_cost_per_million", 0)
    if input_cost == 0:
        parts.append("free")

    if not parts:
        return None

    # Capitalize first letter
    desc = ", ".join(parts)
    return desc[0].upper() + desc[1:] if desc else None


# =============================================================================
# Curated Model Lists (recommended models for major providers)
# =============================================================================

# Curated list of recommended models per provider.
# These are just model IDs and is_recommended flags.
# All other info (description, pricing, capabilities) comes from LiteLLM.
RECOMMENDED_MODELS: dict[str, list[dict]] = {
    "openai": [
        {"model_id": "gpt-4.1", "is_recommended": True},
        {"model_id": "gpt-4.1-mini", "is_recommended": True},
        {"model_id": "gpt-4.1-nano", "is_recommended": True},
        {"model_id": "gpt-4o", "is_recommended": True},
        {"model_id": "gpt-4o-mini", "is_recommended": True},
        {"model_id": "o3-mini", "is_recommended": True},
        {"model_id": "o1"},
        {"model_id": "o1-mini"},
        {"model_id": "gpt-4-turbo"},
        {"model_id": "gpt-3.5-turbo"},
    ],
    "anthropic": [
        {"model_id": "claude-3-5-sonnet-latest", "is_recommended": True},
        {"model_id": "claude-3-5-haiku-latest", "is_recommended": True},
        {"model_id": "claude-3-opus-latest"},
        {"model_id": "claude-3-sonnet-20240229"},
        {"model_id": "claude-3-haiku-20240307"},
    ],
    "google": [
        {"model_id": "gemini-2.0-flash-exp", "is_recommended": True},
        {"model_id": "gemini-1.5-pro", "is_recommended": True},
        {"model_id": "gemini-1.5-flash"},
        {"model_id": "gemini-1.0-pro"},
    ],
    "groq": [
        {"model_id": "llama-3.3-70b-versatile", "is_recommended": True},
        {"model_id": "llama-3.1-70b-versatile"},
        {"model_id": "llama-3.1-8b-instant"},
        {"model_id": "mixtral-8x7b-32768"},
        {"model_id": "llama-3.2-90b-vision-preview"},
    ],
    "together": [
        {"model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "is_recommended": True},
        {"model_id": "meta-llama/Llama-Vision-Free", "is_recommended": True},
        {"model_id": "Qwen/Qwen2.5-72B-Instruct-Turbo"},
        {"model_id": "mistralai/Mixtral-8x22B-Instruct-v0.1"},
    ],
    "deepseek": [
        {"model_id": "deepseek-chat", "is_recommended": True},
        {"model_id": "deepseek-coder"},
    ],
    "mistral": [
        {"model_id": "mistral-large-latest", "is_recommended": True},
        {"model_id": "mistral-small-latest"},
        {"model_id": "pixtral-large-latest"},
        {"model_id": "codestral-latest"},
    ],
    "dashscope": [
        {"model_id": "qwen-vl-max", "is_recommended": True},
        {"model_id": "qwen-vl-plus"},
        {"model_id": "qwen-max"},
        {"model_id": "qwen-turbo"},
    ],
    "xai": [
        {"model_id": "grok-2-latest", "is_recommended": True},
        {"model_id": "grok-2-vision-1212"},
        {"model_id": "grok-beta"},
    ],
    "perplexity": [
        {"model_id": "llama-3.1-sonar-large-128k-online", "is_recommended": True},
        {"model_id": "llama-3.1-sonar-small-128k-online"},
        {"model_id": "llama-3.1-sonar-large-128k-chat"},
    ],
    "fireworks": [
        {"model_id": "accounts/fireworks/models/llama-v3p1-70b-instruct", "is_recommended": True},
        {"model_id": "accounts/fireworks/models/llama-v3p2-11b-vision-instruct", "is_recommended": True},
        {"model_id": "accounts/fireworks/models/mixtral-8x22b-instruct"},
        {"model_id": "accounts/fireworks/models/qwen2-vl-72b-instruct"},
    ],
    "cohere": [
        {"model_id": "command-r-plus", "is_recommended": True},
        {"model_id": "command-r"},
        {"model_id": "embed-english-v3.0"},
        {"model_id": "embed-multilingual-v3.0"},
    ],
}


# =============================================================================
# Response Models
# =============================================================================

class ProviderCatalogResponse(BaseModel):
    """Provider from the hardcoded catalog."""
    type: str
    name: str
    description: str
    api_key_env: Optional[str]
    api_key_url: Optional[str]
    is_local: bool
    is_builtin: bool   # True if built into macOS (no config needed)
    supports_vision: bool
    supports_embeddings: bool
    supports_streaming: bool
    default_model: Optional[str]
    has_api_key: bool  # Whether user has stored key
    # UI metadata (for SwiftUI - no hardcoded values in frontend)
    icon: str          # SF Symbol name (fallback)
    logo_asset: Optional[str]  # Bundled image asset name (e.g., "Providers/OpenAI")
    color: str         # Color name for SwiftUI
    sort_order: int    # Display order (lower = first)


class ProviderResponse(BaseModel):
    """User-configured provider."""
    id: str
    name: str
    provider_type: str
    api_base: Optional[str]
    enabled: bool
    sort_order: int
    has_api_key: bool
    created_at: str


class ModelResponse(BaseModel):
    """Rich model info from LiteLLM or local provider."""
    model_id: str
    full_name: str
    description: Optional[str] = None
    is_recommended: bool = False
    is_local: bool = False  # True for Ollama/LM Studio/Apple - shows "Free" in UI

    # Pricing (per million tokens)
    input_cost_per_million: float = 0
    output_cost_per_million: float = 0
    batch_input_cost_per_million: Optional[float] = None  # Batch API pricing
    batch_output_cost_per_million: Optional[float] = None
    cache_read_cost_per_million: Optional[float] = None   # Prompt caching

    # Context windows
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None

    # Mode (chat, embedding, image_generation, audio_transcription, etc.)
    mode: str = "chat"

    # Capabilities
    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_pdf_input: bool = False
    supports_prompt_caching: bool = False
    supports_reasoning: bool = False
    supports_web_search: bool = False
    supports_streaming: bool = True
    supports_batch_api: bool = False

    # Provider info
    provider: Optional[str] = None  # e.g., "openai", "anthropic"


class UserModelResponse(BaseModel):
    """User-configured model."""
    id: str
    provider_id: str
    name: str
    model_id: str
    capabilities: list[str]
    is_default: bool
    enabled: bool
    input_cost: Optional[float]
    output_cost: Optional[float]


# =============================================================================
# Request Models
# =============================================================================

class ProviderCreate(BaseModel):
    """Create a new provider configuration."""
    provider_type: str  # e.g., "openai"
    name: Optional[str] = None  # Custom display name
    api_base: Optional[str] = None  # Custom endpoint
    api_key: Optional[str] = None  # Store in keychain


class ProviderUpdate(BaseModel):
    """Update provider settings."""
    name: Optional[str] = None
    api_base: Optional[str] = None
    enabled: Optional[bool] = None
    api_key: Optional[str] = None  # Update keychain


class ModelCreate(BaseModel):
    """Add a model to a provider."""
    provider_id: str
    model_id: str  # LiteLLM model ID
    name: Optional[str] = None  # Display name
    is_default: bool = False


# =============================================================================
# Catalog Routes (read-only info about available providers)
# =============================================================================

@router.get("/catalog")
async def list_provider_catalog() -> list[ProviderCatalogResponse]:
    """List all available providers from the catalog, sorted by sort_order."""
    result = []
    for info in list_catalog_providers():
        result.append(ProviderCatalogResponse(
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
        ))
    # Sort by sort_order
    result.sort(key=lambda x: x.sort_order)
    return result


@router.get("/catalog/{provider_type}")
async def get_catalog_provider(provider_type: str) -> ProviderCatalogResponse:
    """Get info about a specific provider type."""
    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider type not found: {provider_type}")

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
# Models Discovery (from LiteLLM registry)
# =============================================================================

@router.get("/models/{provider_type}")
async def list_models_for_provider(
    provider_type: str,
    search: Optional[str] = Query(None, description="Filter models by name"),
    vision_only: bool = Query(False, description="Only show vision-capable models"),
    sort_by: str = Query("name", description="Sort by: name, cost"),
) -> list[ModelResponse]:
    """List available models for a provider.

    For local providers (ollama, lmstudio, apple_vision, apple_intelligence),
    queries the running server or returns built-in models.
    For cloud providers, uses LiteLLM's static registry with cost info.
    """
    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider type not found: {provider_type}")

    models = []

    # Apple - built-in macOS frameworks (Vision, Speech, Intelligence)
    if provider_type == "apple":
        models = [
            ModelResponse(
                model_id="apple-vision",
                full_name="Apple Vision (OCR)",
                input_cost_per_million=0,
                output_cost_per_million=0,
                supports_vision=True,
                description="On-device text recognition using Vision Framework (macOS 10.15+). Fast, private, works offline.",
                is_local=True,
                is_recommended=True,
                mode="chat",
            ),
            ModelResponse(
                model_id="apple-speech",
                full_name="Apple Speech (Transcription)",
                input_cost_per_million=0,
                output_cost_per_million=0,
                supports_audio_input=True,
                description="On-device audio transcription using Speech Framework (macOS 10.15+). Supports streaming.",
                is_local=True,
                is_recommended=True,
                mode="audio_transcription",
            ),
            ModelResponse(
                model_id="apple-intelligence",
                full_name="Apple Intelligence",
                input_cost_per_million=0,
                output_cost_per_million=0,
                supports_vision=True,
                description="On-device AI using Apple Intelligence (macOS 15+ required). Private, fast, no cloud.",
                is_local=True,
                is_recommended=True,
                mode="chat",
            ),
        ]

    # Ollama - query local server
    elif provider_type == "ollama":
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("models", []):
                        details = m.get("details", {})
                        families = details.get("families", [])
                        size_gb = m.get("size", 0) / (1024 ** 3)
                        param_size = details.get("parameter_size", "")
                        is_vision = "vision" in families or "clip" in families
                        # Build informative description
                        desc_parts = []
                        if param_size:
                            desc_parts.append(f"{param_size} parameters")
                        desc_parts.append(f"{size_gb:.1f}GB on disk")
                        if is_vision:
                            desc_parts.append("supports images")
                        desc_parts.append("runs locally, free")
                        models.append(ModelResponse(
                            model_id=m["name"],
                            full_name=m["name"],
                            input_cost_per_million=0,
                            output_cost_per_million=0,
                            supports_vision=is_vision,
                            description=", ".join(desc_parts),
                            is_local=True,
                        ))
        except Exception as e:
            logger.warning(f"Failed to query Ollama: {e}")

    # LM Studio - query local server
    elif provider_type == "lmstudio":
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:1234/v1/models", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("data", []):
                        model_id = m["id"]
                        is_vision = "vl" in model_id.lower() or "vision" in model_id.lower()
                        is_embed = "embed" in model_id.lower()
                        # Detect model family/type from name
                        model_lower = model_id.lower()
                        if is_vision:
                            if "qwen" in model_lower:
                                desc = "Qwen Vision model - excellent for OCR and image understanding. Runs locally, free."
                            elif "llava" in model_lower:
                                desc = "LLaVA vision model - good for image description. Runs locally, free."
                            else:
                                desc = "Vision/multimodal model - supports image input. Runs locally, free."
                        elif is_embed:
                            if "nomic" in model_lower:
                                desc = "Nomic text embeddings - great for semantic search. Runs locally, free."
                            else:
                                desc = "Embedding model - converts text to vectors for search. Runs locally, free."
                        else:
                            if "llama" in model_lower:
                                desc = "Meta Llama model - versatile chat/instruction model. Runs locally, free."
                            elif "qwen" in model_lower:
                                desc = "Alibaba Qwen model - strong multilingual support. Runs locally, free."
                            elif "mistral" in model_lower or "mixtral" in model_lower:
                                desc = "Mistral AI model - efficient and fast. Runs locally, free."
                            elif "phi" in model_lower:
                                desc = "Microsoft Phi model - small but capable. Runs locally, free."
                            elif "gemma" in model_lower:
                                desc = "Google Gemma model - efficient open model. Runs locally, free."
                            else:
                                desc = "Chat/instruction model. Runs locally, free."
                        models.append(ModelResponse(
                            model_id=model_id,
                            full_name=model_id,
                            input_cost_per_million=0,
                            output_cost_per_million=0,
                            supports_vision=is_vision,
                            description=desc,
                            is_local=True,
                        ))
        except Exception as e:
            logger.warning(f"Failed to query LM Studio: {e}")

    # Cloud providers - combine curated recommendations with LiteLLM registry
    else:
        from fichero.llm import list_models_for_provider as llm_list_models

        # Get all models from LiteLLM
        raw_models = llm_list_models(provider_type)
        litellm_models = {m["model_id"]: m for m in raw_models}

        # If we have curated models, mark them as recommended
        curated_ids = set()
        if provider_type in RECOMMENDED_MODELS:
            for m in RECOMMENDED_MODELS[provider_type]:
                curated_ids.add(m["model_id"])

        # Build final model list
        for model_id, model_data in litellm_models.items():
            # Mark as recommended if in curated list
            if model_id in curated_ids:
                model_data["is_recommended"] = True

            # Generate description from capabilities if not provided
            if not model_data.get("description"):
                model_data["description"] = generate_model_description(model_data)

            models.append(ModelResponse(**model_data))

        # Add any curated models not in LiteLLM (shouldn't happen often)
        litellm_ids = set(litellm_models.keys())
        for m in RECOMMENDED_MODELS.get(provider_type, []):
            if m["model_id"] not in litellm_ids:
                # Create minimal model response for curated model not in LiteLLM
                models.append(ModelResponse(
                    model_id=m["model_id"],
                    full_name=m["model_id"],
                    is_recommended=m.get("is_recommended", False),
                ))

    # Apply filters
    if search:
        search_lower = search.lower()
        models = [m for m in models if search_lower in m.model_id.lower() or search_lower in m.full_name.lower()]

    if vision_only:
        models = [m for m in models if m.supports_vision]

    # Apply sorting - recommended models always at top
    if sort_by == "cost":
        models.sort(key=lambda m: (
            0 if m.is_recommended else 1,  # Recommended first
            (m.input_cost_per_million or 0) + (m.output_cost_per_million or 0)
        ))
    else:  # Default: name, but recommended first
        models.sort(key=lambda m: (
            0 if m.is_recommended else 1,  # Recommended first
            m.model_id.lower()
        ))

    return models


# =============================================================================
# User Provider Configuration
# =============================================================================

@router.get("")
async def list_providers() -> list[ProviderResponse]:
    """List user's configured providers."""
    providers = db.all(ProviderModel)
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
async def create_provider(request: ProviderCreate) -> ProviderResponse:
    """Create a new provider configuration."""
    # Validate provider type
    try:
        ptype = ProviderType(request.provider_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider type: {request.provider_type}")

    info = get_provider_info(ptype)
    if not info:
        raise HTTPException(status_code=400, detail=f"Unknown provider type: {request.provider_type}")

    # Create provider record
    provider = ProviderModel(
        name=request.name or info.name,
        provider_type=ptype,
        api_base=request.api_base,
        enabled=True,
    )
    db.save(provider)

    # Store API key in keychain if provided
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
        created_at=provider.created_at.isoformat(),
    )


@router.get("/{provider_id}")
async def get_provider(provider_id: str) -> ProviderResponse:
    """Get a specific provider configuration."""
    provider = db.get(ProviderModel, provider_id)
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
async def update_provider(provider_id: str, request: ProviderUpdate) -> ProviderResponse:
    """Update a provider configuration."""
    provider = db.get(ProviderModel, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Update fields if provided
    if request.name is not None:
        provider.name = request.name
    if request.api_base is not None:
        provider.api_base = request.api_base
    if request.enabled is not None:
        provider.enabled = request.enabled

    db.save(provider)

    # Update API key in keychain if provided
    if request.api_key is not None:
        if request.api_key:
            set_api_key(provider.provider_type.value, request.api_key)
        else:
            # Empty string means delete
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
async def delete_provider(provider_id: str):
    """Delete a provider and optionally its API key."""
    provider = db.get(ProviderModel, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Delete associated models
    models = db.query(ModelModel, provider_id=provider_id)
    for model in models:
        db.delete(model)

    # Delete provider
    db.delete(provider)

    return {"status": "deleted"}


# =============================================================================
# API Key Management
# =============================================================================

class APIKeyRequest(BaseModel):
    """Request body for setting API key."""
    api_key: str


@router.post("/{provider_type}/api-key")
async def set_provider_api_key(provider_type: str, request: APIKeyRequest):
    """Store API key for a provider type in keychain."""
    if not keychain_available():
        raise HTTPException(status_code=503, detail="Keychain not available")

    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider type not found: {provider_type}")

    if info.is_local:
        raise HTTPException(status_code=400, detail="Local providers don't need API keys")

    logger.info(f"Saving API key for {provider_type}")
    success = set_api_key(provider_type, request.api_key)
    if not success:
        logger.error(f"Failed to store API key for {provider_type}")
        raise HTTPException(status_code=500, detail="Failed to store API key")

    logger.info(f"Successfully stored API key for {provider_type}")
    return {"status": "stored"}


@router.delete("/{provider_type}/api-key")
async def delete_provider_api_key(provider_type: str):
    """Delete API key for a provider type from keychain."""
    if not keychain_available():
        raise HTTPException(status_code=503, detail="Keychain not available")

    delete_api_key(provider_type)
    return {"status": "deleted"}


@router.get("/{provider_type}/api-key/status")
async def check_api_key_status(provider_type: str):
    """Check if API key exists for a provider type."""
    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider type not found: {provider_type}")

    return {
        "provider_type": provider_type,
        "has_api_key": has_api_key(provider_type) if not info.is_local else True,
        "is_local": info.is_local,
        "keychain_available": keychain_available(),
    }


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
async def test_provider_connection(provider_type: str) -> ConnectionTestResponse:
    """
    Test connection to a provider.

    Makes a minimal API call to verify:
    - Network connectivity
    - API key validity (for cloud providers)
    - Server availability (for local providers)
    """
    import time
    import httpx

    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"Provider type not found: {provider_type}")

    start_time = time.time()

    try:
        # Handle different provider types
        if provider_type == "apple_vision":
            # Apple Vision is built-in, always works
            return ConnectionTestResponse(
                success=True,
                provider_type=provider_type,
                message="Apple Vision Framework is available",
                latency_ms=0,
            )

        elif provider_type == "apple_intelligence":
            # Apple Intelligence - check macOS version
            import platform
            version = platform.mac_ver()[0]
            major = int(version.split('.')[0]) if version else 0
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
            # Test Ollama local server
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
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
            # Test LM Studio local server
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:1234/v1/models", timeout=5.0)
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
            # Test OpenAI API
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
            # Test Anthropic API (no /models endpoint, use a simple check)
            api_key = get_api_key("anthropic")
            if not api_key:
                return ConnectionTestResponse(
                    success=False,
                    provider_type=provider_type,
                    message="No API key configured",
                )
            # Anthropic doesn't have a simple health check, so we verify key format
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
            # Test Hugging Face API
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
            # Test Google AI API
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
            # Test Groq API
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
            # Generic check - just verify API key exists
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
# User Model Configuration
# =============================================================================

@router.get("/{provider_id}/models")
async def list_provider_models(provider_id: str) -> list[UserModelResponse]:
    """List user's configured models for a provider."""
    provider = db.get(ProviderModel, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    models = db.query(ModelModel, provider_id=provider_id)
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
async def add_model_to_provider(provider_id: str, request: ModelCreate) -> UserModelResponse:
    """Add a model configuration to a provider."""
    provider = db.get(ProviderModel, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Get cost info from LiteLLM
    from fichero.llm import get_model_cost

    cost_info = get_model_cost(f"{provider.provider_type.value}/{request.model_id}")

    model = ModelModel(
        provider_id=provider_id,
        name=request.name or request.model_id,
        model_id=request.model_id,
        is_default=request.is_default,
        input_cost=cost_info.get("input_cost_per_token") * 1_000_000 if cost_info else None,
        output_cost=cost_info.get("output_cost_per_token") * 1_000_000 if cost_info else None,
    )
    db.save(model)

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
async def remove_model_from_provider(provider_id: str, model_id: str):
    """Remove a model from a provider."""
    model = db.get(ModelModel, model_id)
    if not model or model.provider_id != provider_id:
        raise HTTPException(status_code=404, detail="Model not found")

    db.delete(model)
    return {"status": "deleted"}
