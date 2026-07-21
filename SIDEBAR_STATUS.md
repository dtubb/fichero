# Sidebar lane status

Branch `lane/sidebar-ux`. Worktree `~/code/fichero-worktrees/sidebar`. Do NOT push (manager gates).

## Done
- **Phase 1 — fabel review** → `docs/design/sidebar-view-fabel-review.md` (committed).
  Current state, target (one unified node list per tab), gaps vs the 8 milestone-#116
  issues, multi-select design. Reviewed by a `critic` subagent; findings folded in (§6.4).
- **Phase 2 — native multi-select** (committed `da12433e2`):
  - `List(selection:)` now binds `Set<SidebarDestination>` → shift-click contiguous
    range, cmd-click toggle, shift+arrow extend come from macOS natively.
  - `SidebarSelectionState`: added `selectedDestinations` (highlight) + kept
    `selectedDestination` as routed primary; synced at two seams (no didSet).
  - Escape collapses batch → single anchor (`.onExitCommand`).
  - Tap-selection fallback (#645/#1165) bails when Cmd/Shift held (critic-caught bug).
  - Pure helpers `sidebarPrimaryDestination` / `sidebarCollapsedSelection` + unit tests
    in `SidebarSelectionTests.swift`.
  - Orphan cleanup `deleteSelectedActivityRuns` removed (commit `5639057c8`).

## ⚠️ Ship gate for manager (before merge)
- **Full `xcodebuild` + FicheroTests** — worker only compile-checks; builds serialized.
- **Manual: shift-click range across section boundaries** (Library / Automation /
  Saved Searches DisclosureGroups + pinned global rows). Native `List(selection: Set)`
  in a nested tree is the one unknown. If range breaks at a boundary, a pure
  `contiguousRange(from:to:in:)` helper must be promoted in-scope (design §6.3).

## Next — CONFIRMED ORDER (Daniel, 2026-07-21)
- A. Prefetch one level down → finish #3355 + **option-click = expand WHOLE subtree**
  (Finder-style, lazy-loading each level).
- **1.** Collapse the 3 per-library sub-sections into ONE node list (driven by `node_kind`);
  retire remaining Activity-row residue (handleUnifiedRowTap, selectedActivityItemIds,
  ActivityRunGridCell) — keep live Activity view-mode routing (`unifiedSelectedRun`).
- **2.** Sidebar bug-fixes: #3390 drag-drop, #2496 click-select + trailing affordance,
  #2491 right-align count.
- **3.** Batch **actions**: delete / open-in-tabs over the multi-selection set.

## Decisions for Daniel
- **#2515** moved to **Reader View — Page (#248)** ✓ (was mis-filed under Sidebar #116).
- On library switch I deliberately DON'T clear the multi-selection (disagreed with
  the critic): all open libraries render in the tree, so a selection in library A
  stays valid when focus moves to B — clearing would regress cross-library selection.
