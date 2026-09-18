# Library View Modes — Design Spec

> Milestone: library-view-modes (GitHub #312)
> Manual: TBD — the user manual needs a "Changing how the Library looks" section: icon/list/
> table/columns as the everyday browsing modes, Sheet/Cards/Timeline/Calendar/Map as the
> dataset modes over the same rows, Canvas/Space as the spatial modes, and that switching
> between them never changes what you're looking AT, only how it's drawn.

> Design-led spec (Testing Constitution). The creative director owns the intent; tests
> enforce it; code makes them pass. One line per behavior, each cited by its pinning test.
> **Status: DRAFT — PASS 1 of 2** (built behaviors only, grounded in disk 2026-09-18; the
> fold-in of the nine legacy milestones' ~101 open issues is PASS 2, awaiting the fold plan's
> review before any issue moves).
> Tags: **[OK]** behaves this way today · **[PARTIAL]** implemented, not fully verified/tested
> · **[BROKEN]** regression, code contradicts the line · **[GAP]** intended, never built.

## Intent (the design)

This spec is the OTHER axis from `modes-to-panes.md`. That spec rules that everything the
sidebar can select — a workflow, a chat, an entity, the knowledge graph — is a **node**, not
a mode, and that selecting one never changes what the Library pane IS: "the Library pane is
always the navigator... selecting a node keeps the Library showing the tree/table it already
showed." This spec covers what happens ONCE a folder or a KG collection IS the thing the
Library is navigating: the same row set (documents, or — per that spec's own
`m2p.kg-graph-retires-as-library-takeover` — entities/claims when a KG collection is selected)
renders through one of **eleven interchangeable view modes**: Icon, List, Table, Columns, four
dataset renderers (Sheet, Cards, Timeline, Calendar, Map) plus Space, and Canvas. Changing the
view mode is a **lens change**, never a content change — the same node set, the same
selection, the same chrome (bottom action bar, row context menu, drag/drop, ⌘A) hold across
every mode. This is the Finder-like direct-manipulation principle already invoked elsewhere in
these specs (`kg-tables.md`, `sidebar-crud.md`): show ALL items, multi-select works everywhere,
one set of gestures.

Nine legacy GitHub milestones (UX - Library & Reading Surface, Library View, Library View —
Icons/List/Spatial/Canvas/Column Browser & Columns, Library - Engine, UX - Representations)
held roughly 101 open issues about exactly this surface with no spec behind any of them — this
spec is that surface's home, per the legacy-milestones ledger
(`agent-work/spec-pipeline/legacy-milestones-ledger.md`, row 1 of the burn-down).

Surfaces: `ViewDisplayMode` (`App/ViewDisplayMode.swift`), `LibraryView
+ContentBranches.swift` (`libraryRowsOrEmptyState`, the one dispatch switch),
`LibraryView+CanvasModes.swift`, `DatasetModeView`/`DatasetRenderer`
(`Views/Library/ViewModes/Dataset/DatasetModeStore.swift`), the per-mode view files under
`Views/Library/ViewModes/{Icon,List,Table,Columns}/`, `LibraryView+Insets.swift`
(`bottomInsetContent`), `LibraryView+KeyboardShortcuts.swift`
(`servicesRowKeyboardGrammar`/`usesSpatialProjection`).

## Behaviors (each → one pinning test)

### A. The mode set and its one dispatch point

- `library.modes.eleven-selectable` — **[OK]** `ViewDisplayMode.selectableCases` is exactly
  Icon, List, Table, Columns, Sheet (`.grid`), Cards, Timeline, Calendar, Map (`.geoMap`),
  Canvas, Space — eleven live, user-choosable modes; the twelfth case, `.workspace`, is a
  decode-only legacy alias that normalizes to `.canvas` and is never itself selectable.
  Pinned: `ViewDisplayModeTests.testSelectableCasesAreTheCoherentSet`,
  `ViewDisplayModeTests.testAllCasesNoLongerIncludeRetiredAliases`.
- `library.modes.one-dispatch-switch` — **[OK]** every mode is mounted from exactly ONE
  `switch displayMode` in `libraryRowsOrEmptyState`
  (`LibraryView+ContentBranches.swift:105-128`), and the empty-collection state is checked
  BEFORE that switch, so no mode branch can ever substitute for "there is nothing here yet."
  Verified each case mounts a real view, not a stub: `.icon`→`iconsView`, `.list`→`listView`,
  `.table`→`tableView`, `.columns`→`columnsView`, `.grid`/`.cards`/`.timeline`/`.calendar`/
  `.geoMap`→`datasetModeView(_:)` (one shared renderer host), `.canvas`/`.workspace`→
  `canvasModeView`, `.space`→`spaceModeView`. Pinned:
  `LibraryImportAffordancesTests.testEmptyLibraryShowsEmptyStateBeforeAnyViewMode` (asserts
  both branches exist and the empty check precedes the mode switch, by source position).
- `library.modes.dataset-renderers-share-one-host` — **[PARTIAL]** (→ #4865) the four dataset
  modes plus Map are not four separate view types but one `DatasetModeView` parameterized by
  `DatasetRenderer` (`.grid`/`.cards`/`.timeline`/`.calendar`/`.map`,
  `DatasetModeStore.swift:9-11`), scoped to the same folder query, the same live change
  stream (`documentStore.revision`), and the same open/open-source callbacks as every other
  mode. Grounded in reading `LibraryView+ContentBranches.swift:243-280` directly
  (`datasetModeView(_:)`'s single call site per case, same construction for all five); no
  dedicated render/dispatch test exists yet, so PARTIAL rather than OK.
- `library.modes.canvas-and-space-are-gated-renderer-pairs` — **[PARTIAL]** (→ #4865) Canvas
  and Space each mount ONE of two renderers behind a feature flag reading the SAME shared stores
  (`libraryProjection`, `canvasLayoutStore`, `canvasItemStore`) — Canvas:
  `CanvasSceneView` (RealityKit-ortho) when `isCanvasRealityKit2DEnabled`, else the SwiftUI
  `Spatial2DCanvas`; Space: `CanvasSpaceView` when `isCanvasRealityKit3DEnabled`, else
  `SpaceSceneView` — so switching the engine flag is transparent to the mode itself
  (`LibraryView+CanvasModes.swift:108-168`). Verified at HEAD: both renderer pairs are live,
  neither is dead code — this matches the still-open legacy-milestone issues asking to
  finish the RealityKit cutover (P2 in the former "Library View - Spatial" milestone), which
  is a completion question for PASS 2, not a defect in what exists today.

### B. One node, one set of chrome, across every mode

- `library.chrome.one-bottom-bar-every-mode` — **[OK]** the bottom action bar is mounted
  UNCONDITIONALLY in `bottomInsetContent` (`LibraryView+Insets.swift`) — no branch on
  `displayMode` reaches it, so every mode (including the dataset cluster, which the
  maintainer specifically re-tested) shows the identical bar, never a mode-specific
  substitute. Pinned:
  `LibraryPaneSurfaceGuardTests.oneBottomBarForEveryMode`,
  `LibraryPaneSurfaceGuardTests.showControlIsNotModeSwapped`.
- `library.chrome.one-row-menu-builder` — **[OK]** every browse mode (icon/list/table/
  columns) and both canvases build a row's context menu from the ONE shared builder — the
  canvases add at most one verb of their own and defer the rest — and every dataset renderer
  likewise builds from the ONE shared `DatasetRowMenu`, a deliberately narrower vocabulary
  than the browse menu, not a second copy of it. Pinned:
  `LibraryMenuParityTests` (`"every browse mode and both canvases build their row menu from
  the ONE shared builder"`, `"the canvases add exactly one verb of their own, and defer the
  rest"`, `"every dataset renderer builds its menu from the ONE shared DatasetRowMenu"`,
  `"the dataset verbs are spelled in the shared builder and nowhere else"`).
- `library.chrome.select-all-follows-the-visible-surface` — **[OK]** ⌘A selects everything
  VISIBLE in the focused surface, mode by mode, not the folder's full document set
  regardless of what's on screen — fixing two costumes of the same defect: a dataset mode's
  own date/prototype filter used to be bypassed (⌘A selected the unfiltered folder), and a
  bounded 3D board used to let ⌘A reach past its own render cap. Pinned:
  `SelectAllVisibleSurfaceTests` (four cases spanning dataset filtering and the 3D board's
  cap), `LibraryMenuParityTests.selectAllHasOneOwner` (`"⌘A has one owner — canvas
  defers to the menu command (M1 resolved)"`).
- `library.input.keyboard-grammar-is-explicit-per-mode` — **[OK]** the row-ordinal keyboard
  grammar (arrows, type-ahead, Return-to-open, Space-to-preview) is serviced by the ordered
  modes (icon/list/table/columns) and deliberately NOT by the spatial modes (canvas/space),
  where an arrow key used to silently move the list selection while the user looked at a
  spatial layout; every mode has an explicit, deterministic answer, and no mode claims both
  spatial and row-keyed at once. Delete and the focused-item menu actions are NOT scoped away
  in spatial modes — they act on the shared selection, which is meaningful everywhere.
  Pinned: `LibraryInputScopeTests` (`"spatial modes do not service the row keyboard
  grammar"`, `"ordered modes keep the row grammar"`, `"every display mode has an explicit
  answer"`, `"no mode is both spatial and row-keyed"`, `"delete and focused actions survive
  in spatial modes"`).
- `library.list.scroll-policy-is-deliberate` — **[OK]** list-mode selection changes do not
  scroll the viewport as a side effect of every mutation — removing a row from the
  selection, clearing it, or a same-primary shift-extend all leave the viewport where it
  was; only a selection written from elsewhere (e.g. a restored launch selection, or a
  cross-surface jump) scrolls the new selection into view. Pinned:
  `ListSelectionScrollPolicyTests` (seven cases: removal, clear, click, shift-extend,
  external write, launch restore, and `"list mode consults the policy instead of scrolling
  unconditionally"`).

### C. Search scoping across modes

- `library.search.spatial-modes-share-one-projection` — **[OK]** all three spatial-adjacent
  modes (the two canvases and the dataset cluster) build their filtered view from ONE
  projection of the already-filtered document set under an active search — not three
  independent filters that could drift from each other or from what the browse modes show
  for the same query. Pinned: `ModeScopeFollowsSearchTests` (`"the spatial projection is
  built from the FILTERED documents"`, `"all three spatial modes go through that one
  projection"`, `"the projection cannot drift from the filter that feeds it"`).
- `library.search.columns-show-hits-not-browse-root` — **[OK]** under an active search, the
  Columns mode's first column shows the search hits, not the ordinary browse root; drilling
  into a hit resumes ordinary browsing from there. The dataset modes keep their own,
  separate hit-id seam rather than sharing the Columns one. Pinned: `ModeScopeFollowsSearchTests`
  (`"column 0 shows the hits while a search is up, not the browse root"`, `"deeper columns
  still browse — drilling into a hit is browsing again"`, `"the dataset modes keep their own
  hit-id seam"`).

### D. Per-pane override and persistence

- `library.modes.per-pane-override` — **[PARTIAL]** (→ #4865) a workspace can request a specific
  display mode for its OWN library pane (`PaneConfig.libraryLayout` →
  `ViewDisplayMode(paneLibraryLayout:)`, `App/ViewDisplayMode.swift:165-196`), read through
  the `paneLibraryLayout` environment key, and `LibraryView.displayMode` prefers it over the
  window's global mode unless the user has set an explicit per-pane override
  (`paneDisplayModeOverride` wins over both). Grounded in reading
  `App/ViewDisplayMode.swift` and `LibraryView.swift:35-51` directly; no test exercises the
  three-way precedence (`paneDisplayModeOverride` > `paneLibraryLayout` > `defaultDisplayMode`)
  end to end, so this is PARTIAL rather than OK.
- `library.modes.legacy-raw-values-reset-not-migrate` — **[OK]** an old persisted mode string
  ("Map"/"Spatial"/"RealityKit" from before the Canvas/Space split) decodes to `nil` (falling
  back to the default mode), not silently folded onto `.canvas` — a deliberate clean-start
  decision recorded because the library data wasn't yet in production use when the
  vocabulary settled. Pinned: `ViewDisplayModeTests.testLegacyRawValuesNoLongerDecode`,
  `ViewDisplayModeTests.testCanonicalRawValuesDecode`.

## Cross-references — rulings honored, not restated here

- **The Library pane is always the navigator** — `modes-to-panes.md`'s own ruling; this spec
  is entirely downstream of it (a view mode is how the navigator draws itself, never a
  reason for the navigator to stop being the navigator).
- **The knowledge graph's timeline and map are ordinary Library view modes**, and the legacy
  KG browser/graph mode retired rather than living beside them — `modes-to-panes.md`'s
  `m2p.kg-graph-retires-as-library-takeover`. This spec's `.timeline`/`.geoMap` behaviors
  above are the SAME modes that ruling already names; not duplicated as a separate claim.
  The force-directed graph as a Reader rendition of one focused entity is that ruling's own
  future-work note, not something this spec re-opens.
- **Canvas and Space fold into the Library as view modes**, not a separate top-level surface
  — already true at HEAD (section A above); the remaining legacy-milestone issues about them
  (RealityKit cutover completion, nested containers, agent/MCP access) are PASS 2 fold
  candidates, not open design questions about whether they belong here.
- **Finder-like direct-manipulation principle** (show all items, multi-select everywhere, one
  gesture grammar) — invoked the same way `kg-tables.md` and `sidebar-crud.md` already invoke
  it, not re-derived as a new rule specific to view modes.
