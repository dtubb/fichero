"""
Unit tests for fichero.llm module (thinking models support).

Tests core LLM functionality including:
- Thinking model response parsing
- Model type detection
- Hugging Face Inference API calls
"""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

import fichero.llm as llm
from fichero.llm import (
    _build_fallback_config,
    apple_intelligence_fits_in_context,
    estimate_token_count,
    is_thinking_model,
    LLMBatchItemError,
    LLMConfig,
    LocalOnlyViolationError,
    parse_thinking_response,
    vision_inference_api,
)
from fichero.local_inference import LocalProviderStartupPolicy, LocalServiceState


class _StructuredResult(BaseModel):
    answer: str


# =============================================================================
# parse_thinking_response() Tests
# =============================================================================

def test_parse_thinking_response_with_both_tags():
    """Test parsing response with both <think> and <answer> tags."""
    text = "<think>Let me analyze this image...</think><answer>Result: 42</answer>"
    answer, thinking = parse_thinking_response(text)

    assert answer == "Result: 42"
    assert thinking == "Let me analyze this image..."


def test_parse_thinking_response_multiline():
    """Test parsing response with multiline thinking."""
    text = """<think>
First, I'll identify the key elements.
Then I'll structure the output.
Finally, I'll format as markdown.
</think><answer>
# Document Title

Content here
</answer>"""
    answer, thinking = parse_thinking_response(text)

    assert "# Document Title" in answer
    assert "First, I'll identify" in thinking
    assert "Finally, I'll format" in thinking


def test_parse_thinking_response_no_tags():
    """Test parsing plain response without thinking tags."""
    text = "This is a simple answer without any thinking process."
    answer, thinking = parse_thinking_response(text)

    assert answer == text
    assert thinking is None


def test_parse_thinking_response_only_answer_tag():
    """Test parsing with only <answer> tag."""
    text = "<answer>Just the answer</answer>"
    answer, thinking = parse_thinking_response(text)

    assert answer == "Just the answer"
    assert thinking is None


def test_parse_thinking_response_only_think_tag():
    """Test parsing with only <think> tag (malformed)."""
    text = "<think>Some reasoning...</think>"
    answer, thinking = parse_thinking_response(text)

    # Should extract thinking but use full text as answer
    assert answer == text
    assert thinking == "Some reasoning..."


def test_parse_thinking_response_incomplete_tags():
    """Test parsing with incomplete/malformed tags."""
    text = "<think>Incomplete reasoning"
    answer, thinking = parse_thinking_response(text)

    # Should treat as plain text
    assert answer == text
    assert thinking is None


def test_parse_thinking_response_nested_content():
    """Test parsing with nested similar-looking text."""
    text = "<think>Analyzing <code>tags</code> in content</think><answer>The code is valid</answer>"
    answer, thinking = parse_thinking_response(text)

    assert answer == "The code is valid"
    assert "Analyzing <code>tags</code> in content" == thinking


def test_parse_thinking_response_whitespace_handling():
    """Test that whitespace is properly stripped."""
    text = "<think>  \n  Reasoning with spaces  \n  </think><answer>  \n  Clean answer  \n  </answer>"
    answer, thinking = parse_thinking_response(text)

    assert answer == "Clean answer"
    assert thinking == "Reasoning with spaces"


# =============================================================================
# is_thinking_model() Tests
# =============================================================================

def test_is_thinking_model_numarkdown():
    """Test detection of NuMarkdown thinking models."""
    assert is_thinking_model("numind/NuMarkdown-8B-Thinking")
    assert is_thinking_model("numind/NuMarkdown-8B-reasoning")
    assert is_thinking_model("numind/numarkdown-large")  # Case insensitive


def test_is_thinking_model_deepseek():
    """Test detection of DeepSeek reasoner models."""
    assert is_thinking_model("deepseek/deepseek-reasoner-v1")
    assert is_thinking_model("DeepSeek/DeepSeek-Reasoner-V2")


def test_is_thinking_model_qwen():
    """Test detection of Qwen reasoning models."""
    assert is_thinking_model("qwen/qwq-32b-preview")
    assert is_thinking_model("Qwen/QwQ-7B")


def test_is_thinking_model_keyword_detection():
    """Test detection via thinking/reasoning keywords."""
    assert is_thinking_model("org/model-with-thinking-v1")
    assert is_thinking_model("company/model-reasoning-large")
    assert is_thinking_model("team/reasoner-model")


def test_is_thinking_model_non_thinking():
    """Test that regular models are not detected as thinking models."""
    assert not is_thinking_model("meta-llama/Llama-3.2-11B-Vision-Instruct")
    assert not is_thinking_model("openai/gpt-4o")
    assert not is_thinking_model("anthropic/claude-3-opus")
    assert not is_thinking_model("google/gemini-pro-vision")


def test_is_thinking_model_edge_cases():
    """Test edge cases in model name detection."""
    # Should not match partial keywords
    assert not is_thinking_model("company/rethink-model")  # "think" in middle
    assert not is_thinking_model("org/reason-able-model")  # "reason" split

    # Should be case insensitive
    assert is_thinking_model("NUMIND/NUMARKDOWN-THINKING")


# =============================================================================
# vision_inference_api() Tests
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_success():
    """Test successful API call to HF Inference API.

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_model_loading():
    """Test handling of model loading state (503).

    NOTE: This test is skipped due to complexity of mocking aiohttp async context managers.
    Error handling will be validated through integration tests with real HF API.
    """
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_image_too_large():
    """Test handling of image too large error (413).

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_rate_limit():
    """Test handling of rate limit error (429).

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_bad_request():
    """Test handling of bad request error (400).

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


@pytest.mark.asyncio
async def test_vision_inference_api_invalid_image():
    """Test handling of invalid base64 image data."""
    with pytest.raises(ValueError, match="Invalid base64 image data"):
        await vision_inference_api(
            images=["data:image/jpeg;base64,!!!invalid!!!"],
            prompt="Test",
            model="test/model",
            api_key="key",
        )


@pytest.mark.asyncio
async def test_vision_inference_api_no_images():
    """Test handling of empty images list."""
    with pytest.raises(ValueError, match="At least one image required"):
        await vision_inference_api(
            images=[],
            prompt="Test",
            model="test/model",
            api_key="key",
        )


def test_estimate_token_count_is_conservative_and_handles_empty():
    assert estimate_token_count("") == 0
    assert estimate_token_count("abc") == 1
    assert estimate_token_count("abcdefghij") == 3


def test_apple_intelligence_fits_in_context_counts_all_budget_inputs():
    prompt = "a" * 3000
    instructions = "b" * 300

    assert apple_intelligence_fits_in_context(
        prompt,
        instructions=instructions,
        schema_overhead_tokens=100,
        response_headroom=500,
        context_size=2000,
    ) is True
    assert apple_intelligence_fits_in_context(
        prompt,
        instructions=instructions,
        schema_overhead_tokens=400,
        response_headroom=700,
        context_size=2000,
    ) is False


def test_build_fallback_config_threads_transport_overrides(monkeypatch):
    monkeypatch.setenv("FICHERO_LARGE_BASE_URL", "http://127.0.0.1:8765/v1")
    monkeypatch.setenv("FICHERO_LARGE_API_KEY", "override-key")
    monkeypatch.setattr(
        "fichero.llm.resolve_model_alias",
        lambda provider, model: ("openrouter", "openai/gpt-4o"),
    )

    cfg = LLMConfig(
        provider="apple",
        model="apple-intelligence",
        temperature=0.2,
        max_tokens=321,
        api_key="original-key",
        api_base="http://original",
        timeout=45,
        extra={"trace": "on"},
        reasoning_effort="medium",
    )

    fallback = _build_fallback_config(cfg, "large")
    assert fallback.provider == "openrouter"
    assert fallback.model == "openai/gpt-4o"
    assert fallback.temperature == 0.2
    assert fallback.max_tokens == 321
    assert fallback.api_key == "override-key"
    assert fallback.api_base == "http://127.0.0.1:8765/v1"
    assert fallback.timeout == 45
    assert fallback.extra == {"trace": "on"}
    assert fallback.reasoning_effort == "medium"


def test_build_fallback_config_uses_original_transport_without_overrides(monkeypatch):
    monkeypatch.delenv("FICHERO_MEDIUM_BASE_URL", raising=False)
    monkeypatch.delenv("FICHERO_MEDIUM_API_BASE", raising=False)
    monkeypatch.delenv("FICHERO_MEDIUM_API_KEY", raising=False)
    monkeypatch.setattr(
        "fichero.llm.resolve_model_alias",
        lambda provider, model: ("anthropic", "claude-sonnet-4"),
    )

    cfg = LLMConfig(
        provider="apple",
        model="apple-intelligence",
        api_key="keep-key",
        api_base="http://keep-base",
    )

    fallback = _build_fallback_config(cfg, "medium")
    assert fallback.provider == "anthropic"
    assert fallback.model == "claude-sonnet-4"
    assert fallback.api_key == "keep-key"
    assert fallback.api_base == "http://keep-base"


def test_resolve_api_key_prefers_explicit_config_over_lookup(monkeypatch):
    cfg = LLMConfig(provider="openai", model="gpt-5", api_key="config-key")
    monkeypatch.setattr(llm, "get_api_key", lambda _provider: "lookup-key")

    assert llm._resolve_api_key(cfg) == "config-key"


def test_get_api_key_returns_none_for_keyless_local_provider() -> None:
    assert llm.get_api_key("ollama") is None


@pytest.mark.parametrize(
    ("provider", "expected_base_url"),
    [
        ("ollama", "http://localhost:11434/v1"),
        ("lmstudio", "http://localhost:1234/v1"),
        ("omlx", "http://localhost:8000/v1"),
    ],
)
def test_build_langchain_model_uses_placeholder_key_for_keyless_local_providers(
    monkeypatch,
    provider: str,
    expected_base_url: str,
) -> None:
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "_resolve_api_key", lambda _config: None)
    monkeypatch.setattr(
        llm,
        "_get_shared_httpx_async_client",
        lambda **_kwargs: "shared-httpx-client",
    )
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )

    cfg = LLMConfig(provider=provider, model="local-model")
    model = llm._build_langchain_model(cfg)

    assert isinstance(model, FakeChatOpenAI)
    assert captured["model"] == "local-model"
    assert captured["api_key"] == provider
    assert captured["base_url"] == expected_base_url
    assert captured["http_async_client"] == "shared-httpx-client"


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_timeout():
    """Test handling of timeout.

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO: Complex async mocking - will be covered by integration tests")
async def test_vision_inference_api_dict_response():
    """Test handling of dict response format (some models).

    NOTE: Skipped due to async mocking complexity. Covered by integration tests.
    """
    pass


# =============================================================================
# Apple Intelligence guardrail fallback (#838)
# =============================================================================


@pytest.mark.asyncio
async def test_chat_with_fallback_passes_through_on_success():
    """When the primary chat() call succeeds, chat_with_fallback returns
    its result unchanged — no fallback path taken."""
    from fichero.llm import chat_with_fallback, LLMConfig

    config = LLMConfig(provider="apple", model="apple-intelligence")
    with patch("fichero.llm.chat", new=AsyncMock(return_value="ok response")):
        result = await chat_with_fallback("hi", config=config)

    assert result == "ok response"


@pytest.mark.asyncio
async def test_chat_with_fallback_routes_around_guardrail_when_paid_fallback_enabled():
    """When Apple Intelligence raises GuardrailViolationError, the fallback
    resolves $medium first and retries with the resolved
    config. Returns the fallback model's response."""
    from fichero.llm import chat_with_fallback, LLMConfig, GuardrailViolationError

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[LLMConfig] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append(config)
        if config.provider == "apple":
            raise GuardrailViolationError("guardrailViolation: May contain unsafe content")
        return "fallback response"

    with patch("fichero.llm.chat", new=fake_chat), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("anthropic", "claude-sonnet-4"),
         ), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
        result = await chat_with_fallback("hi", config=primary_config)

    assert result == "fallback response"
    assert len(call_log) == 2, "should have tried Apple first, then $medium"
    assert call_log[0].provider == "apple"
    assert call_log[1].provider == "anthropic"
    assert call_log[1].model == "claude-sonnet-4"


@pytest.mark.asyncio
async def test_chat_with_fallback_skips_remote_large_when_paid_fallback_disabled():
    """Plain chat fallback must match the structured path: no remote tier
    call unless paid remote fallback consent is enabled."""
    from fichero.llm import chat_with_fallback, LLMConfig, GuardrailViolationError

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[LLMConfig] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append(config)
        raise GuardrailViolationError("guardrailViolation: blocked")

    alias_calls: list[str] = []

    def fake_resolve(provider: str, _model: str) -> tuple[str, str]:
        alias_calls.append(provider)
        return ("openai", "gpt-5")

    with patch("fichero.llm.chat", new=fake_chat), \
         patch("fichero.llm.resolve_model_alias", side_effect=fake_resolve), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        with pytest.raises(GuardrailViolationError, match="blocked"):
            await chat_with_fallback("hi", config=primary_config)

    assert [(c.provider, c.model) for c in call_log] == [
        ("apple", "apple-intelligence")
    ]
    assert alias_calls == ["$medium", "$large"]


@pytest.mark.asyncio
async def test_chat_with_fallback_local_large_allowed_when_paid_fallback_disabled():
    """The paid fallback gate only blocks remote providers; local fallback
    remains available for local-first workflows."""
    from fichero.llm import chat_with_fallback, LLMConfig, GuardrailViolationError

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[LLMConfig] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append(config)
        if config.provider == "apple":
            raise GuardrailViolationError("guardrailViolation: blocked")
        return "local fallback response"

    with patch("fichero.llm.chat", new=fake_chat), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("ollama", "llama3.2"),
         ), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        result = await chat_with_fallback("hi", config=primary_config)

    assert result == "local fallback response"
    assert [(c.provider, c.model) for c in call_log] == [
        ("apple", "apple-intelligence"),
        ("ollama", "llama3.2"),
    ]


@pytest.mark.asyncio
async def test_chat_with_fallback_escalates_medium_then_large():
    from fichero.llm import (
        chat_with_fallback,
        GuardrailViolationError,
        ProviderQuotaError,
    )

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[tuple[str, str]] = []
    alias_calls: list[str] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append((config.provider, config.model))
        if config.provider == "apple":
            raise GuardrailViolationError("guardrailViolation: blocked")
        if config.model == "gpt-5-mini":
            raise ProviderQuotaError(
                provider=config.provider,
                model=config.model,
                detail="quota",
            )
        return "from-large"

    def fake_resolve(provider: str, _model: str) -> tuple[str, str]:
        alias_calls.append(provider)
        if provider == "$medium":
            return ("openai", "gpt-5-mini")
        if provider == "$large":
            return ("anthropic", "claude-sonnet-4")
        raise AssertionError(provider)

    with patch("fichero.llm.chat", new=fake_chat), \
         patch("fichero.llm.resolve_model_alias", side_effect=fake_resolve), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
        result = await chat_with_fallback("hi", config=primary_config)

    assert result == "from-large"
    assert alias_calls == ["$medium", "$large"]
    assert call_log == [
        ("apple", "apple-intelligence"),
        ("openai", "gpt-5-mini"),
        ("anthropic", "claude-sonnet-4"),
    ]


@pytest.mark.asyncio
async def test_plain_and_structured_fallback_share_paid_remote_gate_decision():
    """For the same Apple failure and remote fallback config, both wrappers
    refuse the remote provider when paid fallback consent is off."""
    from fichero.llm import (
        chat_structured_with_fallback,
        chat_with_fallback,
        LLMConfig,
        GuardrailViolationError,
    )

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")

    async def fake_chat(prompt, config, system=None, **_kwargs):
        raise GuardrailViolationError("plain blocked")

    async def fake_structured(*_args, **_kwargs):
        raise GuardrailViolationError("structured blocked")

    with patch("fichero.llm.chat", new=fake_chat), \
         patch("fichero.llm.chat_structured", new=fake_structured), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("openai", "gpt-5"),
         ), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        with pytest.raises(GuardrailViolationError, match="plain blocked"):
            await chat_with_fallback("hi", config=primary_config)
        with pytest.raises(GuardrailViolationError, match="structured blocked"):
            await chat_structured_with_fallback(
                prompt="hi", schema=_StructuredResult, config=primary_config
            )


@pytest.mark.asyncio
async def test_chat_structured_with_fallback_skips_remote_medium_and_large_when_paid_disabled():
    from fichero.llm import (
        chat_structured_with_fallback,
        GuardrailViolationError,
    )

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[tuple[str, str]] = []
    alias_calls: list[str] = []

    async def fake_structured(*args, **kwargs):
        config = kwargs.get("config") or args[2]
        call_log.append((config.provider, config.model))
        raise GuardrailViolationError("structured blocked")

    def fake_resolve(provider: str, _model: str) -> tuple[str, str]:
        alias_calls.append(provider)
        if provider == "$medium":
            return ("openai", "gpt-5-mini")
        if provider == "$large":
            return ("anthropic", "claude-sonnet-4")
        raise AssertionError(provider)

    with patch("fichero.llm.chat_structured", new=fake_structured), \
         patch("fichero.llm.resolve_model_alias", side_effect=fake_resolve), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        with pytest.raises(GuardrailViolationError, match="structured blocked"):
            await chat_structured_with_fallback(
                prompt="hi", schema=_StructuredResult, config=primary_config
            )

    assert call_log == [("apple", "apple-intelligence")]
    assert alias_calls == ["$medium", "$large"]


@pytest.mark.asyncio
async def test_chat_structured_with_fallback_attempts_cloud_medium_when_paid_enabled(
    monkeypatch,
):
    from fichero.llm import (
        chat_structured_with_fallback,
        GuardrailViolationError,
    )

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[tuple[str, str]] = []

    async def fake_structured(*args, **kwargs):
        config = kwargs.get("config") or args[2]
        call_log.append((config.provider, config.model))
        if config.provider == "apple":
            raise GuardrailViolationError("structured blocked")
        return _StructuredResult(answer="from-cloud-medium")

    monkeypatch.setenv("FICHERO_ALLOW_PAID_AI_FALLBACKS", "1")

    with patch("fichero.llm.chat_structured", new=fake_structured), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("openai", "gpt-5-mini"),
         ):
        result = await chat_structured_with_fallback(
            prompt="hi", schema=_StructuredResult, config=primary_config
        )

    assert result == _StructuredResult(answer="from-cloud-medium")
    assert call_log == [
        ("apple", "apple-intelligence"),
        ("openai", "gpt-5-mini"),
    ]


@pytest.mark.asyncio
async def test_chat_structured_with_fallback_skips_same_model_medium_and_uses_large():
    from fichero.llm import (
        chat_structured_with_fallback,
        GuardrailViolationError,
    )

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[tuple[str, str]] = []
    alias_calls: list[str] = []

    async def fake_structured(*args, **kwargs):
        config = kwargs.get("config") or args[2]
        call_log.append((config.provider, config.model))
        if config.provider == "apple":
            raise GuardrailViolationError("structured blocked")
        return _StructuredResult(answer="from-large")

    def fake_resolve(provider: str, _model: str) -> tuple[str, str]:
        alias_calls.append(provider)
        if provider == "$medium":
            return ("apple", "apple-intelligence")
        if provider == "$large":
            return ("ollama", "llama3.2")
        raise AssertionError(provider)

    with patch("fichero.llm.chat_structured", new=fake_structured), \
         patch("fichero.llm.resolve_model_alias", side_effect=fake_resolve), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        result = await chat_structured_with_fallback(
            prompt="hi", schema=_StructuredResult, config=primary_config
        )

    assert result == _StructuredResult(answer="from-large")
    assert call_log == [
        ("apple", "apple-intelligence"),
        ("ollama", "llama3.2"),
    ]
    assert alias_calls == ["$medium", "$large"]


@pytest.mark.asyncio
async def test_chat_with_fallback_reraises_when_no_large_configured():
    """When no fallback tier is configured, chat_with_fallback re-raises
    the original GuardrailViolationError so callers can show a meaningful
    'configure fallback tiers to enable fallback'
    message rather than a confusing 'no default large model' error."""
    from fichero.llm import chat_with_fallback, LLMConfig, GuardrailViolationError

    config = LLMConfig(provider="apple", model="apple-intelligence")
    primary = AsyncMock(side_effect=GuardrailViolationError("guardrailViolation"))

    with patch("fichero.llm.chat", new=primary), \
         patch(
             "fichero.llm.resolve_model_alias",
             side_effect=ValueError("no default large model configured"),
         ):
        with pytest.raises(GuardrailViolationError):
            await chat_with_fallback("hi", config=config)


@pytest.mark.asyncio
async def test_chat_with_fallback_does_not_swallow_other_errors():
    """Non-guardrail errors (network, JSON parse, etc.) propagate without
    triggering the fallback — only guardrail refusals route around."""
    from fichero.llm import chat_with_fallback, LLMConfig

    config = LLMConfig(provider="apple", model="apple-intelligence")
    primary = AsyncMock(side_effect=RuntimeError("network unreachable"))

    with patch("fichero.llm.chat", new=primary):
        with pytest.raises(RuntimeError, match="network unreachable"):
            await chat_with_fallback("hi", config=config)


@pytest.mark.asyncio
async def test_chat_with_fallback_routes_around_unsupported_locale():
    """When Apple Intelligence rejects the prompt's language (Spanish-LatAm
    on a model that only ships Spanish-Spain, e.g.), chat_with_fallback
    must route to $large the same way it does for guardrail refusals.
    Both errors share the AppleUnavailableError base — the single except
    clause catches both (#868)."""
    from fichero.llm import chat_with_fallback, LLMConfig, UnsupportedLocaleError

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[LLMConfig] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append(config)
        if config.provider == "apple":
            raise UnsupportedLocaleError(
                "Apple Intelligence (unsupported_language): "
                "An unsupported language or locale was used"
            )
        return "fallback response"

    with patch("fichero.llm.chat", new=fake_chat), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("anthropic", "claude-sonnet-4-6"),
         ), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
        result = await chat_with_fallback("hola, esto es Español", config=primary_config)

    assert result == "fallback response"
    assert len(call_log) == 2
    assert call_log[0].provider == "apple"
    assert call_log[1].provider == "anthropic"


@pytest.mark.asyncio
async def test_chat_refuses_remote_provider_when_local_only_enabled(monkeypatch):
    from fichero.llm import chat

    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    config = LLMConfig(provider="openai", model="gpt-5")

    with pytest.raises(LocalOnlyViolationError, match="remote provider openai/gpt-5"):
        await chat("hi", config=config)


@pytest.mark.asyncio
async def test_vision_refuses_remote_provider_when_local_only_enabled(monkeypatch):
    from fichero.llm import vision

    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "true")
    config = LLMConfig(provider="openai", model="gpt-4o")

    with pytest.raises(LocalOnlyViolationError, match="vision call"):
        await vision(["data:image/png;base64,AAAA"], "describe", config=config)


@pytest.mark.asyncio
async def test_chat_local_provider_succeeds_when_local_only_enabled(monkeypatch):
    from fichero.llm import chat

    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "on")
    config = LLMConfig(provider="mock", model="mock")

    result = await chat("hi", config=config)

    assert isinstance(result, str)
    assert result


@pytest.mark.asyncio
async def test_chat_default_local_only_off_preserves_remote_provider_behavior(monkeypatch):
    from fichero.llm import chat

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    config = LLMConfig(provider="openai", model="gpt-5")

    class FakeResponse:
        content = "remote response"
        usage_metadata = {}

    fake_model = AsyncMock()
    fake_model.ainvoke.return_value = FakeResponse()

    with patch("fichero.llm.get_langchain_model", return_value=fake_model):
        result = await chat("hi", config=config)

    assert result == "remote response"


@pytest.mark.asyncio
async def test_chat_streaming_returns_chunks_from_langchain_stream():
    from fichero.llm import chat

    config = LLMConfig(provider="openai", model="gpt-5")

    async def fake_stream():
        for chunk in ("hello", " ", "world"):
            yield chunk

    fake_model = MagicMock()

    with patch("fichero.llm.get_langchain_model", return_value=fake_model), patch(
        "fichero.llm._stream_chat_langchain",
        return_value=fake_stream(),
    ) as stream_mock:
        result = await chat("hi", config=config, stream=True)
        chunks = [chunk async for chunk in result]

    assert chunks == ["hello", " ", "world"]
    assert stream_mock.call_count == 1


@pytest.mark.asyncio
async def test_chat_propagates_provider_errors_without_fallback():
    from fichero.llm import chat

    config = LLMConfig(provider="openai", model="gpt-5")
    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))

    with patch("fichero.llm.get_langchain_model", return_value=fake_model):
        with pytest.raises(RuntimeError, match="provider down"):
            await chat("hi", config=config)


def test_get_langchain_model_reuses_cached_model_for_identical_config(monkeypatch):
    llm._LANGCHAIN_MODEL_CACHE.clear()
    llm._LANGCHAIN_MODEL_CACHE_NO_LOOP.clear()

    built_models: list[object] = []

    def fake_build(_config: LLMConfig) -> object:
        model = object()
        built_models.append(model)
        return model

    monkeypatch.setattr(llm, "_build_langchain_model", fake_build)

    shared = LLMConfig(
        provider="openai",
        model="gpt-5",
        temperature=0.2,
        max_tokens=512,
        api_key="key-a",
        api_base="https://api.example.test/v1",
    )
    same = LLMConfig(
        provider="openai",
        model="gpt-5",
        temperature=0.2,
        max_tokens=512,
        api_key="key-a",
        api_base="https://api.example.test/v1",
    )
    different_model = LLMConfig(
        provider="openai",
        model="gpt-5-mini",
        temperature=0.2,
        max_tokens=512,
        api_key="key-a",
        api_base="https://api.example.test/v1",
    )
    different_key = LLMConfig(
        provider="openai",
        model="gpt-5",
        temperature=0.2,
        max_tokens=512,
        api_key="key-b",
        api_base="https://api.example.test/v1",
    )

    first = llm.get_langchain_model(shared)
    second = llm.get_langchain_model(same)
    third = llm.get_langchain_model(different_model)
    fourth = llm.get_langchain_model(different_key)

    assert first is second
    assert first is not third
    assert first is not fourth
    assert len(built_models) == 3


@pytest.mark.asyncio
async def test_get_langchain_model_returns_apple_chat_model(monkeypatch):
    from langchain_core.messages import HumanMessage, SystemMessage

    cfg = LLMConfig(provider="apple", model="apple-intelligence")
    chat_mock = AsyncMock(return_value="apple says hi")
    monkeypatch.setattr(llm, "chat", chat_mock)

    model = llm.get_langchain_model(cfg)
    response = await model.ainvoke(
        [
            SystemMessage(content="be concise"),
            HumanMessage(content="hello"),
        ]
    )

    assert response.content == "apple says hi"
    assert isinstance(model, llm.ChatAppleIntelligence)
    prompt_arg, config_arg = chat_mock.await_args.args[:2]
    assert prompt_arg == [
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hello"},
    ]
    assert config_arg == cfg


@pytest.mark.asyncio
async def test_apple_chat_model_with_structured_output_delegates(monkeypatch):
    from langchain_core.messages import HumanMessage, SystemMessage

    cfg = LLMConfig(provider="apple", model="apple-intelligence")
    parsed = _StructuredResult(answer="structured apple")
    structured_mock = AsyncMock(return_value=parsed)
    monkeypatch.setattr(llm, "chat_structured", structured_mock)

    model = llm.get_langchain_model(cfg)
    structured_model = model.with_structured_output(_StructuredResult, include_raw=True)
    result = await structured_model.ainvoke(
        [
            SystemMessage(content="extract"),
            HumanMessage(content="prompt"),
        ]
    )

    assert result["parsed"] == parsed
    assert result["parsing_error"] is None
    assert result["raw"].content == parsed.model_dump_json()
    assert structured_mock.await_args.args[:3] == ("prompt", _StructuredResult, cfg)
    assert structured_mock.await_args.kwargs["system"] == "extract"


@pytest.mark.asyncio
async def test_omlx_chat_starts_managed_profile_before_langchain_call(monkeypatch):
    from fichero.api.routes import local_inference as routes

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")
    profile = routes._configured_omlx_profile().model_copy(
        update={"startup_policy": LocalProviderStartupPolicy.on_demand}
    )
    manager = _omlx_manager()
    model = _ManagedOmlxModel()
    monkeypatch.setattr(routes, "_configured_omlx_profile", lambda: profile)
    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: manager)
    monkeypatch.setattr(llm, "get_langchain_model", lambda _cfg: model)

    result = await llm.chat("hello", cfg)

    assert result == "local-ok"
    assert manager.start_calls == 1
    assert model.calls == 1


@pytest.mark.asyncio
async def test_omlx_start_failure_raises_unavailable_and_skips_langchain(monkeypatch):
    from fichero.api.routes import local_inference as routes

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")
    manager = _omlx_manager(healthy=False, last_error="stderr excerpt")
    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: manager)
    monkeypatch.setattr(llm, "get_langchain_model", lambda _cfg: (_ for _ in ()).throw(AssertionError("langchain should not run")))

    with pytest.raises(llm.LocalModelUnavailableError, match="stderr excerpt"):
        await llm.chat("hello", cfg)


@pytest.mark.asyncio
async def test_omlx_runtime_missing_raises_typed_error(monkeypatch):
    from fichero.api.routes import local_inference as routes
    from fichero.local_inference import LocalInferenceRuntimeMissingError

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")

    class _Manager:
        state = LocalServiceState.stopped
        restart_count = 0
        process = SimpleNamespace(is_running=lambda: False)

        async def start(self):
            raise LocalInferenceRuntimeMissingError("provision runtime")

    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: _Manager())

    with pytest.raises(llm.LocalModelRuntimeMissingError, match="provision runtime"):
        await llm.chat("hello", cfg)


@pytest.mark.asyncio
async def test_omlx_hardware_gate_raises_typed_error(monkeypatch):
    from fichero.api.routes import local_inference as routes
    from fichero.local_inference import LocalModelHardwareError as LocalInferenceHardwareError

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")

    class _Manager:
        state = LocalServiceState.stopped
        restart_count = 0
        process = SimpleNamespace(is_running=lambda: False)

        async def start(self):
            raise LocalInferenceHardwareError("Qwen3-VL 8B needs 16 GB unified memory; this Mac has 8 GB")

    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: _Manager())

    with pytest.raises(llm.LocalModelHardwareError, match="16 GB unified memory"):
        await llm.chat("hello", cfg)


@pytest.mark.asyncio
async def test_omlx_manual_policy_never_auto_starts(monkeypatch):
    from fichero.api.routes import local_inference as routes

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")
    profile = routes._configured_omlx_profile().model_copy(
        update={"startup_policy": LocalProviderStartupPolicy.manual}
    )
    manager = _omlx_manager(healthy=False, last_error="not healthy")
    monkeypatch.setattr(routes, "_configured_omlx_profile", lambda: profile)
    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: manager)

    with pytest.raises(llm.LocalModelUnavailableError, match="manual-start only"):
        await llm.chat("hello", cfg)

    assert manager.start_calls == 0


@pytest.mark.asyncio
async def test_unmanaged_omlx_base_url_bypasses_manager(monkeypatch):
    from fichero.api.routes import local_inference as routes

    cfg = LLMConfig(
        provider="omlx",
        model="local-model",
        api_base="http://127.0.0.1:9999/v1",
    )
    model = _ManagedOmlxModel()
    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: (_ for _ in ()).throw(AssertionError("manager should not run")))
    monkeypatch.setattr(llm, "get_langchain_model", lambda _cfg: model)

    result = await llm.chat("hello", cfg)

    assert result == "local-ok"
    assert model.calls == 1


@pytest.mark.asyncio
async def test_omlx_restart_cap_stays_failed(monkeypatch):
    from fichero.api.routes import local_inference as routes

    cfg = LLMConfig(provider="omlx", model="mlx-community/Qwen3-VL-8B")
    manager = _omlx_manager(
        healthy=False,
        last_error="still crashed",
        state=LocalServiceState.failed,
        restart_count=llm._MANAGED_OMLX_RESTART_CAP,
    )
    monkeypatch.setattr(routes, "_manager_for_profile", lambda _profile_id: manager)

    with pytest.raises(llm.LocalModelUnavailableError, match="still crashed"):
        await llm.chat("hello", cfg)

    assert manager.restart_calls == 0


class _ConcurrencyResponse:
    content = "ok"
    usage_metadata = {}


class _BatchResponse:
    def __init__(self, content: str, usage_metadata: dict | None = None) -> None:
        self.content = content
        self.usage_metadata = usage_metadata or {}


class _BatchCountingModel:
    def __init__(self) -> None:
        self.abatch_calls: list[list[object]] = []
        self.configs: list[dict | None] = []

    async def abatch(self, inputs, *, config=None, return_exceptions=False):
        self.abatch_calls.append(list(inputs))
        self.configs.append(config)
        assert return_exceptions is True
        return [_BatchResponse(f"result-{idx}") for idx, _ in enumerate(inputs)]


class _BatchExceptionModel:
    async def abatch(self, inputs, *, config=None, return_exceptions=False):
        assert return_exceptions is True
        return [
            _BatchResponse("first"),
            RuntimeError("boom"),
            _BatchResponse("third"),
        ][:len(inputs)]


class _CountingModel:
    def __init__(self) -> None:
        self.current = 0
        self.maximum = 0
        self.lock = asyncio.Lock()

    async def ainvoke(self, _messages):
        async with self.lock:
            self.current += 1
            self.maximum = max(self.maximum, self.current)
        await asyncio.sleep(0.01)
        async with self.lock:
            self.current -= 1
            return _ConcurrencyResponse()


class _ManagedOmlxModel:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        return SimpleNamespace(content="local-ok", usage_metadata={})


def _omlx_manager(*, healthy: bool = True, last_error: str | None = None, state=LocalServiceState.stopped, restart_count: int = 0):
    status = SimpleNamespace(healthy=healthy, last_error=last_error)

    class _Process:
        def is_running(self) -> bool:
            return False

    class _Manager:
        def __init__(self) -> None:
            self.state = state
            self.restart_count = restart_count
            self.process = _Process()
            self.start_calls = 0
            self.restart_calls = 0

        async def start(self):
            self.start_calls += 1
            return status

        async def restart_after_crash(self):
            self.restart_calls += 1
            return status

        async def health(self):
            return status

        def status(self):
            return status

    return _Manager()


def _reset_remote_llm_limit(monkeypatch) -> _CountingModel:
    llm._REMOTE_LLM_SEMAPHORE = None
    llm._REMOTE_LLM_SEMAPHORE_LIMIT = None
    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "2")
    model = _CountingModel()
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: model)
    return model


@pytest.mark.asyncio
async def test_chat_concurrency_cap_limits_in_flight_calls(monkeypatch):
    model = _reset_remote_llm_limit(monkeypatch)
    config = LLMConfig(provider="openai", model="gpt-5")

    tasks = [llm.chat("hello", config) for _ in range(8)]

    await asyncio.gather(*tasks)

    assert model.maximum <= 2


@pytest.mark.asyncio
async def test_vision_concurrency_cap_limits_in_flight_calls(monkeypatch):
    model = _reset_remote_llm_limit(monkeypatch)
    config = LLMConfig(provider="openai", model="gpt-5")

    tasks = [llm.vision(["data:image/png;base64,AAAA"], "describe", config) for _ in range(8)]

    await asyncio.gather(*tasks)

    assert model.maximum <= 2


@pytest.mark.asyncio
async def test_chat_batch_uses_model_abatch_and_preserves_order(monkeypatch):
    model = _BatchCountingModel()
    config = LLMConfig(provider="openai", model="gpt-5")
    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "4")
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: model)

    results = await llm.chat_batch(["one", "two", "three"], config)

    assert results == ["result-0", "result-1", "result-2"]
    assert len(model.abatch_calls) == 1
    assert len(model.abatch_calls[0]) == 3
    assert model.configs == [{"max_concurrency": 4}]


@pytest.mark.asyncio
async def test_vision_batch_uses_model_abatch_and_preserves_order(monkeypatch):
    model = _BatchCountingModel()
    config = LLMConfig(provider="openai", model="gpt-5")
    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "4")
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: model)

    results = await llm.vision_batch(
        [
            ["data:image/png;base64,AAAA"],
            ["data:image/png;base64,BBBB"],
            ["data:image/png;base64,CCCC"],
        ],
        "describe",
        config,
    )

    assert results == ["result-0", "result-1", "result-2"]
    assert len(model.abatch_calls) == 1
    assert len(model.abatch_calls[0]) == 3
    assert model.configs == [{"max_concurrency": 4}]


@pytest.mark.asyncio
async def test_chat_batch_reuses_one_cached_model_lookup(monkeypatch):
    config = LLMConfig(provider="openai", model="gpt-5")
    model = _BatchCountingModel()
    calls = 0

    def fake_get_model(_config):
        nonlocal calls
        calls += 1
        return model

    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "8")
    monkeypatch.setattr(llm, "get_langchain_model", fake_get_model)

    results = await llm.chat_batch(["one", "two", "three", "four"], config)

    assert results == ["result-0", "result-1", "result-2", "result-3"]
    assert calls == 1


@pytest.mark.asyncio
async def test_chat_batch_respects_concurrency_cap_via_abatch_chunking(monkeypatch):
    model = _BatchCountingModel()
    config = LLMConfig(provider="openai", model="gpt-5")
    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "2")
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: model)

    results = await llm.chat_batch(["one", "two", "three", "four", "five"], config)

    assert results == ["result-0", "result-1", "result-0", "result-1", "result-0"]
    assert [len(call) for call in model.abatch_calls] == [2, 2, 1]
    assert model.configs == [
        {"max_concurrency": 2},
        {"max_concurrency": 2},
        {"max_concurrency": 2},
    ]


@pytest.mark.asyncio
async def test_chat_batch_returns_typed_per_item_errors(monkeypatch):
    config = LLMConfig(provider="openai", model="gpt-5")
    monkeypatch.setenv("FICHERO_MAX_INFLIGHT_LLM", "8")
    monkeypatch.setattr(llm, "get_langchain_model", lambda _config: _BatchExceptionModel())

    results = await llm.chat_batch(["one", "two", "three"], config)

    assert results[0] == "first"
    assert results[2] == "third"
    assert isinstance(results[1], LLMBatchItemError)
    assert results[1].index == 1
    assert results[1].kind == "chat"
    assert isinstance(results[1].cause, RuntimeError)
    assert "boom" in str(results[1].cause)


@pytest.mark.asyncio
async def test_chat_with_fallback_reraises_unsupported_locale_when_no_large():
    """No $large configured → original UnsupportedLocaleError surfaces so
    UI can show 'configure $large to enable Spanish' rather than swallowing."""
    from fichero.llm import chat_with_fallback, LLMConfig, UnsupportedLocaleError

    config = LLMConfig(provider="apple", model="apple-intelligence")
    primary = AsyncMock(side_effect=UnsupportedLocaleError("locale rejected"))

    with patch("fichero.llm.chat", new=primary), \
         patch(
             "fichero.llm.resolve_model_alias",
             side_effect=ValueError("no default large model configured"),
         ):
        with pytest.raises(UnsupportedLocaleError, match="locale rejected"):
            await chat_with_fallback("hi", config=config)


@pytest.mark.asyncio
async def test_collect_usage_records_chat_usage_metadata() -> None:
    from fichero.llm import collect_usage, chat

    cfg = LLMConfig(provider="openai", model="gpt-5")
    response_msg = MagicMock()
    response_msg.content = "ok"
    response_msg.usage_metadata = {
        "input_tokens": 50,
        "output_tokens": 20,
        "total_tokens": 70,
    }
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=response_msg)

    with patch("fichero.llm.get_langchain_model", return_value=model):
        with collect_usage() as bucket:
            await chat("hi", config=cfg)

    assert bucket == [
        {
            "provider": "openai",
            "model": "gpt-5",
            "kind": "chat",
            "input_tokens": 50,
            "output_tokens": 20,
            "total_tokens": 70,
            "estimated": False,
        }
    ]


@pytest.mark.asyncio
async def test_collect_usage_ignores_missing_chat_usage_metadata() -> None:
    from fichero.llm import collect_usage, chat

    cfg = LLMConfig(provider="openai", model="gpt-5")
    response_msg = MagicMock()
    response_msg.content = "ok"
    response_msg.usage_metadata = None
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=response_msg)

    with patch("fichero.llm.get_langchain_model", return_value=model):
        with collect_usage() as bucket:
            result = await chat("hi", config=cfg)

    assert result == "ok"
    assert bucket == []


@pytest.mark.asyncio
async def test_collect_usage_records_structured_usage_metadata() -> None:
    from fichero.llm import collect_usage, chat_structured

    cfg = LLMConfig(provider="openai", model="gpt-5")
    raw_message = MagicMock()
    raw_message.usage_metadata = {
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
    }
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(
        return_value={
            "raw": raw_message,
            "parsed": _StructuredResult(answer="from-dict"),
            "parsing_error": None,
        }
    )
    base_model = MagicMock()
    base_model.profile = {"structured_output": True}
    base_model.with_structured_output = MagicMock(return_value=structured_model)

    with patch("fichero.llm._ensure_managed_local_provider_ready", new=AsyncMock()):
        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            with collect_usage() as bucket:
                result = await chat_structured(
                    prompt="hi", schema=_StructuredResult, config=cfg
                )

    assert result == _StructuredResult(answer="from-dict")
    assert bucket == [
        {
            "provider": "openai",
            "model": "gpt-5",
            "kind": "structured",
            "input_tokens": 120,
            "output_tokens": 45,
            "total_tokens": 165,
            "estimated": False,
            "method": "function_calling",
        }
    ]


@pytest.mark.asyncio
async def test_collect_usage_ignores_missing_structured_usage_metadata() -> None:
    from fichero.llm import collect_usage, chat_structured

    cfg = LLMConfig(provider="omlx", model="local-model")
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(
        return_value={
            "raw": MagicMock(usage_metadata=None),
            "parsed": _StructuredResult(answer="local"),
            "parsing_error": None,
        }
    )
    base_model = MagicMock()
    base_model.with_structured_output = MagicMock(return_value=structured_model)

    with patch("fichero.llm._ensure_managed_local_provider_ready", new=AsyncMock()):
        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            with collect_usage() as bucket:
                result = await chat_structured(
                    prompt="hi", schema=_StructuredResult, config=cfg
                )

    assert result == _StructuredResult(answer="local")
    assert bucket == []


def test_raise_provider_quota_error_classifies_429() -> None:
    exc = RuntimeError("too many requests")
    exc.response = types.SimpleNamespace(status_code=429, text="too many requests")
    cfg = LLMConfig(provider="openai", model="gpt-5")

    with patch("fichero.llm._log_provider_quota_hit"):
        with pytest.raises(llm.ProviderQuotaError) as caught:
            llm._raise_provider_quota_error(cfg, exc)

    assert caught.value.provider == "openai"
    assert caught.value.model == "gpt-5"
    assert caught.value.status_code == 429


def test_raise_provider_quota_error_ignores_unrelated_500() -> None:
    exc = RuntimeError("internal server error")
    exc.response = types.SimpleNamespace(status_code=500, text="internal server error")
    cfg = LLMConfig(provider="openai", model="gpt-5")

    with patch("fichero.llm._log_provider_quota_hit") as log_quota_hit:
        llm._raise_provider_quota_error(cfg, exc)

    assert log_quota_hit.call_count == 0
