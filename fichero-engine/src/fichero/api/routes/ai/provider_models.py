"""
Provider model discovery routes.

Pydantic request/response models + LiteLLM model registry discovery.
Included by providers.py via router.include_router().
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from fichero.db.app import get_app_db
from fichero.security.keychain import get_api_key
from fichero.providers import get_provider_info

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_model_description(model_data: dict) -> str:
    """Generate a factual description from model capabilities.

    Creates descriptions based on what the model actually does,
    derived from LiteLLM's capability flags and pricing data.
    """
    parts = []

    max_input = model_data.get("max_input_tokens")
    if max_input:
        if max_input >= 1_000_000:
            parts.append(f"{max_input // 1_000_000}M token context")
        elif max_input >= 100_000:
            parts.append(f"{max_input // 1_000}K token context")

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

    input_cost = model_data.get("input_cost_per_million")
    output_cost = model_data.get("output_cost_per_million")
    if input_cost == 0 and output_cost == 0:
        parts.append("free")

    if not parts:
        return None

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
        {
            "model_id": "gpt-5",
            "is_recommended": True,
            "supports_vision": True,
            "supports_pdf_input": True,
            "description": "General-purpose multimodal model for OCR, handwriting, and structured extraction.",
        },
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
        {
            "model_id": "gemini-3-pro-preview",
            "is_recommended": True,
            "supports_vision": True,
            "supports_pdf_input": True,
            "description": "Preview Gemini 3 multimodal model for OCR, handwriting, and document understanding.",
        },
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
        {
            "model_id": "accounts/fireworks/models/llama-v3p1-70b-instruct",
            "is_recommended": True,
        },
        {
            "model_id": "accounts/fireworks/models/llama-v3p2-11b-vision-instruct",
            "is_recommended": True,
        },
        {"model_id": "accounts/fireworks/models/mixtral-8x22b-instruct"},
        {"model_id": "accounts/fireworks/models/qwen2-vl-72b-instruct"},
    ],
    "huggingface": [
        {
            "model_id": "Qwen/Qwen3-VL-8B-Instruct",
            "is_recommended": True,
            "supports_vision": True,
            "supports_pdf_input": True,
            "description": "Qwen3-VL 8B Instruct for OCR, handwriting, and general document reasoning.",
        },
        {
            "model_id": "datalab-to/chandra-ocr-2",
            "is_recommended": True,
            "supports_vision": True,
            "supports_pdf_input": True,
            "description": "Chandra OCR model for high-accuracy document and handwriting extraction.",
        },
        {
            "model_id": "nanonets/Nanonets-OCR-s",
            "is_recommended": True,
            "supports_vision": True,
            "supports_pdf_input": True,
            "description": "Nanonets OCR-S model for OCR and layout-aware document transcription.",
        },
    ],
    "omlx": [
        {
            "model_id": "Qwen3-VL",
            "is_recommended": True,
            "supports_vision": True,
            "description": "Local MLX vision model for OCR and document understanding.",
        },
        {
            "model_id": "Nanonets-OCR",
            "is_recommended": True,
            "supports_vision": True,
            "description": "Local OCR-focused MLX model.",
        },
        {
            "model_id": "Chandra-OCR",
            "is_recommended": True,
            "supports_vision": True,
            "description": "Local OCR-focused MLX model.",
        },
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
    is_builtin: bool  # True if built into macOS (no config needed)
    supports_vision: bool
    supports_embeddings: bool
    supports_streaming: bool
    default_model: Optional[str]
    has_api_key: bool  # Whether user has stored key
    # UI metadata (for SwiftUI - no hardcoded values in frontend)
    icon: str  # SF Symbol name (fallback)
    logo_asset: Optional[str]  # Bundled image asset name (e.g., "Providers/OpenAI")
    color: str  # Color name for SwiftUI
    sort_order: int  # Display order (lower = first)


class ProviderCatalogListResponse(BaseModel):
    """Envelope for a list of catalog providers."""

    items: list[ProviderCatalogResponse]
    count: int


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


class ProviderListResponse(BaseModel):
    """Envelope for a list of user-configured providers."""

    items: list[ProviderResponse]
    count: int


class ModelResponse(BaseModel):
    """Rich model info from LiteLLM or local provider."""

    model_id: str
    full_name: str
    description: Optional[str] = None
    is_recommended: bool = False
    is_local: bool = False  # True for Ollama/LM Studio/Apple - shows "Free" in UI

    # Pricing (per million tokens)
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    batch_input_cost_per_million: Optional[float] = None  # Batch API pricing
    batch_output_cost_per_million: Optional[float] = None
    cache_read_cost_per_million: Optional[float] = None  # Prompt caching

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


class ModelListResponse(BaseModel):
    """Envelope for a list of discovered models."""

    items: list[ModelResponse]
    count: int


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


class UserModelListResponse(BaseModel):
    """Envelope for a list of user-configured models."""

    items: list[UserModelResponse]
    count: int


def _configured_api_base(provider_type: str, default: str) -> str:
    """Return the first configured api_base for provider_type, else default."""
    try:
        app_db = get_app_db()
        for provider in app_db.list_providers():
            if provider.provider_type.value == provider_type and provider.api_base:
                return provider.api_base.rstrip("/")
    except Exception as exc:
        logger.debug("Provider api_base lookup failed for %s: %s", provider_type, exc)
    return default.rstrip("/")


def _openai_models_url(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _local_server_root(api_base: str) -> str:
    base = api_base.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def _local_model_is_vision(model_id: str) -> bool:
    model_lower = model_id.lower()
    return any(
        token in model_lower
        for token in ("vl", "vision", "ocr", "nanonets", "chandra")
    )


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
# Models Discovery (from LiteLLM registry)
# =============================================================================


@router.get("/models/{provider_type}", response_model=ModelListResponse)
async def list_models_for_provider(
    provider_type: str,
    search: Optional[str] = Query(None, description="Filter models by name"),
    vision_only: bool = Query(False, description="Only show vision-capable models"),
    sort_by: str = Query("name", description="Sort by: name, cost"),
) -> ModelListResponse:
    """List available models for a provider.

    For local providers (ollama, lmstudio, apple_vision, apple_intelligence),
    queries the running server or returns built-in models.
    For cloud providers, uses LiteLLM's static registry with cost info.
    """
    import httpx  # lazy (#3985): keep off the engine boot path

    info = get_provider_info(provider_type)
    if not info:
        raise HTTPException(
            status_code=404, detail=f"Provider type not found: {provider_type}"
        )

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
            api_base = _configured_api_base("ollama", "http://localhost:11434")
            tags_url = f"{_local_server_root(api_base)}/api/tags"
            async with httpx.AsyncClient() as client:
                response = await client.get(tags_url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("models", []):
                        details = m.get("details", {})
                        families = details.get("families", [])
                        size_gb = m.get("size", 0) / (1024**3)
                        param_size = details.get("parameter_size", "")
                        is_vision = "vision" in families or "clip" in families
                        desc_parts = []
                        if param_size:
                            desc_parts.append(f"{param_size} parameters")
                        desc_parts.append(f"{size_gb:.1f}GB on disk")
                        if is_vision:
                            desc_parts.append("supports images")
                        desc_parts.append("runs locally, free")
                        models.append(
                            ModelResponse(
                                model_id=m["name"],
                                full_name=m["name"],
                                input_cost_per_million=0,
                                output_cost_per_million=0,
                                supports_vision=is_vision,
                                description=", ".join(desc_parts),
                                is_local=True,
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to query Ollama: {e}")

    # LM Studio - query local server
    elif provider_type == "lmstudio":
        try:
            api_base = _configured_api_base("lmstudio", "http://localhost:1234")
            models_url = _openai_models_url(api_base)
            async with httpx.AsyncClient() as client:
                response = await client.get(models_url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("data", []):
                        model_id = m["id"]
                        is_vision = (
                            "vl" in model_id.lower() or "vision" in model_id.lower()
                        )
                        is_embed = "embed" in model_id.lower()
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
                        models.append(
                            ModelResponse(
                                model_id=model_id,
                                full_name=model_id,
                                input_cost_per_million=0,
                                output_cost_per_million=0,
                                supports_vision=is_vision,
                                description=desc,
                                is_local=True,
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to query LM Studio: {e}")

    # oMLX - local OpenAI-compatible MLX server
    elif provider_type == "omlx":
        try:
            api_base = _configured_api_base("omlx", "http://localhost:8000/v1")
            headers = {}
            api_key = get_api_key("omlx")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    _openai_models_url(api_base),
                    headers=headers,
                    timeout=5.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    curated_models = {
                        m["model_id"]: m
                        for m in RECOMMENDED_MODELS.get(provider_type, [])
                    }
                    for m in data.get("data", []):
                        model_id = m["id"]
                        curated = curated_models.get(model_id, {})
                        is_vision = bool(
                            curated.get("supports_vision")
                            or _local_model_is_vision(model_id)
                        )
                        desc = curated.get("description")
                        if not desc:
                            if is_vision:
                                desc = (
                                    "Local MLX vision/OCR model. Runs locally, free."
                                )
                            else:
                                desc = (
                                    "Local OpenAI-compatible MLX model. Runs locally, free."
                                )
                        models.append(
                            ModelResponse(
                                model_id=model_id,
                                full_name=model_id,
                                input_cost_per_million=0,
                                output_cost_per_million=0,
                                supports_vision=is_vision,
                                description=desc,
                                is_local=True,
                                is_recommended=bool(curated.get("is_recommended")),
                                provider="omlx",
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to query oMLX: {e}")

    # Cloud providers - combine curated recommendations with LiteLLM registry
    else:
        from fichero.llm import list_models_for_provider as llm_list_models

        raw_models = llm_list_models(provider_type)
        litellm_models = {m["model_id"]: m for m in raw_models}
        curated_models = {
            m["model_id"]: m for m in RECOMMENDED_MODELS.get(provider_type, [])
        }

        for model_id, model_data in litellm_models.items():
            curated = curated_models.get(model_id)
            if curated:
                model_data["is_recommended"] = True
                if curated.get("description") and not model_data.get("description"):
                    model_data["description"] = curated["description"]
                for key in ("supports_vision", "supports_pdf_input", "mode", "provider"):
                    if key in curated and curated[key] is not None:
                        model_data.setdefault(key, curated[key])

            if not model_data.get("description"):
                model_data["description"] = generate_model_description(model_data)

            models.append(ModelResponse(**model_data))

        litellm_ids = set(litellm_models.keys())
        for model_id, model_data in curated_models.items():
            if model_id not in litellm_ids:
                data = dict(model_data)
                data.setdefault("full_name", model_id)
                data.setdefault("provider", provider_type)
                models.append(ModelResponse(**data))

    # Apply filters
    if search:
        search_lower = search.lower()
        models = [
            m
            for m in models
            if search_lower in m.model_id.lower() or search_lower in m.full_name.lower()
        ]

    if vision_only:
        models = [m for m in models if m.supports_vision]

    # Apply sorting - recommended models always at top
    if sort_by == "cost":
        models.sort(
            key=lambda m: (
                0 if m.is_recommended else 1,
                (m.input_cost_per_million or 0) + (m.output_cost_per_million or 0),
            )
        )
    else:  # Default: name, but recommended first
        models.sort(
            key=lambda m: (
                0 if m.is_recommended else 1,
                m.model_id.lower(),
            )
        )

    return ModelListResponse(items=models, count=len(models))
