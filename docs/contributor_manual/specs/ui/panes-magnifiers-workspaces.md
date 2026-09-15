# Panes, Magnifiers & Workspaces — Design Spec

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

- `panes.chat.toggle-in-sidebar-top` — **[GAP]** the chat show/hide toggle should sit at the
  TOP of the sidebar, to the LEFT of the sidebar (panel) button — not the sparkles button in
  the main toolbar.
- `panes.sidebar-button.in-sidebar-section` — **[GAP]** the sidebar toggle button belongs IN
  the sidebar's own top-left section (Xcode-style), not floating in the main window toolbar's
  left group.
- `panes.split.asymmetric` — **[GAP/BROKEN]** splitting a preview vertically then horizontally
  makes a **2×2 grid of 4**; the CD wants asymmetric nesting ("2 over 1" — two panes on top,
  one below). The current split caps at a symmetric 2×2 (`SplittablePane.swift:156-166`) and
  every sub-pane renders the same content. Needs nested/asymmetric split (part of F7).
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

### Post-F7 design refinements (CD, 2026-09-14) — capture, revisit after F7

- `panes.kg.select-shows-item-inspector` — **[GAP, post-F7]** clicking a claim or entity row
  auto-opens the full **document inspector** (with its source) today (works, but heavy). The
  CD wants selection to instead show a **focused inspector for THAT claim/entity** — the
  item's own inspector, not the whole document+source surface. (Ties `kg-entity-inspector`;
  a claim inspector is the claim-side equivalent.)
- `panes.kg.clickable-lists-and-sidebar` — **[GAP, post-F7]** richer click-through
  interactions in the claims/entities lists AND the sidebar (click things to act/navigate).
  Deferred by the CD until F7 lands.
- `panes.content-column-under-sidebar` — **[BROKEN, F7]** (screenshots confirm) the content
  column starts at the window's LEFT EDGE (x=0) and runs UNDER the sidebar: with the sidebar
  shown, the leftmost columns are covered; hide the sidebar and the full content appears. CD
  2026-09-14: this is NOT KG-specific — **Claims, Entities, workflows, and images all do it**,
  so it's the general content-column placement in the renderer, not a per-view bug. The column
  isn't reserving the sidebar's width. An F7 issue (one renderer that lays the content column
  out consistently for every view).
- `panes.vertical-no-breadcrumb` — **[BROKEN, F7]** the vertical split/pane has no breadcrumb
  bar (the horizontal one does). Another renderer-consistency gap → F7.
- `panes.kg.filter-targets-active-view` — **[BROKEN]** two disconnected entity-filter controls:
  the main view (`EntitiesLibraryContent`/`ClaimsLibraryContent`) uses a LOCAL `@State filterText`,
  while the inspector + ontology surfaces read the shared `EntitySearchState` bus (a `@State` on
  ContentView). So the bottom-toolbar "Filter Entities" (which drives the bus) filters the
  INSPECTOR's entity digest, not the clicked main list. One filter must target the active view.
  (Another KG-vs-inspector divergence → F7 one-view-system.)

### Reliability sweep (same-class latent bugs, 2026-09-13 overnight) — F7/NEEDS-CD

A sweep for the same bug class as the fixed findings surfaced deeper, design-entangled
defects (the toggle half of the CD's "can't turn preview/library/reader on or off"):

- `panes.toggles.inert-outside-widescreen` — **[BROKEN, F1/F7]** the Preview/Reader/Chat
  toolbar toggles are **no-ops in `.standard`/`.none` layout modes**: `centerContentRouting`
  (`ContentView+SidebarLayout.swift:170-197`) reads only `showDocumentGrid`, never
  `showDocumentCanvas`/`showReadingPane`/`showChatPane` — those flags are honored ONLY by
  the widescreen pane-list path. Worse, turning a pane ON force-sets
  `currentLayoutMode = .widescreen` (`ContentView+ActionsUI.swift:86-102`) — an unrequested
  reflow riding on a toggle; turning OFF is just inert. This is the two-renderer divergence
  (F1); the honest fix is F7 (one renderer, all modes honor the pane list), OR a CD ruling on
  what a toggle should DO in non-widescreen. Testable seam: a pure
  `visiblePanes(layoutMode:showDocumentGrid:showDocumentCanvas:showReadingPane:showChatPane:)`
  whose result must change when EACH flag flips, for EVERY LayoutMode (fails today for
  `.none`/`.standard`).
- `panes.dead-toggle-policy` — **[BROKEN, cleanup]** `ReadingWorkspacePaneTogglePolicy`
  (`Models/LayoutMode.swift:237-253`) documents the exact intended behavior for the above
  ("a toggle from None/Standard enters the widescreen workspace and shows that pane") but has
  **zero call sites** — the real toggle path reimplements only its ON-half inline. A second
  "documented policy isn't the one running" instance (after the dead
  `PaneContentPlan.plan(entitySelection:)`). Resolve WITH the above: wire it (covers OFF too)
  or delete it — not before the direction is decided.

**These confirm the reliability root is F1/F7:** the toolbar controls promise pane management
the legacy renderer doesn't deliver. The reliable fix is one composition path (F7), which is
why "make it reliable so I can experiment" and "generalize to a pane list" are the same task.

**The 2-column target (CD, restated):** LEFT column = the browser (library / entities / claims)
on top with a reader beneath it; RIGHT column = the preview (source image). Chat in the sidebar.
This is the Mail default below, expressed in the eventual pane-list model.

## F7 implementation plan (the reliability generalization) — for CD review

F7 is the one change that makes the pane system reliable AND lets you experiment with
layouts. It subsumes the toggle-inertness (#1), the dead policies (#2), the
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

- `panes.split.focused-column-only` — **[BROKEN]** splitting a pane (vertical or
  horizontal) splits the **focused** pane, not every column at once. Today a vertical split
  applies to both columns rather than the one selected.
- `panes.split.independent-mode-per-pane` — **[BROKEN]** each pane holds its own view mode;
  changing one pane to Entities or Claims does not clear or convert the others. Today
  switching a pane's node-type to entity/claim in the entities view removes them from the
  other panes.
- `panes.open-view-arbitrarily` — **[GAP]** any pane can be set to any view mode (source /
  words / entities / claims / graph / inspector) directly, without routing through a
  document selection. Today there is no way to open an entity or claim view arbitrarily in
  a window.
- `panes.compose-three-plus` — **[GAP]** a window supports three or more panes, and any
  pane may hide its image while another shows it.

### B. Magnifier & synchronized zoom

- `panes.magnifier.follow-mouse` — **[GAP]** a pane's bottom magnifier bar can track the
  pointer, magnifying the region under the mouse.
- `panes.magnifier.per-pane-open-state` — **[GAP]** each pane's magnifier opens and closes
  independently — one pane magnified while another is not.
- `panes.zoom.sync-across-panes` — **[GAP]** when synchronization is on, zoom/magnification
  in one pane drives the corresponding region in the others (original ↔ words), so the loupe
  is shared; sync is toggleable, off by default.
- `panes.words.fill-bounding-box` — **[GAP]** on request, transcribed words expand to fill
  their segment's bounding box, occupying the same geometry as the underlying ink (ties
  `segment-representations` — the `text` representation rendered into the segment anchor).

### C. Unified entity ↔ claims view system

- `panes.kg.one-view-system` — **[BROKEN]** the entities view and the claims view are the
  same pane-system view, sharing selection grammar, split, magnifier, and workspace
  persistence. Today they are separate implementations that behave differently.
- `panes.kg.library-change-resets` — **[OK]** (fixed 5b709aca0) switching the active library
  resets the claims AND entities tables to the new library's data — Claims key `.task` on a
  composite `library|folder` key and rebuild the cached model on a library switch; Entities
  key on `ObjectIdentifier(store)`. Pinned:
  `Tests/Unit/general/Views/Library/ClaimsLibraryReloadKeyTests.swift`.
- `panes.entity.sources-pane` — **[GAP]** an entity pane can show **all source pages** the
  entity appears on — scroll through them, see the same name across four documents, judge
  whether it is one person. (An entity is a name; its statements/sources are where it
  lives — see `kg-entity-inspector`.)
- `panes.claim.sources-pane` — **[GAP]** a claim (or a page's set of claims) can show its
  source pages in a preview pane, each anchored to the passage.

### D. Workspaces

- `panes.workspace.save` — **[GAP]** a pane composition (which panes, their modes, split,
  sync, and current selection scope) is saveable as a named workspace.
- `panes.workspace.reopen` — **[GAP]** reopening a workspace restores its panes, modes, and
  layout. (Ties the related-entities → sources → inspector composition in the Intent.)

### E. Default layout & chat placement

- `panes.layout.mail-default` — **[GAP]** a fresh window opens in the Mail-style default:
  sidebar+chat (left) · library-browser-top + reader(s)-bottom (centre horizontal split) ·
  full-height source (right).
- `panes.chat.below-sidebar` — **[BROKEN]** the chat history and its input live in the left
  sidebar beneath the folder tree, in a collapsible split region; the input is attached to
  the chat history. Today the chat prompt sits at the bottom of the centre column, under the
  image/reader, rather than under the chat text.
- `panes.chat.collapsible-split` — **[GAP]** the sidebar↔chat divider drags to resize and
  collapses the chat region when only navigating.
- `panes.library.horizontal-icon-strip` — **[BROKEN/GAP]** the library browser renders as a
  horizontal thumbnail strip (icon/list, Mail message-list style) at the top of the centre
  column ("I want the icon view back — horizontal, like in Mail").
- `panes.reader.one-or-two-below-browser` — **[GAP]** below the browser strip sit one or two
  readers (transcription / summary / metadata), driven by the browser selection.
- `panes.source.full-height-right` — **[GAP]** the source image occupies the full-height
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

Paths relative to `fichero/fichero/`. From a read-only code map; every line verified.

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
- **TWO redundant built-in sets — RETIRE the overlap.** `BuiltInWorkspace`
  (`.reading/.cataloguing/.everything`, with bars+toolbar) and `WindowLayoutPreset`
  (`.libraryOnly/.reading/.everything`, visibility-only) overlap by name and intent. This is the
  "old system" to remove: collapse both into ONE built-in catalog (the nine below).
- **The model split is the core debt.** Saved workspaces persist a `WindowLayoutSnapshot` (six
  `showXPane` Bools + `splits:[String:PaneSplitCounts]` + `paneKindOverrides`), while the F7
  model is `PaneList` (Models/PaneList.swift). **They are not connected.** F7 = a saved
  workspace becomes a `PaneList` (already `Codable`), applied by *setting the window's pane list*,
  which the one renderer draws — so workspaces, claims, entities, reader and preview all render
  through the single path.
- **Dead flags:** `ToolbarVisibilityPlan.showSplitMenu/showLayoutsMenu` (decode-only) and
  `LayoutMode.keyboardShortcut` (unbound metadata) — delete on the way through.

## The best nine workspaces — PROPOSED 2026-09-14 (⌘⌥1–9), for CD ratification

One built-in catalog, a spectrum browse→read→close-read→analyse→everything. Each is a `PaneList`
(top-level nodes = a horizontal row; a `split` nests along its axis). ⌘⌥1–9 are all free today.

| # | Shortcut | Name | Pane list (composition) |
|---|---|---|---|
| 1 | ⌘⌥1 | **Library** | `[library]` — the list alone, full width (browse) |
| 2 | ⌘⌥2 | **Reader** | `[library · reader]` — list beside the transcription (the Mail default) |
| 3 | ⌘⌥3 | **Source** | `[library · preview]` — list beside the full-height page image |
| 4 | ⌘⌥4 | **Close Reading** | `[library · preview · reader]` — original · image · words, side by side |
| 5 | ⌘⌥5 | **Compare** | `[library · split(h,[preview(A) · preview(B)])]` — two sources, different scopes |
| 6 | ⌘⌥6 | **Cataloguing** | `[library · preview · inspector]` (+ workflow bar) |
| 7 | ⌘⌥7 | **Claims** | `[claims · preview]` — claims table beside the source of the selected claim |
| 8 | ⌘⌥8 | **Entities** | `[entities · preview]` — entities table beside its source pages |
| 9 | ⌘⌥9 | **Everything** | all panes on |

Notes: (a) #7/#8 make claims & entities *first-class workspaces* rendered by the one path, not
bespoke screens (spec §"Entities and Claims are one view system"). (b) `inspector` (#6/#9) is a
pane kind the model must gain — today it is a `NavigationSplitView` sibling, not a `PaneKind`;
folding it in is part of "one path". (c) The Workspace Manager dialog (2026-09-14 ratified) lets
the CD add/delete/rename these and rebind the ⌘⌥N keys — the nine are defaults, not fixtures set
in stone. Each also seeds a design-led test fixture.

## F7 implementation plan — one renderer (2026-09-14)

Behavior-preserving increments, each build+unit-gated; the CD verifies each visually:

1. **Pure seam [done, this pass].** `PaneList.forLayout(mode:showsPreview:showsDocumentGrid:widescreen:)`
   reproduces `centerContentRouting`'s branch structure AS DATA; `.standard` bottom-preview becomes
   a `split(.vertical,[library,preview])`. Unit-tested in `PaneListTests` (mode→composition, the
   "same system" contract that preview is a pane in both side and bottom modes).
2. **One node renderer.** Generalize `widescreenPaneRow` into `paneRow(_ list: PaneList)` that
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

## Cross-references

- `kg-entity-inspector.md` — the entity pane's statements → source model.
- `kg-tables.md` / `kg-interactions.md` — the entities/claims tables this view system hosts;
  claim richness and the shared interaction verb set.
- `segment-representations.md` — the words/transcription representation that
  `panes.words.fill-bounding-box` renders into segment geometry.
