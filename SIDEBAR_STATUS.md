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

- **Item A — #3355 disclosure chevrons + option-click expand-all** (committed `6a01b0963`):
  - Root-caused: backend never sends `child_count` (engine Document model has no such
    field) → every folder decodes `childCount==0` → chevron missing until the folder is
    SELECTED (grid load side-effect). Old `isExpanded` `childCount>0` gate was dead.
  - Fix: eager one-level prefetch at both load seams (new `DocumentStore+SidebarPrefetch.swift`);
    `isExpanded` drops the dead gate; **option-click = expand whole subtree** (`expandSubtree`).
  - Extracted to a new file to keep `DocumentStore.swift` ≤400 (file_length).

## ⚠️ Ship gate for manager (before merge)
- **Full `xcodebuild` + FicheroTests** — worker only compile-checks; builds serialized.
- **Manual: shift-click range across section boundaries** (Library / Automation /
  Saved Searches DisclosureGroups + pinned global rows). Native `List(selection: Set)`
  in a nested tree is the one unknown. If range breaks at a boundary, a pure
  `contiguousRange(from:to:in:)` helper must be promoted in-scope (design §6.3).
- **Manual: #3355** — confirm folder-of-folders shows chevrons before any click, and
  watch the prefetch **fetch volume** on load/refresh: `loadCollections` now fires one
  `getChildren` per root container per refresh (Daniel chose eager). If a wide library
  lags, gate the prefetch or parallelize (`prefetchChildContainerChildren` ponytail note).
- **Behavioral test gap**: prefetch/expand tests are source-wiring only — a real GET-stub
  DocumentService test is blocked on the same mock-infra gap as #3917.

## Next — CONFIRMED ORDER (Daniel, 2026-07-21)
- A. Prefetch one level down → #3355 + option-click expand-all — ✅ DONE (`6a01b0963`).
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
