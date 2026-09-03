# Image Cleanup Quality Review — Remove Background & Clean Up

**Date:** 2026-09-02 · **Lane:** image-processing worker (Fable review, authorized by Daniel)
**Trigger:** live testing — Remove Background eats parts of the text along with the
ground; Clean Up / despeckle doesn't make pages easier to read.

---

## 1. The prior art (what the archive did)

The old project's image tools live at
`~/code/fichero_archive/_archive/fichero_legacy/tools/`. A folder named
*wcritos / wscritos / escritos* was **not found** anywhere under `~/code`,
`~/Documents`, or Spotlight; a full-code sweep for OpenCV cleanup calls
(`adaptiveThreshold` / `fastNlMeans` / `floodFill`) landed only on the legacy
tools folder — that folder is the prior art this review ports from. If the
wcritos work lives elsewhere (external drive, old machine), it is worth
recovering; nothing matching survives on this machine.

### `remove_background.py` — `BlackBackgroundRemoverMulti` (the one that worked)

The key property: **the mask is drawn at the PAGE level, never per pixel.**

1. Skip if <1% of pixels are dark (`gray < 80`) — no ground to remove.
2. Threshold at 80: paper → white, ground → black.
3. Find **external contours**; keep the large ones (≥20% of foreground or of the
   largest) plus anything near the image centre.
4. Draw the kept contours **filled solid** — so every ink stroke inside the page
   boundary is inside the mask by construction, regardless of its colour.
5. Morph open (5×5) + close (7×7), Gaussian-blur 21×21 → feathered alpha, ×0.95.
6. Crop to the alpha bounding box.

There was also an optional `rembg` (u2net) AI path with the OpenCV method as
fallback — subject-lifting was already recognized as secondary for documents.

### `enhance.py` — `DocumentAnalyzer` + `DocumentEnhancer` (the legibility pass)

- Classify handwritten vs typescript (OCR confidence, morphological stroke
  density fallback) and measure yellow cast (LAB b-channel).
- **CLAHE on the L channel** (clip 2.2, 8×8 tiles for handwriting; 1.6, 16×16
  for typescript) — local contrast, the actual legibility win.
- Gentle yellow-cast subtraction in LAB.
- Unsharp: `addWeighted(img, 1.5, blur, -0.5)`.

### `crop.py`

Page detection via `cv2.adaptiveThreshold(GAUSSIAN, 11, 2)` + contours (plus an
optional YOLO document detector). Not ported tonight; noted as the pattern for a
better auto-crop later.

### `fuzzy_clean.py` (legacy)

Was a **text** cleaner (LLM-transcript de-boilerplating) — the name migrated to
an image tool in the current app; the algorithms are unrelated.

---

## 2. What we did until tonight, and why it ate text

Two code paths, three implementations:

| Surface | Path | Default method |
|---|---|---|
| Image editor ("Remove background" button) | `/edits` chain → `media/image_ops.apply_operation` | `opencv`, falls back to `threshold` |
| Workflow tool | `workflows/tools/remove_background_images.py` (own copy) | `threshold` |

**Critical deployment fact:** OpenCV is deliberately NOT bundled in the embedded
Mac engine (`pyproject.toml` optional `image` extra). So in the shipping app
*both* surfaces fell through to the `threshold` method.

- **`threshold` (what Daniel actually ran):** alpha = per-pixel colour
  difference from the **corner pixel**. On a scan the corner is the paper, so
  every paper-coloured pixel went transparent — the entire page ground vanished,
  the counters inside letters vanished, and every anti-aliased or faint stroke
  edge within tolerance of the paper was eaten with it. Exactly the reported
  symptom: parts of the text go with the ground.
- **Workflow `opencv` (when cv2 present):** Otsu **inverse** threshold — the
  kept "foreground" was only the DARK pixels, i.e. it deleted the paper
  entirely, then a 3×3 morphological open ate the thin strokes too. Strictly
  worse than the archive's contour method for the same dependency cost.
- **Editor `opencv`:** already a simplified port of the archive contour method
  (good), but unreachable in the embedded app.

**Clean Up / despeckle:** `apply_fuzzy_clean` = `MedianFilter(3|5)` +
`ImageOps.autocontrast`. A scan's histogram already spans the full range (ink
gives the dark end, highlights the light end), so autocontrast is close to a
no-op; the median softens strokes slightly. Net effect: visibly "did something",
readability unchanged — the reported symptom.

---

## 3. What landed tonight (bounded, tested)

One shared owner, following the `media/image_flatten.py` precedent:

1. **`media/image_ops.remove_scan_background(image, threshold)`** — the
   magic-wand approach, pure PIL+numpy so it works in the embedded engine:
   flood-fill from the borders; only pixels within tolerance of the border
   colour (median of all border pixels, not one corner) **and connected to the
   border** become transparent. Ink strokes, the paper between them, and
   enclosed counters are interior → they survive by construction. Connectivity
   is computed at ≤1024px working size; similarity at full resolution keeps the
   page edge crisp. This replaces the corner-difference as the `threshold`
   method on BOTH surfaces.
2. **Contour method promoted to the shared owner** —
   `remove_black_background_opencv` (the archive port already in `image_ops`)
   is now what the workflow tool's `opencv` method calls; the Otsu-inverse
   implementation is deleted. cv2-absent falls back to the flood fill.
3. **`apply_fuzzy_clean` moved to `media/image_ops`** (was in
   `workflows/tools/fuzzy_clean_images.py`, imported backwards into media at
   call time per #3950 — that hack is now gone). `background_clean=True` now
   does **illumination flattening**: estimate the paper via downscale →
   grayscale-dilate (MaxFilter reaches past the ink) → blur → upscale, then
   divide the page by the estimate. Shadows, stains, yellowing and uneven
   lighting flatten to near-white while ink keeps full contrast — the legacy
   CLAHE intent in pure PIL/numpy. A light UnsharpMask follows. (Found while
   testing: autocontrast AFTER the flatten is actively harmful — a
   background-dominated histogram gets its paper stretched toward black — so
   the flatten path deliberately omits it.)

Behavioral tests (synthetic fixtures, `tests/unit/media/test_image_ops.py` +
updated `tests/unit/workflows/test_remove_background_images.py`): ink strokes
and enclosed counters survive remove-background; the dark ground goes; the
downscale flood path is exercised; speckles despeckle to paper while a 3px
stroke survives; a shadowed page top comes out as light as the bottom. The old
cv2 test that pinned the Otsu implementation shape was replaced by a behavioral
test of the contour method.

Both surfaces improve at once because the editor's `/edits` renderer and the
workflow tools now call the same functions — no client change needed.

## 4. Recommended per-case approach

- **Scans / photographed manuscript pages (our main case):** the border
  flood-fill (`threshold`) or, when cv2 is present, the contour lift
  (`opencv`). Both are page-preserving by construction. Subject-mask models
  (rembg, VisionKit) are the wrong tool here: they are trained to lift
  *objects* and routinely classify text as background texture.
- **Photo-like content (an object on a desk, a seal, a bookplate):** a
  subject-lifting model wins. The macOS route Daniel suspects —
  `VNGenerateForegroundInstanceMaskRequest` (what Finder/Preview use) — is
  attractive because it ships with the OS: zero bundle cost, unlike rembg's
  ~170MB u2net. It is Swift/pyobjc-side, though, and the engine must keep a
  pure-Python path for remote/iOS-serving engines. Honest assessment: worth
  adding as a **third method** (`vision`) via pyobjc behind the existing
  `method` seam, macOS-only, falling back to flood-fill — but NOT as the
  default for manuscript pages, and not tonight (needs live testing against
  the sandbox + pyobjc-framework-Vision is only in dev extras).

## 5. Unification map (editor ⟷ workflow tools)

Now (after tonight):

| Operation | Shared owner | Editor path | Workflow path |
|---|---|---|---|
| remove_background | `media/image_ops` (`remove_scan_background`, `remove_black_background_opencv`) | ✅ via `apply_operation` | ✅ delegates |
| fuzzy_clean / denoise | `media/image_ops.apply_fuzzy_clean` | ✅ | ✅ |
| flatten-for-JPEG | `media/image_flatten` | ✅ | ✅ |
| rotate/crop/deskew/binarize/levels | `media/image_ops.apply_operation` | ✅ | thin tools append chain ops (`adaptive_binarize_images`, `denoise_images`, `deskew_images`) — already unified |

Remaining duplication (report-only, for follow-up issues):

1. **`api/routes/ingest/image_editing.py` dead branch** — `_apply_operation`
   returns via `media/image_ops` on its first line, but ~500 lines of the old
   per-op implementations (including its own `_remove_black_background_opencv`
   and `_remove_background`) are kept below the `return` "temporarily for
   source compatibility". One test still imports the route-local copy. That is
   exactly the shim shape Rule 0 forbids; deleting the dead branch and
   repointing the test is a mechanical cleanup, but it's a big diff in an
   API file mid-lane — not done tonight.
2. **`enhance_images.py`** keeps its own brightness/contrast/sharpness loop
   while the editor's `enhance` op has an equivalent in `apply_operation`.
   Route `enhance_image_file` through
   `apply_operation(image, {"op": "enhance", ...})` next pass. Also worth
   considering: fold the illumination-flatten into `enhance` as the archive's
   CLAHE successor.
3. **`_save_image` + `_normalise_format`** are copy-pasted across
   `remove_background_images.py`, `fuzzy_clean_images.py`, `enhance_images.py`
   (and near-variants elsewhere). A `media/` save helper (which would also be
   the single place that calls `flatten_for_opaque_format`) is the flatten-
   sweep's natural sequel.

## 6. Explicitly deferred (too risky for tonight)

- Deleting the image_editing.py dead branch (above).
- The `vision` (VisionKit) method for photo-like content (above).
- CLAHE proper + yellow-cast correction as an `enhance` upgrade — needs cv2 or
  a numpy CLAHE; the illumination flatten covers most of the same ground for
  scans, so measure on real pages first.
- Auto page-detection crop from the archive's `crop.py` (adaptive threshold +
  contours) as an `auto_crop_border` upgrade — the current `detect_content_bbox`
  is a naive `> 20` luminance scan in pure Python (O(w·h) getpixel loop; slow
  and dark-ground-only).
- rembg model choice/caching (archive cached u2net under resources): moot until
  we decide to ship rembg at all; it is absent from the embedded engine today.
