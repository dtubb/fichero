(AI generated. Reviewed by Daniel in-session 2026-07-21.)

# Sidebar View — Fabel Review

Milestone [#116 "Sidebar View"](https://github.com/dtubb/fichero/milestone/116).
Sub-milestones: **Folders**, **Nodes**, **Workspace**. Lane: `lane/sidebar-ux`.

Design-first pass before touching code: current state (grounded in the source on
this branch), the target Daniel named, the gaps, and a concrete plan. Every claim
cites a file. Priority feature = **contiguous / multi-select** (Phase 2 below).

---

## 1. Scope & sources read

- Views: `Views/Sidebar/**` (37 files, ~6.8k LoC). Entry: `SidebarView.swift`.
- Selection: `Views/Sidebar/State/SidebarStateManagers.swift`
  (`SidebarSelectionState`, `SidebarDestination`).
- Node model backing: `docs/contributor/node-model.md`,
  `fichero-server` `Document.node_kind` (read-only reference — engine not touched).
- Existing tests: `fichero/fichero-tests/Models/SidebarItemTests.swift` (Swift Testing).

---

## 2. Current state (grounded)

### 2.1 It is already a native `List(selection:)` tree — single-select

`SidebarView+ViewComponents.swift:71` renders the whole sidebar as one
`List(selection: $selectionState.selectedDestination)` with `.listStyle(.sidebar)`.
Rows carry `.tag(item.destination)` (`SidebarView+UnifiedRows.swift:140`) and the
library disclosure carries `.tag(SidebarDestination.library(...))`
(`SidebarView+UnifiedLibrarySections.swift:86`).

The binding is a **single optional** — `SidebarSelectionState.selectedDestination:
SidebarDestination?` (`SidebarStateManagers.swift:150`). `SidebarDestination`
(`:13`) is a `Hashable` enum with a `serializedID` string round-trip, so it is
already a first-class, hashable selection value.

**Consequence:** the sidebar cannot express a multi-row selection today. The one
place that needed it — Activity rows — hand-rolled a parallel `Set<String>`
(`selectedActivityItemIds`, `SidebarView.swift:71`) driven by a `TapGesture`
reading `modifierFlags`, precisely *because* "`List(selection:)`'s `String?`
binding can't express a `Set<String>`" (`SidebarView+UnifiedRows.swift:108-111`).
Activity is now gone (§2.4), so that bespoke path is dead weight — the lesson is
that the fix belongs in the List binding, not a side-channel.

### 2.2 Rendering is split into hard-coded per-library sub-sections

`SidebarView+UnifiedLibrarySections.swift:133` builds each library as three
separate `DisclosureGroup` sections — **Library** (`:138`), **Automation**
(`:162`), **Saved Searches** (`:177`) — from pre-filtered buckets
(`computeLibraryItemBuckets`, `:29`) split by `itemType` / `category`. App-level
destinations (Workflows / Batches / Entities / Research) are pinned once at the
bottom via `pinnedGlobalNavigationRows()` (`SidebarView+ViewComponents.swift:77`,
rationale at `SidebarView+UnifiedLibrarySections.swift:155-160`, #1456).

This is the "separate sections" era Daniel described. It is not one node list.

### 2.3 Selection routing

`.onChange(of: selectionState.selectedDestination)` → `handleSelectionChange`
(`SidebarView+SelectionHandling.swift:13`) maps a single destination to
`sidebarMode` + `viewMode`, switching `windowState.libraryId` when the item is in
another library (`:104`). `lastHandledSelectionDestination` makes it idempotent so
a restored `@SceneStorage` selection reconciles once (#2548). A `TapGesture`
fallback (`SidebarItemRow+Presentation+Body.swift:34`) covers native-List click
misses (#645/#1165) by writing `selectedItemId`.

### 2.4 Activity is already removed from the tree

`activityItems` is hard-coded empty (`SidebarView+UnifiedLibrarySections.swift:120`)
and the Activity section no longer renders. Residue remains: `selectedActivityItemIds`
state, `SidebarView+ActivityRows.swift`, and `onDeleteCommand { deleteSelectedActivityRuns() }`
(`SidebarView+ViewComponents.swift:83`). Dead — safe to retire as part of this lane.

### 2.5 Lazy children + disclosure (#3355 already partly fixed)

Expansion lazy-loads one level: `SidebarItemRow.isExpanded` (`:177`) calls
`store.loadSidebarChildren(of:)` on expand when `childCount > 0 && children == nil`.
`isExpandable` (`SidebarItem.swift:67`) shows a chevron when `children` is non-nil
**or** `document.isNavigableContainer && childCount > 0`. `sidebarNeedsDeferredDisclosureContent`
(`SidebarItemRow+Presentation+Body.swift:4`, #3355) keeps the chevron visible while
children stream in. So the chevron is correct **iff `childCount` is populated
before expansion** — which is the remaining #3355 gap (metadata not prefetched
one level down).

### 2.6 Per-tab, node-backed, observable

Selection is per scene: `@SceneStorage("selectedSidebarItem")` (`LibraryWindow.swift:43`),
one `SidebarSelectionState` per `ContentView`. "Sidebar is per tab" already holds.
Data flows through `@Observable` stores (`libraryManager`, `documentStore`, …);
the sidebar builds `SidebarItem`s from those, matching the node model
(`docs/contributor/node-model.md`: everything is a `Document` with
`doc_type`/`node_kind`/`prototype_key`) and the observable-data-layer /
knowledge-consistency mandates (no hand-rolled `URLSession`).

---

## 3. Target design (Daniel, this session)

1. **One unified node list per library, per tab.** Collapse the Library /
   Automation / Saved Searches sub-sections (§2.2) into a single tree of nodes.
   Node behavior comes from the backend `node_kind` (saved_search, workspace,
   plan, alias/bookmark, …), not from front-end bucket sorting.
2. **Global default workflows pinned at the top**, but a workflow can be placed
   anywhere in the tree (it is a node like any other).
3. **Lazy-load one level down** so a folder-of-folders shows the correct
   disclosure chevron before expansion (finishes #3355). **Option-click** a
   chevron expands the entire subtree (Finder behavior).
4. **Contiguous + discontiguous multi-select** (the priority — Phase 2).
5. Constraints: `@Observable` stores everywhere; no hand-rolled URLs; per-tab
   selection state; semantic system fonts; standard controls; show ALL items;
   context menu + open-in-tab/window; every frame perfect.

---

## 4. Gaps vs the 8 open issues

| # | Issue | Where it lives | Note |
|---|-------|----------------|------|
| 2496 | Hard to click-to-select; add easy click-select + trailing affordance | `SidebarItemRow+Presentation+Body.swift` hit region; tap fallback | Full-width `contentShape` exists (`fullWidthLabel:213`); trailing affordance missing. Overlaps multi-select work. |
| 2491 | Right-align item count | `SidebarView+LibraryHeaderHelpers.swift` disclosure label | Push count to trailing edge; small. |
| 3355 | Disclosure chevron only after click; nested children invisible | §2.5 | Prefetch `childCount` one level down (target §3.3). Partly fixed. |
| 3390 | PDF drag-drop no drop indication / does not drop | `SidebarItemRow+DropHandlers.swift`, `+Drop.swift` | Drop-target highlight exists (`sidebarDropHighlight`); PDF UTType path failing. |
| 2397 | Can't drag item between libraries | `SidebarItemRow+DropHandlers.swift` | Cross-library reparent. |
| 2515 | Reader toolbar overlaps filmstrip; overflow → "…" | Reader toolbar, **not sidebar** | Mis-filed under this milestone; flag to manager. |
| 2498 | iOS shows one open library, Mac shows two | `libraryManager.openLibraries` / iOS shell | Platform parity; low sidebar-view coupling. |
| 2408 | iPad slow on rotation | perf | Likely whole-tree rebuild churn; §2.2 buckets + #3862 relevant. |

None of the 8 is "multi-select" — that is Daniel's separately-named priority, and
it also unblocks 2496 (selection ergonomics).

---

## 5. Plan (priority order)

**Phase 2 (this lane, now): contiguous / multi-select.** Adopt native
`List(selection: Set<SidebarDestination>)`. Detail below §6. Ships with unit tests.
**Ship gate (manual, manager build):** shift-click range must be verified across
the Library / Automation / Saved-Searches DisclosureGroup boundaries and the
pinned global rows — the one thing native selection may not handle in a nested
tree. If range breaks at a boundary, promote a pure `contiguousRange(from:to:in:
[flattenedIDs])` helper into scope before merge (§6.3).

Then, in rough order (separate commits, design-doc already grounds them):

- **A. Prefetch one level down** → finishes #3355. When a folder node loads,
  fetch its children's `childCount` (metadata only) so chevrons are correct. Add
  **option-click = expand-all-descendants** on the chevron.
- **B. Collapse to one node list** (§3.1). Replace the three per-library
  DisclosureGroups (§2.2) with a single node tree driven by `node_kind`. Retire
  the Activity residue (§2.4). Largest change — do after multi-select lands so the
  two don't collide on the same files.
- **C. Trailing affordance + right-aligned count** → #2496 / #2491 (small, visual).
- **D. Drop fixes** → #3390 / #2397 (drag-drop lane; own files).

This review commits first; each item lands as its own small commit.

---

## 6. Phase 2 design — multi-select

### 6.1 Approach: native `Set` selection (ponytail: SwiftUI already does this)

macOS `List(selection: Binding<Set<SelectionValue>>)` gives, for free:
shift-click contiguous range from the anchor, cmd-click toggle, shift+arrow
extend, and plain-click collapse to one. That is exactly the spec. Rows are
already `.tag(SidebarDestination)` (hashable), so the only change is the binding
type — no per-row rework, no hand-rolled model (which is what the dead Activity
`Set<String>` path was, §2.1).

### 6.2 State change (`SidebarSelectionState`)

Add the highlight set; keep `selectedDestination` as the **routed primary** that
every existing consumer already reads/writes (§6.4). One reconciliation seam:

```swift
var selectedDestinations: Set<SidebarDestination> = []      // bound to the List
var selectedDestination: SidebarDestination? {              // routed primary (unchanged API)
    didSet {
        guard oldValue != selectedDestination else { return }
        // Programmatic single-select (openInWindow, creation handlers, restored
        // scene selection) collapses the highlight to match. No-op when the set
        // already agrees (List binding already set it).
        if let d = selectedDestination, selectedDestinations != [d] {
            selectedDestinations = [d]
        }
    }
}
```

The List binding (in `unifiedContent`) is the other seam — it derives the primary
from the set so the detail pane follows a **single** row and stays stable during a
batch selection:

```
set count == 0  → selectedDestination = nil
set count == 1  → selectedDestination = the one row   (routes, existing behavior)
set count  > 1  → leave selectedDestination as-is      (batch mode; no detail thrash)
```

Escape → collapse the set to `{primary}` via `.onExitCommand` (macOS). Plain click
already collapses natively.

### 6.3 Testable pure logic (Swift Testing)

Native SwiftUI owns range/toggle, so the *custom* code is the primary-derivation +
collapse rules. Extract them as free functions (mirroring the existing
`sidebarSelectionFallback`) and unit-test:

- `sidebarPrimaryDestination(for: Set, previous:) -> SidebarDestination?`
  (0→nil, 1→that, >1→previous). Covers "cmd-toggle down to one routes".
- `sidebarCollapsedSelection(primary:) -> Set` (Escape / plain-click collapse).

"Range from anchor" is native; if the tree (nested DisclosureGroups) proves flaky
for shift-range, add a pure `contiguousRange(from:to:in: [flattenedIDs])` helper
and test it — but not before it's needed (YAGNI).

### 6.4 As-built refinements (from the fabel critic pass)

A critic review of this plan surfaced three correctness issues, all fixed in the
shipped code:

- **No `didSet`.** An earlier sketch synced the set from a `didSet` on
  `selectedDestination`; during a batch selection the List binding legitimately
  holds `selectedDestinations != [primary]`, so a force-syncing didSet would
  clobber the multi-row set. The two write seams (the `selectedItemId` setter and
  the List binding) sync explicitly instead, each in a fixed order (set first,
  then derive primary).
- **Primary never points at an unhighlighted row.** `sidebarPrimaryDestination`
  falls back to a remaining set member when the previous primary was just
  deselected from a 3+ selection (not blindly `previous`).
- **Tap fallback bails on modifier keys.** The `#645/#1165` plain-click fallback
  writes a *single* selection; it now returns early when Cmd/Shift is held so it
  can't collapse a native multi-select gesture.

### 6.5 Blast radius

`selectedDestination` / `selectedItemId` keep their API, so the ~25 external
writers (mostly `ContentView+*` navigation/persistence, creation handlers) are
untouched. Only two files change: `SidebarStateManagers.swift` (add set + didSet)
and `SidebarView+ViewComponents.swift` (binding + Escape). Batch **actions**
(delete/open-in-tabs over the whole set) are a follow-up slice; this slice lands
the selection machinery + tests first.
