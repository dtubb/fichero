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
- **Manual: one-list collapse (item 1)** — confirm documents / saved searches / automation
  read as one continuous node list (no section headers), and that library-ROOT Finder
  drops still work now that the section-header drop targets are gone (drops go through the
  `unifiedRows` ForEach `.dropDestination`; the old "Library" header used to be one).

## Next — CONFIRMED ORDER (Daniel, 2026-07-21)
- A. Prefetch one level down → #3355 + option-click expand-all — ✅ DONE (`6a01b0963`).
- **1.** Collapse the 3 per-library sub-sections into ONE node list — ✅ DONE
  (`edd399fbe` collapse, `5ba662e99` Activity-residue retire). Removed Library/Saved
  Searches/Automation DisclosureGroup headers + divider; one continuous node list per
  tab, per-kind `unifiedRows` blocks preserve reorder. Retired dead Activity-row code;
  kept live `.run` view-mode routing.
- **2.** Sidebar bug-fixes: #3390 drag-drop, #2496 click-select + trailing affordance,
  #2491 right-align count.  ← NEXT
- **3.** Batch **actions**: delete / open-in-tabs over the multi-selection set.

## Critic pass on item 1 (findings verified as PRE-EXISTING, not regressions)
A `critic` reviewed the collapse. Both flagged issues were checked against the pre-change
code (`edd399fbe^`) and are behavior-preserving in my diff — carry as follow-ups:
- **Schedules+triggers drag-snap**: dragging an automation row shows the move indicator
  then snaps back (`handleUnifiedRowsMove` `default: return`). The OLD Automation section
  rendered the identical `scheduleItems + triggerItems` mixed block, so no change. Fix in
  **item 2** (drag-drop): `.moveDisabled(true)` on non-reorderable kinds.
- **`workflowItems` bucket computed but never rendered**: also true before the collapse
  (only used in `totalCount`). Verify it's always empty per-library, then delete the
  bucket. Follow-up.
- **`unifiedSectionExpansionStates`** left as dead persistence on SidebarState — file a
  cleanup ticket (harmless).

## Decisions for Daniel
- **#2515** moved to **Reader View — Page (#248)** ✓ (was mis-filed under Sidebar #116).
- On library switch I deliberately DON'T clear the multi-selection (disagreed with
  the critic): all open libraries render in the tree, so a selection in library A
  stays valid when focus moves to B — clearing would regress cross-library selection.
