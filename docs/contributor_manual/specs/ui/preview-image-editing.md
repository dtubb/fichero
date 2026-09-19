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

## PASS 2 fold plan (not executed — no issues moved)

Legacy milestone **#168 "Preview - Image Editing"** (16 open issues) is this spec's own
milestone's predecessor, not yet read issue-by-issue against the behaviors above — that
reading is Pass 2's job. Recommend the same discipline the last three folds used: read every
BODY fresh (not just titles), verify "looks already built" claims against the substantial
test coverage found in this pass (`ImageEditStepEditingTests`, `ImageEditChainSyncTests`,
`ImageEditRenditionRefreshTests`, `ImageEditClipboardTests`, `TestReversibleImageCrop`/
`TestReversibleImageSplit`, `TestQuarterTurnsAreLossless` already cover a wide slice of the
step-chain/caching/clipboard mechanics — several of #168's older issues may be verify-close
candidates rather than fresh GAPs), and watch for issues that are actually about
`preview-surface.md`'s territory (mounting/dispatch) or `preview-magnifier.md`'s (the loupe
inside the editor canvas) rather than the editing operations themselves. Not done in this
pass — Pass 1 was the ask.
