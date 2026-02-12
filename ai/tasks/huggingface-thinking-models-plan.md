# Implementation Plan: Hugging Face Inference API + Thinking Models

## Goal
Add support for Hugging Face Inference API to enable thinking/reasoning models like NuMarkdown-8B-Thinking that output structured `<think>...</think><answer>...</answer>` format.

## Background
- Current: Uses `router.huggingface.co/v1` (OpenAI-compatible) via LangChain
- Problem: Not all HF models available through router (e.g., NuMarkdown)
- Solution: Add direct Inference API support with thinking model parsing

## Architecture Changes

### Backend (Python)

#### 1. llm.py - Core LLM Interface
**New Functions:**
- `vision_inference_api()` - Direct HF Inference API for vision models
- `parse_thinking_response()` - Extract answer from `<think>/<answer>` format
- `is_thinking_model()` - Detect if model uses thinking format

**Modified Functions:**
- `vision()` - Add HF Inference API fallback path
- `get_langchain_model()` - No changes needed (keep router for non-vision)

**Implementation Details:**
```python
async def vision_inference_api(
    images: list[str],  # base64 data URIs
    prompt: str,
    model: str,  # e.g., "numind/NuMarkdown-8B-Thinking"
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Call HF Inference API directly for vision models.

    Uses POST to https://api-inference.huggingface.co/models/{model}
    with multimodal input format.
    """
    pass

def parse_thinking_response(text: str) -> tuple[str, str | None]:
    """Parse thinking model response.

    Returns:
        (answer, thinking) tuple
        - answer: The actual result (from <answer> tag or full text)
        - thinking: The reasoning process (from <think> tag or None)
    """
    pass

def is_thinking_model(model: str) -> bool:
    """Check if model is a known thinking model.

    Known patterns:
    - Contains "-thinking" or "-reasoning"
    - Specific models: numind/NuMarkdown-*, deepseek-reasoner-*
    """
    pass
```

**Error Handling:**
- HTTP 400: Model not found
- HTTP 413: Image too large (suggest resize)
- HTTP 503: Model loading (retry with backoff)
- HTTP 429: Rate limit (propagate to user)

#### 2. vision_base.py - Vision Tool Base
**Modified Functions:**
- `process_vision()` - Route to Inference API for specific models

**Implementation:**
```python
async def process_vision(...):
    # ... existing code ...

    # Check if we should use Inference API instead of router
    if should_use_inference_api(effective_config):
        text = await vision_inference_api(
            images=[image_uri],
            prompt=final_prompt,
            model=effective_config.model,
            api_key=effective_config.api_key,
            temperature=effective_config.temperature,
            max_tokens=effective_config.max_tokens,
        )
        # Parse thinking response
        answer, thinking = parse_thinking_response(text)

        # Log thinking if present
        if thinking:
            logger.info(f"Model thinking: {thinking[:200]}...")

        # Use answer for further processing
        parsed = parse_output(answer, output_format, output_options)
    else:
        # Existing LangChain path
        text = await vision(...)
        parsed = parse_output(text, output_format, output_options)
```

#### 3. providers.py - Provider Metadata
**Add Field:**
```python
class ProviderDefinition:
    # ... existing fields ...
    uses_inference_api: bool = False  # True for HF Inference API
```

**Update HuggingFace Provider:**
```python
PROVIDERS["huggingface"] = ProviderDefinition(
    id="huggingface",
    name="Hugging Face",
    # ... existing fields ...
    uses_inference_api=True,  # NEW
    supports_vision=True,
    known_thinking_models=[
        "numind/NuMarkdown-8B-Thinking",
        "numind/NuMarkdown-8B-reasoning",
        # Add more as discovered
    ],
)
```

#### 4. models.py - Response Models
**Add Fields (optional):**
```python
class AIArtifact(BaseModel):
    # ... existing fields ...
    thinking_process: str | None = None  # Store reasoning for thinking models
```

### Frontend (Swift)

#### 1. Model Metadata
**Add to Provider/Model responses:**
- `is_thinking_model: bool` - Flag for thinking models
- `supports_inference_api: bool` - Can use direct Inference API

#### 2. UI Indicators
**NodePopover.swift:**
- Show "Thinking Model" badge for thinking models
- Add toggle to show/hide thinking process in results

**ActivityDetailView.swift:**
- Display thinking process in activity logs (collapsible section)

#### 3. Model Filtering (Future)
- Filter models by capability (thinking, vision, chat)

## Testing Strategy

### Unit Tests
**tests/unit/test_llm.py:**
```python
def test_parse_thinking_response():
    # Test with thinking tags
    text = "<think>reasoning here</think><answer>result</answer>"
    answer, thinking = parse_thinking_response(text)
    assert answer == "result"
    assert thinking == "reasoning here"

    # Test without thinking tags
    text = "plain result"
    answer, thinking = parse_thinking_response(text)
    assert answer == "plain result"
    assert thinking is None

    # Test malformed tags
    text = "<think>incomplete"
    answer, thinking = parse_thinking_response(text)
    assert answer == "<think>incomplete"
    assert thinking is None

def test_is_thinking_model():
    assert is_thinking_model("numind/NuMarkdown-8B-Thinking")
    assert is_thinking_model("deepseek-reasoner-v1")
    assert not is_thinking_model("meta-llama/Llama-3.2-11B-Vision")

@pytest.mark.asyncio
async def test_vision_inference_api_success():
    # Mock HF API response
    # Verify request format
    # Check response parsing
    pass

@pytest.mark.asyncio
async def test_vision_inference_api_error_handling():
    # Test 413 error (image too large)
    # Test 503 error (model loading)
    # Test 429 error (rate limit)
    pass
```

**tests/unit/test_vision_base.py:**
```python
@pytest.mark.asyncio
async def test_process_vision_thinking_model():
    # Test that thinking models route to Inference API
    # Verify thinking is logged/stored
    # Check answer is used for output
    pass
```

### Integration Tests
**tests/integration/test_huggingface_inference.py:**
```python
@pytest.mark.asyncio
@pytest.mark.skipif(not has_hf_api_key(), reason="HF API key required")
async def test_numarkdown_inference():
    """Test NuMarkdown model via Inference API."""
    # Use real API call with test image
    # Verify response format
    # Check thinking extraction
    pass
```

### Manual Testing Checklist
- [ ] NuMarkdown model loads in provider list
- [ ] Transcribe workflow with NuMarkdown executes successfully
- [ ] Thinking process is captured in activity logs
- [ ] Image resizing works for 413 errors
- [ ] Error messages are user-friendly
- [ ] Performance is acceptable (< 10s for typical image)

## Implementation Order

1. **Backend Core (llm.py)**
   - [ ] Add `parse_thinking_response()`
   - [ ] Add `is_thinking_model()`
   - [ ] Add `vision_inference_api()`
   - [ ] Write unit tests for parsing functions

2. **Backend Integration (vision_base.py)**
   - [ ] Update `process_vision()` to route to Inference API
   - [ ] Add thinking process logging
   - [ ] Write unit tests for vision routing

3. **Provider Metadata (providers.py)**
   - [ ] Add `uses_inference_api` field
   - [ ] Update HuggingFace provider definition
   - [ ] Add known thinking models list

4. **Testing**
   - [ ] Run unit tests: `pytest tests/unit/test_llm.py -v`
   - [ ] Run integration tests (if HF key available)
   - [ ] Manual testing with NuMarkdown model

5. **Frontend (Optional for MVP)**
   - [ ] Add thinking model badge to NodePopover
   - [ ] Show thinking process in activity logs
   - [ ] Update model filtering

6. **Documentation**
   - [ ] Update llm.py docstrings
   - [ ] Add examples to vision_base.py
   - [ ] Document HF Inference API support in README

## Rollout Strategy

### Phase 1: Backend Only (MVP)
- Add HF Inference API support
- Add thinking response parsing
- Basic logging of thinking process
- Works with existing UI

### Phase 2: Enhanced Frontend
- Display thinking badges
- Show thinking process in activity logs
- Model capability filtering

### Phase 3: Advanced Features
- Store thinking process in artifacts
- Allow users to toggle thinking visibility
- Add thinking-specific prompting strategies

## Known Limitations

1. **Inference API Rate Limits**: Free tier has limits, may need retry logic
2. **Model Loading Time**: Cold start can take 20-60 seconds
3. **Image Size Limits**: Need to enforce max size to avoid 413 errors
4. **Thinking Format Variance**: Some models may use different tags

## Success Criteria

- [ ] NuMarkdown model works via Inference API
- [ ] Thinking process is extracted and logged
- [ ] Error handling is robust and user-friendly
- [ ] Unit tests pass with >90% coverage
- [ ] Integration test works with real API
- [ ] No regressions in existing vision models

## Rollback Plan

If issues arise:
1. Inference API calls fail → Fall back to router API
2. Thinking parsing breaks → Return full response as-is
3. Performance issues → Add caching layer
4. Rate limits exceeded → Queue requests or suggest local inference
