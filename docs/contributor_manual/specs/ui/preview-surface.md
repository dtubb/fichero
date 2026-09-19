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

- `preview.reveal.prefers-transient-source-over-shown-document` — **[OK]** Preview prefers a
  transient `sourceRevealDocument` over whatever document is otherwise "shown" — a
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
- `preview.reveal.region-and-passage-share-one-resolve` — **[OK]** clicking a statement
  resolves its source location ONCE and posts to BOTH highlight channels from that one
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

## PASS 2 fold plan (not executed — no issues moved)

Nine issues are waiting on this spec (found while reading bodies fresh during the
`library-view-modes.md` and `reader-view.md` folds — by the CODE PATHS their bodies name,
`Views/Preview/PDFViewer/`, `Views/Preview/ImageViewer/`, `Views/Preview/DocumentCanvas.swift`,
not by title resemblance to "reading surface" vocabulary that belongs to the Reader):
**#2257** (a 2D page-grid mode for PDFs — its body names `PDFPageWithToolbar`), **#2090**
(multi-page 1-up/2-up/N-up layouts — names `DocumentCanvas.swift`/`PDFPageView.swift`),
**#2040** (multi-select continuous-scroll preview — its own title says "preview"), **#1817**
(continuous-scroll multi-image viewer — "the image viewer"), **#1747** (unify page/image
navigation — the same `DocumentCanvas.swift`), **#1552** (swipe page-change parity, PDF vs
images — `PDFPageController`, the image-viewer sibling-swipe gesture), **#4587** (zoom-out has
no sensible floor), **#4583** (first click delay before the full image loads), **#588** (PDF
trackpad pinch-zoom + parent-gesture interception). None read yet against this spec's actual
behaviors above — that reading is Pass 2's job, not done here (Pass 1 was the ask).

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
