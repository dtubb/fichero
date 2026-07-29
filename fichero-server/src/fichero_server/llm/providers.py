"""
Fichero Provider Catalog

Hardcoded provider definitions for supported LLM services.
Uses LiteLLM for model info, costs, and unified calling.

The catalog is version-controlled and defines:
- Provider types and their capabilities
- API key environment variables
- Local vs cloud providers

User configurations (enabled providers, custom endpoints)
are stored in DuckDB via the Provider model.

Usage:
    from fichero_server.llm.providers import PROVIDERS, ProviderType, get_provider_info

    # Get all providers
    for ptype, info in PROVIDERS.items():
        print(f"{info.name}: {info.description}")

    # Check if provider needs API key
    info = get_provider_info(ProviderType.openai)
    if info.api_key_env:
        print(f"Set {info.api_key_env} for {info.name}")
"""

from enum import Enum
from dataclasses import dataclass


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    # On-device (Apple)
    apple = "apple"
    # Built-in deterministic debug provider (no LLM, no cost) — #1566
    mock = "mock"
    # Local servers
    ollama = "ollama"
    lmstudio = "lmstudio"
    omlx = "omlx"
    # Open source / aggregators
    huggingface = "huggingface"
    openrouter = "openrouter"  # Multi-provider aggregator
    # Cloud providers
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    groq = "groq"
    together = "together"
    deepseek = "deepseek"
    mistral = "mistral"
    cohere = "cohere"
    # Additional LiteLLM providers
    dashscope = "dashscope"  # Alibaba Qwen (great for OCR)
    xai = "xai"  # Grok
    perplexity = "perplexity"  # Search-augmented
    fireworks = "fireworks"  # Fast inference
    deepl = "deepl"  # DeepL translation API
    azure = "azure"  # Azure OpenAI
    bedrock = "bedrock"  # AWS Bedrock


@dataclass(frozen=True)
class ProviderInfo:
    """Static provider metadata."""

    type: ProviderType
    name: str
    description: str
    api_key_env: str | None  # Environment variable name for API key
    api_key_url: str | None  # Where to get API key
    is_local: bool = False  # True if runs locally (no API key needed)
    is_builtin: bool = False  # True if built into macOS (no config needed at all)
    supports_vision: bool = False
    supports_embeddings: bool = False
    supports_streaming: bool = True
    default_model: str | None = None
    # UI metadata (for SwiftUI - no hardcoded values in frontend)
    icon: str = "cpu"  # SF Symbol name (fallback)
    logo_asset: str | None = None  # Bundled image asset name (e.g., "Providers/OpenAI")
    color: str = "blue"  # Color name for SwiftUI
    sort_order: int = 100  # Display order (lower = first)


# =============================================================================
# Provider Catalog
# =============================================================================

PROVIDERS: dict[ProviderType, ProviderInfo] = {
    # ==========================================================================
    # On-Device (Apple) - sort_order 0
    # ==========================================================================
    ProviderType.apple: ProviderInfo(
        type=ProviderType.apple,
        name="Apple Intelligence",
        description="On-device LLM (Foundation Models, macOS 26+)",
        api_key_env=None,
        api_key_url=None,
        is_local=True,
        is_builtin=True,  # macOS frameworks, no config needed
        supports_vision=True,
        supports_embeddings=True,
        supports_streaming=True,
        default_model="apple-vision",
        icon="apple.logo",
        color="gray",
        sort_order=0,
    ),
    # ==========================================================================
    # Built-in Debug Provider (#1566) - deterministic, zero-cost.
    #
    # Selected only by explicit LLMConfig(provider="mock"). Registered
    # is_local + is_builtin so it inherits every free / no-PAID gate via
    # _is_local_or_builtin_provider. No alias / preset / fallback ever
    # yields "mock", so it can never activate by accident — it exists so a
    # whole folder/PDF catalogue run can be debugged end-to-end (output,
    # persistence, per-page artifacts, UI) with ZERO paid LLM calls.
    # ==========================================================================
    ProviderType.mock: ProviderInfo(
        type=ProviderType.mock,
        name="Mock (Debug)",
        description="Built-in deterministic responder — zero-cost catalogue debug runs",
        api_key_env=None,
        api_key_url=None,
        is_local=True,
        is_builtin=True,  # inherits the free / no-PAID gates
        supports_vision=False,
        supports_embeddings=False,
        supports_streaming=False,
        default_model="mock",
        icon="wrench.and.screwdriver",
        color="gray",
        sort_order=999,
    ),
    # ==========================================================================
    # Local Servers - sort_order 1-2
    # ==========================================================================
    ProviderType.ollama: ProviderInfo(
        type=ProviderType.ollama,
        name="Ollama",
        description="Run models locally: Llama, Qwen, Mistral",
        api_key_env=None,
        api_key_url=None,
        is_local=True,
        supports_vision=True,
        supports_embeddings=True,
        default_model="llama3.2",
        icon="server.rack",
        logo_asset="Providers/Ollama",
        color="purple",
        sort_order=1,
    ),
    ProviderType.lmstudio: ProviderInfo(
        type=ProviderType.lmstudio,
        name="LM Studio",
        description="Local GUI for running models",
        api_key_env=None,
        api_key_url=None,
        is_local=True,
        supports_vision=True,
        supports_embeddings=True,
        default_model="local-model",
        icon="desktopcomputer",
        logo_asset="Providers/LMStudio",
        color="indigo",
        sort_order=2,
    ),
    ProviderType.omlx: ProviderInfo(
        type=ProviderType.omlx,
        name="MLX (Local)",
        description="Local OpenAI-compatible MLX server for Qwen3-VL, Nanonets-OCR, and Chandra-OCR",
        api_key_env=None,
        api_key_url=None,
        is_local=True,
        supports_vision=True,
        supports_embeddings=False,
        default_model="local-model",
        icon="cpu",
        color="teal",
        sort_order=3,
    ),
    # ==========================================================================
    # Open Source - sort_order 4
    # ==========================================================================
    ProviderType.huggingface: ProviderInfo(
        type=ProviderType.huggingface,
        name="Hugging Face",
        description="Inference API with thinking models (NuMarkdown, DeepSeek, Qwen)",
        api_key_env="HUGGINGFACE_API_KEY",
        api_key_url="https://huggingface.co/settings/tokens",
        supports_vision=True,
        supports_embeddings=True,
        default_model="Qwen/Qwen3-VL-8B-Instruct",
        icon="face.smiling",
        logo_asset="Providers/HuggingFace",
        color="yellow",
        sort_order=4,
    ),
    ProviderType.openrouter: ProviderInfo(
        type=ProviderType.openrouter,
        name="OpenRouter",
        description="Access 100+ models: Claude, GPT-4, Llama, Gemini",
        api_key_env="OPENROUTER_API_KEY",
        api_key_url="https://openrouter.ai/keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="openai/gpt-4o-mini",
        icon="point.3.connected.trianglepath.dotted",  # Network/routing icon
        logo_asset="Providers/OpenRouter",
        color="teal",
        sort_order=5,
    ),
    # ==========================================================================
    # Cloud Providers - sort_order 6+
    # ==========================================================================
    ProviderType.openai: ProviderInfo(
        type=ProviderType.openai,
        name="OpenAI",
        description="GPT-5, GPT-4.1, GPT-4o, DALL-E, Whisper",
        api_key_env="OPENAI_API_KEY",
        api_key_url="https://platform.openai.com/api-keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="gpt-5",
        icon="sparkles",
        logo_asset="Providers/OpenAI",
        color="green",
        sort_order=6,
    ),
    ProviderType.anthropic: ProviderInfo(
        type=ProviderType.anthropic,
        name="Anthropic",
        description="Claude 4, Claude 3.5, Claude 3",
        api_key_env="ANTHROPIC_API_KEY",
        api_key_url="https://console.anthropic.com/settings/keys",
        supports_vision=True,
        supports_embeddings=False,
        default_model="claude-3-5-sonnet-20241022",
        icon="brain",
        logo_asset="Providers/Anthropic",
        color="orange",
        sort_order=7,
    ),
    ProviderType.google: ProviderInfo(
        type=ProviderType.google,
        name="Google AI",
        description="Gemini 3, Gemini 2.0, Gemini 1.5 Pro/Flash",
        api_key_env="GOOGLE_API_KEY",
        api_key_url="https://makersuite.google.com/app/apikey",
        supports_vision=True,
        supports_embeddings=True,
        default_model="gemini-3-pro-preview",
        icon="globe",
        logo_asset="Providers/GoogleAI",
        color="blue",
        sort_order=8,
    ),
    ProviderType.groq: ProviderInfo(
        type=ProviderType.groq,
        name="Groq",
        description="Ultra-fast inference: Llama 3, Mixtral",
        api_key_env="GROQ_API_KEY",
        api_key_url="https://console.groq.com/keys",
        supports_vision=True,
        supports_embeddings=False,
        default_model="llama-3.3-70b-versatile",
        icon="bolt.fill",
        logo_asset="Providers/Groq",
        color="orange",
        sort_order=9,
    ),
    ProviderType.together: ProviderInfo(
        type=ProviderType.together,
        name="Together AI",
        description="Open source models: Llama, Qwen, Mixtral",
        api_key_env="TOGETHER_API_KEY",
        api_key_url="https://api.together.xyz/settings/api-keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        icon="square.stack.3d.up",
        logo_asset="Providers/TogetherAI",
        color="teal",
        sort_order=10,
    ),
    ProviderType.deepseek: ProviderInfo(
        type=ProviderType.deepseek,
        name="DeepSeek",
        description="DeepSeek V3, DeepSeek Coder",
        api_key_env="DEEPSEEK_API_KEY",
        api_key_url="https://platform.deepseek.com/api_keys",
        supports_vision=False,
        supports_embeddings=False,
        default_model="deepseek-chat",
        icon="water.waves",
        logo_asset="Providers/DeepSeek",
        color="cyan",
        sort_order=11,
    ),
    ProviderType.mistral: ProviderInfo(
        type=ProviderType.mistral,
        name="Mistral AI",
        description="Mistral Large, Codestral, Pixtral",
        api_key_env="MISTRAL_API_KEY",
        api_key_url="https://console.mistral.ai/api-keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="mistral-large-latest",
        icon="wind",
        logo_asset="Providers/MistralAI",
        color="blue",
        sort_order=12,
    ),
    ProviderType.cohere: ProviderInfo(
        type=ProviderType.cohere,
        name="Cohere",
        description="Command R+, Embed, Rerank",
        api_key_env="COHERE_API_KEY",
        api_key_url="https://dashboard.cohere.com/api-keys",
        supports_vision=False,
        supports_embeddings=True,
        default_model="command-r-plus",
        icon="text.alignleft",
        logo_asset="Providers/Cohere",
        color="pink",
        sort_order=13,
    ),
    # ==========================================================================
    # Additional LiteLLM Providers - sort_order 14+
    # ==========================================================================
    ProviderType.dashscope: ProviderInfo(
        type=ProviderType.dashscope,
        name="DashScope (Alibaba)",
        description="Qwen VL, Qwen Max - excellent for OCR",
        api_key_env="DASHSCOPE_API_KEY",
        api_key_url="https://www.alibabacloud.com/en/solutions/generative-ai/dashscope",
        supports_vision=True,
        supports_embeddings=True,
        default_model="qwen-vl-max",
        icon="eye.circle.fill",
        logo_asset="Providers/DashScope",
        color="orange",
        sort_order=14,
    ),
    ProviderType.xai: ProviderInfo(
        type=ProviderType.xai,
        name="xAI",
        description="Grok models from xAI",
        api_key_env="XAI_API_KEY",
        api_key_url="https://console.x.ai/",
        supports_vision=True,
        supports_embeddings=False,
        default_model="grok-2-latest",
        icon="x.circle.fill",  # X logo style
        logo_asset="Providers/xAI",
        color="gray",
        sort_order=15,
    ),
    ProviderType.perplexity: ProviderInfo(
        type=ProviderType.perplexity,
        name="Perplexity",
        description="Search-augmented AI models",
        api_key_env="PERPLEXITY_API_KEY",
        api_key_url="https://www.perplexity.ai/settings/api",
        supports_vision=False,
        supports_embeddings=False,
        default_model="llama-3.1-sonar-large-128k-online",
        icon="magnifyingglass.circle.fill",
        logo_asset="Providers/Perplexity",
        color="teal",
        sort_order=16,
    ),
    ProviderType.fireworks: ProviderInfo(
        type=ProviderType.fireworks,
        name="Fireworks AI",
        description="Fast inference for open models",
        api_key_env="FIREWORKS_API_KEY",
        api_key_url="https://fireworks.ai/api-keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        icon="flame.fill",
        logo_asset="Providers/Fireworks",
        color="red",
        sort_order=17,
    ),
    ProviderType.deepl: ProviderInfo(
        type=ProviderType.deepl,
        name="DeepL",
        description="High-quality translation API",
        api_key_env="DEEPL_API_KEY",
        api_key_url="https://www.deepl.com/pro-api",
        supports_vision=False,
        supports_embeddings=False,
        default_model="deepl-default",
        icon="character.bubble",
        color="blue",
        sort_order=18,
    ),
    ProviderType.azure: ProviderInfo(
        type=ProviderType.azure,
        name="Azure OpenAI",
        description="OpenAI models on Azure (enterprise)",
        api_key_env="AZURE_API_KEY",
        api_key_url="https://portal.azure.com/",
        supports_vision=True,
        supports_embeddings=True,
        default_model="gpt-4o",
        icon="cloud.fill",
        logo_asset="Providers/Azure",
        color="blue",
        sort_order=18,
    ),
    ProviderType.bedrock: ProviderInfo(
        type=ProviderType.bedrock,
        name="AWS Bedrock",
        description="Claude, Llama, Titan on AWS",
        api_key_env="AWS_ACCESS_KEY_ID",  # Uses AWS credentials
        api_key_url="https://console.aws.amazon.com/bedrock/",
        supports_vision=True,
        supports_embeddings=True,
        default_model="anthropic.claude-3-sonnet-20240229-v1:0",
        icon="square.stack.3d.up.fill",
        logo_asset="Providers/Bedrock",
        color="orange",
        sort_order=19,
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================


def get_provider_info(provider_type: ProviderType | str) -> ProviderInfo | None:
    """Get provider info by type.

    Args:
        provider_type: ProviderType enum or string name

    Returns:
        ProviderInfo or None if not found
    """
    if isinstance(provider_type, str):
        try:
            provider_type = ProviderType(provider_type)
        except ValueError:
            return None
    return PROVIDERS.get(provider_type)


def list_providers() -> list[ProviderInfo]:
    """Get all providers as a list."""
    return list(PROVIDERS.values())


def get_cloud_providers() -> list[ProviderInfo]:
    """Get providers that require API keys (cloud services)."""
    return [p for p in PROVIDERS.values() if not p.is_local]


def get_local_providers() -> list[ProviderInfo]:
    """Get providers that run locally."""
    return [p for p in PROVIDERS.values() if p.is_local]


def get_vision_providers() -> list[ProviderInfo]:
    """Get providers that support vision/image input."""
    return [p for p in PROVIDERS.values() if p.supports_vision]


def get_embedding_providers() -> list[ProviderInfo]:
    """Get providers that support embeddings."""
    return [p for p in PROVIDERS.values() if p.supports_embeddings]


__all__ = [
    "ProviderType",
    "ProviderInfo",
    "PROVIDERS",
    "get_provider_info",
    "list_providers",
    "get_cloud_providers",
    "get_local_providers",
    "get_vision_providers",
    "get_embedding_providers",
]
