# STATE.md — Fichero

Last updated: 2026-03-15 (session end, automation @ 13:43Z)

## Current Branch

`main` (clean)

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

- Verified recovery from sandbox blockers (network, gh auth, .venv).
- Merged PR #312 into `main`.
- Closed issues #310 (Unicode filenames) and #311 (Workflow API 404).
- Rebuilt `.venv` and verified with 28 passing backend tests.
- Re-synced local `main` with origin.

## Blocked

- Claude Code sub-agent is hitting interactive permission prompts for `gh` commands in the terminal.

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

## Next Session — Start Here

1. Daniel: Approve the interactive `gh` permission prompt in the terminal.
2. Run `/assign-task` to pick up the next priority item from the 0.0.1 milestone.
3. Priority candidate: `#291` (default workflow templates) or `#288` (Search UX simplification).
