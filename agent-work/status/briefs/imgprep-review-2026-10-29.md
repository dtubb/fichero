# Image preparation and image editing — review (2026-10-29)

Written for the spec rewrite of `docs/contributor_manual/specs/source/image-preparation.md` (#5382),
`docs/contributor_manual/specs/source/image-enhancement.md` (#6185) and the tools section added to
`docs/contributor_manual/specs/ui/preview-image-editing.md`. Facts read from the code of
`origin/integration` at fba46989f, the legacy tree at `~/code/fichero_archive/_archive/fichero_legacy/tools/`,
issues #5382, #6185, #6188, #6189, #6190, #6192, #6198, and the spec review of 2026-10-20
(`agent-work/status/spec-review-2026-10-20.md`, which touched only the onboarding and card lines, not the
image tools). The builder's inventory (`agent-work/status/briefs/imgprep-inventory.md`) had not appeared when
this was written; the code was read directly instead.

## 1. What exists

### The engine

| Piece | Where | State |
| --- | --- | --- |
| Find the page with Apple Vision's document outline, cut a spread at the darkest column of the middle band, propose below a confidence | `fichero-server/src/fichero_server/media/page_split.py` (`detect_document_outline`, `find_gutter`, `plan_split`), node `workflows/tools/split_pages.py` | built, pinned by `fichero-server/tests/unit/media/test_page_split.py` on 11 Sergio photos. The four-corner quad is returned, not stored; no perspective correction; the outline is not written as an attribute. |
| Deskew by Hough median (±15°) | `media/image_ops.detect_deskew_angle`, node `deskew_images.py`, editor `straighten` | built; the angle is not recorded on the row (`straighten` stores `angle: 0` for "auto"). |
| Content bounding box | `media/image_ops.detect_content_bbox`, node `auto_crop_border_images.py` | built; a per-pixel loop (#6190); returns the whole frame on a grey table (the page_split docstring measured 11 of 11). |
| Remove background (black mount, scan border) | `media/image_ops.remove_black_background_opencv`, `remove_scan_background` | built; it is really a dark-mount page finder wearing an "AI background removal" label. |
| Enhance | `media/image_ops.apply_operation("enhance")`, node `enhance_images.py` | PIL brightness, contrast, sharpness, autocontrast, median denoise. All three sliders default to 1.0, so the default is a no-op. Nothing local: a stain and the ink beside it get the same stretch. |
| Fuzzy clean, denoise, adaptive binarize, grayscale, flips, auto levels | `media/image_ops.py`, `workflows/tools/*_images.py` | built, each pinned by `fichero-server/tests/unit/workflows/test_*_images.py`. |
| Segment | `media/image_ops.apply_operation("segment")` returns the image unchanged (`image_ops.py:323`) | the editor's Segment tool writes a chain row that does nothing to the pixels; regions belong to Find Regions. |
| Edit chain | `api/routes/ingest/image_editing.py`, model `ImageEditChain` | built: reversible rows, preview from the original every time, batch for crop and split with whole-batch undo (#1265). |
| Renditions | `persist_workflow_renditions` in `workflows/tools/image_edit_chains.py` | built: a workflow's outputs become renditions. The prepared image of the recipe is still not attached (#5386, [BROKEN]). |
| Upright frame | `media/upright.py` | built: EXIF applied once, `frame: "upright"` on new geometry (Test 14, ## 1114). |
| YOLO | `llm/yolo_runtime.py` (PyTorch on MPS), `recipes/regions.py`, `training/yolo_set.py`, `training/yolo_local.py` | built for regions: the DocLayNet card runs and a fine-tune ran on this Mac (two epochs, 11 s). No page detector; nothing trains from corrected page boxes. |
| Onboarding | `recipes/stages.py` stage `prepare-images`: "Two pages per image?" (default no) and "Straighten, crop, brighten?" (default none) | the answers are stored; only `split-pages` runs; `prepare-the-image` is "Fichero's own rules, nothing to configure" in `recipes/start.py:569` and the Start plan does not run it. |
| Blank or faded sample checks | `recipes/prepare.py` (`is_faded`, `sample_shows_faded`, `is_text`) | built; used by nothing a person sees. |
| Leave Out | `recipes/leave_out.py` | reads `page_box` metadata that nothing writes (#6198). |

### The app (Preview's image editing)

`fichero/fichero/Views/Preview/ImageEditor/` (12 files, 2,402 lines) and `fichero/fichero/Services/ImageEditingService.swift`.
Reached from the Preview pane's Edits facet. One toolbar, a side panel of steps with its own "Add Step" tool
set, a marquee overlay, a live Core Image preview for the sliders, a clipboard for copying chains.

### The legacy tools (`fichero_archive/_archive/fichero_legacy/tools/`)

`crop.py` (881 lines: YOLOv8 page model `fichero_resources/yolo_models/yolov8s-fichero.pt` first, then
contour templates `dark_background` 120, `light_background` inverse 180, `otsu`, `adaptive`, `edge`; area
0.15–0.99, aspect 0.5–2.0, pad 30), `split.py` (810 lines: aspect gate 1.35, a "periodic binding pattern"
score for spiral notebooks, darkest column in the middle, a neighbour test, cover and label detection by
edge density and filename), `rotate.py` (Hough lines within ±2°, median), `enhance.py` (LAB CLAHE clip 2.2
tile 8 for handwriting, 1.6/16 for print; b-channel yellow reduction; unsharp), `remove_background.py`
(black mount mask). The enhancement spec of 2026-10-26 already restated these parameters and reproduced
the owner's "good result" to 1.4/255. Nothing in the legacy did stains, ruling, show-through or blank
pages.

## 2. What is wrong

### The onboarding step does not run

The Set Up stage asks two questions and runs nothing but the splitter. "Straighten, crop, brighten" is
stored and ignored (`recipes/start.py:569`). There is no sample, no suggested default, no time shown for
the step, and no page is listed for a person to check afterwards. The person reaches Preview's editor
only by opening each page by hand.

### Automatic preparation has no check-and-correct path

`split_pages` proposes a cut below its confidence (`MIN_GUTTER_CONFIDENCE = 0.15`), but the proposal goes
nowhere a person sees: there is no worklist, no dashed outline on the page, no "accept" or "move the
gutter". A correction on one page does not reach the others in the folder. No correction is kept as a
training label.

### The page outline is lost

Vision returns a four-corner quad with a confidence. `split_pages` keeps the box, drops the quad, writes
no `page_region` attribute and no `page_box` metadata. Leave Out therefore never says "off the page"
(#6198), Find Regions runs on the whole frame including the ruler (#6189), and the Preview cannot show
where the page was found.

### The editor's tools: unclear, duplicated, not visual

Every tool is a one-shot button that posts to the engine and shows the result; none is a direct
manipulation on the picture except the marquee. The icons, by file and line:

| Icon | Where | Problem |
| --- | --- | --- |
| `wand.and.stars` | `ImageEditorView+Toolbar.swift:32` (the "Edited" half of the Original/Edited segment), `ImageEditChainPanel.swift:130` (empty-chain placeholder), `ImageEditingService.swift:44` (the Enhance row's icon) | one glyph, three meanings; in Photos the wand means Auto Enhance, here it means "show edited". |
| `slider.horizontal.3` | `ImageEditorView+Toolbar.swift:64` (Enhance button), `ImageEditChainPanel.swift:62` (the "Edit Steps" panel title), `ImageEditChainPanel+Steps.swift:347` (Add Step → Enhance), `ImageEditingService.swift:54` (fallback icon for any unknown op) | the Enhance tool and the panel it lives in share a glyph; the Enhance row in the chain shows the wand instead, so the same step has two icons on one screen. |
| `crop.rotate` | `ImageEditorView+Toolbar.swift:56` (Straighten), `ImageEditChainPanel+Steps.swift:117`, `ImageEditingService.swift:43` | the symbol depicts crop-and-rotate; a person reads it as a crop tool. |
| `angle` | `ImageEditorView+Toolbar.swift:76`, popover titled "Rotate" at `ImageEditorView+Popovers.swift:60` | a second rotate tool beside Rotate Left/Right and Straighten; its help says "fine straighten angle", its title says "Rotate". Three controls for one idea. |
| `rotate.right` | `ImageEditorView+Toolbar.swift:53` and `ImageEditingService.swift:42` | every rotate row in the chain shows the right-turn glyph, including a left turn and a 180. |
| `person.and.background.dotted` vs `scissors` | `ImageEditorView+Toolbar.swift:83`, `ImageEditChainPanel+Steps.swift:195`, `:352` vs `ImageEditingService.swift:49` | a portrait-subject symbol for a document tool; the toolbar and the chain row disagree. The help says "AI-powered"; the code is an OpenCV threshold. |
| `sparkles` | `ImageEditorView+Toolbar.swift:86`, `ImageEditChainPanel+Steps.swift:217`, `:355` | sparkles reads as "AI" or "auto"; the tool is a median despeckle. |
| `square.split.2x1` vs `square.split.bottomrightquarter` vs `rectangle.split.2x1` | `ImageEditorView+Toolbar.swift:89`, `ImageEditChainPanel+Steps.swift:239`, `:359` (Segment) vs `ImageEditingService.swift:50` (the Segment row) vs `ImageEditorView+Toolbar.swift:162` (the Side-by-Side compare mode) | three near-identical glyphs; the Segment tool and its own chain row differ; the compare mode's glyph is the one that should mean "split a spread", and the Segment op does nothing to the image (`image_ops.py:323`). |
| `arrow.counterclockwise.circle` | `ImageEditorView+Toolbar.swift:109` and `ImageEditChainPanel.swift:76` | Revert to Original twice on one screen. |
| `minus.circle` | `ImageEditChainPanel.swift:180` | a third way to remove a step, beside Undo (`:103`) and the Edit menu. |
| `crop` | `ImageEditorView+Toolbar.swift:133`, only while a marquee exists | the one tool the owner wants most is hidden until a drag happens; Preview and Photos show Crop always and enable it on selection. |
| `highlighter` | `ImageEditorView+Toolbar.swift:138` | "save selection as annotation" is reading markup, not an image edit; it appears only with the marquee. |
| `square.stack.3d.up` | `ImageEditorView+Toolbar.swift:273` (Apply to N menu) and `ImageEditorView+Clipboard.swift:41` | the same glyph for "batch" and for "paste steps to all". |
| `photo` / `wand.and.stars` segment, `rectangle` / `rectangle.righthalf.inset.filled.arrow.right` / `rectangle.split.2x1` segment | `ImageEditorView+Toolbar.swift:29-44`, `:155-169` | two compare controls (Original/Edited, and Single/Wipe/Side-by-Side) with overlapping states; Single+Original and Single+Edited are the same two pictures the wipe already shows. |
| Add Step panel | `ImageEditChainPanel+Steps.swift:290-362` | a second, text-labelled copy of the whole toolbar inside the side panel. |
| Batch menu | `ImageEditorView+Toolbar.swift:242-280` | a third copy of four tools as text, with a fifth name ("Auto-Enhance") for Enhance. |

Missing tools: a page-box (crop) that can be dragged by its corners and filled by "find the page"; a
split that shows the gutter line and lets it be moved; marks for the ruler and the colour card; a blank-page
mark; enhancement with before/after on the picture while the slider moves (the live preview exists for the
three PIL sliders only).

### Specs

`image-preparation.md` (2026-10-03) and `image-enhancement.md` (2026-10-26) overlap: both own page crop,
deskew and split (`prep.find-the-page`/`image.enhance.page-crop`, `prep.straighten-and-flatten`/
`image.enhance.rotate-deskew`, `prep.split-at-the-gutter`/`image.enhance.split-spread`). Four issues (#6188,
#6189, #6190, #6192) cite behaviour ids (`prep.page.opencv-default-yolo-optional`,
`prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported`, `prep.enhance.clahe-ported`,
`prep.crop.content-bbox-is-fast`, `prep.cleanup.*`) that exist in no spec. The editor tools are described
only as a change table in the enhancement spec; `ui/preview-image-editing.md` has no behaviour for any tool.

## 3. The gaps, in one list

1. The Set Up step: questions with suggested defaults from a sample, the steps that run by themselves,
   the time shown before Start, a runnable `prepare-the-image` in the Start plan.
2. The page outline kept: `page_region` attribute (quad + box + method + confidence) and `page_box`
   metadata; Find Regions and Leave Out read it.
3. Check and correct: a worklist of proposals and a sample of confident pages; the page box, gutter,
   rotation, blank mark and furniture marks editable on the picture; a correction applied to the folder.
4. Corrections as training labels: a one-class page detector fine-tuned from corrected boxes when there
   are enough; adopted only when it beats Vision on held-out pages.
5. Turn by the text (0/90/180/270), blank pages marked, ruling suppressed, stains flattened, show-through
   suppressed (all specified in the enhancement spec, all [GAP]).
6. The editor: one tool set, one icon table, direct manipulation, before/after on the picture.
7. The prepared image attached as a rendition (#5386), with its steps recorded (#6191).

## 4. Method decisions and trade-offs

### Finding the page

| Method | For | Against | Decision |
| --- | --- | --- | --- |
| Apple Vision `VNDetectDocumentSegmentationRequest` (built) | in the OS, no download, no licence, found 11 of 11 Sergio notebooks at 0.99, returns the quad, ~0.3 s | macOS only (the engine already runs only inside the Mac app); trained on documents, so a dark mount with a page and a ruler may return the whole mount | **default card** |
| OpenCV contours, the legacy templates (`crop.py`) | Apache-2.0, already a dependency, fast, no model, handles the dark mount by threshold | hand-tuned thresholds; fails on a busy or light table; needs the template chosen (auto by border brightness) | **fallback card**, and the dark-mount method |
| YOLO page detector, trained from corrected boxes | learns this collection's furniture (ruler, card, hands); the pipeline exists for regions | needs PyTorch loaded (seconds, GBs), needs a few dozen corrected pages, Ultralytics is AGPL-3.0 | **third card, optional**, offered only after corrections exist and adopted only on evidence |

The bake-off between cards is the existing recipe mechanism (`source.recipe.*`): the same sample of pages,
box overlap against the hand-drawn boxes, and later character error rate.

**Licence.** Ultralytics 8.4 is AGPL-3.0; so is Fichero (`LICENSE`, and the ruling of 2026-10-09 recorded at
`fichero-server/pyproject.toml:307`). Linking is compatible. Two cautions stay in the spec: (1) Ultralytics
holds that models trained with its code inherit AGPL; a Fichero-trained page detector is therefore AGPL,
which is fine for Fichero's own use and for sharing with a recipe, but it cannot be relicensed; (2) the
App Store's terms are widely held to conflict with the (A)GPL. Fichero ships by DMG and TestFlight today
(`distribution-rulings-2026-08-25`), so this is a note for the App Store decision, not a blocker. Apple
Vision and OpenCV (Apache-2.0) carry no such caution, which is one more reason they are the default.

### Splitting

Vision's outline plus the darkest column (built) with the legacy aspect gate (narrower than tall is one
page) and neighbour test (the gutter must be darker than 180 and 15 darker than its neighbours). The
legacy "periodic binding pattern" score is not ported: on the Sergio set the gutter is already found by
darkness, and the score's thresholds (`vertical_pattern > 1000`, `width > 2000`) are tied to one camera.
Covers and labels by filename are not ported (cataloguing owns names).

### Turning and straightening

Quarter turns from the text: Vision text recognition tried at four orientations on a reduced copy, the one
with the most recognised words wins; skipped when the first try is confident. This reuses what the engine
already calls (`VNRecognizeTextRequest`) and avoids a new model. Deskew stays Hough median, with the angle
recorded on the row and skipped under 0.3°.

### The ruler and the colour card

They are **regions**, not pixels (owner ruling 2026-10-26: prep never marks, Leave Out never paints). The
page outline excludes them when they lie beside the paper. When they lie on the paper, a person marks them
in the editor (a region with kind `ruler` or `colour card`) or the layout card finds them; Leave Out gives
every line inside such a region that reason. Marked regions are also labels for the layout detector.

### Enhancement

The enhancement spec's choices stand: the legacy CLAHE as one `contrast` step with sliders, stains by
morphological background estimate, ruling by hue mask, show-through by local-contrast threshold and, where
the verso is in the folder, by registered subtraction. All model-free, all OpenCV, all as renditions.

### The editor

Preview and Photos conventions: tools that act on the picture directly (drag the page box's corners, drag
the gutter line, drag a dial to straighten), one icon per tool everywhere it appears (toolbar, chain row,
batch sheet), the automatic result shown as a proposal a person adjusts rather than a button that
replaces the picture. Compare collapses to one gesture (press and hold to see the original, as Photos) and
one wipe. Remove Background, Despeckle, Segment and the second Rotate leave the toolbar: the first becomes
Crop's dark-mount method, the second folds into Stains, the third does nothing, the fourth is Straighten.
