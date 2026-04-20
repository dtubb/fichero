# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed clean through `9db9b539` (PDF fix revert).

**Active worktree:** `~/code/fichero-0.0.2` — 0.0.2 bug sweep, not released.

## In Progress

- `0.0.2` is feature-freeze-ish. Daniel verified most of the session's fixes; three items remain.

## Blocked / needs follow-up

1. **#619 backend startup** — poll interval went 1s → 100ms but Daniel says "not much faster". The real cost is elsewhere. Need profiling (DB open, hierarchy build, embeddings init). Don't guess.
2. **#591/#592 PDF scroll → grid sync** — revert landed (`9db9b539`). `contentView.postsBoundsChangedNotifications` approach wasn't ready. Try again with a different observation path — either poll `visiblePages` on a timer during interaction, or use a different PDFKit notification.
3. **#609 Run Workflow button enable** — Daniel hasn't tested the fix yet. Verify on device before closing.
4. **#622 icon/list view column too wide** — filed today, not addressed.

## Next Session — Start Here

1. **Profile `0.0.2` startup** (not speculation). Use `⏱` log breadcrumbs around `AppState.init` → `checkBackendHealth` → `LibraryManager.load` → `SidebarItemBuilder.build`. Find the actual bottleneck for #619/#605.
2. **Verify #609 Run Workflow** on device — preview doc open, no grid selection, trigger Run. If working: close #609 (part a only; part b input-kind stays open).
3. **Fix #622 (narrower grid column)** — lower the grid column's `frame(minWidth:)` in the content-layout view builders. Same pattern as #615.
4. **Take another run at #591/#592** — try `DispatchQueue.main.asyncAfter` polling `view.visiblePages` only while `NSEvent.pressedMouseButtons != 0` (scrollbar being dragged), stop when released.
5. **Think about #605 (startup perf) and the 0.0.3 scope** — Daniel asked what the difference is. See comparison block below.

## 0.0.2 vs 0.0.3 — milestone scope

- **0.0.2 "Backend Merge + Bug Fixes"** (milestone 8, OPEN): polish + drag/drop + reorder + preview parity. First public release gate. Issues remaining: #619, #605, #609, #600, #603, #595, #590, #591-revisit, #592-revisit, #598-verify, #599-verify, #610-verify, #614-verify, #616, #520, #622.
- **0.0.3 "Wire: Search v1"** (milestone 17, QUEUED): enable text search end-to-end. Search bar → results list → click to open doc. `SearchView`, `SearchResultsDisplay`, `SearchSidebarContent`. Daniel mentioned wanting semantic search working for 0.0.2 — flagged `searchEnabledInternal = true` already so the feature gate is on; actual wiring is the 0.0.3 scope.
- **Two-ahead rule holds**: 0.0.3 worktree (`~/code/fichero-0.0.3`) is on hold until Daniel approves 0.0.2.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-20 (session-end)* — 13 landed commits + 1 revert. See HISTORY.md for the full list.
