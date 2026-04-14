# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean after backend file-splitting pass.

**Status:** All oversized files split. 1780 passing, 5 pre-existing failures. Lint clean.

## In Progress

Nothing active.

## Known Pre-Existing Test Failures (not regressions)

- `test_knowledge_graph_security.py` — 2 failures (ImportError in PyKEEN tests)
- `test_providers.py` — 2 failures (mock target mismatch: patches `fichero.llm._get_litellm` but function moved to `llm_models`)
- `test_tasks.py::TestTaskPriority::test_tasks_ordered_by_priority` — 1 failure (APScheduler race condition)

## Next Session — Start Here

1. **Backend code review pass** (#460) — systematic review of all Python backend files against `docs/architecture/api/`. Check consistency, naming, patterns, thin handlers. File splitting is done; focus shifts to conventions pass.
2. **Fix `test_providers.py` mock target** — patches `fichero.llm._get_litellm` but function is now in `llm_models`; update mock target to fix 2 failures.
3. **Decide 0.0.2 → main merge** — all milestone work in, test coverage complete. Ready for final review.
4. **Start 0.0.4 milestone** — #372 claim review queue UI, #373 contradiction triage, #374 search metrics panel, #375 interpretations workspace.

---
*Last updated: 2026-04-14* — file-splitting pass complete (1780 passing, 5 pre-existing failures)
