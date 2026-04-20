# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `b8a1e483`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — sidebar drag/drop feature-complete, Daniel device-testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (on hold, two-ahead rule)

**Status:** #607 (insertion-line drop) effectively shipped via spacer-row pattern — thin per-view `.onDrop` spacers bypass the SwiftUI DisclosureGroup limitation. Top-level + nested cross-hierarchy drops both work with cycle guard. Debug HUD removed. Daniel to verify on relaunch.

## Issues status

**Progressed recently:**
- `#607` folder reorder / cross-hierarchy drop — TOP-LEVEL, NESTED, and BETWEEN-ROW all work now via a combination of `.onMove` (same-list reorder) + `SidebarInsertionSpacer` (cross-hierarchy insert) + per-row `.onDrop` (into-folder). Cycle prevention via `isDescendant` on nested drops.
- `#612` sidebar drag/drop/select — resolved per Daniel's previous "working good" verdict. Keep closed pending any regression.
- `#610` Finder folder flatten — fixed.
- `#605` click-then-wait — partially fixed (off-main thumbnails + cache).

**Still to confirm this session:**
- Drop a folder between sibling rows → blue line appears, drop reparents to this level at correct offset.
- Cycle: drag parent onto its own descendant → silently rejected (no backend call).
- "Bug 1" (parent-onto-child): Daniel reported this but the existing cycle check in `handleDropIntoFolder` should reject. Needs a fresh log from Daniel showing the exact drag + whether "circular reference detected" appears.

**Still open on 0.0.2:**
- `#613` context-menu Delete no-op
- `#615` sidebar mode-icon rail min width
- `#609` toolbar "Run Workflow" doesn't execute
- `#608` Finder-style sidebar polish (includes right-hover chevron wish)
- `#604` preview magnifier 25% cap
- `#603` ingest mode badges
- `#618` flatten row indentation to match NNW
- `#617` per-pane toolbars (NNW pattern)
- `#616` hide icon-grid list panel toggle
- `#619` slow backend connection on launch

## Test Health

**Swift tests:** 259 pass / 13 pre-existing #594 fixture failures. Includes 11 new `SidebarReorderedDocIdsWithInsertTests`.

**Python tests:** 1793 pass / 21 skipped.

## Next Session — Start Here

1. **Verify the spacer drops on device** — drag a folder from inside a nested folder → drop on the blue line between top-level siblings. Should reparent + position at offset. Also test the cycle case (parent onto descendant) — should silently reject.
2. **Fix "Bug 1" if still present** — if Daniel reproduces "can drop parent onto child," capture the log output around "handleDropIntoFolder called with..." to see if the cycle check fires or if `allCachedItems` lookup is failing.
3. **Consider spacer height tuning** — spacers are 2pt at rest / 3pt targeted. If Daniel finds them too thin to hit reliably, bump the at-rest height (edit `SidebarInsertionSpacer.body` in `SidebarView+ViewComponents.swift`).
4. **Then pivot to untouched bugs** — #613 (Delete), #609 (Run Workflow), #608 (Finder polish), #615 (mode-icon rail), or the startup-latency issues in #619/#605.

## Parallel Workflow

0.0.2 is the first public release (0.0.1 is private). 0.0.3 (Wire: Search v1) waits. Gate: Claude never merges to `main` without Daniel's `/release N`.

---

*Last updated: 2026-04-20 (insertion-line drop mini-session)* — 4 commits. `SidebarInsertionSpacer` ships the insertion-line feature via per-view `.onDrop` that bypasses the SwiftUI DisclosureGroup limitation. Memory updated with the spacer-row pattern.
