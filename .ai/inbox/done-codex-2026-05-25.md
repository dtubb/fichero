# done-codex-2026-05-25

Completed backend issue `#1118` on the `codex` branch.

What changed:
- Added a shared NER contract in `fichero/kg/ner.py` for normalised entity records and provider adapters.
- Added workflow-side NER providers for `llm`, `spacy`, and `transformers` backends under `fichero/workflows/ner/`.
- Added a selectable `ner` workflow tool and wired the extractor pre-pass to consume the provider abstraction instead of hardcoding spaCy.

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/kg/ner.py fichero-engine/src/fichero/workflows/ner/__init__.py fichero-engine/src/fichero/workflows/ner/providers.py fichero-engine/src/fichero/workflows/tools/ner.py fichero-engine/src/fichero/workflows/tools/extractors.py fichero-engine/src/fichero/workflows/tools/__init__.py fichero-engine/src/fichero/kg/__init__.py fichero-engine/tests/unit/workflows/test_ner_providers.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/workflows/test_ner_providers.py fichero-engine/tests/unit/kg/test_spacy_ner.py -q`

Notes:
- The existing workspace has unrelated local edits in `AGENTS.md`, `CLAUDE.md`, `HISTORY.md`, `MEMORY.md`, and `STATE.md`; I left those alone.

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
