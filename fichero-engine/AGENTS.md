# fichero-engine — Python / FastAPI backend

This folder owns the engine logic. The whole-system picture lives in the top-level
[README](../README.md); the backend architecture notes are in
[site/docs/developer/architecture-overview.md](../site/docs/developer/architecture-overview.md).

## Keep in mind

- Run Python commands from the repo root with `PYTHONPATH=fichero-engine/src`.
- Start the backend with `bash fichero-engine/scripts/start_backend.sh`; the Swift app
  expects HTTPS on loopback.
- Lint touched backend code with `ruff check fichero-engine/src/`.
- Run focused unit tests for touched areas with
  `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived`.
- Sync the Swift client after backend API/schema changes with
  `./fichero-engine/scripts/sync_openapi_schema.sh`.
- Do not hand-edit generated client or contract artifacts.
- Prefer the existing helpers in `fichero-engine/scripts/`; `fichero-engine/scripts/README.md`
  lists the supported entry points.
