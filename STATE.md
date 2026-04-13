# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` (consolidated — all feature branches merged in)

**Status:** 0.0.2 fully consolidated. 0.0.3 milestone issues were previously completed on separate branches and are now merged. GitHub has only `0.0.2` and `main`.

## In Progress

Nothing active. All branch consolidation work complete.

## Known Pre-Existing Test Failures (not regressions)

- `test_canonical_knowledge_routes.py` — 20 failures (schema/DB setup issue)
- `test_background_tasks.py` — 1 failure (test_metrics_is_idempotent)
- `test_mcp_knowledge_adapters.py` — 2 failures (test checks router-internal paths, not final FastAPI paths)

Total: 33 failing, 1276 passing.

## Next Session — Start Here

1. **Decide 0.0.2 → main merge**: `0.0.2` has all milestone work (0.0.3 backend, SwiftUI bug fixes). Ready for review and merge to `main`.
2. **Fix pre-existing test failures**: The 33 failures above are good cleanup targets before merging to main — especially `test_canonical_knowledge_routes.py` (20 failures).
3. **Start 0.0.4 milestone** (Semantic UX + Trust Workflow):
   - #372: Claim review queue UI with curation workflow
   - #373: Contradiction triage UI with side-by-side provenance
   - #374: Search explanation and metrics visibility panel
   - #375: Interpretations workspace v1 linked to claims
4. **GitHub project board**: https://github.com/users/dtubb/projects/5

---
*Last updated: 2026-04-13* — branch consolidation complete, 0.0.2 pushed and clean
