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


# Match a markdown code fence at the start (optional language hint) and end
# of an LLM response. Some providers (notably Qwen via OpenRouter) wrap
# their entire output in ``` even when the prompt asks for raw text. (#776)
_CODE_FENCE_OPEN = re.compile(r"\A`{3,}[a-zA-Z0-9_+\-]*\s*\n")
_CODE_FENCE_CLOSE = re.compile(r"\n`{3,}\s*\Z")


def _strip_outer_code_fences(content: Any) -> Any:
    """Strip a single outer markdown code fence from an LLM string response.

    Only strips when both an opening fence at the very start AND a closing
    fence at the very end are present — preserves stray ``` mid-content
    (e.g., a transcription that legitimately contains code samples).

    Returns non-string values unchanged so multimodal / structured-output
    responses pass through untouched.
    """
    if not isinstance(content, str):
        return content
    text = content.strip()
    open_match = _CODE_FENCE_OPEN.match(text)
    if not open_match:
        return content
    close_match = _CODE_FENCE_CLOSE.search(text)
    if not close_match:
        return content
    inner = text[open_match.end():close_match.start()]
    return inner


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
# Model aliases ($small / $large) — see #810
# =============================================================================


_MODEL_ALIASES = {"$small", "$large"}


class GuardrailViolationError(RuntimeError):
    """Raised when Apple Intelligence's on-device safety filter refuses a
    generation. The Foundation Models error surface gives us a structured
    `guardrailViolation` enum case that fm-bridge stringifies; we detect
    that string in the stderr payload and raise this typed error so
    callers can catch it specifically and route around (#838).

    Apple's safety policies are tuned for consumer use cases (Mail
    compose, image gen) — academic users hit the filter on Spanish
    vernacular literature, court records, ethnographic notes, etc. The
    answer is to fall back to the user-configured frontier model, not
    to surface the failure to the user.
    """


def resolve_model_alias(provider: str, model: str) -> tuple[str, str]:
    """Resolve $small / $large aliases against app-level settings.

    Returns the input pair unchanged when not an alias. Raises ValueError
    with an actionable message when the alias is used but the matching
    setting is unconfigured.

    Aliases let workflow presets stay portable across users with different
    provider configurations: a node can declare `provider: "$small"` and
    the runtime fills in whichever concrete provider/model the user picked
    in Settings → AI Defaults (#810).
    """
    raw = (provider or "").strip()
    if raw not in _MODEL_ALIASES:
        return (provider, model)

    from fichero.app_db import get_app_db
    db = get_app_db()
    tier = "small" if raw == "$small" else "large"
    resolved_provider = db.get_setting(f"default_{tier}_provider")
    resolved_model = db.get_setting(f"default_{tier}_model")

    if not resolved_provider or not resolved_model:
        raise ValueError(
            f"Workflow node uses {raw} but no default {tier} model is "
            f"configured. Set one in Settings → AI Defaults → "
            f"Default {tier} model."
        )
    return (resolved_provider, resolved_model)


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

    # Apple Intelligence (Foundation Models) lives outside LangChain — Swift-
    # native API requires the fm-bridge subprocess. Route before LangChain
    # tries to construct a model class for it.
    if config.provider == "apple":
        if stream:
            raise ValueError(
                "Apple Intelligence does not support streaming yet — "
                "the fm-bridge wrapper returns a single response."
            )
        return await _apple_intelligence_chat(prompt, config, system)

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
        return _strip_outer_code_fences(response.content)


async def chat_with_fallback(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    system: str | None = None,
) -> str:
    """Like chat(), but falls back to the user's $large model when Apple
    Intelligence's on-device guardrail refuses the call. (#838)

    Apple's safety filter is tuned for consumer use cases and refuses
    scholarly text containing literary profanity, drug references,
    historical slurs, court-record vocabulary, etc. Frontier cloud
    providers handle the same content with their academic-appropriate
    safety policies. The fallback keeps the local-first default
    (everything still tries Apple Intelligence first when configured)
    but escapes to the user-configured cloud provider when needed.

    Streaming is intentionally unsupported — callers that need streaming
    are using direct chat() and accept the responsibility of catching
    GuardrailViolationError themselves.

    Returns the response string. Raises the original error when fallback
    is unavailable (no $large configured) or also fails.
    """
    try:
        return await chat(prompt, config, system=system)
    except GuardrailViolationError as guardrail_exc:
        # Only Apple Intelligence raises this — try $large if configured.
        try:
            large_provider, large_model = resolve_model_alias("$large", "")
        except ValueError:
            # No $large configured — surface the original guardrail error so
            # the caller knows it was Apple's refusal, not a missing key.
            logger.warning(
                "GuardrailViolation but no $large fallback configured; "
                "set Settings → AI Defaults → Default large model to enable."
            )
            raise guardrail_exc

        fallback_config = LLMConfig(
            provider=large_provider,
            model=large_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
            api_base=config.api_base,
            timeout=config.timeout,
            extra=dict(config.extra),
        )
        logger.info(
            f"Apple Intelligence guardrail refused; retrying with "
            f"$large = {large_provider}/{large_model}"
        )
        return await chat(prompt, fallback_config, system=system)


async def _apple_intelligence_chat(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    system: str | None = None,
) -> str:
    """Bridge to FoundationModels via the bundled Swift fm-bridge binary.

    Apple Intelligence's public API is Swift-native (LanguageModelSession.
    respond(to:)) and not @objc-exposed, so pyobjc loads the classes but
    can't call their methods. The fm-bridge binary (compiled from
    fichero-engine/bin/fm-bridge/main.swift) is a tiny CLI that takes a JSON
    request on stdin and emits a JSON response on stdout.

    Build with:
        swiftc -O -parse-as-library -o fichero-engine/bin/fm-bridge/fm-bridge \\
            fichero-engine/bin/fm-bridge/main.swift
    """
    import json as _json
    from pathlib import Path
    import asyncio

    # Flatten messages list into a single prompt + optional system
    # instructions. Apple Intelligence's session API doesn't model OpenAI's
    # multi-turn message list directly; we collapse to user prompt + system.
    if isinstance(prompt, str):
        user_text = prompt
        instructions = system or ""
    else:
        instructions = system or ""
        user_parts: list[str] = []
        for msg in prompt:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Multimodal content list — flatten the text parts only;
                # Apple Intelligence is text-only (no vision in this bridge).
                content = " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                )
            if role == "system" and not instructions:
                instructions = str(content)
            else:
                user_parts.append(str(content))
        user_text = "\n\n".join(user_parts)

    # Locate fm-bridge. Lives in src/fichero/resources/bin/fm-bridge as
    # part of the Python package — briefcase auto-bundles anything under
    # src/fichero/. Dev path (repo/fichero-engine/bin/...) is kept as a
    # fallback for working without the resources copy.
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "resources" / "bin" / "fm-bridge",  # package data (bundled & dev)
        here.parent / "bin" / "fm-bridge" / "fm-bridge",  # earlier hot-patch path (kept)
        here.parents[3] / "bin" / "fm-bridge" / "fm-bridge",  # dev: repo/fichero-engine/bin/...
        Path("fichero-engine/bin/fm-bridge/fm-bridge").resolve(),
    ]
    binary: Path | None = next((p for p in candidates if p.is_file() and p.stat().st_mode & 0o111), None)
    if binary is None:
        raise RuntimeError(
            "fm-bridge binary not found. Build with: "
            "swiftc -O -parse-as-library -o fichero-engine/bin/fm-bridge/fm-bridge "
            "fichero-engine/bin/fm-bridge/main.swift"
        )

    # Pass temperature + max_tokens through to fm-bridge → Apple's
    # GenerationOptions. Lets callers pin temperature=0.0 for
    # deterministic structured tasks (extract_all) and longer
    # max_tokens for narrative synthesis (catalogue narrative). Unset
    # values omitted so fm-bridge keeps Foundation Models defaults
    # rather than overriding with our LLMConfig defaults.
    request_dict: dict[str, Any] = {
        "prompt": user_text,
        "instructions": instructions,
    }
    # LLMConfig.temperature defaults to 0.7; only forward when explicit.
    if config.temperature is not None:
        request_dict["temperature"] = config.temperature
    if config.max_tokens is not None and config.max_tokens > 0:
        request_dict["max_tokens"] = config.max_tokens
    request_payload = _json.dumps(request_dict).encode()

    proc = await asyncio.create_subprocess_exec(
        str(binary),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(request_payload)

    if proc.returncode != 0:
        _raise_from_bridge_stderr(stderr_bytes, proc.returncode)

    try:
        result = _json.loads(stdout_bytes.decode())
    except _json.JSONDecodeError as exc:
        raise RuntimeError(
            f"fm-bridge stdout was not valid JSON: {stdout_bytes!r}"
        ) from exc

    return result.get("response", "")


def _raise_from_bridge_stderr(stderr_bytes: bytes, returncode: int) -> None:
    """Translate fm-bridge's structured error JSON (`kind` + `error`) into
    a Python exception. The bridge emits a typed `kind` per #843:
    guardrail / refusal / decoding / context_overflow / rate_limited /
    concurrent / unsupported_guide / unsupported_language / assets / json /
    schema / generation. We map the safety-related kinds to
    GuardrailViolationError so chat_with_fallback / chat_structured_with_fallback
    can route around them (#838); other kinds become RuntimeError carrying
    the kind for upstream classification.

    Falls back to RuntimeError when stderr isn't a JSON payload (e.g.
    bridge crashed before it could emit one).
    """
    import json as _json

    stderr_text = stderr_bytes.decode()
    try:
        err = _json.loads(stderr_text)
    except _json.JSONDecodeError:
        raise RuntimeError(
            f"fm-bridge exited {returncode}: {stderr_text}"
        )

    kind = err.get("kind", "error")
    message = err.get("error", stderr_text)

    if kind in {"guardrail", "refusal"}:
        # Both denote model-side refusal; treat as guardrail so the
        # existing $large fallback kicks in. (`refusal` is structured-
        # only and carries an explanation; `guardrail` is the safety
        # filter outside the model.)
        raise GuardrailViolationError(
            f"Apple Intelligence ({kind}): {message}"
        )

    raise RuntimeError(f"Apple Intelligence ({kind}): {message}")


async def _apple_vision_dispatch(
    images: list[str],
    prompt: str,
    config: LLMConfig,
) -> str:
    """Apple provider's vision dispatch — picks the right on-device API
    based on config.model, since FoundationModels' Swift LLM (apple-
    intelligence) is text-only on macOS 26 and a separate Vision
    framework handles OCR (apple-vision).

    Routes:
      * model='apple-vision' (or empty / 'default') → on-device OCR via
        the existing apple_vision_ocr() in vision_base. Multi-image
        OCR concatenates results with page separators.
      * model='apple-intelligence' → ValueError. FoundationModels can't
        consume images yet; user should pick apple-vision for OCR or
        switch provider for general image understanding.
      * model='apple-speech' → ValueError. Wrong modality (audio).

    Note: ignores `prompt` for OCR — Apple Vision's API is not prompt-
    driven (it's a recognition pass, not a generative model). Caller's
    prompt becomes effectively unused, which is fine for the catalogue
    workflow's vision tools that just want text out.
    """
    from fichero.workflows.tools.vision_base import apple_vision_ocr
    import asyncio
    import base64
    import tempfile
    import os
    from urllib.parse import urlparse

    model_id = (config.model or "").lower().strip()
    # Treat empty / 'default' as apple-vision since OCR is the only
    # dispatchable on-device vision route today.
    if model_id in ("", "default", "apple-vision"):
        pass  # fall through to OCR
    elif model_id == "apple-intelligence":
        raise ValueError(
            "Apple Intelligence (Foundation Models) is text-only on macOS 26 "
            "and cannot process images. Pick model='apple-vision' for OCR, or "
            "switch provider for general image understanding."
        )
    elif model_id == "apple-speech":
        raise ValueError(
            "Apple Speech is for audio transcription, not vision. "
            "Pick model='apple-vision' for image OCR."
        )
    else:
        raise ValueError(
            f"Unknown Apple model for vision: {config.model!r}. "
            "Supported: apple-vision."
        )

    if not images:
        return ""

    # Apple Vision's Quartz-based image loader takes a file path. Most
    # workflow callers pass base64 data URIs; write each to a temp file
    # and clean up after. apple_vision_ocr is sync, so dispatch via
    # asyncio.to_thread to keep the async caller non-blocking.
    page_texts: list[str] = []
    cleanup_paths: list[str] = []
    try:
        for index, img in enumerate(images):
            file_path: str
            cleanup_this = False
            if img.startswith("data:"):
                # data URI: data:image/jpeg;base64,XXXX
                _header, _, b64 = img.partition(",")
                # Infer extension from the mime type for CoreGraphics codec
                mime = _header.split(";")[0].removeprefix("data:") or "image/png"
                ext = "." + (mime.split("/")[1] if "/" in mime else "png")
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                try:
                    tmp.write(base64.b64decode(b64))
                finally:
                    tmp.close()
                file_path = tmp.name
                cleanup_this = True
            elif urlparse(img).scheme in ("file", ""):
                file_path = urlparse(img).path or img
            else:
                raise ValueError(
                    f"Apple Vision can't fetch remote URLs ({img[:40]}...). "
                    "Pass a local path or data: URI."
                )
            if cleanup_this:
                cleanup_paths.append(file_path)
            text = await asyncio.to_thread(apple_vision_ocr, file_path, "en")
            if text:
                if len(images) > 1:
                    page_texts.append(f"--- Image {index + 1} ---")
                page_texts.append(text)
        return "\n\n".join(page_texts)
    finally:
        for p in cleanup_paths:
            try:
                os.remove(p)
            except OSError:
                pass


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

    # Apple provider unified dispatch — Apple has no LangChain integration,
    # so we route by model BEFORE falling through to LangChain. Three Apple
    # models exist (per the bundled provider seed):
    #   * apple-vision        → on-device OCR via Vision framework
    #   * apple-speech        → audio-only (rejected here, vision call)
    #   * apple-intelligence  → FoundationModels LLM, text-only on macOS 26
    # This mirrors chat()'s apple branch — without it, every workflow node
    # that does vision-with-provider=apple bombed with "Unknown LLM
    # provider: 'apple'" (Daniel's regression after consolidating to a
    # single Catalogue preset that uses provider=apple by default).
    if config.provider == "apple":
        return await _apple_vision_dispatch(images, prompt, config)

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
    return _strip_outer_code_fences(response.content)


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


async def chat_structured(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
) -> BaseModel:
    """Provider-routed structured output. Returns a Pydantic instance.

    Two backends, both grammar-constrained at the decode level so the
    "LLM emitted truncated JSON, parser threw" failure mode physically
    cannot occur (#799/#819):

    - **Apple Intelligence** (provider="apple"): fm-bridge structured
      mode. Schema converted from Pydantic via `_pydantic_to_apple_schema`
      and shipped to FoundationModels.DynamicGenerationSchema. Decoder
      is constrained at the token level — invalid JSON cannot be emitted.

    - **Everything else**: LangChain's `with_structured_output(schema)`
      which routes to the provider's native structured-output API
      (OpenAI / OpenRouter `response_format=json_schema`, Anthropic /
      Mistral tool-calling, Gemini function-calling). Same guarantee.

    `system` is forwarded as instructions on Apple Intelligence and as
    a SystemMessage on LangChain models.

    `include_schema_in_prompt` is Apple-only (FoundationModels parameter):
    when our system instructions already describe the shape, set False to
    avoid the auto-injected schema dump and save prompt tokens in the
    on-device 4K window. None = use FoundationModels' default (True).
    Ignored on LangChain providers since they don't have an equivalent.

    Replaces the old prompt-engineer-then-json.loads() pattern in
    extract_all + cleanup, where the model emitted free-form text we
    asked nicely to be JSON, then parsed and prayed.
    """
    if config.provider == "apple":
        return await _apple_intelligence_structured(
            prompt, schema, config, system,
            include_schema_in_prompt=include_schema_in_prompt,
        )

    from langchain_core.messages import HumanMessage, SystemMessage

    model = get_langchain_model(config)

    # Prefer tool/function-calling over strict JSON-Schema mode. The
    # `json_schema` default in LangChain only works on providers that
    # implement OpenAI-style strict structured output (notably native
    # OpenAI). OpenRouter proxies to many backends — some do, some
    # don't — and strict mode silently degrades on the rest. Tool-
    # calling is the lowest-common-denominator that every major provider
    # and OpenRouter-routed model supports, so it's the safest default.
    structured_model = model.with_structured_output(
        schema, method="function_calling"
    )

    messages: list[Any] = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    result = await structured_model.ainvoke(messages)
    return result


async def chat_structured_with_fallback(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
) -> BaseModel:
    """Like chat_structured(), but falls back to the user's $large model
    when Apple Intelligence's on-device guardrail refuses the call (#838).

    Mirrors chat_with_fallback() for the structured-output path. Lets
    extract_all and cleanup keep the local-first default while still
    completing on documents Apple Intelligence's safety filter rejects.
    """
    try:
        return await chat_structured(
            prompt, schema, config, system=system,
            include_schema_in_prompt=include_schema_in_prompt,
        )
    except GuardrailViolationError as guardrail_exc:
        from fichero.providers import resolve_default_provider
        try:
            large_config = resolve_default_provider(role="large")
        except Exception:
            raise guardrail_exc

        if large_config.provider == config.provider and large_config.model == config.model:
            raise guardrail_exc

        logger.warning(
            f"Apple Intelligence guardrail refused structured call; retrying "
            f"with {large_config.provider}/{large_config.model}"
        )
        # The fallback provider is LangChain-based, so the Apple-only
        # include_schema_in_prompt parameter is ignored here.
        return await chat_structured(prompt, schema, large_config, system=system)


def _pydantic_to_apple_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic class into the schema-tree shape fm-bridge
    builds DynamicGenerationSchema from. Inlines `$ref` definitions
    against `$defs` so the bridge doesn't need cross-file references.

    Pydantic emits JSON Schema; Apple's DynamicGenerationSchema is a
    similar tree with object/array/primitive shape but a different
    property layout (list of `{name, schema, optional}` instead of a
    `properties` dict + separate `required` list). This helper bridges
    the two without depending on any OpenAPI-style JSON-Schema library.
    """
    full = model.model_json_schema()
    defs = full.get("$defs", {})

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        # Resolve a single $ref against $defs; deep-copy so callers can
        # mutate without polluting the shared definition.
        if "$ref" in node:
            ref = node["$ref"]
            assert ref.startswith("#/$defs/"), f"unexpected $ref: {ref}"
            name = ref.split("/")[-1]
            return resolve({**defs[name]})
        return node

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        node = resolve(node)
        # anyOf with `null` is Pydantic's Optional[T] form — strip the
        # null branch and recurse on the remaining type.
        if "anyOf" in node and not node.get("type"):
            non_null = [b for b in node["anyOf"] if b.get("type") != "null"]
            if len(non_null) == 1:
                return convert(non_null[0])

        type_ = node.get("type", "object")
        out: dict[str, Any] = {"type": type_}
        if title := node.get("title"):
            out["name"] = title
        if desc := node.get("description"):
            out["description"] = desc

        if type_ == "object":
            required = set(node.get("required", []))
            properties = node.get("properties", {})
            props_out: list[dict[str, Any]] = []
            for pname, psub in properties.items():
                psub_resolved = resolve(psub)
                pschema = convert(psub_resolved)
                pdesc = psub.get("description") or psub_resolved.get("description")
                entry: dict[str, Any] = {"name": pname, "schema": pschema}
                if pdesc:
                    entry["description"] = pdesc
                if pname not in required:
                    entry["optional"] = True
                props_out.append(entry)
            out["properties"] = props_out
        elif type_ == "array":
            items = resolve(node.get("items", {"type": "string"}))
            out["items"] = convert(items)
            if (mn := node.get("minItems")) is not None:
                out["minimum_elements"] = mn
            if (mx := node.get("maxItems")) is not None:
                out["maximum_elements"] = mx
        # Primitives (string/integer/number/boolean): nothing extra.

        return out

    return convert(full)


async def _apple_intelligence_structured(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
) -> BaseModel:
    """Subprocess fm-bridge in structured mode and return a Pydantic
    instance built from the grammar-constrained JSON output. Mirrors
    `_apple_intelligence_chat`'s subprocess pattern but adds `schema`
    + optional `include_schema_in_prompt` to the request and parses
    `response_json` from the bridge.

    `include_schema_in_prompt`: see Apple's docs for `respond(to:schema:)`.
    Default is FoundationModels' default (`True`) — the schema is
    auto-injected into the prompt to bias the model. Set `False` when
    our system instructions already describe the shape, saving prompt
    tokens in the on-device 4K window.
    """
    import json as _json
    from pathlib import Path

    here = Path(__file__).resolve()
    candidates = [
        here.parent / "resources" / "bin" / "fm-bridge",
        here.parent / "bin" / "fm-bridge" / "fm-bridge",
        here.parents[3] / "bin" / "fm-bridge" / "fm-bridge",
        Path("fichero-engine/bin/fm-bridge/fm-bridge").resolve(),
    ]
    binary: Path | None = next(
        (p for p in candidates if p.is_file() and p.stat().st_mode & 0o111),
        None,
    )
    if binary is None:
        raise RuntimeError(
            "fm-bridge binary not found; run "
            "fichero-engine/bin/fm-bridge/build.sh and copy to "
            "src/fichero/resources/bin/"
        )

    request: dict[str, Any] = {
        "prompt": prompt,
        "instructions": system or "",
        "schema": _pydantic_to_apple_schema(schema),
    }
    if include_schema_in_prompt is not None:
        request["include_schema_in_prompt"] = include_schema_in_prompt
    if config.temperature is not None:
        request["temperature"] = config.temperature
    if config.max_tokens is not None and config.max_tokens > 0:
        request["max_tokens"] = config.max_tokens
    payload = _json.dumps(request).encode()

    proc = await asyncio.create_subprocess_exec(
        str(binary),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(payload)

    if proc.returncode != 0:
        _raise_from_bridge_stderr(stderr_bytes, proc.returncode)

    bridge_result = _json.loads(stdout_bytes.decode())
    response_json = bridge_result.get("response_json", "")
    # Parse the grammar-constrained JSON (always valid by construction)
    # into the Pydantic class. Validation here is belt-and-suspenders —
    # the schema constraint should already guarantee shape, but a typed
    # parse gives downstream code a real Pydantic instance to consume.
    return schema.model_validate_json(response_json)


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

    # Common parameters. max_retries=10 (LangChain default is 6) bumps
    # the auto-retry budget on transient transport failures (network
    # blips, 429 rate-limit, 5xx). Exponential backoff with jitter
    # makes ~10 attempts cheap when most retries land in <5s, and means
    # the qwen3.5/OpenRouter hiccups Daniel hit earlier (parallel
    # extract_all chunks failing on transient provider load) recover
    # silently rather than aborting the whole workflow (#844).
    common_params = {
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "max_retries": 10,
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
    elif provider == "apple":
        # Apple has no LangChain integration (FoundationModels is Swift-only,
        # not @objc-exposed). Workflow tools should call chat() / vision()
        # which route to fm-bridge / apple_vision_ocr respectively. This
        # branch only fires from direct get_langchain_model callers
        # (multi_agent, agent) — surface a clear error so the caller knows
        # the path doesn't exist yet.
        raise NotImplementedError(
            "Apple Intelligence has no LangChain ChatModel wrapper yet. "
            "Use llm.chat() / llm.vision() (which route to fm-bridge / "
            "apple_vision_ocr) or pick a different provider for "
            "multi_agent / agent tools."
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
            f"xai, perplexity, fireworks, azure, bedrock, huggingface, apple"
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
