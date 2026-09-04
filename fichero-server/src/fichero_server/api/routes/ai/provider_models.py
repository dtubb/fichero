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

from fichero_server.db.app import get_app_db
from fichero_server.security.keychain import get_api_key
from fichero_server.llm.providers import get_provider_info
from fichero_server.llm.model_types import infer_vision_support, is_batch_only_model

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
    # Daniel's picks (2026-08-25): the cheap-and-good tier, pinned on top of
    # the LIVE list — recommendation flags only, the catalog itself is live.
    "openrouter": [
        {"model_id": "anthropic/claude-haiku-4.5", "is_recommended": True,
         "description": "Cheap, fast Anthropic tier — Daniel's pick for everyday runs."},
        {"model_id": "openai/gpt-5-mini", "is_recommended": True,
         "description": "OpenAI's cheap tier — Daniel's pick."},
        {"model_id": "google/gemini-3.1-flash-lite", "is_recommended": True, "supports_vision": True,
         "description": "The known-good paleography draft model — cheap, vision-capable."},
        {"model_id": "qwen/qwen3-vl-8b-instruct", "is_recommended": True, "supports_vision": True,
         "description": "Small vision model for OCR/handwriting — Daniel's pick."},
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


# ---------------------------------------------------------------------------
# LIVE catalogs (2026-08-25). LiteLLM's bundled registry is a SNAPSHOT — the
# standing rule is "litellm for PRICING only", yet it had become the model
# catalog: HuggingFace showed exactly our 3 curated entries and OpenRouter
# lagged its weekly churn ("some seemed off"). Providers that publish a live
# catalog get asked LIVE, with an in-process TTL cache and the old static
# path as the fallback — a network hiccup can never make the list worse
# than it was before this.
# ---------------------------------------------------------------------------

_LIVE_CATALOG_TTL_SECONDS = 3600.0
_live_catalog_cache: dict[str, tuple[float, list[dict]]] = {}


def _live_cache_get(key: str) -> list[dict] | None:
    import time

    hit = _live_catalog_cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _LIVE_CATALOG_TTL_SECONDS:
        return hit[1]
    return None


def _live_cache_put(key: str, models: list[dict]) -> None:
    import time

    _live_catalog_cache[key] = (time.monotonic(), models)


async def _live_openrouter_models() -> list[dict]:
    """OpenRouter's own /models — id, name, per-token pricing, modality."""
    import httpx  # lazy, matching the route's own import discipline

    if (cached := _live_cache_get("openrouter")) is not None:
        return cached
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models", timeout=8.0
        )
        response.raise_for_status()
        payload = response.json()

    def per_million(raw: object) -> float | None:
        try:
            return float(raw) * 1_000_000  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    models: list[dict] = []
    for m in payload.get("data", []):
        modality = str((m.get("architecture") or {}).get("modality") or "")
        pricing = m.get("pricing") or {}
        models.append({
            "model_id": m.get("id", ""),
            "full_name": m.get("name") or m.get("id", ""),
            "input_cost_per_million": per_million(pricing.get("prompt")),
            "output_cost_per_million": per_million(pricing.get("completion")),
            "supports_vision": "image" in modality,
            "supports_pdf_input": "file" in modality,
            "max_input_tokens": m.get("context_length"),
            "description": (m.get("description") or "")[:200],
            "provider": "openrouter",
            "mode": "chat",
        })
    models = [m for m in models if m["model_id"]]
    if models:
        _live_cache_put("openrouter", models)
    return models


async def _live_huggingface_models() -> list[dict]:
    """HF Hub models with WARM serverless inference — the ones an API key can
    actually call. Two sweeps: vision document models and text generation,
    by downloads, capped so the browser stays navigable."""
    import httpx

    if (cached := _live_cache_get("huggingface")) is not None:
        return cached
    sweeps = [
        ("image-text-to-text", True),
        ("image-to-text", True),
        ("text-generation", False),
    ]
    models: list[dict] = []
    seen: set[str] = set()
    async with httpx.AsyncClient() as client:
        for pipeline, vision in sweeps:
            response = await client.get(
                "https://huggingface.co/api/models",
                params={
                    "pipeline_tag": pipeline,
                    "sort": "downloads",
                    "limit": 60,
                    "inference": "warm",
                },
                timeout=8.0,
            )
            response.raise_for_status()
            for m in response.json():
                model_id = m.get("id", "")
                if not model_id or model_id in seen:
                    continue
                seen.add(model_id)
                models.append({
                    "model_id": model_id,
                    "full_name": model_id,
                    "supports_vision": vision,
                    "description": f"{pipeline} · Hugging Face serverless inference",
                    "provider": "huggingface",
                    "mode": "chat",
                    "is_local": False,
                })
    if models:
        _live_cache_put("huggingface", models)
    return models


async def _live_openai_compatible_models(provider_type: str) -> list[dict]:
    """GET {base}/v1/models with the stored key — the OpenAI wire format a
    dozen providers speak. Returns ids only (these endpoints carry no
    pricing); costs enrich from LiteLLM afterwards, pricing-only."""
    import httpx

    cache_key = f"oai:{provider_type}"
    if (cached := _live_cache_get(cache_key)) is not None:
        return cached
    from fichero_server.llm import _OPENAI_COMPATIBLE_BASE_URLS

    default_base = (
        "https://api.openai.com/v1"
        if provider_type == "openai"
        else _OPENAI_COMPATIBLE_BASE_URLS.get(provider_type, "")
    )
    if not default_base:
        raise RuntimeError(f"no known base URL for {provider_type}")
    base = _configured_api_base(provider_type, default_base)
    api_key = get_api_key(provider_type)
    if not api_key:
        raise RuntimeError(f"no API key stored for {provider_type}")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _openai_models_url(base),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    models = [
        {
            "model_id": m.get("id", ""),
            "full_name": m.get("id", ""),
            "provider": provider_type,
            "mode": "chat",
            # Same floor as the Anthropic/Google live catalogs: /v1/models on
            # the OpenAI wire format carries ids and nothing else, so without
            # this every GPT-4o-class model reads as text-only.
            "supports_vision": infer_vision_support(m.get("id", "")),
        }
        for m in payload.get("data", [])
        if m.get("id")
    ]
    if models:
        _live_cache_put(cache_key, models)
    return models


async def _live_anthropic_models() -> list[dict]:
    import httpx

    if (cached := _live_cache_get("anthropic")) is not None:
        return cached
    api_key = get_api_key("anthropic")
    if not api_key:
        raise RuntimeError("no API key stored for anthropic")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    # A live catalog ships ids with NO capability flags. Without a floor
    # every freshly released Claude arrived as supports_vision=False and was
    # filtered straight out of the vision pickers (Daniel, 2026-09-01:
    # "cannot select a model like Opus"). The static registry still wins
    # wherever it has a row — the enrichment in list_models_for_provider
    # overwrites this key from the static entry whenever one exists, so the
    # floor only survives for models the registry has never heard of.
    models = [
        {
            "model_id": m.get("id", ""),
            "full_name": m.get("display_name") or m.get("id", ""),
            "provider": "anthropic",
            "mode": "chat",
            "supports_vision": infer_vision_support(m.get("id", "")),
        }
        for m in payload.get("data", [])
        if m.get("id")
    ]
    if models:
        _live_cache_put("anthropic", models)
    return models


async def _live_google_models() -> list[dict]:
    import httpx

    if (cached := _live_cache_get("google")) is not None:
        return cached
    api_key = get_api_key("google")
    if not api_key:
        raise RuntimeError("no API key stored for google")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 200},
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for m in payload.get("models", []):
        name = str(m.get("name", "")).removeprefix("models/")
        if not name or "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        # Gemini's ListModels reports supportedGenerationMethods, not
        # modalities — so the vision floor is the only thing that keeps a new
        # Gemini out of the "text only" bucket (Daniel, 2026-09-01: "or
        # Google"). inputTokenLimit alone never implied it.
        models.append({
            "model_id": name,
            "full_name": m.get("displayName") or name,
            "max_input_tokens": m.get("inputTokenLimit"),
            "description": (m.get("description") or "")[:200],
            "provider": "google",
            "mode": "chat",
            "supports_vision": infer_vision_support(name),
        })
    if models:
        _live_cache_put("google", models)
    return models


def _openai_compatible_fetcher(provider_type: str):
    async def fetch() -> list[dict]:
        return await _live_openai_compatible_models(provider_type)
    return fetch


_LIVE_CATALOG_FETCHERS = {
    "openrouter": _live_openrouter_models,
    "huggingface": _live_huggingface_models,
    "anthropic": _live_anthropic_models,
    "google": _live_google_models,
    **{
        p: _openai_compatible_fetcher(p)
        for p in (
            "openai", "groq", "together", "deepseek",
            "dashscope", "xai", "perplexity", "fireworks",
        )
    },
}


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


# =============================================================================
# The built-in Apple rows (#935/#937), as DATA.
#
# One statement per model of what it can do — and it has to agree with
# `_CANONICAL_APPLE_CAPABILITIES` in providers.py, which is what a saved row
# carries and what every capability check reads. The two had drifted:
# `apple-intelligence` was served here with supports_vision=True while its
# canonical capabilities are ["text"] — and FoundationModels takes no image
# input at all (fm-bridge opens a SystemLanguageModel session; there is no
# image path in it). A row that claims a capability the framework does not
# have is exactly how a vision step ends up pointed at a text-only on-device
# model.
#
# Hoisted out of the route so a test can hold the two sources side by side —
# a rule with no fixture proving it fires is not a rule.
# =============================================================================
APPLE_BUILTIN_MODELS: list[ModelResponse] = [
    ModelResponse(
        model_id="apple-vision",
        full_name="Apple Vision (OCR)",
        input_cost_per_million=0,
        output_cost_per_million=0,
        supports_vision=True,
        description=(
            "On-device text recognition using Vision Framework (macOS 10.15+). "
            "Fast, private, works offline."
        ),
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
        description=(
            "On-device audio transcription using Speech Framework (macOS 10.15+). "
            "Supports streaming."
        ),
        is_local=True,
        is_recommended=True,
        mode="audio_transcription",
    ),
    ModelResponse(
        model_id="apple-intelligence",
        full_name="Apple Intelligence (Foundation Models)",
        input_cost_per_million=0,
        output_cost_per_million=0,
        # TEXT ONLY. Guided generation with a schema-constrained decoder
        # (DynamicGenerationSchema via fm-bridge), no image input — see above.
        supports_vision=False,
        description=(
            "On-device text LLM using Apple Foundation Models (macOS 26+). "
            "Schema-constrained structured output, private, free, offline."
        ),
        is_local=True,
        is_recommended=True,
        mode="chat",
    ),
]


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
        models = list(APPLE_BUILTIN_MODELS)

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
        # Downloaded models are listed from the STORE first, not only from a
        # running server (#4560). Asking `GET /v1/models` was the whole answer,
        # which meant a model the user had explicitly downloaded was invisible
        # in every picker until the sidecar happened to be up -- and the
        # sidecar starts on demand FOR A RUN, so there was no way to pick the
        # model that would have started it. Downloading a model is the user
        # saying they want it; the catalog says so too, server or no server.
        seen_model_ids: set[str] = set()
        try:
            from fichero_server.llm.mlx_model_store import get_mlx_model_store

            for entry in get_mlx_model_store().list_catalog_entries():
                if not entry.installed:
                    continue
                is_vision = "vision" in entry.capabilities
                seen_model_ids.add(entry.model_id)
                models.append(
                    ModelResponse(
                        model_id=entry.model_id,
                        full_name=entry.display_name,
                        input_cost_per_million=0,
                        output_cost_per_million=0,
                        supports_vision=is_vision,
                        description=(
                            "Downloaded MLX vision/OCR model. Runs locally, free."
                            if is_vision
                            else "Downloaded local MLX model. Runs locally, free."
                        ),
                        is_local=True,
                        is_recommended=True,
                        provider="omlx",
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to read the local MLX model store: {e}")
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
                        if model_id in seen_model_ids:
                            # Already listed from the store; the store knows
                            # its real display name and capabilities, and the
                            # server reports a bare snapshot path.
                            continue
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

    # DeepL — a translation service, not an LLM catalog. It publishes no
    # /models endpoint and the vendored LiteLLM snapshot has never heard of
    # it, so the generic cloud path below returns an EMPTY list: Settings
    # could add the provider and then offer nothing to select, leaving the
    # key unsavable through the normal flow (Daniel, 2026-09-03: the DeepL
    # key belongs in the provider screen like every other key). One engine,
    # named once, priced per CHARACTER — so the per-token cost fields stay
    # None rather than carrying a number that would be a lie.
    elif provider_type == "deepl":
        models = [
            ModelResponse(
                model_id="deepl-default",
                full_name="DeepL Translate",
                description=(
                    "DeepL's translation engine (/v2/translate). Billed per "
                    "character, not per token. Translation only — it does not "
                    "answer prompts."
                ),
                mode="translation",
                supports_streaming=False,
                is_recommended=True,
                provider="deepl",
            )
        ]

    # Cloud providers — LIVE catalog when the provider publishes one
    # (2026-08-25), else LiteLLM's static registry; curated flags merge on
    # top either way. A live fetch that fails falls straight through to the
    # static path, so the list can never be worse than before.
    else:
        from fichero_server.llm import list_models_for_provider as llm_list_models

        raw_models: list[dict] = []
        if (fetch_live := _LIVE_CATALOG_FETCHERS.get(provider_type)) is not None:
            try:
                raw_models = await fetch_live()
            except Exception as exc:
                logger.warning(
                    "Live model catalog for %s failed (%s) — using the static registry",
                    provider_type, exc,
                )
        if raw_models:
            # PRICING-ONLY enrichment (the LiteLLM rule): live catalogs
            # mostly ship ids without costs; fill missing cost/capability
            # fields from the static registry WITHOUT letting it decide
            # which models exist. Absent pricing stays absent — an honest
            # blank beats a stale number.
            static_by_id: dict[str, dict] = {}
            try:
                for m in llm_list_models(provider_type):
                    static_by_id[m["model_id"]] = m
                    static_by_id[m["model_id"].split("/", 1)[-1]] = m
            except Exception:
                static_by_id = {}
            for live in raw_models:
                static = static_by_id.get(live["model_id"]) or static_by_id.get(
                    live["model_id"].split("/", 1)[-1]
                )
                if static:
                    for key, value in static.items():
                        if value is not None:
                            live.setdefault(key, value)
                    # The live row's supports_vision is a FAMILY FLOOR, not a
                    # statement — setdefault would let a guess outrank the
                    # registry. Where the registry has an opinion, it wins;
                    # the floor only survives for models it has never heard
                    # of, which is exactly what it is for.
                    if "supports_vision" in static:
                        live["supports_vision"] = bool(static["supports_vision"])
        else:
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

    # A model Fichero cannot actually call must not be OFFERED. Batch-only
    # SKUs answer a normal run with a 404 naming the provider's batches
    # endpoint; Fichero has no batch client, so listing one only buys the
    # user a failed run (Daniel, 2026-09-01). The preflight refuses one too
    # — this is the half that stops it being picked in the first place.
    models = [m for m in models if not is_batch_only_model(m.model_id)]

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
