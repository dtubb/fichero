# STATE.md — Fichero

Last updated: 2026-03-09

## Current Branch

`main` (clean, synced with `origin/main`)

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

- Repo hygiene completed:
  - all current work merged into `main`
  - local stale branches cleaned
  - remote stale branches deleted (only `origin/main` remains)
- Pushed fixes directly to `main`:
  - `77c67c48` fix preview-pane image centering regression
  - `978af20a` fix Apply Workflow to Selection to execute created batch
  - `048bceb5` fix backend workflow runtime by registering `files` source tool
- Verified backend workflow unit tests after `files` tool fix:
  - `134 passed`
- Posted milestone progress update to `#279`:
  - https://github.com/dtubb/fichero/issues/279#issuecomment-4020847610

## Current 0.0.1 Outstanding (Open)

Highest priority implementation issues:
- `#292` crash when using `+` in workflow Files node picker
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

1. Execute/close `#292` first with deterministic repro + test pass.
2. Implement `#291` default workflow templates + reset.
3. Complete `#288` Search simplification and wire toolbar search flow QA.
4. Resolve `#263` build-phase reliability.
5. Finalize `#278` Sparkle 0.0.1 release configuration.
6. Drive `#238`, `#250`, and `#279` checklists to explicit pass/fail evidence.
