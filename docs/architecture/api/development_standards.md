# Backend Development Standards

## Best Practices

### API Design
- **RESTful Conventions**: Follow standard HTTP methods (GET, POST, PUT, DELETE)
- **Pydantic Models**: Use Pydantic for request/response validation
- **Error Handling**: Consistent HTTP error codes (400, 404, 500) with meaningful messages
- **Documentation**: Use docstrings for all endpoints

### Code Quality
- **Type Hints**: Use Python type hints for all functions
- **Async/Await**: Use async/await for I/O operations
- **Dependency Injection**: Pass dependencies explicitly rather than global state
- **Logging**: Use structured logging for debugging and monitoring

### Database Operations
- **DuckDB**: Use for structured metadata queries
- **LanceDB**: Use for vector search and semantic operations
- **Transactions**: Use proper transaction management for data consistency

## Testing Standards

### Unit Testing
- **Isolation**: Test individual components in isolation
- **Mocking**: Use unittest.mock or pytest-mock for dependencies
- **Coverage**: Aim for 100%+ test coverage on critical paths

### Integration Testing
- **End-to-End**: Test complete API flows
- **Real Dependencies**: Use real database connections where possible
- **Test Client**: Use FastAPI TestClient for API testing

### Test Organization
```
tests/
├── unit/                # Isolated component tests
│   ├── test_api.py       # API endpoint tests
│   ├── test_db.py        # Database operation tests
│   └── test_models.py    # Data model tests
└── integration/         # End-to-end tests
    ├── test_workflows.py # Workflow execution tests
    └── test_search.py    # Search functionality tests
```

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test type
pytest tests/unit/
pytest tests/integration/

# Run with coverage
pytest --cov=src/fichero tests/
```

## LLM Calls — Structured Output Standard

Every extraction-style LLM call (where the response shape is known
in advance) MUST use `chat_structured_with_fallback()` from `llm.py`
rather than `chat()` + `json.loads()`. The grammar-constrained path
makes it physically impossible for the model to emit invalid JSON,
which eliminates the recurring "Unterminated string at line N",
"Expecting ',' delimiter", and prose-wrapped-JSON failure modes.

Two backends, one Python API:

- **Apple Intelligence** (`provider="apple"`): subprocesses `fm-bridge`
  with `LanguageModelSession.respond(to:schema:)` using
  `DynamicGenerationSchema` built from the Pydantic schema. Decoder is
  constrained at the token level.
- **Everything else**: LangChain's
  `model.with_structured_output(schema, method="function_calling")`.
  We default to `function_calling` because it's the lowest-common-
  denominator across OpenAI, OpenRouter, Anthropic, Mistral, Gemini.
  Strict `json_schema` mode (LangChain default) silently degrades on
  some OpenRouter-routed models.

### When to use which API

| Use case | API |
|---|---|
| Extract typed entities, classify, parse | `chat_structured_with_fallback(prompt, MySchema, config)` |
| Free-form prose (catalogue narrative, summaries) | `chat_with_fallback(prompt, config, system=...)` |
| Streaming, multi-turn chat, agent loops | `chat(prompt, config, stream=...)` |

### Authoring schemas

Pydantic models live **alongside their tool**, not in a shared schemas
module. Each tool owns its extraction shape; sharing creates coupling
when one tool's needs evolve.

```python
# fichero-engine/src/fichero/workflows/tools/my_tool.py
from pydantic import BaseModel, Field

class _Person(BaseModel):
    name: str
    context: str = Field(description="role and importance")

class _Extraction(BaseModel):
    """Schema for the my_tool LLM call."""
    people: list[_Person] = Field(default_factory=list)
    summary: str = ""

async def my_tool(inputs, state, llm_config):
    result = await chat_structured_with_fallback(
        prompt=inputs["text"],
        schema=_Extraction,
        config=llm_config,
        system="Extract entities. Be precise.",
        # Apple Intelligence has a ~4K window; the schema is enforced
        # by the decoder, so the auto-injected schema dump in the
        # prompt is wasted tokens. Set False when our system message
        # already covers behavior.
        include_schema_in_prompt=False,
    )
    # `result` is a typed _Extraction instance — no parse step needed.
    for person in result.people:
        ...
```

### Apple Intelligence specifics

- `include_schema_in_prompt=False` is recommended whenever the system
  instructions describe behavior; the schema is enforced by the
  decoder regardless. Saves prompt tokens in the on-device 4K window.
- `fm-bridge` returns a typed error `kind` on failure (guardrail,
  refusal, decoding, context_overflow, rate_limited, concurrent,
  unsupported_guide, unsupported_language, assets, generation,
  schema, json). Python's `_raise_from_bridge_stderr()` maps the
  safety-related kinds (guardrail, refusal) to
  `GuardrailViolationError` so `chat_structured_with_fallback`
  routes around them with `$large`.
- Per-call schema construction: `_pydantic_to_apple_schema()` walks
  Pydantic's `model_json_schema()`, resolves `$ref`/`$defs`, and
  flattens `Optional[T]` (anyOf with null) so `DynamicGenerationSchema`
  receives the shape it expects (list of `{name, schema, optional}`).
  No need to maintain a parallel JSON schema by hand.

### LangChain specifics

- `method="function_calling"` (default in `chat_structured`) routes
  through tool-calling on every provider that supports it. For
  models that natively support strict `response_format=json_schema`
  (e.g. OpenAI gpt-5+), upgrading is a future improvement (#844 item
  7) once `model.profile` exposes the capability flag.
- `max_retries=10` (LangChain default is 6) is set in
  `get_langchain_model`'s common params. Exponential backoff with
  jitter handles transient OpenRouter / Anthropic rate-limit and
  network blips silently.

### Tests

- Mock `fichero.workflows.tools.<tool>.chat_structured_with_fallback`
  with an `AsyncMock(return_value=YourSchema(...))`. The mock returns
  a typed Pydantic instance — no JSON-string fixtures.
- Cover the LLM-failure path: `AsyncMock(side_effect=RuntimeError(...))`.
  Tools should degrade gracefully (identity grouping, empty result, or
  page-level error artifact — never silently drop data).

### Don't

- Don't `json.loads(response)` after a `chat()` call. If the shape is
  knowable, switch to `chat_structured_with_fallback`.
- Don't write `_strip_fences()` / `_strip_json_fences()` helpers. The
  structured path returns valid JSON by construction; fence-stripping
  is a relic.
- Don't share Pydantic schemas across tools "to avoid duplication."
  Each tool's contract evolves independently.

