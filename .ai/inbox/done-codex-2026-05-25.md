# done-codex-2026-05-25

Backend lane completed in priority order.

## #1173
- Verified the existing pronoun-annotation path in `fichero-engine/src/fichero/workflows/tools/extract_all.py`.
- Confirmed coverage in `fichero-engine/tests/unit/workflows/test_extract_all_systemic.py::TestAnnotatePronounSource`.
- Re-verified with `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/workflows/test_extract_all_systemic.py::TestAnnotatePronounSource`.

## #1054
- Verified the search threshold already exists in `fichero-engine/src/fichero/api/routes/search_explain.py::_semantic_search`.
- Re-verified with `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/integration/test_search_end_to_end.py::TestRouteLevelEnhancedSearch::test_phrase_filter_drops_partial_matches`.

## #1198 backend half
- Added `GET /api/entities/digest` in `fichero-engine/src/fichero/api/routes/entities.py`.
- Added markdown and plain-text digest renderers plus regression coverage in `fichero-engine/tests/unit/test_routes_entities_kg_integration.py`.
- Verified with `bash scripts/verify_python.sh` and the targeted digest tests.

## Verification
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/api/routes/entities.py fichero-engine/tests/unit/test_routes_entities_kg_integration.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/workflows/test_extract_all_systemic.py::TestAnnotatePronounSource fichero-engine/tests/integration/test_search_end_to_end.py::TestRouteLevelEnhancedSearch::test_phrase_filter_drops_partial_matches`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/test_routes_entities_kg_integration.py::TestEntityDigestEndpointAfterExtractorWrite`
- `bash scripts/verify_python.sh`
