# fichero-server — Python / FastAPI backend

This subtree owns the engine. The SwiftUI app, `python -m fichero_cli`, and MCP server are
clients over its HTTP surface.

## What lives here

- `src/fichero_server/api/` — FastAPI app and route modules
- `src/fichero_server/cli/` — typed CLI over the engine HTTP surface
- `src/fichero_server/actions/` — audited action layer
- `src/fichero_server/db.py`, `src/fichero_server/models.py` — storage and Pydantic models
- `scripts/` — supported backend entry points, schema sync, guardrails
- `tests/` — `unit/`, `integration/`, `contracts/`

## Hard rules for this subtree

- Every Python command runs from repo root with `PYTHONPATH=fichero-server/src`,
  against the repo-root `.venv`. Building that venv is documented once, in
  [../CONTRIBUTING.md](../CONTRIBUTING.md). There is no `requirements.txt`;
  `pyproject.toml` is the manifest.
- Start the server with `bash fichero-server/scripts/start_backend.sh`. Do not use bare `uvicorn`; the app expects loopback HTTPS.
- Lint/test only your diff: `PYTHONPATH=fichero-server/src .venv/bin/ruff check ...` and focused `pytest ...`. The manager owns the full suite and cross-stack gate.
- If routes or schema change, run `bash fichero-server/scripts/sync_openapi_schema.sh` and commit all regenerated contract files.
- Pydantic fields, DB shape, and OpenAPI must move together. A declared API field written via `additionalProperties` or omitted from the model is how data disappears.
- New mutation routes should follow the shipped `registry.invoke(...)` pattern so audit and change emission happen on the same path.
- **The engine is macOS-only when embedded.** It is bundled with Briefcase, and
  `pyproject.toml` declares one platform (`[tool.briefcase.app.engine.macOS]`).
  iOS/iPadOS **cannot** embed it — LanceDB and the Apple Vision PyObjC bindings ship
  no iOS wheels — so those targets always talk to an external/remote engine over
  HTTPS. Never assume the engine is in-process; never gate a capability on it being
  local. See [README.md](README.md) → *macOS only*.

## Read next

- Repo-wide workflow and verification: [../AGENTS.md](../AGENTS.md)
- Engine layout and runtime entry points: [README.md](README.md)
- Backend conventions: [../docs/contributor/backend-development-standards.md](../docs/contributor/backend-development-standards.md)
- OpenAPI/client contract: [../docs/contributor/openapi-and-clients.md](../docs/contributor/openapi-and-clients.md)
- Action registry pattern: [../docs/contributor/action-registry.md](../docs/contributor/action-registry.md)
