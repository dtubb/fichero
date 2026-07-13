# Image Editing / Preview Surface — Design (2026-07-12)

> **Daniel correction (2026-07-12), overrides the "Mount point" analysis below.**
> Edit CONTROLS live in the **document Inspector** (Photos/Lightroom-style:
> fine-grained detailed controls per action — contrast, rotate, dequantize,
> etc.). WHEN editing, the edit mode **also overtakes the Preview pane**, which
> becomes the live editing canvas showing the result. So: **Inspector = the
> controls; Preview = the live canvas during edit mode.** The functionality is
> "partly there but not properly exposed," and there is a real bug: entering
> edit today can turn the Preview **all black** (fix as part of exposing this).
> This supersedes the doc's earlier "editor stays a Preview-pane trailing panel,
> not the Inspector" recommendation — Daniel wants the controls IN the Inspector,
> with Preview as the canvas. Everything else in this doc (the hybrid
> client-CoreImage / server-truth architecture, the ImageEditChain as source of
> truth, the #3218 resolve_edited_source choke point, the parametric-vs-derived
> split) stands. See memory [[preview-reader-inspector-three-surfaces]].

Status: proposed direction, unreviewed. Resolves the design threads on
#3213 (Quartz evaluation), #1385 (AI-enhanced non-destructive editing epic),
#1174 (Lightroom-style stage-variant inspector), plus the two open technical
debts #3218 (edit chain is preview-only) and #1176 (parametric pipeline +
transient cache). Grounded entirely in the current implementation — no
rewrite proposed, per #3213's own conclusion.

## What already exists (the audit)

The image-editing surface is **already built and working**, not greenfield:

- **Engine**: `fichero-engine/src/fichero/api/routes/image_editing.py` — a
  single router that stores an ordered `ImageEditChain.operations` list per
  document (`fichero-engine/src/fichero/models.py:1008`) and renders
  `/images/{id}/preview?apply_edits=` on demand by replaying the chain in
  Pillow/PyMuPDF (`_apply_operation`, `_load_source_image`). Every mutating
  route is already wrapped in `asyncio.to_thread` (fixes the PIL-on-event-loop
  class of bug, #3216) and every mutation is already a registered, audited,
  undoable action (`@action("image.crop"...)`, EPIC #1848/#2014) whose inverse
  is simply "restore the previous `operations` list" — cheap because the
  chain **is** the document's edit state.
- **Reversible node model reconciliation is already partially done.** Two
  *different* non-destructive mechanisms coexist today, and they are
  correctly kept distinct rather than conflated:
  1. **In-place chain ops** (rotate/enhance/straighten/remove-bg/fuzzy-clean)
     mutate `ImageEditChain.operations` on the **same** document — a
     parametric pipeline replayed against the one source, exactly #1176's
     "non-destructive parametric image pipeline."
  2. **Structural derivation** (crop, split, segment) creates real **child
     `Document` rows** via `derived_from`/`crop_source_id`/`split_source_id`
     metadata + `bbox`, using the same reversible node model as split/group
     elsewhere in the app (`crop_image_child_impl`, `split_image_impl`,
     `_create_segment_documents`). Undo soft-deletes the children
     (`uncrop_image_child`, `unsplit_image`) — this is the general
     derived-child reversal contract, not a bespoke one.
- **Client**: `ImageEditorModel` (`fichero/fichero/Views/Library/ImageEditor/`)
  is an `@Observable` store that owns exactly one `ImageEditingServiceGenerated`
  (OpenAPI-generated) and renders **server-rendered PNG/JPEG bytes** for both
  the original and edited preview — there is **no client-side Core Image
  compositing today**. `ImageEditChainPanel` is already a Photos/Lightroom-
  style edit-history list (expandable steps, bidirectional canvas↔panel
  selection, re-apply-in-place) — #1174 is ~80% built already under a
  different name.
- **Mount point**: the editor is not a Reader tab. It replaces
  `DocumentCanvas` inside the **Preview pane** (`EditorView.swift`) behind an
  `isEditing` toggle, gated `macOS`-only
  (`supportsImageEditingPreview`). The reader IA doc
  (`docs/superpowers/specs/2026-07-11-reader-ia-design.md`, referenced from
  `ReaderTab.swift`) already documents "image edits" as absorbed into the
  Reader's **Page** tab in the long run, and the Inspector IA doc explicitly
  retires "Inspector View - Image Edits" as a milestone, confirming: **edit UI
  lives with the visual canvas (Preview/Reader), never the Inspector.**
- **Batch/workflow bridge already exists.**
  `fichero-engine/src/fichero/workflows/tools/image_edit_chains.py` —
  `append_image_edit_operations()` — lets *workflow* tools (batch, ML-driven)
  append to the same `ImageEditChain` rows the interactive editor writes to.
  This is the existing seam for #1385's AI tools; it is not a new mechanism.
- **The gap (#3218) is real and precisely scoped.** `resolve_source()` is the
  one function that returns the *original, unedited* file bytes, and it is
  called from: `storage.py` (thumbnails/display cache), `api/routes/storage.py`
  (`get_source_file`, display), `export_service.py`
  (`_require_image_source` for Markdown/DOCX export), and
  `vision_base.py`/Apple Vision OCR (`apple_vision_ocr_with_geometry` opens
  `image_path` directly via Quartz `CGImageSourceCreateWithURL`). **None of
  these call sites know `ImageEditChain` exists.** Only
  `GET /images/{id}/preview?apply_edits=true` ever renders the edited result.
  So today: editing a scanned page in the Preview pane changes nothing about
  what OCR transcribes, what gets exported, or what the thumbnail/display
  cache shows outside the editor. That is the bug to fix, not the whole
  storage layer.
- **The architecture decision for Quartz already exists** in
  `docs/contributor/architecture/image_editing_backend_strategy.md` (#2061):
  Pillow/PyMuPDF stays canonical; Quartz/Core Image is an **Apple-native
  acceleration layer for preview + throughput**, OpenCV stays a narrow
  segmentation/matting helper. #3213 does not need a new decision, it needs
  the **client-side half** of that decision (today 100% server-rendered) plus
  a concrete cache strategy.

## Decision — the hybrid architecture (#3213)

**Keep the server chain as the sole source of truth. Add a client-side Core
Image preview layer as a latency optimization only, never as a second
authority.**

### What renders where

| Concern | Owner | Why |
|---|---|---|
| **Truth**: what edits exist, in what order, with what params | `ImageEditChain` row on the engine (Pillow-replayable) | Already typed, audited, undoable, synced across devices via OpenAPI. Never move this client-side — it would fork state per device and break undo/audit. |
| **Interactive preview while dragging a slider** (brightness/contrast/sharpen/rotate angle) | **Client Core Image** (`CIFilter` chain over the already-fetched original bytes) | Sliders firing a network round-trip per tick is the #1401 async-crop-perf class of bug generalized. A local `CIContext` compositing brightness/contrast/sharpen/rotate over the cached original frame gives 60fps feedback with zero network chatter. |
| **Committed result** (the byte-identical, audit-quality frame OCR/export will read) | **Server** — re-render via the existing `_apply_operation` chain and persist `derived_path` | Guarantees the same-visible-result contract from #2061 across platforms and avoids Core-Image-vs-Pillow drift becoming the source of truth. The client preview is provisional; only the server's replay counts. |
| **Crop / split / segment marquee preview** | Client draws the overlay rect only (no pixel compositing needed) | Already how `ImageMarqueeOverlay` works — no change. |
| **Structural derivation (crop/split/segment commit)** | Server, unchanged | These already create real child Documents; no client-side approximation is safe here (pixel-exact bbox matters for downstream OCR/citation).|

### Concrete mechanism

1. `ImageEditorModel` keeps fetching the **unedited original** once per
   document (already does this: `originalPreview`). Add a lightweight
   `LiveEditPreview` helper (`CIFilter.colorControls` + `CIFilter.straightenFilter`
   composited via `CIContext(options: [.useSoftwareRenderer: false])`) that
   takes the original `CGImage` + the *in-progress* slider values and produces
   a live frame **without calling the backend**.
2. On slider release / tool commit (`enhance()`, `rotate()`, etc. in
   `ImageEditorModel`), the existing flow is unchanged: POST the operation,
   append to `ImageEditChain`, re-render via `_render_and_append`, refresh
   `editedPreview` from the server bytes. This is the "authoritative resync" —
   the client's provisional Core Image frame is discarded and replaced by the
   server's Pillow-rendered frame the moment the network round-trip lands, so
   the two can never silently diverge for more than one frame's worth of
   latency.
3. Crop/rotate-90/straighten/remove-background/segment/fuzzy-clean (discrete,
   one-shot ops, not continuously-dragged) **skip the client preview
   entirely** and keep going straight to the server — they don't need it, and
   remove-background/segment are OpenCV-only today with no Core Image
   equivalent worth building.
4. Add a **client-side eviction hook** identical to the existing
   `onEditApplied` → `storageService.invalidateImageCache` pattern already in
   `ImageEditorView.swift:97` — extend it so `LiveEditPreview`'s CGImage cache
   is also dropped whenever `documentId` changes or the chain resets.

### Cache strategy (server side, ties #1176's "transient cache")

`_write_derived_image()` currently writes to
`tempfile.gettempdir()/fichero-image-edits/{doc}/page-{n}/latest.{ext}` and
overwrites on every op — that's fine as a *display* cache but is not keyed to
chain state, so a stale `derived_path` can outlive the chain that produced it
across process restarts. Change to:

- Key the cache file by a hash of `(document_id, page, chain.updated_at)`,
  mirroring the existing **mtime-keyed thumbnail cache** pattern already in
  `storage.py` (`_thumbnail_cache_path` keyed off `source_mtime_ns`). This
  gives cheap invalidation without touching the DB schema.
- Treat the on-disk derived file purely as a render cache the same way
  thumbnails are — deletable/regeneratable, never authoritative. The
  authoritative artifact is always "replay `ImageEditChain.operations` against
  the untouched source."
- Bound cache size the same way the roadmap's batch-scale guidance already
  states (`image_editing_backend_strategy.md` "Batch plan for thousands of
  images"): one in-flight frame per worker, LRU-evict old `page-{n}` dirs.

### What this is NOT (per #3213's own conclusion)

- **Not a rewrite of `image_editing.py`.** Every `*_impl` function stays; the
  hybrid only adds a client compositing layer in front of the same server
  calls.
- **Not a move to Core Image as the source of truth.** Core Image never
  writes to `ImageEditChain`; it only renders a throwaway preview frame that
  gets replaced by the server's render.
- **Not a second edit-chain format.** No new "client chain" data structure —
  the live preview consumes the *same* `ImageEditOperation` params (angle,
  brightness, contrast, sharpen) the server already models, just evaluated
  locally for the in-flight frame.
- **Not a general cross-platform Core Image port.** Core Image is
  AppKit/UIKit-only; the portable Pillow/PyMuPDF path remains canonical for
  every platform and every committed result, per #2061.

## Reconciling the edit chain with the reversible node model

**An "edit" is not automatically a new derived child.** The model already
splits cleanly along an existing seam, and the design should keep that split
explicit rather than force everything into one shape:

- **Parametric, order-independent, fully-reversible-by-removal operations**
  (rotate, straighten, enhance, remove-background, fuzzy-clean) stay as
  **chain ops on the same document** — no new node, because there is nothing
  to "derive": the operation is a pure function of (source pixels, params),
  and reverting means deleting the op from the list. This is #1176's
  parametric pipeline, already implemented.
- **Structural, non-invertible-by-parameter operations that change the
  document graph** (crop-into-permanent-region, split-into-pages,
  segment-into-regions) stay as **derived children** via `derived_from` +
  `bbox`, because downstream references (annotations, entities, citations)
  need a stable child id to anchor to — you cannot anchor a claim to "crop
  step 3 of document X's chain," you need a document id. This already works
  today (`crop_image_child_impl`, `split_image_impl`,
  `_create_segment_documents`).
- **No change needed here.** The two mechanisms are not in conflict; they
  answer different questions ("what does this pixel-region look like" vs
  "what pixel-region is this"). The only actual gap is #3218 below — parametric
  chain ops on a document currently do not flow into what that document's
  *derived children* or *downstream consumers* see.

## Flowing edits to downstream artifacts (#3218)

The fix is **one new choke point**, not a rewrite of every caller of
`resolve_source`.

1. **Add `resolve_edited_source(doc, db, *, page=1) -> Path`** next to
   `resolve_source()` in `fichero-engine/src/fichero/storage.py`. It:
   - Calls `resolve_source()` for the raw bytes (unchanged).
   - Looks up `ImageEditChain` for `doc.id`; if empty, returns the raw path
     unchanged (zero-cost for the common no-edits case).
   - If non-empty, replays the chain via the *existing* `_apply_operation`
     logic (move that helper — already private in `image_editing.py` — into a
     shared module, e.g. `fichero-engine/src/fichero/image_ops.py`, so both the route and
     `storage.py` import the same replay code; **iterate, don't duplicate**)
     and writes/returns the cached derived path from the new mtime-keyed
     cache described above.
2. **Route call sites through it, one at a time, by consumer priority:**
   - `vision_base.py` / `apple_vision_ocr_with_geometry` and any LLM-vision
     transcription tool (`transcribe.py`) — highest priority: OCR/transcription
     must read what the user actually sees. Swap the raw `image_path` build
     for `resolve_edited_source`.
   - `export_service.py` `_require_image_source` — exports must ship the
     edited frame.
   - `api/routes/storage.py` `get_source_file` **stays on raw
     `resolve_source`** — this is explicitly "get me the original file," used
     by import/checksum/provenance flows that must never see edits. Do not
     touch it.
   - Thumbnail/display generation (`storage.py` `ensure_thumbnail`,
     `get_display`) — becomes edited by switching their internal `source =
     resolve_source(...)` line to `resolve_edited_source(...)`; this also
     fixes the existing "canvas outside edit mode still shows the original"
     inconsistency for good, once `StorageDisplayImageCanvas` calls the same
     preview endpoint.
3. **Contract clarity**: keep `/images/{id}/preview?apply_edits=` as the
   interactive editor's endpoint (original vs edited toggle needs BOTH), but
   make `apply_edits` default `True` project-wide for every *other* consumer
   — the "original" is now the edit-mode-only special case, not the default
   read path.

## Lightroom-style stage-variant inspector UX (#1174)

`ImageEditChainPanel` already delivers the core of this. To finish the
"stage variant" framing and fit the shared `SurfaceTabBar`/`MiniToolbar`
chrome:

- **Mount point stays the Preview pane trailing panel**, not the Document
  Inspector — consistent with the Inspector IA doc's explicit call that
  "image Edits leaves for the Reader canvas" and the retirement of the
  "Inspector View - Image Edits" milestone. Do not re-add an Edits tab to
  `DocumentInspector`.
- **Header strip** (`ImageEditChainPanel.header`) already matches
  `MiniToolbar<EmptyView, EmptyView>.standardHeight` — keep it, just apply
  `.inspectorGlassStrip()`/`.glassEffect` treatment already used by
  `DocumentInspector` for one visual system across all trailing panels.
- **"Stage" framing**: each `ImageEditOperation` row *is* a stage/variant
  step; the existing bidirectional `selectedStepIndex` binding between panel
  and canvas is exactly Lightroom's "click a history entry, canvas jumps to
  that state" behavior. The one addition worth making: a **thumbnail strip**
  above the step list showing the frame *before* vs *after* each committed
  step (small `CIImage`-rendered from the client cache in the hybrid model
  above — cheap, since the frames are already resident from live-preview
  compositing). This is additive to the existing `ImageEditChainPanel`, not a
  rewrite.
- **Compare mode already implements "original vs edited variant"**
  (`CompareMode.single/.wipe/.sideBySide` in `ImageEditorView`) — this is the
  Lightroom before/after slider; no new component needed, just keep it wired
  to the hybrid preview so the wipe view stays smooth during live slider drags.
- **Cross-platform**: today gated `#if canImport(AppKit)` / macOS-only via
  `supportsImageEditingPreview`. Extending to iPad/iPhone is a real, separate
  piece of work (touch-friendly marquee, popover→sheet for the enhance
  controls) — track as its own concrete issue, not folded silently into this
  design.

## Where AI/ML tools plug in (#1385)

The bridge already exists (`image_edit_chains.py`
`append_image_edit_operations`) — #1385's job is **adding tools that call it**,
not building new infrastructure:

- **Images**: port legacy ML tools (denoise, deskew-via-ML, super-resolution,
  auto-crop-border-detection, colorization) as new `_apply_operation` cases in
  the shared `image_ops.py` module (from the #3218 refactor above), each
  exposed as:
  1. A new `op` name in the chain vocabulary (parametric, reversible-by-removal
     — same shape as `enhance`/`fuzzy_clean` today), for interactive use from
     `ImageEditChainPanel`'s "Add Step" grid.
  2. A workflow tool under `fichero-engine/src/fichero/workflows/tools/`
     (mirroring `enhance_images.py`/`fuzzy_clean_images.py`) that calls
     `append_image_edit_operations()` for batch/automated runs, so the same
     op is available both interactively and via workflow automation with zero
     duplicated logic.
- **PDF pages**: `doc.docType == .page` already routes through the same
  `ImageEditorView`/`ImageEditChain` machinery (`_load_source_image` already
  branches on `.pdf` via PyMuPDF rasterization, `page` param threaded
  everywhere). AI tools need no PDF-specific plumbing — they operate on the
  rasterized page frame exactly like any image, and the derived-child crop/
  split model already applies per-page (`crop_image_child_impl` takes a
  `page` field).
- **Model execution stays local-first**, per the existing
  `image_editing_backend_strategy.md` privacy posture ("no cloud image
  processing by default") — route any local ML model through `mlx-lm-server`/
  local execution the same way the rest of the AI infra (#2056) does, not a
  new inference path specific to images.

## Milestone / issue reconciliation

**Concrete bugs to grind now** (no design blocker, small/bounded, matches an
existing pattern):

- **#3218** — add `resolve_edited_source()` + route OCR/transcribe/export/
  thumbnail-display through it. This is the highest-value fix; everything
  else in this doc is either already built or downstream of this.
- **#1176** — mostly already built (the parametric chain IS this); close as
  "verify and document" once the shared `image_ops.py` extraction lands, or
  re-scope narrowly to the cache-key-by-`updated_at` fix described above.
- Any small ML-tool port under #1385 that fits the existing `op` vocabulary
  shape (e.g. denoise, auto-crop-border) — grind these one at a time using
  the `enhance_images.py`/`fuzzy_clean_images.py` pattern; each is an
  independent, disjoint-file addition.
- Cross-platform iPad/iPhone image-editor enablement (removing
  `supportsImageEditingPreview`'s macOS gate) — bounded, but needs its own
  issue with explicit touch-target/gesture design; don't silently bundle it
  into a "make it work everywhere" catch-all.

**Design-gated (need this doc reviewed/approved first, or a follow-up
design pass)**:

- **#3213** — resolved by this doc: hybrid client-preview/server-truth
  architecture, no rewrite. Once approved, split into small PRs: (a) shared
  `image_ops.py` extraction (mechanical, low-risk, unblocks #3218 too), (b)
  `LiveEditPreview` Core Image compositor (net-new, needs its own tests for
  drift-vs-server-render), (c) cache-key-by-chain-`updated_at`.
- **#1174** — resolved by this doc: the panel exists, keep it in the Preview
  pane, add the before/after thumbnail strip. Needs a small follow-up spec
  only if Daniel wants the thumbnail-strip visual reviewed before building.
- **#1385** (the EPIC itself) — stays open as an umbrella; slice into
  per-tool issues as ML tools are actually ported, following the exact
  pattern above. Do not try to "complete" the epic in one PR.

**Zombies to check for retirement** (verify-before-close, not assumed dead):
any open issue under the "Image Editing" milestone whose description
pre-dates the `@action`/audited-registry migration (i.e., references a
plain non-audited crop/rotate/enhance route) is very likely already resolved
by the current `image_editing.py` — verify against the file before closing,
per the standing "verify-and-close before implementing" discipline.

## Cross-cutting contracts this design must not violate

- **Node model**: no third derivation mechanism; reuse `derived_from`/`bbox`
  exactly as split/crop/segment already do.
- **@Observable store as sole endpoint accessor**: `ImageEditorModel` stays
  the only thing calling `ImageEditingServiceGenerated`; the Core Image live
  preview is purely a rendering helper invoked *by* the model, never a
  parallel data path.
- **OpenAPI-only transport**: the hybrid adds zero new network calls (Core
  Image consumes bytes already fetched); no hand-rolled `URLSession`.
- **Shared chrome**: the edit-chain panel keeps the existing
  `MiniToolbar`/glass-strip treatment; no bespoke panel chrome.
- **Audited action layer**: every chain mutation (including future AI-tool
  ops) registers as an `@action` with `invert=_invert_image_chain`, exactly
  like the seven ops that already do this — new ops get undo for free by
  following the pattern, not by writing new undo logic.
