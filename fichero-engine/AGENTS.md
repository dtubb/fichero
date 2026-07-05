# fichero-engine — Python / FastAPI backend

This subtree owns the engine. The SwiftUI app, `python -m fichero`, and MCP server are
clients over its HTTP surface.

## What lives here

- `src/fichero/api/` — FastAPI app and route modules
- `src/fichero/cli/` — typed CLI over the engine HTTP surface
- `src/fichero/actions/` — audited action layer
- `src/fichero/db.py`, `src/fichero/models.py` — storage and Pydantic models
- `scripts/` — supported backend entry points, schema sync, guardrails
- `tests/` — `unit/`, `integration/`, `contracts/`

## Hard rules for this subtree

- Every Python command runs from repo root with `PYTHONPATH=fichero-engine/src`.
- Start the server with `bash fichero-engine/scripts/start_backend.sh`. Do not use bare `uvicorn`; the app expects loopback HTTPS.
- Lint/test only your diff: `PYTHONPATH=fichero-engine/src .venv/bin/ruff check ...` and focused `pytest ...`. The manager owns the full suite and cross-stack gate.
- If routes or schema change, run `bash fichero-engine/scripts/sync_openapi_schema.sh` and commit all regenerated contract files.
- Pydantic fields, DB shape, and OpenAPI must move together. A declared API field written via `additionalProperties` or omitted from the model is how data disappears.
- New mutation routes should follow the shipped `registry.invoke(...)` pattern so audit and change emission happen on the same path.

## Read next

- Repo-wide workflow and verification: [../AGENTS.md](../AGENTS.md)
- Engine layout and runtime entry points: [README.md](README.md)
- Backend conventions: [../docs/contributor/backend-development-standards.md](../docs/contributor/backend-development-standards.md)
- OpenAPI/client contract: [../docs/contributor/openapi-and-clients.md](../docs/contributor/openapi-and-clients.md)
- Action registry pattern: [../docs/contributor/action-registry.md](../docs/contributor/action-registry.md)
