# Sidebar lane status

Branch `lane/sidebar-ux`. Worktree `~/code/fichero-worktrees/sidebar`. Do NOT push (manager gates).

## Done
- **Phase 1 fabel review** → `docs/design/sidebar-view-fabel-review.md` (committed).
  Grounded current state, target (one unified node list per tab), gaps vs the 8
  milestone-#116 issues, and the multi-select design.

## In progress
- **Phase 2: contiguous / multi-select** via native `List(selection: Set<SidebarDestination>)`.
  Files touched: `SidebarStateManagers.swift` (add `selectedDestinations` set +
  didSet sync), `SidebarView+ViewComponents.swift` (Set binding + Escape collapse).
  Plus pure helpers + unit tests.

## Next (separate commits, from the review §5)
- A. Prefetch one level down → finish #3355 + option-click expand-all.
- B. Collapse the 3 per-library sub-sections into one node list; retire Activity residue.
- C. Trailing affordance + right-aligned count (#2496 / #2491).
- D. Drag-drop fixes (#3390 / #2397).

## Decisions for Daniel
- **#2515** (Reader toolbar overlaps filmstrip) is mis-filed under Sidebar milestone
  #116 — it's a Reader-toolbar bug, not sidebar. Suggest re-milestoning. Left untouched.
- Multi-select **actions** (batch delete / open-in-tabs over the set) are a follow-up
  slice after the selection machinery lands — confirm scope.

## Build note for manager
- Worker only compile-checks small units (builds are serialized). Needs a full
  `xcodebuild` gate before merge.
