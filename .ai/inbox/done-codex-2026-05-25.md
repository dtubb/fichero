# done-codex-2026-05-25

Completed backend review follow-up for `#1198` on the `codex` branch.

What changed:
- Exposed the entity digest route in the OpenAPI contract.
- Switched the digest route to the shared library database resolver path so missing or invalid library headers return the expected HTTP errors.
- Added regression coverage for markdown, plain text, missing library header, and unsupported format cases.
- Regenerated the OpenAPI contract artifacts.

Verified already-fixed, no code changes:
- `#1173` KG pronoun/coreference handling
- `#1054` search relevance threshold

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/api/routes/entities.py fichero-engine/tests/unit/test_routes_entities_kg_integration.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/test_routes_entities_kg_integration.py::TestEntityDigestEndpointAfterExtractorWrite`
- `./fichero-engine/scripts/sync_openapi_schema.sh`

Notes:
- The full backend gate was not re-run here because the authoritative serial gate is owned by the manager.
