# fichero-api

Python/FastAPI backend for Fichero.

## What lives here
- `src/fichero/`: API routes, workflows, ingest, storage, providers
- `src/fichero_backend/`: Briefcase entry point for bundled backend app
- `tests/`: unit/integration/contract tests
- `pyproject.toml`: package + Briefcase config

## Run
From repo root:

```bash
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765 --reload
```

## Test
From repo root:

```bash
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived
```

## Bundle backend app
From repo root:

```bash
./fichero-api/scripts/build_backend_bundle.sh
```

## Keep Swift client in sync
When backend API routes or schemas change, regenerate and copy the OpenAPI schema into the Swift package used by the app:

```bash
./fichero-api/scripts/sync_openapi_schema.sh
```
