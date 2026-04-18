# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `1c532cdd`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar UX polish + regression hardening; Daniel actively testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (on hold — two-ahead rule)

**Status:** 28 commits on 0.0.2 this session. Sidebar drag/drop/select is now reliable; reorder persists via native `.onMove` + backend `Document.sort_order` migration. Thumbnails decode off-main and cache hits, so folder-click latency dropped sharply. −1,400 LOC of dead code removed.

Daniel confirmed at session end: "working good."

## Issues status

**Progressed this session:**
- `#612` sidebar drag/drop broken — essentially resolved via 9 commits. Single `.onDrop(of: [UTType])`, removed competing TapGesture on Text, Return-key rename, contrast fix, FocusedValue warning silenced, tag restored on top-level rows.
- `#610` Finder folder drop flattens — fixed (`14146f8e`): `ingest_folder` now creates a folder Document when `parent_id` is given.
- `#605` click-then-wait — partially fixed (`48a738da` off-main thumbnails, `23559dbf` cache). Residual latency still present; needs Instruments for the remaining main-thread hot spots.
- `#607` between-row insertion-line reorder — TOP-LEVEL works now (`.onMove` attached, backend endpoint wired via `Document.sort_order` migration + declaration). Nested-folder insertion lines remain un-rendered (SwiftUI limitation with DisclosureGroup).

**Still open on 0.0.2:**
- `#613` context-menu Delete no-op
- `#614` bolder section headers + native accent — shipped
- `#615` sidebar mode-icon rail min width
- `#609` toolbar "Run Workflow" doesn't execute
- `#608` Finder-style sidebar polish
- `#604` preview magnifier 25% cap
- `#603` ingest mode badges

## Test Health

**Swift tests:** 253 pass / 13 pre-existing #594 fixture failures (unrelated to this session). Added `SidebarActionsEqualityTests` + `SidebarSelectionInfoEqualityTests` (regression guards for FocusedValue churn fix).

**Python tests:** 1793 pass / 21 skipped. Includes all ingest_module tests after the 14146f8e parent-folder fix.

## Next Session — Start Here

1. **Confirm `2a400cc9` reorder-persist works in practice** — Daniel needed to restart backend to pick up the Document.sort_order field. On a fresh session, drag a top-level folder to reorder; verify items stay in new position after the refresh. If they still snap back, the OpenAPI schema didn't regen cleanly — re-run `./scripts/start_backend.sh`.
2. **Then: decide on remaining sidebar UX items** — insertion lines inside subfolder DisclosureGroups (requires custom DropDelegate or spacer-row hack; non-trivial), chevron-on-right-hover on category headers (requires replacing DisclosureGroup wholesale), or the remaining click-wait latency (needs Instruments profiling of a folder-click).
3. **Flip back to untouched bugs** — #613 (Delete no-op), #609 (Run Workflow), #608 (Finder polish), #615 (mode-icon rail) are all visible but unrelated to what we worked today.
4. **Debug HUD is still in the sidebar** (yellow bar showing selectedItemId). If Daniel wants it removed for production testing, delete or `#if false`-gate the `sidebarDebugHUD` block in SidebarView+ViewComponents.swift.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-18 (sidebar deep overhaul session)* — 28 commits. #612 resolved, #610 resolved, #605 partial, #607 top-level working. Memory updated with 4 new durable lessons + 1 revision.
