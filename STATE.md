# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — clean, pushed. All feature branches deleted.

**Status:** Repo docs cleaned up. Agent-generic language throughout. Ready for backend review pass.

## In Progress

Nothing active.

## Known Pre-Existing Test Failures (not regressions)

- `test_canonical_knowledge_routes.py` — 20 failures (schema/DB setup issue)
- `test_background_tasks.py` — 1 failure (test_metrics_is_idempotent)
- `test_mcp_knowledge_adapters.py` — 2 failures (test checks router-internal paths, not final FastAPI paths)

Total: ~33 failing, ~1276 passing.

## Next Session — Start Here

1. **Backend code review pass** — systematic review of all Python backend files against `docs/architecture/api/`. Check consistency, file sizes, naming, patterns. See prompt in HISTORY.md (2026-04-13 entry) or ask for it.
2. **Fix pre-existing test failures** — 33 failures above are good cleanup targets before merging to main.
3. **Decide 0.0.2 → main merge** — all milestone work is in. Ready for review.
4. **Start 0.0.4 milestone** — #372 claim review queue UI, #373 contradiction triage, #374 search metrics panel, #375 interpretations workspace.

---
*Last updated: 2026-04-13* — repo cleanup complete, 0.0.2 pushed and clean
