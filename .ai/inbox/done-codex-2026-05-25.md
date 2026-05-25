# done-codex-2026-05-25

Backend lane update on `codex`.

## #1198 Entity digest
- Exposed `GET /api/entities/digest` in OpenAPI by setting `include_in_schema=True` and regenerating the contract artifacts.
- Kept the route on the shared library resolver path, but translated the missing-header case to `400` for the digest endpoint.
- Renamed the query param to `library_path`, removed the dead `title` fallback, and kept the library label path-safe with `Path(...).stem`.
- Added regression coverage for:
  - missing library header -> `400`
  - unsupported `format` -> `400`
  - markdown and plain-text digest rendering

## #1207 NER runaway
- Added normalized-name deduping and per-category truncation in `fichero-engine/src/fichero/workflows/tools/entities.py`.
- Added a per-section/page cap in `_write_kg_rows` before KG writes.
- Added tests covering normalized-name deduping, max-item truncation, and oversized KG batches.

## Verification
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_entities_kg_integration.py -k digest -q`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_workflow_tools.py -k extract_entities -q`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_extractor_svo_composition.py -k "caps_overlarge_page_batches or dedup" -q`
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/api/routes/entities.py fichero-engine/src/fichero/workflows/tools/entities.py fichero-engine/src/fichero/workflows/tools/extractors.py fichero-engine/tests/conftest.py fichero-engine/tests/unit/test_routes_entities_kg_integration.py fichero-engine/tests/unit/test_workflow_tools.py fichero-engine/tests/unit/test_extractor_svo_composition.py`
