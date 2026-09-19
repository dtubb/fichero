# Panes & Workspaces — Design Spec

> Milestone: panes-workspaces
> Manual: TBD — a "Workspaces" section for Part I (Getting Started): what a workspace is, the
> five built-ins and their ⌘⌥1–5 shortcuts, how to split/close/resize a pane, and how the
> pane head's left icon changes what a pane shows.

> Design-led (Testing Constitution). The Fichero creative director owns this intent;
> tests enforce it; code makes them pass. One line per behavior, each to be cited by its
> pinning test. **Status: DRAFT (most behaviors are [GAP]) — but the DESIGN DIRECTION is
> RATIFIED 2026-09-13 (see Design decisions). Grounded in a read-only code map + Findings
> F1–F7. Fix sequence: F5 reset [done] → F3 pin [done] → F6 plan==render [next] → then pane-list
> generalization (F7), legacy renderer retired, entities/claims unified.**
> Tags: **[OK]** today · **[BROKEN]** regression, code contradicts the line · **[GAP]**
> intended, never built.
>
> **The finding in one line:** the workspace is a half-finished migration to a pane-list
> model — the reliability fix is to *finish it* (one renderer, one vocabulary, a real pane
> list, per-instance pane state), not to patch symptoms. See F1–F7.
>
> **Changelog 2026-09-16 (dfa937946, CD live-testing pass).** The always-a-`PaneList` step landed:
> `activePaneList` now **SEEDS to Read**, so the F7 `PaneList` path is *always* the render path and the
> legacy visibility-Bool fallback no longer renders. This closes the two-libraries / close-both /
> split-both cluster at the root (they were the legacy path showing through a nil-defaulted `@State`).
> Also shipped: the built-in set is now **five** (Read · Browse · Transcribe · Transcribe·Tall ·
> Compare; ⌘⌥1–5 — Catalogue + Claims dropped, no separate Default Layout); the layout-recursion
> crash is fixed (`WorkspaceSplitStack` GeometryReader + clamp + single per-child frame); the
> Transcribe/Compare library strip is pinned to 72pt (`PaneConfig.paneExtent`); split-then-close-both
> is fixed (PaneHead close-ladder reorder); the kind-switcher is wired on the applied path
> (`PaneList.changingLeafKind` + `\.paneKindSwitcher`); `\.isSolePane` collapses a lone pane's head
> close; pane heads are consistent liquid-glass (`PaneFilterBar.showsSeparator` default off, ChatView
> Divider removed); and the loupe now requires Option to be the *sole* modifier (so ⌘⌥1 no longer
> summons it). Pinned by `BuiltInWorkspaceLayoutTests`, `MenuShortcutUniquenessTests`,
> `PaneInstanceIndependenceTests`. The spec Status stays DRAFT.
>
> **Changelog 2026-09-18 (#4685/#4686/#4687 completion + adversarial-review fixes).** The
> "one renderer, not yet one model" gap the 2026-09-17 residue note tracked is CLOSED: there is now
> exactly one pane-visibility model, one persistence funnel, and the dead widescreen-era code around
> both is deleted, not left dormant.
> - **`activePaneList` is the ONLY source of pane visibility.** The three legacy `@SceneStorage`
>   Bools (`showDocumentGrid`/`showDocumentCanvas`/`showReadingPane`) are DELETED from
>   `ContentView.swift`; `paneVisibility` (`PaneVisibility.swift`) is now a pure derivation of
>   `activePaneList.kinds` — there is no separate storage that could disagree with what's on
>   screen. Every site that used to read a Bool directly (toolbar lit-state, `cyclePaneFocus`,
>   `paneAwareDetailMinWidth`, `currentPaneVisibilityPlan`) now asks `paneVisibility`/
>   `activePaneList`. See `panes.visibility.derived-from-list` below.
> - **One funnel, `paneListDidChange()`, both syncs and persists.** Every writer of
>   `activePaneList` (`setPaneVisible`, `applyWorkspaceLayout`, a saved-workspace apply,
>   `splitFocusedLeaf`, pane-head close/kind-switch) ends by calling this ONE function
>   (`PaneVisibility.swift`), which remembers the applied composition in
>   `WorkspaceLayoutDefaults` (`rememberPaneList`) for the next launch. The seed
>   (`ContentView.activePaneList`'s default) restores it —
>   `WorkspaceLayoutDefaults.rememberedPaneList() ?? BuiltInWorkspaceLayout.read.panes` — falling
>   back to Read when nothing was ever remembered. See `workspaces.persist-applied-list` below.
> - **Saved workspaces carry the real composition.** `WindowLayoutSnapshot.paneList: PaneList?`
>   is the field that was missing (§"Existing machinery"'s "model split" debt, closed): capture =
>   `activePaneList`, apply = assign it. An old snapshot without the field decodes with
>   `paneList == nil` and applies as the Read default (logged, not crashed); a PRESENT but
>   malformed value ALSO degrades to `nil` rather than throwing out of decode and voiding the
>   whole saved-workspace catalog (the SF10 adversarial-review finding). See
>   `panes.workspace.save`/`panes.workspace.reopen` below.
> - **Built-in layouts have STABLE leaf ids.** `BuiltInWorkspaceLayout.panes` used to call the
>   plain `.leaf`/`.split` factories (`PaneList.swift`), which mint a fresh random `UUID()` on
>   EVERY access — so re-deriving the same built-in (navigating Read → Browse → Read, or a
>   relaunch re-seeding against it) silently lost a dragged divider's stored width and orphaned
>   `@SceneStorage` keys, because `WorkspaceSplitStack`/`PaneSpec` key that per-instance state off
>   a leaf's id (the SF6 finding). Fixed at the source with `PaneNode.stableLeaf`/`.stableSplit` +
>   `UUID(stableName:)` (deterministic, MD5-based) — every built-in composition now uses these,
>   named `"\(rawValue).<role>"`. Runtime mutations (`toggling`, `splittingLeaf`'s duplicate,
>   `settingVisible`'s appended leaf) are UNCHANGED — they still mint fresh random ids, or two
>   toggled-on panes of the same kind would collide instead of coexisting. See
>   `panes.builtin.stable-ids` below.
> - **A proportional split stays proportional until a real drag.** `WorkspaceSplitStack`'s
>   `.fraction` sizing used to convert to absolute points on first appear and write that into
>   `@SceneStorage` (SF3 finding) — so a 0.4-fraction column seeded once at a 1000pt window stayed
>   pinned to 400pt forever, even after the window (or the whole Mac) moved to a very different
>   size. The eager seed is deleted; the divider's binding is now a computed one whose getter is
>   the freshly-resolved display value and whose setter (the only thing that writes stored state)
>   fires exclusively from an actual drag. See `panes.split.fraction-not-seeded` below.
> - **Menu Split routes through the model.** `SplitCommandRouting` (the dead `"<slot>-<kind>"`
>   key space the applied renderer never matched, #4685) is DELETED. The toolbar Workspaces menu's
>   Split Right/Below and the menu-bar Workspaces submenu's twin now resolve the focused KIND
>   (`focusedPane ?? paneFocusHint`) to `activePaneList.leafIDs(of: kind).first` and mutate via
>   `activePaneList.splittingLeaf(id, axis:)` — symmetric with how close already worked via
>   `removingLeaf`. **Known limitation, not yet fixed:** with two same-kind panes (Compare) this
>   always resolves to the FIRST leaf of that kind, not necessarily the instance under the
>   pointer — full per-instance precision is still the deferred "increment 4" this spec's
>   Migration order names. Every built-in today has at most one leaf per kind, so it's exact for
>   all of them. See `panes.split.focused-only` below (updated).
> - **Deleted, confirmed callerless before removal:** `widescreenPaneSpecs` (PaneSpec.swift),
>   `PaneList.fromVisibility` (its only caller was `widescreenPaneSpecs`), the `paneKindOverrides`
>   WRITE side (`captureLayoutSnapshot`/`applyLayoutSnapshot` — the live `ContentView.
>   paneKindOverrides` dict has had zero readers since `SplitCommandRouting` went; the
>   `WindowLayoutSnapshot` field itself stays, decode-only, so an old snapshot with the key still
>   decodes), `SplitCommandRouting`, `WindowLayoutPreset` and `WindowLayoutCommands.applyPreset`
>   (a second built-in-arrangement system parallel to `BuiltInWorkspaceLayout`, the exact
>   `workspaces.one-system` violation below). Pinned by `WorkspaceSystemBoundaryTests.
>   testAppliedWorkspaceSplitIsWiredThroughThePaneListModel` (un-skipped — it now finds a real
>   caller of `splittingLeaf(`), `WorkspaceLayoutDefaultsTests.
>   testEveryActivePaneListWriterCallsTheOneFunnel` (a source guardrail: every known
>   `activePaneList` mutation site is followed by `paneListDidChange()`), `WindowWorkspaceTests`
>   (paneList round-trip, malformed-decode leniency, dead-field cleanup),
>   `BuiltInWorkspaceLayoutTests` (stable-id stability/uniqueness, `splittingLeaf`/`removingLeaf`
>   still mint/preserve ids correctly), `WorkspaceSplitStackSeedingTests` (fraction re-resolves
>   proportionally, not seeded).
>
> This is an AREA spec for how a window is *composed* — the pane system that hosts every
> view mode (source/preview, transcription/words, entities, claims, graph/canvas,
> inspector). It sits above the per-mode specs (`kg-tables`, `kg-entity-inspector`,
> `segment-representations`) and owns the cross-pane concerns: split, per-pane
> configuration, synchronized magnification, and saving a composition as a workspace.

## Intent (the design)

A window is a composition of **panes**, not a fixed source/detail pair. Each pane holds one
view of the library — the page image, its transcribed words, the entities, the claims, a
graph/canvas of related things, or an inspector — and each pane is **independently
configurable**: its own view mode, its own zoom, its own magnifier state. Panes compose
freely: three panes side by side, with the image shown in one and hidden in another; a
source pane beside an entity pane beside a claims pane; or two source/preview panes for
comparison. A composition can be **saved as a workspace** and reopened.

The reading surface is built for close looking. A page's original image sits in one pane;
its transcribed **words** sit in another and, on request, **expand to fill their bounding
box** so the text occupies the same geometry as the ink. A **magnifier** (a zoom bar along
the bottom of a pane) can **follow the mouse**, and magnification can be **synchronized
across panes** so moving the loupe over the original moves it over the words too — or
decoupled, one pane's magnifier open while another's is closed.

Entities and claims are not two bespoke screens; they are **two views in the one pane
system**, sharing its selection grammar, split behavior, and workspace persistence. From an
entity you can reach every source page it appears on; from a claim you can reach its
sources. Selecting related things across panes composes a working set — related entities in
a graph pane, their source pages in a preview pane, an inspector on the right — that is
itself saveable.

## Current architecture (grounded, 2026-09-13) — a half-finished migration

The workspace unreliability is not a pile of small bugs; it is **one migration left
half-done**. A code map (every claim cited in Findings below) shows:

- **Two renderers for the centre.** A newer **pane-list** model (`PaneSpec` list →
  `widescreenPaneRow`, each slot wrapped in its own `SplittablePane`) runs only in
  `LayoutMode.widescreen` (the default). `.standard`/`.none` fall to an **older
  hand-branched** renderer (`centerContentRouting` with `PlatformVSplitView`). Any
  behavior can diverge by layout mode. (F1)
- **Three vocabularies for the same panes.** `PaneVisibility`/`WorkspaceLayoutDefaults`
  say `grid/canvas/reading`; `PaneSpec.Kind` says `library/preview/reading/chat`;
  `WindowLayoutSnapshot` says `showLibraryPane/…`. An invariant can't be stated once. (F2)
- **Pin state lives at two different scopes.** The Reader keeps pin *inside*
  `ReadingPaneView` (per split instance — correct); Preview and Library keep pin *on
  `ContentView`*, above the split, so both split halves share one pin. Same-looking
  control, opposite behavior. Entities/Claims have no pin at all. (F3)
- **Zoom is already per-instance** (`webZoom` per `ReadingPaneView`, `PDFZoomController`
  per `PDFPageWithToolbar`) — no shared/global store exists. The "split shares one zoom"
  report is **not explained by the code**; it needs a live repro before any fix. (F4)
- **Claims don't reset on library change.** Entities read a per-library `EntityStore` from
  the environment; Claims cache a `LibraryClaimsModel` that captures the service once and
  reload on `.task(id: folderId)` — keyed to folder, never library — so the library-wide
  Claims row (`folderId == nil` on both sides of a switch) never refires. (F5)
- **Preview "isn't always there."** `PaneContentPlan` claims preview content for
  `.chat/.comparison/.workflow/…`, but `previewView` renders only for `.library` ("the
  remaining #4525 step"); plan and implementation disagree. Plus `.none` mode and the
  width-collapse order shed the preview. (F6)
- **The pane model is fixed-slots, not a list.** `WidescreenPanePlan` is four `Bool`s and
  `PaneSpec.Kind` a fixed 4-case enum, so it **cannot represent two of a kind** — three
  previews side-by-side (original · words · reader) is impossible today; the only "second
  preview" trades the Reader slot away via `paneKindOverrides`. (F7)

### The design: converge on one pane model

The north star is a single model, reached by finishing the migration — not a rewrite:

1. **One renderer.** The pane-list path is canonical; retire `centerContentRouting`. Every
   layout mode composes the same `PaneSpec` list (a `.none`/`.standard` mode is just a
   different *list*, not a different renderer).
2. **One vocabulary.** Collapse `grid/canvas/reading` and `showLibraryPane/…` onto
   `PaneSpec.Kind`; the visibility/persistence layers speak that one language.
3. **A pane LIST, not four Bools.** Replace `WidescreenPanePlan`'s booleans with an ordered
   list of pane entries (kind + content binding), so a window can hold **N panes including
   several of the same kind with different content** — the enabler for "three previews:
   original · words · reader," and for arbitrary compositions the reader saves as a
   workspace. Split (2×2 per slot) stays, but is no longer the *only* way to get a second
   pane of a kind.
4. **Per-instance pane state for every kind.** Pin (and any future per-pane setting) lives
   *inside* the pane instance like the Reader already does, so split halves are independent
   for Preview and Library too, and Entities/Claims gain a consistent pin.
5. **Entities and Claims are one view system.** Same data-lifecycle (per-library store, or
   both keyed on library id), same selection grammar, same reset-on-library-change, same
   pin — differing only in row content and open-target.
6. **Plan == render.** A pane the plan says has content must actually render it, or the plan
   must not claim it (close the #4525 gap).

## North star (CD, 2026-09-13): RELIABILITY over any specific layout

The overriding goal is a pane system that is **reliable and works**, so the CD can
**experiment with various layouts** — not one hard-coded arrangement. Every finding below
is a reliability defect (a pane vanishes, a toggle disappears, a split produces a state you
didn't ask for, a view "takes over"). Fixing these — one composition path, consistent
toggles, predictable split, panes that never silently drop — matters MORE than delivering
the Mail default. The Mail layout is just one composition the reliable system can express.

## CD runtime review 2026-09-13 (design-lead testing) — findings from a live build

Findings from the creative director running the chat-in-sidebar build. Chat-in-sidebar
itself works (committed c4a22c2b5). The rest are the workspace/pane defects to pin+fix.

- `panes.chat.toggle-in-sidebar-top` — **[GAP]** (→ #4705 increment 6) the chat show/hide toggle
  should sit at the TOP of the sidebar, to the LEFT of the sidebar (panel) button — not the
  sparkles button in the main toolbar.
- `panes.sidebar-button.in-sidebar-section` — **[GAP]** (#4735) the sidebar toggle button belongs IN
  the sidebar's own top-left section (Xcode-style), not floating in the main window toolbar's
  left group.
- `panes.split.asymmetric` — **[GAP/BROKEN]** (#4737) splitting a preview vertically then horizontally
  makes a **2×2 grid of 4**; the CD wants asymmetric nesting ("2 over 1" — two panes on top,
  one below). The current split caps at a symmetric 2×2 (`SplittablePane.swift:156-166`) and
  every sub-pane renders the same content. Needs nested/asymmetric split (part of F7).
- `panes.minimap-secondary-pane` — **[GAP]** (#1932) a secondary split pane can act as a MINIMAP
  of the primary — a zoomed-out overview, especially for the WebKit/KG view. The split/side-by-
  side half of this request is substantially covered already (`panes.split.asymmetric`,
  `panes.split.independent-mode-per-pane`, `panes.compose-three-plus`) — the minimap-specific
  rendering mode is the part none of those name.
- `panes.library.horizontal-and-entities-parity` — **[OK]** (fixed a7d349724) the Entities view
  no longer "takes over" — entity/claim/folder library selections all keep the same panes. Was:
  `showsPreviewPane` special-cased only entities→false (full-width takeover) while Claims kept
  the two-pane layout, violating the stable-panes policy. Fix: pure `showsPreviewPane(viewMode:
  layoutMode:)` with no selection input → parity structural. Pinned: `ShowsPreviewPanePolicyTests`.
  (Any remaining left-alignment detail is a follow-up once the takeover is gone.)
- `panes.toolbar.toggles-consistent` — **[OK]** (fixed d4ab628fb) the pane toggles + Workspaces
  menu no longer vanish for KG collections. Was: both gated on `supportsReadingWorkspace`
  (`.library && !isKGLibrarySelection`), so Entities/Claims hid every toggle AND the recovery
  menu. Fix: pure `showsPaneToggles(sidebarMode:compactFlow:)` (drops isKG) + `showsWorkspacesMenu`
  (compact-only); Workspaces menu moved to its own un-gated conditional. Pinned:
  `ToolbarTogglePolicyTests`.
- `panes.claim.source-is-document` — **[OK]** (fixed b7be99143) the Claims Source column shows
  the document NAME (resolved over ALL loaded docs, not just the folder scope — the id-fallback
  bug), is **draggable** (shared `LibraryItemDrag` payload), and **clicks through** to the source
  (the existing `ClaimSourceRequest.request(for:)` cursor entity statements use). Pinned:
  `ClaimSourceLabelTests`.

### Legacy milestone fold — toolbar and shared chrome (#125 UX - Toolbars & Mini Toolbars,
### #251 Surface Chrome - Shared Components; both milestones had no spec of their own)

The window toolbar (pane toggles, the breadcrumb/principal lozenge, the status island, the
Workspaces menu icon) and the shared pane-head/footer chrome (`MiniToolbar`, `PaneFilterBar`)
are already this spec's surface — folding the two legacy toolbar milestones in here rather than
starting a new one.

- `panes.filter-bar.shares-minitoolbar-height` — **[PARTIAL]** (implemented and tested;
  #3370 still open pending close) every mini-toolbar-like pane
  strip — the sidebar bottom toolbar, the document-inspector annotation filter strip, the
  reader/library/preview mini-toolbars — shares ONE height and Liquid-Glass-compatible chrome
  across macOS/iPad/iOS, instead of `PaneFilterBar` hard-coding its own 24pt. Verified at HEAD:
  `PaneFilterBar.height` (`Views/Components/PaneFilterBar.swift:32`) reads
  `MiniToolbar<EmptyView, EmptyView>.standardHeight` directly — there is no separate constant
  left to drift — and both surfaces the issue named, `SidebarBottomToolbar.swift` and
  `DocumentInspectorAnnotationsTab.swift`, both build on `PaneFilterBar`. Pinned:
  `MiniToolbarMetricPolicyTests.testPaneFilterBarUsesMiniToolbarHeight`.
- `panes.status-island.separates-connection-and-activity` — **[PARTIAL]** (#4536) the status
  island should present backend connection, remote connections, WHO else is connected as a
  user, and activity as four SEPARATE indications, not one folded glyph+spinner. Verified at
  HEAD: two of the four already split out as their own toolbar items —
  `EngineStatusToolbarItem` and `ActivityStatusToolbarItem` — each with its own Liquid Glass
  section and popover, leaving `StatusIslandToolbarItem` for the message/selection line only
  (`StatusIslandToolbarItem.swift:1-13`, its own doc comment records the 2026-08-23 split).
  Still missing: a distinct "remote connections" indicator and a "who else is connected"
  indicator — multi-user/agent-session presence has no toolbar surface yet.
- `panes.status-island.message-budget` — **[PARTIAL]** (implemented and tested; #4366 still
  open pending close) every island message reads
  completely at the island's real width; nothing the app authors truncates mid-word. Verified
  at HEAD: `StatusIslandMessage.budget`/`.declaredMaxWidth`, `.authoredMessages` (the
  app-authored strings held to budget by test) and `.shortForm(_:)` (a named, tested seam
  that clips an OS/backend string on a word boundary, never a silent SwiftUI clip) all exist
  exactly as asked (`StatusIslandToolbarItem.swift:156-215`). Pinned:
  `StatusIslandMessageBudgetTests`.
- `panes.status-island.errors-are-short-and-typed` — **[PARTIAL]** (#4269) the content area
  never shows raw error text (NSError descriptions, domains, codes, URLs); the island shows a
  short human sentence, and clicking it reveals the full technical text plus a one-click
  "Report to GitHub." Verified at HEAD: `StatusIslandMessage.resolve` already routes every
  engine/import failure through `shortForm(_:)` before it reaches the island
  (`StatusIslandToolbarItem.swift:244-266`), so the SHORT-message half is built. Not verified
  on disk: a details-on-click popover showing the full text, and the "Report to GitHub" filing
  pipeline — no such view or endpoint call was found under `Views/Shell/Toolbar/`.
- `panes.status-island.selection-noun-matches-type` — **[PARTIAL]** (#4586) the selection
  noun ("N images/pages/folders selected") should pick off the SELECTION's own file/doc
  types, matching PDFs-have-pages / folders-have-documents-or-images / images-are-images.
  Verified at HEAD: the noun-derivation closure (`ContentView+Toolbar.swift:349-357`) already
  checks `fileType == .image` before `docType == .page`, so an all-image selection should
  already read "images." No test pins this derivation (`StatusIslandToolbarTests` only
  exercises `resolve` given an already-decided noun string), so whether the live repro the maintainer
  filed is actually fixed cannot be confirmed from source alone — flagged for a live re-check
  before this is retagged OK or closed.
- `panes.toolbar.owns-identity-namespace` — **[GAP]** (#3203) every item contributing to a
  window toolbar should carry an explicit `ToolbarItem(id:)` from one shared namespace, so a
  prior duplicate-identifier class of launch crash (two earlier, already-closed P0 incidents)
  cannot recur, with a guardrail failing CI on a new id-less toolbar item. Verified at HEAD:
  only 2 of the 46
  `.toolbar {` contribution sites in the tree declare any `ToolbarItem(id:)`
  (`ContentView+Toolbar.swift`, `ContentView+InspectorContainer.swift`) — the other 44 still
  rely on SwiftUI's auto-derived identifiers. No guardrail script exists yet for this class.
- `panes.toolbar.ia-groups-by-what-it-acts-on` — **[GAP]** (#4374) a toolbar control's
  position should say what it acts on: the pane-visibility toggles (sidebar/reader/reading/
  inspector) form one cluster at the window's edge, and controls that act on the library
  (sort, filter, view-mode) sit over the library's own mini-toolbar, not at the window's far
  edge. Not verified as built; the View-menu-duplicating toolbar button this issue also flags
  is a `menus-and-commands.md` question, not repeated here.
- `panes.toolbar.breadcrumb-is-a-real-path` — **[GAP]** (#4378) the breadcrumb should read as
  a drillable PATH (`Library > Folder > PDF > 1`) with a page SELECTION at the end, not a
  count prefix, and every element should be a real, draggable macOS proxy icon (file
  promises, so it still works when the server is remote). The existing breadcrumb/principal-
  lozenge behavior above this spec already owns is the format's home; this issue is the
  richer interaction on top of it, not built.
- `panes.toolbar.declutters-per-item-actions` — **[GAP]** (#2433) a main-toolbar button that
  only acts on the current selection (e.g. "open this attribute in a text window") belongs in
  a contextual menu and/or a mini-toolbar icon on the thing itself, not the main window
  toolbar; "open in a new window" should be one general capability reachable for any node
  (doc/page/artifact/attribute), consistent with the reader/inspector mini-toolbars. Not
  verified as built.
- `panes.chrome.shared-surfacechrome-component` — **[GAP]** (#3530) the Reader/Inspector tab
  bar + bottom mini-toolbar + sub-tab pattern should be extracted into one reusable
  `SurfaceChrome` component set so Workflow/Chat/Agent/Research/Search can adopt the same
  chrome without re-deriving it. Verified at HEAD: no `SurfaceChrome`-named type exists
  anywhere under `fichero/fichero/` — `MiniToolbar`/`PaneFilterBar` are shared, but the tab-bar
  half of the pattern is not yet extracted.

Needs maintainer triage, not folded as a behavior here: **#3540** ("DECISIONS NEEDED —
surface-consistency, fourteen open questions for the maintainer") asks which surfaces adopt `SurfaceChrome` and
how (Workflow tabs, Chat/Agent tabs, Research's 3-pane layout, Search's tab strategy, the KG
view-mode switcher's location) — filed 2026-07-12, before the modes-to-panes and panes-
workspaces rulings that have since answered several of its 14 questions on their own terms
(the KG switcher question in particular looks pre-empted by `panes.kg.select-shows-item-
inspector` and the modes-to-panes "KG graph/map = Library view modes" ruling). Re-reading it
question-by-question against what has shipped since, rather than assuming it is still live in
full, is a maintainer call, not one to make while folding a milestone.

Left in its legacy milestone, not folded here: **#2501** (swipe-to-delete / row swipe actions
on library and inspector list rows) is a Library/Inspector ROW-gesture ask, not window or
pane chrome — no existing spec's surface is the row itself (the library-view-modes spec
proposed in the milestone ledger would be the right home once it exists). Left in #125 for
now rather than forced into this spec.

### Legacy milestone fold — window/pane redirects from "Library View" (#117)

Two more issues, redirected from the legacy "Library View" milestone while folding
`library-view-modes.md`'s pass 2 (neither is a view-MODE question; both are window/pane
behavior this spec already owns):

- `panes.double-click-focuses-current-window` — **[GAP]** (#3364) double-clicking a
  sidebar/library item should focus/navigate in the CURRENT window by default; opening in a
  new window or tab stays reachable only from an explicit contextual command. Not verified
  as built.
- `panes.split.each-pane-its-own-document` — **[GAP]** (#2422) a split reader pane should be
  independently targetable to a different document (drag a doc into a pane, or a per-pane
  picker), with a clear control choosing "different doc per split" versus the existing
  same-doc/compare mode. Not verified as built; ties this spec's existing split-independence
  behaviors (`panes.split.independent-mode-per-pane`) to CONTENT independence, which those
  behaviors do not yet cover.

One more, redirected from the legacy "UX - Library & Reading Surface" milestone while folding
`library-view-modes.md`'s pass 2 (a toolbar-chrome question, this spec's territory, not a
Library view-mode question):

- `panes.toolbar.reader-filter-button-is-explained-or-removed` — **[GAP]** (#1473) the
  reading-surface top toolbar has a "filter" button whose purpose is unexplained — either
  give it a clear function and label, or remove it. Not verified either way.

One more, redirected from the legacy "Reader View - Page" milestone while folding
`reader-view.md`'s pass 2 (the same toolbar-overflow territory `panes.toolbar.*` above
already owns):

- `panes.toolbar.reader-overflow-collapses-before-overlapping` — **[GAP]** (#2515) the
  Reader's own toolbar (top and/or bottom strip) must stay within the reading column — never
  overlap the library sidebar/filmstrip or the inspector — and secondary tools should
  collapse into the trailing "…" overflow menu BEFORE anything overlaps, not after. Not
  verified as built; the issue's own diagnosis (a `ViewThatFits` likely measuring the whole
  window rather than the content column) was not re-checked this pass.

### Post-F7 design refinements (CD, 2026-09-14) — capture, revisit after F7

- `panes.kg.select-shows-item-inspector` — **[GAP, post-F7]** (→ #4705 increment 7) clicking a claim or entity row
  auto-opens the full **document inspector** (with its source) today (works, but heavy). The
  CD wants selection to instead show a **focused inspector for THAT claim/entity** — the
  item's own inspector, not the whole document+source surface. (Ties `kg-entity-inspector`;
  a claim inspector is the claim-side equivalent.)
- `panes.kg.clickable-lists-and-sidebar` — **[GAP, post-F7]** (#4742) richer click-through
  interactions in the claims/entities lists AND the sidebar (click things to act/navigate).
  Deferred by the CD until F7 lands.
- `panes.content-column-under-sidebar` — **[BROKEN, F7]** (#4743, re-diagnosed 2026-09-18: CANNOT
  CONFIRM from source, not retagged) (screenshots confirm as of 2026-09-14) the content
  column starts at the window's LEFT EDGE (x=0) and runs UNDER the sidebar: with the sidebar
  shown, the leftmost columns are covered; hide the sidebar and the full content appears. CD
  2026-09-14: this is NOT KG-specific — **Claims, Entities, workflows, and images all do it**,
  so it's the general content-column placement in the renderer, not a per-view bug. Re-checked:
  the shell is a native `NavigationSplitView` (`ContentView+RootLayout.swift`) whose detail
  column (`detailColumn`) is a proper split-view slot with safe-area insets, not an
  absolutely-positioned overlay — structurally unlikely to bleed under the sidebar, and the F7
  one-renderer migration this was filed against has since landed (`activePaneList` now always
  seeds to Read). But this is a rendered-pixel claim ("screenshots confirm"); source reading
  cannot prove a layout bug is gone. **Manual check (ten seconds): open the app, select a
  Library/Claims/Entities/workflow item with the sidebar visible, and look at whether the
  content area's left edge sits flush against the sidebar's trailing edge or extends under
  it.**
- `panes.vertical-no-breadcrumb` — **[BROKEN, F7]** (#4744, re-diagnosed 2026-09-18: looks
  FIXED, by a different mechanism than the issue assumed — not retagged pending verify-close)
  the vertical split/pane has no breadcrumb bar (the horizontal one does). Re-checked: the
  per-pane clickable breadcrumb strip this issue describes was RETIRED entirely, not extended
  to the vertical case — `ContentView+SidebarLayout.swift:194-199`'s own comment: the pane-level
  strip was one of FOUR in-window copies of the same path and is retired (a dedupe);
  the location breadcrumb now lives ONLY in the window toolbar's principal lozenge, which does
  not depend on split orientation at all. There is no longer a per-pane copy that could be
  present on one orientation and missing on another. Recommend verify-close.
- `panes.kg.filter-targets-active-view` — **[GAP]** (#4745, re-diagnosed a SECOND time
  2026-09-18: the mechanism named above was wrong; corrected below, awaiting a product
  decision, not a mechanical fix) TEXT search is NOT the divergence — traced symbol by
  symbol: the ONE per-window search request (`activeSearchQuery`) is passed to BOTH tables
  identically (`LibraryView+ContentBranches.swift`'s `claimsContent`/`entitiesContent`,
  `searchQuery: activeSearchQuery` on each); each table's own local `filterText` is a
  deliberate in-table REFINE that intersects it, already pinned by `EntitiesFilterTests`/
  `ClaimsFilterTests`. The REAL divergence is entity-KIND VISIBILITY, two mechanisms that
  never read each other: (A) the "Filter Entities" menu
  (`LibraryView+EntityFiltering.swift`) — a multi-select hide/show per kind, persisted
  app-wide and cross-window in `@AppStorage("inspector.kg.hiddenKinds")` — obeyed by the
  list view AND the inspector (`KnowledgeGraphInspectorSection.swift` reads the same key).
  (B) the Entities/Claims TABLES each keep their own private single-select
  `@State filterType: String?` (verified: `EntitiesLibraryContent.swift:33`,
  `ClaimsLibraryContent.swift:43`) and never read the hidden-kinds preference at all — so
  hiding a kind everywhere else still shows it in the table, and the table's own type filter
  means nothing elsewhere. **This is a product decision, not a bug to fix mechanically** —
  three options: (a) additive, the tables also obey the hidden-kinds preference alongside
  their own refine; (b) one control, replacing the tables' dropdown with the same
  multi-select; (c) declare the boundary intentional (a persisted "never show Dates" and a
  momentary "only People right now" are different intents). A separate, related question:
  the hidden-kinds preference is app-global `@AppStorage` today — with independent
  per-window/per-pane view modes coming (`panes.split.independent-mode-per-pane`, #4720),
  should it become per-window or per-pane instead? (Ties `panes.kg.one-view-system` above,
  → #4705 increment 3 — the underlying entities/claims unification is a separate, larger
  question this filter-visibility decision doesn't have to wait for.)

### Reliability sweep (same-class latent bugs, 2026-09-13 overnight) — F7/NEEDS-CD

A sweep for the same bug class as the fixed findings surfaced deeper, design-entangled
defects (the toggle half of the CD's "can't turn preview/library/reader on or off"):

- `panes.toggles.inert-outside-widescreen` — **[OK, 2026-09-18]** (fixed 73478d926, 9d428aee9,
  fe5b282c4) the Preview/Reader/Chat toolbar toggles are no longer no-ops outside widescreen —
  `centerContentRouting` (the layoutMode-gated legacy renderer this bug depended on) is DELETED
  (confirmed: only a doc comment referencing it remains, `PaneSpec.swift:21`), and the toggle
  buttons (`ContentView+Toolbar.swift:186,195,207,256`) read/write `paneVisibility`/
  `activePaneList` directly — derived from the pane list, not gated by `LayoutMode`. A repo-wide
  search for `currentLayoutMode = .widescreen` (the force-reflow this line complained about)
  found zero remaining call sites. Pinned: `ToolbarSurfaceLitStateTests`
  (`paneTogglesLight` — the toolbar reads `paneVisibility`, not a layoutMode-gated Bool) —
  same fix cluster as `panes.visibility.derived-from-list` above.
- `panes.dead-toggle-policy` — **[OK]** (bca344581, #4747 closed) `ReadingWorkspacePaneTogglePolicy`
  documented the exact intended behavior for the above ("a toggle from None/Standard enters
  the widescreen workspace and shows that pane") but had zero call sites — the real toggle
  path reimplemented only its ON-half inline. Resolved by DELETION, not wiring — the type and
  its two self-only tests are removed entirely, matching the F7 plan's own stated direction
  (the pane-list model's `toggling(kind:)` is the one toggle path now, not a second documented
  policy nothing calls). Verified: `git log`'s own commit message confirms the removal;
  `ReadingWorkspacePaneTogglePolicy` no longer exists anywhere in `fichero/fichero`. The
  OFF-half the dead policy only documented is now covered by the SAME `toggling(kind:)` model
  every other toggle already runs through. Pinned:
  `PaneListTests.toggleAbsentAppends`, `.togglePresentRemoves`, `.toggleTwiceRoundTrips`,
  `.toggleAlwaysChangesKinds`.

**These confirm the reliability root is F1/F7:** the toolbar controls promise pane management
the legacy renderer doesn't deliver. The reliable fix is one composition path (F7), which is
why "make it reliable so I can experiment" and "generalize to a pane list" are the same task.

**The 2-column target (CD, restated):** LEFT column = the browser (library / entities / claims)
on top with a reader beneath it; RIGHT column = the preview (source image). Chat in the sidebar.
This is the Mail default below, expressed in the eventual pane-list model.

## F7 implementation plan (the reliability generalization) — for CD review

F7 is the one change that makes the pane system reliable AND lets you experiment with
layouts. It subsumes the toggle-inertness (#1), the undocumented-vs-documented policy
divergence (#2, resolved — bca344581 deleted the unwired policy), the
widescreen-only pin/split (#3), the asymmetric split, and the 2-column target — because
all of those are symptoms of *two renderers + a fixed-slot plan*. Incremental, not a
rewrite; each step is independently shippable and testable.

1. **Model — a pane LIST, not four Bools.** Introduce `PaneList = [PaneEntry]`, where
   `PaneEntry = { kind: PaneKind, scope: PaneScope, split: SplitSpec? }`. `PaneKind` =
   library/preview/reading/chat (the existing `PaneSpec.Kind`). `PaneScope` = which
   library/document/folder the entry shows (this is what enables *different libraries /
   different previews side by side*). Replaces `WidescreenPanePlan`'s four `showsXPane`
   Bools. Pure + `Codable` → unit-testable and directly serializable as a workspace.
2. **One renderer.** A single `paneRow(from: PaneList)` (generalise the existing
   `widescreenPaneRow`) renders EVERY layout mode. Retire `centerContentRouting`: `.none`
   and `.standard` become just *shorter PaneLists* (e.g. `.none` = `[library]`, `.standard`
   = `[library, preview]`), not a different code path. **Fixes #1** (all modes honor the
   list, so toggles work everywhere) and **#3** (pin/split chrome is per-entry, so it's
   available in every mode).
3. **Toggles mutate the list.** A pane toggle adds/removes a `PaneEntry` of that kind
   (works in every mode; no more `showDocumentGrid`/`showDocumentCanvas`/… Bools — the list
   is the single source of truth). Deletes the `showsPaneToggles`/`visiblePanes` divergence
   and the dead `ReadingWorkspacePaneTogglePolicy` (#2). Pure seam: `PaneList.toggling(kind:)`.
4. **Asymmetric split is a nested list.** `SplitSpec` lets a `PaneEntry` hold sub-entries
   (a pane's content is itself a small `PaneList` in a `.horizontal`/`.vertical` split),
   recursively — so "2 over 1" is `split(.vertical, [split(.horizontal, [a, b]), c])`.
   Replaces the symmetric 2×2 `SplittablePane` cap. Pure seam: the split tree + its
   flatten-to-views. **Fixes the asymmetric-split finding.**
5. **Per-instance state stays per-entry.** Pin/zoom already live per sub-pane instance
   (F3/F4 done); each `PaneEntry`'s rendered view keeps that. The list just says *which*
   entries exist and how they nest.
6. **Persistence + workspaces.** A saved workspace IS a `PaneList` (kinds + scopes + splits).
   `WindowWorkspace` snapshots become PaneLists. **Delivers "save/reopen arbitrary
   compositions."**
7. **The Mail default is a starting list.** sidebar+chat (left column, already done) ·
   centre `[library, reader]` stacked · right `[preview]` — expressed as the default PaneList.
   No special layout code; just the initial value.

**Sequence:** (1) model + (3) toggling as pure Codable types with tests → (2) route the
widescreen path through `paneRow(from:)` (it's already list-shaped via `PaneSpec`) → fold
`.standard`/`.none` in and retire `centerContentRouting` → (4) nested split → (6) workspace
serialization → (7) default. Each step keeps the suite green; the risky view-composition
steps (2, 4) need CD runtime verification, the model/logic steps (1, 3, 6) are unit-gated.

## Default composition (Mail-style) — RATIFIED 2026-09-12

The default window is a three-region Mail-style layout. It prioritises the primary source
image (full height, right) while grouping navigation and the AI workspace on the left and
the browse→read flow down the centre.

```
┌────────────────┬─────────────────────────────┬──────────────────┐
│ Sidebar        │ Library browser             │                  │
│ (folder tree)  │ (icon/list — a HORIZONTAL   │                  │
│                │  thumbnail strip, Mail       │                  │
│                │  message-list style)         │   Source image   │
│                ├─────────────────────────────┤   (the archival  │
│ ─── divider ── │ Reader(s)                    │    scan, FULL    │
│ Chat history   │ (transcription / summary /   │    HEIGHT, far   │
│                │  metadata — one or two       │    right)        │
│                │  readers)                    │                  │
│ [ ask prompt ] │                              │                  │
└────────────────┴─────────────────────────────┴──────────────────┘
   left sidebar      centre: horizontal split       right column
```

- **Left** — folder tree on top; **chat history + its input stacked directly beneath it**,
  in a collapsible split region (an `NSSplitView` divider the user can drag to give chat
  more room or collapse when just navigating). The chat input is attached to the chat
  history — it does **not** float at the bottom of the image/reader.
- **Centre** — a **horizontal split**: the library browser (a horizontal thumbnail strip)
  on top, one or two readers (transcription / summary / metadata) below. Selecting a
  thumbnail above drives the reader below.
- **Right** — the source image, anchored full height (historical documents are vertically
  oriented, so uninterrupted top-to-bottom space maximises zoom and minimises scrolling).

## Behaviors (each → one pinning test)

### A. Pane composition & split

- `panes.split.focused-only` — **[PARTIAL]** splitting a pane (vertical or horizontal) splits
  the **focused** pane, not every column at once. Model + routing fixed (2026-09-15,
  33cbcdf92): `PaneList.splittingLeaf(id:axis:)` splits only the targeted leaf, and
  `PaneSpec.slot` makes each pane's split key per-instance (was per-kind), so same-kind panes
  no longer share one split cell. **2026-09-18:** the toolbar Workspaces menu's Split Right/Below
  and its menu-bar twin now ACTUALLY route through the stored `PaneList` (fixed, closed) —
  resolving `focusedPane ?? paneFocusHint` to a kind, then `activePaneList.leafIDs(of: kind).first`, then
  `activePaneList.splittingLeaf(id, axis:)`. REMAINING (#4795): instance-precise focus — with
  two same-kind panes (Compare) this still targets the FIRST leaf of the focused kind, not
  necessarily the instance under the pointer; every built-in today has at most one leaf per
  kind, so it's exact for all of them, but full per-instance precision (the "increment 4" this
  spec's Migration order names) is still open. Pinned: `PaneListTests` ("splitting a pane splits
  ONLY that pane…") + `WorkspaceSystemBoundaryTests.
  testAppliedWorkspaceSplitIsWiredThroughThePaneListModel` (un-skipped 2026-09-18 — it now finds
  a real caller of `splittingLeaf(` outside the model's own file).
- `panes.close.this-pane-only` — **[OK]** (applied path always live 2026-09-16, dfa937946) closing a
  pane removes only that pane; its siblings survive and a split that loses a child collapses to the
  survivor, not the whole row. The VIEW now always renders the stored `PaneList` (seed = Read), so the
  close routes through `\.paneCloseAction` → `removingLeaf(id:)` rather than the legacy `setPaneVisible`
  Bool. Split-then-close-both is fixed by reordering the PaneHead close ladder so an active in-slot
  split collapses by one before the leaf is removed. Pinned:
  `Tests/Unit/general/Models/PaneListTests.swift` ("closing a pane removes ONLY that pane…",
  "…collapses to the survivor — the row does not disappear") + `PaneInstanceIndependenceTests`.
- `panes.head.kind-switcher-everywhere` — **[PARTIAL]** (#4706; Reader fixed d8621ecc3, pinned by
  `PaneHeadKindSwitcherParityTests`; Chat follows → #4705 increment 6) every pane head
  that renders a leaf kind mounts the kind selector, so ANY pane can become a Library, Source or
  Reader. Cause (verified): the Reader head mounts `PaneKindSelector` with `collapsesKindIntoLens: true`
  (the one-icon ruling), whose merged-lens path never consulted `\.paneKindSwitcher`; Library /
  Preview / Chat take the adaptive path, which does. Every leaf already receives the switcher
  (`PaneSpec.swift:318-321`). Placeholder kinds
  (`.inspector`, `.chat`) stay out of the list until they are real leaves (#4705, increments 6–7);
  the chat head gains the selector when chat becomes a pane. *Test:* a source guardrail that every
  pane head mounts `PaneKindSelector`, plus a pure test of `selectableKinds`.
- `panes.split.independent-mode-per-pane` — **[BROKEN]** (#4720) each pane holds its own view mode;
  changing one pane to Entities or Claims does not clear or convert the others. Today
  switching a pane's node-type to entity/claim in the entities view removes them from the
  other panes.
- `panes.open-view-arbitrarily` — **[GAP]** (#4722) any pane can be set to any view mode (source /
  words / entities / claims / graph / inspector) directly, without routing through a
  document selection. Today there is no way to open an entity or claim view arbitrarily in
  a window.
- `panes.compose-three-plus` — **[GAP]** (#4724) a window supports three or more panes, and any
  pane may hide its image while another shows it.
- `panes.visibility.derived-from-list` — **[OK, 2026-09-18]** which content panes show
  (library/preview/reading) is a PURE derivation of `activePaneList.kinds`
  (`PaneVisibility.paneVisibility`, `PaneVisibility.swift`) — not a separate stored Bool per
  pane. The three legacy `@SceneStorage` Bools this used to read are DELETED from
  `ContentView.swift`, so there is nothing left for toolbar labels, View-menu checkmarks, or
  `cyclePaneFocus`'s pane-cycle order to drift out of sync with what the window actually
  renders. Pinned: `WorkspaceLayoutDefaultsTests`
  (`testOnlyTheDeliberatelyChosenSurfacesAreRemembered` — the remembered-Bool inventory is
  chat + layoutMode only, not the three panes) + `ToolbarSurfaceLitStateTests`
  (`paneTogglesLight` — the toolbar reads `paneVisibility`, not a Bool).
- `panes.builtin.stable-ids` — **[OK, 2026-09-18]** a built-in workspace's leaf ids are STABLE
  across every access (same `PaneList` value every time `BuiltInWorkspaceLayout.read.panes` is
  read), not freshly random each time. `PaneNode.stableLeaf`/`.stableSplit` (`PaneList.swift`,
  `UUID(stableName:)`, MD5-based) replace the plain `.leaf`/`.split` factories in every built-in
  composition (`BuiltInWorkspaceLayout.swift`); a leaf's name is `"\(rawValue).<role>"`, unique
  within a case and across cases. Without this, navigating away from and back to a built-in (or
  a relaunch reseeding against it) silently lost a dragged divider's stored width and orphaned
  `@SceneStorage` keys, because `WorkspaceSplitStack`/`PaneSpec` key that per-instance state off
  a leaf's id. Runtime mutation (`toggling`, `splittingLeaf`'s duplicate, `settingVisible`'s
  appended leaf) still mints fresh random ids — a stable id there would make two toggled-on
  panes of the same kind collide instead of coexisting. Pinned: `BuiltInWorkspaceLayoutTests`
  (stability across two accesses, no id shared between built-ins, `splittingLeaf` still mints a
  fresh id for the new duplicate, `removingLeaf` leaves survivors' ids untouched).
- `panes.split.fraction-not-seeded` — **[OK, 2026-09-18]** a `.fraction`-sized split column
  (`WorkspaceSplitStack`) stays proportional to the CURRENT window size until the user actually
  drags its divider — it is never converted to an absolute-points value just because the window
  happened to render once. Before this, `seedIfNeeded` wrote `fraction × total` into
  `@SceneStorage` on the first `.onAppear`, so a 0.4-fraction column seeded at a 1000pt window
  stayed pinned to 400pt forever, even after the window (or the whole Mac) moved to a very
  different size. Fixed by deleting the eager seed and making the divider's binding computed:
  its getter is the freshly-resolved display value (`WorkspaceSplitStack.resolvedExtents`,
  already unset-aware); its setter — the only thing that ever writes stored state — fires
  exclusively from `ResizableDivider`'s own drag handler. Pinned:
  `WorkspaceSplitStackSeedingTests` (an unseeded fraction re-resolves proportionally across two
  different totals; a real stored override still wins regardless of total).
- `panes.split.peers-open-even` — **[BROKEN]** (#4849) the rule stated precisely: when a
  horizontal split has 2, 3, or 4 SIBLING peer panes and the user has not yet dragged a
  divider, the columns open EQUAL — each is 1/n of the row. A user's drag still wins
  afterwards, same as `panes.split.fraction-not-seeded` above. A deliberately UNEQUAL built-in
  layout (for example a narrow Library navigator beside wider content) is not a peer split and
  keeps its own specified weights — the even rule is the default for PEERS, not a blanket
  override of every split. Verified BROKEN: `PaneSpec.childExtents` (`PaneSpec.swift:382-404`)
  seeds every non-last sibling from its own `paneFraction` (or a `0.4` fallback) and always
  flexes only the LAST child — with three or four siblings the seeded fractions do not divide
  the row evenly, so the flexing pane ends up a different width from the rest. Compounding it:
  `WorkspaceSplitStack` persists at most TWO resizable/proportional child slots via
  `@SceneStorage` (`WorkspaceSplitStack.swift:55-58`) — a third or fourth resizable sibling has
  no slot and re-resolves fresh from its fraction every render rather than sharing the
  persisted-drag benefit the first two get. Reported from maintainer testing: a four-pane row
  opened as two narrow previews, one wider preview, and a wide reader — exactly this shape.
- `panes.strip.fixed-extent-is-content-not-whole-pane` — **[BROKEN]** (#4848) a HARD-pinned
  pane extent (`PaneConfig(paneExtent:)`) describes the visible CONTENT the user is meant to
  see — a strip of page icons, say — not the whole pane including its own head and footer
  chrome. Verified BROKEN: every built-in bottom Library strip is pinned at
  `PaneConfig(libraryLayout: "icons", paneExtent: 72)` (`BuiltInWorkspaceLayout.swift:115, 137,
  155`), and `PaneSpec.childExtents` (`PaneSpec.swift:382-404`) treats that `72` as the pane's
  TOTAL extent — the pane head and footer bar together already use roughly that much, leaving
  the icon strip itself almost no room. Fix direction: the fixed extent should describe the
  icon strip's own content height, with the pane's actual extent computed as that content
  height plus its head/footer chrome — not the reverse. Reported from maintainer testing: a
  bottom-strip workspace showed only the pane head and footer bar, no page icons at all.
- `panes.split.minimap` — **[GAP]** (#1932) a split pane can act as a minimap of another pane's
  content — especially the WebKit/KG graph view, where a small secondary pane shows an overview
  of the whole document/graph while the main pane is zoomed in. Splitting and side-by-side
  comparison themselves are already covered above (`panes.split.focused-only`,
  `.independent-mode-per-pane`, `.fraction-not-seeded`) — this behavior is specifically the
  MINIMAP relationship between two panes, not plain splitting. Distinct from
  `NavigatorMiniMap.swift` (`Views/Preview/ImageViewer/`), which is an image-viewer zoom
  navigator inside a single pane (`preview-magnifier.md`'s territory) — not a second PANE
  showing an overview of a first one. Not built.

### B. Cross-pane zoom & magnifier state

> SCOPE (creative-director, 2026-09-17): the magnifier/loupe ITSELF is a **Preview / source**
> feature — how it tracks the pointer, magnifies, parks and resizes belongs to
> [[preview-magnifier]], not here. What is a PANE concern is only how that state behaves across
> MORE THAN ONE pane: whether each pane holds its own, and whether they sync. This spec owns the
> plumbing; the preview spec owns the instrument.

- `panes.magnifier.per-pane-open-state` — **[GAP]** (#4725) each pane's magnifier opens and closes
  independently — one pane magnified while another is not. (Pane-scoped state; the magnifier's
  own behavior is `preview-magnifier`.)
- `panes.zoom.sync-across-panes` — **[GAP]** (#4726) when synchronization is on, zoom/magnification
  in one pane drives the corresponding region in the others (original ↔ words), so the loupe
  is shared; sync is toggleable, off by default. This is the ONE genuinely cross-pane magnifier
  behavior — it cannot live in the preview spec because it is about panes relating to each other.
- `panes.words.fill-bounding-box` — **[GAP]** (#4728) on request, transcribed words expand to fill
  their segment's bounding box, occupying the same geometry as the underlying ink. Owned by
  `segment-representations` (the `text` representation rendered into the segment anchor); listed
  here only because it is observed in a pane.

### C. Unified entity ↔ claims view system

- `panes.kg.one-view-system` — **[BROKEN]** (→ #4705 increment 3) the entities view and the claims view are the
  same pane-system view, sharing selection grammar, split, magnifier, and workspace
  persistence. Today they are separate implementations that behave differently.
- `panes.kg.library-change-resets` — **[OK]** (fixed 5b709aca0) switching the active library
  resets the claims AND entities tables to the new library's data — Claims key `.task` on a
  composite `library|folder` key and rebuild the cached model on a library switch; Entities
  key on `ObjectIdentifier(store)`. Pinned: `ClaimsLibraryReloadKeyTests`
  (`fichero/Tests/Unit/general/Views/Library/ClaimsLibraryReloadKeyTests.swift`).
- `panes.entity.sources-pane` — **[GAP]** (#4729) an entity pane can show **all source pages** the
  entity appears on — scroll through them, see the same name across four documents, judge
  whether it is one person. (An entity is a name; its statements/sources are where it
  lives — see `kg-entity-inspector`.)
- `panes.claim.sources-pane` — **[GAP]** (#4730) a claim (or a page's set of claims) can show its
  source pages in a preview pane, each anchored to the passage.
- `panes.inspector-always-visible` — **[GAP]** (#1199) the inspector is a stable, always-present
  rightmost pane across every view (library, reading, KG graph, workflow) — never hidden, never
  replaced by a takeover. Not built: `.inspector` is a PLACEHOLDER kind today, not a real leaf
  (`panes.head.kind-switcher-everywhere`'s own text: "placeholder kinds (`.inspector`, `.chat`)
  stay out of the list until they are real leaves"); the spec's own Migration order already names
  "Inspector as a `PaneKind`" as a planned step (§Migration item 3) — this behavior is that
  step's acceptance criterion, not new scope.
- `panes.inspector-chrome-icon-tabs` — **[GAP]** (#1854) every right-hand inspector surface
  (document inspector, WebKit/KG view, image/preview) renders its tabs as a compact SF-Symbols
  icon tab-bar (Xcode-style) with a centered "No Selection" placeholder when nothing is selected,
  rather than each surface inventing its own chrome. Pure presentation, not a content change —
  distinct from `panes.inspector-always-visible` above (whether the inspector exists at all vs.
  how its own tabs look once it does).

### D. Workspaces

- `panes.workspace.crud-contract` — **[OK]** (verify-close candidate; TL-2's original ask, filed
  before this backend existed) a workspace's `curated_items` support atomic add/remove/reorder
  and resolve their aliases to full objects, library-canonical (never copied). Built:
  `PATCH /{doc_id}/workspace` (`documents.py:997`) and `GET /{doc_id}/workspace/items`
  (`documents.py:1015`, resolving `curated_items` via `_normalize_curated_items`) both exist.
  Pinned: `test_routes_documents_workspace.py::test_workspace_patch_add_remove_reorder_items`,
  `::test_workspace_items_resolve_document_alias_targets`,
  `::test_list_workspaces_returns_only_workspace_docs`,
  `::test_document_and_agent_workspaces_have_distinct_endpoints`.
- `panes.workspace.save` — **[PARTIAL]** "Save Current as
  Workspace…" captures the REAL pane composition, not a lie: `WindowLayoutSnapshot.paneList:
  PaneList?` (`WindowWorkspace.swift`) is set to `activePaneList` (`captureLayoutSnapshot`,
  `ContentView+LayoutChooser.swift`) — this was the field that was missing (§"Existing
  machinery"'s "model split" debt); pinned by
  `WindowWorkspaceTests.testSnapshotCarriesTheAppliedPaneListThroughJSON` (round-trip incl.
  leaf ids). REMAINING (#4731): sync-toggle state and a live selection-scope snapshot beyond
  `PaneScope.documentId` are not captured — deliberately out of scope for this increment
  (spec §"Resolved 2026-09-15": save = layout only, by design), tracked as a real backlog
  item rather than closed as won't-fix.
- `panes.workspace.reopen` — **[OK]** applying a saved workspace assigns its `paneList` to
  `activePaneList` (`applyLayoutSnapshot`) — before this fix it never touched `activePaneList`
  at all, so applying a saved workspace changed nothing visible. An OLD snapshot (saved before
  this field existed — a brand-new coding key, so old JSON simply lacks it) decodes with
  `paneList == nil` and applies as the Read default, logged rather than crashed. A PRESENT but
  MALFORMED value (the SF10 adversarial-review finding) also degrades to `nil` — via a local
  `try?` around the one field's decode inside `WindowLayoutSnapshot.init(from:)` — rather than
  throwing out of decode and voiding the ENTIRE saved-workspace catalog
  (`WindowWorkspaceCatalog.decoded(from:)` swallows any throw from a member's decode to `nil`
  for the whole catalog). Pinned: `WindowWorkspaceTests`
  (`testAnOldShapeSnapshotDecodesWithPaneListNil`,
  `testASnapshotWithMalformedPaneListDataStillDecodesWithPaneListNil`,
  `testOneWorkspaceWithMalformedPaneListDoesNotDeleteTheRestOfTheCatalog`).
- `workspaces.persist-applied-list` — **[OK, 2026-09-18]** the applied `PaneList` survives a
  relaunch: EVERY writer of `activePaneList` (`setPaneVisible`, `applyWorkspaceLayout`, a
  saved-workspace apply, `splitFocusedLeaf`, pane-head close/kind-switch) ends by calling
  `PaneVisibility.paneListDidChange()`, the ONE funnel, which remembers the composition via
  `WorkspaceLayoutDefaults.rememberPaneList` (a JSON-encoded `UserDefaults` key, kept OUTSIDE the
  Bool-only `WorkspaceLayoutDefaults.Key` enum since it's a different shape). `ContentView.
  activePaneList`'s seed reads it back — `WorkspaceLayoutDefaults.rememberedPaneList() ??
  BuiltInWorkspaceLayout.read.panes` — falling back to Read when nothing was ever remembered.
  Pinned: `WorkspaceLayoutDefaultsTests`
  (`testRememberedPaneListRoundTripsThroughUserDefaults`,
  `testNoRememberedPaneListReturnsNilSoTheCallerCanFallBackToRead`,
  `testThePaneListSeedIsWired`, and the structural guardrail
  `testEveryActivePaneListWriterCallsTheOneFunnel` — every known mutation site is followed by
  `paneListDidChange()` within a few lines — a new writer that skips it fails this test by name).

### E. Default layout & chat placement

- `panes.layout.mail-default` — **[OK]** (seed built 2026-09-16, dfa937946; pinned `BuiltInWorkspaceLayoutTests`) a fresh window now
  seeds a real built-in `PaneList` — `activePaneList` defaults to **Read** — so the window always
  opens in a composed workspace via the F7 path (no more nil-defaulted legacy fallback). The specific
  *Mail-style* composition below is **superseded as the seed by Read** (library+reader beside a
  full-height preview); the sidebar+chat left column and full-height right source hold, but the exact
  centre split described here is the Browse/Read arrangement, not a distinct "Mail" default. Pinned:
  `BuiltInWorkspaceLayoutTests` (Read is the default; one library leaf over reader, beside preview).
- `panes.chat.below-sidebar` — **[BROKEN]** (→ #4705 increment 6) the chat history and its input live in the left
  sidebar beneath the folder tree, in a collapsible split region; the input is attached to
  the chat history. Today the chat prompt sits at the bottom of the centre column, under the
  image/reader, rather than under the chat text.
- `panes.chat.collapsible-split` — **[GAP]** (→ #4705 increment 6) the sidebar↔chat divider drags to resize and
  collapses the chat region when only navigating.
- `panes.library.horizontal-icon-strip` — **[BROKEN/GAP]** (#4732, #1856 — now folded onto this
  milestone, same duplicate request) the library browser renders as a
  horizontal thumbnail strip (icon/list, Mail message-list style) at the top of the centre
  column ("I want the icon view back — horizontal, like in Mail"). #1856 additionally frames
  this as a display-mode alongside grid/list/table/map (`LibraryView+DisplayModes.swift`,
  `LibraryView+TableMapViews.swift`) with its own toolbar/View-menu toggle and per-window
  `@SceneStorage` — the same capability #4732 already tracks here, not a second one.
- `panes.reader.one-or-two-below-browser` — **[GAP]** (#4733) below the browser strip sit one or two
  readers (transcription / summary / metadata), driven by the browser selection.
- `panes.source.full-height-right` — **[GAP]** (#4734) the source image occupies the full-height
  right column by default.

## Known bugs to fix (already observed by the creative director)

1. ~~**Claims don't reset on library change**~~ — **FIXED 5b709aca0** (F5): Claims + Entities
   now key their reload on the library and reset on a switch; pinned by
   `ClaimsLibraryReloadKeyTests`. Built + tested green.
2. ~~**Pin shares across split halves**~~ — **FIXED** (F3, all pane kinds): pin is now
   per-split-half for Reader (was already), Preview (474802124), and Library (070cd1115).
   Preview/Library pin moved into per-sub-pane hosts (`PreviewSplitPaneHost` /
   `LibrarySplitPaneHost`) mirroring the Reader; a monotonic `libraryPinClearToken` carries
   the cross-cutting search-clear to the per-instance library pins. Pure seams
   (`PreviewPanePin`, `LibraryPanePin`); pinned by `PreviewPanePinTests` (6) +
   `LibraryPanePinTests` (7). Built + green.
3. **Preview isn't always there** (F6) — plan==render parity; close the #4525 gap.
4. **Chat prompt is under the image, not under the chat** (`panes.chat.below-sidebar`) — move
   the chat history + input into the left sidebar beneath the folder tree.
5. **No two-of-a-kind panes** (F7) — the enabler for 3 previews side-by-side; the pane-list
   generalization. (Larger, sequenced after the convergence decisions.)

Split-affects-both-columns and shared-zoom are in **Verify-on-build** above, not here — the
code splits per focused slot and holds zoom per-instance, so those need a live repro first.

These are the first wave to pin — each needs a pinning test that asserts the *behavior* (not
the code, per the capability-scrape ruling) and a fix that makes it pass. Delivering the
Mail-style default (§Default composition) is the companion layout work, and falls out almost
free once the pane list (F7) exists — a default is just a starting list.

## Findings (code evidence, 2026-09-13)

Paths relative to `fichero/fichero/`. From a read-only code map; every line verified **at the
time of the audit**. HISTORICAL: F1's second renderer and the symbols it names
(`widescreenPaneRow`, `centerContentRouting`'s raw switch) were deleted 2026-09-17 (#4683). The
findings stand as the record of why the migration was needed, not as a description of the code now.

- **F1 — Two centre renderers.** `Views/Shell/ContentView/Layout/PaneSpec.swift:15-46,78-225`
  (`PaneSpec`, `widescreenPaneSpecs`, `widescreenPaneRow`) runs only in
  `LayoutMode.widescreen`; `Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift:143-213`
  (`centerContentRouting`, a `switch LayoutMode`) is the legacy `.standard`/`.none` path.
  The `.none` branch there (170-180) is **dead** — an earlier `!showsPreviewPane` guard
  (line 154) diverts first.
- **F2 — Three pane vocabularies.** `Views/Shell/PaneVisibility.swift:5-7` (`grid/canvas/reading`)
  vs `PaneSpec.swift:16-20` (`library/preview/reading/chat`) vs
  `Views/Shell/WindowLayout/WindowWorkspace.swift:41-52` (`showLibraryPane/…`).
- **F3 — Pin scope split.** *(FIXED — Preview 474802124, Library 070cd1115: pin moved into
  per-sub-pane hosts `PreviewSplitPaneHost`/`LibrarySplitPaneHost` with pure seams
  `PreviewPanePin`/`LibraryPanePin`; library reset via a monotonic `libraryPinClearToken`.)*
  Reader: per-instance `@State` inside the pane —
  `Views/Reader/Page/ReadingPaneView.swift:131-135` (`isPinned`, `pinnedDocument`, …),
  read at `:167-170`, toggled at `:544-555`; the type doc (`:6-9`) states independence-per-split
  as the goal. Preview: `@State var pinnedPreviewDocument` on `ContentView` —
  `Views/Shell/ContentView/ContentView.swift:60-62`, toggle at
  `ContentView+PreviewPaneHead.swift:116-119`; each split half's head reads the one shared
  property. Library: `@State var pinnedLibrary` on `ContentView` — `ContentView.swift:63-64`.
  Entities/Claims: no pin affordance.
- **F4 — Zoom is per-instance (no shared store).** `ReadingPaneView.swift:136`
  (`@State var webZoom`), `Views/Preview/PDFViewer/PDFPageWithToolbar.swift:38`
  (`@State var zoom = PDFZoomController()`); `SplittablePane.swift:516-521` invokes the
  content closure per slot → distinct `@State`. No `AppStorage`/`SceneStorage`/doc-id-keyed
  zoom store exists. **The CD's "split shares one zoom" is unexplained by the code — LIVE
  REPRO NEEDED** before spec'ing a fix.
- **F5 — Claims not keyed to library.** Entities: `EntitiesLibraryContent.swift:64`
  (`.task { store.loadEntities(…) }`, no `id:`), store is per-library
  (`Models/EntityStore.swift:46-47`, injected `LibraryWorkspaceRoot.swift:96`). Claims:
  `ClaimsLibraryContent.swift:65` (`.task(id: folderId)`), model cached
  `@State … model ?? LibraryClaimsModel(service:)` (`:66`), service captured permanently
  (`LibraryClaimsModel.swift:29-33`); library-wide row has `folderId == nil` both sides of a
  switch (`LibraryView+ContentBranches.swift:215`) so `.task(id:)` never refires.
  `ContentView.handleLibraryChange()` (`ContentView+StateEvents.swift:316-331`) clears
  detail/selection/search/KG-focus but neither KG table.
- **F6 — Plan claims preview content the view won't render.** `PaneContentPlan.swift:82-162`
  vs `ContentView+DetailLayout.swift:226-306` (`previewView` renders only `.library`; comment
  "the remaining #4525 step" at `:298-300`). Also `.none` gate
  (`ContentView+ActionsClaim.swift:68-69`) and collapse order (`Models/LayoutMode.swift:186-207`).
- **F7 — Fixed slots, not a pane list.** `WidescreenPanePlan` = four `Bool`s
  (`Models/LayoutMode.swift:128-135`); `widescreenPaneSpecs` appends one spec per flag
  (`PaneSpec.swift:78-102`); `PaneSpec.Kind` a fixed 4-case enum with an exhaustive
  `kindContent` switch (`:173-225`). A boolean can't count past one → no two-of-a-kind.
  Split caps 2×2 (`SplittablePane.swift:156-166`) but every sub-pane renders the *same*
  content closure → identical-kind panes only. `paneKindOverrides` (`ContentView.swift:65-67`)
  can only trade the reading slot to a 2nd preview, not add a 3rd.

## Test matrix (from the coverage audit)

The pane system's **pure-model** layer is well-tested (`PaneVisibilityTests`,
`PaneContentPlanTests`, `WindowWorkspaceTests` split-routing + snapshots,
`WorkspaceLayoutDefaultsTests`, `ContentViewPersistenceTests`). The gaps are the exact
reliability concerns — each is the first-wave pinning test:

| Concern | Today | Required pinning test (behavior, not source-scrape) |
|---|---|---|
| Split focused-only isolation | routing keys tested, isolation not | splitting pane A does not change pane B's split count |
| Pin under split (F3) | 0 behavior tests (2 source-scrapes) | pin left preview split-half; right half stays live; unpin releases — for Preview/Library like Reader |
| Zoom independence (F4) | 0 tests | zoom one split half; the other's zoom is unchanged (after a live repro confirms the report) |
| Claims reset on library change (F5) | MISSING (both tables) | switch library → Claims (and Entities) show the new library's rows, not stale |
| Plan==render (F6) | plan tested, render-parity not | for every mode the plan marks preview `.content`, the view renders content |
| N-pane / two-of-a-kind (F7) | capped, untested | the pane list can hold two `.preview` entries with different content |
| Convert the seed-write scrape | `WorkspaceLayoutDefaultsTests::testTheSeedAndTheWriteBackAreBothWired` is a baselined scrape | drive the view/store, toggle a pane, assert `WorkspaceLayoutDefaults` was written |

## Verify-on-build (before spec'ing a fix)

Two CD reports are NOT explained by the code as written; confirm empirically on a running
build before treating them as bugs:
- **Shared zoom across a split** (F4) — split a reader/preview, zoom one half, watch the other.
- **Split affects both columns** — the code splits per focused slot in `.widescreen`; if the
  report reproduces, capture which `LayoutMode` and pane it happens in (likely the legacy path).

## Design decisions — RATIFIED 2026-09-13 (creative director)

1. **Generalize to a pane list — YES, after the safe fixes.** (F7) The plan becomes an
   **ordered pane list** instead of four Bools. **A pane entry carries a *kind* AND a
   *scope*** (which library / document / folder it shows), not just a kind — so the list
   can hold **different previews, different readers, or even different LIBRARIES side by
   side** (CD, 2026-09-13: "we want to be able to have different libraries, or different
   previews, or readers"), not merely N-of-one-kind. Enables 3-previews (original · words ·
   reader), heterogeneous compositions, and saved workspaces; the Mail default becomes just
   a starting list. Sequenced *after* F3 (pin) + F6 (plan==render). Open sub-questions: the
   cap (max panes per row); whether 2×2 split stays once a list can add more of a kind; and
   how a pane's scope is chosen/persisted (a per-pane library/document picker). Chat is NOT
   a row pane in this model — it lives inside the sidebar (`panes.chat.below-sidebar`).
2. **Zoom — independent + opt-in sync.** (F4) Each split half zooms alone (matches the
   code); a "sync zoom" toggle links them on request. Still confirm the live repro of the
   "shared zoom" report first, in case there's an actual bug to fix underneath.
3. **Retire the legacy renderer — YES, one renderer.** (F1) Every layout mode routes through
   the pane-list path (`.none`/`.standard` = a shorter list); behavior can't diverge by mode.
4. **Entities & Claims — YES, one view system.** (F5) Shared data-lifecycle, selection,
   reset, pin — differing only in row content + open-target. F5 already aligned their reset.

## Design decisions — RATIFIED 2026-09-14 (creative director)

**Every layout is one workspace.** There is no "bottom preview mode" vs "side preview mode" —
those are the *same* nestable pane list drawn two ways, and the fact that one has pane heads
(breadcrumb, close) and the other doesn't is the F1 two-renderer bug, not a feature. The
reliability north star lands as: **one pane-list model, one renderer, and layouts are just
saved instances of it.** Worked examples the creative director wants expressible (all the same
model, different nesting):

- a table above a reader, beside a tall full-height preview;
- three previews side by side;
- a list at the top with a related-files list to its right, then three previews below it;
- three previews across the top with one long-thin library beneath;
- three previews and a reader, with a long-thin library.

5. **Workspace Manager — a dialog.** A simple manager to **add, delete, and rename** workspaces
   and **assign each a keyboard shortcut, ⌘⌥1 through ⌘⌥9**. Built-in starting workspaces (the
   Mail default, three-up preview, reader+preview) ship as ordinary entries the user can keep,
   edit, or delete — nothing is privileged. Pressing a bound shortcut switches the window's pane
   list to that workspace. This is the surface on top of the F7 pane-list model (a workspace IS
   a `PaneList`, already `Codable`).
6. **Workspaces double as the test fixtures (design-led testing).** Each ratified workspace is a
   named `PaneList` fixture; the tests assert the *spec's* workspace composes and renders as
   specified (kinds, order, split axis, pane heads present), never the code's internals. Adding
   a workspace to the manager adds a fixture; a test that breaks means the renderer diverged
   from the spec, which is exactly the F1 divergence we're closing.
7. **Accessibility is first-class, not a follow-up.** ⌘⌥1–9 workspace switching; full keyboard
   navigation *between* panes (focus ring moves pane→pane) and *within* the focused pane; every
   pane head (breadcrumb, close, kind switch) reachable and labelled for VoiceOver. A workspace
   the keyboard can't drive is not done.

## Existing machinery — inventory 2026-09-14 (what to keep, what to retire)

A read-only code map found the workspace feature is **already LIVE**, not a stub — so F7 is a
*consolidation*, not a build-from-zero:

- **Catalog + persistence exist.** `WindowWorkspace.swift` defines `SavedWindowWorkspace`
  (id·name·savedAt·`WindowLayoutSnapshot`) and `WindowWorkspaceCatalog`; `WindowWorkspaceStore`
  (`.shared`, `@Observable`) persists them to `UserDefaults` (`window.workspaces`). Save / apply
  / remove all work (`ContentView+LayoutChooser.swift` `captureLayoutSnapshot` /
  `applyLayoutSnapshot`).
- **The Workspaces toolbar icon is live.** `ContentView+Toolbar.swift:229` → `workspacesMenu`
  (`ContentView+LayoutChooser.swift:90`), SF Symbol **`rectangle.grid.1x2`**, a populated
  dropdown (Layouts · Split · Built-ins · Saved · Save Current… · Delete · Toolbar Buttons). A
  menu-bar twin exists (`WindowLayoutCommands` → `WorkspaceCommandsSection`).
- **TWO redundant built-in sets — RETIRED 2026-09-15/2026-09-18.** `BuiltInWorkspace`
  (`.reading/.cataloguing/.everything`, with bars+toolbar) was deleted first; `WindowLayoutPreset`
  (`.libraryOnly/.reading/.everything`, visibility-only) and its `WindowLayoutCommands.applyPreset`
  verb were deleted 2026-09-18, confirmed callerless first — there is now ONE built-in catalog,
  `BuiltInWorkspaceLayout` (the five below). Enforced by `WorkspaceSystemBoundaryTests.
  testNoParallelLayoutPresetSystemBesideWorkspaces`.
- **The model split was the core debt — CLOSED 2026-09-18.** Saved workspaces used to persist only
  a `WindowLayoutSnapshot` (six `showXPane` Bools + `splits:[String:PaneSplitCounts]` +
  `paneKindOverrides`) while the F7 model was `PaneList` (Models/PaneList.swift), NOT connected.
  `WindowLayoutSnapshot.paneList: PaneList?` connects them: capture = `activePaneList`, apply =
  assign it, so workspaces, claims, entities, reader and preview all render through the single
  path via the one field a saved arrangement was missing. See `panes.workspace.save`/`.reopen` and
  `workspaces.persist-applied-list` in §Behaviors D. The legacy `paneKindOverrides` WRITE side is
  now dead too (its live consumer, `SplitCommandRouting`, is deleted) — the `Codable` field stays,
  decode-only, for an old snapshot that has it.
- **Dead flags:** `ToolbarVisibilityPlan.showSplitMenu/showLayoutsMenu` (decode-only) and
  `LayoutMode.keyboardShortcut` (unbound metadata) — delete on the way through.

## The built-in workspaces — v2 SHIPPED 2026-09-16 (FIVE, ⌘⌥1–5)

The v1 built-ins (shipped 41880cde9) only show/hide panes. The CD's brief (2026-09-15): make them
**real compositions** — Mail-style and other genuinely useful arrangements grounded in who uses the
app (an archivist browsing; a reader; a transcriber who wants the page image, its word boxes, and an
editor at once; someone on a width-sensitive script who needs those stacked vertically; a collator).
Each workspace is a `PaneList`. The sidebar (with chat beneath) is always present and is NOT a centre
pane. `H[…]` is a horizontal row, `V[…]` a vertical stack.

**SHIPPED (dfa937946, CD live 2026-09-16): the built-in set is FIVE, ⌘⌥1–5.** `BuiltInWorkspaceLayout`
enumerates exactly `read · browse · transcribe · transcribeTall · compare`. **Catalogue and Claims were
dropped** (the cataloguer / KG-research personas), and there is **no separate "Default Layout"** — a
fresh window seeds to **Read** (see the seed changelog below). Inspector is kept as an available
add-on pane, not one of the five defaults. Pinned:
`Tests/Unit/general/Views/Shell/BuiltInWorkspaceLayoutTests.swift`
(`allCases.count == 5`; `compare.defaultSlot == 5`; Read composes exactly ONE library leaf;
Transcribe·Tall is three-long).

| # | ⌘⌥ | Name | Composition | Persona | Built |
|---|---|---|---|---|---|
| 1 | 1 | **Read** | `[ library(docs,table) · reading ]` beside `preview(image)` | reader (default seed) | **[OK]** |
| 2 | 2 | **Browse** | `H[ library(docs,icons) · preview(image) · reading ]` | archivist browsing | **[OK]** |
| 3 | 3 | **Transcribe** | `V[ H[ preview(image) · reading ] · library(icons strip) ]` | transcriber | **[OK]** |
| 4 | 4 | **Transcribe · Tall** | `V[ H[ preview(image) · preview(words) · reading/editor ] · library(icons strip) ]` (three-long over strip) | width-sensitive scripts | **[OK]** |
| 5 | 5 | **Compare** | `V[ H[ preview(image)@A · preview(image)@B · reading ] · library(icons strip) ]` | collation | **[OK]** |

The removed Catalog / Knowledge / Everything workspaces (former #7–9) are **not built**; ⌘⌥6–9 are
free for user-saved workspaces (the slot→workspace map). Their compositions above are retained only as
design history for when the cataloguer / KG-research personas return.

Grounded in the surface inventory (2026-09-15): `preview(words)` = the preview pane with the OCR
word-box overlay on (`OCRGeometryOverlay`, today a global `imagePreview.inlineTextEnabled`);
`library(claims|entities)` = the library pane on the `LibraryContentKind` axis (sidebar-driven today);
`inspector(...)` = the `.inspector()` sibling's `InspectorSection` (source/notes/knowledge/artifacts);
`@A/@B` = `PaneScope.documentId` pins (already in the model); `V[…]` = `SplitAxis.vertical` (already
rendered).

### Model changes the v2 workspaces need (the PaneList migration)

A pane leaf must carry **per-pane configuration**, not just kind + scope — this is the heart of the
migration (CD-approved 2026-09-15):

1. **`PaneKind.inspector`** (new) + a `kindContent` branch that hosts the existing inspector content
   as a centre pane (today it is a `NavigationSplitView` sibling).
2. **Library-pane config on the leaf:** `contentKind` (documents / entities / claims — the existing
   `LibraryContentKind` axis) and `displayMode` (the existing `LibraryLayout`). So one leaf renders
   "library, claims, as a table."
3. **Preview-pane config on the leaf:** `lens` (preview / edit) and a `wordBoxes` overlay flag —
   making today's global `imagePreview.inlineTextEnabled` per-pane, so Transcribe can show a plain
   image beside a word-box image.
4. **Saved workspaces become `PaneList`** (replacing `WindowLayoutSnapshot`'s six Bools), applied by
   setting the window's pane list. Collapse `BuiltInWorkspace` + `WindowLayoutPreset` into these nine.

Shortcuts: a **slot→workspace map** (CD-approved 2026-09-15) — the nine ⌘⌥ slots are one app-wide
mapping the Manager edits; each slot points at exactly one workspace (built-in or saved); no
conflicts by construction; the nine above are the default mapping. The Workspace Manager dialog
(add / delete / rename / rebind slot) is built now, CD to verify visually.

## F7 implementation plan — one renderer (2026-09-14)

Behavior-preserving increments, each build+unit-gated; the CD verifies each visually:

1. **Pure seam [done, then deleted 2026-09-17].** `PaneList.forLayout(mode:showsPreview:showsDocumentGrid:widescreen:)`
   was the bridge from the Bool-driven modes to a `PaneList`; once a workspace was always applied
   it had no production caller and went with the second renderer (#4683). Historical:
   reproduces `centerContentRouting`'s branch structure AS DATA; `.standard` bottom-preview becomes
   a `split(.vertical,[library,preview])`. Unit-tested in `PaneListTests` (mode→composition, the
   "same system" contract that preview is a pane in both side and bottom modes).
2. **One node renderer [done as `paneListRow`; `widescreenPaneRow` deleted 2026-09-17].**
   Original plan: generalize `widescreenPaneRow` into `paneRow(_ list: PaneList)` that
   renders a node recursively — leaf → `kindContent` (its head chrome + `.clipped()`); split →
   H/VStack of children along the axis with the existing `ResizableDivider`. Route `centerContent`
   through `paneRow(PaneList.forLayout(...))` for the non-compact path; the compact reader flow is
   unchanged. Retire the `centerContentRouting` switch and its raw `PlatformVSplitView`. Result:
   bottom preview gains the breadcrumb/close head and the clip, and toggles act in every mode.
3. **Inspector as a `PaneKind`.** Add `.inspector` so #6/#9 compose in the list rather than as a
   `NavigationSplitView` sibling.
4. **Workspaces on `PaneList`.** `SavedWindowWorkspace.layout` gains/derives a `PaneList`; apply
   sets the window's pane list; collapse `BuiltInWorkspace`+`WindowLayoutPreset` into the nine.
5. **Workspace Manager dialog + ⌘⌥1–9** (2026-09-14 ratified): add/delete/rename/bind, keyboard
   + VoiceOver reachable.

## Decisions needed to continue (2026-09-14) — for the CD

The one-renderer and the first six built-in workspaces (⌘⌥1–6) shipped; these block the rest:

1. **The ⌘⌥1–9 shortcut model** (blocks saved-workspace rebinding + the Manager). Two shapes:
   - **(A) per-workspace `shortcutNumber`** — each workspace optionally owns a number; the app
     resolves conflicts. Simple to store, but two workspaces can claim the same key.
   - **(B, recommended) a slot→workspace MAP** — the nine ⌘⌥ slots are a single app-wide
     mapping the Manager edits; each slot points at exactly one workspace (built-in OR saved),
     so there are no conflicts by construction and the built-ins are just the default mapping.
   Today built-ins own ⌘⌥1–6 by list position (a special case of B). Recommend B.
2. **Workspaces #7–9** (Compare, Claims, Entities). Compare needs two preview panes with
   different scopes (only `PaneList` expresses that, not the six-Bool plan); Claims/Entities
   need the library pane's *view mode* to be part of the workspace. Both imply moving saved
   workspaces onto `PaneList` + adding a per-pane view-mode/scope. Ruling needed on that model.
3. **The Manager dialog** — data ops exist (save/remove/rename); the dialog UI is built once
   the CD can verify it visually (RenderPreview is toolchain-blocked in the agent environment).

## Resolved 2026-09-15 (creative director)

- **Save = layout only.** A saved workspace (and each built-in) captures the pane composition +
  per-pane config, NOT the live selection; panes re-fill from context. Pinning a specific
  document (Compare's A/B) is an explicit per-pane opt-in (`PaneScope.documentId`).
- **Magnifier zoom = independent + a sync toggle.** Each pane zooms alone; a "sync zoom" toggle
  links panes in a workspace on request (matches the code). Confirms the 2026-09-13 ruling.
- **Word-boxes default = recognised text inside each box** (proof the transcription in place); a
  pane-head switch drops to outlines-only.
- **Claim/Knowledge subjects = the full set** — people, places, organizations, events, concepts,
  citations, works, dates-as-subjects (supersedes the "richer subject types" open question).

## RATIFIED 2026-09-15 — ONE system, enforced by tests (creative director)

> "Don't have two workspace systems, two rendering systems, etc. We want one system, well done."

The pane/workspace feature shipped as a **half-finished migration** (spec §"Current architecture"):
a legacy Bool-visibility system (`BuiltInWorkspace` presets, `WindowLayoutPreset` "Layouts",
`WindowLayoutSnapshot`, the `showXPane` toggles) running *alongside* the F7 `PaneList` model. Two
systems for one job is the reliability root. This ruling closes it: there is exactly ONE of each,
and a **guardrail test** keeps the second from growing back.

- `workspaces.one-system` — **[RATIFIED → enforced]** A workspace **is a `PaneList`** — built-in or
  saved, there is one model. The built-in defaults are `BuiltInWorkspaceLayout` (**FIVE v2
  compositions as of 2026-09-16, ⌘⌥1–5** — Read · Browse · Transcribe · Transcribe·Tall · Compare;
  Catalogue + Claims dropped); user workspaces are saved `PaneList`s (⌘⌥6–9). The legacy
  `BuiltInWorkspace` enum and the `WindowLayoutPreset` "Layouts" presets are **deleted**, not
  hidden. *Enforced:* `BuiltInWorkspaceSystemTests.noLegacyWorkspaceSystem` — a source guardrail
  that greps the app target and fails if `BuiltInWorkspace`/`WindowLayoutPreset`/`applyBuiltIn`/
  `applyLayoutPreset` reappear (their deletion is also compile-time). One list of defaults in the
  menus, never three competing lists.
- `panes.one-renderer` — **[RATIFIED → enforced, tightened 2026-09-17]** The window centre is
  drawn by ONE path: `paneListRow(activePaneList)`. `activePaneList` is **non-optional** — a
  workspace is always applied — so there is no fallback branch and nothing to fall back to. The
  earlier two-path shape (`paneComposition` for a derived default, `paneListRow` for an applied
  workspace) was deleted (#4683): the derived default had been unreachable since the workspace seed
  landed, and an unreachable second renderer is where drift hides. Deleted with it:
  `PaneList.forLayout`, `WidescreenVisibility`, `widescreenPaneRow`, `paneDivider`,
  `paneContent(for:)`. *Enforced:* `WorkspaceSystemBoundaryTests` asserts the routing file
  contains `paneListRow(activePaneList)` and contains neither `paneComposition(` nor
  `PaneList.forLayout(`, and asserts `activePaneList` is declared non-optional — so reintroducing
  either the second renderer or the Optional that kept it alive fails a test by name.
  *Residue RESOLVED 2026-09-18:* menu Split now routes through `activePaneList.splittingLeaf`
  (#4685; `widescreenPaneSpecs`/`SplitCommandRouting` deleted, confirmed callerless first) and the
  three legacy visibility Bools are DELETED, not merely bypassed (#4687; `paneVisibility` derives
  from `activePaneList.kinds`, so there is nothing left for toolbar/menu state to drift from).
  One renderer, one model — see the 2026-09-18 changelog entry above for the full list.
- `panes.instance-safe` stays enforced by `everyBuiltInIsInstanceSafe` (below) — one system does not
  mean one pane; two same-kind panes are fine, and the structural guard keeps them loop-free.

**Migration order (each increment built + committed before the next):** (1) instance-safety fix;
(2) delete the legacy built-in/preset lists + wire ⌘⌥1–6 to `BuiltInWorkspaceLayout`; (3) saved
workspaces store a `PaneList`, the window is *always* a `PaneList`, the Bool-visibility path retired;
(4) split/close act on the focused leaf instance (`panes.split.focused-only` /
`panes.close.this-pane-only`). Tests grow with each step and cite the behavior id they pin.

### Increment 3 — RATIFIED 2026-09-15 (evening, CD): PaneList is the ONE split model

> "We might want 3 columns, one long below — or even four columns and 2 below. And remember: one
> system, not multiple systems."

- `workspaces.pane-list-is-the-split-model` — **[RATIFIED]** the window is ALWAYS a `PaneList`, and
  ALL splits — including the rich compositions the CD wants (3 columns over one wide pane; 4 columns
  over 2) — are expressed by `PaneList`'s NESTED splits, e.g. `3-cols-over-1-wide` =
  `split(.vertical, [ split(.horizontal, [a, b, c]), d ])`; `4-over-2` =
  `split(.vertical, [ split(.horizontal, [a,b,c,d]), split(.horizontal, [e,f]) ])`. Nesting already
  expresses everything `SplittablePane`'s in-slot 3-per-axis / 2×2 grid did, and more, so the head
  "+" and the window Split commands must build these into the `activePaneList` (`splittingLeaf` +
  friends), NOT the leaf's own `SplittablePane`. The `SplittablePane` split mechanism is then RETIRED
  — its 3-per-axis/grid model is the "second system" this consolidation removes. One model, one place
  splits live, and a workspace saves exactly what you see.
- Consequence: `PaneNode` may need equal-flex weights (or explicit ratios) so "one long below" reads
  as a greedy row under three short columns — the height policy `verticallyFramedPane` fakes today
  becomes per-node data on the `PaneList`. Split/close then act on the focused leaf uniformly
  (close already does, via `\.paneCloseAction` → `removingLeaf`; **2026-09-18: the window Split
  commands now do too**, via `activePaneList.leafIDs(of: kind).first` → `splittingLeaf` — a
  plain function call resolving `focusedPane ?? paneFocusHint`, not a per-leaf environment seam
  like `\.paneCloseAction`'s, since the menu commands aren't inside a specific leaf's own view
  subtree the way the pane head's close button is. See `panes.split.focused-only` for the
  Compare instance-precision caveat this leaves open).

### Pane-linkage color coding — IDEA 2026-09-15 (CD), for design

- `panes.linkage-color` — **[GAP/IDEA]** (#4666) In a multi-column workspace (Compare especially) it isn't
  obvious which library/list drives which preview/reader. Idea: tint each linked pane GROUP with a
  soft background color — the Xcode-theme-picker model (colored row bands) — so "this list → this
  preview → this reader" reads at a glance. Each `PaneScope` group (a column's library + the panes
  that follow its selection) shares one tint; unlinked/independent panes stay neutral. Needs a design
  pass: how tints are assigned (per column? per scope link?), how quiet they stay (Golden-Gate
  restraint — a wash, not a highlight), and dark-mode behavior. Captured from the CD's Xcode
  theme-picker reference.

## Open questions (for the design lead)

- **Naming.** What do we call editing directly inline within a pane, where each pane may
  carry different settings? ("inline edit mode" / "live edit" / something else?)
- **Richer subject types.** Claims today anchor people / places / organizations (and the
  model already has event / concept / citation / other). Should the claims tables and
  subject pickers surface the full set — and are there types beyond the current enum the
  creative director wants (objects, works, dates-as-subjects)? (Ties `kg-interactions`
  claim-richness.)
- **Sync granularity.** Is magnifier sync a per-window toggle, a per-pair binding, or a
  per-pane opt-in?
- **Workspace scope.** Does a saved workspace capture a live selection (these four people)
  or only the pane layout, rehydrating selection from context?

## CD runtime review 2026-09-15 (live build) — split/close not pane-scoped

Creative director, running the app (the one-renderer + old split/close wiring still in place):

- `panes.split.focused-only` — **[FIXED, model + isolation]** Splitting one pane splits ONLY that
  pane (pinned by PaneListTests "splitting a pane splits ONLY that pane"; the live per-slot
  `@SceneStorage` isolation landed 2026-08-24). **RESOLVED 2026-09-18** (was "Open — increment 3
  design question" below): the toolbar/menu-bar Split commands now route through
  `activePaneList.splittingLeaf(id, axis:)`, not the leaf's own `SplittablePane` mechanism — a split
  made this way IS stored in the `PaneList` and DOES save with the workspace. See the canonical
  entry in §Behaviors A (above) for the exact routing and the Compare instance-precision caveat
  that remains open.
- `panes.close.this-pane-only` — **[FIXED 2026-09-15, applied path]** Closing a pane in an applied
  workspace now removes THAT leaf from the stored `PaneList` (`removingLeaf(id)`, which collapses a
  singleton split to its survivor and removes a top-level pane in one operation) — never the whole
  row. Wired through a `\.paneCloseAction` environment seam that `PaneHead`'s X prefers over the
  legacy scope-shared close (commit ba575a64e; model pinned by PaneListTests). **UPDATE 2026-09-16
  (dfa937946): the always-a-`PaneList` step landed — `activePaneList` seeds to Read, so the window is
  always the stored `PaneList` and the legacy visibility-Bool path no longer renders.** Split-then-
  close-both is also fixed (the PaneHead close-ladder now collapses an active in-slot split by one
  before removing the whole leaf). **UPDATE 2026-09-18: the split side is now symmetric with close**
  (see `panes.split.focused-only` above) — both act on the stored `PaneList` by leaf id.
- `panes.head.consistent-minimal` — **[PARTIAL]** (implemented, unpinned; #4796) (fixed
  2026-09-16, dfa937946) every pane head is now the same consistent liquid-glass style with
  no per-kind chrome: `PaneFilterBar.showsSeparator` defaults OFF (no Library/Reader
  hairline), and the ChatView standalone `Divider` was removed. `\.isSolePane` additionally
  collapses the head's close control when a pane is the only one. (The preview's minimal,
  line-less, tight style is now the shared one — Golden-Gate restraint.) No test found
  pinning `showsSeparator`'s default or `isSolePane`'s effect — tracked in #4796.
- `panes.inspector.icon-tabs-and-empty-state` — **[GAP]** (#1854) the right-inspector's own tab
  bar should be compact SF-Symbol icon tabs (Xcode-style), and an inspector with nothing
  selected should show a centered "No Selection" placeholder rather than blank or stale
  content. Verified NOT built: `DocumentInspector+TabBar.swift:70` renders
  `Text(facet.rawValue)` — text tabs, not icon tabs — and no "No Selection"/empty-state view
  was found anywhere under `Views/Inspector/`. Distinct from `panes.head.consistent-minimal`
  above, which covers chrome CONSISTENCY (no per-kind hairlines/dividers) — this behavior is
  about the tab bar's own presentation and the empty state specifically, neither touched by
  that fix.
- `panes.head.drag-to-rearrange` — **[GAP, requested]** (#4748) Dragging a pane by the icon at the LEFT of
  its head (the kind/preview icon) should let the user move that pane elsewhere in the composition
  (reorder / re-nest). A direct-manipulation complement to the pane list. New.
- `panes.head.inspector-always-visible` — **[GAP]** (#1199) an inspector column should be a
  stable, always-present rightmost pane across every view (library, reading, KG graph,
  workflow), never disappearing so a user loses their place. Verified NOT true today:
  `ShellLayoutPolicy.swift` takes an `inspectorVisible: Bool` and a `collapseInspector` policy
  that together hide the inspector below a width threshold (`:80-127`) — the inspector is
  conditionally hidden by design, not a bug that slipped through. **Open design tension, not
  decided here:** under the current "one system, every pane is a `PaneList` leaf" architecture
  (`workspaces.one-system` above), the inspector is itself just one pane kind among many — a
  user can already close or rearrange it like any other pane. Whether "always visible, never
  hidden" survives that architecture, or whether the issue's 2026-06-08 framing predates it and
  needs re-scoping to "never auto-collapsed below a size threshold" specifically, is a real
  open question — reshaped, needs maintainer triage, not decided by this pass.
- `panes.head.names-its-own-window` — **[BROKEN]** (#4860) a pane head names the library ITS
  OWN window (or, once panes carry their own scope, its own pane) is showing — never an
  app-wide pointer that any window could have last written. Verified at HEAD
  (`git show HEAD:.../LibraryView+PaneHead.swift`): the root crumb is built from
  `LibraryManager.shared.currentLibraryId` (`:63`, `:77`), a property on the app-wide manager
  written by app-level events (initial window open, the File menu, AppleScript, one window
  action) — never by a sidebar selection in a specific window. With two window tabs on
  different libraries, the crumb shows whichever window wrote last, not the library that
  window is actually displaying — the same singleton-pointer mistake
  `kg.entity.focus-is-per-window` (`kg-entity-inspector.md`) fixes for entity focus, found the
  same day. No fix in flight for this file as of this pass. A deliberate app-level use of
  `currentLibraryId` (which library File > New targets) is out of scope for this behavior and
  should stay explicit, not folded into the same fix.

- `panes.instance-safe` — **[FIXED 2026-09-15]** a workspace may mount more than one pane of the
  same kind in one window (Compare: two previews, two readers, two libraries). Applying it used to
  beachball: repeated `makeNSView`, "Fetched 8 artifacts / Loaded 0 annotations" repeating, a
  32-second sidebar→content update.
  **Root cause (confirmed, not the earlier selection/shared-state hypothesis):** a window-scoped
  `focusedSceneValue` admits exactly ONE publisher per key. Each pane-list leaf mounts its own
  unsplit `SplittablePane`, so two same-kind leaves both have `isSecondarySplitPane == false` and
  both publish the SAME scene keys (`\.librarySelectAll`, `\.readerLens`, `\.imageZoomActions`, …)
  every frame → SwiftUI's *"FocusedValue update tried to update multiple times per frame"* fault →
  recursive scene-graph invalidation → the remount storm. It's the exact fault the intra-`SplittablePane`
  library split already fixed via `\.isSecondarySplitPane` (LibraryView+KeyboardShortcuts,
  `applyFocusedActions`); the applied-workspace path defeated that guard because each leaf is its own
  pane, never marked secondary.
  **Fix:** `PaneList.secondaryLeafIDs()` flags every leaf whose kind already appeared earlier in
  traversal order; `PaneSpec.paneNodeView` injects `.environment(\.isSecondarySplitPane, true)` on
  those, and the reader / image-preview / image-editor publishers now gate their `focusedSceneValue`
  on the flag (library already did). Only the PRIMARY of each kind publishes; the duplicates render
  content only. Compare ships in its full designed form again.
  **Completion (88ad63eea):** a duplicate leaf mounts its own unsplit `SplittablePane`, whose primary
  re-published `isSecondarySplitPane = false` and defeated the flag — so `SplittablePane` now ORs an
  inherited-secondary flag into every `splitPane` (`isSecondary || inheritedSecondary`), keeping a
  duplicate leaf's whole subtree secondary. Without this the flag never reached the publishers and the
  loop returned. Runtime-confirm with a ⌘R on Compare (env propagation isn't unit-testable).
  **Layout-recursion crash also fixed (2026-09-16, dfa937946):** `WorkspaceSplitStack` stacked a
  `frame(width: fixed)` + `frame(maxHeight: .infinity)`, feeding an unbounded proposal into nested
  AppKit panes → infinite `_layoutSubtree` recursion. Rewritten with `GeometryReader` + clamp + a
  single per-child frame. The Transcribe/Compare library strip is pinned to 72pt via
  `PaneConfig.paneExtent` while content flexes. Pinned by `PaneInstanceIndependenceTests` +
  `BuiltInWorkspaceLayoutTests` (film-strip pin).

**Testing this class (design-led answer, "why can a test do these"):** the fault is a **Scene-level
focused-value collision**, and where it lives dictates the test:
1. **Structural DATA guard (the guardrail — have it now):** the loop is deterministic from the
   `PaneList` shape, so a pure unit test asserts instance-safety at the model level —
   `BuiltInWorkspaceLayoutTests.everyBuiltInIsInstanceSafe`: among the leaves NOT flagged secondary
   (the publishers), each kind appears at most once. A default that would loop fails here before it
   can ever render. `compareFlagsDuplicatesSecondary` pins that Compare marks one of each kind
   secondary. Fast, deterministic, and immune to the arm64e canvas bug.
2. **XCUITest apply-workspace-and-stay-responsive (the only runtime reproduction):** apply each
   workspace against a real `WindowGroup` Scene, then assert a follow-up interaction completes within
   N seconds (a beachball fails it). Belongs in the click-around leg.
   **NOT `ImageRenderer`/`#Preview` (corrected):** a snapshot render has no Scene and no
   `@FocusedValue` environment, so it CANNOT reproduce a "multiple updates per frame" fault — a
   render-with-timeout would pass green while the app hangs. Snapshots are the wrong tool for this
   class; the structural guard is the right one.

These are per-instance-state defects (spec §"Per-instance pane state for every kind", F3): split
count and close must key on the pane's own slot, resolved from `focusedPane`, not a window- or
row-shared coordinator. Fix design-led: add the failing pinning test (splitting pane A leaves pane
B's split count unchanged; closing pane A leaves the row intact) BEFORE the fix. The wiring of the
six workspaces (apply + ⌘⌥1–6 + Manager) rides on the same per-instance renderer, so this is fixed
first.

## MCP-controllable layout — RATIFIED 2026-09-15 (CD)

The pane layout must be **adjustable from MCP**, not just the SwiftUI UI — because a workspace IS a
`PaneList` (Codable), the same data an agent would send (spec [[agent-chat-model-is-a-user]],
[[one-audited-action-layer]]). So the window's current pane list lives in an **observable, settable
store** (one endpoint the UI mutates), and MCP exposes typed tools over it:
- apply a named built-in workspace (`BuiltInWorkspaceLayout`) or a raw `PaneList` to a window;
- split / close / reorder a specific pane (by slot) — the same per-instance operations the UI does;
- read the current pane list back (so an agent can see the composition it's arranging).
This makes the layout scriptable and testable end-to-end (the cross-surface invariant: UI == MCP),
and is why the per-instance split/close fix matters for BOTH surfaces at once.

## Preview harness

`WorkspaceLayoutPreview` (`fichero/fichero/Views/Shell/WindowLayout/WorkspaceLayoutPreview.swift`,
`#if DEBUG`) renders every `BuiltInWorkspaceLayout` as a labelled mini window from the real
`PaneList` data — the fast, no-boot canvas surface for verifying and screenshotting the built-in
compositions (spec template §"Preview harness"). Its `#Preview` "Workspaces — the defaults"
is the source for the manuals' workspace screenshots. (As of 2026-09-16 the built-in set is FIVE,
⌘⌥1–5.)

## Cross-references

- `kg-entity-inspector.md` — the entity pane's statements → source model.
- `kg-tables.md` / `kg-interactions.md` — the entities/claims tables this view system hosts;
  claim richness and the shared interaction verb set.
- `segment-representations.md` — the words/transcription representation that
  `panes.words.fill-bounding-box` renders into segment geometry.
