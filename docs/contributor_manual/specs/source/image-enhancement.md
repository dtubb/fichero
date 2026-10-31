# Source Model — Image enhancement: page images made easier to read, as nodes, editor tools and renditions — Design Spec (#6185)

> Milestone: image-enhancement
> Manual: TBD — a section, "Enhancing page images", explaining what Fichero can do to a photograph or scan
> before reading it (crop to the page, straighten, split, lift the ink, even out stains, quiet ruling and
> show-through), that the original is never changed, how to preview and undo it on one page or a folder,
> and how to see whether it helped.
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code makes them pass.
> **Status: DRAFT — ruled 2026-10-29, ready to build; the APPROVED tag waits on the manual section and the first pinning test** (drafted 2026-10-26; trimmed 2026-10-29 to its own line,
> see the review `agent-work/status/briefs/imgprep-review-2026-10-29.md`; the owner's ruling of 2026-10-29
> that the FULL OpenCV suite comes over, as automatic steps and as editor options, folded in the same day:
> see "The suite, step by step"). **This spec owns the pixel steps that write renditions** (contrast,
> yellowing, sharpen, stains, ruling, show-through, binarise, denoise, the show-through-only verso, the
> working rendition, the reader prompt fragments) and the rule that one function stands behind every door. **`image-preparation.md`** (#5382) owns the Set Up step: finding the
> page, the page box, split, turn, straighten, blanks, the worklist, the detectors and their training, the
> time shown before Start (`prep.*`). **`../ui/preview-image-editing.md`** section T owns the editor's tools
> (`preview.edit.tool.*`). Where a line below was a twin of a `prep.*` line it now says so and defers; the
> id is kept so the issues that cite it resolve. `recipe-designer.md` owns the Leave Out stage
> (`designer.clean.leaves-out-non-text`, #6070).
> Tags: [OK] built · [GAP] not built · [PARTIAL] exists elsewhere / not wired · [BROKEN] built, wrong.

## Intent

The archive's pages are hard: a wooden ruler and a colour card beside the paper, a wide dark mount, torn
and holed edges, water and mould stains, faint ink, green ruling, revenue stamps over the text, and the
other side's writing showing through mirrored and faint. The old command-line Fichero cleaned such pages
with OpenCV and the result was good enough to read for years; the new app has an Enhance button that does
less, three sliders over PIL. This spec ports **the methods and parameters** of the old tools into the
engine as **typed steps** written to the app's rules, and leaves the old app's shape behind. The owner's
ruling of 2026-10-29: the whole suite, not levels; every step both runs by itself as a recipe step that
makes a rendition and is a control in Preview's editor with a slider and before/after. Port, do not
rewrite: each step below names the function it comes from.

Two steps, kept distinct (owner 2026-10-26):

1. **Image enhancement** (this spec) makes a page easier to read and **writes renditions**: crop to the
   page, rotate and deskew, split a spread, lift contrast, even out stains, quiet ruling, suppress
   show-through. It never decides what is ignored.
2. **Leave Out** (`recipe-designer.md`, #6070, `recipes/leave_out.py`) decides what is **not read**: the
   ruler, the colour card, the mount, specks, show-through lines, stamps where wanted, show-through-only
   versos. It never changes pixels.

Order of a run: **enhance → find regions and lines (one pass) → leave out → read.** Enhancement writes the
`page_box` Leave Out reads and the rendition whose ink contrast Leave Out measures.

## What exists today

- **Three systems the steps must plug into.**
  - *Workflow nodes* (`workflows/tools/*_images.py`, registered in `registry_builtins.py`): `split_pages`,
    `split_images`, `rotate_images`, `deskew_images`, `auto_crop_border_images`,
    `remove_background_images`, `adaptive_binarize_images`, `denoise_images`, `enhance_images`,
    `fuzzy_clean_images`, `prepare_images`; each runs on a page, folder or project and persists its outputs
    as renditions through `image_edit_chains.persist_workflow_renditions` (paired by source path, bytes
    copied under library storage). Pinned by `tests/unit/workflows/test_*_images.py`.
  - *Editor operations* (`api/routes/ingest/image_editing.py`, `preview.edit.*`): a per-page chain of
    reversible rows; crop, rotate, straighten, enhance, remove background, segment, flip, auto levels,
    grayscale, auto crop border, adaptive binarize, denoise, fuzzy clean; preview rendered on demand;
    batch-apply over a folder for crop and split with whole-batch undo (#1265).
  - *Renditions* (`models.Rendition`: `id, document_id, role, path, is_primary`; `api/routes/document/renditions.py`;
    the app's `RenditionService` flips "from least to most processed" and a reader records the
    `rendition_id` its geometry was measured on, `llm/kraken_runtime.py`). The import makes a thumbnail
    (1024 px) and a display image (2200 px, `db/storage.ensure_display`) per page.
- **The Enhance button today** (editor and engine, `_apply_operation("enhance")`): PIL only — optional
  median denoise, optional `ImageOps.autocontrast`, then `ImageEnhance.Brightness`, `Contrast`,
  `Sharpness` by three sliders (default 1.0 each: a no-op). `enhance_images` the node is the same two PIL
  calls. Nothing local: a stain and the ink beside it get the same stretch.
- **Leave Out** (`recipes/leave_out.py`, #6070): reasons `too small`, `off the page`, `likely bleed-through`;
  `off the page` needs the document's `page_box` metadata and **nothing writes it today**; `likely
  bleed-through` needs an ink-contrast reading of the line and is skipped where there is none.
- **Reader prompts**: `llm/line_reader.PROMPT` already says *answer null for a ruler, graph paper, blank
  paper, a smudge* and *leave out fragments of lines above and below*; it says nothing about mirrored
  show-through or stamps. The wording is a constant, not versioned, not recorded on the run, not
  editable per project. `recipes/review_profiles.review_prompt` is the only per-lens prompt builder.
- **Leaves and blank versos**: `finding-documents.md` pairs pages into leaves before anything else; a blank
  verso is not a document and show-through on a blank verso "can be read mirrored and matched to its
  recto" (§ leaves). Nothing marks a page as show-through-only yet.

## What exists and what changes

Every piece of code that touches a page image today, and what this spec does to it. "Upgrade" means
the existing door stays and calls the new function with the same parameters; "replace" means the new
step takes the door and the old code survives only for chains that already carry it.

| Where | File | Today | Change | Behaviour | Issue |
| --- | --- | --- | --- | --- | --- |
| Editor: Crop | `fichero/fichero/Views/Preview/ImageEditor/ImageEditorView+Toolbar.swift`, engine `_action_crop` in `fichero-server/src/fichero_server/api/routes/ingest/image_editing.py` | a hand-drawn box, reversible row | becomes the page-box tool with handles and *Find Page* (`../ui/preview-image-editing.md`, `preview.edit.tool.crop-is-a-page-box`) | `prep.find-the-page` | #6188 |
| Editor: Rotate, Straighten | same files, `_action_rotate`, `straighten` | quarter turns; `straighten` by a typed angle | Straighten becomes a dial with *Auto*; the `angle` popover goes (`preview.edit.tool.straighten-is-a-dial`); the angle is recorded (`prep.straighten-and-flatten`) | `image.enhance.rotate-deskew` | #6190 |
| Editor: Enhance | `ImageEditorView+Popovers.swift` (three sliders + Auto Levels), engine `_apply_operation("enhance")` | PIL brightness, contrast, sharpness, autocontrast, median denoise | **replace**: Auto Enhance (one click, `contrast` at its defaults) and Adjust (sliders per step, live before/after, `preview.edit.tool.adjust-previews-live-before-after`); old op kept as `legacy_enhance` for existing chains only | `image.enhance.editor-enhance-is-the-new-step` | #6190 |
| Editor: Remove Background | `_remove_background` in `image_editing.py`, `media/image_ops.remove_black_background_opencv`, `remove_scan_background` | black-mount mask, scan-border mask | leaves the toolbar; becomes the dark-mount method of find-the-page (`prep.page.remove-background-is-the-dark-mount-method`) | `preview.edit.tool.retired-ops-still-render` | #6188 |
| Editor: Segment, Fuzzy Clean | `_segment_image`, `media/image_ops.apply_fuzzy_clean` | cuts strips; a local "fuzzy" clean | both leave the toolbar: Segment changes no pixel (regions are Find Regions'); Fuzzy Clean folds into `stain-flatten`; old rows still render (`preview.edit.tool.retired-ops-still-render`) | `image.enhance.stain-flattening` | #6195 |
| Editor: flip, auto levels, grayscale, auto crop border, adaptive binarize, denoise | `_PARAMETERLESS_OPERATIONS`, `DenoiseOperationRequest` | parameterless rows | keep; auto crop border calls the fast `detect_content_bbox` | `image.enhance.rotate-deskew` | #6190 |
| Editor: batch over a selection | `ImageEditorModel.batchApply`, `POST /api/images/batch-apply`, `…/{batch_id}/undo`, `/crops/batch` | crop and split only, whole-batch undo | upgrade to every step, three-page preview, per-page record; the sheet is `preview.edit.tool.*`'s Apply to Selection; a Set Up correction applied to a folder uses it (`prep.check.apply-correction-to-the-folder`) | `image.enhance.batch-preview-undo` | #6192 |
| Editor: chain, preview, revert | `GET/PUT/DELETE /{id}/edits`, `/preview`, `RenditionService+EditStates.swift` | reversible rows, on-demand preview, cache | keep; a row gains `method`, `confidence`, `who` | `image.enhance.rendition-records-its-steps` | #6191 |
| Nodes: `enhance_images`, `prepare_images` | `fichero-server/src/fichero_server/workflows/tools/enhance_images.py`, `prepare_images.py` | PIL contrast/sharpness; grayscale + autocontrast | **replace** by the `contrast` node; `prepare_images` becomes the ordered sequence of the new steps | `image.enhance.contrast-clahe` | #6190 |
| Nodes: `deskew_images`, `rotate_images`, `auto_crop_border_images` | `workflows/tools/deskew_images.py`, `rotate_images.py`, `auto_crop_border_images.py`; `media/image_ops.detect_deskew_angle`, `detect_content_bbox` | Hough median; EXIF or typed angle; per-pixel bbox loop | upgrade: call the one function; bbox in NumPy | `image.enhance.rotate-deskew` | #6190 |
| Nodes: `split_pages`, `split_images` | `workflows/tools/split_pages.py`, `media/page_split.py`; `split_images.py` | Vision outline + darkest column; fixed grid | upgrade `split_pages` (neighbour test); keep `split_images`; owned by `prep.split-at-the-gutter` | `image.enhance.split-spread` | #5382 |
| Nodes: `remove_background_images`, `adaptive_binarize_images`, `denoise_images`, `fuzzy_clean_images` | `workflows/tools/*.py` | one op each | `remove_background` → page-crop's dark-mount method; binarize and denoise keep; fuzzy clean → `stain-flatten` | `image.enhance.stain-flattening` | #6195 |
| Nodes: persistence | `workflows/tools/image_edit_chains.persist_workflow_renditions`, `workflows/tool_outputs.py` | pairs outputs by source path, copies bytes, one rendition per page | keep; writes `role: enhanced` and `metadata.steps` | `image.enhance.rendition-records-its-steps` | #6191 |
| Recipe stage: Prepare Images | `fichero-server/src/fichero_server/recipes/stages.py` (`prepare-images`), `assemble.py` (`split-pages` built-in), `jobs.py` (`prepare-the-image`) | the answer is stored; only `split-pages` runs | owned by `image-preparation.md`: three questions suggested from a sample, what runs by itself, the time before Start (`prep.setup.*`, `prep.estimate.*`) | `image.enhance.onboarding-step` | #5580 |
| Recipe stage: Leave Out | `fichero-server/src/fichero_server/recipes/leave_out.py` | `too small`, `off the page` (needs `page_box`, never written), `likely bleed-through` (needs contrast) | upgrade: reads `page_box` from page-crop, contrast from the rendition, new reasons | `image.enhance.leave-out-reads-the-page-box` | #6198 |
| Reader prompt | `fichero-server/src/fichero_server/llm/line_reader.py` `PROMPT`, `_page_context_uri` | one constant; page context re-rendered from the full page per batch | upgrade: fragments appended by id; page context from the working rendition | `image.enhance.reader-prompt-fragment`, `image.enhance.working-rendition-once` | #6199, #6200 |
| Derivatives at import | `fichero-server/src/fichero_server/importers/derivatives.py` `_thumbnail_stage_body`, `queue_derivatives`; `db/storage.ensure_thumbnail`, `ensure_display`, `_generate_image` | `Image.open` the full file then `img.thumbnail(LANCZOS)`; cache keyed by document id and path; no `draft()`; display 2200 px made the same way; a run or a view can call `ensure_*` again | upgrade: ONE working rendition, rendered once with shrink-on-load, keyed by content hash and size; thumbnail cut from it; nothing re-renders | `image.enhance.working-rendition-once` | #6200, #6193 |
| Display in the app | `fichero/fichero/Services/RenditionService.swift`, `RenditionService.swift` | fetches display/thumbnail by document id | keep; reads the working rendition by its key | `image.enhance.working-rendition-once` | #6200 |
| Legacy | `fichero_archive/_archive/fichero_legacy/tools/*` | not in the engine | never imported; methods restated | `image.enhance.old-conventions-left-behind` | #6194 |

## The legacy methods, read closely (2026-10-26)

`fichero_archive/_archive/fichero_legacy/tools/` — a CLI app with an `assets/<stage>/` folder per step and
a JSONL manifest per stage. **Only the methods come over.** The evidence run is under
`agent-work/status/briefs/image-prep-samples/` (two typed pages of the Nicolasa Blandón file: the legacy
crop as *before*, the legacy enhanced file on the drive as *reference*, the method restated and re-run,
and today's Enhance at auto-levels, contrast 1.3, sharpen 1.3; `notes.json` has the timings). The
restated method matches the reference to a mean of 1.4/255 — JPEG noise — so the parameters below are
the ones that made the owner's "good result".

| Tool | Input → output | Method and parameters | Keep |
| --- | --- | --- | --- |
| `crop.py` | photo → page crop + box, method, confidence | YOLOv8 page model first (best box, 30 px pad left/top/bottom); else contours: grey, optional blur, threshold by template (`dark_background` binary 120, `light_background` inverse 180, `otsu`, `adaptive` 11/2, `edge` Canny 50/150 + dilate), external contours, keep area 0.15–0.99 and aspect 0.5–2.0, largest, pad; else the original | the templates and filter; YOLO optional |
| `remove_background.py` | photo → RGBA + crop | black coverage check; threshold 80; external contours; keep by size/centre; mask open 5, close 7, blur 21; crop to alpha | the mount mask as the dark-mount page finder |
| `enhance.py` | page → page | LAB; CLAHE on L (clip 2.2, tile 8×8, then ×1.1 −5 for "handwritten"; clip 1.6, tile 16×16 for "typescript"; the stroke-density heuristic calls nearly every page handwritten — both typed samples scored 8 %, threshold 0.5 %); yellow cast from mean b: subtract min(8, 3·cast), a ×0.98; unsharp 1.5/−0.5 at σ 3 | all of it, as one setting |
| `rotate.py` | page → page | Hough lines within ±2°, median, warpAffine white fill | today's `detect_deskew_angle` is the same idea (±15°, longer lines) |
| `split.py` | spread → pages | aspect gate; darkest column in the middle 40 %; split only if darker than 180 and 15 darker than its neighbours; covers and labels by edges and filename | the aspect gate and the neighbour test |
| `segment.py` | page → line strips | deskew by three methods voted with a confidence (`deskew_image`: text baselines `get_text_baseline_angle`, Hough `get_hough_angle`, the largest contour's `minAreaRect`; disagreement makes it conservative; ±2°; expand-and-crop so nothing is cut off); connected-component lines (`get_connected_component_lines`: Otsu inverse, external contours, boxes); safe cut points by row projection | the baseline fit and the component lines feed the dewarp (`prep.flatten.curve-toward-the-gutter`); the three-method vote is the deskew's confidence (`prep.straighten-and-flatten`); the Tesseract `validate_rotation` is not ported (no Tesseract in the app) |
| `prepare_images.py` | photo → JPEG | EXIF rotation, compression | nothing (`media/upright.py`) |
| `fuzzy_clean.py` | text → text | repeated-phrase and line cleaning of transcriptions, no pixels | nothing here (it is text, not image, despite the engine's `fuzzy_clean` op sharing the name) |
| `enhance.DocumentAnalyzer` | page → `document_type`, `is_yellowed` | type by Tesseract confidence, else stroke density (`_morphological_heuristic`: gradient of the Otsu binary, over 0.5 % = handwritten); yellowing from the LAB b mean (`_detect_yellowing`: (b − 128) / 30, clamped 0–1) | the yellowing measure as the suggester for `yellowing`; the stroke-density heuristic as the suggester for `contrast`'s profile, with the honest note that it calls nearly every page handwritten; Tesseract is not ported |

**What the legacy did not do, despite the memory of it:** no stain flattening (CLAHE evens the lighting
around a stain; the stain stays, as the reference shows), no ruled-line handling, no bleed-through
handling, no blank or verso detection. Those are new below, model-free, and short.

**What the legacy did wrong and the port does not:** files written beside the originals with no link
back; one folder layout and manifest per stage; crop before everything (so a loose YOLO box, as on
sample 011, was never re-done); a "handwritten/typescript" switch that never switched; no preview, no
undo, no per-page parameters.

## The design

### One function, three doors

Each step is **one engine function** `media/enhance/<step>.py: run(image, params) -> (image, account)`
with a typed `params` model. The same function is reached through three doors with the same parameters:

| Door | Where | Scope | Writes |
| --- | --- | --- | --- |
| Workflow node | `workflows/tools/<step>.py`, in the registry; a recipe's Prepare Images step and the Start plan name it | page, folder, project | a rendition per page via `persist_workflow_renditions`, with the run id |
| Editor operation | `api/routes/ingest/image_editing.py` `operations/<step>`; the editor's tool, sliders from the params model | one page (chain row), or a multi-selection (batch) | a chain row; the batch stamps its id on each row |
| Rendition | `models.Rendition` with `role: "enhanced"` and `metadata.steps: [{step, params, method, confidence, run_id|batch_id|person}]` | the page | several renditions coexist; the viewer switches; a reader names which it read |

Rule of thumb: a parameter that exists in one door exists in all three, from one Pydantic model, so the
OpenAPI client and the node config cannot drift.

### The steps, in their usual order

The geometric steps (find and crop the page, square, flatten, rotate and deskew, split) are `prep.*`
in `image-preparation.md`; this spec keeps for them only that each is a rendition recorded with its method
and confidence. The pixel steps that follow run in this order when a recipe runs them all, and each is
also one control in the editor's Adjust:

1. **Contrast** (`contrast`) · 2. **Yellowing** (`yellowing`) · 3. **Stains** (`stain-flatten`) ·
4. **Ruled lines** (`ruled-lines`) · 5. **Show-through** (`bleed-through`) · 6. **Denoise**
(`denoise`) · 7. **Sharpen** (`sharpen`) · 8. **Binarise** (`binarise`, last, and only for a reader
that wants it) · and, not pixels, 9. **Show-through-only verso** (`verso-mark`).

Each step: previewed on three sample pages (first, middle, last) before a folder runs; undone per page
(delete the row) or as a batch (`batch-apply/{id}/undo`); recorded on the rendition with its parameters.
A recipe's Prepare Images step writes **one** `enhanced` rendition per page carrying the ordered steps,
not one rendition per step; the editor's Adjust writes one chain row per applied step, and the chain
renders to the same pixels as the recipe would for the same values (`image.enhance.three-doors-one-function`).

### The suite, step by step (owner 2026-10-29: the full OpenCV suite, ported not rewritten)

For every step: **Source** is the function the port starts from (the legacy tree
`fichero_archive/_archive/fichero_legacy/tools/`, or today's engine), named so the builder copies its
method and parameters; **Params** are the one Pydantic model behind the three doors, with defaults;
**Runs by itself** says when the recipe applies it without being asked; **Editor** is its control in
Adjust (`preview.edit.tool.adjust-previews-live-before-after`): every control has an on/off switch, its
sliders, a live preview on the picture and the Before hold; **Rendition** is what it writes; **Test** is
its pinning check. "No legacy source" is said where the legacy had nothing, so nobody looks for it.

| Step | Source | Params (default) | Runs by itself | Editor | Rendition | Test |
| --- | --- | --- | --- | --- | --- | --- |
| **Contrast** `contrast` | `enhance.DocumentEnhancer.enhance`, step 1: LAB, `cv2.createCLAHE` on L, then `cv2.convertScaleAbs(l, 1.1, −5)` for handwriting; the typescript branch is clip 1.6, tile 16, no gain | `clip` 2.2 (1.0–4.0) · `tile` 8 (4–16) · `gain` 1.1 (0.8–1.4) · `lift` −5 (−20–20) · `profile` handwritten \| typescript (handwritten; the typescript profile sets clip 1.6, tile 16, gain 1.0, lift 0; suggested by the stroke-density heuristic, which nearly always says handwritten, so the person's answer wins) | yes when Set Up's answer is "stained or faded", and for every page the bake-off shows it helps (`prep.judged-by-reading`); the engine's one-click Auto Enhance is this step at its defaults | *Contrast*: Strength (clip), Detail (tile), Gain, Lift; a Handwritten / Typescript switch | `enhanced` with `steps[].step: contrast` | the two typed samples reproduce the reference enhanced files to a mean under 3/255 (`image.enhance.contrast-clahe`) |
| **Yellowing** `yellowing` | `enhance.DocumentAnalyzer._detect_yellowing` (cast = (mean b − 128) / 30, clamped 0–1) and `DocumentEnhancer.enhance` step 2: `cv2.subtract(b, min(8, 3·cast))` when cast > 0.1, `cv2.convertScaleAbs(a, 0.98, 0)` | `strength` auto (0–8, the subtraction in LAB b; auto = min(8, 3·cast)) · `desaturate_a` 0.98 (0.9–1.0) | yes when the five-page sample's mean cast is over 0.1 on 3 of 5 (the "stained or faded" answer); a page with cast under 0.1 writes nothing | *Yellowing*: Strength, with "Auto" ticked by default | the same `enhanced` rendition, `steps[].step: yellowing` | a page tinted by a known b offset comes back within 2 of neutral in b; a neutral page is unchanged |
| **Stains** `stain-flatten` | today's `media/image_ops._flatten_illumination` (PIL: MaxFilter 7 at 1/8 scale, GaussianBlur 4, divide, ×245) restated in OpenCV: `cv2.morphologyEx(MORPH_CLOSE)` on L with an elliptical kernel of long side / 40, blur, divide, rescale to the paper's median; no legacy source (the legacy CLAHE evened the light around a stain and left the stain) | `kernel` long side / 40 (1/80–1/20) · `strength` 1.0 (0–1, a blend with the input) · `paper` auto (the median of the top 20 % of L) | yes when Set Up's answer is "stained or faded"; the Fuzzy Clean op's `background_clean` folds into it | *Stains*: Strength, Size (kernel) | `steps[].step: stain-flatten` | a painted stain's mean is within 10/255 of clean paper after; the ink's dark pixels (under the local background by more than the paper noise) are unchanged (`image.enhance.stain-flattening`) |
| **Ruled lines** `ruled-lines` | no legacy source; new: coloured ruling by an HSV hue mask (green, blue, red bands) kept where thin (under 3 px) and long (over 30 % of the page), filled with `cv2.inpaint` radius 3; grey ruling by `cv2.HoughLinesP` with the legacy `rotate.hough_line_rotate` parameters (threshold 100, min length 100, gap 10) kept where thin and horizontal | `colour` auto \| green \| blue \| red \| none (auto) · `grey` off · `max_width` 3 px · `min_length` 0.3 · `inpaint_radius` 3 | **off** until Set Up's answer is "ruled or graph paper" AND the bake-off shows it helps this collection (ruling 2026-10-04: some models use the ruling as a guide) | *Ruling*: on/off, Colour, Strength (max width) | `steps[].step: ruled-lines` | drawn green ruling over text is gone, the ink's dark pixels unchanged, in `test_enhance_stains_and_ruling.py` (`image.enhance.ruled-lines`) |
| **Show-through** `bleed-through` | no legacy source; method A: after stains, an ink threshold on local contrast (`cv2.adaptiveThreshold`-style local mean minus `k`·local std, the Sauvola idea in OpenCV calls) pushes faint mirrored text to paper; method B when the verso is in the folder: mirror it, `cv2.findTransformECC` on the downsampled pair, subtract the registered copy scaled by a fitted gain | `method` A \| B (A; B offered when the leaf's verso is present) · `k` 0.2 (0–0.5) · `window` long side / 60 · `gain` auto (B) · `scope` whole \| regions (whole; see the show-through ruling below) | yes when Set Up's answer is "writing shows through" | *Show-through*: on/off, Strength (k), Method A/B, Whole page / By region | `steps[].step: bleed-through` with `scope` and, by region, the tile grid and gains | the synthetic recto/verso pair: mirrored faint text under the paper noise, ink stroke width unchanged (`image.enhance.bleed-through-suppression`) |
| **Denoise** `denoise` | today's `media/image_ops.apply_fuzzy_clean` (PIL MedianFilter 3 or 5) restated as `cv2.medianBlur`; specks by the legacy `remove_background.BlackBackgroundRemoverMulti` mask hygiene (`cv2.morphologyEx` open 5×5 then close 7×7) applied to the ink mask, so an isolated blob smaller than the open kernel goes and strokes stay | `radius` 3 (3 \| 5) · `speck` 5 px (0–9; 0 off) | no; on when a person asks, and in the recipe only where the bake-off shows it helps (specks mislead a segmenter more than a reader) | *Denoise*: Radius, Specks | `steps[].step: denoise` | a page with 1 % salt-and-pepper noise comes back with under 0.05 % and the ink's component count unchanged |
| **Sharpen** `sharpen` | `enhance.DocumentEnhancer.enhance` step 3: `cv2.GaussianBlur(σ 3)` and `cv2.addWeighted(1.5, −0.5)` | `amount` 0.5 (0–1.5) · `radius` 3 (1–6) | yes, as the last pixel step of Contrast's automatic run (the legacy did them together); never twice | *Sharpen*: Amount, Radius | `steps[].step: sharpen` | the typed samples' reference match counts it; a flat grey page is unchanged |
| **Binarise** `binarise` | `crop.py`'s threshold methods (`otsu`: `cv2.threshold(THRESH_OTSU)`; `adaptive`: `cv2.adaptiveThreshold(ADAPTIVE_THRESH_GAUSSIAN_C, 11, 2)`), `segment.get_connected_component_lines` (Otsu inverse); today's `apply_operation("adaptive_binarize")` is a global mean threshold wearing the adaptive name and is replaced | `method` otsu \| adaptive (adaptive) · `block` 31 (11–101, odd; the legacy 11 was for small images) · `c` 2 (−10–10) | no; the recipe runs it only for a reader card whose sheet says it reads a binary image (Kraken's own binarisation stays Kraken's) | *Binarise*: on/off, Method, Block, Offset | `steps[].step: binarise`, a separate rendition `role: binarised` so the enhanced greyscale stays | the Doc11 crop binarised by Otsu and by adaptive: the ink's component count within 5 % of the greyscale's; an old `adaptive_binarize` chain row re-renders to its old pixels |
| **Mount removal** (the dark-mount page finder) | `remove_background.BlackBackgroundRemoverMulti.remove_background` (threshold 80, skip under 1 % black, external contours, keep the largest and any over 20 % of it or near the centre, open 5 close 7, blur 21, alpha ×0.95, crop to alpha) | owned by `prep.page.opencv-default-yolo-optional` and `prep.page.remove-background-is-the-dark-mount-method` | yes, as the finder's dark-mount method | Crop's *Find Page* | the page crop; transparency flattens to white (`media/image_flatten`) | `test_find_page.py` |
| **Square** and **Flatten** | `crop.py`'s contour polygon; `segment.get_connected_component_lines` and `get_text_baseline_angle`'s baseline fit | owned by `prep.square.*` and `prep.flatten.*` | yes | Crop's corner handles; Adjust's *Flatten* switch (on/off, Strength) | the squared and flattened renditions | `test_square_page.py`, `test_flatten_curve.py` |
| **Deskew** | `rotate.hough_line_rotate` (±2°, Hough 100/100/10, `cv2.warpAffine` white) and `segment.deskew_image`'s three-method vote; today's `detect_deskew_angle` | owned by `prep.straighten-and-flatten` | yes | Straighten's dial | the deskewed rendition | `test_image_ops_legacy_port.py` |
| Flip, Grayscale, Auto Levels | today's parameterless ops | none | no | the panel's Add Step menu | a chain row | existing `test_*_images.py` |

**Not ported, and why:** the Tesseract document-type test and `validate_rotation` (no Tesseract in the
app); the YOLO page weights `yolov8s-fichero.pt` as a dependency (a baseline to beat, `prep.yolo.page-detector`);
`fuzzy_clean.py` (text, not pixels); the `rembg` "AI" remover (`remove_background.AIBackgroundRemover`:
a portrait model, a 170 MB download, and worse than the threshold on a mount); the `assets/<stage>/`
folders and manifests (`image.enhance.old-conventions-left-behind`).

**Show-through: one setting, then regions (owner 2026-10-29).** The recipe fits method A's `k` (and
method B's gain) **once for the folder from the five-page sample** and applies it to every page. It
switches to **per-region** settings only when the sample is uneven: the sample pages are tiled 4×4, the
show-through contrast measured per tile (the mean local contrast of the mirrored-text mask), and when
the tiles' coefficient of variation is over 0.5 on 3 of 5 pages the step fits `k` per tile, smoothed
across tile borders. The rendition's row says which (`scope: whole` or `scope: regions` with the grid
and gains), the Set Up card says "show-through: one setting" or "by region, the sample is uneven", and
the editor's switch lets a person change it for a page.

**Which door, which rendition.** A recipe run writes one `enhanced` rendition per page with its ordered
steps and the run id; the editor writes chain rows and renders them; Apply to Selection writes a batch
of chain rows with the batch id. A reader names the rendition it read (`image.enhance.rendition-records-its-steps`).

### Leave Out, after enhancement

Leave Out's vocabulary gains `ruler`, `colour card`, `show-through`, `show-through-only verso` beside
`too small`, `off the page`, `likely bleed-through`. The page box comes from page-crop; the ruler and the
colour card are regions (the YOLO layout card's labels, or the strips of the page box the finder
excluded) marked with their reason; the ink-contrast reading comes from the chosen enhancement
rendition when there is one; a show-through-only verso's lines are all left out with the page-level
reason. Prep never marks; Leave Out never paints.

### Reader prompt fragments

`llm/prompt_fragments.py`: named, versioned fragments, one wording per reader kind (line reader; page
VLM read: Gemini, Qwen-VL, local MLX), appended to the reader's prompt when the recipe step names them;
the run record stores the ids and versions so results compare.

| Fragment | Line reader wording | Page reader wording |
| --- | --- | --- |
| `ignore-show-through@1` | "Faint, mirrored writing is the other side of the leaf showing through: do not read it." | "Ignore faint mirrored text showing through from the other side of the leaf; transcribe only the writing on this side." |
| `ignore-furniture@1` | (already in `PROMPT`: ruler, graph paper, blank paper → null) | "Ignore the ruler, the colour card, the mount and anything outside the page." |
| `read-over-stamps@1` | "A stamp or seal over the writing is not text: read the writing under and around it." | "Where a stamp or seal lies over the text, read the text, not the stamp; name the stamp in one bracketed note." |

A project can switch a fragment off; a new wording is a new version, never an edit in place.

### The working rendition

The display image the import already makes (2200 px) becomes the **working rendition**: made once, keyed
by content hash and size, reused by the canvas, Preview, the line reader's page context, VLM page reads
and cleanup previews, never regenerated by a run. Kraken and full-resolution steps read the original. If
the source file is lost or its drive not mounted, the project still views, reads and re-runs whatever
needs only the working rendition, and says plainly which step needs the original.

### Measured

On two named sample pages (the owner's: `EAP1477_GHC_B16_Doc02_IMG_003.jpg`, the hard one — stains, holes,
faint ink, green ruling, a revenue stamp; `…IMG_069.jpg`, blue ink, show-through, stamps; **not on the
drive on 2026-10-26, the `Fichero GHG/GHG` folder is empty — to be supplied as fixtures**) and the typed
pair already in the evidence folder: lines found, lines left out by reason, words read, show-through
words, seconds per page — before and after each step, and the 2×2 of prompt fragment × cleanup.

## Behaviors

- `image.enhance.never-the-original` — **[OK]** every step writes a rendition or a chain row; the source file's bytes and checksum are unchanged. Pinned by `tests/unit/workflows/test_image_prep_source_immutability.py` and `preview.edit.chain-is-a-separate-row-never-the-source`.
- `image.enhance.three-doors-one-function` — **[GAP]** (#6194) each step is one function under `media/enhance/` reached by the workflow node, the editor operation and the batch with the same typed params; the editor request schema and the node config come from that one model.
- `image.enhance.old-conventions-left-behind` — **[GAP]** (#6194) the engine never imports from `fichero_archive`, never reads or writes an `assets/<stage>/` folder or a stage manifest; a guardrail test names the forbidden import.
- `image.enhance.rendition-records-its-steps` — **[PARTIAL]** (#6191) an enhancement rendition carries `metadata.steps` (step, params, method, confidence, who: run id, batch id or person); the viewer switches between renditions; a reader records the rendition it read. Built: `persist_workflow_renditions` pairs outputs by source and copies bytes; the chain row holds the editor's params. Missing: the card and run id on recipe-made renditions, `role: enhanced`, the prepared image attached as a rendition (#5386).
- `image.enhance.page-crop` — **[PARTIAL]** (#6188) finding the page is `prep.find-the-page` and `prep.page.opencv-default-yolo-optional` in `image-preparation.md`; this spec keeps only that the crop is a rendition recorded with its method and confidence (`image.enhance.rendition-records-its-steps`). Built: `split_pages` crops to Vision's box. Missing: the crop as a recorded rendition.
- `image.enhance.page-crop-writes-page-box` — **[GAP]** (#6198) is `prep.page.region-attribute-and-page-box`; kept so #6198 resolves; its test is that line's.
- `image.enhance.rotate-deskew` — **[PARTIAL]** (#6190) the one function `media/enhance/deskew.py` behind the node, the editor's Straighten and the batch; the method and the angle on the row are `prep.straighten-and-flatten`. Built: `rotate_images`, `deskew_images`, the editor's rotate and straighten. Missing: the one function.
- `image.enhance.split-spread` — **[PARTIAL]** (#5382) is `prep.split-at-the-gutter`; this spec adds only that the split's parts are renditions and children recorded with the run id. Built: `split_pages` and `persist_workflow_child_regions`. Missing: the run id on the rows.
- `image.enhance.contrast-clahe` — **[GAP]** (#6190) the `contrast` step is the legacy `enhance.DocumentEnhancer.enhance` step 1 restated (LAB CLAHE clip 2.2 tile 8, L ×1.1 −5; the typescript profile clip 1.6 tile 16) with `clip`, `tile`, `gain`, `lift`, `profile` as params; with `yellowing` and `sharpen` at their defaults it reproduces the two typed samples' reference enhanced files to a mean difference under 3/255.
- `image.enhance.yellowing` — **[GAP]** (#6190; owner 2026-10-29) the `yellowing` step is the legacy `_detect_yellowing` measure and step 2 of `DocumentEnhancer.enhance` (b minus min(8, 3·cast) when the cast is over 0.1, a ×0.98) with `strength` auto and `desaturate_a`; runs by itself when the sample's cast is over 0.1 on 3 of 5; a tinted fixture comes back within 2 of neutral in b and a neutral page is unchanged.
- `image.enhance.sharpen` — **[GAP]** (#6190) the `sharpen` step is step 3 of `DocumentEnhancer.enhance` (Gaussian σ 3, weights 1.5 and −0.5) with `amount` and `radius`; the recipe runs it once after contrast, never twice; a flat grey page is unchanged.
- `image.enhance.editor-enhance-is-the-new-step` — **[GAP]** (#6190) the editor's Auto Enhance runs `contrast`, `yellowing` (auto) and `sharpen` at their defaults, and Adjust exposes every step of the suite with its sliders, on/off switch, live preview and Before (`preview.edit.tool.adjust-previews-live-before-after`); the PIL brightness/contrast/sharpness operation survives only as `legacy_enhance` so an existing chain re-renders to the same pixels; new chains never write it.
- `image.enhance.every-step-is-a-recipe-step-and-an-editor-control` — **[GAP]** (#6185; owner 2026-10-29) every pixel step in the suite table is reachable both as an automatic recipe step that writes a rendition and as an Adjust control in the editor, with the same params model and the same pixels for the same values; a guardrail test walks the params registry and asserts each step has a node, an editor operation and an Adjust control identifier.
- `image.enhance.stain-flattening` — **[GAP]** (#6195) background by `cv2.morphologyEx` closing (kernel long side / 40), divide and rescale to the paper's median, the OpenCV form of today's `_flatten_illumination`; a stain's mean within 10/255 of clean paper after, ink contrast kept; the Fuzzy Clean op's `background_clean` folds into it.
- `image.enhance.ruled-lines` — **[GAP]** (#6195) coloured ruling by hue mask (thin, long), grey ruling by long thin `cv2.HoughLinesP` lines with the legacy `hough_line_rotate` parameters, filled by `cv2.inpaint` radius 3; the ink's dark pixels unchanged; off by default, on from the onboarding answer and only where the bake-off shows it helps.
- `image.enhance.bleed-through-suppression` — **[GAP]** (#6196) method A (local-contrast ink threshold after stains, `k` and `window`) pushes mirrored faint text under the paper noise without thinning the ink; method B (mirrored verso registered by `cv2.findTransformECC` and subtracted with a fitted gain) offered when the verso is in the folder; previewed on three pages.
- `image.enhance.show-through-one-setting-then-regions` — **[GAP]** (#6196; owner 2026-10-29) the recipe fits the show-through setting once for the folder from the five-page sample and applies it to every page; it fits per 4×4 tile, smoothed, only when the sample's tiles' show-through contrast has a coefficient of variation over 0.5 on 3 of 5 pages; the rendition row and the Set Up card say which; the editor's switch overrides it for a page. A uniform synthetic pair gets `scope: whole`; a pair whose verso is faint on one half and strong on the other gets `scope: regions`.
- `image.enhance.denoise` — **[GAP]** (#6185) the `denoise` step is `cv2.medianBlur` (radius 3 or 5, today's `apply_fuzzy_clean` restated) plus speck removal by the legacy mask hygiene (open 5, close 7) on the ink mask; off unless asked or shown to help; 1 % salt-and-pepper noise falls under 0.05 % with the ink's component count unchanged.
- `image.enhance.binarise` — **[GAP]** (#6185) the `binarise` step is Otsu or Gaussian adaptive thresholding from `crop.py`'s methods with `block` and `c`, written as a separate `binarised` rendition; today's `adaptive_binarize` (a global mean threshold) is replaced and an old chain row carrying it re-renders to its old pixels; the recipe runs it only for a reader whose card asks for a binary image.
- `image.enhance.show-through-only-verso` — **[GAP]** (#6197) a fixture pair (recto, mirrored faint verso) marks the second `show-through-only` with its recto; listed, dimmed, left out by default, one click to include, reversible, kept as method B's input.
- `image.enhance.leave-out-reads-the-page-box` — **[GAP]** (#6198) Leave Out's reasons gain `ruler`, `colour card`, `show-through`, `show-through-only verso`; the page box and the ruler/card regions come from page-crop and the layout card; `_ink_contrast` reads the chosen enhancement rendition; prep never marks, Leave Out never paints.
- `image.enhance.reader-prompt-fragment` — **[GAP]** (#6199) versioned fragments per reader kind in `llm/prompt_fragments.py`; a step names them; the run stores ids and versions; a project switches one off; the line reader's existing furniture sentence becomes `ignore-furniture@1`.
- `image.enhance.prompt-and-cleanup-measured-2x2` — **[GAP]** (#6199) on three sample pages the engine reports show-through words per page for fragment on/off × cleanup on/off, and lines found, words read and seconds per page before and after each step (#6189 for the Kraken timing).
- `image.enhance.batch-preview-undo` — **[PARTIAL]** (#6192) a batch over a folder for every step of the suite, three sample pages before and after, one confirmation, batch undo and per-page undo. Built: crop/split batch with batch undo (#1265). Missing: the other steps, the preview, the per-page record.
- `image.enhance.onboarding-step` — **[GAP]** (#5580) is `prep.setup.step-runs-from-the-start-plan` with `prep.setup.three-questions-suggested-from-a-sample`; this spec adds only that the answers "stained or faded", "ruled paper" and "writing shows through" switch on `contrast`, `ruled-lines` and `bleed-through` respectively.
- `image.enhance.working-rendition-once` — **[PARTIAL]** (#6200, #6193) the stored working image is the SINGLE SOURCE for every reduced view of a page: rendered ONCE at import with shrink-on-load (`Image.draft` for JPEG, the reduced read of a pyramidal TIFF, then one LANCZOS fit to 2200 px), keyed by content hash and size, the thumbnail cut from it, and read by the canvas, Preview, the line reader's page context, VLM page reads and cleanup previews. NO RUN RENDERS IT AGAIN: a workflow, a read, a view or a re-import that finds the key present reads the file; `ensure_thumbnail`/`ensure_display` with the key present do no decode; Kraken and full-resolution steps read the original. Owner's evidence (2026-10-26): a thumbnail at 1.6 s alone, about a minute under Kraken's memory pressure, is a full decode of the TIF per request, not a reuse. Built: `ensure_display` makes a 2200 px file. Missing: the hash key (the cache is keyed by document id and path), shrink-on-load (`_generate_image` opens the whole file), the thumbnail derived from the display (made separately today), the consumers that still re-render (`line_reader._page_context_uri` resizes the full page every batch), and the rule, pinned by a test, that a run never renders.
- `image.enhance.reads-without-the-source` — **[GAP]** (#6200) with the source unmounted, Preview, Read-a-page and a re-run that needs only the working rendition succeed; a step that needs the original says so and waits.

## Test matrix

Fixtures (`fichero-server/tests/fixtures/image_enhance/`, to add): a reduced Doc11 page with ruler, colour
card and dark mount and its hand-drawn page box; the two GHC_B16 pages when supplied (IMG_003 hard,
IMG_069 show-through); a synthetic recto/verso pair (text, then its mirror at 25 % contrast); a page with
green ruling drawn over text; a page with a painted stain; a page tinted by a known LAB b offset; a page
with 1 % salt-and-pepper noise; a second recto/verso pair whose verso is faint on one half and strong on
the other; the two typed pages' crops and their reference enhanced files.

| Behaviour | Unit | Click-around | Notes |
| --- | --- | --- | --- |
| `image.enhance.three-doors-one-function`, `image.enhance.old-conventions-left-behind` | `tests/unit/media/test_enhance_three_doors.py` | not needed | Same params model in node config and editor request; forbidden import named. |
| `image.enhance.rendition-records-its-steps` | `tests/unit/workflows/test_prepare_images_rendition_recipe.py` | needed | The viewer switches renditions; the reader names which it read. |
| `image.enhance.page-crop`, `image.enhance.page-crop-writes-page-box` | `tests/unit/media/test_find_page.py`, `tests/unit/recipes/test_leave_out_reads_page_box.py` | needed | Outline within 2 % of the hand-drawn box; Doc11 ruler lines left out `off the page`. |
| `image.enhance.rotate-deskew`, `image.enhance.split-spread` | `tests/unit/media/test_image_ops_legacy_port.py`, `tests/unit/media/test_page_split.py` | not needed | Angle on the row; the aspect gate. |
| `image.enhance.contrast-clahe`, `image.enhance.yellowing`, `image.enhance.sharpen`, `image.enhance.editor-enhance-is-the-new-step` | `tests/unit/media/test_image_ops_legacy_port.py` | needed | Mean diff to the reference under 3/255; the tinted page neutral within 2; an old chain re-renders unchanged. |
| `image.enhance.every-step-is-a-recipe-step-and-an-editor-control` | `tests/unit/media/test_enhance_suite_registry.py`; `ImageEditAdjustControlsTests.swift` | needed | Every step in the registry has a node, an editor op and an Adjust control; the same values give the same pixels through both. |
| `image.enhance.stain-flattening`, `image.enhance.ruled-lines` | `tests/unit/media/test_enhance_stains_and_ruling.py` | needed | Stain within 10/255 of paper; ink pixels unchanged; ruling gone. |
| `image.enhance.bleed-through-suppression`, `image.enhance.show-through-one-setting-then-regions`, `image.enhance.show-through-only-verso` | `tests/unit/media/test_enhance_bleed_through.py`, `tests/unit/media/test_show_through_only_verso.py` | needed | Synthetic pair; the uniform pair `scope: whole`, the uneven pair `scope: regions`; the verso marked, dimmed, included with one click. |
| `image.enhance.denoise`, `image.enhance.binarise` | `tests/unit/media/test_enhance_denoise_binarise.py` | not needed | Noise under 0.05 % with components unchanged; Otsu and adaptive component counts within 5 %; an old `adaptive_binarize` row re-renders unchanged. |
| `image.enhance.leave-out-reads-the-page-box` | `tests/unit/recipes/test_leave_out_reads_page_box.py` | not needed | Reasons vocabulary; contrast from the rendition; page-level verso reason. |
| `image.enhance.reader-prompt-fragment`, `image.enhance.prompt-and-cleanup-measured-2x2` | `tests/unit/llm/test_prompt_fragments.py` | not needed | Ids and versions on the run; four cells reported. |
| `image.enhance.batch-preview-undo`, `image.enhance.onboarding-step` | `tests/unit/api/test_image_batch_prepare.py`, `tests/unit/recipes/test_start_plan_prepare_step.py`; app `ImageBatchPrepareTests.swift` | needed | Preview writes no row; the Start plan holds the step. |
| `image.enhance.working-rendition-once`, `image.enhance.reads-without-the-source` | `tests/unit/db/test_working_rendition_once.py` | needed | Second call renders nothing; unmounted source still previews and reads. |

## Build order

### Stage 1 — The foundation and the page

#### Step 1.1 — One function, three doors (#6194)
- Behaviours: `image.enhance.three-doors-one-function`, `image.enhance.old-conventions-left-behind`
- Tests: fichero-server/tests/unit/media/test_enhance_three_doors.py
- Size: M

#### Step 1.2 — Renditions record their steps (#6191)
- Behaviours: `image.enhance.rendition-records-its-steps`
- Tests: fichero-server/tests/unit/workflows/test_prepare_images_rendition_recipe.py
- Depends on: 1.1
- Size: S

#### Step 1.3 — Page crop and the page box (#6188)
- Behaviours: `image.enhance.page-crop`, `image.enhance.page-crop-writes-page-box`
- Tests: fichero-server/tests/unit/media/test_find_page.py, fichero-server/tests/unit/recipes/test_leave_out_reads_page_box.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — The working rendition, once (#6200)
- Behaviours: `image.enhance.working-rendition-once`, `image.enhance.reads-without-the-source`
- Tests: fichero-server/tests/unit/db/test_working_rendition_once.py
- Depends on: 1.1
- Size: M

### Stage 2 — The ported methods

#### Step 2.1 — Contrast, yellowing and sharpen replace Enhance; rotate, deskew, split (#6190)
- Behaviours: `image.enhance.contrast-clahe`, `image.enhance.yellowing`, `image.enhance.sharpen`, `image.enhance.editor-enhance-is-the-new-step`, `image.enhance.rotate-deskew`
- Tests: fichero-server/tests/unit/media/test_image_ops_legacy_port.py, fichero-server/tests/unit/media/test_page_split.py
- Depends on: 1.2
- Size: M

#### Step 2.2 — Stains and ruled lines (#6195)
- Behaviours: `image.enhance.stain-flattening`, `image.enhance.ruled-lines`, `image.enhance.split-spread`
- Tests: fichero-server/tests/unit/media/test_enhance_stains_and_ruling.py, fichero-server/tests/unit/media/test_page_split.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — Show-through, one setting then regions, and the show-through-only verso (#6196)
- Behaviours: `image.enhance.bleed-through-suppression`, `image.enhance.show-through-one-setting-then-regions`, `image.enhance.show-through-only-verso`
- Tests: fichero-server/tests/unit/media/test_enhance_bleed_through.py, fichero-server/tests/unit/media/test_show_through_only_verso.py
- Depends on: 2.2
- Size: M

#### Step 2.4 — Denoise and binarise; every step through both doors (#6185)
- Behaviours: `image.enhance.denoise`, `image.enhance.binarise`, `image.enhance.every-step-is-a-recipe-step-and-an-editor-control`
- Tests: fichero-server/tests/unit/media/test_enhance_denoise_binarise.py, fichero-server/tests/unit/media/test_enhance_suite_registry.py, fichero/Tests/Unit/general/Views/Preview/ImageEditAdjustControlsTests.swift
- Depends on: 2.3
- Size: M

### Stage 3 — Around the reading

#### Step 3.1 — Leave Out reads what enhancement wrote (#6198)
- Behaviours: `image.enhance.leave-out-reads-the-page-box`
- Tests: fichero-server/tests/unit/recipes/test_leave_out_reads_page_box.py
- Depends on: 2.3
- Size: S

#### Step 3.2 — Prompt fragments and the 2×2 measure (#6199)
- Behaviours: `image.enhance.reader-prompt-fragment`, `image.enhance.prompt-and-cleanup-measured-2x2`
- Tests: fichero-server/tests/unit/llm/test_prompt_fragments.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — Batch with preview and undo; the onboarding step (#6192)
- Behaviours: `image.enhance.batch-preview-undo`, `image.enhance.onboarding-step`
- Tests: fichero-server/tests/unit/api/test_image_batch_prepare.py, fichero-server/tests/unit/recipes/test_start_plan_prepare_step.py
- Depends on: 3.2
- Size: M

## Rulings

- 2026-10-26 (owner): two steps, prep (pixels, renditions) and Leave Out (decisions); order prep → find
  regions and lines → leave out → read. Port the methods and parameters, not the old app's shape. The
  legacy "enhanced" look is the target. Both sides of a leaf photographed: a show-through-only verso is
  marked and left out, never deleted. The working rendition is made once at import.
- 2026-10-29 (owner, paraphrased): the whole OpenCV suite comes over, not levels alone: CLAHE contrast,
  yellowing, stains, show-through, ruled lines, binarisation, denoise and despeckle, sharpening, mount
  removal and the gutter dewarp; each is an automatic recipe step that writes a rendition AND a control in
  Preview's editor with sliders and before/after; the port names its source function and does not
  rewrite. Show-through is one setting fitted from the sample, by region only when the sample is uneven.
  Perspective correction and the dewarp are in now, owned by `image-preparation.md`.

## Open questions

None. Method B's gain (the former question 1) is ruled: one gain from the sample, per tile only when the
sample is uneven (`image.enhance.show-through-one-setting-then-regions`); perspective moved to
`image-preparation.md` and is ruled there.
(Not a decision: the two GHC_B16 sample pages are not on the drive (`Fichero GHG/GHG` was empty on 2026-10-26); the measure in `image.enhance.prompt-and-cleanup-measured-2x2` waits on them as fixtures.)
