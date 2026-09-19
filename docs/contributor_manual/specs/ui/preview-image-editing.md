# Preview Image Editing — Design Spec

> Milestone: preview-image-editing (GitHub #315)
> Manual: TBD — the user manual needs an "Editing an image" section: the Edits facet, the
> reversible operation chain, compare modes (single/side-by-side/wipe), copying edits between
> images, and that Revert to Original always asks first because every step is already saved.

> Design-led spec (Testing Constitution). The creative director owns the intent; tests
> enforce it; code makes them pass. One line per behavior, each cited by its pinning test.
> **Status: DRAFT — PASS 1 of 2** (built behaviors only, grounded in disk 2026-09-18; the
> fold-in of legacy milestone #168's sixteen issues is PASS 2 — a fold plan follows this
> spec's own behaviors, no issues moved yet).
> Tags: **[OK]** behaves this way today · **[PARTIAL]** implemented, not fully verified/tested
> · **[BROKEN]** regression, code contradicts the line · **[GAP]** intended, never built.

## Intent (the design)

Image editing is reached from `preview-surface.md`'s own territory — the Preview pane's
"Edits" facet — but is substantial enough to be its own spec, the same relationship
`reading-markup-annotations.md` has to `reader-view.md`: `preview-surface.md` owns mounting
and dispatching the canvas Preview shows; this spec owns what happens once the user starts
editing what's on it. `Views/Preview/ImageEditor/` is an 11-file, self-contained subsystem
(2,402 lines: the editor view, its toolbar, popovers, a step-chain panel, a marquee-select
overlay, a live-edit preview, and a clipboard for copying edits between images).

**`[[never rewrite source]]`, verified precisely from the code, not assumed:** editing is
non-destructive by construction, not by convention. An edit is one operation appended to an
`ImageEditChain` — its own database row (`document_id` + an ordered `operations: list[dict]`)
— never a mutation of the document's own file bytes. Rendering a preview
(`GET /api/images/{id}/preview?apply_edits=true|false`) loads the ORIGINAL source image fresh
from disk every time (`_load_source_image(source_path, …)`), applies the chain's operations to
an in-memory copy, and writes only the RENDERED RESULT to a disposable cache directory
(`storage/preview-cache/{document_id}/page-{page}/{hash}.bin`, keyed on document id + page +
`apply_edits` + the chain's own `updated_at`, capped at four cached revisions per page). The
source file at `source_path` is read, never written, anywhere in this path. `apply_edits=false`
is how the "original" side of a compare mode is produced — no separate original copy is kept,
because the source itself always IS the original.

**Ratified rulings honored here, not restated:** the three-surfaces rule (Preview/Reader/
Inspector never merge) from `preview-surface.md`; `preview-surface.md`'s own mounting of
`DocumentCanvas`, which this spec's editor sits beside, not inside — `EditorView`'s own
`previewRoute(for:isEditing:)` chooses between `DocumentCanvas`'s plain storage-display canvas
and this spec's full `ImageEditorView`, both driven by the SAME toggle
(`inspectorSelectedTab == .edits`), so the two specs share one on/off switch without either
one owning the other's surface.

Surfaces: `ImageEditorView` (+`+Canvas`/`+Clipboard`/`+Popovers`/`+Toolbar`/`+Types`),
`ImageEditorModel`, `ImageEditChainPanel` (+`+Steps`), `ImageMarqueeOverlay`,
`LiveEditPreview`, `ImageEditClipboard`, `ImageEditingService` (client),
`fichero_server.models.ImageEditChain`, `api/routes/ingest/image_editing.py`.

## Behaviors (each → one pinning test)

### A. Non-destructive storage — the source is never rewritten

- `preview.edit.chain-is-a-separate-row-never-the-source` — **[OK]** an edit is one operation
  appended to `ImageEditChain` (`document_id` + ordered `operations`), its own database row —
  never a write to the document's source file. Verified at HEAD: `_render_preview`
  (`image_editing.py:613-641`) calls `_load_source_image(source_path, …)` to read the ORIGINAL
  every time, applies `chain.operations` to an in-memory copy via `apply_operation`, and writes
  only the rendered bytes to a disposable preview-cache path — no code path in this function
  (or `_append_operation`) opens `source_path` for writing. Pinned:
  `test_routes_image_editing.py::TestImageEditChainRoutes::test_valid_chain_round_trips_without_transient_path`.
- `preview.edit.preview-toggles-original-vs-edited-with-no-second-copy` — **[OK]** the
  `apply_edits` query parameter on `GET /api/images/{id}/preview` is the entire mechanism for
  showing "original" versus "edited" — `apply_edits=false` skips the chain entirely and
  renders straight from the source, so there is no separately-stored "original" copy to drift
  from the real source. Pinned:
  `test_routes_image_editing.py::TestImagePreviewRoute::test_preview_returns_original_without_edits`,
  `::test_preview_resolves_library_relative_source_path`.
- `preview.edit.operations-validated-at-the-boundary` — **[OK]** an invalid operation (an
  unknown op name, an out-of-range rotate angle, a negative crop dimension) is refused with a
  422 at the PUT boundary, never silently accepted and failing later at render time. Pinned:
  `test_routes_image_editing.py::TestImageEditChainRoutes::test_put_rejects_invalid_operations`
  (parametrized over three invalid shapes).
- `preview.edit.crop-and-split-are-reversible` — **[OK]** cropping or splitting an image is a
  chain operation like any other, not a destructive file replacement — reversible the same way
  every other step is (delete the step, or revert the whole chain). Pinned:
  `test_routes_image_editing.py::TestReversibleImageCrop`,
  `::TestReversibleImageSplit`.
- `preview.edit.quarter-turns-are-lossless` — **[OK]** a 90/180/270-degree rotation is a
  lossless quarter-turn operation, not a lossy re-encode-and-rotate. Pinned:
  `test_image_edit_chains.py::TestQuarterTurnsAreLossless`.

### B. Mounting — reached through the Preview surface's Edits facet

- `preview.edit.mounted-from-the-edits-facet` — **[PARTIAL]** (→ #4872) `EditorView
  .previewRoute(for:isEditing:)` mounts the full `ImageEditorView` (its `.imageEditor` route
  case) when `isEditing` is true (`inspectorSelectedTab == .edits`) AND the document is
  editable (`fileType == .image` or `docType == .page`) — for a plain image/page, a folder's
  image, or a PDF page alike (`EditorView.swift:175-238`). The SAME `isEditing`/
  `inspectorSelectedTab == .edits` toggle also drives `DocumentCanvas`'s `isEditing` binding
  when the doc ISN'T routed to the full editor, greying its edit-affordance control instead —
  one toggle, two surfaces, per `preview-surface.md`'s own `DocumentCanvas` behaviors. Not
  verified as built: no dedicated mount/dispatch test asserts `previewRoute` picks
  `.imageEditor` under these exact conditions; grounded in reading the exhaustive route
  function directly.

### C. Editor mechanics — the step chain, caches, and copying edits

- `preview.edit.re-editing-a-step-rewrites-it-in-place` — **[OK]** re-opening an already-applied
  step's controls and adjusting them rewrites that SAME step in the chain — it does not append
  a second, competing step for the same operation. Pinned:
  `ImageEditStepEditingTests.updateOperationKeepsPosition` (file
  `fichero/Tests/Unit/general/Views/Preview/ImageEditStepEditingTests.swift`, suite
  `ImageEditStepEditingTests`).
- `preview.edit.delete-step-and-revert-are-reachable-and-confirmed` — **[OK]** deleting a
  single step, and reverting the whole chain to the original, are both reachable from the
  steps panel, and reverting always asks for confirmation first — every step is already
  committed/saved, so reverting always discards real, saved work, never just an in-progress
  draft. Pinned: `ImageEditStepEditingTests` (suite `ImageEditStepEditingTests`, case
  "delete-a-step and revert-to-original stay reachable and confirmed").
- `preview.edit.rendition-caches-invalidate-on-every-edit` — **[OK]** a successful edit drops
  BOTH derived-pixel caches (not just the storage-service one), including on the way OUT of
  the editor, so leaving edit mode can never show stale pixels; a batch-applied edit
  invalidates the cache per DOCUMENT touched, not only for whichever one is on screen. Pinned:
  `ImageEditRenditionRefreshTests` (file
  `fichero/Tests/Unit/general/Views/Preview/ImageEditRenditionRefreshTests.swift`, suite
  `ImageEditRenditionRefreshTests`; all three cases).
- `preview.edit.chain-sync-avoids-redundant-refetch` — **[OK]** the editor's chain-sync
  mechanism re-fetches and re-renders exactly once per real change (a bumped storage epoch),
  never on an unchanged epoch, never for an edit the model made itself echoing back through
  the sync path, and does nothing for a model with no document loaded. The Inspector's Edits
  facet and the editor canvas both watch the same storage epoch, and the facet draws only the
  step LIST, never the pixels (that stays the canvas's job). Pinned: `ImageEditChainSyncTests`
  (file `fichero/Tests/Unit/general/Views/Preview/ImageEditChainSyncTests.swift`, suite
  `ImageEditChainSyncTests`; all seven cases).
- `preview.edit.clipboard-copies-and-pastes-a-chain` — **[OK]** an edit chain can be copied
  from one image and pasted onto another (or across a multi-selection) — copying strips the
  per-document bookkeeping so the copy travels cleanly, pasting REPLACES the target's chain
  rather than appending to it, copying an intentionally-empty chain is still a real copy (not
  a silent no-op), and pasting across a multi-selection asks for confirmation first (since it
  may replace saved chains on files not currently on screen) while pasting onto a single image
  does not. Pinned: `ImageEditClipboardTests` (file
  `fichero/Tests/Unit/general/Views/Preview/ImageEditClipboardTests.swift`, suite
  `ImageEditClipboardTests`; all four cases).

### D. Compare modes — true but untested

- `preview.edit.compare-modes-single-side-by-side-wipe` — **[PARTIAL]** (→ #4872) the editor
  offers three ways to compare original and edited: `.single` (one canvas, toggled), `.wipe`
  (a slider split), and `.sideBySide` (`ImageEditorView+Types.swift:3-7`, `CompareMode`).
  Single mode reuses the shared `DocumentCanvas` zoom; side-by-side and wipe are plain images
  with their own independent zoom control, since a second zoom pill over `DocumentCanvas`
  would fight with its own. Grounded in reading the enum and its call sites directly; no test
  found exercising any of the three modes.

## PASS 2 — the fold (legacy milestone #168, 16 issues, every body read fresh)

### E. New behaviors (fits, cited from HEAD, moved onto #315)

- `preview.edit.pdf-edit-toggle-is-dead` — **[BROKEN]** (#2261) the edit toggle should work on
  a top-level PDF document, not only on one of its child pages. Verified BROKEN at HEAD:
  `EditorView.previewRoute` (`EditorView.swift:190-198`) checks `doc.docType == .page` and
  routes THAT to `pagePreviewRoute`, which does check `isEditing` — but a plain PDF file
  (`doc.fileType == .pdf`, not a page) returns `.storageDisplay` unconditionally, with no
  `isEditing` check at all. The per-page raster edit chain (`ImageEditorView`) already works;
  a PDF parent simply never routes to it.
- `preview.edit.continuous-scroll-through-pages` — **[GAP]** (#1933) the image editor should
  scroll continuously through a document's pages/images, the way the PDF viewer's continuous
  mode does, rather than one page at a time. Not verified as built — the editor's canvas
  (`ImageEditorView+Canvas.swift`) shows the single active document, stepped via prev/next,
  with no continuous-scroll mode found.
- `preview.edit.toolbar-icon-alignment` — **[GAP]** (#1556) the edit button in the image
  mini-toolbar should share the same baseline/vertical centering and sizing as its
  neighbouring controls (zoom, fit). Not verified either way — a small, cosmetic claim not
  worth a source-scan proof either way.
- `preview.edit.native-vision-remove-background` — **[GAP]** (#1540) Remove Background should
  offer a macOS-native option (Vision's subject-lift, the same engine Preview/Quick Look use)
  alongside the existing methods, since the current default's output quality is poor.
  Verified at HEAD: the server's `_remove_background` (`media/image_ops.py:162-178`) supports
  exactly three methods — `rembg`, `opencv`, `threshold` — no Vision-based method exists; the
  client's `removeBackground(method:)` defaults to `"opencv"` and offers no alternative in its
  UI. Not built.
- `preview.edit.segments-panel-and-recombine` — **[GAP]** (#504) splitting a document should
  surface a segments panel (browse the resulting pages/segments as separate items, run a
  workflow on one independently) and a recombine action restoring the parent — with no
  duplicate files created on disk. Verified PARTIALLY at HEAD: the underlying reversible
  split/uncrop chain operation is built and tested (see `preview.edit.crop-and-split-are-
  reversible` above), but no segments-BROWSING panel or recombine UI was found anywhere under
  `Views/Preview/ImageEditor/`. The chain mechanism exists; the panel this issue actually asks
  for does not.
- `preview.edit.epic-tracks-already-built-and-remaining-pieces` — **[GAP]** (#1385, the
  founding EPIC: "AI-enhanced, non-destructive image editing — port legacy ML tools; apply to
  images AND PDF pages") — its five stated principles are a mix of DONE and open, stated
  plainly rather than left as one undifferentiated ask: non-destructive storage is built (see
  section A above); an A/B compare UI is built (`CompareMode`: single/wipe/side-by-side,
  `preview.edit.compare-modes-single-side-by-side-wipe`); a macOS-native option for at least
  one tool (Remove Background) is NOT built (`preview.edit.native-vision-remove-background`
  above); "apply to any image OR to a page/range of pages of a PDF" is contradicted by
  `preview.edit.pdf-edit-toggle-is-dead` above — a PDF parent's edit toggle doesn't even
  route to the editor; EXIF-awareness across transforms was not independently checked this
  pass. Kept as one line naming the whole, with each concrete piece cited to its own specific
  behavior rather than duplicated here.

### F. Redirected to an existing spec

- **#4418** ("show recognised text regions on images AND PDFs") → `segment-representations.md`
  as `segment.overlay.recognized-text-regions` — a region/anchor with its own provenance
  (PDF text layer, model, or human correction) is that spec's own subject, not an editing
  operation. The bidirectional region↔text cursor it asks for is explicitly the SAME seam
  `reader-overlay-frame-identity.md` already owns, cited there rather than re-specified here.

### G. Verify-close — evidence posted, left OPEN, not closed here

Given the test coverage Pass 1 found, several older issues describe symptoms already fixed by
a DIFFERENT mechanism than the one they proposed — evidence stated as what it is (the code
read, not a rendered screen):

- **#502** ("Wire: Image Editing v1 — Crop + Rotate") — every item in its own test checklist
  is built and tested: crop/rotate live-update, Original toggle confirms the source is
  unchanged, undo reverts, the chain persists across relaunch. Section A's behaviors above
  (`preview.edit.chain-is-a-separate-row-never-the-source`,
  `.crop-and-split-are-reversible`, `.quarter-turns-are-lossless`) are this issue's own
  acceptance criteria, verified from the code.
- **#503** ("Wire: Image Editing v2 — Enhance + Remove BG") — enhance sliders
  (brightness/contrast/sharpen state in `ImageEditorView`) and a Remove Background action
  (`ImageEditorModel.removeBackground(method:)`) both exist and are reachable from the
  toolbar and the step panel. Not independently checked this pass: the specific "Auto-enhance"
  one-click button and whether export specifically re-applies the chain.
- **#1161** ("Document editing tools: deskew, color-correct, split, crop, rotate") — every
  named operation exists server-side: `detect_deskew_angle`/`auto_deskew`,
  `brightness`/`contrast` (`media/image_ops.py`), crop, rotate, and split (Section A above);
  batch-apply across a multi-selection is built and tested
  (`preview.edit.clipboard-copies-and-pastes-a-chain`'s "pasting across a selection" case).
- **#1558** ("side-by-side / wipe compare forces images to square") — verified FIXED at HEAD:
  `ImageEditorView+Canvas.swift`'s wipe mode computes `ImageFit.fittedRect(imagePixelSize:
  in:)` for its frame — a real aspect-ratio-preserving fit, not a hardcoded square — and both
  wipe layers carry `.aspectRatio(contentMode: .fit)`.
- **#1590** ("edited image doesn't update the image viewer / library thumbnail") — the exact
  complaint this issue names ("rotate an image and the library row and preview strip kept
  showing the old one") is fixed, but by a DIFFERENT, later mechanism than the issue's own
  proposed notification: `ImageEditorView`'s `onEditApplied` and `finishEditing()` both call
  `storageService.invalidateImageCache(for:)` AND `renditionService?.invalidate(documentId:)`
  — the exact two caches `ImageEditRenditionRefreshTests`'s own doc comment names as the ones
  that have to drop together. **Still an explicitly open question, not fixed and not
  reopened as broken** — this issue's own body flags it, not this pass: workflows
  (Catalogue/Transcribe/OCR) resolve input via `storage.resolve_source(doc)`, which returns
  the ORIGINAL file with no knowledge of the edit chain, so a workflow run after an edit still
  processes the unedited original. Not independently re-checked this pass; the issue itself
  called this "flagged for decision," not fixed.
- **#3213** ("Quartz evaluation — recommend hybrid, not a rewrite") — its core recommendation
  is built: `LiveEditPreview.swift` maps the pending op to `CIFilter.colorControls()`,
  `.sharpenLuminance()`, and `.straighten()` for live, local preview while dragging, exactly
  the "client-side live preview with Core Image for the pending op only" the issue
  recommends — the server-authoritative chain remains the committed source of truth,
  unchanged. Not independently checked: the issue's own proposed drift test (server render
  and CI preview agree within tolerance on a fixture set) and latency budget test.
- **#3756** ("wire reversible image editing into SwiftUI") — crop, split, batch-apply, and
  undo are all wired and tested (Section A and C above); "uncrop"/"unsplit" specifically were
  not found as separately named operations — they read as the same generic
  delete-a-step/revert-to-original mechanism `preview.edit.delete-step-and-revert-are-
  reachable-and-confirmed` already covers, not a gap of their own.

### H. Maintainer triage — no home found

- **#1174** ("Lightroom-style non-destructive Document Inspector for stage variants") — a
  stage/variant NAVIGATOR inside the Document Inspector, not this spec's editing-operations
  surface — no spec read this session owns the Document Inspector's general tab/facet
  structure (`kg-entity-inspector.md` is scoped to the entity focus pane specifically).
- **#1176** ("Non-destructive parametric image pipeline + transient cache") — a BACKEND
  workflow-tools pipeline for paleography preprocessing (`prepare_images`/`rotate`/`split`/
  `segment`/`enhance`/`convert_to_svg` as workflow tools, with recipe caching/eviction), its
  own text says "backend-first... designed for SwiftUI inspector integration LATER" — a
  different pipeline from this spec's interactive `ImageEditChain`, not this surface's
  question to answer.

## Milestone

Legacy milestone #168 does not reach zero this pass: of 16 open issues, 6 fit and move onto
#315, 1 redirects to `segment-representations.md`, 7 are verify-close (evidence posted,
left OPEN for the maintainer, none closed here), and 2 go to maintainer triage — 9 remain on
#168. Not closed.
