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
    from fichero_server.llm import chat, vision, embed, LLMConfig

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
import contextlib
import contextvars
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
import threading
import weakref
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import AsyncIterator, Any, Literal as _Literal

from pydantic import BaseModel

from fichero_server.llm.model_types import (  # noqa: F401 (re-exported)
    estimate_cost,
    get_model_cost,
    get_model_info,
    list_models_for_provider,
)
from fichero_server.llm.embeddings import (  # noqa: F401 (re-exported)
    _get_langchain_embeddings,
    aembed,
    embed,
)

logger = logging.getLogger(__name__)

_FM_BRIDGE_MISSING_MESSAGE = (
    "fm-bridge binary not found. Build it with "
    "fichero-server/bin/fm-bridge/build.sh"
)


# =============================================================================
# Usage telemetry — async-context-scoped collector (#852)
# =============================================================================
# Workflow runners wrap each node's execution in `with collect_usage() as
# bucket: …` to capture every LLM call's token count. Without an active
# collector, calls just log to INFO as today. The contextvars-based
# bucket survives task switches inside the with-block (asyncio Tasks
# inherit the current context) so a fan-out node still sees its
# children's usage.

_usage_collector: contextvars.ContextVar[list[dict[str, Any]] | None] = (
    contextvars.ContextVar("fichero_llm_usage", default=None)
)

_DEFAULT_MAX_INFLIGHT_LLM = 6
_LANGCHAIN_MODEL_CACHE_SIZE = 16

_REMOTE_LLM_SEMAPHORE: asyncio.Semaphore | None = None
_REMOTE_LLM_SEMAPHORE_LIMIT: int | None = None
_REMOTE_LLM_SEMAPHORE_LOCK = threading.Lock()

_ModelCacheKey = tuple[
    str,
    str,
    float,
    int,
    int,
    str,
    str,
    str,
    str,
    str,
]
_LANGCHAIN_MODEL_CACHE: weakref.WeakKeyDictionary[
    Any, OrderedDict[_ModelCacheKey, Any]
] = weakref.WeakKeyDictionary()
_LANGCHAIN_MODEL_CACHE_NO_LOOP: OrderedDict[_ModelCacheKey, Any] = OrderedDict()
_LANGCHAIN_MODEL_CACHE_LOCK = threading.Lock()

# Process-level cache of RESOLVED provider API keys (#2545, M1 — 100k-image
# hardening). The resolved key is part of the model-cache key, so it is looked
# up BEFORE every model-cache lookup; at 100k images × N LLM nodes that is
# hundreds of thousands of synchronous Keychain round-trips. We cache the
# resolved value keyed on the exact `provider` string passed to get_api_key()
# (the only input it takes — see get_api_key). Different providers never collide
# because they get distinct dict keys. We cache None too, so a genuinely missing
# key is not re-read on every call; callers MUST clear the cache when a
# credential is created/rotated/deleted (see clear_api_key_cache).
# Ceiling: one entry per provider string seen — bounded by the provider set, so
# no eviction/TTL machinery is warranted beyond the existing lock.
_API_KEY_CACHE: dict[str, str | None] = {}
_API_KEY_CACHE_LOCK = threading.Lock()


def clear_api_key_cache(provider: str | None = None) -> None:
    """Invalidate the resolved-API-key cache.

    Call whenever a provider credential is created, updated, rotated, or
    deleted so the next resolution re-reads the Keychain/env instead of serving
    a stale key. Pass ``provider`` to clear just that entry, or omit to clear
    everything.

    TODO(#2545): hook this into the provider-key write paths that own those
    files — ``fichero/api/routes/provider_keys.py`` (``set_api_key`` /
    ``delete_api_key`` actions, ~L97/L114) and
    ``fichero/api/routes/providers.py`` (~L296/L548/L550) — so rotations bust
    the cache automatically. This lane may not edit those files (other lanes
    own them); until then those write paths must call this function.
    """
    with _API_KEY_CACHE_LOCK:
        if provider is None:
            _API_KEY_CACHE.clear()
        else:
            _API_KEY_CACHE.pop(provider, None)

    # A rotated key must also drop cached embedding clients built with the old
    # key (#2545 N1). Cheap and rare; clear all (the client cache isn't keyed
    # by provider). Lazy import avoids a circular dependency at module load.
    from fichero_server.llm.embeddings import clear_embeddings_client_cache

    clear_embeddings_client_cache()

# Content-addressed result cache for vision (and future LLM) calls (#2224).
# Keyed by SHA-256 of (provider, model, prompt, per-image content hashes).
# Caps at 1 000 entries with FIFO eviction. Thread-safe via a lock.
_LLM_RESULT_CACHE: dict[str, str] = {}
_LLM_RESULT_CACHE_LOCK = threading.Lock()
_LLM_RESULT_CACHE_MAX = 1000


def _vision_cache_key(config: "LLMConfig", prompt: str, images: list[str]) -> str:
    """Return a stable SHA-256 cache key for a vision call.

    Base64 data URIs are digested by payload only so the key stays short
    regardless of image size; URLs are used verbatim (already compact).
    """
    def _img_digest(img: str) -> str:
        if img.startswith("data:"):
            payload = img.split(",", 1)[-1]
            return hashlib.sha256(payload.encode()).hexdigest()[:16]
        return img

    key_obj = {
        "provider": config.provider,
        "model": config.model,
        "prompt": prompt,
        "images": [_img_digest(img) for img in images],
    }
    return hashlib.sha256(json.dumps(key_obj, sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def collect_usage() -> Iterator[list[dict[str, Any]]]:
    """Context manager that captures every LLM-call's usage telemetry
    while the block is active. Returns the bucket list; consumers
    (workflow node runner, batch runner, etc.) read it after the block
    exits and stuff it into the Activity record's metadata. (#852)

    Each entry is a dict with at least:
      provider, model, kind ("chat"|"structured"|"vision"),
      input_tokens, output_tokens, total_tokens, estimated (bool).

    Nested collectors stack — the inner block's bucket captures only its
    own calls; the outer block's bucket sees everything (including the
    inner's). asyncio.Task inherits the active ContextVar.
    """
    bucket: list[dict[str, Any]] = []
    token = _usage_collector.set(bucket)
    try:
        yield bucket
    finally:
        _usage_collector.reset(token)


def _record_usage(
    provider: str,
    model: str,
    kind: str,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    estimated: bool = False,
    method: str | None = None,
) -> None:
    """Push a usage entry to the active collector (if any) and log at
    INFO. Centralizes the logging shape so chat / chat_structured /
    apple_chat / apple_structured all emit identically formatted lines
    that downstream consumers can parse uniformly."""
    bucket = _usage_collector.get()
    if bucket is not None:
        entry: dict[str, Any] = {
            "provider": provider,
            "model": model,
            "kind": kind,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated": estimated,
        }
        if method is not None:
            entry["method"] = method
        bucket.append(entry)

    marker = "~" if estimated else ""
    estimated_suffix = " (estimated)" if estimated else ""
    method_suffix = f" method={method}" if method else ""
    logger.info(
        "LLM usage [%s/%s %s]: input=%s%s output=%s%s total=%s%s%s%s",
        provider, model, kind,
        marker, input_tokens,
        marker, output_tokens,
        marker, total_tokens,
        method_suffix, estimated_suffix,
    )


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
    # Reasoning effort for models that support extended thinking (#859).
    # None or "off" → no reasoning (default). "low"/"medium"/"high" →
    # enabled, with provider-specific routing in get_langchain_model:
    #   - anthropic native: thinking={'type':'enabled', 'budget_tokens':N}
    #     plus forces temperature=1 (Anthropic's API constraint)
    #   - openai (o-series): reasoning_effort kwarg directly
    #   - openrouter: extra_body={'reasoning':{'effort':...}}
    #   - apple intelligence + everything else: silently ignored
    # Wired ON only at the catalogue narrative call site for now —
    # mechanical extractors don't benefit from reasoning + would slow
    # measurably. (#872 Phase 3 step 15)
    reasoning_effort: str | None = None

    def get_model_name(self) -> str:
        """Get LiteLLM-format model name (provider/model)."""
        # Some providers need special handling
        if self.provider in ("ollama", "lmstudio"):
            return f"ollama/{self.model}"
        if self.provider == "huggingface":
            return f"huggingface/{self.model}"
        return f"{self.provider}/{self.model}"


# =============================================================================
# Model aliases ($small / $medium / $large) — see #810 / #1308
# =============================================================================


_TEXT_MODEL_ALIASES = {"$small", "$medium", "$large"}
_VISION_MODEL_ALIASES = {"$vision_small", "$vision_medium", "$vision_large"}
_MODEL_ALIASES = _TEXT_MODEL_ALIASES | _VISION_MODEL_ALIASES
_MODEL_PROFILE_PREFIXES = ("$profile:", "profile:")


def extract_model_profile_reference(value: str | None) -> str | None:
    """Extract a model profile id/name from a provider-style reference."""
    raw = (value or "").strip()
    for prefix in _MODEL_PROFILE_PREFIXES:
        if raw.startswith(prefix):
            ref = raw[len(prefix):].strip()
            return ref or None
    return None


class AppleUnavailableError(RuntimeError):
    """Base class for Apple Intelligence failures that should fall back
    to the cloud $large model. Subclasses distinguish *why* Apple can't
    serve the call — useful for telemetry, tests, and per-cause UX —
    but callers that just want fallback semantics catch this base.

    The chat_with_fallback / chat_structured_with_fallback wrappers
    catch this base and resolve $large; existing call sites that catch
    GuardrailViolationError specifically still work because that class
    inherits from this one. Adding a new "Apple can't proceed" reason
    means subclassing this and mapping the bridge `kind` in
    _raise_from_bridge_stderr — no fallback wiring changes needed (#868).
    """


class LocalModelUnavailableError(AppleUnavailableError):
    """Managed local inference failed to become healthy."""


class LocalModelRuntimeMissingError(LocalModelUnavailableError):
    """Managed local inference runtime has not been provisioned."""


class LocalModelHardwareError(LocalModelUnavailableError):
    """Managed local inference cannot run on current hardware."""


class GuardrailViolationError(AppleUnavailableError):
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


class UnsupportedLocaleError(AppleUnavailableError):
    """Raised when Apple Intelligence rejects a prompt because its
    language/locale isn't in the model's supported set. Apple's locale
    support has expanded over OS releases (15.1 = en-US only; 15.4 added
    Spanish-Spain + others; macOS 26 broader still) and within Spanish
    distinguishes es-ES from es-MX/es-CO etc. — a Spanish-LatAm prompt
    on a model that only ships es-ES still raises `unsupportedLanguageOrLocale`.

    Falls back to $large (cloud frontier model) which has no locale
    restriction. (#868)
    """


class StructuredDecodeError(AppleUnavailableError):
    """Raised when Apple Intelligence's grammar-constrained decoder fails
    to produce a valid Generable for the requested schema — symptom is
    'terminated generation early before producing valid output: Failed
    to deserialize a Generable type from model output'.

    Happens unpredictably on dense / long / unusual input where the
    constrained sampler can't find a path that satisfies the grammar
    within the available context. fm-bridge surfaces this as kind
    `decoding`, `generation`, `context_overflow`, or `schema` depending
    on which part of the pipeline gave up.

    Treating these as Apple-unavailable lets chat_structured_with_fallback
    escape to $large for the chunk, which is what we want — extract_all
    was losing ~10% of chunks (#949 / #962) because these errors became
    plain RuntimeError and the fallback path skipped them.

    `kind` carries which of the four fm-bridge kinds this was (#1027).
    They want different handling: `decoding` / `generation` are often
    transient (the stochastic sampler missed a valid path) and worth one
    on-device retry; `context_overflow` / `schema` will fail identically
    on a retry of the same chunk + schema, so they go straight to the
    paid fallback.
    """

    # fm-bridge kinds worth retrying once on-device before paying for
    # the cloud fallback — see chat_structured_with_fallback.
    RETRYABLE_KINDS = frozenset({"decoding", "generation"})

    def __init__(self, message: str = "", kind: str | None = None):
        super().__init__(message)
        self.kind = kind


class ProviderQuotaError(RuntimeError):
    """Raised when a remote provider reports quota / limit exhaustion."""

    def __init__(
        self,
        provider: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        self.model = model
        super().__init__(
            "Provider "
            f"{provider} quota/limit hit — set a different $large provider in Settings"
        )


class LocalOnlyViolationError(RuntimeError):
    """Raised when local-only mode would otherwise call a remote provider."""

    def __init__(self, provider: str, *, model: str | None = None, kind: str = "llm"):
        self.provider = provider
        self.model = model
        self.kind = kind
        model_label = f"/{model}" if model else ""
        super().__init__(
            "Local-only AI mode is enabled; refusing "
            f"{kind} call to remote provider {provider}{model_label}. "
            "Choose an on-device/local provider or disable FICHERO_LOCAL_ONLY."
        )


class LLMBatchItemError(RuntimeError):
    """One item inside a batched LLM call failed."""

    def __init__(
        self,
        index: int,
        *,
        provider: str,
        model: str,
        kind: str,
        cause: BaseException,
    ) -> None:
        self.index = index
        self.provider = provider
        self.model = model
        self.kind = kind
        self.cause = cause
        super().__init__(
            f"{kind} batch item {index} failed for {provider}/{model}: "
            f"{type(cause).__name__}: {cause}"
        )


_PROVIDER_QUOTA_HITS: set[str] = set()
_PROVIDER_QUOTA_HITS_LOCK = threading.Lock()


def _log_provider_quota_hit(
    provider: str,
    model: str | None = None,
    detail: str | None = None,
) -> None:
    """Log a provider quota hit once per provider/model for the process."""
    provider_key = (provider or "unknown").strip().lower() or "unknown"
    model_key = (model or "").strip().lower() or "*"
    quota_key = f"{provider_key}/{model_key}"
    with _PROVIDER_QUOTA_HITS_LOCK:
        if quota_key in _PROVIDER_QUOTA_HITS:
            return
        _PROVIDER_QUOTA_HITS.add(quota_key)

    message = (
        f"Provider {provider or 'unknown'} quota/limit hit — "
        "set a different $large provider in Settings"
    )
    logger.warning(message)
    if detail:
        logger.debug("%s detail: %s", provider or "unknown", detail)

    try:
        from fichero_server.workflows.activity import get_activity_tracker
        from fichero_server.workflows.activity_types import ActivityLevel, ActivityType

        tracker = get_activity_tracker()
        tracker.log(
            type=ActivityType.SYSTEM_WARNING,
            level=ActivityLevel.WARNING,
            message=message,
            metadata={"provider": provider or "unknown"},
        )
    except Exception:
        # Activity logging is best-effort; the Python logger above is the
        # guaranteed fallback.
        pass


def _extract_exc_status_code(exc: BaseException) -> int | None:
    """Pull a status code off common provider exception shapes."""
    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(exc, attr, None)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue

    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
    return None


def _extract_exc_message(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    for attr in ("message", "detail", "error"):
        value = getattr(exc, attr, None)
        if isinstance(value, str):
            parts.append(value)
        elif value is not None:
            parts.append(str(value))
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("text", "reason", "content"):
            value = getattr(response, attr, None)
            if isinstance(value, str):
                parts.append(value)
            elif value is not None:
                parts.append(str(value))
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(str(body))
    return " ".join(part for part in parts if part)


def _is_provider_quota_error(exc: BaseException) -> tuple[bool, int | None, str]:
    """Return quota detection status, status code, and a detail string."""
    status_code = _extract_exc_status_code(exc)
    message = _extract_exc_message(exc)
    lower = message.lower()

    # Context-length errors can match broad quota phrases (e.g. "limit exceeded")
    # but are NOT billing failures — the caller should retry with a shorter prompt
    # or a model with a bigger context window, not skip the provider entirely.
    context_length_keywords = (
        "context length",
        "context_length",
        "maximum context",
        "context window",
        "token limit",
        "maximum length",
        "tokens in the input",
        "too long for",
        "max_tokens",
    )
    if any(token in lower for token in context_length_keywords):
        return False, status_code, message

    quota_keywords = (
        "insufficient_quota",
        "insufficient quota",
        "quota exceeded",
        "key limit exceeded",
        "limit exceeded",
        "rate limit",
        "rate_limit",
        "too many requests",
    )

    if status_code in {402, 429}:
        return True, status_code, message
    if status_code == 403 and any(token in lower for token in quota_keywords):
        return True, status_code, message
    if any(token in lower for token in quota_keywords):
        return True, status_code, message
    return False, status_code, message


def _raise_provider_quota_error(
    config: LLMConfig,
    exc: BaseException,
) -> None:
    """Convert quota/limit provider errors into a typed exception."""
    is_quota, status_code, detail = _is_provider_quota_error(exc)
    if not is_quota:
        return
    _log_provider_quota_hit(config.provider, model=config.model, detail=detail)
    raise ProviderQuotaError(
        config.provider,
        status_code=status_code,
        detail=detail,
        model=config.model,
    ) from exc


def _alias_tier(raw_alias: str) -> str:
    tier = raw_alias[1:]
    if tier.startswith("vision_"):
        return tier
    return tier


def resolve_model_alias(
    provider: str,
    model: str,
    *,
    required_capability: str | None = None,
) -> tuple[str, str]:
    """Resolve configured model aliases against app-level settings.

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

    capability = (required_capability or "").strip().lower()
    if raw in _TEXT_MODEL_ALIASES and capability == "vision":
        raise ValueError(
            f"{raw} is a text-tier model alias and cannot be used for vision "
            "workflow nodes. Use $vision_small, $vision_medium, or "
            "$vision_large, or choose a concrete vision-capable provider/model."
        )
    if raw in _VISION_MODEL_ALIASES and capability and capability != "vision":
        raise ValueError(
            f"{raw} is a vision-tier model alias and cannot be used for "
            f"{capability} workflow nodes. Use $small, $medium, or $large "
            "for text nodes, or choose a concrete capable provider/model."
        )

    env_provider = os.environ.get(f"FICHERO_{raw[1:].upper()}_PROVIDER")
    env_model = os.environ.get(f"FICHERO_{raw[1:].upper()}_MODEL")
    if env_provider and env_model:
        return (env_provider, env_model)

    from fichero_server.db.app import get_app_db
    db = get_app_db()
    tier = _alias_tier(raw)
    resolved_provider = db.get_setting(f"default_{tier}_provider")
    resolved_model = db.get_setting(f"default_{tier}_model")

    if not resolved_provider or not resolved_model:
        label = tier.replace("_", " ")
        raise ValueError(
            f"Workflow node uses {raw} but no Default {label} model is "
            "configured. Set one in Settings → AI Defaults."
        )
    return (resolved_provider, resolved_model)


def _model_has_capability(
    provider: str,
    model: str,
    required_capability: str,
) -> bool | None:
    """Return model capability support when saved model metadata exists.

    ``None`` means no saved metadata was found, so callers should fall back to
    provider-level capability metadata.
    """
    try:
        from fichero_server.db.app import get_app_db

        db = get_app_db()
        provider_key = (provider or "").strip().lower()
        model_key = (model or "").strip()
        for saved_provider in db.list_providers():
            provider_type = getattr(saved_provider, "provider_type", "")
            provider_type_value = getattr(provider_type, "value", str(provider_type))
            if str(provider_type_value).strip().lower() != provider_key:
                continue
            for saved_model in db.list_models(saved_provider.id):
                if getattr(saved_model, "model_id", "") != model_key:
                    continue
                capabilities = [
                    str(cap).strip().lower()
                    for cap in (getattr(saved_model, "capabilities", None) or [])
                ]
                if not capabilities:
                    return None
                if required_capability in {"llm", "text"}:
                    return "text" in capabilities or "llm" in capabilities
                return required_capability in capabilities
    except Exception as exc:
        logger.debug("Model capability lookup failed for %s/%s: %s", provider, model, exc)
    return None


def _configured_vision_model_suggestions(limit: int = 3) -> list[str]:
    """Configured, enabled provider/model pairs that can run a vision node.

    Error-message garnish only (#4187) — never suggest anything the user
    hasn't actually configured. Mirrors the tri-state rule the payload uses:
    an explicit "vision" capability counts, and a model with NO saved
    capabilities inherits its provider's catalog vision support. Best-effort:
    any lookup failure yields no suggestions, never a second error.
    """
    try:
        from fichero_server.db.app import get_app_db
        from fichero_server.llm.providers import get_provider_info

        suggestions: list[str] = []
        app_db = get_app_db()
        for saved_provider in app_db.list_providers():
            if not getattr(saved_provider, "enabled", False):
                continue
            provider_type = saved_provider.provider_type.value
            provider_info = get_provider_info(provider_type)
            provider_vision = bool(provider_info and provider_info.supports_vision)
            for saved_model in app_db.list_models(saved_provider.id):
                if not getattr(saved_model, "enabled", False):
                    continue
                capabilities = [
                    str(cap).strip().lower()
                    for cap in (getattr(saved_model, "capabilities", None) or [])
                ]
                if ("vision" in capabilities) or (not capabilities and provider_vision):
                    suggestions.append(f"{provider_type}/{saved_model.model_id}")
                    if len(suggestions) >= limit:
                        return suggestions
        return suggestions
    except Exception as exc:
        logger.debug("Vision model suggestion lookup failed: %s", exc)
        return []


def validate_model_capability(
    provider: str,
    model: str,
    *,
    required_capability: str | None,
) -> None:
    """Validate concrete provider/model metadata for a required capability."""
    capability = (required_capability or "").strip().lower()
    if not capability:
        return

    if capability == "vision":
        from fichero_server.llm.providers import get_provider_info

        provider_info = get_provider_info((provider or "").strip().lower())
        if provider_info and not provider_info.supports_vision:
            raise ValueError(
                f"Provider {provider} does not support vision. Choose a "
                "vision-capable provider/model for this workflow node."
            )

    model_support = _model_has_capability(provider, model, capability)
    if model_support is False:
        label = "text" if capability in {"llm", "text"} else capability
        message = (
            f"Model {provider}/{model} is not marked as {label}-capable. "
            f"Choose a {label}-capable model for this workflow node."
        )
        if capability == "vision":
            suggestions = _configured_vision_model_suggestions()
            if suggestions:
                message += (
                    " Configured vision-capable models: "
                    + ", ".join(suggestions)
                    + "."
                )
            else:
                message += (
                    " No configured model is marked vision-capable — "
                    "add one under Settings → AI."
                )
        raise ValueError(message)


def _profile_role_matches_capability(profile_role: str, capability: str | None) -> bool:
    role = (profile_role or "").strip().lower()
    required = (capability or "").strip().lower()
    if role == "general" or not required:
        return True
    if required == "llm":
        required = "text"
    return role == required


def resolve_model_profile_for_capability(
    profile_ref: str,
    *,
    base_config: LLMConfig | None = None,
    required_capability: str | None,
) -> LLMConfig:
    """Resolve a named profile and enforce role/capability/privacy policy."""
    from fichero_server.db.app import get_app_db
    from fichero_server.llm.model_profiles import (
        ModelProfileNotFoundError,
        enforce_model_profile_privacy,
        llm_config_from_profile,
    )

    ref = (profile_ref or "").strip()
    embedded_ref = extract_model_profile_reference(ref)
    if embedded_ref:
        ref = embedded_ref
    if not ref:
        raise ModelProfileNotFoundError(profile_ref)

    db = get_app_db()
    profile = db.get_model_profile(ref) or db.get_model_profile_by_name(ref)
    if profile is None:
        raise ModelProfileNotFoundError(ref)
    if not _profile_role_matches_capability(profile.role.value, required_capability):
        required = (required_capability or "text").strip().lower()
        if required == "llm":
            required = "text"
        raise ValueError(
            f"Model profile '{profile.name}' is role '{profile.role.value}' "
            f"and cannot be used for {required} workflow nodes."
        )

    enforce_model_profile_privacy(profile)
    validate_model_capability(
        profile.provider,
        profile.model,
        required_capability=required_capability,
    )
    return llm_config_from_profile(profile, base_config=base_config)


def resolve_model_alias_for_capability(
    provider: str,
    model: str,
    *,
    required_capability: str | None,
) -> tuple[str, str]:
    """Resolve aliases, then enforce provider/model capability metadata."""
    resolver = resolve_model_alias
    try:
        parameters = inspect.signature(resolver).parameters
    except (TypeError, ValueError):
        parameters = {}
    supports_capability_kw = "required_capability" in parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in parameters.values()
    )
    if supports_capability_kw:
        resolved_provider, resolved_model = resolver(
            provider,
            model,
            required_capability=required_capability,
        )
    else:
        resolved_provider, resolved_model = resolver(provider, model)
    validate_model_capability(
        resolved_provider,
        resolved_model,
        required_capability=required_capability,
    )
    return (resolved_provider, resolved_model)


def enforce_local_only_provider(provider: str, model: str, *, kind: str) -> None:
    """Apply the local-only policy to a concrete provider/model pair."""
    _enforce_local_only_provider(LLMConfig(provider=provider, model=model), kind=kind)


def _resolve_tier_transport_settings(tier: str) -> tuple[str | None, str | None]:
    """Resolve env-only overrides for a tier's transport settings."""
    tier_name = tier.upper()
    base_url = (
        os.environ.get(f"FICHERO_{tier_name}_BASE_URL")
        or os.environ.get(f"FICHERO_{tier_name}_API_BASE")
    )
    api_key = os.environ.get(f"FICHERO_{tier_name}_API_KEY")
    return base_url, api_key


def _build_fallback_config(config: LLMConfig, tier: str = "large") -> LLMConfig:
    """Build a tier fallback config, including transport overrides."""
    fallback_provider, fallback_model = resolve_model_alias(f"${tier}", "")
    base_url, api_key = _resolve_tier_transport_settings(tier)
    return LLMConfig(
        provider=fallback_provider,
        model=fallback_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=api_key or config.api_key,
        api_base=base_url or config.api_base,
        timeout=config.timeout,
        extra=dict(config.extra),
        reasoning_effort=config.reasoning_effort,
    )


def _fallback_tier_order() -> tuple[str, ...]:
    """Ordered fallback tiers after Apple. Defaults to $medium -> $large."""
    raw = os.environ.get("FICHERO_AI_FALLBACK_TIERS")
    if raw is None:
        return ("medium", "large")

    tiers: list[str] = []
    for item in raw.split(","):
        tier = item.strip().lower().lstrip("$")
        if not tier:
            continue
        if tier not in {"medium", "large"}:
            raise ValueError(
                f"Invalid fallback tier {item!r}; expected comma-separated medium/large."
            )
        if tier not in tiers:
            tiers.append(tier)
    return tuple(tiers) or ("medium", "large")


def _local_runtime_missing(origin_error: BaseException | None) -> bool:
    """Whether the failure was "the on-device runtime is not installed" (#4502).

    This is NOT the same failure as Apple's guardrail refusing a prompt, even
    though both arrive as ``AppleUnavailableError`` — and the difference decides
    whether a paid fallback is a kindness or a substitution.

    - ``GuardrailViolationError`` / unsupported locale: Apple *cannot serve this
      CONTENT*. Nothing the user installs changes that, and escaping to a
      frontier model is the documented intent (academic text trips a consumer
      safety filter).
    - ``LocalModelUnavailableError``: the runtime is missing or the hardware
      cannot run it. Someone chose MLX, and the reasons to choose MLX are free,
      on-device, and private. Answering "your runtime is not installed" with a
      paid cloud call charges them money AND sends the data off-device — it
      substitutes the very thing they rejected. It is a provisioning problem
      with a fix, so the honest move is to say so.
    """
    return isinstance(origin_error, LocalModelUnavailableError)


def _iter_fallback_configs(
    config: LLMConfig,
    *,
    original_config: LLMConfig,
    error_name: str,
    kind: str,
    origin_error: BaseException | None = None,
) -> Iterator[tuple[str, LLMConfig, bool]]:
    """Yield usable fallback configs in ordered tier order.

    ``origin_error`` is what failed on the primary attempt. When it says the
    LOCAL RUNTIME IS MISSING, only local fallbacks are yielded — see
    :func:`_local_runtime_missing`. Defaults to None so existing callers keep
    today's behaviour rather than silently changing it.
    """
    for tier in _fallback_tier_order():
        try:
            fallback_config = _build_fallback_config(config, tier)
        except ValueError:
            logger.warning(
                "%s but no $%s fallback configured; continuing fallback chain.",
                error_name,
                tier,
            )
            continue

        if (
            fallback_config.provider == original_config.provider
            and fallback_config.model == original_config.model
        ):
            continue

        fallback_is_local = _is_local_or_builtin_provider(fallback_config.provider)
        _enforce_local_only_provider(fallback_config, kind=f"{kind} ${tier} fallback")

        # A missing on-device runtime never escalates to a paid provider,
        # EVEN when paid fallbacks are enabled (#4502). Enabling paid fallbacks
        # is consent to escape Apple's guardrail, not consent to replace the
        # local model someone deliberately chose. Falling to another LOCAL tier
        # is still fine — that keeps the property they picked it for.
        if _local_runtime_missing(origin_error) and not fallback_is_local:
            logger.warning(
                "%s: the on-device runtime is unavailable, so NOT falling back "
                "to paid $%s %s/%s. Install the local runtime, or pick a "
                "different provider explicitly — a local-model failure will "
                "not silently become a billed remote call.",
                error_name,
                tier,
                fallback_config.provider,
                fallback_config.model,
            )
            continue

        if not _paid_remote_fallbacks_enabled() and not fallback_is_local:
            logger.warning(
                "Skipping $%s %s fallback %s/%s because paid remote fallbacks "
                "are disabled by default. Configure a local provider or set "
                "FICHERO_ALLOW_PAID_AI_FALLBACKS=1.",
                tier,
                kind,
                fallback_config.provider,
                fallback_config.model,
            )
            continue

        yield tier, fallback_config, fallback_is_local


def _paid_remote_fallbacks_enabled() -> bool:
    """Whether Apple structured fallback may use paid remote providers."""
    raw = os.environ.get("FICHERO_ALLOW_PAID_AI_FALLBACKS")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    try:
        from fichero_server.db.app import get_app_db

        setting = get_app_db().get_setting("allow_paid_ai_fallbacks")
    except Exception:
        setting = None

    if setting is None:
        return False
    return str(setting).strip().lower() in {"1", "true", "yes", "on"}


def is_local_only() -> bool:
    """Whether LLM calls must stay on local / built-in providers only."""
    raw = os.environ.get("FICHERO_LOCAL_ONLY")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    try:
        from fichero_server.db.app import get_app_db

        setting = get_app_db().get_setting("local_only_ai")
    except Exception:
        setting = None

    if setting is None:
        return False
    return str(setting).strip().lower() in {"1", "true", "yes", "on"}


def _is_local_or_builtin_provider(provider: str) -> bool:
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info((provider or "").strip().lower())
    return bool(info and (info.is_local or info.is_builtin))


def _enforce_local_only_provider(config: LLMConfig, *, kind: str) -> None:
    if not is_local_only():
        return
    if _is_local_or_builtin_provider(config.provider):
        return
    raise LocalOnlyViolationError(config.provider, model=config.model, kind=kind)


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
    # Process-level cache (#2545): avoid a synchronous Keychain round-trip on
    # every call. Cached by `provider` — the only input that determines the
    # result. Bust via clear_api_key_cache() when a credential changes.
    with _API_KEY_CACHE_LOCK:
        if provider in _API_KEY_CACHE:
            return _API_KEY_CACHE[provider]

    resolved = _read_api_key_uncached(provider)

    with _API_KEY_CACHE_LOCK:
        _API_KEY_CACHE[provider] = resolved
    return resolved


def _read_api_key_uncached(provider: str) -> str | None:
    """Resolve an API key from the Keychain then env, without caching."""
    from fichero_server.llm.providers import get_provider_info

    # App-supplied first (#4534): under app-owned keys this is the normal
    # source on macOS. Checked before the keychain because a running app's
    # push is fresher than anything on disk, and because the engine is
    # expected to stop reading keychains at all.
    from fichero_server.security.provider_keys import supplied_api_key

    supplied = supplied_api_key(provider)
    if supplied:
        return supplied

    # Then the keychain -- still consulted for engines that predate the
    # ownership move and for the audit-chain secret. Not removed here: the
    # cutover is the APP starting to supply, and ripping the read out in the
    # same commit would strand any engine no app has pushed to yet.
    try:
        from fichero_server.security.keychain import (
            KeychainUnreadableError,
            get_api_key as _keychain_get,
        )

        key = _keychain_get(provider)
        if key:
            return key
    except ImportError:
        pass
    except KeychainUnreadableError as exc:
        # #4534: the key EXISTS and we were refused. The env fallback below is
        # still legitimate -- a key in the environment is a real key -- so we
        # take it, but we say WHY we took it, at the point we take it. The old
        # code could not even reach this branch: an unreadable read arrived
        # here as None and was indistinguishable from "nothing in the
        # keychain", so the fallback looked like the normal path.
        logger.warning(
            "Keychain key for %s exists but is unreadable (%s); falling back to the environment",
            provider,
            exc.detail or "no detail",
        )

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


def _model_cache_extra_identity(config: LLMConfig) -> tuple[str, str]:
    """Return provider-specific constructor fields that affect model identity."""
    provider = (config.provider or "").strip().lower()
    if provider == "bedrock":
        return (str(config.extra.get("region", "us-east-1")), "")
    if provider == "azure":
        return ("", str(config.extra.get("api_version", "2024-02-01")))
    return ("", "")


def _langchain_model_cache_key(
    config: LLMConfig,
    *,
    api_key_identity: str,
) -> _ModelCacheKey:
    provider = (config.provider or "").strip().lower()
    base_url = (config.api_base or "").strip()
    reasoning_effort = (config.reasoning_effort or "").strip().lower()
    extra_a, extra_b = _model_cache_extra_identity(config)
    return (
        provider,
        config.model,
        float(config.temperature),
        int(config.max_tokens),
        int(config.timeout),
        base_url,
        api_key_identity,
        reasoning_effort,
        extra_a,
        extra_b,
    )


def _max_inflight_llm() -> int:
    raw = os.environ.get("FICHERO_MAX_INFLIGHT_LLM")
    if raw is None:
        return _DEFAULT_MAX_INFLIGHT_LLM
    try:
        parsed = int(raw.strip())
    except ValueError:
        logger.warning(
            "Invalid FICHERO_MAX_INFLIGHT_LLM=%r; using default %d",
            raw,
            _DEFAULT_MAX_INFLIGHT_LLM,
        )
        return _DEFAULT_MAX_INFLIGHT_LLM
    return parsed if parsed > 0 else _DEFAULT_MAX_INFLIGHT_LLM


def _get_remote_llm_semaphore() -> asyncio.Semaphore:
    global _REMOTE_LLM_SEMAPHORE, _REMOTE_LLM_SEMAPHORE_LIMIT

    limit = _max_inflight_llm()
    semaphore = _REMOTE_LLM_SEMAPHORE
    if semaphore is not None and _REMOTE_LLM_SEMAPHORE_LIMIT == limit:
        return semaphore

    with _REMOTE_LLM_SEMAPHORE_LOCK:
        semaphore = _REMOTE_LLM_SEMAPHORE
        if semaphore is not None and _REMOTE_LLM_SEMAPHORE_LIMIT == limit:
            return semaphore
        semaphore = asyncio.Semaphore(limit)
        _REMOTE_LLM_SEMAPHORE = semaphore
        _REMOTE_LLM_SEMAPHORE_LIMIT = limit
        return semaphore


@contextlib.asynccontextmanager
async def _remote_llm_call_slot(config: LLMConfig) -> AsyncIterator[None]:
    """Throttle remote LLM calls without touching local / built-in providers."""
    if _is_local_or_builtin_provider(config.provider):
        yield
        return

    async with _get_remote_llm_semaphore():
        yield


@contextlib.asynccontextmanager
async def _remote_llm_batch_slots(
    config: LLMConfig,
    count: int,
) -> AsyncIterator[None]:
    """Reserve up to ``count`` remote-call slots for one abatch chunk."""
    if _is_local_or_builtin_provider(config.provider):
        yield
        return

    semaphore = _get_remote_llm_semaphore()
    permits = max(1, count)
    for _ in range(permits):
        await semaphore.acquire()
    try:
        yield
    finally:
        for _ in range(permits):
            semaphore.release()


def _batch_max_concurrency(config: LLMConfig) -> int | None:
    if _is_local_or_builtin_provider(config.provider):
        return None
    return _max_inflight_llm()


def _coerce_batch_item_exception(
    config: LLMConfig,
    exc: BaseException,
) -> BaseException:
    try:
        _raise_provider_quota_error(config, exc)
    except ProviderQuotaError as quota_exc:
        return quota_exc
    return exc


def _record_batch_usage(
    responses: list[Any],
    config: LLMConfig,
    *,
    kind: str,
) -> None:
    for response in responses:
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict) and usage:
            _record_usage(
                config.provider,
                config.model,
                kind,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            )


async def _call_model_abatch(
    model: Any,
    inputs: list[Any],
    config: LLMConfig,
) -> list[Any]:
    budget = _compute_timeout(config, "langchain")
    batch_config = None
    max_concurrency = _batch_max_concurrency(config)
    if max_concurrency is not None:
        batch_config = {"max_concurrency": max_concurrency}

    kwargs: dict[str, Any] = {}
    if batch_config is not None:
        kwargs["config"] = batch_config

    try:
        return await asyncio.wait_for(
            model.abatch(inputs, return_exceptions=True, **kwargs),
            timeout=budget,
        )
    except TypeError as exc:
        message = str(exc)
        if "config" in message and "unexpected keyword argument" in message:
            try:
                return await asyncio.wait_for(
                    model.abatch(inputs, return_exceptions=True),
                    timeout=budget,
                )
            except TypeError as retry_exc:
                if "return_exceptions" not in str(retry_exc):
                    raise
                return await asyncio.wait_for(
                    model.abatch(inputs),
                    timeout=budget,
                )
            except asyncio.TimeoutError as timeout_exc:
                raise RuntimeError(
                    f"LangChain {config.provider}/{config.model} batch call "
                    f"exceeded {budget}s — provider hang"
                ) from timeout_exc
        elif "return_exceptions" not in message:
            raise
        try:
            return await asyncio.wait_for(
                model.abatch(inputs, **kwargs),
                timeout=budget,
            )
        except TypeError as retry_exc:
            if "return_exceptions" not in str(retry_exc):
                raise
            return await asyncio.wait_for(
                model.abatch(inputs),
                timeout=budget,
            )
        except asyncio.TimeoutError as timeout_exc:
            raise RuntimeError(
                f"LangChain {config.provider}/{config.model} batch call "
                f"exceeded {budget}s — provider hang"
            ) from timeout_exc
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"LangChain {config.provider}/{config.model} batch call "
            f"exceeded {budget}s — provider hang"
        ) from exc


async def _run_abatch_chunks(
    model: Any,
    inputs: list[Any],
    config: LLMConfig,
) -> list[Any]:
    if not inputs:
        return []

    max_concurrency = _batch_max_concurrency(config) or len(inputs)
    results: list[Any] = []
    for start in range(0, len(inputs), max_concurrency):
        chunk = inputs[start:start + max_concurrency]
        async with _remote_llm_batch_slots(config, len(chunk)):
            try:
                chunk_results = await _call_model_abatch(model, chunk, config)
            except Exception as exc:
                chunk_results = [exc] * len(chunk)
        results.extend(chunk_results)
    return results


async def _bounded_batch_fallback(
    limit: int,
    factories: list[Callable[[], Any]],
) -> list[Any]:
    semaphore = asyncio.Semaphore(limit)

    async def _run(factory: Callable[[], Any]) -> Any:
        async with semaphore:
            try:
                return await factory()
            except Exception as exc:
                return exc

    return await asyncio.gather(*(_run(factory) for factory in factories))


def _normalize_batch_chat_prompt(
    prompt: str | list[dict[str, Any]],
    *,
    system: str | None,
) -> list[Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    if isinstance(prompt, str):
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        return messages
    return _convert_to_langchain_messages(prompt)


def _normalize_batch_chat_result(
    result: Any,
    index: int,
    config: LLMConfig,
) -> str | LLMBatchItemError:
    if isinstance(result, BaseException):
        return LLMBatchItemError(
            index,
            provider=config.provider,
            model=config.model,
            kind="chat",
            cause=_coerce_batch_item_exception(config, result),
        )
    return _strip_outer_code_fences(result.content)


def _normalize_batch_vision_result(
    result: Any,
    index: int,
    config: LLMConfig,
) -> str | LLMBatchItemError:
    if isinstance(result, BaseException):
        return LLMBatchItemError(
            index,
            provider=config.provider,
            model=config.model,
            kind="vision",
            cause=_coerce_batch_item_exception(config, result),
        )
    return _strip_outer_code_fences(result.content)


# =============================================================================
# Chat
# =============================================================================


async def chat(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    stream: bool = False,
    system: str | None = None,
    permissive_guardrails: bool = False,
    use_case: str | None = None,
) -> str | AsyncIterator[str]:
    """Send a chat message using LangChain.

    Args:
        prompt: User message (string) or full messages list
        config: LLM configuration
        stream: If True, return async generator of chunks
        system: Optional system message
        permissive_guardrails: Apple-only. Pass True for narrative /
            summary calls over content the default safety filter
            false-positives (literary profanity, court-record
            vocabulary). Has no effect on non-Apple providers (#850).

    Returns:
        Response string, or async generator if streaming
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    _enforce_local_only_provider(config, kind="chat")

    # Apple Intelligence (Foundation Models) lives outside LangChain — Swift-
    # native API requires the fm-bridge subprocess. Route before LangChain
    # tries to construct a model class for it.
    if config.provider == "apple":
        if stream:
            raise ValueError(
                "Apple Intelligence does not support streaming yet — "
                "the fm-bridge wrapper returns a single response."
            )
        return await _apple_intelligence_chat(
            prompt, config, system,
            permissive_guardrails=permissive_guardrails,
            use_case=use_case,
        )

    # Built-in deterministic debug provider (#1566). The catalogue
    # narrative node calls plain chat() (not chat_structured), so without
    # this branch a full mock run would reach LangChain with a nonexistent
    # model and error. Return a fixed canned narrative so a whole
    # folder/PDF catalogue runs free end-to-end.
    if config.provider == "mock":
        if stream:
            raise ValueError(
                "Mock provider does not support streaming — it returns a "
                "single deterministic response."
            )
        from fichero_server.llm.mock import mock_chat_response

        prompt_text = prompt if isinstance(prompt, str) else str(prompt)
        return mock_chat_response(prompt_text)

    # Get LangChain model
    await _ensure_managed_local_provider_ready(config)
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
        return _stream_chat_langchain(model, messages, config)
    else:
        # Hard wall-clock timeout (#844 robustness). LangChain accepts a
        # `timeout` kwarg per provider but enforcement varies — some
        # backends ignore it under HTTP keepalive, leading to indefinite
        # hangs (observed live on ChatOpenRouter mid-narrative). Wrap
        # every ainvoke in asyncio.wait_for so a stuck call eventually
        # surfaces a TimeoutError that chat_with_fallback / structured
        # callers can route around.
        budget = _compute_timeout(config, "langchain")
        try:
            async with _remote_llm_call_slot(config):
                response = await asyncio.wait_for(
                    model.ainvoke(messages), timeout=budget,
                )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"LangChain {config.provider}/{config.model} chat exceeded "
                f"{budget}s — provider hang"
            ) from exc
        except Exception as exc:
            _raise_provider_quota_error(config, exc)
            raise
        # Surface usage_metadata to the cost-tracking layer (#844 item 8 +
        # #852). AIMessage.usage_metadata is the LangChain ≥0.3 standard
        # shape: input_tokens / output_tokens / total_tokens dict.
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict) and usage:
            _record_usage(
                config.provider, config.model, "chat",
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
        return _strip_outer_code_fences(response.content)


async def chat_batch(
    prompts: list[str | list[dict[str, Any]]],
    config: LLMConfig,
    *,
    system: str | None = None,
    permissive_guardrails: bool = False,
    use_case: str | None = None,
) -> list[str | LLMBatchItemError]:
    """Send multiple chat prompts with per-item error isolation."""
    _enforce_local_only_provider(config, kind="chat")

    if not prompts:
        return []

    if config.provider in {"apple", "mock"}:
        limit = _batch_max_concurrency(config) or _DEFAULT_MAX_INFLIGHT_LLM
        results = await _bounded_batch_fallback(
            limit,
            [
                lambda prompt=prompt: chat(
                    prompt,
                    config,
                    system=system,
                    permissive_guardrails=permissive_guardrails,
                    use_case=use_case,
                )
                for prompt in prompts
            ],
        )
        return [
            result
            if isinstance(result, str)
            else LLMBatchItemError(
                index,
                provider=config.provider,
                model=config.model,
                kind="chat",
                cause=_coerce_batch_item_exception(config, result),
            )
            for index, result in enumerate(results)
        ]

    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)
    messages_batch = [
        _normalize_batch_chat_prompt(prompt, system=system)
        for prompt in prompts
    ]
    results = await _run_abatch_chunks(model, messages_batch, config)
    _record_batch_usage(
        [result for result in results if not isinstance(result, BaseException)],
        config,
        kind="chat",
    )
    return [
        _normalize_batch_chat_result(result, index, config)
        for index, result in enumerate(results)
    ]


async def chat_with_fallback(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    system: str | None = None,
    permissive_guardrails: bool = False,
) -> str:
    """Like chat(), but falls back through the ordered tier chain when Apple
    Intelligence can't service the request.

    Apple's safety filter is tuned for consumer use cases and refuses
    scholarly text containing literary profanity, drug references,
    historical slurs, court-record vocabulary, etc. Apple's locale
    matrix also evolves per OS release (en-US only on 15.1; Spanish-
    Spain added 15.4; broader on 26+) and rejects out-of-set prompts
    with `unsupportedLanguageOrLocale`. Frontier cloud providers
    handle both — academic content + any locale — so the fallback
    keeps the local-first default but escapes to the user-configured
    cloud provider when needed.

    Streaming is intentionally unsupported — callers that need streaming
    are using direct chat() and accept the responsibility of catching
    AppleUnavailableError subclasses themselves.

    Returns the response string. Raises when every configured fallback tier
    is unavailable or fails.
    """
    try:
        return await chat(
            prompt, config, system=system,
            permissive_guardrails=permissive_guardrails,
        )
    except AppleUnavailableError as apple_exc:
        last_failure: Exception | None = None
        attempted = False
        for tier, fallback_config, fallback_is_local in _iter_fallback_configs(
            config,
            original_config=config,
            error_name=type(apple_exc).__name__,
            kind="chat",
            origin_error=apple_exc,
        ):
            attempted = True
            cost_note = (
                "an on-device model — no API cost"
                if fallback_is_local
                else "a PAID remote model — this request now incurs cost"
            )
            logger.warning(
                "Apple Intelligence unavailable (%s); falling back to %s: "
                "$%s = %s/%s.",
                type(apple_exc).__name__,
                cost_note,
                tier,
                fallback_config.provider,
                fallback_config.model,
            )
            try:
                result = await chat(
                    prompt,
                    fallback_config,
                    system=system,
                    permissive_guardrails=permissive_guardrails,
                )
            except (AppleUnavailableError, ProviderQuotaError) as exc:
                last_failure = exc
                continue
            logger.info(
                "Fallback to $%s %s/%s succeeded.",
                tier,
                fallback_config.provider,
                fallback_config.model,
            )
            return result

        if attempted and last_failure is not None:
            raise last_failure
        raise apple_exc


async def _translate_with_deepl(
    *,
    text: str,
    source_lang: str | None,
    target_lang: str,
    config: LLMConfig,
) -> str:
    """DeepL translation call via `/v2/translate`."""
    import aiohttp

    if not text.strip():
        return ""
    api_key = _resolve_api_key(config)
    if not api_key:
        raise ValueError("DeepL provider requires DEEPL_API_KEY (or config.api_key).")

    base = (config.api_base or "https://api-free.deepl.com").rstrip("/")
    url = f"{base}/v2/translate"
    payload: dict[str, Any] = {
        "text": [text],
        "target_lang": target_lang.upper(),
    }
    src = (source_lang or "").strip()
    if src and src.lower() != "auto":
        payload["source_lang"] = src.upper()

    timeout = aiohttp.ClientTimeout(total=max(config.timeout, 10))
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status >= 400:
                detail = await response.text()
                raise RuntimeError(
                    f"DeepL translate failed ({response.status}): {detail[:400]}"
                )
            body = await response.json()

    translations = body.get("translations", [])
    if not translations:
        raise RuntimeError("DeepL translate returned no translations")
    translated = translations[0].get("text")
    if not isinstance(translated, str):
        raise RuntimeError("DeepL translate returned invalid payload")
    return translated


async def translate_text(
    text: str,
    *,
    source_lang: str | None = "auto",
    target_lang: str = "en",
    config: LLMConfig,
) -> str:
    """Unified translation helper for workflow tools and CLI."""
    _enforce_local_only_provider(config, kind="translation")

    if config.provider.lower() == "deepl":
        return await _translate_with_deepl(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            config=config,
        )

    src = (source_lang or "auto").strip()
    tgt = (target_lang or "en").strip()
    from_clause = f"from {src} " if src.lower() != "auto" else ""
    prompt = (
        f"Translate the following text {from_clause}into {tgt}. "
        "Output only the translation with original structure preserved.\n\n"
        f"{text}"
    )
    return await chat(prompt, config)


async def _apple_intelligence_chat(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    system: str | None = None,
    permissive_guardrails: bool = False,
    use_case: str | None = None,
) -> str:
    """Bridge to FoundationModels via the bundled Swift fm-bridge binary.

    Apple Intelligence's public API is Swift-native (LanguageModelSession.
    respond(to:)) and not @objc-exposed, so pyobjc loads the classes but
    can't call their methods. The fm-bridge binary (compiled from
    fichero-server/bin/fm-bridge/FmBridge.swift) is a tiny CLI that takes a JSON
    request on stdin and emits a JSON response on stdout.

    Build with:
        swiftc -O -parse-as-library -o fichero-server/bin/fm-bridge/fm-bridge \\
            fichero-server/bin/fm-bridge/FmBridge.swift
    """
    import asyncio
    import json as _json

    user_text, instructions = _collapse_apple_prompt(prompt, system)

    unavailable_reason = _fm_bridge_unavailable_reason()
    if unavailable_reason is not None:
        raise RuntimeError(unavailable_reason)

    binary = _find_fm_bridge_binary()
    if binary is None:
        raise RuntimeError(_FM_BRIDGE_MISSING_MESSAGE)

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
    # Permissive guardrails (#850): relax the on-device safety filter for
    # string-output generations. Useful for narrative/summary calls over
    # scholarly text with literary profanity / court-record vocabulary
    # the default guardrails false-positive (e.g. the Sánchez Juliao
    # epigraph case). Apple's docs note this only affects string output;
    # structured/Generable calls run with default guardrails regardless,
    # which is why chat_structured doesn't expose this parameter.
    if permissive_guardrails:
        request_dict["guardrails"] = "permissive"
    # Optional Apple Intelligence use-case (#853). Today only
    # "content_tagging" is wired through to fm-bridge — Apple's specialised
    # tagging model produces crisper lowercase topic/object tags than the
    # general-purpose model. Use it for keyword extraction; ignore for
    # everything else.
    if use_case in {"content_tagging"}:
        request_dict["use_case"] = use_case
    request_payload = _json.dumps(request_dict).encode()

    proc = await asyncio.create_subprocess_exec(
        str(binary),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Bound subprocess by _compute_timeout(apple_chat) so a hung Apple
    # Intelligence session can't block the workflow forever. On timeout,
    # kill the process and surface a generation error so chat_with_fallback
    # can route to $large. (#855)
    chat_budget = _compute_timeout(config, "apple_chat")
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(request_payload),
            timeout=chat_budget,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"Apple Intelligence (timeout): fm-bridge exceeded "
            f"{chat_budget}s for prompt — provider hang"
        )

    if proc.returncode != 0:
        _raise_from_bridge_stderr(stderr_bytes, proc.returncode)

    try:
        result = _json.loads(stdout_bytes.decode())
    except _json.JSONDecodeError as exc:
        raise RuntimeError(
            f"fm-bridge stdout was not valid JSON: {stdout_bytes!r}"
        ) from exc

    response_text = result.get("response", "")
    if not _log_apple_usage_from_bridge(config, result, kind="chat"):
        # Fallback when bridge payload has no token usage.
        _log_apple_usage_estimate(config, prompt, response_text, kind="chat")
    return response_text


def _log_apple_usage_estimate(
    config: LLMConfig,
    prompt: Any,
    response_text: str,
    *,
    kind: str,
) -> None:
    """Emit an INFO log with estimated input/output/total tokens for an
    Apple Intelligence call. Best-effort — Foundation Models doesn't
    expose token counts through fm-bridge's stdout payload yet, so we
    estimate from char counts via estimate_token_count. Marked
    (estimated) so dashboards can distinguish from cloud-reported
    usage. (#843 item 3)
    """
    if isinstance(prompt, str):
        prompt_text = prompt
    elif isinstance(prompt, list):
        # OpenAI-style messages list: concat content fields for the estimate.
        prompt_text = " ".join(
            str(m.get("content", "")) for m in prompt if isinstance(m, dict)
        )
    else:
        prompt_text = str(prompt)
    input_tokens = estimate_token_count(prompt_text)
    output_tokens = estimate_token_count(response_text or "")
    _record_usage(
        config.provider, config.model, kind,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated=True,
    )


def _log_apple_usage_from_bridge(
    config: LLMConfig,
    bridge_result: dict[str, Any],
    *,
    kind: str,
) -> bool:
    """Emit exact usage from fm-bridge payload when present.

    Expected shape:
      {"usage": {"input_tokens": int, "output_tokens": int, "total_tokens": int}}
    """
    usage = bridge_result.get("usage")
    if not isinstance(usage, dict):
        return False
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(isinstance(v, int) for v in (input_tokens, output_tokens, total_tokens)):
        return False

    _record_usage(
        config.provider, config.model, kind,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated=False,
    )
    return True


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

    if kind == "unsupported_language":
        # Apple's per-OS locale matrix doesn't cover all Spanish variants
        # (es-ES vs es-LatAm) even on macOS 26. Treat as Apple-unavailable
        # so chat_with_fallback / chat_structured_with_fallback escape to
        # cloud $large the same way they handle guardrail refusals (#868).
        raise UnsupportedLocaleError(
            f"Apple Intelligence ({kind}): {message}"
        )

    if kind in {"decoding", "generation", "context_overflow", "schema"}:
        # Grammar-constrained Generable calls that the on-device sampler
        # couldn't satisfy. Symptom: 'terminated generation early —
        # Failed to deserialize a Generable type from model output'.
        # extract_all was losing ~10% of chunks (#949 / #962) because
        # these became plain RuntimeError and the structured-fallback
        # wrapper only escaped on AppleUnavailableError subclasses.
        # Promote them so the cloud $large model gets a retry per
        # chunk (matching the guardrail / locale paths).
        raise StructuredDecodeError(
            f"Apple Intelligence ({kind}): {message}",
            kind=kind,
        )

    raise RuntimeError(f"Apple Intelligence ({kind}): {message}")


def is_recognition_only_vision_model(provider: str, model: str) -> bool:
    """True when this provider/model does RECOGNITION, not generation (#4345).

    Apple Vision is an OCR pass, not a generative model: ``_apple_vision_dispatch``
    below ignores the caller's prompt entirely and returns the recognized text.
    That is fine for a tool that just wants text out, and useless for a tool
    whose contract is "answer this prompt as JSON" — the response is page text,
    so the parse fails on every run.

    Mirrors ``_apple_vision_dispatch``'s OCR route exactly (empty/``default``
    model means apple-vision, the only dispatchable on-device vision route).
    """
    if (provider or "").strip().lower() != "apple":
        return False
    return (model or "").strip().lower() in ("", "default", "apple-vision")


async def _apple_vision_dispatch(
    images: list[str],
    prompt: str,
    config: LLMConfig,
    *,
    language: str | None = None,
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

    `language` is the caller's already-resolved document language (#2092).
    It used to be the literal `"en"` here regardless of what the workflow had
    resolved (#4497), so Spanish colonial material was requested as English on
    this route — invisibly, because the setter downstream discarded bad values
    in silence too. `None` keeps the historical en-US default for callers
    (similarity, compare, video) that have no document language to offer.
    """
    from fichero_server.workflows.tools.vision_base import (
        apple_vision_ocr,
        validate_vision_language,
    )
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

    # Resolve (and reject) the recognition locale ONCE, before any image work,
    # so a bad language fails on the request rather than per page.
    ocr_language = validate_vision_language(language)

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
            text = await asyncio.to_thread(
                apple_vision_ocr, file_path, ocr_language
            )
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


async def _stream_chat_langchain(
    model: Any,
    messages: list,
    config: LLMConfig,
) -> AsyncIterator[str]:
    """Stream chat response using LangChain."""
    async with _remote_llm_call_slot(config):
        async for chunk in model.astream(messages):
            if chunk.content:
                yield chunk.content


def _convert_to_langchain_messages(messages: list[dict]) -> list:
    """Convert OpenAI-format messages to LangChain message objects."""
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(
                AIMessage(
                    content=content,
                    tool_calls=msg.get("tool_calls", []),
                )
            )
        elif role == "tool":
            result.append(
                ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                    name=msg.get("name"),
                )
            )
        else:  # user or default
            result.append(HumanMessage(content=content))

    return result


def _langchain_messages_to_openai_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Convert LangChain message objects into the OpenAI-style dicts our Apple path already accepts."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            role = "system"
        elif isinstance(msg, AIMessage):
            role = "assistant"
        elif isinstance(msg, HumanMessage):
            role = "user"
        else:
            role = getattr(msg, "type", "user") or "user"
        result.append({"role": role, "content": getattr(msg, "content", "")})
    return result


def _collapse_apple_prompt(
    prompt: str | list[dict[str, Any]],
    system: str | None,
) -> tuple[str, str]:
    """Flatten OpenAI-style messages into the user+instructions pair fm-bridge expects."""
    if isinstance(prompt, str):
        return prompt, system or ""

    instructions = system or ""
    user_parts: list[str] = []
    for msg in prompt:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        if role == "system" and not instructions:
            instructions = str(content)
        else:
            user_parts.append(str(content))
    return "\n\n".join(user_parts), instructions


class _AppleStructuredRunnable:
    """Minimal LangChain-compatible structured wrapper over chat_structured()."""

    def __init__(
        self,
        model: "ChatAppleIntelligence",  # noqa: F821 (built lazily in _chat_apple_intelligence_cls)
        schema: type[BaseModel],
        *,
        include_raw: bool,
    ) -> None:
        self._model = model
        self._schema = schema
        self._include_raw = include_raw

    async def ainvoke(self, input_data: Any, config: Any = None, **kwargs: Any) -> Any:
        from langchain_core.messages import AIMessage

        prompt, system = self._model._structured_prompt_and_system(input_data)
        parsed = await chat_structured(
            prompt,
            self._schema,
            self._model.config,
            system=system,
        )
        if not self._include_raw:
            return parsed
        raw = AIMessage(content=parsed.model_dump_json())
        return {"raw": raw, "parsed": parsed, "parsing_error": None}

    def invoke(self, input_data: Any, config: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(self.ainvoke(input_data, config=config, **kwargs))


# ChatAppleIntelligence is built lazily (see _chat_apple_intelligence_cls below)
# so that merely importing this package doesn't eagerly pull in langchain_core
# (and its requests/httpx transitive deps) — Apple Intelligence is a rarely
# used provider and langchain should stay lazy for the common case.
_CHAT_APPLE_CLS: type | None = None


def _chat_apple_intelligence_cls() -> type:
    """Build (once) and cache the ChatAppleIntelligence class.

    Deferred so importing `fichero_server.llm` doesn't eagerly import langchain_core.
    """
    global _CHAT_APPLE_CLS
    if _CHAT_APPLE_CLS is not None:
        return _CHAT_APPLE_CLS

    from langchain_core.language_models.chat_models import BaseChatModel

    class ChatAppleIntelligence(BaseChatModel):
        config: LLMConfig
        bound_tools: tuple[Any, ...] = ()
        tool_choice: str | None = None

        @property
        def _llm_type(self) -> str:
            return "apple_intelligence"

        @property
        def _identifying_params(self) -> dict[str, Any]:
            return {
                "provider": self.config.provider,
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

        def bind_tools(
            self,
            tools: list[Any],
            *,
            tool_choice: str | None = None,
            **kwargs: Any,
        ) -> "ChatAppleIntelligence":
            # ponytail: interface-preserving no-op until fm-bridge exposes native tool-call envelopes.
            return self.model_copy(update={"bound_tools": tuple(tools), "tool_choice": tool_choice})

        def with_structured_output(
            self,
            schema: dict[str, Any] | type,
            *,
            include_raw: bool = False,
            **kwargs: Any,
        ) -> _AppleStructuredRunnable:
            if not isinstance(schema, type) or not issubclass(schema, BaseModel):
                raise ValueError(
                    "Apple Intelligence structured output currently requires a Pydantic model class."
                )
            return _AppleStructuredRunnable(self, schema, include_raw=include_raw)

        def _structured_prompt_and_system(self, input_data: Any) -> tuple[str, str | None]:
            if isinstance(input_data, str):
                return input_data, None
            if not isinstance(input_data, list):
                raise TypeError(f"Unsupported Apple structured input: {type(input_data)!r}")
            prompt, system = _collapse_apple_prompt(
                _langchain_messages_to_openai_messages(input_data),
                None,
            )
            return prompt, system or None

        async def _agenerate(
            self,
            messages: list[Any],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> Any:
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            response_text = await chat(
                _langchain_messages_to_openai_messages(messages),
                self.config,
            )
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=response_text))]
            )

        def _generate(
            self,
            messages: list[Any],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> Any:
            return asyncio.run(
                self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            )

    _CHAT_APPLE_CLS = ChatAppleIntelligence
    return _CHAT_APPLE_CLS


def __getattr__(name: str) -> Any:
    """PEP 562 lazy module attribute — `from fichero_server.llm import ChatAppleIntelligence`
    still works without forcing langchain to load at package-import time."""
    if name == "ChatAppleIntelligence":
        return _chat_apple_intelligence_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# =============================================================================
# Vision
# =============================================================================


async def vision(
    images: list[str],
    prompt: str,
    config: LLMConfig,
    *,
    language: str | None = None,
) -> str:
    """Analyze images with a vision model using LangChain.

    Args:
        images: List of image URLs or base64 data URIs
        prompt: Analysis prompt
        config: LLM configuration (must use vision-capable model)
        language: Document language already resolved by the caller's language
            policy (#2092). Only the Apple/on-device OCR route reads it —
            generative providers take their language cue from the prompt.

    Returns:
        Analysis text
    """
    from langchain_core.messages import HumanMessage

    _enforce_local_only_provider(config, kind="vision")

    # Apple provider unified dispatch — Apple has no LangChain integration,
    # so we route by model BEFORE falling through to LangChain. Three Apple
    # models exist (per the bundled provider seed):
    #   * apple-vision        → on-device OCR via Vision framework
    #   * apple-speech        → audio-only (rejected here, vision call)
    #   * apple-intelligence  → FoundationModels LLM, text-only on macOS 26
    # This mirrors chat()'s apple branch — without it, every workflow node
    # that does vision-with-provider=apple bombed with "Unknown LLM
    # provider: 'apple'" (a regression after consolidating to a
    # single Catalogue preset that uses provider=apple by default).
    if config.provider == "apple":
        return await _apple_vision_dispatch(images, prompt, config, language=language)

    # Built-in deterministic debug provider (#1566), same as chat()'s branch:
    # without it a mock run's vision node reached LangChain and died with
    # "Unknown LLM provider: 'mock'" (#4345).
    if config.provider == "mock":
        from fichero_server.llm.mock import mock_vision_response

        return mock_vision_response(prompt, len(images))

    # Content-addressed cache (#2224) — skip remote call for identical inputs.
    _cache_key = _vision_cache_key(config, prompt, images)
    with _LLM_RESULT_CACHE_LOCK:
        if _cache_key in _LLM_RESULT_CACHE:
            return _LLM_RESULT_CACHE[_cache_key]

    # Get LangChain model
    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)

    # Build multimodal message content (LangChain format)
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": img}})

    # Create multimodal message
    message = HumanMessage(content=content)

    # Hard wall-clock timeout (#2228, mirrors chat() #844 robustness). Some
    # vision providers ignore the LangChain `timeout` kwarg under keepalive.
    budget = _compute_timeout(config, "langchain")
    try:
        async with _remote_llm_call_slot(config):
            response = await asyncio.wait_for(
                model.ainvoke([message]), timeout=budget,
            )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"LangChain {config.provider}/{config.model} vision exceeded "
            f"{budget}s — provider hang"
        ) from exc
    except Exception as exc:
        _raise_provider_quota_error(config, exc)
        raise
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        _record_usage(
            config.provider, config.model, "vision",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    result = _strip_outer_code_fences(response.content)

    with _LLM_RESULT_CACHE_LOCK:
        if len(_LLM_RESULT_CACHE) >= _LLM_RESULT_CACHE_MAX:
            oldest = next(iter(_LLM_RESULT_CACHE))
            del _LLM_RESULT_CACHE[oldest]
        _LLM_RESULT_CACHE[_cache_key] = result
    return result


async def audio_transcription(
    file_path: str,
    prompt: str,
    config: LLMConfig,
    *,
    language: str | None = None,
) -> str:
    """Transcribe audio through LangChain's OpenAI-compatible parser."""
    from langchain_community.document_loaders.parsers.audio import OpenAIWhisperParser
    from langchain_core.document_loaders import Blob

    _enforce_local_only_provider(config, kind="audio transcription")
    provider = config.provider.lower()
    if provider != "openai" and provider not in _OPENAI_COMPATIBLE_BASE_URLS:
        raise ValueError(
            f"Remote audio transcription requires an OpenAI-compatible provider, got '{provider}'"
        )

    parser = OpenAIWhisperParser(
        api_key=_resolve_api_key(config),
        base_url=config.api_base or _OPENAI_COMPATIBLE_BASE_URLS.get(provider),
        language=None if language in {None, "auto"} else language,
        prompt=prompt,
        model=config.model,
    )

    def parse() -> str:
        return "\n".join(
            document.page_content.strip()
            for document in parser.lazy_parse(Blob.from_path(file_path))
            if document.page_content.strip()
        )

    budget = _compute_timeout(config, "langchain")
    try:
        async with _remote_llm_call_slot(config):
            return await asyncio.wait_for(asyncio.to_thread(parse), timeout=budget)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"LangChain {config.provider}/{config.model} audio transcription "
            f"exceeded {budget}s — provider hang"
        ) from exc


async def vision_batch(
    image_lists: list[list[str]],
    prompt: str,
    config: LLMConfig,
) -> list[str | LLMBatchItemError]:
    """Analyze multiple image groups with per-item error isolation."""
    from langchain_core.messages import HumanMessage

    _enforce_local_only_provider(config, kind="vision")

    if not image_lists:
        return []

    if config.provider == "apple":
        limit = _batch_max_concurrency(config) or _DEFAULT_MAX_INFLIGHT_LLM
        results = await _bounded_batch_fallback(
            limit,
            [
                lambda images=images: vision(images, prompt, config)
                for images in image_lists
            ],
        )
        return [
            result
            if isinstance(result, str)
            else LLMBatchItemError(
                index,
                provider=config.provider,
                model=config.model,
                kind="vision",
                cause=_coerce_batch_item_exception(config, result),
            )
            for index, result in enumerate(results)
        ]

    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)
    messages_batch = []
    for images in image_lists:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": img}})
        messages_batch.append([HumanMessage(content=content)])

    results = await _run_abatch_chunks(model, messages_batch, config)
    _record_batch_usage(
        [result for result in results if not isinstance(result, BaseException)],
        config,
        kind="vision",
    )
    return [
        _normalize_batch_vision_result(result, index, config)
        for index, result in enumerate(results)
    ]


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

    _enforce_local_only_provider(
        LLMConfig(provider="huggingface", model=model, api_key=api_key),
        kind="vision",
    )

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
        remote_config = LLMConfig(provider="huggingface", model=model, api_key=api_key)
        async with _remote_llm_call_slot(remote_config):
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
    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)

    # Bind tools to model
    model_with_tools = model.bind_tools(tools)

    # Build messages
    if isinstance(prompt, str):
        messages = [HumanMessage(content=prompt)]
    else:
        messages = _convert_to_langchain_messages(prompt)

    # Call model with tools
    try:
        async with _remote_llm_call_slot(config):
            response = await model_with_tools.ainvoke(messages)
    except Exception as exc:
        _raise_provider_quota_error(config, exc)
        raise

    # Extract tool calls from response
    tool_calls = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_calls = response.tool_calls

    return {
        "content": response.content,
        "tool_calls": tool_calls,
    }


def _prepend_system_message(
    prompt: str | list[dict[str, Any]],
    system: str | None,
) -> str | list[dict[str, Any]]:
    if system is None:
        return prompt
    if isinstance(prompt, str):
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    return [{"role": "system", "content": system}, *prompt]


async def chat_workflow(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    *,
    system: str | None = None,
    schema: type[BaseModel] | None = None,
    tools: list[Any] | None = None,
) -> Any:
    """Single workflow/tool entry point for LangChain-backed LLM calls."""
    if schema is not None and tools is not None:
        raise ValueError("Structured output and tools cannot be requested together")

    if schema is not None:
        if not isinstance(prompt, str):
            raise ValueError("Structured workflow chat requires a string prompt")
        return await chat_structured(
            prompt,
            schema,
            config,
            system=system,
        )

    effective_prompt = _prepend_system_message(prompt, system)
    if tools is not None:
        return await chat_with_tools(effective_prompt, tools, config)
    return await chat(effective_prompt, config)


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
    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)

    # Use LangChain's with_structured_output for clean schema binding
    structured_model = model.with_structured_output(schema)

    # Call model
    try:
        async with _remote_llm_call_slot(config):
            result = await structured_model.ainvoke([HumanMessage(content=prompt)])
    except Exception as exc:
        _raise_provider_quota_error(config, exc)
        raise

    return result


async def chat_structured(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
    use_case: str | None = None,
    permissive_guardrails: bool = False,
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
    _enforce_local_only_provider(config, kind="structured chat")

    if config.provider == "apple":
        return await _apple_intelligence_structured(
            prompt, schema, config, system,
            include_schema_in_prompt=include_schema_in_prompt,
            use_case=use_case,
            permissive_guardrails=permissive_guardrails,
        )

    # Built-in deterministic debug provider (#1566): no LLM, no network,
    # no cost. chat_structured_with_fallback inherits this automatically.
    if config.provider == "mock":
        from fichero_server.llm.mock import mock_structured_response

        return mock_structured_response(schema, prompt)

    from langchain_core.messages import HumanMessage, SystemMessage

    await _ensure_managed_local_provider_ready(config)
    model = get_langchain_model(config)

    # Some local OpenAI-compatible servers (omlx/lmstudio/ollama) do
    # not implement tool-calling or response_format=json_schema. Let
    # LangChain pick its provider-default strategy there (typically
    # prompt-embedded schema + parse), which is the path that works.
    # Other providers keep explicit profile-driven method selection.
    method: str | None
    if config.provider.lower() in {"omlx", "lmstudio", "ollama"}:
        method = None
    elif (
        config.provider.lower() == "openrouter"
        or "openrouter" in (config.api_base or "").lower()
    ):
        # OpenRouter forwards Claude/etc. to backends (e.g. Amazon Bedrock).
        # The two non-tool-calling paths both fail here:
        #   - json_schema (strict response_format) → Bedrock-Claude returns an
        #     EMPTY body → "expected value at line 1 column 1".
        #   - json_mode (response_format={"type":"json_object"}) → the OpenAI
        #     route 400s ("'messages' must contain the word 'json' …") because
        #     LangChain doesn't inject the literal token, and Bedrock under-
        #     fills nested sections.
        # The robust path is function_calling — every OpenRouter-routed model
        # supports tool-calling — but LangChain pairs it with
        # parallel_tool_calls=False, whose Bedrock translation
        # (tool_choice.disable_parallel_tool_use) is rejected as an extraneous
        # key. We strip that param at the request layer in get_langchain_model
        # (`_openrouter_strip_parallel_tool_use`) so function_calling works on
        # BOTH the OpenAI and Bedrock-Claude routes. (#1802)
        method = "function_calling"
    elif config.provider.lower() == "openai":
        # OpenAI's response_format=json_schema linter rejects schemas with an
        # open map (our `additional_entities: dict[str, list[str]]`) even with
        # strict=False — "Invalid schema for response_format … 'required' must
        # include every key". function_calling binds the SAME pydantic schema as
        # a tool, whose argument-schema validation is lenient (open maps allowed)
        # and which OpenAI-direct accepts without the parallel_tool_calls issue
        # that only bites OpenRouter→Bedrock. (#1803)
        method = "function_calling"
    else:
        # Profile-driven method selection (#844 item 7). LangChain ≥1.1
        # exposes `model.profile` — a dict of capability flags powered by
        # models.dev. When the model reports native structured output
        # (`structured_output: True`), use json_schema mode: faster,
        # one round-trip, no tool-message overhead. Otherwise fall back
        # to function_calling, the lowest-common-denominator that every
        # tool-capable provider supports (OpenRouter-routed models that
        # advertise structured_output but don't actually support strict
        # mode silently degrade on json_schema; function_calling is safer).
        profile = getattr(model, "profile", None)
        if isinstance(profile, dict) and profile.get("structured_output"):
            method = "json_schema"
        else:
            method = "function_calling"
    # include_raw=True returns a dict with both the parsed Pydantic
    # instance and the raw AIMessage so we can surface usage_metadata
    # (token counts, finish reason) alongside the parsed result. Without
    # this the structured path was invisible to cost tracking — token
    # counts only flowed through plain chat() (#844 item 8).
    structured_kwargs: dict[str, Any] = {"include_raw": True}
    if method is not None:
        structured_kwargs["method"] = method
    # OpenAI's `json_schema` method defaults to strict=True, which validates the
    # emitted JSON-schema rigidly and 400s on schemas it considers malformed
    # (e.g. our open `additional_entities` map, or a `required` array that
    # doesn't list every property) — "Invalid schema for response_format".
    # strict=False keeps LangChain's structured coercion (output still parsed
    # into the pydantic model) without OpenAI's strict-schema gate. (#1803)
    if method == "json_schema":
        structured_kwargs["strict"] = False
    structured_model = model.with_structured_output(schema, **structured_kwargs)

    messages: list[Any] = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    # Wall-clock timeout (#844 robustness, mirrors chat()). Some
    # backends ignore the per-model timeout kwarg under HTTP keepalive;
    # asyncio.wait_for is the backstop.
    budget = _compute_timeout(config, "langchain")
    try:
        async with _remote_llm_call_slot(config):
            result = await asyncio.wait_for(
                structured_model.ainvoke(messages), timeout=budget,
            )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"LangChain {config.provider}/{config.model} structured call "
            f"exceeded {budget}s — provider hang"
        ) from exc
    except Exception as exc:
        _raise_provider_quota_error(config, exc)
        raise

    # `result` is a dict {'raw': AIMessage, 'parsed': Schema, 'parsing_error': ...}
    # when include_raw=True. Older code paths and tests that mocked
    # with_structured_output return the parsed instance directly — handle
    # both shapes so the rollout doesn't break consumers.
    parsed: BaseModel | None = None
    raw_message: Any = None
    if isinstance(result, dict) and "parsed" in result:
        parsed = result.get("parsed")
        raw_message = result.get("raw")
        parsing_error = result.get("parsing_error")
        if parsing_error and parsed is None:
            raise RuntimeError(
                f"LangChain {config.provider}/{config.model} structured "
                f"parse failed: {parsing_error}"
            )
    else:
        parsed = result

    # Log usage_metadata when present so it flows into the cost-tracking
    # collector (#852). AIMessage.usage_metadata is a dict with
    # input_tokens / output_tokens / total_tokens (LangChain ≥0.3 standard).
    usage = getattr(raw_message, "usage_metadata", None) if raw_message else None
    if isinstance(usage, dict) and usage:
        _record_usage(
            config.provider, config.model, "structured",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            method=method,
        )

    if parsed is None:
        raise RuntimeError(
            f"LangChain {config.provider}/{config.model} structured call "
            f"returned no parsed result (raw={raw_message!r})"
        )
    return parsed


async def chat_structured_with_fallback(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
    use_case: str | None = None,
    permissive_guardrails: bool = False,
) -> BaseModel:
    """Like chat_structured(), but falls back through $medium then $large
    when Apple Intelligence can't service the request (guardrail refusal
    #838 or unsupported locale #868).

    Mirrors chat_with_fallback() for the structured-output path. Lets
    extract_all, cleanup, and per-section extractors keep the local-first
    default while still completing on documents Apple Intelligence
    rejects (Spanish-LatAm court records, scholarly text with literary
    profanity, etc.).
    """
    try:
        return await chat_structured(
            prompt, schema, config, system=system,
            include_schema_in_prompt=include_schema_in_prompt,
            use_case=use_case,
            permissive_guardrails=permissive_guardrails,
        )
    except AppleUnavailableError as apple_exc:
        # Catches GuardrailViolationError, UnsupportedLocaleError, and
        # any future "Apple can't proceed" subclass uniformly.

        # #1027: a `decoding` / `generation` decode failure is often
        # transient — the grammar-constrained sampler missed a valid
        # path this time, but a single on-device retry frequently lands
        # one. Retry once before paying for the $large cloud model.
        # `context_overflow` / `schema` are NOT retried: the same chunk
        # and schema fail identically, so they go straight to fallback.
        if (
            isinstance(apple_exc, StructuredDecodeError)
            and apple_exc.kind in StructuredDecodeError.RETRYABLE_KINDS
        ):
            logger.warning(
                "Apple Intelligence structured decode failed (%s) — "
                "retrying once on-device before paid fallback.",
                apple_exc.kind,
            )
            try:
                return await chat_structured(
                    prompt, schema, config, system=system,
                    include_schema_in_prompt=include_schema_in_prompt,
                    use_case=use_case,
                    permissive_guardrails=permissive_guardrails,
                )
            except AppleUnavailableError as retry_exc:
                # Retry also failed — fall through to $large with the
                # retry's error as the operative cause.
                apple_exc = retry_exc

        if (
            isinstance(apple_exc, StructuredDecodeError)
            and include_schema_in_prompt is not False
            and apple_exc.kind in {"context_overflow", "schema"}
        ):
            logger.warning(
                "Apple Intelligence structured decode failed (%s) — "
                "retrying once on-device with include_schema_in_prompt=False.",
                apple_exc.kind,
            )
            try:
                return await chat_structured(
                    prompt,
                    schema,
                    config,
                    system=system,
                    include_schema_in_prompt=False,
                    use_case=use_case,
                    permissive_guardrails=permissive_guardrails,
                )
            except AppleUnavailableError as compact_retry_exc:
                apple_exc = compact_retry_exc

        last_failure: Exception | None = None
        attempted = False
        for tier, fallback_config, fallback_is_local in _iter_fallback_configs(
            config,
            original_config=config,
            error_name=type(apple_exc).__name__,
            kind="structured",
            origin_error=apple_exc,
        ):
            attempted = True
            cost_note = (
                "an on-device model — no API cost"
                if fallback_is_local
                else "a PAID remote model — this request now incurs cost"
            )
            logger.warning(
                "Apple Intelligence unavailable for structured call (%s); "
                "falling back to %s: $%s = %s/%s.",
                type(apple_exc).__name__,
                cost_note,
                tier,
                fallback_config.provider,
                fallback_config.model,
            )
            # The fallback provider is LangChain-based, so the Apple-only
            # include_schema_in_prompt parameter is ignored on that path.
            try:
                result = await chat_structured(
                    prompt,
                    schema,
                    fallback_config,
                    system=system,
                    use_case=use_case,
                    permissive_guardrails=permissive_guardrails,
                )
            except (ProviderQuotaError, AppleUnavailableError) as exc:
                last_failure = exc
                continue
            logger.info(
                "Structured fallback to $%s %s/%s succeeded.",
                tier,
                fallback_config.provider,
                fallback_config.model,
            )
            return result

        if attempted and last_failure is not None:
            raise last_failure
        raise apple_exc


# Apple Intelligence on-device model context window size. Documented at
# https://developer.apple.com/documentation/foundationmodels (4,096 tokens
# for the SystemLanguageModel as of macOS 26.x). When SDK 26.4 lands we'll
# replace this constant with a dynamic .contextSize lookup (#854).
APPLE_INTELLIGENCE_CONTEXT_SIZE = 4096

# Headroom we hold back from the context size as response budget. The
# model needs space to actually generate its output; we won't submit a
# prompt that consumes more than CONTEXT_SIZE - APPLE_RESPONSE_HEADROOM.
APPLE_RESPONSE_HEADROOM = 1024


def estimate_token_count(text: str) -> int:
    """Heuristic estimator for token count (#848 proactive variant).

    Apple's authoritative SystemLanguageModel.tokenUsage(for:) requires
    the macOS 26.4 SDK (we're on 26.2 today). Until SDK 26.4 lands and
    we can wire #854 in, we approximate via char count.

    Heuristic per Apple's docs: a single token ≈ 3–4 characters in
    English/Spanish/German, ≈ 1 token per character in CJK languages.
    Symbols and digits often consume more tokens than letters (e.g.
    a phone number `+1-(408)-555-0123` can use 10+ tokens for ~16
    chars). We use len(text) // 3 — biased high to give a conservative
    over-estimate, which is the safe direction for budgeting (better
    to chunk a request that would fit than fail one we thought fit).

    Use this BEFORE submitting an Apple Intelligence call to detect
    likely context-window overflow. The reactive chunked-retry path in
    cleanup.py is a backstop; this is the proactive optimization.
    """
    if not text:
        return 0
    # // 3 is intentionally conservative — most English/Spanish text
    # tokenizes at ~4 chars/token, but we'd rather overcount than risk
    # submitting an oversized prompt and burning seconds on a failed
    # generation. CJK callers should pass a larger safety margin via
    # the surrounding budget logic.
    return len(text) // 3


def apple_intelligence_fits_in_context(
    prompt: str,
    instructions: str | None = None,
    schema_overhead_tokens: int = 0,
    response_headroom: int = APPLE_RESPONSE_HEADROOM,
    context_size: int = APPLE_INTELLIGENCE_CONTEXT_SIZE,
) -> bool:
    """Check whether (prompt + instructions + schema_overhead + response
    headroom) fits in Apple Intelligence's context window. Returns True
    when the request is likely to fit, False when the caller should
    chunk before submitting.

    `schema_overhead_tokens` is the caller's estimate of what the
    grammar-constrained schema will add when `includeSchemaInPrompt=True`
    — for our extraction schemas this is roughly 200-400 tokens. Pass 0
    when calling with `include_schema_in_prompt=False`.

    `response_headroom` is the number of tokens we reserve for the
    model's output. Cleanup needs ~512 (groups + aliases for a typical
    list); narrative summary needs ~1024+; default 1024 is safe.
    """
    estimate = estimate_token_count(prompt)
    if instructions:
        estimate += estimate_token_count(instructions)
    estimate += schema_overhead_tokens
    return estimate + response_headroom <= context_size


_TimeoutKind = _Literal["langchain", "apple_chat", "apple_structured"]


def _compute_timeout(
    config: LLMConfig,
    kind: _TimeoutKind,
    *,
    schema_chars: int | None = None,
) -> float:
    """Single source of truth for wall-clock timeouts on every LLM call
    path (#855, #862, #867).

    Three formulas, scaled by config.timeout, config.max_tokens, and
    (for Apple structured) the schema size. Outputs are clamped to
    sensible floors and ceilings so a misconfigured config can't
    starve legitimate work or leave a stuck call hanging forever.

    Knobs:
    - config.timeout: base seconds, scaled by `kind` factor
    - config.max_tokens: longer outputs get more wall-clock budget;
      a 4K-token narrative legitimately takes longer than a 200-token
      tag list. Reference baseline = 1024 tokens (1.0x scale).
    - schema_chars: only used for `apple_structured`. A 6-section
      _Extraction (~5K chars) needs more budget than a 5-name dedup
      (~500 chars). Reference baseline = 2K chars.

    Replaces the three scattered formulas (#855):
    - _langchain_timeout_budget (config.timeout × 5, [60, 600])
    - apple chat (max(30, config.timeout) or 120)
    - apple structured (max(180, config.timeout × 3) or 300)
    """
    base = config.timeout if config.timeout else 60

    output_factor = max(0.25, (config.max_tokens or 1024) / 1024)

    if kind == "langchain":
        # LangChain ainvoke is wrapped in asyncio.wait_for as a backstop
        # for backends that ignore their own timeout under HTTP keepalive.
        # Generous: 5× base × output factor.
        budget = base * 5 * output_factor
        return float(min(600, max(60, budget)))

    if kind == "apple_chat":
        # Free-form generation finishes faster than guided decoding.
        # Tighter budget so a hung session doesn't block too long.
        budget = base * output_factor
        return float(min(180, max(30, budget)))

    if kind == "apple_structured":
        # Guided decoding has per-token overhead proportional to the
        # schema's branching factor. Scale by the schema's serialized
        # size as a cheap proxy.
        schema_factor = max(1.0, (schema_chars or 2000) / 2000)
        budget = base * 2 * output_factor * schema_factor
        return float(min(600, max(60, budget)))

    raise ValueError(f"Unknown timeout kind: {kind!r}")


def _langchain_timeout_budget(config: LLMConfig) -> float:
    """Backwards-compat shim — delegates to _compute_timeout. Kept so
    existing imports don't break; new code should call _compute_timeout
    directly."""
    return _compute_timeout(config, "langchain")


def _fm_bridge_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    # This body now lives at fichero/llm/__init__.py (#2566); its old
    # location was fichero/llm.py, one level shallower, so the parent-walk
    # depths below are bumped by one relative to the pre-move code.
    return [
        here.parent.parent / "resources" / "bin" / "fm-bridge",
        here.parent.parent / "bin" / "fm-bridge" / "fm-bridge",
        here.parents[4] / "bin" / "fm-bridge" / "fm-bridge",
        Path("fichero-server/bin/fm-bridge/fm-bridge").resolve(),
    ]


def _find_fm_bridge_binary() -> Path | None:
    return next(
        (
            candidate
            for candidate in _fm_bridge_candidates()
            if candidate.is_file() and candidate.stat().st_mode & 0o111
        ),
        None,
    )


def _fm_bridge_unavailable_reason() -> str | None:
    from fichero_server.llm.local_inference import get_local_inference_capabilities

    if not get_local_inference_capabilities().subprocess_capable:
        return "Apple Intelligence is not available on this device"
    return None


async def probe_apple_intelligence_bridge() -> tuple[bool, str | None]:
    unavailable_reason = _fm_bridge_unavailable_reason()
    if unavailable_reason is not None:
        return False, unavailable_reason
    binary = _find_fm_bridge_binary()
    if binary is None:
        return False, _FM_BRIDGE_MISSING_MESSAGE

    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            "--probe",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
    except Exception as exc:  # noqa: BLE001
        return False, f"Couldn't run fm-bridge: {exc}"

    try:
        result = json.loads(stdout_bytes.decode())
    except json.JSONDecodeError:
        return False, stderr_bytes.decode().strip() or "fm-bridge probe returned invalid JSON"
    return bool(result.get("available")), result.get("reason")


# Cache + lock for the async locale probe. We can't use lru_cache on a
# coroutine (it caches the coroutine object, not the resolved value), so
# we do explicit dict + asyncio.Lock — same effect, async-safe.
_LOCALE_SUPPORT_CACHE: dict[str, bool] = {}
_LOCALE_SUPPORT_LOCK: asyncio.Lock | None = None


async def apple_intelligence_supports_locale(locale: str) -> bool:
    """Check whether Apple Intelligence's on-device model supports a
    given locale (#849). Returns True when the model accepts the locale
    for prompts/responses, False when it doesn't.

    Cached at the process level — locale support depends only on the
    on-device model and doesn't change at runtime. The cache + lock
    pattern is async-safe (lru_cache can't wrap coroutines correctly).

    Implementation: spawns fm-bridge --supports-locale <code> via
    asyncio.create_subprocess_exec — non-blocking, fits the rest of
    the LLM stack's async shape. Falls back to False on any failure
    (binary missing, model unavailable, etc.) so callers don't
    accidentally route to a non-functional path.

    Use this before submitting an Apple Intelligence call when the
    document language is known and might be unsupported. Cheaper than
    discovering it via mid-generation `unsupportedLanguageOrLocale` error.
    """
    import json as _json

    if locale in _LOCALE_SUPPORT_CACHE:
        return _LOCALE_SUPPORT_CACHE[locale]

    global _LOCALE_SUPPORT_LOCK
    if _LOCALE_SUPPORT_LOCK is None:
        _LOCALE_SUPPORT_LOCK = asyncio.Lock()

    async with _LOCALE_SUPPORT_LOCK:
        # Re-check after acquiring lock — concurrent first-callers race
        # to compute, but only one actually shells out.
        if locale in _LOCALE_SUPPORT_CACHE:
            return _LOCALE_SUPPORT_CACHE[locale]

        if _fm_bridge_unavailable_reason() is not None:
            _LOCALE_SUPPORT_CACHE[locale] = False
            return False

        binary = _find_fm_bridge_binary()
        if binary is None:
            logger.debug("fm-bridge not found; assuming locale unsupported")
            _LOCALE_SUPPORT_CACHE[locale] = False
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                str(binary), "--supports-locale", locale,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=5,
            )
            if proc.returncode != 0:
                _LOCALE_SUPPORT_CACHE[locale] = False
                return False
            payload = _json.loads(stdout.decode())
            supported = bool(payload.get("supported", False))
            _LOCALE_SUPPORT_CACHE[locale] = supported
            return supported
        except (asyncio.TimeoutError, _json.JSONDecodeError, OSError) as exc:
            logger.debug(f"fm-bridge --supports-locale {locale!r} failed: {exc}")
            _LOCALE_SUPPORT_CACHE[locale] = False
            return False


def _pydantic_to_apple_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic class into the schema-tree shape fm-bridge
    builds DynamicGenerationSchema from. Inlines `$ref` definitions
    against `$defs` so the bridge doesn't need cross-file references.

    Pydantic emits JSON Schema; Apple's DynamicGenerationSchema is a
    similar tree with object/array/primitive shape but a different
    property layout (list of `{name, schema, optional}` instead of a
    `properties` dict + separate `required` list). This helper bridges
    the two without depending on any OpenAPI-style JSON-Schema library.

    Supported Pydantic shapes:
    - object types (BaseModel subclasses, nested)
    - list[T] arrays (with item type T)
    - primitives: str, int, float, bool
    - Optional[T] (anyOf with null) — flattened, marked optional
    - Field(description=...) — propagates as `description`
    - $ref / $defs — resolved (inlined)

    NOT supported (raise on attempt):
    - Discriminated unions (anyOf with non-null branches)
    - Recursive types (model referencing itself)
    - Enum types (str enums in particular)
    - Annotated[T, ...] with custom validators
    - JSON Schema `format` keywords (date, uri, email, etc.)

    If your tool needs one of the unsupported shapes, either decompose
    into supported primitives or extend this converter (#852-adjacent
    work). The grammar-constrained generation will still work without
    these — they just won't be expressed in the schema tree the bridge
    consumes.
    """
    full = model.model_json_schema()
    defs = full.get("$defs", {})

    _SUPPORTED_PRIMITIVES = {"string", "integer", "number", "boolean"}
    # JSON Schema `format` keywords (date, uri, email, …) imply runtime
    # validation that Apple's DynamicGenerationSchema doesn't enforce —
    # silently dropping them would let through prompts the caller thinks
    # are validated. Fail loud so the caller decomposes into supported
    # primitives or extends this converter (#856).
    _UNSUPPORTED_FORMAT_HINT = (
        "JSON Schema 'format' keywords are not modeled by Apple "
        "DynamicGenerationSchema; remove the format constraint and "
        "validate post-hoc, or decompose the field."
    )

    def _fail(field_path: str, msg: str) -> None:
        raise ValueError(
            f"_pydantic_to_apple_schema: unsupported shape on "
            f"'{field_path}' — {msg} (see #856)"
        )

    # Shared across one conversion: the set of $defs names currently
    # being expanded. Detects recursive types (a model whose definition
    # eventually $refs itself) — DynamicGenerationSchema can't express
    # them, so fail loud instead of recursing until the stack blows.
    expanding: set[str] = set()

    def convert(node: dict[str, Any], field_path: str = "$") -> dict[str, Any]:
        # Walk $refs while tracking which definitions are currently in
        # the expansion stack. Self-referential models hit `expanding`
        # second time around and fail loud here.
        ref_stack: list[str] = []
        try:
            while "$ref" in node:
                ref = node["$ref"]
                if not ref.startswith("#/$defs/"):
                    _fail(field_path, f"unexpected $ref shape: {ref!r}")
                name = ref.split("/")[-1]
                if name in expanding:
                    _fail(
                        field_path,
                        f"recursive type detected (cycle through $defs/{name}); "
                        "Apple DynamicGenerationSchema can't express recursive "
                        "shapes — flatten or bound the recursion at definition time",
                    )
                if name not in defs:
                    _fail(field_path, f"$ref target $defs/{name} not found")
                expanding.add(name)
                ref_stack.append(name)
                node = {**defs[name]}

            # anyOf is supported only when it's Optional[T] — exactly one
            # non-null branch. Discriminated unions (multiple non-null
            # branches) aren't expressible in DynamicGenerationSchema today.
            if "anyOf" in node and not node.get("type"):
                non_null = [b for b in node["anyOf"] if b.get("type") != "null"]
                if len(non_null) == 1:
                    return convert(non_null[0], field_path)
                _fail(
                    field_path,
                    f"anyOf with {len(non_null)} non-null branches "
                    "(only Optional[T] = single non-null branch is supported); "
                    "discriminated unions need a custom converter or flat decomposition",
                )

            # `enum` keyword (str enums, literal types) — not modeled today.
            # Failing loud lets a future converter add support without
            # breaking surprised callers.
            if "enum" in node:
                _fail(
                    field_path,
                    f"enum types not yet supported (values: {node['enum']!r}); "
                    "use a plain string field and validate post-hoc, or extend the converter",
                )

            type_ = node.get("type", "object")
            if type_ not in {"object", "array"} | _SUPPORTED_PRIMITIVES:
                _fail(field_path, f"unsupported type: {type_!r}")

            if type_ in _SUPPORTED_PRIMITIVES and "format" in node:
                _fail(
                    field_path,
                    f"format={node['format']!r}: {_UNSUPPORTED_FORMAT_HINT}",
                )

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
                    child_path = (
                        f"{field_path}.{pname}" if field_path != "$" else pname
                    )
                    pschema = convert(psub, child_path)
                    pdesc = psub.get("description")
                    entry: dict[str, Any] = {"name": pname, "schema": pschema}
                    if pdesc:
                        entry["description"] = pdesc
                    if pname not in required:
                        entry["optional"] = True
                    props_out.append(entry)
                out["properties"] = props_out
            elif type_ == "array":
                child_path = f"{field_path}[]"
                items = node.get("items", {"type": "string"})
                out["items"] = convert(items, child_path)
                if (mn := node.get("minItems")) is not None:
                    out["minimum_elements"] = mn
                if (mx := node.get("maxItems")) is not None:
                    out["maximum_elements"] = mx
            # Primitives: nothing extra.
            return out
        finally:
            for name in ref_stack:
                expanding.discard(name)
        # Primitives (string/integer/number/boolean): nothing extra.

        return out

    return convert(full)


async def _apple_intelligence_structured(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
    system: str | None = None,
    include_schema_in_prompt: bool | None = None,
    use_case: str | None = None,
    permissive_guardrails: bool = False,
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

    unavailable_reason = _fm_bridge_unavailable_reason()
    if unavailable_reason is not None:
        raise RuntimeError(unavailable_reason)

    binary = _find_fm_bridge_binary()
    if binary is None:
        raise RuntimeError(_FM_BRIDGE_MISSING_MESSAGE)

    apple_schema_dict = _pydantic_to_apple_schema(schema)
    request: dict[str, Any] = {
        "prompt": prompt,
        "instructions": system or "",
        "schema": apple_schema_dict,
    }
    if include_schema_in_prompt is not None:
        request["include_schema_in_prompt"] = include_schema_in_prompt
    # contentTagging useCase (#853). When the schema is a flat list-of-
    # strings (keywords), the specialised tagging variant produces
    # crisper output. fm-bridge accepts use_case on both free-form and
    # structured paths since chatModel is shared.
    if use_case in {"content_tagging"}:
        request["use_case"] = use_case
    if permissive_guardrails:
        request["guardrails"] = "permissive"
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
    # Subprocess timeout for structured calls scales with schema size
    # (#862) and config.max_tokens (#867) so a 5-name dedup doesn't pay
    # the same wall-clock as a 6-section _Extraction. (#855)
    schema_chars = len(_json.dumps(apple_schema_dict)) if apple_schema_dict else 2000
    structured_budget = _compute_timeout(
        config, "apple_structured", schema_chars=schema_chars,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(payload),
            timeout=structured_budget,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"Apple Intelligence (timeout): fm-bridge exceeded "
            f"{structured_budget}s for structured prompt — provider hang"
        )

    if proc.returncode != 0:
        _raise_from_bridge_stderr(stderr_bytes, proc.returncode)

    bridge_result = _json.loads(stdout_bytes.decode())
    response_json = bridge_result.get("response_json", "")
    if not _log_apple_usage_from_bridge(config, bridge_result, kind="structured"):
        # Fallback when bridge payload has no token usage.
        _log_apple_usage_estimate(config, prompt, response_json, kind="structured")
    # Parse the grammar-constrained JSON (always valid by construction)
    # into the Pydantic class. Validation here is belt-and-suspenders —
    # the schema constraint should already guarantee shape, but a typed
    # parse gives downstream code a real Pydantic instance to consume.
    return schema.model_validate_json(response_json)


# =============================================================================
# LangChain Integration
# =============================================================================


_OPENAI_COMPATIBLE_BASE_URLS: dict[str, str] = {
    # Providers that speak OpenAI's chat-completions API but live at a
    # different base URL. ChatOpenAI handles them via base_url override;
    # the per-config api_base wins when set, these are the defaults.
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "omlx": "http://localhost:8000/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "xai": "https://api.x.ai/v1",
    "perplexity": "https://api.perplexity.ai",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "huggingface": "https://router.huggingface.co/v1",
}

# Providers that speak OpenAI but accept any string for the api_key
# field — the actual auth is unsigned localhost. We pass a placeholder
# so ChatOpenAI's required-key check doesn't reject empty.
_KEYLESS_OPENAI_COMPATIBLE: set[str] = {"ollama", "lmstudio", "omlx"}
_MANAGED_OMLX_RESTART_CAP = 2


async def _ensure_managed_local_provider_ready(config: LLMConfig) -> None:
    if config.provider.lower() != "omlx":
        return
    from fichero_server.api.routes.ai.local_inference import _configured_omlx_profile, _manager_for_profile
    from fichero_server.llm.local_inference import (
        LocalModelHardwareError as LocalInferenceHardwareError,
        LocalInferenceRuntimeMissingError,
        LocalModelNotInstalledError,
        LocalProviderStartupPolicy,
        LocalServiceState,
    )

    profile = _configured_omlx_profile()
    effective_base_url = (config.api_base or _OPENAI_COMPATIBLE_BASE_URLS["omlx"]).rstrip("/")
    if not profile.managed_by_app or str(profile.base_url).rstrip("/") != effective_base_url:
        return

    manager = _manager_for_profile(profile.id)
    try:
        if profile.startup_policy == LocalProviderStartupPolicy.manual:
            status = await manager.health() if manager.state != LocalServiceState.stopped else manager.status()
        elif manager.state != LocalServiceState.stopped and not manager.process.is_running():
            if manager.restart_count >= _MANAGED_OMLX_RESTART_CAP:
                status = await manager.health()
            else:
                status = await manager.restart_after_crash()
        else:
            status = await manager.start()
    except LocalInferenceRuntimeMissingError as exc:
        raise LocalModelRuntimeMissingError(str(exc)) from exc
    except LocalInferenceHardwareError as exc:
        raise LocalModelHardwareError(str(exc)) from exc
    except LocalModelNotInstalledError as exc:
        raise LocalModelUnavailableError(str(exc)) from exc

    if not status.healthy:
        detail = status.last_error or "local model unavailable"
        if profile.startup_policy == LocalProviderStartupPolicy.manual:
            detail = f"Managed local model is manual-start only and not healthy: {detail}"
        raise LocalModelUnavailableError(detail)

# Sentinel for dict.pop "was-present" detection without colliding on a
# legitimately-stored None value.
_MISSING = object()


async def _openrouter_strip_parallel_tool_use(request: Any) -> None:
    """httpx request hook: drop the `parallel_tool_calls` field (and the
    nested `tool_choice.disable_parallel_tool_use` key) from OpenRouter
    chat-completion bodies before they leave the box.

    Why: LangChain's `with_structured_output(method="function_calling")`
    path sets `parallel_tool_calls=False` so the model returns exactly one
    tool call. OpenAI-direct accepts this, but OpenRouter forwards Claude
    to Amazon Bedrock, whose schema validator hard-400s on the resulting
    `tool_choice` extension key `disable_parallel_tool_use` —
    "extraneous key [disable_parallel_tool_use] is not permitted" — failing
    every structured call (#1802). We already bind exactly one schema tool,
    so single-tool behaviour is the effective default; dropping the hint is
    lossless and keeps the reliable tool-calling path instead of degrading
    to json_mode (which OpenAI routes reject for lacking the literal word
    "json") or strict json_schema (which Bedrock-Claude answers with an
    empty body).

    Security: rewrites only the request *body* shape — never touches
    headers' auth, TLS, or the URL — and logs nothing (no payloads, no
    keys). Non-JSON bodies and bodies without the offending key pass
    through untouched.
    """
    import json as _json

    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        return
    try:
        body = _json.loads(request.content.decode())
    except Exception:
        # Streaming/multipart or anything we can't parse — leave it alone.
        return
    if not isinstance(body, dict):
        return

    changed = body.pop("parallel_tool_calls", _MISSING) is not _MISSING
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict):
        if tool_choice.pop("disable_parallel_tool_use", _MISSING) is not _MISSING:
            changed = True
    if not changed:
        return

    import httpx

    new_content = _json.dumps(body).encode()
    request.stream = httpx.ByteStream(new_content)
    request._content = new_content
    request.headers["content-length"] = str(len(new_content))


_HTTPX_ASYNC_CLIENT_CACHE: weakref.WeakKeyDictionary[
    Any, dict[tuple[str, str, str, str], Any]
] = weakref.WeakKeyDictionary()
_HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP: dict[tuple[str, str, str, str], Any] = {}
_HTTPX_ASYNC_CLIENT_CACHE_LOCK = threading.Lock()


def _get_shared_httpx_async_client(
    *,
    provider: str,
    base_url: str,
    model_name: str,
    api_key: str | None,
) -> Any:
    """Return a process-global ``httpx.AsyncClient`` for one client identity.

    The transport client is cached per event loop because httpx async clients
    are loop-affine. Within a loop, calls that share the same provider /
    endpoint / model / API key identity reuse one connection pool.
    """
    import httpx

    cache_key = (provider, base_url, model_name, api_key or "")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        cached_client = _HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP.get(cache_key)
        if cached_client is not None:
            return cached_client

        with _HTTPX_ASYNC_CLIENT_CACHE_LOCK:
            cached_client = _HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP.get(cache_key)
            if cached_client is not None:
                return cached_client

            client_kwargs: dict[str, Any] = {}
            if provider == "openrouter":
                client_kwargs["event_hooks"] = {
                    "request": [_openrouter_strip_parallel_tool_use],
                }
            cached_client = httpx.AsyncClient(**client_kwargs)
            _HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP[cache_key] = cached_client
            return cached_client

    cached_by_loop = _HTTPX_ASYNC_CLIENT_CACHE.get(loop)
    if cached_by_loop is not None:
        cached_client = cached_by_loop.get(cache_key)
        if cached_client is not None:
            return cached_client

    with _HTTPX_ASYNC_CLIENT_CACHE_LOCK:
        cached_by_loop = _HTTPX_ASYNC_CLIENT_CACHE.get(loop)
        if cached_by_loop is None:
            cached_by_loop = {}
            _HTTPX_ASYNC_CLIENT_CACHE[loop] = cached_by_loop

        cached_client = cached_by_loop.get(cache_key)
        if cached_client is not None:
            return cached_client

        client_kwargs: dict[str, Any] = {}
        if provider == "openrouter":
            client_kwargs["event_hooks"] = {
                "request": [_openrouter_strip_parallel_tool_use],
            }
        cached_client = httpx.AsyncClient(**client_kwargs)
        cached_by_loop[cache_key] = cached_client
        return cached_client


def _build_langchain_model(config: LLMConfig) -> Any:
    """Create a LangChain ChatModel from Fichero LLMConfig.

    Architecture (#844):
    - Native providers (openai, anthropic, google_genai, mistralai,
      cohere) → `init_chat_model("provider:model")`. The canonical
      LangChain ≥1.0 entrypoint; new model names work without
      LangChain version bumps because the model string is parsed
      dynamically. Per the late-2025 LangChain Models docs, this is
      now the recommended way to instantiate chat models.
    - OpenRouter → `ChatOpenRouter` (langchain-openrouter package).
      Per the LangChain docs: "For OpenRouter and LiteLLM, prefer the
      dedicated integrations" — provider-routing fields and tool-
      support flags get preserved instead of being stripped by a bare
      ChatOpenAI + base_url override.
    - OpenAI-compatible third parties (groq, together, deepseek, xai,
      etc.) → ChatOpenAI with a per-provider default base_url. The
      _OPENAI_COMPATIBLE_BASE_URLS table is the single source of
      truth — adding a new provider is a one-line change.
    - Azure OpenAI → AzureChatOpenAI (different param shape).
    - AWS Bedrock → ChatBedrock (different package).
    - apple → ChatAppleIntelligence, a thin BaseChatModel adapter over
      the existing fm-bridge chat()/chat_structured() helpers.

    `max_retries=10` (LangChain default is 6) is set on every model so
    transient OpenRouter / Anthropic blips recover silently with
    exponential backoff + jitter.
    """
    provider = config.provider.lower()
    model_name = config.model
    api_key = _resolve_api_key(config)

    # Common parameters. max_retries=10 bumps LangChain's default 6 so
    # transient transport failures (network blips, 429, 5xx) recover
    # without breaking long parallel runs.
    common_params: dict[str, Any] = {
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "max_retries": 10,
    }

    # Reasoning effort routing (#859). Each provider exposes the knob
    # differently:
    #   - Anthropic native: thinking={'type':'enabled', 'budget_tokens':N}
    #     and the API requires temperature=1 when thinking is on.
    #   - OpenAI o-series: reasoning_effort=<level> kwarg.
    #   - OpenRouter: extra_body={'reasoning':{'effort':<level>}} per its
    #     normalized request shape; works for both Claude and gpt-5 routes.
    # Apple Intelligence has no reasoning surface today (handled outside
    # this function, in _apple_intelligence_chat) so the field is silently
    # ignored on that path.
    _REASONING_BUDGETS = {"low": 1024, "medium": 4096, "high": 16000}
    effort = (config.reasoning_effort or "off").lower()
    reasoning_on = effort in _REASONING_BUDGETS

    # Native LangChain providers via init_chat_model. The "provider:model"
    # string form is the canonical entrypoint per docs.langchain.com.
    # init_chat_model imports the right package automatically; we don't
    # have to maintain per-provider class imports.
    _NATIVE_PROVIDER_PREFIX = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "google_genai",
        "mistral": "mistralai",
        "cohere": "cohere",
        "bedrock": "bedrock",
    }
    if provider in _NATIVE_PROVIDER_PREFIX:
        from langchain.chat_models import init_chat_model

        prefix = _NATIVE_PROVIDER_PREFIX[provider]
        kwargs = dict(common_params)
        if api_key:
            kwargs["api_key"] = api_key
        if provider == "openai" and config.api_base:
            # OpenAI proper accepts a custom base_url for org proxies /
            # corporate gateways. Pass through when set; pure init_chat_model
            # doesn't expose it via the model string.
            kwargs["base_url"] = config.api_base
        if provider == "bedrock":
            # ChatBedrock takes region_name, not api_key.
            kwargs.pop("api_key", None)
            kwargs["region_name"] = config.extra.get("region", "us-east-1")
        if reasoning_on:
            if provider == "anthropic":
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": _REASONING_BUDGETS[effort],
                }
                # Anthropic requires temperature=1 when thinking is on.
                kwargs["temperature"] = 1.0
            elif provider == "openai":
                # o-series accepts the canonical reasoning_effort kwarg.
                kwargs["reasoning_effort"] = effort
            # Other natives (google, mistral, cohere, bedrock) don't expose
            # a reasoning surface today — silently no-op.
        return init_chat_model(f"{prefix}:{model_name}", **kwargs)

    # OpenRouter — uses ChatOpenAI with the OpenRouter base URL. We
    # tried langchain-openrouter's ChatOpenRouter (per LangChain's late-
    # 2025 docs recommendation) but its ainvoke hangs indefinitely on
    # claude-sonnet-4.6 calls — direct curl to the same endpoint with
    # the same model + key returns in <1s, isolating the bug to the SDK.
    # Filed as a follow-up; for 0.0.2 we keep the proven ChatOpenAI
    # path which has worked reliably for OpenRouter for months.
    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        base_url = config.api_base or "https://openrouter.ai/api/v1"
        kwargs = dict(common_params)
        if reasoning_on:
            # OpenRouter normalizes reasoning across underlying providers
            # via the `reasoning` extra_body field — works for Claude
            # (thinking) and gpt-5/o-series (reasoning_effort) alike.
            kwargs["extra_body"] = {"reasoning": {"effort": effort}}
        # Strip `parallel_tool_calls` / `disable_parallel_tool_use` from the
        # outgoing body so function_calling structured output survives the
        # OpenRouter→Bedrock-Claude route (#1802). See
        # `_openrouter_strip_parallel_tool_use`.
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            http_async_client=_get_shared_httpx_async_client(
                provider=provider,
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
            ),
            **kwargs,
        )

    # OpenAI-compatible third parties: ChatOpenAI with per-provider
    # default base_url (per-config api_base wins when set).
    if provider in _OPENAI_COMPATIBLE_BASE_URLS:
        from langchain_openai import ChatOpenAI

        base_url = config.api_base or _OPENAI_COMPATIBLE_BASE_URLS[provider]
        effective_key = api_key
        if provider in _KEYLESS_OPENAI_COMPATIBLE and not effective_key:
            effective_key = provider  # placeholder — local servers ignore it
        return ChatOpenAI(
            model=model_name,
            api_key=effective_key,
            base_url=base_url,
            http_async_client=_get_shared_httpx_async_client(
                provider=provider,
                base_url=base_url,
                model_name=model_name,
                api_key=effective_key,
            ),
            **common_params,
        )

    # Azure OpenAI — different param shape (azure_endpoint + api_version).
    if provider == "azure":
        from langchain_openai import AzureChatOpenAI

        base_url = config.api_base or ""
        return AzureChatOpenAI(
            model=model_name,
            api_key=api_key,
            azure_endpoint=config.api_base,
            api_version=config.extra.get("api_version", "2024-02-01"),
            http_async_client=_get_shared_httpx_async_client(
                provider=provider,
                base_url=base_url,
                model_name=model_name,
                api_key=api_key,
            ),
            **common_params,
        )

    if provider == "apple":
        return _chat_apple_intelligence_cls()(config=config)

    if not provider:
        raise ValueError(
            "LLM provider not configured. Please set a provider on the "
            "workflow or node."
        )
    raise ValueError(
        f"Unknown LLM provider: '{provider}'. "
        f"Supported: openai, anthropic, google, mistral, cohere, bedrock, "
        f"openrouter, ollama, lmstudio, groq, together, deepseek, dashscope, "
        f"xai, perplexity, fireworks, huggingface, azure, deepl, apple"
    )


def _cache_langchain_model(
    cache: OrderedDict[_ModelCacheKey, Any],
    cache_key: _ModelCacheKey,
    config: LLMConfig,
) -> Any:
    cached_model = cache.get(cache_key)
    if cached_model is not None:
        cache.move_to_end(cache_key)
        return cached_model

    cached_model = _build_langchain_model(config)
    cache[cache_key] = cached_model
    cache.move_to_end(cache_key)
    while len(cache) > _LANGCHAIN_MODEL_CACHE_SIZE:
        cache.popitem(last=False)
    return cached_model


def get_langchain_model(config: LLMConfig) -> Any:
    """Return a cached LangChain ChatModel for one config identity."""
    api_key_identity = _resolve_api_key(config) or ""
    cache_key = _langchain_model_cache_key(
        config,
        api_key_identity=api_key_identity,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        with _LANGCHAIN_MODEL_CACHE_LOCK:
            return _cache_langchain_model(
                _LANGCHAIN_MODEL_CACHE_NO_LOOP,
                cache_key,
                config,
            )

    with _LANGCHAIN_MODEL_CACHE_LOCK:
        cached_by_loop = _LANGCHAIN_MODEL_CACHE.get(loop)
        if cached_by_loop is None:
            cached_by_loop = OrderedDict()
            _LANGCHAIN_MODEL_CACHE[loop] = cached_by_loop
        return _cache_langchain_model(cached_by_loop, cache_key, config)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Config
    "LLMConfig",
    "LLMBatchItemError",
    "LocalOnlyViolationError",
    "is_local_only",
    # Chat
    "chat",
    "chat_batch",
    # Vision
    "vision",
    "vision_batch",
    "is_recognition_only_vision_model",
    # Embeddings
    "embed",
    "aembed",
    # Tools
    "chat_with_tools",
    # Structured
    "structured_output",
    # Translation
    "translate_text",
    # Model info
    "get_model_info",
    "get_model_cost",
    "estimate_cost",
    "list_models_for_provider",
    # Key resolution
    "get_api_key",
    "clear_api_key_cache",
    # LangChain
    "get_langchain_model",
]
