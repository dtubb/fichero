# Preview Surface — Design Spec

> Milestone: preview-surface (GitHub #314)
> Manual: TBD — the user manual needs a "Previewing a document" section: what Source/Preview
> shows for a document, a workflow, or a schedule/trigger/chain/activity node; the "Open in
> Preview" affordance when it's hidden; and that clicking a statement reveals its source here
> without changing your selection.

> Design-led spec (Testing Constitution). The creative director owns the intent; tests
> enforce it; code makes them pass. One line per behavior, each cited by its pinning test.
> **Status: DRAFT — PASS 1 of 2** (built behaviors only, grounded in disk 2026-09-18; the
> fold-in of nine waiting issues and legacy milestone #168 is PASS 2 — a fold plan follows
> this spec's own behaviors, no issues moved yet).
> Tags: **[OK]** behaves this way today · **[PARTIAL]** implemented, not fully verified/tested
> · **[BROKEN]** regression, code contradicts the line · **[GAP]** intended, never built.

## Intent (the design)

Preview is one of the three surfaces the standing rule protects from ever merging —
**Preview, Reader, and Inspector never merge.** Preview is the Source/Preview pane: a quick
look at what's selected, or the canvas a workflow/schedule/trigger/chain/activity node is
edited or reviewed in. This spec covers that pane's own structure: what it mounts for a
document (image, PDF, or a model-generated rendition), what it mounts for a non-document node
(the `PaneContentPlan` surfaces), the affordance that offers to open it when it's hidden, and
how a knowledge-surface click reveals a source here without disturbing the current selection.

**Ratified rulings honored here, not restated:** `PaneContentPlan.Plan`'s own doc comment —
"Preview, Reader and Inspector remain three distinct surfaces — hard rule; this type must
never merge them" — and the modes-to-panes renditions-per-surface matrix, which is the
authoritative answer for what each SELECTION KIND shows in Preview (a workflow's canvas, a
schedule's detail view, and so on). This spec is downstream of that matrix; it does not
re-litigate which selections reach Preview.

**Two sibling specs own adjacent, NOT absorbed, territory:** `preview-magnifier.md` owns the
loupe/magnifier instrument entirely — this spec never restates its behaviors, only mounts the
canvas the loupe sits over. `reader-overlay-frame-identity.md` owns keeping a highlight or box
anchored to the same pixels through a crop/rotate/straighten transform, and
`segment-representations.md` owns a page's segments and their competing OCR/VLM readings —
both are cited where Preview's own highlight-drawing touches them, never re-specified.

Surfaces: `DocumentCanvas` (`Views/Preview/DocumentCanvas.swift`, "one canonical canvas for
image and PDF documents," routing to `StorageDisplayImageCanvas`/`ZoomableImagePreview`/
`PDFPageWithToolbar`/`MarkdownCanvas`/`WebContentCanvas`), `CanvasDocumentPolicy`
(PDF-vs-image dispatch), `PaneContentPlan.PaneSurface` (`documentPreview`/`nodeDetail`/
`workflowCanvas`), `ContentView+Navigation.swift`'s `openPreviewAffordanceBar`,
`ContentView+DetailLayout.swift`'s `previewDocument`/`previewView`, `PDFPageView`'s
`applyHighlightSpan` (the source-region highlight), `MultiSelectionPreviewStack`.

## Behaviors (each → one pinning test)

### A. One canonical canvas, dispatched correctly

- `preview.canvas.pdf-vs-image-dispatch` — **[OK]** `CanvasDocumentPolicy.shouldUsePDFCanvas`
  correctly routes a PDF (and a PDF's page child) to the PDF canvas and an image (standalone
  or a page child) to the image canvas, and `.documentForCanvas` resolves the right document
  from a selection, a detail document, or a folder/group fallback. Verified at HEAD:
  `Views/Preview/DocumentCanvas.swift`'s own doc comment states this is "one canonical canvas
  for image and PDF documents," (an already-closed earlier feature) replacing three earlier
  parallel zoom wrappers.
  Pinned: `LayoutModeTests` (`fichero/Tests/Unit/general/Models/LayoutModeTests.swift`, suite
  `LayoutModeTests`), `PDFCompactReadingTests`
  (`fichero/Tests/Unit/general/Views/Shell/PDFCompactReadingTests.swift`, suite
  `PDFCompactReadingTests`), `ReaderSearchPassageLandingTests`.
- `preview.canvas.every-content-case-is-mounted` — **[PARTIAL]** (→ #4870) `DocumentCanvas`'s
  `body` switch mounts a real view for all six `Content` cases — `.imageStorageDisplay` →
  `StorageDisplayImageCanvas`, `.imageRendered` → `ZoomableImagePreview`, `.pdf` →
  `PDFPageWithToolbar`, `.markdown` → `MarkdownCanvas`, `.html`/`.svg` → `WebContentCanvas` —
  none a placeholder (`DocumentCanvas.swift:80-125`). Grounded in reading the exhaustive
  switch directly (a new `Content` case fails to compile here until decided); no dedicated
  render/dispatch test exists yet, so PARTIAL rather than OK.
- `preview.selection.stacks-like-finder` — **[OK]** a multi-document selection shows Finder's
  stacked-card preview (the fan + a count), not a silent preview of only the primary
  document — resolved in document order, not set order, and the front card follows an
  explicit `frontId` with the back cards fanning cyclically. Pinned:
  `MultiSelectionPreviewStackTests`
  (`fichero/Tests/Unit/general/Views/Preview/MultiSelectionPreviewStackTests.swift`, suite
  `MultiSelectionPreviewStackTests`).

### B. Non-document nodes get a named Preview surface, or an honest Open affordance

- `preview.plan.node-detail-lands-in-preview` — **[OK]** a schedule/trigger/chain/batches/
  activity selection's Preview cell is `PaneSurface.nodeDetail` (`ScheduleDetailView`/
  `TriggerDetailView`/`ChainEditorView`/`BatchRunView`/`ActivityDetailView`, reused as-is,
  landed 9128ecdee, an increment of the still-open `modes-to-panes.md` migration, tracked
  there not here) — the Library pane stays the plain navigator beside
  it, never a takeover. Pinned:
  `PaneContentPlanTests.nodeDetailModesLandInThePreviewSlot` (file
  `fichero/Tests/Unit/general/Views/Shell/PaneContentPlanTests.swift`, suite
  `PaneContentPlanTests`).
- `preview.plan.generic-document-preview-fallback` — **[OK]** a mode with no dedicated
  Preview rendition of its own gets the generic `documentPreview` cell (`EditorView`) rather
  than an empty pane or a borrowed one. Pinned: `PaneContentPlanTests` (suite
  `PaneContentPlanTests`, case "modes with no dedicated rendition get the generic
  document-preview cell").
- `preview.plan.open-affordance-for-missing-preview` — **[OK]** when the current selection's
  Preview cell is `.workflowCanvas` or `.nodeDetail` and no Preview pane is currently showing,
  a banner names what's hidden and offers ONE explicit action to add it back — "This opens in
  the Preview pane, which is closed. [Open in Preview]" — never an automatic pane addition.
  Deliberately scoped away from `.documentPreview`: a plain document/chat selection with
  Preview hidden is the user's own layout choice (a Reader-only workspace is legitimate), not
  a takeover to retire. Verified at HEAD: `openPreviewAffordanceBar`
  (`ContentView+Navigation.swift:176-190`) reads `PaneContentPlan.missingPreviewSurface`
  exactly this way. Pinned:
  `PaneContentPlanTests.missingPreviewSurfaceFiresOnlyForNodeKindsWithoutAPreviewLeaf`.

### C. Reveal without losing your place (landed tonight, e71bb070b, #4834/#4852)

- `preview.reveal.prefers-transient-source-over-shown-document` — **[BROKEN]** (→ #4834, retagged
  2026-09-19 from the maintainer's own test session — was **[OK]**) clicking a sentence in the
  entity's biography does NOT make Preview follow — Preview shows "No selection" throughout,
  the exact opposite of "prefers a transient source." **The lesson, stated plainly**:
  `ClaimSourceLandingTests` (cited below) passed and this behavior still failed on screen,
  because those tests are source scans and pure functions — none of them mounted a pane. A
  green pinning test proved the mechanism's shape, never that a real Preview pane reads it.
  **Cause, VERIFIED on disk for the KG-Inspector side of this same click (2026-09-19)**: the
  reveal's own call to `focusClaim` omits the entity argument, so `focusClaim` assigns its
  default — `nil` — unconditionally, clearing the focused entity and leaving the Inspector's
  arm rule nothing to show; a regression of e71bb070b (Slice A), fixed in 3f017efac, build
  passes, but NOT yet seen working (tests haven't executed). Tag stays BROKEN until the
  maintainer sees it work. See `kg-readable-representation.md`'s
  `kg.read.sentence-opens-source-highlighted`. **Whether
  Preview's OWN "No selection" symptom shares this exact cause is explicitly NOT yet verified**
  — stated as open, not assumed just because the symptom co-occurs with the entity-focus bug.
  What follows describes the mechanism as designed and unit-tested, now known false
  in the running app: Preview prefers a
  knowledge-surface click (a statement, a claim) can put a source on screen in Preview
  without touching the current selection, `detailDocument`, or the sidebar mode. Verified at
  HEAD: `previewDocument` (`ContentView+DetailLayout.swift:316-318`, "the reveal-aware sibling
  of `readerDocument`") is `sourceRevealDocument ?? detailDocument`, and both the PDF branch
  (`documentTitle: previewDocument?.name`) and the plain-document branch
  (`CanvasDocumentPolicy.documentForCanvas(..., detailDocument: previewDocument, ...)`) read
  it, not `detailDocument` directly. `inspectorDocument` deliberately never reads this value —
  the same asymmetry `reader-view.md`'s
  `reader.reveal.transient-state-preferred-over-shown-document` documents for the Reader side
  of the identical mechanism. Pinned: `ClaimSourceLandingTests`
  (`fichero/Tests/Unit/general/Views/Library/ClaimSourceLandingTests.swift`, suite
  `ClaimSourceLandingTests`; cases "a knowledge-surface reveal never writes sidebar mode or
  selection," "inspectorDocument never reads sourceRevealDocument").
- `preview.reveal.region-and-passage-share-one-resolve` — **[BROKEN]** (→ #4834, retagged 2026-09-19
  from the maintainer's own test session — was **[OK]**) clicking a claim goes to the page but
  the highlight is not precise and he loses his place — consistent with
  `kg-readable-representation.md`'s `kg.read.span-reuses-existing-location-resolver` finding
  for the identical mechanism. **The lesson, stated plainly**: `ClaimSourceLandingTests` (cited
  below) passed and this behavior still failed live — the test proves one resolve is called
  once, not that its result renders correctly in a mounted pane. **Cause, VERIFIED on disk
  (2026-09-19), the same root cause as the sibling behaviors above**: `focusClaim` is called
  without the entity argument and clears the focused entity, a regression of e71bb070b (Slice
  A); fixed in 3f017efac, build passes, but NOT yet seen working (tests haven't executed). Tag
  stays BROKEN until the maintainer sees it work. What follows describes the
  mechanism as designed and unit-tested, now known imprecise in the running app: clicking a
  statement resolves its source location ONCE and posts to BOTH highlight channels from that one
  resolve — the Reader's passage anchor (`postClaimPassageAnchor`) and the source image's
  region highlight (`.ficheroNavigateToPage`'s `bbox` payload, consumed by `PDFPageView`'s
  pre-existing `applyHighlightSpan`, an already-closed earlier feature) — so a
  `.both`-destination request always lights
  both channels from one location lookup, never two independent ones that could disagree.
  Verified precisely at HEAD, not merely from the commit message: `handleOpenClaimSource`
  (`ContentView+StateEvents.swift:479-538`) calls `revealResolvedSource(request)` once, then
  unconditionally calls `postClaimPassageAnchor` and posts `.ficheroNavigateToPage` with the
  request's `bbox` when present — both statements execute regardless of which single
  destination was asked for, exactly matching the doc comment's claim. The region-highlight
  drawing code itself (`PDFPageView.applyHighlightSpan`) is PRE-EXISTING (an already-closed
  earlier feature), not new tonight; what's new is that ONE resolve now feeds it and the
  Reader's passage channel
  together, where each previously had its own path. Pinned: `ClaimSourceLandingTests` (case
  "both highlight channels are posted from the one resolved request").
- `preview.reveal.banner-offers-to-open-when-no-source-pane-visible` — **[PARTIAL]**
  (→ #4870) with no Preview or Reader pane visible, a reveal still happened — the click did
  something honest, it just has nowhere to land — so a banner says so and offers "Open in
  Preview." Verified at HEAD: `openPreviewAffordanceBar`'s second banner
  (`ContentView+Navigation.swift:198-215`) fires exactly on `sourceRevealDocument != nil,
  !paneVisibility.canvas, !paneVisibility.reading`, deliberately NOT folded into
  `missingPreviewSurface` (a reveal is the direct consequence of a click, not a workspace
  layout choice). No test found exercising this second banner specifically — PARTIAL rather
  than OK.
- `preview.reveal.panes-should-follow-not-banner` — **[GAP, DESIGN]** (#4870) seen live
  2026-09-19: the maintainer does not want the banner above — a "Open in Preview" prompt
  reads as the app asking permission to do its job. Expected, stated as intent, not a decided
  mechanism: panes should FOLLOW a reveal automatically rather than asking. **Open questions,
  not decided here:** does a hidden Preview/Reader pane open itself on a reveal (and if so, does
  it ever surprise a user who deliberately closed it), does the banner stay as a fallback for
  some narrower case, and does this interact with `panes.strip`/workspace-layout rulings the
  other lane's findings are deciding (out of this spec's own scope — cross-reference, don't
  restate).

## PASS 2 — the fold (9 waiting issues, every body read fresh)

None redirect elsewhere and none need maintainer triage — all nine are genuinely this spec's
subject. Evidence varies by issue: #2090, #2040, #1817, #1747, #1552, and #588's bodies name a
Preview code path or class directly (`DocumentCanvas.swift`, `PDFPageView.swift`,
`PDFPageController`, "the image viewer"); #2257's body names a specific CLASS
(`PDFPageWithToolbar`) which reading the code (not the issue) places under
`Views/Preview/PDFViewer/`; #4587 and #4583 are evidenced by their own titles ("Preview
zoom-out," "before Preview loads") plus the code read below.

### New behaviors (fits, cited from HEAD, moved onto #314)

- `preview.pdf.page-grid-mode` — **[GAP]** (#2257) a 2D page-GRID mode for a PDF — a
  `LazyVGrid` of thumbnail cells, not one image at a time — mounted via a Page/Grid toggle in
  `PDFPageWithToolbar`, with per-tile or global toggling of image vs. extracted text in the
  grid. Distinct from the spatial node-map (Canvas) and from georeferencing a page onto a
  basemap (waiting on `historical-text-normalization`, per the ledger). Not built.
- `preview.pdf.multi-page-layouts` — **[GAP]** (#2090) multiple page-layout modes for BOTH
  PDFs and image documents — 1-up, 2-up (facing spread), 3-up, 4-up, continuous scroll — split
  honestly into two tiers by what PDFKit gives for free: Tier 1 (single/single-continuous/
  two-up/two-up-continuous) is a small toolbar-control change surfacing `PDFView.displayMode`
  states already rendered; Tier 2 (3-up/4-up, and the same grid for image documents, which
  have no `PDFView` at all) needs one shared custom N-column grid renderer over page images,
  lazy-loaded. Not built.
- `preview.selection.continuous-scroll-on-multiselect` — **[GAP]** (#2040) selecting multiple
  items should turn the image preview into a continuous vertical scroll of their pages
  (Preview.app's own behavior for a multi-selection), as a property of the existing canvas —
  not a second, parallel viewer. Not built.
- `preview.image.continuous-scroll-mode` — **[GAP]** (#1817) a folder of images should offer a
  continuous vertical-scroll mode — flowing through pages the way a PDF's continuous mode
  does — reusing the existing viewer stack, lazy-loading through the storage HTTP endpoints.
  Distinct from `preview.selection.continuous-scroll-on-multiselect` above: that one is
  triggered BY a multi-selection; this one is a standing MODE for browsing any image folder
  regardless of how many items are selected.
- `preview.canvas.unified-sibling-navigation` — **[GAP]** (#1747, #1552 — the same ask: PDF
  and image-folder navigation should behave identically) `DocumentCanvas` should navigate
  siblings the SAME way for a PDF and for a folder of images — left/right swipe, arrow keys,
  on-screen arrow buttons — one navigation model, not two. Verified BROKEN-by-omission at
  HEAD, not merely unbuilt: `DocumentCanvas`'s `onNavigateToDocument` callback (the
  sibling-stepping hook) is threaded to BOTH image `Content` cases
  (`.imageStorageDisplay`/`.imageRendered`, `DocumentCanvas.swift:82,89`), but the `.pdf` case
  (`:113-117`) passes only `documentId`/`pageIndex`/`onPageIndexChange` to
  `PDFPageWithToolbar` — that view has no `onNavigateToDocument` parameter AT ALL (confirmed:
  no such parameter appears anywhere in `PDFPageWithToolbar.swift`). A PDF genuinely cannot
  step to a sibling FILE the way an image can, by construction, not by an unverified report.
  #1552's specific repro (swipe works on a PDF, not on an image in a folder) is the same gap
  from the opposite direction — the image viewer has its own internal swipe-to-next-PAGE
  gesture but no sibling-FILE step wired the same way a PDF's page-turn is, per that issue's
  own note that "the image viewer has no equivalent sibling-nav gesture."
- `preview.zoom.has-a-sensible-floor` — **[GAP]** (#4587) zooming a page image out should
  clamp at fit-to-view (or a small multiple below it), not permit a 1% speck in a grey field.
  Not verified as built.
- `preview.image.shows-cache-before-full-load` — **[GAP]** (#4583) the first click on an icon
  should show Preview's cached thumbnail instantly, swapping in the full image when ready —
  no blank beat. This is the Preview-side half of a symptom `library-view-modes.md`'s
  `library.icon.arrow-nav-latency` names the Library-side half of (synchronous selection,
  async image load) — cross-referenced there, not duplicated as a second behavior for the
  same root cause.

### Verify-close — evidence posted, left OPEN, not closed here

- **#588** ("PDFView: trackpad pinch-zoom + prevent parent gesture interception") — verified
  BUILT at HEAD: `PinchOwningPDFView` (`PDFPageView.swift:22-33`) overrides `magnify(with:)` to
  disable `autoScales` the moment a pinch begins (calling `super.magnify` so PDFKit's native
  pinch recognizer still does the zooming), and two LATER fixes' own comments (#4125, #4279)
  build on this behavior as already-working infrastructure, not as something still broken.
  Not independently tested — no dedicated test exercises the pinch gesture itself. Left OPEN
  for the maintainer to confirm live; not closed here.

**Milestones**: legacy milestone "Reader View - Page" doesn't hold these nine — they came from
the earlier `library-view-modes.md`/`reader-view.md` folds' waiting lists, which have no
single legacy milestone to close (their issues were scattered across "UX - Library & Reading
Surface" and "Reader View - Page," both already handled in prior passes). No milestone closes
from this fold.

**Legacy milestone "Preview - Image Editing" (#168, 16 open issues) — recommend it stays
BESIDE this spec, as its own `preview-image-editing` spec, not folded in.** `DocumentCanvas`
threads an `isEditing` binding down to the image viewer for the edit toggle, and
`Views/Preview/ImageEditor/` is a substantial, self-contained subsystem (11 files: chain
panel, clipboard, marquee overlay, live-edit preview, popovers) reached through it — but
editing is a whole non-destructive pipeline (crop/rotate/filters, an edit chain, undo/redo of
edits specifically) with its own EPIC-sized scope in #168's issues, analogous to how
`reading-markup-annotations.md` is its own spec beside `reader-view.md` rather than folded
into it. This spec's job is mounting and dispatching the canvas Preview shows; #168's job is
what happens once the user starts EDITING what's on that canvas. Matches the legacy-milestones
ledger's own original proposal (row for `preview-image-editing`, high in the burn-down).

No other legacy milestone was found to be substantially about Preview this pass beyond what's
already known (the nine waiting issues and #168) — this was not an exhaustive re-sweep of
every open milestone, only the ones already flagged as candidates.
