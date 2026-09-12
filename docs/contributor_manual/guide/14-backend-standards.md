# 14. Backend Standards


### General practice

RESTful conventions with standard HTTP methods; Pydantic for request/response validation; consistent error codes with meaningful messages; docstrings on endpoints. Type hints on all functions; async/await for I/O; dependencies passed explicitly rather than global state; structured logging. DuckDB for structured metadata queries, LanceDB for vector search; proper transaction management. Mutations go through the action registry — that whole discipline is chapter 5.

Prefer raising over silent fallback: never substitute a different id, document, or value when something cannot be resolved — raise with what was expected and what was found.

### Real-data library discipline

The maintainer uses real libraries in `$HOME/Documents` and iCloud-synced `.fichero` packages. Treat every local DuckDB file as user data:

- **Never nuke or recreate a library database** to fix a schema or index issue.
- **Structural changes go through** `db_migrations.py` when existing libraries need table rewrites, backfills, or index drops/rebuilds.
- Pydantic model fields define the fresh-database shape; `_ensure_table()` handles additive columns; non-additive changes belong in a migration.
- Secondary DuckDB indexes are performance aids, not data contracts — if one becomes unsafe under real write churn, drop/rebuild the index rather than touching user rows.
- Regression tests for storage bugs use persistent on-disk DuckDB files, not only `:memory:` — WAL replay, index maintenance, and multi-connection behavior differ on disk.

### LLM stack

The LLM call surface is `fichero-server/src/fichero_server/llm/`. Contracts to know before touching it:

**Structured output standard.** Every extraction-style LLM call (known response shape) MUST use `chat_structured_with_fallback()` rather than `chat()` + `json.loads()`. The grammar-constrained path makes invalid JSON impossible, eliminating the recurring truncated-JSON and prose-wrapped-JSON failure modes. Two backends, one API: Apple Intelligence (`provider="apple"`) subprocesses the `fm-bridge` helper with a decoder-constrained schema built from the Pydantic model; everything else uses LangChain’s `with_structured_output(schema, method="function_calling")` — the lowest common denominator across providers, because strict `json_schema` mode silently degrades on some routed models.

| Use case | API |
|----|----|
| Extract typed entities, classify, parse | `chat_structured_with_fallback(prompt, MySchema, config)` |
| Free-form prose (narratives, summaries) | `chat_with_fallback(prompt, config, system=...)` |
| Streaming, multi-turn chat, agent loops | `chat(prompt, config, stream=...)` |

**Centralized workflow path.** Workflow and tool code never constructs provider clients directly: callers use `chat_workflow(...)`, which dispatches into the shared `chat` / `chat_structured` / `chat_with_tools` entry points, which call `get_langchain_model(...)` internally. The shipped agent tools (`workflows/tools/agent.py`, `multi_agent.py`) show the pattern.

**LangChain vs LiteLLM.** LangChain is the provider integration and routing layer for chat/tool calls. LiteLLM is **not** the runtime router here — it is used only for model discovery and pricing/cost metadata.

**Schemas live alongside their tool**, not in a shared schemas module — each tool owns its extraction shape; sharing creates coupling. Private Pydantic models (`_Person`, `_Extraction`) in the tool file, with `Field` descriptions. For Apple Intelligence, pass `include_schema_in_prompt=False` when your system message covers behavior — the schema is enforced by the decoder anyway and the on-device window is ~4K tokens.

**Error hierarchy**: `AppleUnavailableError` (base, “use cloud”), with `GuardrailViolationError` and `UnsupportedLocaleError` subclasses. The fallback helpers catch the base; other RuntimeErrors (decoding, overflow, rate-limited) stay bare and retry in place. Adding a new “Apple can’t proceed” reason = subclass + map the bridge `kind`. `fm-bridge` is the canonical Apple path — don’t add a second one.

`_compute_timeout(config, kind, *, schema_chars=None)` is the single source of truth for wall-clock budgets (langchain / apple_chat / apple_structured formulas with clamps) — do not add another formula. **Reasoning routing** (`LLMConfig.reasoning_effort`) routes per provider and is wired on only for synthesis-style calls; mechanical extraction keeps it off. **Local MLX** is the OpenAI-compatible provider path (`omlx`, default `http://localhost:8000/v1`) reached through LangChain’s OpenAI-compatible client — not a separate workflow integration. `collect_usage()` wraps execution for per-call token attribution (a contextvars-based collector; Apple entries are marked `estimated`).

Don’t: `json.loads(response)` after `chat()`; fence-stripping helpers; sharing Pydantic schemas across tools “to avoid duplication.”

Tests mock `fichero_server.workflows.tools.<tool>.chat_structured_with_fallback` with an `AsyncMock` returning a typed instance (no JSON-string fixtures), and cover the LLM-failure path — tools degrade gracefully (identity grouping, empty result, or an error artifact), never silently dropping data.

### Test commands

    # Unit tests (from the repo root; NEVER whole-tree pytest — perf suite)
    PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/ --ignore=fichero-server/tests/unit/_archived

    # One area
    PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/api/

    # With coverage
    PYTHONPATH=fichero-server/src pytest --cov=fichero_server fichero-server/tests/unit/

### Gotchas

- **Multi-library requests need the** `X-Fichero-Library-Path` **header** (app-wide endpoints — health, providers/catalog, settings — skip it).
- **A** `pytest -k` **subset skips the architecture guardrails.** Anything touching a persisted DB, a route, or a Swift service needs the full unit run.
- **Paths assembled from parts hide from a string sweep** — `ROOT / "docs" / "<page>.md"` has no greppable substring; moving a file breaks it silently.
- After any scripted edit that touches imports across many files, AST-parse every touched file — batch tools compound each other’s mistakes around function-local imports.

------------------------------------------------------------------------
