# Reader View — Design Spec

> Milestone: reader-view (GitHub #313)
> Manual: TBD — the user manual needs a "Reading a document" section: the Page/Knowledge/Notes
> tabs, what each Knowledge sub-mode (Statements/Entities/Claims/Graph/Timeline/Map/Related)
> shows, and that clicking a statement reveals its source passage without losing your place.

> Design-led spec (Testing Constitution). The creative director owns the intent; tests
> enforce it; code makes them pass. One line per behavior, each cited by its pinning test.
> **Status: DRAFT — PASS 1 of 2** (built behaviors only, grounded in disk 2026-09-18; the
> fold-in of the legacy "Reader View - Page" milestone's issues, and the 14 issues from the
> `library-view-modes.md` ledger waiting on this spec, is PASS 2 — a fold plan follows this
> spec's own behaviors, no issues moved yet).
> Tags: **[OK]** behaves this way today · **[PARTIAL]** implemented, not fully verified/tested
> · **[BROKEN]** regression, code contradicts the line · **[GAP]** intended, never built.

## Intent (the design)

The Reader is one of the three surfaces the standing rule protects from ever merging into
each other: **Preview, Reader, and Inspector never merge** — Preview is the quick look, the
Reader is the WebKit-hosted, page-by-page reading surface, and the Inspector is curation and
metadata. This spec covers the Reader's OWN internal structure only: what tabs it has, what
each tab shows, and how a click on one surface reaches another without losing your place.

The Reader collapses what used to be ~10 separate WebKit modes into three top-level tabs —
**Page** (read the source), **Knowledge** (explore what we know), **Notes** (the human
reading layer) — with the Knowledge tab further split into native sub-modes (Statements,
Entities, Claims, Graph, Timeline, Map, Related). A single **lens** enum
(`ReaderLens`) is the one user-facing inventory of every surface that actually exists; the
two-enum split beneath it (`ReaderTab` for the top-level tab, `KGSurfaceTab` for the
Knowledge sub-mode) is internal vocabulary the lens maps onto — one user-facing list, two
internal switches, no third source of truth. This spec does not cover the Library's own view
modes (`library-view-modes.md`) or the Preview pane; a lens/tab existing in the enum is a
promise that its surface renders, not a description of the Library or Preview.

**Ratified rulings honored here, not restated:** `modes-to-panes.md`'s
`m2p.reader-consults-the-plan` — the Reader pane renders whatever
`PaneContentPlan.plan(for: viewMode).reader` decides, never routing off a resolved `Document`
alone; and that same spec's "renditions per surface" matrix (§"Selection (`AppViewMode`) |
Library | Source/Preview | Reader | Inspector"), which is the authoritative answer for what
each SELECTION KIND shows in the Reader — a workflow's run log, a chat's document, an
entity/claim row's readable paragraph (still GAP there, see below), and so on. This spec is
downstream of that matrix for document selections specifically; it does not re-litigate which
selections reach the Reader at all.

**`kg-readable-representation.md`'s `kg.read.lives-in-reader` ruling** — the entity biography
paragraph is DESIGNED to live in the Reader, not the Inspector — is cited, not restated: it
remains **[GAP]** there today (the paragraph still renders in the Inspector,
`DocumentInspector.swift:207`). This spec's own Statements lens is the Reader-side surface
that ruling will eventually redirect into; see section D below for the plain statement of the
Statements/Claims overlap the maintainer asked about.

Surfaces: `ReaderLens` (`Views/Reader/Surfaces/ReaderLens.swift`), `ReaderTab`
(`Views/Reader/Surfaces/ReaderTab.swift`), `KGSurfaceTab`
(`Views/Reader/Knowledge/DocumentKGSurface.swift`), `DocumentKGWebPane` (the WebKit host for
Transcript/Statements), `DocumentKGSurface` (the native-vs-WebKit dispatcher for the
Knowledge tab), `PaneContentPlan.ReaderPageRoute`/`ReaderSubject`
(`Views/Shell/PaneContentPlan.swift`), `ContentView+SourceNavigation.swift`
(`sourceRevealDocument`), `ReaderPassageFocus` (`Views/Reader/Page/ReaderPassageAnchor.swift`).

## Behaviors (each → one pinning test)

### A. The lens is the one inventory; two internal switches, no third source of truth

- `reader.lens.every-lens-maps-to-a-surface-that-exists` — **[OK]** every `ReaderLens` case
  maps to a `ReaderTab` (via `.tab`) and, for the Knowledge lenses, a `KGSurfaceTab` (via
  `.representation`) — a lens existing is a promise the surface renders, not aspirational
  naming. Verified at HEAD: `ReaderLens.swift` has exactly nine cases (page, statements,
  entities, claims, graph, timeline, map, related, notes); the deliberate absence of a
  "Translation" lens is stated in the enum's own doc comment ("a lens that goes nowhere is
  the menu lying"). Pinned (file `fichero/Tests/Unit/general/Views/Reader/
  ReaderLensInventoryTests.swift`, suite `ReaderLensInventoryTests`):
  `ReaderLensInventoryTests.lensesAreAnInventory`,
  `ReaderLensInventoryTests.noLensGoesNowhere`.
- `reader.lens.round-trips-tab-and-representation` — **[OK]** `ReaderLens.lens(for:
  representation:)` is the exact inverse of `.tab`/`.representation` — restoring saved state
  or a menu-bar selection lands on the same row the pane head shows, and every knowledge lens
  names a DISTINCT `KGSurfaceTab` (no two lenses silently collapse onto one sub-mode). An
  unknown sub-mode falls back to `.entities` rather than crashing. Pinned (same file, suite
  `ReaderLensInventoryTests`): `ReaderLensInventoryTests.lensesDoNotCollide`,
  `ReaderLensInventoryTests.lensRoundTrips`,
  `ReaderLensInventoryTests.unknownRepresentationFallsBack`.
- `reader.head.is-the-one-lens-selector` — **[OK]** the Reader's own top-tab bar was retired
  (R3, 2026-08-23) in favor of the pane head's lens selector — the head and the menu bar read
  ONE published lens, not two independent pickers that could disagree. Pinned (same file,
  suite `PaneHeadWiringGuardTests`): `PaneHeadWiringGuardTests.tabBarRetired`,
  `PaneHeadWiringGuardTests.oneBindingRenderedTwice`.

### B. Every Knowledge sub-mode is mounted, not a stub

- `reader.knowledge.every-sub-mode-is-mounted` — **[PARTIAL]** (→ #4867) `DocumentKGSurface`'s dispatcher
  mounts a REAL view for all eight `KGSurfaceTab` cases, none a placeholder: Transcript and
  Statements (`.digest`) render inside the shared `DocumentKGWebPane` WKWebView (kept alive
  across tab switches via a ZStack + opacity swap, so scroll position survives); Graph mounts
  `ForceDirectedGraphView`; Timeline mounts `KGTimelineView`; Map mounts `KGMapView`; Claims
  mounts `KnowledgeGraphInspectorSection`; Entities mounts `DocumentInspectorEntitiesTab` (the
  SAME component the Inspector's own Entities tab uses); Related mounts
  `DocumentInspectorRelatedTab` (ditto, "a second implementation would be a second answer to
  what this is related to"). Verified at HEAD: `DocumentKGSurface.swift`'s `content`/
  `nativeTabContent` (`:294-462`) — every case in the `switch activeTab` has a real
  construction, not `EmptyView()` (the only `EmptyView()` cases are `.transcript`/`.digest`,
  which correctly go to the WebKit pane instead, not because they're unbuilt). No dedicated
  render test asserts every case mounts without crashing; grounded in reading the exhaustive
  switch directly (a new `KGSurfaceTab` case fails to compile here until decided, the same
  discipline `PaneContentPlan.Cell.readerPageRoute` uses).
- `reader.knowledge.map-and-timeline-scope-to-this-document` — **[OK]** the Reader's Map and
  Timeline sub-modes are scoped to the document being read (`sourceDocumentId: documentId`
  passed to both `KGTimelineView` and `KGMapView`), not the whole library's first 500 claims —
  a document-scoped reading surface showing library-wide data because the scope parameter was
  missing was the actual defect this fixes. Pinned:
  `MapLensScopeTests.testTheReaderScopesBothSurfacesToItsDocument` (file
  `fichero/Tests/Unit/general/Views/Library/MapLensScopeTests.swift`, suite
  `MapLensScopeTests`).

### C. Passage-level source reveal (landed tonight, e71bb070b, #4834/#4852)

- `reader.reveal.transient-state-preferred-over-shown-document` — **[OK]** (e71bb070b) a
  click on a knowledge surface (a statement, a claim) reveals its source in the Reader and
  the source image WITHOUT changing the current selection or switching sidebar mode — Preview
  and the Reader prefer a transient `sourceRevealDocument` over whatever document is
  otherwise "shown," while the Inspector never reads it and keeps the entity it was already
  showing. Verified at HEAD: `sourceRevealDocument`
  (`Views/Shell/ContentView/ContentView+SourceNavigation.swift:129-190`) is set by
  `focusKGSourcePreview`/the resolved-location path, read by Preview and the Reader, and
  explicitly never read when computing `inspectorDocument`. It clears on any real selection
  change or focus change (guarded against a same-frame resolve wiping its own write) and
  never reaches the workflow-run selection. Pinned:
  `ClaimSourceLandingTests` (file `fichero/Tests/Unit/general/Views/Library/
  ClaimSourceLandingTests.swift`, suite `ClaimSourceLandingTests`; cases "a knowledge-surface
  reveal never writes sidebar mode or selection," "inspectorDocument never reads
  sourceRevealDocument," "a real sidebar or browser selection change clears the reveal," "a
  knowledge-surface reveal never reaches the workflow run selection").
- `reader.reveal.destination-is-explicit-not-a-silent-default` — **[OK]** (e71bb070b) a
  source request now STATES its destination (`.reader`, or both panes) rather than falling
  back to a silent `.reader` default — about 25 construction sites were audited; knowledge
  surfaces that are wired ask for both panes, navigational surfaces (source outline,
  annotations, the artifacts inspector) keep opening the Reader deliberately, and surfaces not
  yet wired state `.reader` explicitly so their behavior is provably unchanged, not
  accidentally inherited. Pinned: `ClaimSourceLandingTests` (`"a .reader request still
  navigates through the selection-changing path"`, `"both highlight channels are posted from
  the one resolved request"`).
- `reader.passage-channel.has-a-second-producer` — **[PARTIAL]** (e71bb070b, → #4834 — tracked
  on its own spec, `kg-readable-representation.md`) the
  Reader's passage-highlight channel, `ReaderPassageFocus` — previously written only by
  in-page SEARCH matches — now has a second producer: following a claim's source latches the
  same passage anchor before navigating, reusing the identical match-then-clear mechanism a
  prior fix (787b624c2) built for search, rather than inventing a second highlight path.
  Verified mounted at HEAD: `ReaderPassageFocus` is read by `ReadingPaneView` and
  `PageContentPane+SourceHighlight.swift` (the actual highlight-drawing code), and written by
  both the search path and `ContentView+ClaimPassageLanding.swift` (the new claim-following
  path). Pinned: `ClaimSourceLandingTests` (`"a claim with a quote latches a passage anchor
  before navigating"`, `"the latch is consumed by the document that used it, not by another"`,
  `"following a claim source records and posts a passage anchor"`). PARTIAL rather than OK:
  the maintainer's own confirmation that both highlights (passage + source-image region)
  render live together is still open, per `kg-readable-representation.md`'s
  `kg.read.span-reuses-existing-location-resolver`, which this behavior is the Reader-side
  half of — cited there, not duplicated as a second open question here.

### D. The Statements/Claims overlap, stated plainly (#4855)

The Reader's Statements lens (`KGSurfaceTab.digest`) and Claims lens
(`KGSurfaceTab.claims`) render the SAME underlying `KnowledgeClaim` rows two different ways —
Statements as WebKit prose grouped by entity, Claims as a native, source-grouped list — and
today each lens's tooltip describes itself using language that belongs to the OTHER lens.
This is `kg-readable-representation.md`'s own finding
(`kg.read.statements-lens-becomes-the-paragraph`, **[BROKEN]**, #4855) and is cited here, not
re-diagnosed: that spec already verified the exact lines
(`DocumentKGSurface.swift:101`/`:105`) and named the direction — Statements should become the
readable paragraph the entry composer produces (`kg.read.lives-in-reader`'s eventual home),
while Claims stays the structured, editable table, so the two differ in KIND (prose versus
data) instead of overlapping in "statement" language. This spec's own `helpText` values above
(`DocumentKGSurface.swift:100-101`) are the exact evidence that finding cites; nothing further
to add here beyond confirming, from this spec's own reading of the same file, that the
overlap is real and unresolved.

## PASS 2 fold plan (not executed — no issues moved)

Two sources feed pass 2, once approved: the legacy milestone "Reader View - Page" (#248, 11
open issues, not yet individually read this pass — the ledger's row 4 sampled its titles
only) and the 14 issues from `library-view-modes.md`'s pass 2 that were left WAITING on this
spec not existing yet:

- **From `library-view-modes.md`'s pass 2 (fold list #158/#209/#210/#183/#159/#260/#165/
  #117):** #2257 (PDFPageMapView, a page grid), #2093 (translation view), #2090 (multi-page
  1-up/2-up/N-up layouts), #2040 (multi-select continuous-scroll preview), #1817 (continuous-
  scroll multi-image viewer), #1749 (WebKit selectable scope), #1747 (unify page/image
  navigation), #1567 (Catalogue/Content pane split + scroll-to-source), #1552 (swipe page-
  change works on PDFs not images), #1483 (WebKit scope selector), #1253 (bidirectional
  scroll sync WebKit ↔ PDF), #1194 (book reading view with inline claim highlights), #973
  (book-aware page numbering), #1491 (source outline endpoint — backend, Reader-adjacent).
- **From #184's disposition table, also waiting on this spec (not yet in the ledger's fold
  list, flagging now):** the same 14 above are the ones the ledger already named; #248's own
  11 issues are additional and have not been individually read yet.

Recommend reading #248's 11 issues and re-checking the 14 above against what `reader-view.md`
now actually documents (several — #1749, #1483 scope selection; #1253 scroll sync — may
already be substantially covered by the lens/tab architecture above, verify-close candidates
rather than fresh GAPs) before proposing behaviors, the same way library-view-modes.md's pass
2 treated its own list. Not done in this pass — Pass 1 was the ask.

## Node-model/prototype-system EPIC family — for the maintainer, comparison only

Four open issues describe the same underlying "Tinderbox-style prototypes/classes" idea,
filed across more than a year, none marked as superseding another:

| Issue | Filed | What it adds beyond the others |
|---|---|---|
| **#1570** | oldest (lowest number) | The broadest framing: "Phase 1 workspace-items → Phase 2 general" — proposes a staged rollout starting from workspace items specifically, generalizing later. The only one of the four that proposes a PHASING plan rather than a single scope. |
| **#1741** | mid | Framed as a revisit — "Class / prototype system — revisit after code cleanup" — the only one that explicitly makes the work CONDITIONAL on a prior cleanup landing first, rather than standalone. |
| **#2081** | mid-late | The most FULLY SPECIFIED of the four: "prototypes (classes) + aliases + entities-as-nodes (Tinderbox-for-archives)" — names three concrete sub-features (prototypes, aliases, entities-as-nodes) rather than one phrase, and is the one most other issues in the fold cross-reference (#2114 names it directly as the hook it extends). |
| **#2114** | newest | The narrowest and most ACTIONABLE scope: "Prototype definitions + attribute inheritance + resolve prototype_key (extend the existing hook)" — the only one of the four that names an EXISTING hook to extend rather than proposing new architecture, suggesting partial groundwork may already exist for this one specifically. |

No disposition proposed here — this is the comparison the maintainer asked for, not a
recommendation for which one carries the work.
