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
- `library.modes.persists-until-changed` — **[BROKEN]** (#4575) the view mode is ONE choice
  per window and must never change itself — ordinary folder navigation only RE-NORMALIZES the
  current mode for availability (falls back only when the mode genuinely can't render the new
  context), per the explicit 2026-08-09 ruling recorded at
  `ContentView+StateEvents.swift:34-41` ("it changes views depending on the folder open... we
  don't want that"), which itself superseded an earlier attempted fix for this same issue.
  **Still a live, verified defect at HEAD**, independent of that ruling: selecting a sidebar
  KG collection (Entities or Claims) unconditionally sets `viewDisplayMode = .list`
  (`ContentView+StateEvents.swift:27`) — regardless of what the user had chosen (Icon, Table,
  Canvas, anything) — with no way to opt out and no relationship to the per-folder-restore
  case the 2026-08-09 ruling fixed. A user who was in Icon view and clicks into the sidebar's
  Entities/Claims section, then back to an ordinary folder, finds their mode already changed
  out from under them — reported as "reverted to column" (Table's older UI name), matching
  the symptom exactly. No test pins this; flagged first in this pass's report because it may
  be reproducible right now.

### E. Icon mode (legacy milestone "Library View — Icons")

- `library.icon.arrow-nav-latency` — **[BROKEN]** (#4590, #4584) arrow-key traversal and Quick
  Look navigation in Icon view lag noticeably versus Finder; the selection change should be
  synchronous and only the image LOAD should be async — the same synchronous-selection/
  async-load split the Preview pane needs for its own click-to-load latency (see section K:
  that half is a Preview-surface question, not this spec's). Not verified as built.
- `library.icon.thumbnail-preload-bounded` — **[GAP]** (#4589) a folder's thumbnails should
  prefetch (bounded, windowed) on open so scrolling doesn't lazy-load-jump. Not verified as
  built.
- `library.icon.selection-chrome-hugs-the-image` — **[GAP]** (#4588) the selection border
  should wrap the artwork itself, Finder-tight, not a padded background tile. Not verified as
  built.
- `library.icon.shift-click-extends-to-item` — **[BROKEN]** (#4582) shift-click in Icon view
  should extend the selection to the clicked item by visual position (Finder's icon-view
  semantics), not select the entire contiguous row the way List view's shift-click correctly
  does — Icon view is currently borrowing List's row-range semantics for a grid layout where
  they don't apply. Not verified as built.
- `library.icon.context-menu-builds-off-main-thread` — **[BROKEN]** (#4585) right-clicking a
  5-6 item selection beachballs — context-menu construction is doing per-item/per-selection
  synchronous work on the main thread; the menu must build from in-hand state with any
  counts/scope resolution async. This is a performance defect IN the one shared row-menu
  builder `library.chrome.one-row-menu-builder` already names, not a second menu system. Not
  verified as built.
- `library.chrome.thumbnail-fallback-shows-type-icon` — **[GAP]** (#4204) when a document has
  no thumbnail, the fallback should be that document's OWN type glyph (a `.docx` shows a Word
  icon, an unrendered image shows an image icon) rather than one generic photo placeholder —
  a fact about the document lost, not only a style choice. Applies to icon tiles, list rows,
  and table rows alike (filed under the Icons milestone, but cross-mode by the issue's own
  scope). Not verified as built.

Left in its legacy milestone, not folded here: **#4581** ("Clear Data" bulk-delete of
content/attributes/entities for a multi-selection) is an audited bulk-CRUD action, not a
view-mode display question — no existing spec (this one, `sidebar-crud.md`, `kg-tables.md`)
squarely owns "bulk-clear a document's derived content while keeping the document," so it
stays on its legacy milestone for maintainer triage rather than forced into any of them.

### F. List mode (legacy milestone "Library View — List")

- `library.list.shift-click-anchor-established-first` — **[BROKEN]** (#4592) the FIRST
  shift-click after a fresh selection sometimes selects only the clicked row instead of the
  range, because the range anchor isn't established from the current single-focused row
  before the first extend — a classic missing-anchor bug; the SECOND shift-click works. Not
  verified as built.
- `library.list.row-content-is-configurable` — **[GAP]** (#4398) a list row's badges
  (Completed/Processing) carry no information the spinner doesn't already show and should be
  silent in the ordinary case; only an error is worth a row affordance, and it must be
  clickable to say what failed. The real fix underneath is letting the user choose which
  columns/properties a row shows (name, kind, size, dates, status, entity/page counts), from
  the SAME vocabulary the inspector uses — not a second naming of the same fields. Not
  verified as built.

Verify-close candidate, left OPEN for the maintainer, not closed here: **#4376** ("⌘A must
Select All in the focused surface") — the LIBRARY half is verified built at HEAD:
`library.chrome.select-all-follows-the-visible-surface` (above) is exactly this behavior,
pinned by `SelectAllVisibleSurfaceTests` and `LibraryMenuParityTests.selectAllHasOneOwner`.
The issue's SECOND half — ⌘A selecting all text in the Reader — is a different surface this
spec doesn't cover; not verified either way, so the issue as a whole should stay open until
the Reader half is checked, even though the Library half this spec owns is done.

Left in its legacy milestone, not folded here: **#4311** (cross-library drag-and-drop copy,
and drag-out-to-Finder) has no clean home among this spec, `panes-workspaces.md`,
`sidebar-crud.md`, or `research.md` — it's a Library drag-and-drop capability, not a view-mode
question, a pane/window question, a sidebar-tree CRUD question, or an agent-tool question.
Left for maintainer triage.

- `library.modes.quality-pass-tracked-here` — **[GAP]** (#4160, #1971, #114 — three umbrella
  audit/quality-pass EPICs over the years, none superseding the others, filed from "every view
  mode as good as the sidebar" through "audit icon/list/table use standard SwiftUI controls"
  to a bare "[QA] Library View Surface Audit") this spec's own growing behavior set (List/
  Icon/Table/Columns/Canvas/Space quality lines above and below) is now where these EPICs'
  per-mode asks are tracked; none is itself a separate behavior to build.
- `library.icon.zoom-scale` — **[PARTIAL]** (#1930) per-view zoom via +/- and pinch-to-zoom,
  with larger thumbnails available. Verified at HEAD: `@AppStorage("library.iconViewScale")`
  (`LibraryView.swift:336`) persists the scale; a live pinch gesture drives `liveIconScale`
  with a clamp so a single thumbnail never exceeds the visible area
  (`LibraryView+IconMode.swift:19-34`) — built. No test found exercising the pinch gesture or
  the persisted scale, so PARTIAL rather than OK. The "grid sidebar view" half of the issue
  (a Finder-style icon-grid sidebar, distinct from the Library pane's own icon mode) was not
  found and may be a separate, still-open ask.
- `library.list.selection-and-save-reliability` — **[GAP]** (#1961, an older, broader
  complaint than the specific anchor bug `library.list.shift-click-anchor-established-first`
  above pins) list click/selection/save described as "overloaded" and unreliable. Not
  verified as built or fixed; kept as its own line rather than folded into the anchor bug
  since the issue names selection AND save, not only range-selection.
- `library.chrome.excluded-from-processing-treatment` — **[GAP]** (#1791) a document excluded
  from processing should read as such wherever it appears — a visual treatment in the
  library, and it should not surface in ordinary search or the knowledge graph. Not verified
  as built.
- `library.chrome.batch-operations-beyond-workflows` — **[GAP]** (#1695) selection-scoped
  batch operations beyond running a workflow — delete/archive/tag/exclude on a multi-selection
  — from the shared bottom action bar (`library.chrome.one-bottom-bar-every-mode` above). Not
  verified as built.

Verify-close candidate, left OPEN for the maintainer (evidence posted as a GitHub comment),
not closed here: **#1931** ("Column view (Miller columns, horizontal), DEVONthink/Mail
style") — an OLDER filing of the same ask `library.modes.eleven-selectable`/`library.modes
.one-dispatch-switch` above already confirm is built (`.columns`, `columnsView`), and the
same caveat as #3697 above applies: `library.columns.seeds-from-the-browsed-folder` (#4594)
may be why it still reads as broken to whoever tests it next.

### G. Columns mode (legacy milestone "Library View — Column Browser & Columns")

- `library.columns.seeds-from-the-browsed-folder` — **[BROKEN]** (#4594) Columns mode should
  show the CURRENTLY BROWSED folder's contents, the way Icon/List/Table all do — not always
  the library's top-level root with the browsed folder absent from the path entirely.
  Verified BROKEN at HEAD: `columnsRootDocuments`
  (`LibraryView+ColumnsSeeding.swift:24-28`) always returns `documentStore.collections` (the
  TOP-LEVEL root) for column 0, and `seedColumnsPathFromSelection()` only seeds a path from
  the current SELECTION's ancestry — if the user has merely BROWSED into a folder via the
  sidebar with nothing selected inside it, no path is seeded and column 0 shows the
  unrelated top-level root, matching the reported repro exactly (a folder with 153 pages
  showing fine in Icon/List, empty in Columns). Root cause is the seeding source (selection,
  not the browsed folder), not a query bug.
- `library.table.facet-columns-from-knowledge-objects` — **[GAP]** (#3700) a document's
  entity/annotation/note/bbox counts should be exposable as columns/facets in the table and
  column browser, reusing the knowledge objects already in the store. Not verified as built.
- `library.table.column-customization` — **[GAP]** (#3698) a column picker should choose
  which columns the table view shows (name, dates, type, entity count, size, etc.),
  persisted per view. Not verified as built.

Verify-close candidate, left OPEN for the maintainer, not closed here: **#3697** ("Column
Browser view mode (Finder-style Miller columns)") — the MODE ITSELF is verified built at
HEAD: `.columns` is a live `ViewDisplayMode.selectableCases` member, mounted via
`columnsView` in the one dispatch switch (`library.modes.eleven-selectable`,
`library.modes.one-dispatch-switch` above). What is NOT verified is whether it was fully
working when this old issue (2026-07-13) was filed, or whether `library.columns.seeds-from-
the-browsed-folder`'s bug (above) is the reason it still reads as broken today.

### H. Dataset modes — Sheet, Cards, Timeline, Calendar, Map (legacy milestone "UX - Representations")

- `library.dataset.timeline-controls-broken` — **[BROKEN]** (#4598) in Timeline mode, changing
  sort has no effect, "show full text" has no effect, and there is no multi- or discontiguous
  selection or editing. Also unconfirmed: whether dated entries surface regardless of
  provenance (date sidecars/manifest as well as workflow-extracted dates) rather than only
  the latter. Not verified as built.
- `library.dataset.sheet-rows-are-multiline-and-sortable` — **[GAP]** (#4595, #4596) Sheet
  mode's rows should show their full multi-line text (top-aligned), and clicking a column
  header should sort by that column, toggling ascending/descending — ordinary Mac table
  behavior neither piece has today. Whether SwiftUI's `Table` can host variable-height
  editable multi-line cells is an open implementation question the issue itself raises;
  worth a design escalation if not. Not verified as built.
- `library.dataset.calendar-interactions` — **[GAP]** (#4599) Calendar mode should support
  Space to Quick-Look a date, click-through to BOTH Reader and Preview (today only Preview
  follows a click), filter/search within the view, and zoomable granularity from day through
  century — an archive spanning decades needs the wide zooms. Not verified as built.

Verify-close candidate, left OPEN for the maintainer, not closed here: **#2667** ("EPIC:
collapse view modes to Canvas (2D) + Space (3D), one positioned-node model, shared xpos/ypos")
— its core frontend asks are verified DONE at HEAD: `ViewDisplayMode` has exactly Canvas and
Space as the two spatial modes today (no separate `.map`/`.spatial`/`.realitykit` — the
epic's own "current state" table describing three overlapping modes no longer matches the
code), and both already share `canvasLayoutStore`/`canvasItemStore` per
`library.modes.canvas-and-space-are-gated-renderer-pairs` above. The epic's backend
persistence-audit task and its deferred endpoint-renaming task were not independently
re-verified this pass.

Left in its legacy milestone, not folded here: **#2807** (iOS first-run parity, an onboarding
product decision) and **#1755** (georeferencing a scanned map image onto a real basemap/globe
— an authoring feature, not a mode that plots existing coordinates the way Map mode does) are
both waiting on a home this spec isn't: onboarding has no spec, and georeferencing is closer
to the not-yet-written `historical-text-normalization` spec than to a Library view mode.

### I. Canvas & Space (legacy milestones "Library View - Spatial", "Library View - Canvas")

- `library.canvas.trackpad-scroll-pans` — **[BROKEN]** (#4408) two-finger trackpad scroll
  should pan the canvas with no modifier — the platform convention every Mac trackpad app
  (Preview, Maps, Freeform, Figma, Photos) follows — while panning today requires holding
  Space. Verified at HEAD: `CanvasSceneView.swift`'s `panOrMarquee` gesture gates panning
  behind the Space key exactly as described; the issue's own read of the code (a plain drag
  must move items, not the camera, per an earlier, already-closed drag-vs-camera fix) is
  sound and does not extend to SCROLL, a
  different input that doesn't compete with drag. Pinch-to-zoom already follows platform
  convention; scroll does not — half a gesture vocabulary today.
- `library.canvas.input-and-selection-polish` — **[GAP]** (#4601, #4603) a consolidated input
  program: rubber-band select with edge autoscroll and the app's standard rubber-band style
  (today's reads as too dark and sometimes beachballs); a multi-select group gets ONE
  bounding box, constant screen-space width regardless of zoom; grab handles on
  single/multi-selection in both 2D and 3D; Space Quick-Looks the selection (today it beeps);
  camera pan via click-drag requires Command; shift-drag constrains movement to one axis.
  Several of these are new asks beyond what `library.canvas.trackpad-scroll-pans` covers.
  Not verified as built.
- `library.canvas.item-crud-affordances` — **[PARTIAL]** (#3085) the backend CRUD exists —
  `CanvasItemStore.createItem`/`.updateItem`/`.deleteItem` (`CanvasItemStore.swift:159-266`)
  — but the UI affordances the issue asks for (add note/quote/text/link from a toolbar menu,
  canvas context menu, or double-click-empty-space; inline text editing; resize via corner
  handle) were not found: `canvasContextMenu()` (`LibraryView+CanvasModes.swift:52-65`) offers
  only "Zoom to Card" and the shared document context menu, nothing that calls
  `createItem`/`updateItem`. Store exists, no caller.
- `library.canvas.universal-container-scope` — **[GAP]** (#3091, #1773 — the same ask, #1773
  the older filing, naming icon/column/map/spatial specifically for an entity-library
  selection whose list mode already shipped) Canvas and Space should be offered as view modes
  on ANY container — search results, an entity-library selection, a workspace — not only
  folders; today search gets `.map` only behind an advanced flag and entity selection is
  list-only. Extends `library.modes.canvas-and-space-are-gated-renderer-pairs` and
  `library.search.spatial-modes-share-one-projection` above, which currently cover only the
  folder-browsing case. Not verified as built.
- `library.canvas.nested-container-navigation` — **[GAP]** (#3092) entering a canvas item that
  is itself a container (a folder, a PDF, an image/page) should switch the canvas to THAT
  item's own scope — its pages, its own notes/annotations/entities as the placeables — using
  the same navigation spine Icon/List already use to drill in and out. Not verified as built.
- `library.canvas.zoom-lod-tiers` — **[GAP]** (#3105) smooth zoom into an image, resolving
  glyph → thumbnail → full-resolution texture identically in Canvas and Space, with hysteresis
  at tier boundaries and frustum/visible-rect culling so a zoomed view fetches only what's
  on screen. Not verified as built.
- `library.canvas.tinderbox-features-beyond-mvp` — **[GAP]** (#4192) the founding EPIC's
  vision beyond what's already built (2D/3D renderer pair sharing one store, per
  `library.modes.canvas-and-space-are-gated-renderer-pairs`): adornments (background regions
  that group notes spatially), typed links with labels and visual variation, aliases (the
  same note in several maps without duplication), and AI-initiated arrangement as a
  first-class, attributable, undoable action. None of these were found built. The epic's own
  open design questions (shared vs. per-scope z-position, adornments as a new type vs.
  reused folders, link-type vocabulary) remain genuinely open, not decided by this pass.
- `library.space.wiring-completeness` — **[PARTIAL]** (#3089) `.space` IS a live selectable
  mode today, offered wherever `.canvas` is (`ContentView+StateLayout.swift:84,89`) and
  mounted via `spaceModeView`. Not verified: a View-menu "Space" entry with a ⌘5 shortcut (no
  match found in `ViewMenuCommands.swift`), and the acceptance demo the issue names — two
  windows on the same folder, one in Canvas, one in Space, each updating live from the
  other's edits.

Verify-close candidates for the maintainer, cited but not re-litigated here: **#3087** ("cut
over `.canvas` to SceneKit, retire `Spatial2DCanvas`") and **#4005** ("wire-in or delete the
legacy canvas fallbacks") both name exactly the pending completion decision
`library.modes.canvas-and-space-are-gated-renderer-pairs` already documents — both renderer
pairs are live at HEAD, neither cutover is finished. Cite that behavior rather than add a
duplicate line for each issue.

### J. Redirected elsewhere (existing specs)

Four issues from these eight milestones were re-read against their OWN best-fitting spec
rather than forced into this one — see `panes-workspaces.md` (`panes.double-click-focuses-
current-window`, #3364; `panes.split.each-pane-its-own-document`, #2422), `research.md`
(`research.canvas-actions-are-agent-tools`, #3093), and `modes-to-panes.md`
(`m2p.grouped-nodes-drill-consistently-across-view-modes`, #3699).

### K. No spec exists yet — left on the legacy milestone, not moved

Four issues wait on a spec this ledger's burn-down proposed but nobody has written yet, per
the fold rule: do not invent a home, do not move the issue.

- **#4364** (Historical dates: adopt undate/EDTF) — waiting on `historical-text-normalization`.
  Left on milestone "Library - Engine" (#165).
- **#4236** (Search returns 0 results for text the Inspector is displaying) — waiting on the
  proposed `search` spec. Left on milestone "Library View" (#117).
- **#1755** (georeference a scanned map as a real-world overlay) — waiting on
  `historical-text-normalization`. Left on milestone "UX - Representations" (#183) (already
  noted in section H).
- **#4583** (Preview pane: first click delay before the full image loads) — RESOLVED since
  this was written: moved onto `preview-surface.md`'s milestone as
  `preview.image.shows-cache-before-full-load`. The SELECTION-latency half of the same
  symptom stays here as `library.icon.arrow-nav-latency` in section E above — cross-referenced
  from both sides, not duplicated.

### L. No existing spec fits either — maintainer triage, not a guess

- **#4581** (Clear Data bulk-delete) — see section E.
- **#4311** (cross-library drag-and-drop, drag-out-to-Finder) — see section F.
- **#2807** (iOS first-run parity, an onboarding product decision) — see section H.
- **#2418** (cross-platform RTF-editor parity investigation) — a Reader/editor-capability
  question, not a Library view-mode question; no spec (`reading-markup-annotations.md`,
  `library-view-modes.md`, or anything else read this pass) squarely owns "is the iOS text
  editor as capable as the Mac one." Left on milestone "Library View" (#117).

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
