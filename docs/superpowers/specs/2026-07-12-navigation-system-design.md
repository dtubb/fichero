# Navigation System — Design (2026-07-12)

Status: **IMPLEMENTED (2026-07-12, 8/8 slices merged)** — Location model + engine
resolve endpoint (#3576), MCP reveal tool (#3578), Swift source-reveal rewire
(#3577), ActiveSurfaceState (#3579), pin⇄active reconciliation (#3580), menu-bar
Back/Forward (#3581), Open-in-tab/window on panes (#3582), DocumentTabView
documented (#3583). Plus a regen toolchain fix (numeric→boolean exclusiveMinimum).
Original proposed direction (Daniel, 2026-07-12) preserved below. Scope: cross-cutting
navigation for the three separate surfaces — Preview (source), Reader
(derived knowledge), Inspector (edit) — plus window/tab management,
active-surface tracking, pinning, addressable locations, and back/forward
history. Does NOT merge Preview/Reader/Inspector; see "What this is NOT".

## 0. What already exists (audit, grounded in code)

This is not a green field. Four real mechanisms already do parts of this job
and must be extended, not duplicated.

### 0.1 Windows, tabs, seeding

- `fichero/fichero/FicheroApp.swift` declares one primary `WindowGroup("Fichero", id: "main")`
  plus a value-seeded sibling `WindowGroup("Fichero", for: WindowSeed.self)`, and five detached
  detail scenes: `artifact-detail`, `citation-detail`, `annotation-detail`,
  `note-detail`, `document-detail` (each `.defaultSize` ~480×620, read-only,
  follow-by-default).
- `fichero/fichero/App/WindowSeed.swift` — a `Codable` snapshot (`libraryId`,
  `libraryPath`, `selectedItemId`, `viewModeType`, `viewModeItemId`) that rides
  `openWindow(value:)`. This is the payload behind **Duplicate Window** (#2262).
- `fichero/fichero/Views/Shell/OpenAffordances.swift` — `WindowOpener.open(libraryId:documentId:asTab:using:)`
  is the ONE place "open in new window" vs "open in new tab" is decided. `asTab: true`
  opens via `openWindow(id: "main")` then merges the new `NSWindow` into the key
  window's native tab group with `hostWindow.addTabbedWindow(newWindow, ordered: .above)`
  (macOS native tabs, not a custom tab bar). `OpenInMenuItems` (same file) is the shared
  Finder-style "Open / Open in New Tab / Open in New Window" context-menu row (#1685),
  already reused across library rows, sidebar rows, and ontology rows.
- `fichero/fichero/App/LibraryWindow.swift` — per-window `@SceneStorage("libraryWindow.libraryId")`
  plus a `WindowState` (`@State private var windowState`), restored on `initializeWindow()`
  in priority order: WindowSeed → pending-window queue → persisted id → `currentLibraryId` →
  first open library → welcome screen. This is the per-window persistence anchor (#2273).
- `fichero/fichero/Views/Shell/ContentView/ContentView.swift` / `ContentView+State.swift` / `ContentView+Persistence.swift`
  own ~15 `@SceneStorage` keys per window: `selectedSidebarItem`, `columnVisibilityRaw`,
  `browserSelectionData`, `viewModeType`, `viewModeItemId`, plus reader-specific keys like
  `reader.topTab`, `reader.page.layout`, `reader.pageLayout`, `reader.notes.mode` (all in
  `ContentView+ViewBuilders.swift` / `PDFPageWithToolbar.swift`). Each window/tab genuinely
  has independent state today.
- `fichero/fichero/Views/Shell/DocumentTabView.swift` — **CORRECTION (#3583): this view is
  LIVE, not dead.** `LibraryWorkspaceRoot` mounts one per window; its load-bearing job is to
  gate on `appState.isBackendRunning` (showing `BackendConnectionView` until the engine is up)
  and forward the per-library `@Environment` services into `ContentView()`. Do NOT delete it.
  Only its internal `document.viewMode` **switch** is the legacy pre-`WindowGroup` abstraction
  (placeholder Workflow/Chat/Search cases) — that switch is deprecated; do not extend it. The
  earlier "largely dead weight" characterization was wrong.

### 0.2 The pin button — FOUND, and it already IS a per-surface-pane pin

Grep for `isPinned`/`pin` across `fichero/fichero/Views` turns up the SAME
pattern repeated independently in six places:

| File | Pinned unit |
|---|---|
| `fichero/fichero/Views/Shell/ContentView/ContentView+ViewBuilders.swift:38` (`ReadingPaneView`) | Reader pane: pins `Document` + page number + page count |
| `fichero/fichero/Views/Preview/PDFViewer/PDFPageWithToolbar.swift:56` | Preview/PDF pane: pins `documentId` + `localPageIndex` |
| `fichero/fichero/Views/Inspector/FocusedDocument.swift:41` (`DocumentDetailWindow`) | Detached document-detail scene |
| `fichero/fichero/Views/Inspector/Citations/CitationsInspectorPane.swift:123` | Citations inspector tab |
| `fichero/fichero/Views/Inspector/Annotations/AnnotationsInspectorPane.swift:204` | Annotations inspector tab |
| `fichero/fichero/Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:326` | Artifacts inspector tab |
| `fichero/fichero/Views/Inspector/Notes/NotesInspectorPane.swift:146` | Notes inspector pane |

Every instance follows the identical shape: `@State private var isPinned = false`
plus a locally-cached "pinned snapshot" (`pinnedDocument`, `pinnedDocumentId`,
`pinnedArtifact`, …), and a computed `effective*`/`shown*` property that reads
the pinned snapshot when `isPinned` else the live/focused value. The toggle
button is `Image(systemName: isPinned ? "pin.fill" : "pin")` with help text
"Pinned — won't follow selection" / "Follow the current selection".

**What it does today:** freezes ONE pane instance to whatever document/page/
item was active at pin time, so navigating the library elsewhere does not
drag that pane along. It is per-**View-instance** state (plain `@State`, not
`@SceneStorage`, not shared) — comment in `ReadingPaneView` is explicit: *"gives
each SplittablePane instance its own independent @State, so left and right
split panes can be pinned/unpinned independently."*

**What is missing today, and what requirement 3 (Daniel) needs:** there is no
single, observable "active surface" concept, and no visual indication (beyond
the pin icon itself) of *which* pane is currently the one that will update on
the next click. Pin is real and correct — it is the *lock* half of the
active/pin model. The *active* half does not exist as a first-class concept;
see §2.

### 0.3 Source-navigation / reveal-in-Preview — the closest thing to a Location model, and it is UI-only

- `fichero/fichero/Views/Inspector/Document/Knowledge/KnowledgeGraphSupport.swift:85-129` —
  `SourceDestination` (`.preview` / `.reader` / `.both`), `ClaimSourceNavigationRequest`
  (`documentId`, `claimId?`, `claimText?`, `pageLabel?`, `pageIndex?`, `charStart?`,
  `charEnd?`, `bbox: [Double]?` normalized `[x, y, w, h]` top-left, `destination`), and
  `ClaimSourceNavigationState` (an `@Observable` request bus: `requestID` + `currentRequest`).
  This is the **#2105/#3437 source-navigation contract**, locked by
  `fichero/fichero-tests/SourceNavigationContractTests.swift`.
- It is explicitly **per-window** (NOT `.shared`): `ContentView` owns one instance
  (`fichero/fichero/Views/Shell/ContentView/ContentView.swift:105`, `@State var claimSourceNavigationState = ClaimSourceNavigationState()`)
  and injects it via `@Environment`. `fichero/fichero-tests/InspectorNavigationScopingTests.swift`
  locks this: "a reveal in window A must not navigate window B."
- Consumption path: `ContentView+State.swift:handleOpenClaimSource()` reads
  `claimSourceNavigationState.currentRequest`, switches `sidebarMode` to `.library`,
  resolves the page's parent document, then posts `NotificationCenter` event
  `.ficheroNavigateToPage` (defined in the same Shared.swift file) with a userInfo
  dict (`documentId`, `claimId?`, `pageLabel?`, `charStart?`, `charEnd?`, `bbox?`).
  `PDFPageView`/`PDFPageWithToolbar` consume that notification to scroll/highlight.
- `KGFocusState` (`fichero/fichero/Models/KGFocusState.swift`) is the sibling
  mechanism for entity/claim clicks: `focusEntity(entityId:sourceDocumentId:sourcePageLabel:)`
  and `requestGraphReveal(entityId:)` (bumps `graphRevealRequestToken`, watched
  by `ContentView` to switch into Knowledge Graph mode).
- **Gap (this is the crux of requirement 4):** this whole mechanism is Swift-only.
  `fichero-engine/src/fichero/mcp_document_tools.py` exposes `fichero_get_document`
  with only a `document_id` param — no page, no bbox, no "reveal"/"navigate" tool at
  all. There is no engine endpoint, no OpenAPI schema, and no audited action
  (`fichero-engine/src/fichero/actions/registry.py`, EPIC #1848) for "resolve/reveal
  a location." An in-app Agent (model-as-user) or an external MCP client today has
  **no way** to point at "page 12, this bbox, in the Preview" — only a human clicking
  a citation can do that, through a NotificationCenter round-trip that never leaves
  the Swift process.

### 0.4 Navigation history — ALREADY BUILT, twice, at two different scopes

- `fichero/fichero/Models/AppNavigationHistory.swift` — a browser-style back/forward
  stack (`Entry { viewType, viewItemId, selectedSidebarItemId, browserSelection,
  detailDocumentId }`, `maxDepth = 80`, `push`/`goBack`/`goForward`/`canGoBack`/
  `canGoForward`). Owned per-window: `ContentView` holds one instance
  (referenced as `navigationHistory` throughout `ContentView+NavigationHistory.swift`).
- `fichero/fichero/Views/Shell/ContentView/ContentView+NavigationHistory.swift` — `recordNavigationEntry()`
  (called from `handleOnAppear`, `handleViewModeChange`, `handleDetailDocumentChange`),
  `navigateBack()`/`navigateForward()`, and `applyNavigationEntry(_:)` which sets a guard
  flag `isRestoringNavigationHistory` (checked everywhere a handler could otherwise
  re-record the very entry being restored — e.g. `handleSidebarSelectionChange`,
  `handleViewModeChange`).
- `fichero/fichero/Views/Shell/ContentView/ContentView.swift:726-747` — Back/Forward are ALREADY real
  toolbar buttons (`ToolbarItem(id: "fichero.nav.back"/"fichero.nav.forward", placement: .navigation)`),
  with keyboard shortcuts **⌘'** (back) and **⌘⇧'** (forward), `.disabled` bound to
  `canGoBack`/`canGoForward`.
- **Gap:** there is no Window/History menu-bar `CommandGroup` — only the toolbar
  buttons + their keyboard shortcuts exist; `FicheroApp.swift`'s `.commands` block has
  no Back/Forward menu items. There is also an odd second wiring: `ContentView.swift:463-466`
  publishes `\.navigationUndoAction` as a **fallback for ⌘Z** — `FocusedCommandButtons.swift:377-419`'s
  Undo button calls `navigationUndoAction.run()` (= `navigateBack`) when there is no
  audited action to undo. This conflates "go back" with "undo" and should be kept
  (cheap safety net) but NOT treated as the real Back menu command.
- A second, narrower history manager already exists for a different scope:
  `fichero/fichero/Models/NavigationHistoryManager.swift` — a smaller `Entry` enum
  (`entityList` / `entityProfile` / `claimJump` / `pdfPage`) owned per `OntologyBrowser`
  instance. Same shape (stack + cursor + `maxDepth = 50`), independently implemented.
  This is a second scope (KG browser back/forward within one window) that should NOT be
  merged into `AppNavigationHistory` (different entry semantics) but should be named
  consistently as "the same back/forward pattern, applied per navigable surface."

### 0.5 Selection → surfaces coupling

- `fichero/fichero/Views/Shell/ContentView/ContentView+State.swift:activeLocationDocument` — already the
  closest thing to an "active surface" resolver: switches on `focusedPane` (`.preview`/
  `.reading` → `pageFocusDocument ?? detailDocument ?? inspectorDocument`; else →
  `inspectorDocument`). `PaneFocus` (`ContentView.swift:22`) is `{ sidebar, content,
  preview, reading, inspector }` — Tab-cycling focus, not literal "last clicked."
- `handleBrowserSelectionChange(_:)` and `handleSidebarSelectionChange(_:)` (both in
  `ContentView+State.swift`) are the two funnels that turn a sidebar/grid click into
  `detailDocument`/`pageFocusDocument` writes — these are what Preview/Reader observe.
  `BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(...)` gates whether a
  grid click actually promotes to the detail pane (layout-mode dependent).
- Both `PDFPageWithToolbar` (Preview) and `ReadingPaneView` (Reader) already ignore
  these live updates locally when their own `isPinned == true` — i.e. the *pin* half
  of active/pinned already works per-pane; only the shared *active* bookkeeping and
  its indicator are missing.

### 0.6 The reversible node model / audited action layer

- `fichero-engine/src/fichero/actions/registry.py` — the single audited write path
  (EPIC #1848 keystone #2013): `ActionContext`, `ActionResult`, `ChangeSpec`. Every
  mutation goes through `invoke()`: validate → `execute()` → mandatory audit row →
  best-effort `emit_change`. A pure-read "resolve/reveal a location" is NOT a mutation
  and does not need `ChangeSpec`/audit, but should reuse the same "one typed FastAPI
  route → generated OpenAPI client → MCP tool" delivery shape so the in-app Agent gets
  it for free.
- Documents already carry stable `id`s; derived artifacts already carry `derived_from` +
  `bbox` (`fichero/fichero/Models/BoundingBoxGeometry.swift`, `PDFRegionGeometry.swift`).
  A Location anchor reuses these ids verbatim — no new identity scheme.

---

## 1. Location / anchor model (the ONE path)

### 1.1 The type

Promote `ClaimSourceNavigationRequest` (Swift-only today) to a serializable,
engine-known **Location** that both UI code and MCP/CLI tool-calls resolve
through:

```
Location {
  documentId: String        // required — the reversible node model's stable id
  page: Int?                // 0-based page index (matches ClaimSourceNavigationRequest.pageIndex)
  bbox: [Double]?            // normalized [x, y, w, h], top-left origin — same convention
                              // as crop_pdf_page / crop_image, so a Location can drive
                              // BOTH the crop endpoint and the highlight overlay
  charRange: (start: Int, end: Int)?   // legacy char-offset anchor, kept additive
  claimId: String?           // optional semantic anchor (which claim this is "about")
  entityId: String?          // optional semantic anchor (mirrors KGFocusState fields)
  surface: Surface           // .preview | .reader | .inspector | .both  (widened from
                              // SourceDestination, which only had preview/reader/both)
}
```

This is `ClaimSourceNavigationRequest` plus: (a) an explicit `surface` that can
also target `.inspector`, and (b) an `entityId` field so `KGFocusState`'s
parallel entity-reveal path collapses into the same shape.

### 1.2 One resolution path, two callers

- **Engine side (new):** one FastAPI route, e.g. `POST /api/locations/resolve`
  (or fold into `documents.py`), taking a `Location`, validating `documentId`
  exists and `page`/`bbox` are in range, returning the resolved anchor (parent
  document if `documentId` was a page-child, resolved page number). This becomes
  the ONE place page-child → parent resolution happens.
- **Generated OpenAPI client:** regenerate a `LocationsService` (mirrors
  `DocumentServiceGenerated.swift`).
- **UI caller:** `handleOpenClaimSource()` rewritten to call
  `locationsService.resolve(location)` then post the SAME `.ficheroNavigateToPage`
  notification (no regression to the working reveal/highlight path).
- **MCP/Agent caller:** new MCP tool `fichero_reveal_location` in
  `mcp_document_tools.py`, same `Location` schema, same resolve endpoint. Because
  the Agent is a model-as-user via audited MCP tools, the same typed action becomes
  an App Intent for free (#1848 "one capability = one typed action"). "Save a
  location" is just persisting a `Location` value (already `Codable`/JSON-schema'd).
- Client-side reveal fan-out (`.ficheroNavigateToPage` → `PDFPageView` bbox highlight,
  `KGFocusState.focusEntity`) is UNCHANGED — additive plumbing in front of the working
  reveal mechanism.

### 1.3 Both existing reveal paths route through it

- Claim/citation source-reveal: construct a `Location`, call resolve, post the
  existing notification.
- Entity-name click (`KGFocusState.focusEntity`): construct a `Location` with
  `entityId` + `surface: .reader` (or `.both` for "Show in Graph"), same resolve.
  `KGFocusState` stays (the right per-window focus bus); only the reveal *trigger*
  goes through shared resolve first.

---

## 2. Active-surface + pinning state model

### 2.1 What "active" means, scoped per window

Add one new per-window `@Observable`, `ActiveSurfaceState` (beside
`ClaimSourceNavigationState` in `ContentView`, per-window NOT `.shared`, matching
the #3437 scoping invariant locked by `InspectorNavigationScopingTests`):

```
ActiveSurfaceState { activeSurfaceId: SurfaceID? }
SurfaceID: Hashable  // one per SplittablePane instance — a stable per-pane UUID
                     // created at pane-mount, so left/right splits qualify independently
```

Rule: every sidebar/grid click that updates `detailDocument`/`pageFocusDocument`
(`handleBrowserSelectionChange`, `handleSidebarSelectionChange`) ALSO writes
`activeSurfaceState.activeSurfaceId` to whichever pane last received a direct
click (inside a Preview/Reader pane), mirroring how `focusedPane` tracks Tab
focus. A pane with `isPinned == true` is skipped when picking a NEW active target.

### 2.2 Visual indication

Active pane gets a subtle accent hairline on its `MiniToolbar` strip (where the
pin button already lives): `.overlay(alignment: .top) { Rectangle().fill(isActive ? .accentColor : .clear).frame(height: 2) }` — additive, flips one pane's overlay,
no relayout (respects no-wholesale-list-rerender).

### 2.3 Pin reconciliation — extend, don't duplicate

Keep the existing per-pane `isPinned` in all six files. Only change: when
`isPinned` flips true, clear `activeSurfaceId` if it pointed here; when a pane is
the ONLY unpinned Preview/Reader, it silently becomes active on next click (no
dead state). No new pin UI.

---

## 3. Window / tab / split semantics (the browser-tab metaphor)

- **New window** = `WindowOpener.open(asTab: false)` → `openWindow(id: "main")`
  with automatic tabbing forced off (existing `openWindowDisallowingAutomaticTabs`).
- **New tab** = `WindowOpener.open(asTab: true)` → `openWindow(id: "main")` +
  `addTabbedWindow` — genuine macOS-native tabs (OS tab bar), getting Move-to-New-Window,
  tab overview (⇧⌘\), Merge All Windows for free.
- **"Open a source in a new window OR tab"** is already `OpenInMenuItems` (#1685) —
  extend its call sites to Preview/Reader pane title bars + citation/entity reveal
  context menus, wiring to `WindowOpener.open(documentId:asTab:)` (the `documentId:`
  param already exists via `LibraryManager.pendingOpenDocumentId`).
- **"Clicking an item shows Preview AND Reader"** is already the behavior
  (`handleBrowserSelectionChange` writes `detailDocument`, both panes observe it) —
  only §2's active bookkeeping is additive.
- **Per-window/per-tab state**: unchanged — existing `@SceneStorage` keys already give
  every window+native-tab its own state (proven by Duplicate Window / WindowSeed).
- **`ActiveSurfaceState`/pin are session-only** (`@State`, not `@SceneStorage`) — a
  relaunch remembers open documents (already handled), not which pane was active.

---

## 4. Navigation history + back/forward

Two working stacks already exist (§0.4) — no new data structure. Only surfacing is
missing:

- **Add a menu-bar `CommandGroup`** in `FicheroApp.swift`'s `.commands` — Back/Forward
  items bound to their OWN `FocusedLibraryAction`s (`navigateBackAction`/`navigateForwardAction`),
  NOT reusing `\.navigationUndoAction` (that stays the ⌘Z fallback only). Keyboard stays
  ⌘'/⌘⇧' (matches existing toolbar buttons).
- **Scope stays per-window** (`AppNavigationHistory` per `ContentView` scene) — correct:
  a browser's Back is per-tab, and Fichero windows+native-tabs are the tab equivalent.
- **KG browser back/forward** (`NavigationHistoryManager`) stays separate (nested,
  incompatible entry shapes) — document as "same pattern, two scopes."

---

## 5. Reveal / bring-to-front flow

**"Click a citation → reveal in Preview":** (1) card builds a `Location`
(documentId+page+bbox+`surface: .preview`); (2) `claimSourceNavigationState.request(location)`;
(3) `handleOpenClaimSource()` calls `locationsService.resolve` instead of inline
resolution; (4) resolved anchor drives sidebar/select + posts `.ficheroNavigateToPage`
(existing consumers unchanged); (5) §2 picks the (unpinned) Preview pane.

**"Click an entity name":** identical, `Location` with `entityId` + `surface: .reader`
(or `.both`), `KGFocusState` fires as today.

**MCP/Agent path** (new): `fichero_reveal_location` → resolve endpoint → returns the
resolved anchor as DATA the Agent can act on. Actually pushing that into a live
window's Preview (cross-process agent-drives-UI) is OUT of scope (see §8).

---

## 6. Cross-platform (iPad / iPhone — no menu bar)

- **iPad**: no menu bar but multi-window (Stage Manager). `WindowOpener`'s `#else`
  branch already stubs "no native tabs; open a new window scene." Back/Forward = toolbar
  pair (the existing `leadingToolbarContent` buttons are NOT macOS-gated — already work
  on iPad) + two-finger swipe-back, same `navigateBack()/Forward()`.
- **iPhone**: `Self.shouldUseCompactNavigationFlow` already collapses to a
  `NavigationStack` push/pop (`pushedLeafDocument` + `.navigationDestination(item:)`);
  Back is the native swipe/back button. `AppNavigationHistory`'s explicit buttons matter
  only in regular-width (iPad landscape / Mac).
- **Pinning**: unaffected (`@State` on the pane; panes exist on iPad too).

---

## 7. Milestone / issue reconciliation

Caveat: `#3407`/`#3394`/`#3413`/`#3393` are live GitHub board issues (window-lifecycle
+ library-drift) not found in tracked code — reconcile against the board; they touch
the same window/tab plumbing audited in §0.1 and should fold into slices 1–8, not be
worked in parallel. `#2105` (source-nav contract) is confirmed in code and is where the
Location model folds directly.

Proposed sequencing (small, independently mergeable slices):

1. **Location model + resolve endpoint** (engine): `Location` schema +
   `POST /api/locations/resolve` in `documents.py` (or `locations.py`), regen OpenAPI.
   No UI change. Additive to #2105.
2. **Swift `Location` type + `handleOpenClaimSource` rewire**: call `locationsService`;
   `ClaimSourceNavigationRequest` becomes a thin wrapper so `SourceNavigationContractTests`
   keeps passing.
3. **MCP tool** `fichero_reveal_location` in `mcp_document_tools.py`. Independently mergeable.
4. **`ActiveSurfaceState`**: new per-window `@Observable` + click wiring + ring overlay.
5. **Pin reconciliation**: the two §2.3 edits across the six pin files.
6. **Back/Forward menu-bar commands**: `CommandGroup` in `FicheroApp.swift`, reusing
   existing `navigateBack()/Forward()`.
7. **`OpenInMenuItems` extension** to Preview/Reader panes + reveal menus.
8. **`DocumentTabView` retirement** (low-priority cleanup): confirm dead + delete, or
   document why kept.

---

## 8. What this is NOT

- **NOT merging Preview, Reader, and Inspector** — three separate surfaces; the Location
  model is a shared *addressing* mechanism, not a shared *view*.
- **NOT a rewrite of window/tab plumbing** — `WindowGroup`/`WindowSeed`/`WindowOpener`/
  per-window `@SceneStorage` are reused as-is (proven by Duplicate Window #2262).
- **NOT a new pin button** — the six-file `isPinned` pattern stays; only its interaction
  with `ActiveSurfaceState` is added.
- **NOT wiring the in-app Agent to drive a live window's UI** — this defines the
  addressable Location an Agent can RESOLVE; cross-process agent-drives-UI is later work.
- **NOT replacing `ClaimSourceNavigationState`/`KGFocusState`/`NavigationHistoryManager`**
  — all stay as the correct per-window/per-surface buses; this adds a shared `Location`
  type + resolve step in front, plus one `ActiveSurfaceState` alongside.
