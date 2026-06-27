# fichero-engine — Python / FastAPI backend

This folder owns the engine logic. The SwiftUI app, the `fichero` CLI, and the MCP
server are thin clients over its HTTP surface.

**Canonical docs (do not duplicate here):**
- Operational manual + hard rules: root [AGENTS.md](../AGENTS.md) — `PYTHONPATH`,
  lint/test, OpenAPI sync, Pydantic + OpenAPI discipline, commit attribution.
- Developer docs: [site/docs/contributor/](../site/docs/contributor/) (architecture
  overview, security model, action registry).
- User manual: [site/docs/user/](../site/docs/user/).
- This component's orientation, layout, and how-it-works: [README](README.md).
- Backend conventions: [docs/architecture/api/development_standards.md](../docs/architecture/api/development_standards.md).

## Component essentials

- Every Python command runs from the repo root with `PYTHONPATH=fichero-engine/src`.
- Start the backend with `bash fichero-engine/scripts/start_backend.sh` (HTTPS on
  loopback; never bare `uvicorn`/HTTP).
- `fichero-engine/scripts/README.md` lists the supported entry points; prefer them
  over ad-hoc commands.
