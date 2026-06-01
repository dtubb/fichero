# fichero-engine

Python/FastAPI backend for Fichero.

## What lives here
- `src/fichero/`: API routes, workflows, ingest, storage, providers
- `src/fichero_backend/`: Briefcase entry point for bundled backend app
- `tests/`: unit/integration/contract tests
- `pyproject.toml`: package + Briefcase config

## Run
From repo root:

```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765 --reload
```

## Test
From repo root:

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
```

## Bundle backend app
From repo root:

```bash
./fichero-engine/scripts/build_backend_bundle.sh
```

## Keep Swift client in sync
When backend API routes or schemas change, regenerate and copy the OpenAPI schema into the Swift package used by the app:

```bash
./fichero-engine/scripts/sync_openapi_schema.sh
```

## OCR vs HTR Model Guidance
- `OCR` (printed/typewritten pages): start with `Qwen/Qwen3-VL-8B-Instruct` or OCR-specialized models like `datalab-to/chandra-ocr-2` and `nanonets/Nanonets-OCR-s`.
- `HTR` (handwritten pages): prefer `gpt-5` first; `gemini-3-pro-preview` is a strong alternative.
- In `Transcribe (Auto-Detect)`, handwritten branches (`manuscript`, `htr`, `paleography`) should use HTR-capable vision models, while printed branches (`typescript`) can prioritize OCR-specialized models.

## Clean local generated artifacts

```bash
./fichero-engine/scripts/clean_local_artifacts.sh
```
