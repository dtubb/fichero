# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean after test coverage sprint.

**Status:** All route modules now have tests. 1774 passing, 11 pre-existing background_tasks failures.

## In Progress

Nothing active.

## Known Pre-Existing Test Failures (not regressions)

- `test_background_tasks.py` — 11 failures (DuckDB+APScheduler concurrency issue in async tests)

## Next Session — Start Here

1. **Fix background_tasks.py failures** — 11 DuckDB/APScheduler concurrency failures in async tests. Investigate whether shared DuckDB connection causes the issue; may need per-task DB isolation.
2. **Backend code review pass** — systematic review of all Python backend files against `docs/architecture/api/`. Check consistency, file sizes, naming, patterns.
3. **Decide 0.0.2 → main merge** — all milestone work in, test coverage complete. Ready for final review before merge.
4. **Start 0.0.4 milestone** — #372 claim review queue UI, #373 contradiction triage, #374 search metrics panel, #375 interpretations workspace.

---
*Last updated: 2026-04-14* — route test coverage sprint complete (1774 passing)
