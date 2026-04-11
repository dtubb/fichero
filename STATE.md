# STATE.md — Fichero

## Current Focus

**Primary Track:** Backend-first milestone execution

- 0.0.2 issue **#364** — implemented and closed (PR **#454** merged into `0.0.2`)
- 0.0.3 issue **#419** — migration/backfill tooling — **VERIFIED COMPLETE**
- 0.0.3 issue **#420** — reindex/repair jobs — **COMPLETE**
- 0.0.3 issue **#421** — multilingual baseline — **COMPLETE** (normalization integrated into KG routes)
- Unit backend test suite: **1228 passed, 21 skipped**

## In Progress

1. Backend-only execution of open milestone issues:
   - **0.0.3:** ~~#419~~ ✅, ~~#420~~ ✅, ~~#421~~ ✅, **#422** (next)
   - **0.0.4 (backend):** #435, #436, #437, #438, #439 (plus #423/#424 duplicates/related)
   - **0.0.5 (backend):** #425
   - **0.1.0 (backend-labeled):** #427, #428, #431 (+ #432-434 re-enable coordination)

2. Operational cleanup item (separate scope):
   - Repo-wide Ruff test-lint debt exists outside current feature scope

## Blocked

- None currently

## Next Session — Start Here

1. Claim and start **#422** (0.0.3 — Thin MCP Adapters for Canonical Knowledge APIs).
2. Use backend issue loop strictly: tests first, implement, pytest + ruff evidence, PR + close.
3. Keep GitHub issue comments updated with command evidence.
4. Continue backend-only until 0.0.3-0.1.0 backend set is complete.

---
*Last updated: 2026-04-11*