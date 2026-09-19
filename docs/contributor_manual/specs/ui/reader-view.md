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

## PASS 2 — the fold (25 issues read fresh: the 14 waiting + #248's 11)

Reading every body fresh surfaced a correction the titles alone didn't show: several of the
14 "waiting on reader-view" issues turn out to be about the **Preview** pane, not the
Reader's WebKit surface — `PDFPageWithToolbar` (`Views/Preview/PDFViewer/`), `DocumentCanvas`
(`Views/Preview/`), and the sibling-swipe image-viewer code (`Views/Preview/ImageViewer/`)
are all Preview components. They were mis-scoped as reader-view candidates by title
resemblance ("reading surface," "document canvas") to actual Reader vocabulary. Corrected
below rather than folded in on a title match.

### E. New Page-tab behaviors (fits, cited from HEAD, moved onto #313)

- `reader.page.scope-selector` — **[GAP]** (#1749, #1483 — the same ask filed twice) the
  WebKit/text reading view should offer a scope selector — current page / folder / parent /
  grandparent — reusing the existing at-page/at-folder scoping concept (an already-closed
  earlier feature) rather than
  inventing new scope levels. Not verified as built.
- `reader.page.catalogue-pane-and-transcript-always-shows` — **[GAP]** (#1567) a separate
  Catalogue/Content pane (left of the reading surface) showing the structured extraction
  output, distinct from the transcript stream; and the WebKit transcript should always render
  SOME transcript for the selection, including the aggregated transcripts of a parent's
  children (a chapter PDF's per-page transcripts), not "No transcript available" when
  children have them. The issue's OWN separate ask — transcript click-to-source — is now
  substantially built: `reader.reveal.transient-state-preferred-over-shown-document` and
  `reader.passage-channel.has-a-second-producer` above are exactly that mechanism, landed
  since this 2026-06 issue was filed. Not verified as built for the catalogue-pane and
  parent-aggregation halves.
- `reader.lens.translation-not-yet-built` — **[GAP]** (#2093, #3544 — the same gap, #3544
  additionally proposing Transcription+Translation as sub-tabs under Page once shared
  sub-tab support lands) a first-class translation lens — view a document/page WITH its
  translation side-by-side or toggled, at doc/page/passage granularity, persisted as a
  reusable artifact — does not exist. `ReaderLens.swift`'s own doc comment already states
  this precisely: "Translation is absent because it does not exist… a lens that goes nowhere
  is the menu lying." This behavior gives that absence its own line with the issues that ask
  for it, rather than leaving it only as a code comment. Not built.
- `reader.lens.book-view-not-yet-built` — **[GAP]** (#1194) a full-document "Book" reading
  mode — the complete transcription typeset as continuous prose (not page-by-page), with
  claim passages and entity names highlighted inline and a claim popover on click — is a
  lens this spec's inventory does not have. This is a NEW lens proposal, not an extension of
  an existing one (Page shows source page-by-page, Statements is per-entity SVO prose, Notes
  is markup) — a genuinely new reading mode. Not built.
- `reader.page.selection-scope` — **[GAP]** (#4597) with multiple items selected, the Reader
  should show the SELECTED items, not the whole folder — the same "selection scope, not
  ambient scope" principle `library.chrome.select-all-follows-the-visible-surface` and
  `library.canvas.trackpad-scroll-pans`'s neighbors already apply elsewhere in this codebase.
  Not verified as built.
- `reader.page.word-level-source-and-find` — **[GAP]** (#4405) two behaviors the issue argues
  are one feature (both are "given a position in the text, show me where that is on the
  page"): clicking a word or line reaches its source region (page-level ships first, honestly,
  before per-word bounding-box geometry exists; never approximating a location it can't
  prove); and an in-reader Find with match count and next/previous, native-Find-equivalent.
  Builds directly on `reader.reveal.transient-state-preferred-over-shown-document` and
  `reader.passage-channel.has-a-second-producer` above — the "one cursor" constraint the issue
  states (a click, a search step, and a scroll all move the SAME focus) is exactly what those
  two behaviors already guarantee for the claim-following case; this issue extends the same
  mechanism to word-level clicks and to search. Not built.
- `reader.page.inline-transcription-editing` — **[GAP]** (#4375) editing a page's transcription
  directly in the WebKit reader, in place, rather than requiring a trip to the inspector.
  The issue's own scoping is the honest one: the mechanic (`contenteditable` + the existing
  script bridge) is easy; the integrity work is real (offset remapping for dependent KG/bbox
  spans, the audited save path, concurrent-write watermarking, diplomatic-vs-normalized
  ambiguity). Not built.
- `reader.page.highlight-layer-precedence` — **[GAP]** (#4355) with several highlight kinds
  now live in the Reader (find-in-page matches, recognized-text bounding boxes, knowledge
  highlights, selection/annotations), which one is visually "in front" should be a function of
  the visible split/pane, not every layer drawing independently and turning the page to
  visual noise. Not built.
- `reader.page.transcript-wraps-not-clips` — **[BROKEN]** (#3805) the transcript should WRAP
  at a narrow pane width; it currently CLIPS, cutting off the left edge of every line.
  Verified BROKEN at HEAD: `document_view.html`'s `.transcript` rule
  (`fichero-server/src/fichero_server/api/templates/document_view.html:147-154`) is a CSS
  grid with no `grid-template-columns` declared — a grid item's default `min-width: auto`
  resolves to min-content (the longest line) for a `white-space: pre-wrap` block, so the
  track refuses to shrink below the longest line and overflows instead of wrapping. The
  issue's own proposed fix (`grid-template-columns: minmax(0, 1fr)`) is not present in the
  file today.
- `reader.page.sepia-paper-themes` — **[GAP]** (#3721) Sepia/Paper reading themes on top of
  the existing Match App/System choice, driving the same CSS custom properties the Reader
  already var-drives (`systemThemeCSS()`/`themeInjectionScript()` in
  `DocumentKGWebPane.swift`) — no new injection path needed, just new theme values. Not built.

### F. Redirected to an existing spec

- **#2515** (reader toolbar overlaps the library/filmstrip; overflow doesn't collapse to "…"
  before it does) → `panes-workspaces.md`, which already owns toolbar/mini-toolbar overflow
  chrome (see this spec's own earlier fold of #125/#251). New behavior there:
  `panes.toolbar.reader-overflow-collapses-before-overlapping` [GAP].
- **#2419** (PDF viewer needs the magnifier/loupe control at the bottom, matching the image
  viewer) → `preview-magnifier.md`, whose entire scope is the magnifier control. New behavior
  there: `magnifier.pdf-viewer-has-the-loupe-too` [GAP].

### G. Verify-close — evidence posted, left OPEN, not closed here

- **#4605** ("Restore the reader graph view: subject-verb-object statements laid out") — the
  complaint this issue describes (a graph surface that "used to exist" and became reachable
  only through the menu bar) is verified FIXED by the R3 lens reform this spec's section A
  documents: `KGSurfaceTab.graph` → `ForceDirectedGraphView` is a live `ReaderLens` case,
  reachable from the pane head, not menu-bar-only. NOT independently verified: whether the
  graph specifically renders "subject-verb-object statements... laid out" (an SVO-statement
  layout) versus the entity-co-occurrence network `ForceDirectedGraphView`'s own doc comments
  describe — those may be the same thing described two ways, or two different asks. Left
  OPEN for the maintainer to confirm which.

### H. Waiting on a spec that doesn't exist (left on the legacy milestone, not moved)

Reclassified from "waiting on reader-view" (already resolved by Pass 1) to "waiting on a
Preview-surface spec" (still doesn't exist) after reading the bodies fresh — all six are
Preview-pane components, not Reader ones:

- **#2257** (PDFPageMapView, a 2D page grid) — `PDFPageWithToolbar` is `Views/Preview/
  PDFViewer/`.
- **#2090** (multi-page 1-up/2-up/N-up layouts) — names `DocumentCanvas.swift`/
  `PDFPageView.swift`, both `Views/Preview/`.
- **#2040** (multi-select continuous-scroll preview) — its own title says "preview"; body:
  "the image preview becomes a continuous scroll."
- **#1817** (continuous-scroll multi-image viewer) — "the image viewer," `Views/Preview/
  ImageViewer/`.
- **#1747** (unify page/image navigation, "document canvas") — same `DocumentCanvas.swift`
  as #2090.
- **#1552** (swipe changes pages on PDF, not images, in a folder) — `PDFPageController`,
  the image-viewer sibling-swipe gesture — both `Views/Preview/`.

Also waiting on the same not-yet-existing spec, from #248:
- **#4587** (Preview zoom-out has no sensible floor at 1%) — Preview's own zoom control.

### I. Maintainer triage — no home found

- **#1253** (bidirectional scroll sync, Reader's WebKit transcript ↔ Preview's native PDF
  viewer) — genuinely cross-surface: the Reader half already has the mechanism this spec
  documents (`ReaderPassageFocus`), but syncing INTO Preview needs the Preview-surface spec
  that doesn't exist yet, and "keep two different panes in scroll sync" isn't obviously
  either surface's spec to own alone.
- **#973** (book-aware page numbering + chapter markers via Apple Intelligence detection) —
  fundamentally a backend detection + citation-label feature (`Document.metadata
  ['book_structure']`, rendered in `ClaimSummaryCard`/`EntityKindRow`), not a Reader-tab
  question; no spec read this pass owns citation-label formatting.
- **#1491** (TL-3: source outline endpoint, hierarchical drill-down API) — backend-only
  ("Thinking Layer" program, `docs/architecture/thinking-layer.md`), no UI surface of its own
  to fold into.

### Fold table (issue → spec → behavior id → tag)

| Issue | Spec | Behavior id | Tag |
|---|---|---|---|
| #1749, #1483 | reader-view | `reader.page.scope-selector` | GAP |
| #1567 | reader-view | `reader.page.catalogue-pane-and-transcript-always-shows` | GAP |
| #2093, #3544 | reader-view | `reader.lens.translation-not-yet-built` | GAP |
| #1194 | reader-view | `reader.lens.book-view-not-yet-built` | GAP |
| #4597 | reader-view | `reader.page.selection-scope` | GAP |
| #4405 | reader-view | `reader.page.word-level-source-and-find` | GAP |
| #4375 | reader-view | `reader.page.inline-transcription-editing` | GAP |
| #4355 | reader-view | `reader.page.highlight-layer-precedence` | GAP |
| #3805 | reader-view | `reader.page.transcript-wraps-not-clips` | BROKEN |
| #3721 | reader-view | `reader.page.sepia-paper-themes` | GAP |
| #2515 | panes-workspaces | `panes.toolbar.reader-overflow-collapses-before-overlapping` | GAP |
| #2419 | preview-magnifier | `magnifier.pdf-viewer-has-the-loupe-too` | GAP |

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
