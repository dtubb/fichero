# STATE.md — Fichero

Last updated: 2026-03-10

## Current Branch

`main` (clean working tree)

## Source of Truth

- Scope/status/priorities are on GitHub only:
  - Milestones: https://github.com/dtubb/fichero/milestones
  - Issues: https://github.com/dtubb/fichero/issues
  - Project: https://github.com/users/dtubb/projects/5
- Local `PLAN.md`/`TASKS.md` are pointer files only.

## 0.0.1 Release Gate

Primary gate issue: `#279`
- https://github.com/dtubb/fichero/issues/279

Milestone `0.0.1` due date:
- 2026-03-22

## Completed This Session

- Pushed directly to `origin/main`:
  - `64c6edc1` fix document deletion integrity and API contract sync (`#279`)
    - Cascading document delete now removes descendants, artifacts, and embeddings.
    - Added `POST /api/documents/cleanup-orphans` for stale unreachable document cleanup.
    - Fixed workflow registry default-port behavior for tools with explicit empty inputs.
    - Synced OpenAPI/endpoint contracts across backend + Swift client.
  - `7b8dabde` fix sidebar state reset + test isolation (`#220`)
    - `DeleteStateManager.cancelDelete()` now clears `showingDeleteError`.
    - `LibraryManagerTests` reset singleton mutable state in setup/teardown.
- Verification completed:
  - Backend:
    - `PYTHONPATH=fichero-api/src fichero-api/.venv/bin/ruff check fichero-api/src fichero-api/tests/unit/test_api.py`
    - `PYTHONPATH=fichero-api/src fichero-api/.venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived`
    - Result: `789 passed, 16 skipped`.
  - Swift:
    - Focused `xcodebuild test` suites passed:
      - `LibraryManagerTests`
      - `StateManagerTests`
      - `EndpointValidationTests`
      - `ContractTests`
- GitHub updates posted:
  - `#279`: status/progress + verification summary.
  - `#220`: fix note and test stabilization summary.
  - `#238`: proposed concrete 0.0.1 manual QA runbook checklist.

## Current 0.0.1 Outstanding (Open)

Highest priority implementation issues:
- `#291` built-in default workflow templates + reset
- `#288` simplify Search UX to 0.0.1 scope
- `#263` SwiftLint/Xcode build-phase path reliability
- `#278` Sparkle updater release configuration
- `#232` / `#233` / `#235` remaining feature-gate hardening and hidden-surface cleanup

Release/QA gate issues still open:
- `#238` manual QA checklist
- `#250` workflow QA and validation gates
- `#114` / `#115` / `#116` / `#117` QA audits (ready-for-test / Daniel validation)

## Active Risks

- Embedding model first-run download is large (`intfloat/multilingual-e5-large`, ~2.25GB) and causes long first execution.
- Sparkle feed/signing/distribution path is not yet finalized for production update channel.
- Xcode SwiftLint script-phase behavior still inconsistent on some local setups.

## Next Session — Start Here

1. Implement `#291` default workflow templates + reset.
2. Complete `#288` Search simplification and wire toolbar search flow QA.
3. Resolve `#263` build-phase reliability.
4. Finalize `#278` Sparkle 0.0.1 release configuration.
5. Drive `#238`, `#250`, and `#279` checklists to explicit pass/fail evidence.

## In Progress Now

- 0.0.1 release gate hardening on `main`:
  - complete remaining release-gate issues and capture pass/fail evidence on GitHub
  - prioritize template workflows and simplified search scope for 0.0.1
