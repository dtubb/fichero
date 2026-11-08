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
>
> **2026-11-05 (owner approved; Fable):** the milestone's seven open issues are placed as Stage 4 of the build
> order, one step each, in the order to build them, with what exists in the code on `origin/integration`
> said against what each issue still asks (#6187, #6189, #6190 first; #6185, #6192, #6197, #6200 after).
> Nothing above Stage 4 was rewritten; the lines that gained code since 2026-10-31 were re-tagged.

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
| Nodes: `deskew_images`, `rotate_images`, `auto_crop_border_images` | `workflows/tools/deskew_images.py`, `rotate_images.py`, `auto_crop_border_images.py`; `media/image_ops.detect_deskew_angle`, `detect_content_bbox` | `detect_deskew_angle` reads the skew from the writing's row profile (±15°, 0.1° steps, page edge, ruler and table not read); `detect_content_bbox` is a NumPy box of the bright page that leaves a dark or grey table out; EXIF or typed angle | upgrade: call the one function; bbox in NumPy | `image.enhance.rotate-deskew` | #6190 |
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
| `rotate.py` | page → page | Hough lines within ±2°, median, warpAffine white fill | today's `detect_deskew_angle` reads the same skew from the writing's row profile instead (±15°) |
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
| **Deskew** | `rotate.hough_line_rotate` (±2°, Hough 100/100/10, `cv2.warpAffine` white) and `segment.deskew_image`'s three-method vote; today's `detect_deskew_angle` (row-profile skew of the writing, not Hough) | owned by `prep.straighten-and-flatten` | yes | Straighten's dial | the deskewed rendition | `test_image_ops_legacy_port.py` |
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

**What the local check needs from the owner's samples (2026-11-05; none supplied yet).** Four things,
each a file the owner drops in a folder, nothing hand-built by a builder:

1. **The typed pair** for `image.enhance.contrast-clahe`: for each page `<name>.before.<ext>` (the
   legacy crop) and `<name>.reference.<ext>` (the legacy enhanced file), as
   `fichero-server/src/fichero_server/media/image_prep_samples.py` reads them from `FICHERO_IMAGE_PREP_SAMPLES`; the evidence folder
   named above (`agent-work/status/briefs/image-prep-samples/`) is not in this checkout.
2. **Doc10 and Doc11** (`EAP1477_GHC_B12_Doc1[01]_IMG_*.tif`, or 1500 px reductions) for #6185 and
   #6189, each with a hand-drawn page box (four corners, fractions of the upright frame) and the
   ruler and colour-card strips named, so the furniture test and the whole-frame measure
   (`measure_whole`, `scripts/measure_page_crop.py`) run on the pages the owner complained about.
3. **GHC_B16 IMG_003 and IMG_069** for the 2×2 measure (still not on the drive).
4. **A real recto/verso pair** whose verso is blank with show-through, with the pair's order in the
   folder, for #6197's threshold (0.5 correlation, half the recto's darkest 0.5 %: set on drawn pages).

Until they arrive every sample-bound line below stays `[PARTIAL]` with "unmeasured on real pages"; the
synthetic fixtures pin the method, not the result. Where the files live (a repo fixture folder, reduced,
or a folder outside the repo named by an environment variable) is an owner question (see the end).

## Behaviors

- `image.enhance.never-the-original` — **[OK]** every step writes a rendition or a chain row; the source file's bytes and checksum are unchanged. Pinned by `tests/unit/workflows/test_image_prep_source_immutability.py` and `preview.edit.chain-is-a-separate-row-never-the-source`.
- `image.enhance.three-doors-one-function` — **[PARTIAL]** (#6194) page-crop, deskew, rotate, split and contrast are each one function `media/enhance/<step>.py: run(image, params) -> (image, account)` with a `Params` model, reached by the editor's rows and routes, the `rotate_images`, `deskew_images` and `split_pages` nodes and the page-crop run; the editor requests for rotate, straighten and contrast and the `split_pages` node config come from that model. The `contrast_images` node (`test_the_contrast_node_runs_the_contrast_step_and_writes_an_enhanced_rendition`) and the batch preview of a turn (`test_the_batch_preview_of_a_turn_reaches_the_rotate_step`) reach those functions, the `contrast_images` config is built from `contrast.Params` (`test_the_contrast_node_is_registered_with_its_config_from_the_params_model`), and the `rotate_images` config carries `angle` and `expand` from `rotate.Params` (`test_the_rotate_node_config_has_the_params_models_angle_and_expand_and_the_node_turns_by_the_angle`; `rotation_degrees` stays beside them as the clockwise quarter turn). Not done: show-through has no engine code yet (stains and ruled lines have: `stain-flatten`, `ruled-lines`).
- `image.enhance.old-conventions-left-behind` — **[OK]** the engine never imports from `fichero_archive`, and the step modules, the image nodes and the page-crop run never use an `assets/<stage>/` folder or a stage manifest; a guardrail test names the forbidden import (`importers/legacy_10_archive.py` reads an old archive's folders on purpose and is outside the check).
- `image.enhance.rendition-records-its-steps` — **[PARTIAL]** (#6191) an enhancement rendition carries `metadata.steps` (step, params, method, confidence, who: run id, batch id or person); the viewer switches between renditions; a reader records the rendition it read. Built: `persist_workflow_renditions` pairs outputs by source and copies bytes; the chain row holds the editor's params. Built (#6191): `Rendition.steps` (step, params, card) and `producer_batch_id` beside `producer_run_id`, written by the recipe's prepare step and `contrast_images` (`prep.derived-image-records-its-recipe`). Missing: `role: enhanced` on the recipe's rendition, `metadata.steps` as named here (the field is `steps`), the other nodes and the editor writing steps.
- `image.enhance.page-crop` — **[PARTIAL]** (#6188) finding the page is `prep.find-the-page` and `prep.page.opencv-default-yolo-optional` in `image-preparation.md`; this spec keeps only that the crop is a rendition recorded with its method and confidence (`image.enhance.rendition-records-its-steps`). Built: `split_pages` crops to Vision's box. Missing: the crop as a recorded rendition.
- `image.enhance.page-crop-writes-page-box` — **[OK]** (#6198) is `prep.page.region-attribute-and-page-box` (built, `tests/unit/recipes/test_page_crop_writes_page_region.py`); kept so #6198 resolves; its test is that line's.
- `image.enhance.page-region-shown-in-the-app` — **[PARTIAL]** (#6187; the issue's id `prep.page.region-is-an-attribute` resolves to `prep.page.region-attribute-and-page-box` for the engine half and to this line for the app half) a page whose document metadata carries `page_region` shows it in two places: the Inspector lists it as one attribute row ("Page: 61 % of the frame, Vision, sure" from `box`, `method`, `confidence`; a person's box says "yours"), and Preview draws its box as a dashed outline on the page whenever the page is shown, in single and compare mode, with no tool chosen; a page with no `page_region` shows no row and no outline and is read as the whole image. Engine (built): `page_crop.py` writes `page_region` (quad, box, method, confidence, `frame: "upright"`, settings) and `page_box`; the document route serves them. App (built 2026-11-05, uncompiled; the outline in compare mode is not): `PageRegionSummary` reads the box, method and confidence, the Inspector's strip shows one "Page" row from it without being switched on, and the editor draws `PageRegionOutline` at rest in single mode. Before that: `PageCorners` reads `metadata["page_region"]` only to draw the four corner handles when the toolbar's corner button is pressed in single compare mode (`ImageEditorView+Toolbar.swift`); no Inspector row, no outline at rest. Acceptance: with a page whose metadata holds a `page_region` of box `[0.3, 0.1, 0.6, 0.8]`, the Inspector's attribute list has one row naming the page's share, method and confidence and the editor's overlay holds one dashed rectangle at that box in the image's fit frame; with the key absent, neither exists. Tests: `fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift` (where `PageCorners` is tested; the outline and Inspector tests go beside it; the issue's `test_page_region_attribute.py` is the engine pin already named above).
- `image.enhance.furniture-lines-never-found` — **[PARTIAL]** (#6189, #6185) on a scan with a page region, Find Regions yields no line whose polygon lies outside the page box, so the ruler's numerals, the colour card's patches and the dark border produce no line in any pass, and the run's account counts what the box saved. Engine (built): the segmenter is given only the crop and every line is mapped back to the whole image's frame; a fixture whose whole frame holds a ruler strip yields the ruler line only when there is no page box (`test_kraken_gets_only_the_page_and_every_line_is_in_the_whole_images_frame`, `test_without_a_page_box_the_whole_image_is_read_as_before`); with `measure_whole` the account carries `whole_lines_inside`/`whole_lines_outside` and seconds beside the cut figures (`prep.page.kraken-time-saved-is-reported`). A fixture with a ruler strip, a colour-card band and a dark border now pins all three (`test_the_ruler_the_card_and_the_border_yield_no_line_inside_the_page_box_and_the_saving_is_counted`, `test_the_same_frame_with_no_page_box_yields_the_ruler_the_card_and_the_border`). Built: when the project's Set Up answer names a ruler or a colour card, the plan's Find Regions run carries `measure_whole` and `find_regions(measure_pages=5)` reads the first five pages whole too, and the step's summary says "N lines and S seconds per page saved by the page box" (`saved_by_the_page_box`; `test_a_run_measures_the_saving_on_the_sample_pages_only_and_says_it_in_words`, `test_a_ruler_or_a_card_beside_the_page_has_the_regions_step_measure`). Not built: the measure on the real Doc10/Doc11 scans (sample 2 above). Acceptance: on a fixture frame with a ruler strip down the left, a colour-card band along the top, a dark border and a page box inside them, every line found lies inside the box and `lines_outside` is 0; the same frame with no page box yields the ruler's and the card's lines; the Prepare Images run, when the project's Set Up answer names a ruler or a card, runs Find Regions with `measure_whole` on the five sample pages only and the run summary says "N lines and S seconds per page saved by the page box". Tests: `fichero-server/tests/unit/recipes/test_find_regions_inside_page.py`, `fichero-server/tests/unit/recipes/test_leave_out_reads_page_box.py`.
- `image.enhance.rotate-deskew` — **[PARTIAL]** (#6190) the one function `media/enhance/deskew.py` behind the node, the editor's Straighten and the batch; the method and the angle on the row are `prep.straighten-and-flatten`. Built (#6194): the one function is `media/enhance/rotate.py` and `media/enhance/deskew.py` (`run(image, params) -> (image, account)`), reached by the editor's rotate and Straighten routes, `rotate_images` and `deskew_images`; each is pinned by `tests/unit/media/test_enhance_three_doors.py` (`test_rotate_run_turns_a_quarter_without_resampling_and_a_fraction_with_expand`, `test_deskew_run_turns_a_tilted_page_back_and_a_square_one_is_left_alone`, `test_editor_rotate_route_reaches_the_rotate_step`, `test_editor_straighten_route_reaches_the_deskew_step`, `test_rotate_node_file_function_reaches_the_rotate_step`, `test_deskew_node_measures_with_the_deskew_step`). The editor's Straighten records the angle the deskew step found, and 0.0 when the tilt is under 0.3° (before, it recorded the raw angle and turned the page): `test_editor_straighten_records_the_angle_deskew_found_and_leaves_a_page_under_the_minimum_unturned`.
- `image.enhance.split-spread` — **[PARTIAL]** (#5382) is `prep.split-at-the-gutter`; this spec adds only that the split's parts are renditions and children recorded with the run id. Built: `split_pages` and `persist_workflow_child_regions`. Missing: the run id on the rows.
- `image.enhance.contrast-clahe` — **[PARTIAL]** (#6190) Built 2026-10-29: `apply_clahe_contrast`, `contrast` with the five params; the reference-sample check is a by-hand script (`fichero-server/src/fichero_server/media/image_prep_samples.py`, `FICHERO_IMAGE_PREP_SAMPLES`), not yet run on real pages; the Enhance popover has Fine-tune sliders for the four values (Swift, unrun). A stored chain row is applied as it was saved: `apply_operation` builds the contrast params without re-validating, so a row with `factor` 12 or `clip` 6.0 saved by an older library still previews (200, not a 500), while the save route (`PUT /edits`) refuses a new out-of-range value with 422: `test_a_stored_contrast_row_out_of_range_still_previews_as_it_was_saved`. the `contrast` step is the legacy `enhance.DocumentEnhancer.enhance` step 1 restated (LAB CLAHE clip 2.2 tile 8, L ×1.1 −5; the typescript profile clip 1.6 tile 16) with `clip`, `tile`, `gain`, `lift`, `profile` as params; with `yellowing` and `sharpen` at their defaults it reproduces the two typed samples' reference enhanced files to a mean difference under 3/255.
- `image.enhance.yellowing` — **[PARTIAL]** (#6190; owner 2026-10-29) built: `media/enhance/yellowing.py` (`test_yellowing_subtracts_min_8_3_cast_from_b_and_leaves_a_neutral_page_alone`); not built: running by itself from the sample, and the "within 2 of neutral" bound (the subtraction is at most 8). The `yellowing` step is the legacy `_detect_yellowing` measure and step 2 of `DocumentEnhancer.enhance` (b minus min(8, 3·cast) when the cast is over 0.1, a ×0.98) with `strength` auto and `desaturate_a`; runs by itself when the sample's cast is over 0.1 on 3 of 5; a tinted fixture comes back within 2 of neutral in b and a neutral page is unchanged.
- `image.enhance.sharpen` — **[PARTIAL]** (#6190) the `sharpen` step is step 3 of `DocumentEnhancer.enhance` (Gaussian σ 3, weights 1.5 and −0.5) with `amount` and `radius`; the recipe runs it once after contrast, never twice; a flat grey page is unchanged. Built (engine): `fichero-server/src/fichero_server/media/enhance/sharpen.py`, `test_sharpen_is_unsharp_mask_1_5_minus_0_5_at_sigma_3_and_leaves_flat_paper_alone`; an `enhance` row with `method: clahe` runs contrast, then yellowing, then sharpen (`test_enhance_with_method_clahe_runs_contrast_then_yellowing_then_sharpen_and_a_row_without_a_method_is_the_pil_enhance`). Not built: "never twice" is unpinned: a recipe whose Prepare step runs `contrast` and a chain that already holds a `sharpen` row must not sharpen again; test to write in `test_image_ops_legacy_port.py`.
- `image.enhance.editor-enhance-is-the-new-step` — **[PARTIAL]** (#6190) the editor's Auto Enhance runs `contrast`, `yellowing` (auto) and `sharpen` at their defaults, and Adjust exposes every step of the suite with its sliders, on/off switch, live preview and Before (`preview.edit.tool.adjust-previews-live-before-after`); the PIL brightness/contrast/sharpness operation survives only as `legacy_enhance` so an existing chain re-renders to the same pixels; new chains never write it. Built (engine): `POST /api/images/{id}/operations/enhance` takes `method: clahe`, `profile`, `clip`, `tile`, `gain`, `lift`; a row without a method is the PIL enhance (`test_the_enhance_route_takes_a_clahe_method_and_profile_and_a_plain_request_is_stored_as_before`). Built (app, unrun): the Enhance popover's "Local contrast (faded writing)" switch, the Handwritten/Typescript choice and the Fine-tune sliders (`ImageEditorView+Popovers.swift`). Built (app, unrun, 2026-11-05): the switch starts on and an untouched Apply sends `clahe`, handwritten (`EnhanceChoice`, `ImageEditDirectToolsTests.enhanceDefaultsToLocalContrast`); sharpen runs once, inside the clahe profile (`test_enhance_with_method_clahe_runs_contrast_then_yellowing_then_sharpen_and_a_row_without_a_method_is_the_pil_enhance`). Not built: the 3/255 reference-sample check (waits on sample 1), so **acceptance for the step is: a new `enhance` row written by the app with nothing touched carries `method: clahe`** (engine test through the route; Swift test that the popover's request defaults to `clahe`); the on/off switch and Before per step; the `legacy_enhance` name (today the old op is "no method"; the name may stay "no method" if the re-render pin holds, `preview.edit.tool.retired-ops-still-render`).
- `image.enhance.every-step-is-a-recipe-step-and-an-editor-control` — **[GAP]** (#6185; owner 2026-10-29) every pixel step in the suite table is reachable both as an automatic recipe step that writes a rendition and as an Adjust control in the editor, with the same params model and the same pixels for the same values; a guardrail test walks the params registry and asserts each step has a node, an editor operation and an Adjust control identifier.
- `image.enhance.stain-flattening` — **[PARTIAL]** (#6195) built: `media/enhance/stain_flatten.py` (closing of the lightness with an ellipse of long side / `kernel_divisor` (default 40, 20-80), blur, divide, rescale to the median of the brightest 20 %, `strength` blend), the `stain_flatten` chain row (saved by `PUT /edits`, previewed by `GET /preview`) and the `stain_flatten_images` node, which writes an `enhanced` rendition whose `steps` row carries the step and its settings (`tests/unit/media/test_enhance_stains_and_ruling.py`: a fixture stain's mean is within 10/255 of clean paper after, and the ink's gap to the paper is kept). The ink's pixels inside a stain are lightened by the divide, so the test holds the ink contrast, not the ink pixels. Not built: the Fuzzy Clean `background_clean` fold, a `paper` setting, the 1/80-1/20 kernel as a fraction (the setting is the divisor), running from Set Up's answer, the editor controls.
- `image.enhance.ruled-lines` — **[PARTIAL]** (#6195) built: `media/enhance/ruled_lines.py` (HSV hue mask for green, blue or red, kept where thinner than `max_width` and longer than `min_length` of the page's side, filled by `cv2.inpaint`, never over dark pixels), the `ruled_lines` chain row and the `ruled_lines_images` node (enhanced rendition with a `steps` row), tested in `test_enhance_stains_and_ruling.py`: green and blue ruling is filled to within 12/255 of the paper, the ink's pixels and the inside of a thick green block are unchanged. The fill reaches one pixel past a rule. Not built: grey ruling by `HoughLinesP`, off-by-default wiring from the onboarding answer and the bake-off, the editor controls.
- `image.enhance.bleed-through-suppression` — **[PARTIAL]** (#6196) built: `media/enhance/bleed_through.py`. Method A: the paper is a per-channel closing (kernel long side / `window_divisor`, 60), a pixel is ink where it is darker than the paper by more than `k` (0.25, 0-0.5) times the page's ink darkness (the 99.5th percentile), ink and one pixel around it are kept exactly and every other pixel is set to the paper estimate. Method B: the verso is mirrored, registered by `cv2.findTransformECC` (affine, coarse then fine) and its darkness times a gain fitted under its ink is taken from the recto where the recto is not ink; with no verso, or no registration, the page comes back unchanged and the account says why. The `bleed_through` chain row (validated on `PUT /edits`, rendered by preview) and the `bleed_through_images` node (method B reads the `versos` input, one per file) write an `enhanced` rendition whose `steps` row carries the settings (`tests/unit/media/test_enhance_bleed_through.py`: the show-through's mean lands within 6/255 of the paper, the ink's pixels are unchanged, the same pair is not cleaned without the registration, three sample pages preview through the routes). `k` is a fraction of the page's ink darkness, not the Sauvola local-mean-minus-`k`-std of the table above. Not built: finding the verso from the next image in the folder, `scope: regions`, running after stains, the editor controls, a stretch of the ink.
- `image.enhance.show-through-one-setting-then-regions` — **[GAP]** (#6196; owner 2026-10-29) the recipe fits the show-through setting once for the folder from the five-page sample and applies it to every page; it fits per 4×4 tile, smoothed, only when the sample's tiles' show-through contrast has a coefficient of variation over 0.5 on 3 of 5 pages; the rendition row and the Set Up card say which; the editor's switch overrides it for a page. A uniform synthetic pair gets `scope: whole`; a pair whose verso is faint on one half and strong on the other gets `scope: regions`.
- `image.enhance.denoise` — **[PARTIAL]** (#6185) the `denoise` step is `cv2.medianBlur` (radius 3 or 5, today's `apply_fuzzy_clean` restated) plus speck removal by the legacy mask hygiene (open 5, close 7) on the ink mask; off unless asked or shown to help; 1 % salt-and-pepper noise falls under 0.05 % with the ink's component count unchanged.
- `image.enhance.binarise` — **[PARTIAL]** (#6185) the `binarise` step is Otsu or Gaussian adaptive thresholding from `crop.py`'s methods with `block` and `c`, written as a separate `binarised` rendition; today's `adaptive_binarize` (a global mean threshold) is replaced and an old chain row carrying it re-renders to its old pixels; the recipe runs it only for a reader whose card asks for a binary image.
- `image.enhance.show-through-only-verso` — **[PARTIAL]** (#6197) a fixture pair (recto, mirrored faint verso) marks the second `show-through-only` with its recto; listed, dimmed, left out by default, one click to include, reversible, kept as method B's input. Built: `media/show_through_only.py` judges each page after another (the leaf rule): no ink of its own (under half the recto's darkest 0.5 %) and its mirrored, registered darkness correlates with the recto's at 0.5 or more; the Prepare step runs it when the paper answer says writing shows through and writes document metadata `page_kind: show-through-only`, `show_through_of`, `show_through_score`, `show_through_only` (`tests/unit/media/test_show_through_only_verso.py`); Leave Out leaves every line out by default; `image.include_show_through_only` includes it (and, with `included` false, leaves it out again) and `image.clear_show_through_only` removes the mark; the page is never rewritten or deleted. Not built: a listing control in the app, a check of the page's own text, and the threshold is untuned against real pages (sample 4 above). App acceptance (#6197, to build): in the item view a page whose metadata `page_kind` is `show-through-only` is listed dimmed with the words "show-through of <recto's name>" and one button *Include*; the button runs the action `image.include_show_through_only` and the row loses its dimming and gains *Leave out*, which runs the same action with `included: false`; Undo puts it back; the page is never removed from the list. Engine (built): the two actions and `image.clear_show_through_only` (`fichero-server/src/fichero_server/api/routes/ingest/image_prepare_actions.py`). App (built, unrun, 2026-11-05): `ShowThroughOnlyLine` above the rows lists each marked page dimmed with \"show-through of <name>\" and Include / Leave Out, each the audited action `image.include_show_through_only` (`fichero/Tests/Unit/general/Views/Preview/BlankPagesHiddenTests.swift`: `showThroughPagesAreListedWithTheirRecto`, `includeAndLeaveOutAreReversibleAndKeepThePage`, `includeRequestUsesTheActionsParameterNames`). Engine (built, 2026-11-06): `image.include_show_through_only` is undoable; its undo is the same action with the page's earlier answer, so the lines come back or go out again as they were (`fichero-server/tests/unit/media/test_show_through_only_verso.py`: `test_undo_puts_back_an_include_and_a_leave_out_with_the_lines_as_they_were`); the app's button is the audited action, so the window's Undo reaches it (unrun). Not built: the threshold on real pages (sample 4). Tests: `fichero-server/tests/unit/media/test_show_through_only_verso.py`, `fichero/Tests/Unit/general/Views/Preview/BlankPagesHiddenTests.swift` (the hidden-line tests; the show-through rows are the same list treatment, tests go beside them).
- `image.enhance.leave-out-reads-the-page-box` — **[PARTIAL]** (#6198, #6185) built: on a cropped scan Leave Out reads the document's `page_box` and `page_furniture` (written by page-crop) and marks the ruler's lines `ruler`, the colour card's `colour card` and the mount's `off the page`, keeping the text lines (`test_the_stage_marks_the_ruler_the_card_and_the_mount_lines_of_a_cropped_scan_and_keeps_the_text`). Built: the reasons `show-through` and `show-through-only verso` exist as constants (`test_the_reasons_vocabulary_has_the_page_level_and_show_through_names`); `_ink_contrast` reads the newest `enhanced` rendition that has no transform, else the page's own image (`test_ink_contrast_reads_the_enhanced_rendition_when_there_is_one`); a document whose metadata `show_through_only` is true has every line left out as `show-through-only verso` and no rendition file changes (`test_a_show_through_only_verso_has_every_line_left_out_with_the_page_level_reason_and_no_pixels_change`). Not built: nothing yet writes `show_through_only` (#6197), and no rule yields the per-line reason `show-through`. Leave Out's reasons gain `ruler`, `colour card`, `show-through`, `show-through-only verso`; the page box and the ruler/card regions come from page-crop and the layout card; `_ink_contrast` reads the chosen enhancement rendition; prep never marks, Leave Out never paints.
- `image.enhance.reader-prompt-fragment` — **[PARTIAL]** (#6199) built: `llm/prompt_fragments.py` holds `ignore-show-through@1`, `ignore-furniture@1`, `read-over-stamps@1` with a `line` and a `page` wording (`test_the_three_fragments_exist_at_version_one_with_a_wording_per_reader`); a read step's `prompt_fragments` list reaches the Transcribe node's config with the ids and versions on the plan (`test_start_carries_the_steps_fragments_with_their_versions_to_the_read_node`); the line reader appends the line wording to its prompt and the result carries `prompt_fragments` `[{id, version, reader}]` (`test_the_transcribe_tool_sends_the_fragment_and_its_result_records_id_and_version`); a library setting `prompt_fragments.off` (comma-separated ids) keeps a fragment from being sent or recorded (`test_a_fragment_the_project_switched_off_is_not_sent_or_recorded`). Not built: the page reader's wording is appended only through the Transcribe tool's prompt, not yet tested through a page read; the line reader's existing furniture sentence stays in `PROMPT` (`ignore-furniture@1` has no extra line wording); no control to switch a fragment off.
- `image.enhance.prompt-and-cleanup-measured-2x2` — **[PARTIAL]** (#6199) built: `prompt_fragments.measure_2x2(pages, read)` reads each page in the four cells fragment on/off x cleanup on/off and reports show-through words and seconds per page and the total per cell (`test_the_2x2_reports_show_through_words_per_page_for_the_four_cells`, with a stub reader). Not built: the three sample pages and a real reader; lines found and words read before and after each step (#6189 for the Kraken timing).
- `image.enhance.batch-preview-undo` — **[PARTIAL]** (#6192) a batch over a folder for every step of the suite, three sample pages before and after, one confirmation, batch undo and per-page undo. Engine (built): `POST /api/images/batch-apply` takes every operation of `media/image_ops` beside crop and split with the step's `params`, stamps one `batch_id` on each page's new chain row, `?preview=3` returns the first, middle and last page before and after and writes nothing, `POST …/batch-apply/{batch_id}/undo` removes the batch's rows and nothing else, and deleting one page's row leaves the rest (`tests/unit/api/test_image_batch_prepare.py`). App (built, unrun): `ImageBatchPrepareSheet` shows three previews, Apply, then a per-page list with Undo, but it calls `batch-prepare` (a squaring's corners or a turn) and `ImageEditorModel.batchApply` still loops the old per-document crop/split calls. Built (app, unrun, 2026-11-05): the toolbar's "Clean up the folder" menu opens `ImageCleanupBatchSheet` for Auto Enhance, Sharpen, Remove Speckle, Clean Stains or Black and White; it calls `batch-apply?preview=3`, shows three before/after pairs and "N pages", applies once, lists each page with Undo (`image.undo_batch_page`) and Undo All calls the batch undo (`fichero/Tests/Unit/general/Views/Preview/ImageCleanupBatchTests.swift`: `theSheetPreviewsOnceApplysOnceAndUndoesOnce`, `applyWaitsForThePreviewAndAPageUndoLeavesTheOthers`). Not built: a split has no preview; contrast, ruling and show-through are not in the menu yet. App acceptance (to build): choosing Apply to Selection on a cleanup step (contrast, stains, ruling, show-through, denoise, binarise, sharpen, yellowing) opens the same sheet, which calls `batch-apply?preview=3` with the step and its params and shows three before/after pairs and "N pages"; Apply calls `batch-apply` once; the list that follows names each page with Undo; Undo all calls the batch undo; a stub engine sees exactly one preview call, one apply and one undo. Tests: `fichero-server/tests/unit/api/test_image_batch_prepare.py`, `fichero/Tests/Unit/general/Views/Preview/ImageBatchPrepareTests.swift`.
- `image.enhance.onboarding-step` — **[PARTIAL]** (#5580) is `prep.setup.step-runs-from-the-start-plan` with `prep.setup.three-questions-suggested-from-a-sample`; this spec adds only that the answers "stained or faded", "ruled paper" and "writing shows through" switch on `contrast`, `ruled-lines` and `bleed-through` respectively. Built: the Start plan's `prepare-the-image` entry carries `paper_steps` (`ruled` names `ruled-lines`, `show-through` names `bleed-through`; `test_each_paper_option_is_its_own_gate_and_the_plan_no_longer_says_ruling_and_show_through_are_not_built`) and the run makes one `enhanced` rendition recording each step (`tests/unit/recipes/test_start_plan_prepare_step.py`). Not built: the bake-off gate on ruling, bleed-through method b.
- `image.enhance.working-rendition-once` — **[PARTIAL]** (#6200, #6193) the stored working image is the SINGLE SOURCE for every reduced view of a page: rendered ONCE at import with shrink-on-load (`Image.draft` for JPEG, the reduced read of a pyramidal TIFF, then one LANCZOS fit to 2200 px), keyed by content hash and size, the thumbnail cut from it, and read by the canvas, Preview, the line reader's page context, VLM page reads and cleanup previews. NO RUN RENDERS IT AGAIN: a workflow, a read, a view or a re-import that finds the key present reads the file; `ensure_thumbnail`/`ensure_display` with the key present do no decode; Kraken and full-resolution steps read the original. Owner's evidence (2026-10-26): a thumbnail at 1.6 s alone, about a minute under Kraken's memory pressure, is a full decode of the TIF per request, not a reuse. Built: `ensure_display` makes a 2200 px file and records the key it was made for (the file's checksum, the longest side, the edit chain's version, a PDF's page) beside it; a call whose key matches does no render and does not open the source, even when the file's modified time moved (`test_a_second_call_with_the_same_content_and_side_does_no_render_even_when_the_file_was_touched`), and a different side or different content renders again (`test_a_different_side_is_a_different_key_and_renders_again`, `test_different_content_is_a_different_key_and_renders_again`). A document with no checksum, or a display file with no recorded key, is still judged by the source's modified time, or re-made once when the source is readable. Built (2026-11-05): `ensure_thumbnail` is cut from the display image when its recorded key matches this content and chain, without opening the original (`test_the_thumbnail_is_cut_from_the_working_rendition_not_the_original`). Built (2026-11-05): shrink-on-load, a JPEG decodes reduced through `thumbnail`'s draft and a pyramidal TIFF is fitted from its smallest flagged reduced level that still covers the box, never the next page of a scan (`test_a_pyramidal_tiff_is_fitted_from_its_reduced_level_not_the_full_frame`, `test_a_second_page_of_a_scan_is_not_taken_for_a_reduced_level`). Built (2026-11-05): the thumbnail's cache identity is the rendition's key when it is made for this content and chain, so the original's modified time moving makes no new thumbnail (`test_the_thumbnail_is_not_made_again_when_the_originals_modified_time_moves`); a document with no checksum or a stale `.key` keeps the modified-time identity (`test_a_document_with_no_checksum_keeps_the_modified_time_identity`, `test_a_stale_key_makes_the_thumbnail_again`); a Prepare Images run's page operations decode the original zero times when the rendition is made (`test_a_prepare_images_run_decodes_the_original_zero_times_when_the_rendition_is_made`). Existing modified-time thumbnails are replaced the next time they are asked for. Missing: the Transcribe tool's other reads and the page VLM read still pass no `working_image`, and the Read half of (d) is not pinned. Acceptance for what is left (#6200, #6193, engine): (a) `ensure_thumbnail` is keyed like `ensure_display` and, when the display file exists, is cut from it without opening the source; (b) `_generate_image` calls `Image.draft` for a JPEG and reads a pyramidal TIFF at its reduced level before the one LANCZOS fit, pinned by counting the decoded size on a 6000 px fixture; (c) the Transcribe tool and the page VLM read pass the display path as `working_image`; (d) a counting stub around `_generate_image` sees zero calls during a Prepare Images run and a Read over pages whose key is present.
- `image.enhance.reads-without-the-source` — **[PARTIAL]** (#6200) with the source unmounted, Preview, Read-a-page and a re-run that needs only the working rendition succeed; a step that needs the original says so and waits. Built: `ensure_display` returns the display image already made when no source can be read, and None when none was made (`test_with_the_source_unmounted_the_made_picture_is_still_served`, `test_a_page_never_made_and_unmounted_answers_nothing_and_does_not_invent_a_picture`). Built (2026-11-05): the page-reading tool passes the made rendition to the line reader (`test_the_line_readers_working_image_is_the_made_rendition_and_none_before_it_is_made`, `test_made_display_names_the_rendition_only_when_it_was_made_for_this_content_and_never_renders`). Missing: the VLM page read, cleanup preview and the canvas picture still read the source, and no step reports plainly that it needs the original.

- `image.ops.one-action-per-operation` — **[PARTIAL]** (#6363; owner 2026-11-06) every image operation is one audited action `image.<op>` in the action registry (`actions/registry.py` `action`, the shape `image.rotate` and `image.enhance` already have), and every door, the recipe's Prepare run, the editor's route, `batch-apply` and the workflow node, writes its chain row or rendition through that action and nothing else. Today twelve operations have an action (`image.rotate`, `image.straighten`, `image.crop`, `image.crop_child`, `image.split`, `image.unsplit`, `image.enhance`, `image.square`, `image.remove_background`, `image.segment`, `image.mark_blank`, `image.batch_apply`); the pixel steps (`contrast`, `yellowing`, `sharpen`, `stain_flatten`, `ruled_lines`, `bleed_through`, `denoise`, `binarise`), `grayscale`, `auto_levels`, `auto_crop_border`, `adaptive_binarize`, `flip_horizontal` and `flip_vertical` are rows a `PUT /edits` validates (`_OPERATION_MODELS`, `_PARAMETERLESS_OPERATIONS`, `image_editing.py:140-146`) with no action of their own, so their audit entry is the chain write, not the operation. Acceptance: a guardrail test walks the chain vocabulary (the keys of `_OPERATION_MODELS` and `_PARAMETERLESS_OPERATIONS`) and asserts each name has a registered action `image.<name>` whose params model is the step's `Params` (from `media/enhance.STEPS`) or the operation's request model; invoking the action on a page writes exactly one chain row carrying the op, the params and `who`, and one audit entry naming the action; `undo` of that action removes that row and no other. *Decided here:* one action per operation, generated from the step registry (one loop over `STEPS`, not thirteen hand-written decorators), because the audit log and Undo already name operations by verb and a single `image.apply_step` action would hide which step ran. Built (2026-11-07): `api/routes/ingest/image_op_actions.py` makes `image.<op>` for every chain name that had no action (brightness, contrast, sharpen, fuzzy_clean, denoise, stain_flatten, ruled_lines, bleed_through, binarise, flip_horizontal, flip_vertical, auto_levels, grayscale, auto_crop_border, adaptive_binarize) by one loop over the vocabulary, each undoable through `image.set_operations`, each row carrying `who` (default `person`; a run passes `run <id>`); `tests/unit/api/test_image_ops_actions.py` walks the vocabulary. Not built: the hand-written actions (crop, rotate, straighten, enhance, remove_background) write rows without `who`; the doors (recipe, route, batch-apply, node) still write their rows themselves and are moved onto these actions in Steps 5.2 and 5.3.
- `image.ops.long-operation-is-bounded` — **[PARTIAL]** (#6384; owner's 8 GB M1 Air log 2026-11-07) a long image operation does not take the engine down with it: its peak memory is a few bytes a pixel on top of the source (not tens), and the engine keeps answering health and reads while it runs. Acceptance: removing the background of a 35-megapixel scan peaks under 14 bytes a pixel in `tracemalloc` (`fichero-server/tests/unit/media/test_remove_background_memory_6384.py`; the old path measured about 17 bytes a pixel on the same scan and about 30 on a 108-megapixel one). Built (2026-11-07): the default `opencv` method of `remove_background` finds the page outline on a copy no longer than 2048 pixels and cuts the page before building its transparency (`media/image_ops.remove_black_background_opencv`); a 108-megapixel scan went from a 4.2 GB peak and 4 s to 1.8 GB and 0.8 s, and a small image takes the same path as before; the editor route's older `_remove_black_background_opencv` in `image_editing.py` now calls the same function. Not built: the other methods (`threshold` keeps a full-resolution int16 copy, `rembg` its own model) and the other pixel steps are not measured yet; a long operation as a background job with an Activity row, progress and Cancel (a client deadline no longer drops the connection) needs an API shape and the app's part; the engine log of the Air has not been read, so that memory was the cause is the reading of the numbers above, not a seen OOM kill. *Decided here:* bound the memory first because it is the one cause the numbers show; the job shape waits for the manager.
- `image.ops.long-operation-is-a-job` — **[PARTIAL]** (#6384; manager's ruling 2026-11-07: the existing Activity job model, no new API shape) any `image.<op>` action that takes a page can be asked for as a job: `POST /api/images/{id}/jobs` with `{action, params}` returns `202` and a job id at once, the operation runs on the images lane (two at a time, one while memory is tight) as a job of kind `image-operation`, the row shows in Activity, and Cancel is the job's own. The job calls the same audited action as the direct route, so the chain row, the audit entry and Undo are the direct call's. Acceptance: the request returns before any pixel work; the job ends `done` with one chain row and one audit entry; two asks of one page are two jobs; a non-image or whole-library action, an unknown action and settings that do not validate are refused with 422 (`fichero-server/tests/unit/api/test_image_operation_job.py`). Built (2026-11-07): `image_op_job.py` (the kind, `queue_image_operation`) and the route in `image_op_actions.py`. Not built: the app asking for it (the Preview editor's remove-background, the batch menu and the designer's run still call the direct route and wait; that is Swift, held), progress inside one page (a page is one step, so the row says running, then done), and a stuck-job limit longer than the images lane's 60 s for a very large scan.
- `image.ops.missing-library-says-so` — **[PARTIAL]** (#6384; owner's M1 Air log 2026-11-07) a saved library that is not on disk at launch is one alert that names it, with Locate… (the panel at its folder, then it opens from where it was found) and Remove (it stays out of the open list), one at a time when several are missing; it is not a line in the log. Acceptance: reporting a missing path shows the alert with the library's name; answering it moves to the next; a path reported twice is asked once. Built (app, Swift not compiled here): `MissingLibraryNotice` and the alert on the sidebar. Not built: a library on a volume that is not mounted is told apart from one deleted.
- `image.ops.workflow-node-per-operation` — **[PARTIAL]** (#6363) every operation has a workflow node named `<op>_images`, registered from the same registry the four `enhance_step_nodes` already come from (`_register`, `enhance_step_nodes.py:85-146`), its config from the params model. Today the nodes are `rotate_images`, `deskew_images`, `enhance_images`, `contrast_images`, `stain_flatten_images`, `ruled_lines_images`, `bleed_through_images`, `binarise_images`, `fuzzy_clean_images`, `denoise_images`, `adaptive_binarize_images`, `auto_crop_border_images`, `remove_background_images`, `segment_images`, `split_pages`, `split_images`; missing are `yellowing_images`, `sharpen_images`, `flip_images` (one node, `direction` horizontal or vertical), `grayscale_images`, `auto_levels_images` and `square_images`. Acceptance: `test_enhance_suite_registry.py` lists one node per operation in the chain vocabulary (split's node is `split_pages`); `yellowing_images` on the tinted fixture reaches `yellowing.run` and writes an `enhanced` rendition whose `steps` row names it, the same assertion shape as `test_the_contrast_node_runs_the_contrast_step_and_writes_an_enhanced_rendition`. Built (2026-11-07): `yellowing_images`, `sharpen_images`, `flip_images` (one node, `direction` horizontal or vertical), `grayscale_images` and `auto_levels_images`, in `workflows/tools/enhance_step_nodes.py` beside the four that were there, from the same `_register`; yellowing and sharpness write no chain row (they run inside Auto Enhance), the other three append the chain row of their operation; `test_enhance_suite_registry.py` walks the chain vocabulary and names the ones with no node yet. Not built: `square_images` (it needs a page's four corners, which a folder run has not got until the page-box step has found them), and `brightness`, `crop` and `mark_blank`, which have no standalone node; the registry test names all four so a new chain operation cannot slip past.
- `image.ops.recipe-designer-offers-every-operation` — **[PARTIAL]** (#6363) the recipe designer's Prepare Images card offers one operation per op, in the suite's order, each with its plain-words sentence and a default worked out from the Set Up answers (`prepare_operations.IDS`, today `split`, `straighten`, `crop`, `clarity`; `clarity` is kept as the name of the ordered contrast → yellowing → sharpen that an `enhance` row with `method: clahe` runs), and the run executes the chosen ones through the operations' actions, one `enhanced` rendition whose `steps` rows list them. Default on: split (when two pages share a picture), straighten, crop, clarity; default off: everything else, switched on by the paper answers as `image.enhance.onboarding-step` says (stains or faded → contrast, ruled → ruled-lines, show-through → bleed-through). Acceptance: `to_run()` for a hand that picks `flip` and `binarise` returns those two in suite order; the plan's how-it-works sentence names them; the run's rendition carries both `steps` rows; a hand that picks nothing runs the four defaults as today (Step 3.3's existing Start-plan pins stay green). *Decided here:* flip and grayscale are offered off by default rather than left out, because a door that exists for one operation exists for all (the one-function rule above) and an unused switch costs nothing. Built (engine): `prepare_operations.EXTRA` lists the rest of the suite (stain-flatten, sharpen, denoise, binarise, flip, grayscale, auto-levels) after the four, each with a sentence, off by default; `to_run()` returns a hand's pick in suite order; the plan's `how` names them; `run_prepare` runs each pick on each page through its audited `image.<op>` action (`ACTION_OF`): one audit entry and one chain row per page and operation, undoable, a second run leaves what the first did (`tests/unit/recipes/test_prepare_every_operation.py`). Not built: a picture for each extra, the enhanced rendition with a `steps` row per pick (the chain row carries the recipe instead), yellowing as its own pick (it is inside clarity), ruled-lines and bleed-through as hand-chosen rows. Built 2026-11-08 (app): the card's rows are the engine's listing, so the extras show as switches after the four, off, with no picture of their own (`PrepareOperationsTests.theRestOfTheSuiteFollows`; Swift not compiled here).
- `image.ops.edit-mode-offers-every-operation` — **[GAP]** (#6363, #6362) the Source pane's edit mode offers every operation and nothing that calls an old path: the tools on the toolbar are the set `preview.edit.tool.set-is-exactly-this` names (Crop as the page box, Straighten dial, Rotate, Split as the gutter line, Square corners, Mark) plus **Flip** (one button, horizontal; Option for vertical); every pixel step is a section of Adjust (`preview.edit.tool.adjust-previews-live-before-after`) and so are **Grayscale**, **Auto Levels** and **Auto Crop Border** as switches with no slider; the show-through-only verso's Include / Leave Out is a line in edit mode too, not only above the Library rows (#6362). The controls that call an old path leave: the toolbar's Despeckle (its op is Adjust's Denoise), Remove Background and Segment (ruled out by `preview.edit.tool.retired-ops-still-render`), the Enhance popover's PIL sliders (Adjust's Contrast, Yellowing, Sharpen), and `batchMenu` (`imageEditBatchMenu`). Acceptance: a Swift test reads the engine's operation vocabulary from the generated client (`BatchImageApplyRequest.operation`'s cases) and asserts that for every operation the editor has exactly one control identifier (`imageEdit<Op>` on a tool or `imageEditAdjust.<op>` on a section), that no identifier names an operation the engine lacks, and that `imageEditBatchMenu` and the Despeckle, Remove Background and Segment tool buttons no longer exist; entering edit mode on a page and reading the toolbar and Adjust shows every operation once. *Decided here:* Flip is a tool, not an Adjust switch, because it is geometric and lossless like Rotate; Auto Levels stays (it is a row old chains carry) but as an Adjust switch.
- `image.ops.batch-is-batch-apply` — **[GAP]** (#6363) every batch from edit mode, over the selection or the folder, is one `POST /api/images/batch-apply` call carrying the operation and the params the single control would send (the `image.batch_apply` action: preview of three, one apply, batch undo and per-page undo, `image.enhance.batch-preview-undo`), from one sheet, `ImageCleanupBatchSheet`, offered for every operation; the client-side per-document loops (`ImageEditorModel.batchApply`, the toolbar `batchMenu`'s Rotate, Straighten, Auto-Enhance and Remove Background) are deleted; a split, which makes pages and has no before/after (`image_editing.py:1244`), shows the count and the names of the first three pages instead of pairs. Acceptance: with a 12-page selection and Rotate chosen for the selection, a stub engine sees one preview call, one `batch-apply` and no per-document `operations/rotate`; Undo All sends one batch undo; a split batch shows "12 pages" and three names and no before/after; `ImageEditorModel.batchApply` no longer exists.
- `image.ops.matrix-is-complete` — **[GAP]** (#6363) the operation × door matrix (`agent-work/status/briefs/image-ops-matrix.md`, lane-ie 2026-11-06, corrected by this spec) is pinned, not kept by hand: one engine test walks the chain vocabulary and asserts each operation has its action, its node and its Prepare operation id, and one Swift test asserts its editor control and that the batch sheet offers it; a new operation added to `media/enhance` without all four doors fails both. Acceptance: adding a step module `noop` (a `Params` and a `run`) under `media/enhance/` in a test tree fails the engine test naming the three missing doors; removing a section from Adjust fails the Swift test naming the operation.
  - Answered by Step 4.7 (#6362, landed 2026-11-06 while this stage was written): Enhance, Clean up the folder and the show-through Include / Leave Out are reachable in the Source pane without edit mode (`SourcePaneImageControls`); the FULL set of operations stays in edit mode, as this stage says, and those three viewing-mode controls call the same actions and batch-apply route Stage 5 names, so they are doors onto the same operations, not a second set.

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
| `image.enhance.page-region-shown-in-the-app` | `tests/unit/recipes/test_page_crop_writes_page_region.py`; app `ImageEditDirectToolsTests.swift` | needed | One Inspector row and one dashed rectangle with the key; none without. |
| `image.enhance.furniture-lines-never-found` | `tests/unit/recipes/test_find_regions_inside_page.py` | not needed | Ruler, card and border yield no line inside the box; `lines_outside` 0; the sample run reports the saving. |

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

### Stage 2 — The ported methods

#### Step 2.1 — Rotate, deskew, split (#6190; the Enhance half is Step 4.3 since 2026-11-05)
- Behaviours: `image.enhance.rotate-deskew`
- Tests: fichero-server/tests/unit/media/test_image_ops_legacy_port.py, fichero-server/tests/unit/media/test_page_split.py
- Depends on: 1.2
- Size: M

#### Step 2.2 — Stains and ruled lines (#6195)
- Behaviours: `image.enhance.stain-flattening`, `image.enhance.ruled-lines`, `image.enhance.split-spread`
- Tests: fichero-server/tests/unit/media/test_enhance_stains_and_ruling.py, fichero-server/tests/unit/media/test_page_split.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — Show-through, one setting then regions (#6196; the show-through-only verso is Step 4.6 since 2026-11-05)
- Behaviours: `image.enhance.bleed-through-suppression`, `image.enhance.show-through-one-setting-then-regions`
- Tests: fichero-server/tests/unit/media/test_enhance_bleed_through.py
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

#### Step 3.3 — The onboarding step (#5580; the batch is Step 4.5 since 2026-11-05)
- Behaviours: `image.enhance.onboarding-step`
- Tests: fichero-server/tests/unit/recipes/test_start_plan_prepare_step.py
- Depends on: 3.2
- Size: M

### Stage 4 — Closing the milestone's open issues (owner approved 2026-11-05)

One step per open issue, in the order to build them. Each names its side (engine or app), what the
step adds to what Stages 1-3 already landed, and the sample it waits on (see "Measured"). A step that
waits on a sample ships its synthetic test first and keeps the line `[PARTIAL]` until the sample runs.

#### Step 4.1 — The page region shown in the app: an Inspector row and a dashed outline at rest (#6187)
- Side: app only (the engine's attribute is built, `prep.page.region-attribute-and-page-box`)
- Behaviours: `image.enhance.page-region-shown-in-the-app`
- Tests: fichero-server/tests/unit/recipes/test_page_crop_writes_page_region.py, fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift
- Depends on: 1.3
- Size: S

#### Step 4.2 — Furniture lines pinned: ruler, colour card and border on the fixture; the saving reported on the sample run (#6189, #6185)
- Side: engine
- Behaviours: `image.enhance.furniture-lines-never-found` (Leave Out's reading of the box stays Step 3.1)
- Tests: fichero-server/tests/unit/recipes/test_find_regions_inside_page.py
- Depends on: 4.1
- Waits on: sample 2 (Doc10/Doc11 with hand-drawn boxes) for the real figures; the fixture test does not
- Size: S

#### Step 4.3 — Auto Enhance is the ported cleanup by default; sharpen once; the reference-sample run (#6190)
- Side: engine and app
- Behaviours: `image.enhance.editor-enhance-is-the-new-step`, `image.enhance.sharpen`, `image.enhance.contrast-clahe`, `image.enhance.yellowing`
- Tests: fichero-server/tests/unit/media/test_image_ops_legacy_port.py, fichero-server/tests/unit/media/test_enhance_three_doors.py, fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift (the popover's default request; the Adjust controls' own file is Step 2.4's)
- Depends on: 2.1
- Waits on: sample 1 (the typed before/reference pairs) for the 3/255 check
- Size: M

#### Step 4.4 — The working rendition, once: the key (built), its consumers and the thumbnail cut from it (#6200, #6193; was Step 1.4)
- Side: engine
- Behaviours: `image.enhance.working-rendition-once`, `image.enhance.reads-without-the-source`
- Tests: fichero-server/tests/unit/db/test_working_rendition_once.py
- Depends on: 1.1
- Size: M

#### Step 4.5 — Cleanup as a batch in the app: the sheet calls batch-apply, three samples, counts, undo (#6192)
- Side: app (the engine's batch-apply, preview and undo are built)
- Behaviours: `image.enhance.batch-preview-undo`
- Tests: fichero-server/tests/unit/api/test_image_batch_prepare.py, fichero/Tests/Unit/general/Views/Preview/ImageBatchPrepareTests.swift
- Depends on: 4.3, 4.4
- Size: M

#### Step 4.6 — The show-through-only verso listed, included with one click; the threshold on real pages (#6197)
- Side: app, then engine tuning
- Behaviours: `image.enhance.show-through-only-verso`
- Tests: fichero-server/tests/unit/media/test_show_through_only_verso.py, fichero/Tests/Unit/general/Views/Preview/BlankPagesHiddenTests.swift
- Depends on: 2.3, 4.5
- Waits on: sample 4 (a real recto/verso pair) for the threshold
- Size: S

#### Step 4.7 — The enhancement controls reach the Source pane without edit mode (#6362)
- Side: app, and the engine's Prepare check worklist
- Built (app unrun, engine tested, 2026-11-06): `SourcePaneImageControls` over the Source pane while it only shows the page (Enhance is the audited `image.enhance`, Clean up the folder opens `ImageCleanupBatchSheet`, a show-through page shows `ShowThroughPageRow`); the Inspector's Edits facet shows the same row; the Prepare Images check list carries show-through rows with Include / Leave out (`test_a_show_through_only_page_is_listed_with_its_recto_until_a_person_includes_it_or_says_leave_out`). Sentence 1's toolbar sits as an overlay on the pane, not inside the shared reader bar.
- Behaviours: `image.enhance.editor-enhance-is-the-new-step`, `image.enhance.batch-preview-undo`, `image.enhance.show-through-only-verso`
- Why: today the Enhance popover, "Clean up the folder" and "Apply to the rest of this folder" live only in `ImageEditorView`'s toolbar, which the Source pane shows only in edit mode; the show-through Include / Leave Out lives only in the Library pane's line above the rows.
- Acceptance (app, to build):
  1. With the Source pane showing an image page and edit mode off, its bottom toolbar offers *Enhance* (Auto Enhance, the clahe default of Step 4.3, applied to this page with one click and undone by the window's Undo) and, when the page sits in a folder, *Clean up the folder*, which opens the same `ImageCleanupBatchSheet` as the editor's menu; a test builds the toolbar's item list for a page in a folder, a loose page and a PDF page and finds the two items on the first, only *Enhance* on the second and neither on the third.
  2. With a show-through-only page in the Source pane, the pane says "show-through of <recto's name>" beside the page, with the one button *Include* (or *Leave Out* once included), running `image.include_show_through_only`; the Inspector's Edits facet shows the same sentence and button for that page.
  3. The Prepare Images check list names a show-through-only page as a row ("show-through of <name>, left out") with *Include* and *Leave out*, the same action; the engine's `prepare_check` worklist carries such pages, and a test pins that a marked page is in the list and an included one is not.
  4. No new request type: every control calls the existing audited action or batch-apply route.
- Tests: fichero/Tests/Unit/general/Views/Preview/SourcePaneImageActionsTests.swift, fichero-server/tests/unit/recipes/test_prepare_check_worklist.py
- Depends on: 4.3, 4.5, 4.6
- Size: M


### Stage 5 — Image operations: one action, three doors; edit mode gets all of them (owner 2026-11-06, #6363)

The inventory is lane-ie's matrix (`agent-work/status/briefs/image-ops-matrix.md`, corrected 2026-11-06: split has two nodes, yellowing has no standalone op, ruled lines, show-through, stains and binarise have chain ops and nodes). Engine before app; each step one reviewable commit with its tests. The editor's own tool shapes (page box, dial, gutter line, Adjust sliders) stay owned by `../ui/preview-image-editing.md` Steps T.1-T.4; Stage 5 adds the doors and the guardrails, not a second drawing of the tools.

#### Step 5.1 — One action per operation, from the step registry (#6363)
- Side: engine
- Behaviours: `image.ops.one-action-per-operation`
- Tests: fichero-server/tests/unit/media/test_enhance_suite_registry.py, test_image_ops_actions.py (not yet written; beside `tests/unit/api/test_image_batch_prepare.py`)
- Depends on: 2.4
- Size: M

#### Step 5.2 — Every operation is a node and a Prepare Images operation (#6363)
- Side: engine
- Behaviours: `image.ops.workflow-node-per-operation`, `image.ops.recipe-designer-offers-every-operation`
- Tests: fichero-server/tests/unit/media/test_enhance_suite_registry.py, fichero-server/tests/unit/media/test_enhance_three_doors.py, fichero-server/tests/unit/recipes/test_start_plan_prepare_step.py
- Depends on: 5.1
- Size: M

#### Step 5.3 — Edit mode offers every operation; every batch is batch-apply (#6363, #6362)
- Side: app (the engine's actions, nodes and batch-apply are Steps 5.1, 5.2 and 4.5)
- Behaviours: `image.ops.edit-mode-offers-every-operation`, `image.ops.batch-is-batch-apply`
- Tests: ImageEditAdjustControlsTests.swift (not yet written, Step T.4's), fichero/Tests/Unit/general/Views/Preview/ImageCleanupBatchTests.swift, ImageEditEveryOperationUITests.swift (not yet written; in fichero/Tests/UI/general/, XCUITest, subclass `FicheroUISessionTests`)
- Depends on: 5.1, 4.5
- Size: M

#### Step 5.4 — The matrix pinned: a new operation without all four doors fails the gate (#6363)
- Side: engine and app
- Behaviours: `image.ops.matrix-is-complete`
- Tests: fichero-server/tests/unit/media/test_enhance_suite_registry.py, ImageEditAdjustControlsTests.swift (not yet written, Step T.4's)
- Depends on: 5.2, 5.3
- Size: S

- test (to write): `test_image_ops_actions.py` in fichero-server/tests/unit/api/ (each chain op has an `image.<op>` action; invoke writes one row and one audit entry; undo removes the row)
- test (to write): `ImageEditEveryOperationUITests.swift` in fichero/Tests/UI/general/ (enter edit mode on a page; every operation appears once across the toolbar and Adjust; Apply to Selection on Rotate for 3 pages makes one batch call)

#### Step 5.5 — A long operation stays inside the machine (#6384)
- Side: engine
- Behaviours: `image.ops.long-operation-is-bounded`, `image.ops.long-operation-is-a-job`
- Tests: fichero-server/tests/unit/media/test_remove_background_memory_6384.py, fichero-server/tests/unit/api/test_image_operation_job.py
- Depends on: none
- Size: S

#### Step 5.6 — A missing library says so (#6384)
- Side: app
- Behaviours: `image.ops.missing-library-says-so`
- Tests: fichero/Tests/Unit/general/Models/MissingLibraryNoticeTests.swift
- Depends on: none
- Size: S

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

Asked 2026-11-05 (Stage 4; the owner's answer goes in Rulings, the step text does not guess):

1. **Where the sample pages live.** Reduced copies committed under `fichero-server/tests/fixtures/image_enhance/` (the archive's pages enter the public history; private manuscripts were purged from it on 2026-10-25), or a folder outside the repo named by `FICHERO_IMAGE_PREP_SAMPLES` and read by a by-hand check that pytest never collects (today's shape)?
2. **The legacy source.** `~/code/fichero-archive` holds only `stale-branches-2026-07-30.bundle`; no plain legacy tree is on this Mac. Is the method table in "The legacy methods, read closely" the port's source of record, or should the bundle be unpacked and the functions re-read before Step 4.3 closes #6190?
3. **Auto Enhance by default.** Step 4.3 makes a new Enhance row `clahe` unless a person turns the switch off. Is the PIL enhance to stay reachable as a choice in the popover, or only as the re-render of old rows?
4. **The Inspector row's words** for the page region (Step 4.1): the share, method and confidence as drafted, or the box's four numbers too?
