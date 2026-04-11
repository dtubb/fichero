# STATE.md — Fichero

## Current Focus

**Primary Track:** Backend-first milestone execution

- 0.0.2 issue **#364** is now implemented and closed (PR **#454** merged into `0.0.2`)
- Backend security/runtime hardening included in that PR (sources routes, SSRF redirect-safe flow, library-path validation, PyKEEN compatibility guard)
- Unit backend test suite currently passing in this worktree:
  - `PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived`
  - Result: **1228 passed, 21 skipped**

## In Progress

1. Backend-only execution of open milestone issues after 0.0.2:
   - **0.0.3:** #419, #420, #421, #422
   - **0.0.4 (backend):** #435, #436, #437, #438, #439 (plus #423/#424 duplicates/related)
   - **0.0.5 (backend):** #425
   - **0.1.0 (backend-labeled):** #427, #428, #431 (+ #432-434 re-enable coordination)

2. Operational cleanup item (separate scope):
   - Repo-wide Ruff test-lint debt exists outside current feature scope

## Blocked

- None currently

## Next Session — Start Here

1. Claim and start **#419** (0.0.3 migration/backfill tooling).
2. Use backend issue loop strictly:
   - tests/security tests first
   - implement
   - run pytest evidence
   - run targeted ruff (`fichero-api/src/` minimum; broader lint debt tracked separately)
   - PR to milestone branch + close issue.
3. Keep GitHub issue comments updated with command evidence and acceptance status.
4. Do not start frontend milestone work until backend milestone set is complete and verified.

---
*Last updated: 2026-04-11*