# done-codex-2026-05-25

Verified backend issue `#1206` on the `codex` branch.

What changed:
- Made the test-only `FICHERO_BASE_PATH` unique per pytest process in `fichero-engine/tests/conftest.py` so concurrent verifier runs no longer collide on the same DuckDB path.
- Added a regression test that checks the helper creates distinct per-process temp directories.

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_conftest_base_path.py -q`
- `PYTHONPATH=fichero-engine/src bash -lc 'set -e; .venv/bin/pytest fichero-engine/tests/unit/test_api_providers.py -q >/tmp/fichero-api-providers-1.log 2>&1 & p1=$!; .venv/bin/pytest fichero-engine/tests/unit/test_api_providers.py -q >/tmp/fichero-api-providers-2.log 2>&1 & p2=$!; wait $p1 $p2; cat /tmp/fichero-api-providers-1.log; printf "\n---\n"; cat /tmp/fichero-api-providers-2.log'`
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/tests/conftest.py fichero-engine/tests/unit/test_conftest_base_path.py`

Notes:
- This was a backend test-harness fix only; no production code paths changed.

# done-codex-2026-05-25

Verified backend queue items `#1118` and `#1115` on the `codex` branch.

What I checked:
- `#1118` NER multi-provider abstraction with per-claim provider attribution is already present in the branch history and the focused backend tests still pass.
- `#1115` explicit KG-write workflow node is already present in the branch history and the focused workflow tests still pass.

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/workflows/test_ner_providers.py fichero-engine/tests/unit/kg/test_spacy_ner.py -q`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/workflows/test_kg_writer.py fichero-engine/tests/unit/workflows/test_default_workflows.py -q`
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/kg/ner.py fichero-engine/src/fichero/workflows/ner/__init__.py fichero-engine/src/fichero/workflows/ner/providers.py fichero-engine/src/fichero/workflows/tools/ner.py fichero-engine/src/fichero/workflows/tools/extractors.py fichero-engine/src/fichero/workflows/tools/__init__.py fichero-engine/src/fichero/kg/__init__.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/workflows/tools/kg_writer.py fichero-engine/src/fichero/workflows/tools/extract_all.py fichero-engine/src/fichero/workflows/tools/__init__.py fichero-engine/src/fichero/workflows/default_workflows.py fichero-engine/tests/unit/workflows/test_kg_writer.py fichero-engine/tests/unit/workflows/test_default_workflows.py`

Notes:
- No backend source edits were required for this session; the queue items are already implemented in the current codex history and the verify-first checks passed cleanly.

# done-codex-2026-05-25

Completed backend issue `#1111` on the `codex` branch.

What changed:
- Added a shared KG paragraph renderer in `fichero/kg/paragraph.py` that composes deterministic prose from `KnowledgeClaim` SVO fields and emits citation marker offsets.
- Added `POST /api/kg/render/paragraph` in `fichero/api/routes/kg_render.py` and registered it on the core API route table.
- Added a targeted regression test covering list-style rendering plus the new narrative endpoint contract and citation metadata.

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/kg/paragraph.py fichero-engine/src/fichero/api/routes/kg_render.py fichero-engine/src/fichero/api/main.py fichero-engine/tests/unit/test_kg_paragraph_rendering.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_kg_paragraph_rendering.py -q`

Notes:
- The renderer folds consecutive claims that share the same subject and verb into one sentence, while preserving per-claim citation metadata and marker offsets for downstream surfaces.

# done-codex-2026-05-25

Completed backend issue `#1115` on the `codex` branch.

What changed:
- Added an explicit `kg_writer` workflow node in `fichero/workflows/` and wired the shipped presets to use it.
- Taught `extract_all` to emit a `kg_payload` bundle and honor `persist_kg=false` so KG persistence can move out of the extractor path.
- Updated the Catalogue and `NER per-page (local)` preset JSON so the KG write is now a visible graph node rather than a hidden side effect.

Verification performed:
- `PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/kg/ner.py fichero-engine/src/fichero/workflows/ner/__init__.py fichero-engine/src/fichero/workflows/ner/providers.py fichero-engine/src/fichero/workflows/tools/ner.py fichero-engine/src/fichero/workflows/tools/kg_writer.py fichero-engine/src/fichero/workflows/tools/extract_all.py fichero-engine/src/fichero/workflows/tools/__init__.py fichero-engine/src/fichero/kg/__init__.py fichero-engine/tests/unit/workflows/test_ner_providers.py fichero-engine/tests/unit/workflows/test_kg_writer.py fichero-engine/tests/unit/workflows/test_default_workflows.py`
- `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/workflows/test_kg_writer.py fichero-engine/tests/unit/workflows/test_default_workflows.py -q`

Notes:
- The earlier #1118 commit is already sealed in this session; it added the multi-provider NER abstraction and the new `ner` workflow tool.

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
