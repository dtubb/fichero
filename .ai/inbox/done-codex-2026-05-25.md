# done-codex-2026-05-25

Completed backend review follow-up for `#1198` on the `codex` branch.

What changed:
- Exposed the entity digest route in the OpenAPI contract.
- Registered the digest dependency override in `fichero-engine/tests/conftest.py` so the digest tests use the same isolated test database path as the rest of the route suite.
- Kept the digest route on the shared library resolver path so the test client no longer depends on same-thread DB cache coincidence.

Verified already-fixed, no code changes:
- `#1173` KG pronoun/coreference handling
- `#1054` search relevance threshold

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check --ignore E402 fichero-engine/tests/conftest.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest -q fichero-engine/tests/unit/test_routes_entities_kg_integration.py::TestEntityDigestEndpointAfterExtractorWrite`

Notes:
- The full backend gate was not re-run here because the authoritative serial gate is owned by the manager.
