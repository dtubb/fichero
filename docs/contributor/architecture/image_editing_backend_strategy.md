(AI generated. Not reviewed.)

# Image Editing Backend Strategy at Scale

> Decision doc for #2061. Scope: backend image-editing strategy only.
> This is an architecture decision, not an implementation plan.

## Decision

Keep the current Pillow-centered backend as the canonical portable path, and
extend it with a small platform strategy layer:

1. **Pillow + PyMuPDF remain the default cross-platform implementation.**
2. **Quartz / Core Image become the Apple-native acceleration path** for
   preview rendering and high-throughput transforms when the backend is running
   on macOS.
3. **OpenCV stays an optional algorithmic helper, not the primary image engine.**
   Use it where it is materially better than Pillow for segmentation and
   foreground/background mask generation.

That split preserves the existing contract in
[`fichero-engine/src/fichero/api/routes/image_editing.py`](../../../fichero-engine/src/fichero/api/routes/image_editing.py)
while giving us a future native fast path on Apple without forcing a rewrite of
the current route or workflow tools.

## Why this is the right split

The current route already does the important product work:

- loads source pages and images
- applies non-destructive edit chains
- renders previews on demand
- persists per-document edit operations

The implementation is intentionally simple and portable. It uses Pillow for
image transforms, PyMuPDF for PDF page rasterization, and optional OpenCV /
`rembg` branches for the few operations that need them. That is the right
default for correctness and cross-platform behavior.

The workflow layer already exposes batch-friendly image tools under
[`fichero-engine/src/fichero/workflows/tools/`](../../../fichero-engine/src/fichero/workflows/tools/):

- [`prepare_images.py`](../../../fichero-engine/src/fichero/workflows/tools/prepare_images.py)
- [`rotate_images.py`](../../../fichero-engine/src/fichero/workflows/tools/rotate_images.py)
- [`enhance_images.py`](../../../fichero-engine/src/fichero/workflows/tools/enhance_images.py)
- [`fuzzy_clean_images.py`](../../../fichero-engine/src/fichero/workflows/tools/fuzzy_clean_images.py)
- [`remove_background_images.py`](../../../fichero-engine/src/fichero/workflows/tools/remove_background_images.py)
- [`segment_images.py`](../../../fichero-engine/src/fichero/workflows/tools/segment_images.py)
- [`split_images.py`](../../../fichero-engine/src/fichero/workflows/tools/split_images.py)

Those tools already model the shape we want at scale: per-file processing,
batch support, and append-only image edit metadata. The scaling work should
build on that seam, not invent a second editing stack.

## Per-operation decision matrix

| Operation | Canonical backend | Apple fast path | OpenCV role | Notes |
|---|---|---|---|---|
| Rotate | Pillow | Quartz / Core Image | None | Rotation is cheap; native acceleration is about throughput and preview fidelity, not correctness. |
| Crop | Pillow | Quartz / Core Image when cropping a rendered page or preview | None | Keep crop semantics identical across platforms. Crop should stay deterministic and not depend on GPU availability. |
| Enhance | Pillow | Core Image for preview/batch color transforms on Apple | None | Brightness/contrast/sharpen/autocontrast stay simple and portable. Use native acceleration only when it preserves the same visible result. |
| Segment | Pillow for glue + data handling | Not primary | OpenCV | Foreground segmentation is the one place OpenCV is genuinely the better fit today. |
| Background removal | Pillow for glue + alpha composition | Not primary | OpenCV for threshold/morphology; future local ML helper optional | OpenCV is the default algorithmic helper for masks. Keep any ML-based matting local and explicit. |
| Preview | Pillow / PyMuPDF fallback | Quartz / Core Image | None | Preview is the best place to use native Apple rendering because it maps to the UI and to PDF fidelity. |
| PDF render | PyMuPDF fallback | Quartz / PDFKit | None | Prefer native PDF rendering on Apple when available; keep PyMuPDF as the portability fallback. |

### Interpretation

- **OpenCV is not the general-purpose answer.** It is good for morphology,
  thresholding, connected components, and some CV-heavy cleanup. It is not the
  default engine for every image edit.
- **Quartz / Core Image are not the cross-platform answer.** They are the
  Apple-native answer for preview and accelerated transforms.
- **Pillow remains the contract.** It is the stable, dependency-light, portable
  baseline that keeps the route working everywhere Fichero runs today.

## Batch plan for thousands of images

The scaling rule is simple: never materialize the whole corpus in memory.

### Execution model

- Process images in **bounded chunks**, not whole folders.
- Load one source frame at a time, render it, write the derivative, then drop
  all references before moving to the next item.
- For PDFs, render only the required page. Do not decode all pages up front.
- Keep the edit chain declarative. The database stores operations; the backend
  replays them on demand instead of baking everything into a single huge asset.
- Use a worker pool bounded by available RAM, not by the number of source files.

### Memory ceiling

Target a **per-worker peak memory budget** and derive concurrency from it.
The right default is:

- one decoded image frame per worker
- chunk size chosen so the chunk fits comfortably inside free RAM
- no pipeline stage that keeps both the source frame and multiple full-size
  intermediates around longer than necessary

The precise numeric threshold can be tuned later, but the architecture should
assume that the safe answer is "smaller chunks, more passes" rather than "hold
everything and hope."

### Scaling shape

For thousands of images, the backend should prefer:

- a producer that enumerates source assets lazily
- a bounded transformer that applies one edit chain per item
- a sink that writes previews/derivatives immediately
- optional progress reporting at chunk boundaries, not per pixel operation

That makes the workload resumable, observable, and cheap to retry.

## GPU / native path

The native path should be treated as an **acceleration layer**, not a new source
of truth.

### Apple host

When the backend runs on macOS:

- use Quartz / Core Image for preview rendering
- reuse native image contexts where it helps
- wrap batch work in autorelease pools so large runs do not retain temporary
  objects longer than necessary
- prefer native PDF rendering for page previews and page images

### Other hosts

When the backend runs on Linux or another non-Apple platform:

- stay on Pillow + PyMuPDF for the same operations
- keep the edit chain behavior identical
- accept lower peak throughput in exchange for portability

### Future GPU boundary

Only move a transform onto GPU/native APIs if it is both:

- measurably faster for the user-visible workload
- visually equivalent to the portable path

That keeps preview acceleration safe without making the correctness contract
depend on Apple-only behavior.

## Cross-platform fallback

The fallback rule is:

- **portable first**
- **native fast path when available**
- **never cloud**

Practical consequences:

- every operation must remain available through Pillow/PyMuPDF
- Apple-specific acceleration must be optional
- OpenCV must stay optional and narrowly used
- a failure to load Quartz/Core Image or OpenCV must degrade cleanly to the
  portable path, not fail the whole edit surface

## Privacy and no-cloud posture

Image editing should have a stronger privacy posture than model inference:

- no cloud image processing by default
- no silent upload or remote fallback
- no external matting/segmentation service unless the user explicitly opts in
- all derived previews and edit artifacts remain local library data

This is a surface that can and should stay fully local. The current backend
already follows that posture; the strategy decision is to keep it that way.

## Pydantic / OpenAPI contract implications

The backend should keep the image-editing contract typed and stable.

### What must remain explicit

- request models for rotate, crop, enhance, background removal, and segment
- the edit-chain envelope
- preview response type
- any derived metadata that the frontend or workflow layer needs to round-trip

That matters because Fichero's OpenAPI contract is not just documentation. It is
the source of truth for generated clients and for backend/frontend round-trips.
If a field is not declared on the Pydantic model, it is easy to lose it later.

### Current route implication

[`image_editing.py`](../../../fichero-engine/src/fichero/api/routes/image_editing.py)
still stores edit operations as raw dictionaries inside `ImageEditChain`.
That is acceptable for the current implementation, but the architecture should
converge on a typed `ImageEditOperation` model if the edit surface grows or if
new metadata needs to survive round-trips.

### Batch implication

If a future bulk-edit route is introduced, it should accept a typed request
body with bounded counts and a clear per-operation schema. Do not smuggle
declared fields through `additionalProperties`.

## Future test plan

This decision should be protected with tests at three levels.

### 1. Operation semantics

Add/keep tests that verify:

- rotate preserves dimensions and EXIF behavior where expected
- crop rejects invalid bounds
- enhance preserves stable defaults for brightness, contrast, sharpen, and
  autocontrast
- segment returns deterministic bounding boxes and child document metadata
- background removal produces the expected alpha/compositing behavior
- preview returns the right MIME type for RGB vs RGBA outputs
- PDF preview renders the requested page and fails cleanly on out-of-range pages

### 2. Backend selection

Add tests that prove:

- Apple-native code is optional, not required
- the portable Pillow/PyMuPDF path remains the fallback everywhere
- OpenCV only activates for the operations that explicitly ask for it
- the local-only/no-cloud posture never routes image content off-device

### 3. Scale and regression

Add tests and bench-style checks for:

- chunked batch runs across hundreds or thousands of images
- memory-bounded execution that never loads the whole corpus at once
- repeated page rendering on PDFs without leaking file handles
- workflow image tools preserving `image_edit_operations` metadata across batch
  processing
- contract round-trips for the request/response models that feed generated
  clients

### 4. Platform-specific confidence

Where Apple-native code is added, keep it behind a test seam so the same test
suite can run with:

- the native strategy enabled
- the native strategy absent, forcing the portable fallback

That prevents the backend from becoming accidentally macOS-only.

## Bottom line

Do not replace the current image-editing route.

Keep **Pillow/PyMuPDF** as the portable baseline, add **Quartz/Core Image** as
the Apple-native fast path for preview and high-throughput transforms, and keep
**OpenCV** as a narrow helper for segmentation/background extraction. Build the
large-image batching story in the workflow tool layer, with bounded memory and
local-only execution as non-negotiable constraints.
