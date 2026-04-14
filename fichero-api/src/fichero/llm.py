"""
Fichero Unified LLM Interface

Shared interface for all LLM operations using LangChain.
LiteLLM is ONLY used for model discovery and pricing info.

Capabilities:
- Chat: Conversational AI with streaming support (via LangChain)
- Vision: Image understanding (GPT-4o, Claude 3, Gemini, etc.)
- Embeddings: Vector embeddings for semantic search
- Tools: Function/tool calling
- Structured Output: JSON mode, schema validation

Usage:
    from fichero.llm import chat, vision, embed, LLMConfig

    # Simple chat
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    response = await chat("Hello!", config)

    # Vision
    response = await vision(
        images=["https://example.com/image.jpg"],
        prompt="Describe this image",
        config=config
    )

    # Embeddings
    vectors = embed(["text to embed"])

    # Streaming
    async for chunk in chat("Hello!", config, stream=True):
        print(chunk, end="")
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from pydantic import BaseModel

from fichero.llm_models import (  # noqa: F401 (re-exported)
    estimate_cost,
    get_model_cost,
    get_model_info,
    list_models_for_provider,
)
from fichero.llm_embeddings import (  # noqa: F401 (re-exported)
    _get_langchain_embeddings,
    aembed,
    embed,
)

logger = logging.getLogger(__name__)

# Lazy import litellm to avoid import overhead
_litellm = None


def _get_litellm():
    """Lazy-load litellm module."""
    global _litellm
    if _litellm is None:
        import litellm

        _litellm = litellm
        # Reduce litellm logging noise
        litellm.suppress_debug_info = True
    return _litellm


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class LLMConfig:
    """Configuration for LLM calls."""

    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    api_key: str | None = None
    api_base: str | None = None
    timeout: int = 60
    extra: dict[str, Any] = field(default_factory=dict)

    def get_model_name(self) -> str:
        """Get LiteLLM-format model name (provider/model)."""
        # Some providers need special handling
        if self.provider in ("ollama", "lmstudio"):
            return f"ollama/{self.model}"
        if self.provider == "huggingface":
            return f"huggingface/{self.model}"
        return f"{self.provider}/{self.model}"


# =============================================================================
# API Key Resolution
# =============================================================================


def get_api_key(provider: str) -> str | None:
    """Get API key for a provider.

    Checks in order:
    1. macOS Keychain (if available)
    2. Environment variable

    Args:
        provider: Provider type name (e.g., "openai")

    Returns:
        API key or None if not found
    """
    from fichero.providers import get_provider_info

    # Try keychain first
    try:
        from fichero.keychain import get_api_key as _keychain_get

        key = _keychain_get(provider)
        if key:
            return key
    except ImportError:
        pass

    # Fall back to environment variable
    info = get_provider_info(provider)
    if info and info.api_key_env:
        return os.environ.get(info.api_key_env)

    return None


def _resolve_api_key(config: LLMConfig) -> str | None:
    """Resolve API key from config or lookup."""
    if config.api_key:
        return config.api_key
    return get_api_key(config.provider)


# =============================================================================
# Chat
# =============================================================================


async def chat(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    stream: bool = False,
    system: str | None = None,
) -> str | AsyncIterator[str]:
    """Send a chat message using LangChain.

    Args:
        prompt: User message (string) or full messages list
        config: LLM configuration
        stream: If True, return async generator of chunks
        system: Optional system message

    Returns:
        Response string, or async generator if streaming
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # Get LangChain model
    model = get_langchain_model(config)

    # Build messages
    if isinstance(prompt, str):
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
    else:
        # Convert dict messages to LangChain format
        messages = _convert_to_langchain_messages(prompt)

    if stream:
        return _stream_chat_langchain(model, messages)
    else:
        response = await model.ainvoke(messages)
        return response.content


async def _stream_chat_langchain(model, messages: list) -> AsyncIterator[str]:
    """Stream chat response using LangChain."""
    async for chunk in model.astream(messages):
        if chunk.content:
            yield chunk.content


def _convert_to_langchain_messages(messages: list[dict]) -> list:
    """Convert OpenAI-format messages to LangChain message objects."""
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        else:  # user or default
            result.append(HumanMessage(content=content))

    return result


# =============================================================================
# Vision
# =============================================================================


async def vision(
    images: list[str],
    prompt: str,
    config: LLMConfig,
) -> str:
    """Analyze images with a vision model using LangChain.

    Args:
        images: List of image URLs or base64 data URIs
        prompt: Analysis prompt
        config: LLM configuration (must use vision-capable model)

    Returns:
        Analysis text
    """
    from langchain_core.messages import HumanMessage

    # Get LangChain model
    model = get_langchain_model(config)

    # Build multimodal message content (LangChain format)
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": img}})

    # Create multimodal message
    message = HumanMessage(content=content)

    # Call model
    response = await model.ainvoke([message])
    return response.content


# =============================================================================
# Thinking Models (Reasoning/Chain-of-Thought)
# =============================================================================


def parse_thinking_response(text: str) -> tuple[str, str | None]:
    """Parse thinking model response that may contain reasoning traces.

    Many reasoning models (e.g., NuMarkdown, DeepSeek-Reasoner) output:
    <think>reasoning process here</think><answer>final result</answer>

    Args:
        text: Full model response

    Returns:
        (answer, thinking) tuple where:
        - answer: The actual result (from <answer> tag or full text if no tags)
        - thinking: The reasoning process (from <think> tag or None)

    Examples:
        >>> parse_thinking_response("<think>Let me analyze...</think><answer>42</answer>")
        ('42', 'Let me analyze...')

        >>> parse_thinking_response("Simple answer without thinking")
        ('Simple answer without thinking', None)
    """

    # Try to extract thinking and answer tags
    think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    answer_match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)

    thinking = think_match.group(1).strip() if think_match else None
    answer = answer_match.group(1).strip() if answer_match else text.strip()

    return answer, thinking


def is_thinking_model(model: str) -> bool:
    """Check if a model is known to use thinking/reasoning traces.

    Args:
        model: Model identifier (e.g., "numind/NuMarkdown-8B-Thinking")

    Returns:
        True if model likely outputs thinking traces

    Examples:
        >>> is_thinking_model("numind/NuMarkdown-8B-Thinking")
        True
        >>> is_thinking_model("meta-llama/Llama-3.2-11B-Vision")
        False
    """
    model_lower = model.lower()

    # Check for explicit thinking/reasoning keywords
    # Match as whole words or with hyphens
    keywords = ["thinking", "reasoning", "reasoner"]
    for keyword in keywords:
        # Match with hyphens (e.g., "model-thinking") or as standalone word
        if f"-{keyword}" in model_lower or f"_{keyword}" in model_lower:
            return True
        # Match as word boundary (e.g., "reasoner-model")
        if (
            keyword in model_lower.split("/")[1]
            if "/" in model_lower
            else keyword in model_lower
        ):
            # Check it's a word, not part of another word (e.g., "rethinking")

            if re.search(rf"\b{keyword}\b", model_lower):
                return True

    # Known thinking model families
    thinking_prefixes = [
        "numind/numarkdown",  # NuMarkdown series
        "deepseek/deepseek-reasoner",  # DeepSeek reasoner
        "qwen/qwq",  # Qwen with Questioning
    ]

    return any(model_lower.startswith(prefix) for prefix in thinking_prefixes)


async def vision_inference_api(
    images: list[str],
    prompt: str,
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = 60,
) -> str:
    """Call Hugging Face Inference API directly for vision models.

    Uses the native Inference API instead of the router. This enables:
    - Access to more models (not all are on the router)
    - Thinking/reasoning models that aren't chat-compatible
    - Direct model inference without OpenAI wrapper

    Args:
        images: List of base64 data URIs (e.g., "data:image/jpeg;base64,...")
        prompt: Text prompt for the vision task
        model: Hugging Face model ID (e.g., "numind/NuMarkdown-8B-Thinking")
        api_key: Hugging Face API key
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens to generate
        timeout: Request timeout in seconds

    Returns:
        Model response text (may contain <think>/<answer> tags)

    Raises:
        ValueError: If image format is invalid or model not found
        TimeoutError: If request exceeds timeout
        RuntimeError: For API errors (rate limits, model loading, etc.)

    Example:
        >>> response = await vision_inference_api(
        ...     images=["data:image/jpeg;base64,/9j/4AAQ..."],
        ...     prompt="Convert this document to markdown",
        ...     model="numind/NuMarkdown-8B-Thinking",
        ...     api_key="hf_...",
        ... )
    """
    import aiohttp

    url = f"https://api-inference.huggingface.co/models/{model}"

    # Extract base64 data from first image (single image for now)
    if not images:
        raise ValueError("At least one image required")

    image_data = images[0]
    if image_data.startswith("data:image"):
        # Extract base64 part from data URI
        _, base64_data = image_data.split(",", 1)
    else:
        base64_data = image_data

    # Decode to bytes
    try:
        image_bytes = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Invalid base64 image data: {e}")

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # Hugging Face Inference API format for vision models
    # Uses multimodal inputs with text and image

    logger.info(f"HF Inference API call: {model} ({len(image_bytes)} bytes)")

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            # For vision models, we need to send the image as part of the request
            # The exact format depends on the model, but for most vision models:
            # - Use multipart/form-data with image and text
            data = aiohttp.FormData()
            data.add_field("inputs", prompt)
            data.add_field("file", image_bytes, content_type="image/jpeg")

            async with session.post(url, headers=headers, data=data) as response:
                if response.status == 200:
                    result = await response.json()

                    # Response format varies by model type
                    # Text generation models return: [{"generated_text": "..."}]
                    # Some vision models return: {"text": "..."}
                    if isinstance(result, list) and result:
                        text = result[0].get("generated_text", "")
                    elif isinstance(result, dict):
                        text = result.get("text", result.get("generated_text", ""))
                    else:
                        text = str(result)

                    logger.info(f"HF API response: {len(text)} chars")
                    return text

                elif response.status == 503:
                    # Model is loading
                    error_data = await response.json()
                    estimated_time = error_data.get("estimated_time", 20)
                    raise RuntimeError(
                        f"Model is loading. Estimated time: {estimated_time}s. "
                        "Please try again in a moment."
                    )

                elif response.status == 413:
                    # Request too large (image too big)
                    raise ValueError(
                        f"Image too large ({len(image_bytes)} bytes). "
                        "Try reducing the max_image_dimension setting."
                    )

                elif response.status == 429:
                    # Rate limit exceeded
                    raise RuntimeError(
                        "Hugging Face API rate limit exceeded. "
                        "Please wait a moment and try again, or upgrade your API plan."
                    )

                elif response.status == 400:
                    # Bad request (often means model doesn't support this input)
                    error_data = await response.json()
                    error_msg = error_data.get("error", "Unknown error")
                    raise ValueError(f"Model API error: {error_msg}")

                else:
                    # Other error
                    error_text = await response.text()
                    raise RuntimeError(
                        f"HF Inference API error (status {response.status}): {error_text}"
                    )

    except aiohttp.ClientError as e:
        raise RuntimeError(f"Network error calling HF Inference API: {e}")
    except asyncio.TimeoutError:
        raise TimeoutError(f"HF Inference API request timed out after {timeout}s")


# =============================================================================
# Tools / Function Calling
# =============================================================================


async def chat_with_tools(
    prompt: str | list[dict[str, Any]],
    tools: list[dict[str, Any]],
    config: LLMConfig,
) -> dict[str, Any]:
    """Chat with tool/function calling support using LangChain.

    Args:
        prompt: User message or messages list
        tools: OpenAI-format tool definitions
        config: LLM configuration

    Returns:
        Dict with 'content' and 'tool_calls' keys
    """
    from langchain_core.messages import HumanMessage

    # Get LangChain model
    model = get_langchain_model(config)

    # Bind tools to model
    model_with_tools = model.bind_tools(tools)

    # Build messages
    if isinstance(prompt, str):
        messages = [HumanMessage(content=prompt)]
    else:
        messages = _convert_to_langchain_messages(prompt)

    # Call model with tools
    response = await model_with_tools.ainvoke(messages)

    # Extract tool calls from response
    tool_calls = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_calls = response.tool_calls

    return {
        "content": response.content,
        "tool_calls": tool_calls,
    }


# =============================================================================
# Structured Output
# =============================================================================


async def structured_output(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
) -> BaseModel:
    """Get structured output matching a Pydantic schema using LangChain.

    Args:
        prompt: User prompt
        schema: Pydantic model class defining expected structure
        config: LLM configuration

    Returns:
        Instance of the schema class
    """
    from langchain_core.messages import HumanMessage

    # Get LangChain model
    model = get_langchain_model(config)

    # Use LangChain's with_structured_output for clean schema binding
    structured_model = model.with_structured_output(schema)

    # Call model
    result = await structured_model.ainvoke([HumanMessage(content=prompt)])

    return result


# =============================================================================
# LangChain Integration
# =============================================================================


def get_langchain_model(config: LLMConfig) -> Any:
    """Create a LangChain ChatModel from Fichero LLMConfig.

    This enables integration with LangChain/LangGraph tools like create_react_agent.

    Args:
        config: Fichero LLM configuration

    Returns:
        LangChain ChatModel instance (ChatOpenAI, ChatAnthropic, etc.)
    """
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Map provider to LangChain class
    provider = config.provider.lower()
    model_name = config.model

    # Resolve API key
    api_key = _resolve_api_key(config)

    # Common parameters
    common_params = {
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
    }

    # Create provider-specific model
    if provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base,
            **common_params,
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
            **common_params,
        )
    elif provider == "google":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            **common_params,
        )
    elif provider == "mistral":
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=model_name,
            api_key=api_key,
            **common_params,
        )
    elif provider == "cohere":
        from langchain_cohere import ChatCohere

        return ChatCohere(
            model=model_name,
            cohere_api_key=api_key,
            **common_params,
        )
    elif provider == "ollama":
        # Use ChatOpenAI with ollama base URL (OpenAI-compatible)
        return ChatOpenAI(
            model=model_name,
            api_key="ollama",  # Ollama doesn't need real key
            base_url=config.api_base or "http://localhost:11434/v1",
            **common_params,
        )
    elif provider == "lmstudio":
        # Use ChatOpenAI with LM Studio base URL (OpenAI-compatible)
        return ChatOpenAI(
            model=model_name,
            api_key="lmstudio",  # LM Studio doesn't need real key
            base_url=config.api_base or "http://localhost:1234/v1",
            **common_params,
        )
    elif provider == "groq":
        # Groq uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.groq.com/openai/v1",
            **common_params,
        )
    elif provider == "together":
        # Together uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.together.xyz/v1",
            **common_params,
        )
    elif provider == "deepseek":
        # DeepSeek uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.deepseek.com/v1",
            **common_params,
        )
    elif provider == "openrouter":
        # OpenRouter uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://openrouter.ai/api/v1",
            **common_params,
        )
    elif provider == "dashscope":
        # Alibaba DashScope uses OpenAI-compatible API
        # Default to international endpoint; China users can override via api_base
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base
            or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            **common_params,
        )
    elif provider == "xai":
        # xAI (Grok) uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.x.ai/v1",
            **common_params,
        )
    elif provider == "perplexity":
        # Perplexity uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.perplexity.ai",
            **common_params,
        )
    elif provider == "fireworks":
        # Fireworks uses OpenAI-compatible API
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://api.fireworks.ai/inference/v1",
            **common_params,
        )
    elif provider == "azure":
        # Azure OpenAI has special handling
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            model=model_name,
            api_key=api_key,
            azure_endpoint=config.api_base,
            api_version=config.extra.get("api_version", "2024-02-01"),
            **common_params,
        )
    elif provider == "bedrock":
        # AWS Bedrock
        from langchain_aws import ChatBedrock

        return ChatBedrock(
            model_id=model_name,
            region_name=config.extra.get("region", "us-east-1"),
            **common_params,
        )
    elif provider == "huggingface":
        # Hugging Face Inference API (OpenAI-compatible)
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=config.api_base or "https://router.huggingface.co/v1",
            **common_params,
        )
    else:
        # FAIL if provider is empty or unknown - don't silently default
        if not provider:
            raise ValueError(
                "LLM provider not configured. Please set a provider on the workflow or node."
            )
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported providers: openai, anthropic, google, mistral, cohere, "
            f"ollama, lmstudio, groq, together, deepseek, openrouter, dashscope, "
            f"xai, perplexity, fireworks, azure, bedrock, huggingface"
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Config
    "LLMConfig",
    # Chat
    "chat",
    # Vision
    "vision",
    # Embeddings
    "embed",
    "aembed",
    # Tools
    "chat_with_tools",
    # Structured
    "structured_output",
    # Model info
    "get_model_info",
    "get_model_cost",
    "estimate_cost",
    "list_models_for_provider",
    # Key resolution
    "get_api_key",
    # LangChain
    "get_langchain_model",
]
