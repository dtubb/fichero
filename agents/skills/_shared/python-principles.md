---
description: Python project conventions for Claude Code agents. Reference doc — not user-invocable.
user-invocable: false
---

# Python Project Principles

## Stack

| Component | Tool | Notes |
|---|---|---|
| CLI | Typer | Declarative CLI with type hints. Commands in `src/<pkg>/cli/` |
| Models | Pydantic | Request/response validation, config, data schemas |
| API | FastAPI | RESTful endpoints with automatic OpenAPI generation |
| Linting | ruff | Format + lint in one tool. Run `ruff check` and `ruff format` |
| Testing | pytest | Unit + integration tests in `tests/` |
| Package | pyproject.toml | PEP 621. No setup.py. Editable install with `pip install -e .` |

## Project Structure

```
src/<package>/
  __init__.py
  cli/              # Typer commands
  api/
    main.py         # FastAPI app entry point
    routes/         # Route modules, one per resource
  models.py         # Pydantic models (single source of truth for schemas)
  db.py             # Database operations
  storage.py        # File/blob management
  workflows/        # Multi-step processing pipelines
tests/
  unit/             # Fast, isolated, mocked dependencies
  integration/      # End-to-end, real dependencies where possible
  contracts/        # API schema validation (OpenAPI export)
pyproject.toml      # Package metadata, dependencies, tool config
```

## Key Patterns

### Pydantic Models
- All external data flows through Pydantic models — never raw dicts at API boundaries.
- Models live in `models.py` (or a `models/` package for large projects). One source of truth.
- Use `model_validator` for cross-field validation. Use `Field()` with descriptions for OpenAPI docs.

### FastAPI Conventions
- One router per resource in `api/routes/`. Register in `main.py`.
- Dependency injection for services — pass via `Depends()`, not global state.
- Async handlers for I/O operations. Sync is fine for CPU-bound work.
- Consistent error responses: raise `HTTPException` with meaningful status codes and detail messages.

### Typer CLI
- Commands mirror the API where applicable (`serve`, `ingest`, `search`).
- Use `typer.Option()` with help text. Keep `--help` output useful.
- Entry point defined in `pyproject.toml` `[project.scripts]`.

### Database
- Database operations isolated in `db.py` — routes never write raw SQL.
- Use transactions for multi-step writes.
- DuckDB for structured queries, LanceDB for vector/semantic search (when applicable).

### Testing
- `pytest` with `pytest-asyncio` for async tests.
- Unit tests mock external dependencies (DB, LLM, filesystem).
- Integration tests use real connections where safe.
- Contract tests validate OpenAPI schema stays in sync with implementation.
- Run: `pytest tests/` or `pytest tests/unit/` for fast feedback.

### Code Quality
- Type hints on all function signatures. No untyped public APIs.
- `ruff check --fix` for lint fixes. `ruff format` for formatting. Configure in `pyproject.toml`.
- Prefer explicit imports over wildcard. Keep imports sorted (ruff handles this).
- Guard clauses over nested conditionals. Early return on error.

## Open Source Conventions

- **Semantic versioning**: MAJOR.MINOR.PATCH. Version in `pyproject.toml`.
- **CHANGELOG.md**: Updated with every release. Group by Added/Changed/Fixed/Removed.
- **README.md**: Installation, quick start, link to docs.
- **LICENSE**: Include one. MIT unless the project specifies otherwise.
- Conventional commit messages: `fix:`, `feat:`, `docs:`, `refactor:`, `test:`.

## What Good Python Looks Like

- Functions do one thing. If it needs a paragraph comment, break it up.
- No dead code. No commented-out code. Delete what's unused.
- Prefer composition over inheritance. Prefer functions over classes for stateless operations.
- `pathlib.Path` over string concatenation for filesystem paths.
- Context managers (`with`) for resource cleanup.
- Explicit is better than implicit. Name things for what they mean.
