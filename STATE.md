# STATE.md — Fichero

Last updated: 2026-03-13 (session end, automation)

## Current Branch

`feature/issue-310` (1 commit ahead locally)

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

- `/session-start-auto` selected and executed issue `#310` (Unicode filename crash in `/api/storage/source`).
- Implemented RFC 5987-safe `Content-Disposition` header generation in backend storage route:
  - Added ASCII fallback `filename="..."` plus UTF-8 `filename*=` parameter.
  - Prevents header encoding crashes on non-ASCII filenames while preserving extension hints for Quick Look.
- Added backend unit coverage for header generation in `fichero-api/tests/unit/test_storage.py`.
- Committed fix on branch `feature/issue-310`:
  - `40ee2a1c` — `fix: handle unicode source filename header (#310)`
- Autonomous `/session-start-auto` startup checks executed.
- Confirmed hard blockers before milestone task execution:
  - Git working tree on `main` is dirty with pre-existing source edits.
  - `gh auth status` fails due to invalid token, so GitHub issue claim/progress sync is blocked.
- Performed docs/handoff-only updates for safe continuity:
  - Updated this `STATE.md` with concrete blocker conditions.
  - Added `memory/2026-03-13.md` session log.
  - Added `memory/handoff-2026-03-13.md` next-run handoff.
  - Refreshed blockers after re-check at `2026-03-13T19:02:33Z`.
- Implemented and verified SwiftUI/editor stability fixes requested by Daniel:
  - Fixed rich-text autosave decode failures by using a lenient date transcoder in `FicheroClient`.
  - Hardened icon-mode keyboard navigation (`up/down/left/right/page up/page down`) with key-down handling plus move-command fallback.
  - Persisted rich-text ruler visibility via `@AppStorage("editor.rulersVisible")` and wired Format menu toggle label/state.
  - Added default content-pane focus on `ContentView` appear to improve immediate keyboard navigation reliability.
- Validation completed:
  - `swiftlint` passes on touched files.
  - `xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme Fichero -configuration Debug -sdk macosx build` succeeds.
- GitHub tracking cleanup:
  - Added issue `#310` (storage Unicode filename header crash).
  - Added issue `#311` (workflow API 404/save-load visibility failure).
  - Assigned both to milestone `0.0.1 - Core Library`.
- Repo hygiene checks:
  - No uncommitted source changes left after sync.
  - `main` pushed and up to date.

## Blocked

- No implementation blockers on #310.
- Infrastructure/tooling blockers in this sandbox:
  - Python env unavailable for project checks (`.venv/bin/ruff` and `.venv/bin/pytest` missing; no `ruff`/`pytest` on PATH).
  - `xcodebuild` cannot access required cache/log paths in sandbox, so full Swift build verification is blocked here.
- Product blockers remain in open issues:
  - `#311` workflow endpoints returning 404 / save-load UX broken
  - `#310` storage source-file response crashes on Unicode filenames (fixed locally on `feature/issue-310`, needs PR/merge)

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

1. Run backend checks in a full local dev env (outside this sandbox):
   - `PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/`
   - `PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_storage.py`
2. Run `xcodebuild` in unrestricted environment to confirm no frontend regressions.
3. Open PR for `feature/issue-310` and update issue `#310` with fix + validation notes.
4. Continue with issue `#311` (workflow API 404 / save-load visibility).

## In Progress Now

- 0.0.1 release hardening: workflow reliability and storage filename handling.
- Workspace is clean and ready for next autonomous run.

## Autonomous Session Notes (2026-03-11)

- `/session-start-auto` selected candidate task `#114` (lowest-numbered open issue in milestone `0.0.1 - Core Library`).
- Session blocked before execution due to repository instruction gate in `AGENTS.md`: "Current Phase: Planning (Phase 0)" and "No coding until Daniel approves the plan."
- No source code changes made. Await explicit Daniel approval to transition from Phase 0 to implementation work.
- Daniel approved transition to execution on 2026-03-11; `AGENTS.md` updated to execution mode and GitHub-first milestone workflow.
- Follow-up `/session-start-auto` run on 2026-03-11 is blocked before task claim/execution: `gh` commands (`gh issue list`, `gh auth status`) hang with no output, so milestone task selection/claim cannot be completed safely.
- Subsequent `/session-start-auto` run succeeded with GitHub access restored; selected unblocked issue `#220`, verified it was already implemented on `main`, and closed it as completed.

## Autonomous Session Notes (2026-03-13)

- Startup context loaded from `SOUL.md`, `MEMORY.md`, `STATE.md`, and `TASKS.md`.
- `main` is not clean; modified SwiftUI files were already present at session start.
- GitHub access is currently blocked by invalid `gh` token:
  - `gh auth status` output: "The token ... is invalid."
- No milestone implementation work was started in this run to avoid writing on top of unknown in-progress code.
- Session completed in docs/handoff mode only, with explicit unblock conditions for the next hourly automation.
- Re-check on `2026-03-13T19:02:33Z` confirms blockers are still active with no state change:
  - dirty Swift source files still present on `main`
  - `gh auth status` still fails for `dtubb`
