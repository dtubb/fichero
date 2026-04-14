# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean. Swift client pipeline fully working.

**Status:** All route handlers have typed Pydantic response models. OpenAPI spec generates complete named schemas for all 448 endpoints. Swift client (`fichero-api-client`) builds cleanly from the spec. 1785 passing, 5 pre-existing failures. Lint clean.

## In Progress

Nothing active.

## Known Pre-Existing Test Failures (not regressions)

- `test_knowledge_graph_security.py` — 2 failures (ImportError in PyKEEN tests)
- `test_providers.py` — 2 failures (mock target mismatch: patches `fichero.llm._get_litellm` but function moved to `llm_models`)
- `test_tasks.py::TestTaskPriority::test_tasks_ordered_by_priority` — 1 failure (APScheduler race condition)

## Next Session — Start Here

1. **Fix `test_providers.py` mock target** — patches `fichero.llm._get_litellm` but function is now in `fichero.llm_models`; update mock target to fix 2 failures.
2. **Decide 0.0.2 → main merge** — file-splitting done, all route handlers typed, Swift client building, test suite stable. Ready for final review and merge.
3. **Start 0.0.4 milestone** — #372 claim review queue UI, #373 contradiction triage, #374 search metrics panel, #375 interpretations workspace.

---
*Last updated: 2026-04-14* — typed response model pass + Swift client pipeline fixed (1785 passing, 5 pre-existing failures)
