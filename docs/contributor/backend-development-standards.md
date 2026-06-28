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

### Real-Data Library Discipline

Daniel is using real libraries in `~/Documents/Fichero` and iCloud-synced
`.fichero` packages. Treat every local DuckDB file as user data:

- **Never nuke or recreate a library database** to fix a schema or index issue.
- **Structural changes go through `db_migrations.py`** when existing libraries
  need table rewrites, backfills, index drops/rebuilds, or other durable state
  changes.
- **Pydantic model fields still define the fresh-database shape**, but existing
  real libraries need an idempotent compatibility path. `_ensure_table()` handles
  additive columns; non-additive changes belong in a migration.
- **Secondary DuckDB indexes are performance aids, not data contracts.** If an
  index becomes unsafe under real write churn, drop/rebuild the index rather than
  touching user rows.
- **Regression tests for storage bugs should use persistent on-disk DuckDB
  files**, not only `:memory:`, because WAL replay, index maintenance, and
  multi-connection behavior differ on disk.

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

### Centralized workflow/tool LLM path

Workflow and tool code should not construct provider clients directly.

The current shipped path is centralized in `fichero-engine/src/fichero/llm.py`:

- workflow/tool callers use `chat_workflow(...)` as the workflow-facing shim
- `chat_workflow(...)` dispatches into the shared `chat(...)`,
  `chat_structured(...)`, or `chat_with_tools(...)` entry points
- those shared functions call `get_langchain_model(...)` inside `llm.py`

That is the important architectural change from the older "each workflow grabs
its own model" shape: provider/model construction now lives behind the central
LLM helpers, not in individual workflow tools.

The shipped agent tools show the pattern directly:

- `fichero-engine/src/fichero/workflows/tools/agent.py` imports
  `chat_workflow` and uses it for both plain chat and tool-calling turns
- `fichero-engine/src/fichero/workflows/tools/multi_agent.py` also uses
  `chat_workflow` for supervisor decisions, worker synthesis, and final
  aggregation

### LangChain vs LiteLLM

This is a common confusion in the repo history, so be explicit:

- **LangChain is the provider integration and routing layer for chat/tool
  calls.** `llm.py` builds provider clients through LangChain integrations such
  as `init_chat_model(...)`, `ChatOpenAI`, `AzureChatOpenAI`, and the Apple
  adapter.
- **LiteLLM is not the runtime chat router here.** In the current `llm.py`, it
  is only used for model discovery and pricing/cost metadata.

If you are changing how a workflow or tool talks to an LLM, the code path to
read first is `llm.py`, not `providers.py`.

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

## LLM Stack Architecture (post-#872)

The LLM call surface in `fichero-engine/src/fichero/llm.py` was overhauled
in commits `d04dae26..da0a6a67` (master plan #872). Five contracts you
should know before touching it:

### 1. Apple-unavailable error hierarchy (#868)

```python
class AppleUnavailableError(RuntimeError):
    """Apple Intelligence cannot service this request → use cloud."""

class GuardrailViolationError(AppleUnavailableError): ...   # safety filter
class UnsupportedLocaleError(AppleUnavailableError): ...    # es-LatAm rejection
```

`chat_with_fallback` and `chat_structured_with_fallback` catch the base.
Adding a new "Apple can't proceed" reason = subclass + map the bridge
`kind` in `_raise_from_bridge_stderr` — no fallback wiring changes.

Other RuntimeErrors (decoding, context_overflow, rate_limited) stay bare
and do NOT trigger the cloud fallback — they're transient/retryable in
place.

### 2. `_compute_timeout(config, kind, *, schema_chars=None)` (#855, #862, #867)

Single source of truth for wall-clock budgets:

| Kind | Formula | Clamp |
|---|---|---|
| `langchain` | `base × 5 × output_factor` | `[60, 600]` |
| `apple_chat` | `base × output_factor` | `[30, 180]` |
| `apple_structured` | `base × 2 × output_factor × schema_factor` | `[60, 600]` |

Where `output_factor = max(0.25, max_tokens/1024)` and
`schema_factor = max(1.0, schema_chars/2000)`.

Use this for any new asyncio.wait_for wrapper. Don't add a fourth
formula somewhere else.

### 3. Reasoning routing (#859)

`LLMConfig.reasoning_effort: "off"|"low"|"medium"|"high"|None`.
`get_langchain_model` routes per provider:

- **anthropic native**: `thinking={'type':'enabled','budget_tokens':N}` +
  forces `temperature=1` (Anthropic API constraint)
- **openai (o-series)**: `reasoning_effort=<level>` kwarg
- **openrouter**: `extra_body={'reasoning':{'effort':...}}` (works for
  Claude AND gpt-5 via OpenRouter's normalized shape)
- **apple intelligence + others**: silently ignored

Wired ON only for synthesis-style calls (catalogue narrative). Mechanical
extraction (extract_all, cleanup) keeps reasoning OFF — pattern matching
doesn't benefit and adds latency.

### 4. MLX / oMLX local path

The local MLX path is the OpenAI-compatible provider path, not a separate
workflow integration.

- `providers.py` exposes `omlx` as a provider type
- `llm.py` treats `omlx` as an OpenAI-compatible local provider with default
  base URL `http://localhost:8000/v1`
- `get_langchain_model(...)` builds that path with `langchain_openai.ChatOpenAI`
  and a base URL override

In practice, MLX here means an `mlx-lm`-style local server speaking the OpenAI
API, reached through LangChain's OpenAI-compatible client layer.

### 5. `_pydantic_to_apple_schema` fail-loud contract (#856)

The converter now raises `ValueError` with field-pointing messages on:

- Discriminated unions (anyOf with >1 non-null branches)
- Enum / Literal types
- JSON Schema format keywords (date, uri, email, ...)
- Recursive types
- Malformed `$ref` / unknown `type`

Optional[T] (anyOf with 1 non-null + null) and `$ref/$defs` inlining
still work. If you're authoring a tool schema and hit a converter
error, decompose into supported primitives or extend the converter.

### 6. fm-bridge is the canonical Apple path (#870)

Closed: `apple-fm-sdk` migration deferred to its 1.0 release. The
fm-bridge subprocess is the production path — `bin/fm-bridge/FmBridge.swift`
+ `_apple_intelligence_chat` / `_apple_intelligence_structured`. Don't
add a second Apple path without explicit approval.

`apple_intelligence_supports_locale(locale)` is async (#857). Call it
from async contexts; do not wrap with `asyncio.run()` from sync code.

### 7. `collect_usage()` for cost tracking (#852)

Workflow runners and any code path that wants per-call token attribution
wraps execution in:

```python
from fichero.llm import collect_usage

with collect_usage() as bucket:
    result = await tool_fn(inputs)
# bucket is now a list of {provider, model, kind, input_tokens,
#                          output_tokens, total_tokens, estimated, [method]}
```

The contextvars-based collector accumulates every `chat` /
`chat_structured` / `_apple_intelligence_*` call's usage. Without an
active collector, recording is a no-op log-only path. asyncio Tasks
inherit the active context so fan-out nodes capture children's usage.

Apple Intelligence entries are marked `estimated: True` (chars-based
estimate; Foundation Models doesn't surface real token counts through
fm-bridge yet — #843 follow-up). LangChain entries are `estimated: False`
when the provider returned `usage_metadata`.

The runner integration (writing the bucket into Activity.metadata at
node-end) is the final wiring step — landing it requires the runner
to set up a per-node collector around each LangGraph tool call.
