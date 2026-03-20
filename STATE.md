# STATE.md — Fichero

Last updated: 2026-03-17 (session end, automation @ 03:03Z)

## Current Branch

`feature/313-connection-ui` (dirty: four Swift files + session memory docs)

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

- Ran `/session-start-auto` verification and session-end pass on `feature/313-connection-ui` without adding new source edits.
- Revalidated local `#313/#314/#315` implementation files:
  - `swiftlint lint --no-cache fichero-swiftui/fichero-swiftui/Views/ContentView+Navigation.swift fichero-swiftui/fichero-swiftui/Views/Library/LibraryView+ColumnConfig.swift fichero-swiftui/fichero-swiftui/Views/Library/LibraryView+InlineEditing.swift fichero-swiftui/fichero-swiftui/Views/Library/LibraryView+KeyboardShortcuts.swift` ✅
  - `PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/` ✅
  - `PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived` ❌ (22 failures; unchanged baseline mix: activity route 404s + provider/HuggingFace network + DB path permissions)
  - `xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj -scheme fichero-swiftui -configuration Debug -sdk macosx -derivedDataPath /tmp/fichero-derived -disableAutomaticPackageResolution build` ❌ (offline Swift package fetch + CoreSimulator/cache/log sandbox restrictions)
- Reconfirmed GitHub/network constraints:
  - `git fetch --all --prune` cannot resolve `github.com`
  - `gh auth status` token invalid for `dtubb`
  - `gh issue list --state open --milestone "0.0.1 - Core Library"` is still readable (public issue visibility), but write/auth flows remain blocked

## Blocked

- `git fetch --all --prune` cannot resolve `github.com` in this environment.
- `gh auth status` reports invalid token for account `dtubb`.
- `gh issue view` cannot reach `api.github.com` (issue-body retrieval blocked).
- Full pytest includes environment-constrained failures:
  - sandbox file permission failures opening app/library DuckDB files under `~/Library/Application Support/ca.tubb.fichero/`
  - HuggingFace provider route tests returning 502 due DNS/network unavailability
- `xcodebuild` cannot complete in this environment:
  - package resolution requires `github.com` access (DNS unavailable)
  - sandbox restrictions deny some CoreSimulator/cache/log paths

## Current 0.0.1 Outstanding (Open)

Active implementation focus:
- `#313` Library View: add connection/API error state UI (implemented locally; needs full app-level verification and PR flow)
- `#314` Library View: table Size column hardcoded dash (implemented locally; needs app-level verification + issue update when GitHub is reachable)
- `#315` Library View: replace print() error logging with ErrorService (implemented locally; needs issue update/PR flow when GitHub is reachable)

Release/QA gate issues still open:
- `#279` 0.0.1 sprint burn-down and release gate
- `#114` / `#115` / `#116` / `#117` QA audits (ready-for-test / Daniel validation)

## Next Session — Start Here

1. Start from [`memory/handoff-2026-03-17.md`](/Users/dtubb-openclaw/code/fichero/memory/handoff-2026-03-17.md) and continue on `feature/313-connection-ui`.
2. If network/sandbox constraints are lifted, rerun full validation (`swiftlint`, `xcodebuild`, `ruff`, `pytest`) to clear app-level verification for local `#313/#314/#315`.
3. As soon as GitHub API access/auth is restored, post implementation updates on `#313`, `#314`, and `#315`, then pick the next open 0.0.1 Library issue.
