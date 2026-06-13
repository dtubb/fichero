"""
Unit tests for fichero.llm module (thinking models support).

Tests core LLM functionality including:
- Thinking model response parsing
- Model type detection
- Hugging Face Inference API calls
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

import fichero.llm as llm
from fichero.llm import (
    _build_fallback_config,
    apple_intelligence_fits_in_context,
    estimate_token_count,
    parse_thinking_response,
    is_thinking_model,
    LocalOnlyViolationError,
    vision_inference_api,
    LLMConfig,
)


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
    resolves $large via resolve_model_alias and retries with the resolved
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
    assert len(call_log) == 2, "should have tried Apple first, then $large"
    assert call_log[0].provider == "apple"
    assert call_log[1].provider == "anthropic"
    assert call_log[1].model == "claude-sonnet-4"


@pytest.mark.asyncio
async def test_chat_with_fallback_skips_remote_large_when_paid_fallback_disabled():
    """Plain chat fallback must match the structured path: no remote $large
    call unless paid remote fallback consent is enabled."""
    from fichero.llm import chat_with_fallback, LLMConfig, GuardrailViolationError

    primary_config = LLMConfig(provider="apple", model="apple-intelligence")
    call_log: list[LLMConfig] = []

    async def fake_chat(prompt, config, system=None, **_kwargs):
        call_log.append(config)
        raise GuardrailViolationError("guardrailViolation: blocked")

    with patch("fichero.llm.chat", new=fake_chat), \
         patch(
             "fichero.llm.resolve_model_alias",
             return_value=("openai", "gpt-5"),
         ), \
         patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        with pytest.raises(GuardrailViolationError, match="blocked"):
            await chat_with_fallback("hi", config=primary_config)

    assert [(c.provider, c.model) for c in call_log] == [
        ("apple", "apple-intelligence")
    ]


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
async def test_chat_with_fallback_reraises_when_no_large_configured():
    """When $large isn't configured (resolve_model_alias raises ValueError),
    chat_with_fallback re-raises the original GuardrailViolationError so
    callers can show a meaningful 'configure $large to enable fallback'
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


class _ConcurrencyResponse:
    content = "ok"
    usage_metadata = {}


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
