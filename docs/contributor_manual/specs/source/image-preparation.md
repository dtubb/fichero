# Source Model — Image preparation: the Set Up step that turns photographs into pages a model can read — Design Spec (#5382)

> Milestone: source-model
> Manual: TBD — a section, "Preparing images", explaining what Fichero does to a photograph before
> reading it (find the page, split, turn, straighten, clean), that the original is never changed,
> how to check and correct what it did, and how to see whether a step helped.
>
> Design-led (Testing Constitution). **Status: DRAFT — ruled 2026-10-29, ready to build** (first draft
> 2026-10-03; rewritten 2026-10-29; the owner's rulings of 2026-10-29 folded in the same day, see
> Rulings; no open question remains; the APPROVED tag waits only on the manual section and the first
> pinning test, as `check_spec_manual_refs` and `check_specs_have_tests` require). Review:
> `agent-work/status/briefs/imgprep-review-2026-10-29.md`. Stage 1 to 2 of `../../roadmap/research-pipeline.md`.
>
> **Three specs, one line between them.** This spec owns the **Set Up step**: the questions and their
> defaults, what runs by itself, finding the page, squaring a lopsided photograph, dewarping a curved
> page, splitting, turning, blank pages, the check-and-correct flow, the detectors as cards, how
> corrections train a detector, and the time and cost shown before Start (`prep.*`). `image-enhancement.md`
> (#6185) owns the **pixel steps that write renditions** (the whole OpenCV suite: contrast, yellowing,
> stains, ruling, show-through, binarise, denoise, sharpen, the working rendition, `image.enhance.*`) and
> the one function behind every door. `../ui/preview-image-editing.md` owns the **editor** a person corrects with (`preview.edit.*`,
> its tools in section C). Where two specs could say one thing, this spec cites the owner and does not
> restate it. The `prep.*` ids of 2026-10-03 are kept; the ids four issues cite but no spec carried
> (#6188, #6189, #6190, #6192) are added below with their tags.
>
> Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built · [BROKEN] built, wrong.

## Intent

Archives are photographed, not scanned: a book open on a table, two pages at once, a ruler and a colour
card beside the paper, a dark mount, the camera a little turned. Models read single, upright, flat, clean
pages; a photograph taken at an angle, or a bound page curving into the gutter, is neither flat nor
square. Image preparation turns the one into the other **by itself, for a whole collection**, as the first
step of a recipe, and a person **checks and corrects** it instead of doing it. Every result is a new
rendition beside the original, which is never changed. The step is judged by whether reading improves, not
by how the picture looks.

What the person sees: in Set Up, one card, "Prepare Images", with three short questions already answered
from a sample of their pages, and a line saying how long the step takes on this Mac. After Start, a short
list of pages to check: the ones Fichero was unsure about, and a few it was sure about, so the person sees
both. Each opens in Preview with the page box, its four corners, the cut and the turn drawn on the photograph,
ready to be dragged. A correction on one page can be applied to the rest of its folder. Enough corrections, and Fichero
offers to train a detector on them; the detector replaces the default only when it measures better.

The first test sets: Sergio Mosquera's notebooks (`fichero-projects/projects/sergio-notebooks`: 374
photographs, 3000×2000, open spiral notebooks on a dark table, a ruler along the top, the left page often
blank graph paper) and the Istmina scans (EAP1477 GHC_B12 Doc10 and Doc11: a wooden ruler down the left
edge, a grey colour card at the top, a wide dark border).

## What exists today

- **Finding the page and the gutter** (`fichero-server/src/fichero_server/media/page_split.py`, node
  `fichero-server/src/fichero_server/workflows/tools/split_pages.py`): Apple Vision's document outline
  (`VNDetectDocumentSegmentationRequest`), an outline narrower than tall left whole, the gutter at the
  darkest column of the middle band, a confidence from the gutter's depth, a proposal below 0.15. Pinned on
  11 Sergio photos by `fichero-server/tests/unit/media/test_page_split.py`. The four-corner quad is returned
  and dropped; no attribute, no `page_box`, no perspective correction.
- **Deskew** by Hough median (`media/image_ops.detect_deskew_angle`, ±15°), the editor's Straighten and the
  node `deskew_images`. The angle is not recorded on the row.
- **Content box** (`media/image_ops.detect_content_bbox`): a per-pixel loop that returns the whole frame
  on a grey table.
- **Remove background** (`media/image_ops.remove_black_background_opencv`, `remove_scan_background`): a
  dark-mount mask, labelled "AI background removal" in the editor.
- **The edit chain and renditions**: `preview.edit.*` in `../ui/preview-image-editing.md`; renditions from
  a workflow by `persist_workflow_renditions`. The recipe's prepared image is not attached as a rendition
  (#5386).
- **The upright frame** (`media/upright.py`): EXIF applied once, new geometry marked `frame: "upright"`.
- **The onboarding stage** (`fichero-server/src/fichero_server/recipes/stages.py`, `prepare-images`): two
  questions, "Two pages per image?" and "Straighten, crop, brighten?", stored and not run; the Start plan
  runs `split-pages` only and treats `prepare-the-image` as nothing to configure
  (`fichero-server/src/fichero_server/recipes/start.py`).
- **Sample checks that nobody sees** (`fichero-server/src/fichero_server/recipes/prepare.py`): a page is
  faded, a sample is text.
- **YOLO** (`fichero-server/src/fichero_server/llm/yolo_runtime.py`, `recipes/regions.py`,
  `training/yolo_set.py`, `training/yolo_local.py`): the DocLayNet layout card runs on the GPU and a
  fine-tune from corrected regions ran on this Mac. No page detector; nothing trains from page boxes.
- **The legacy tools** (`fichero_archive/_archive/fichero_legacy/tools/`, outside this repository): a
  YOLOv8 page model and contour templates (`crop.py`), the aspect gate and neighbour test (`split.py`),
  Hough rotation (`rotate.py`). Their methods are restated in `image-enhancement.md`; the code is never
  imported (`image.enhance.old-conventions-left-behind`).
- **Leave Out** (`fichero-server/src/fichero_server/recipes/leave_out.py`) reads a `page_box` that nothing
  writes.

## Prior art

Apple's own document scanning (Notes, Files) finds the paper with Vision's document segmentation and
corrects perspective from its quad; Fichero adopts the same request and keeps the quad. ScanTailor and
Transkribus prepare pages as an ordered sequence (crop, deskew, split, clean) with a review of the
unsure pages; Fichero does the same, as a recipe step with a worklist. Kraken and the eScriptorium flow
treat page geometry as data a later step reads (regions inside the page); Fichero stores the page outline
as a Shape so Find Regions and Leave Out can read it. Ultralytics YOLO is the usual trainable detector
for pages and page furniture; Fichero keeps it as an optional, trained card behind the two model-free
methods. Nothing here is invented.

## The design

### The Set Up step: three questions, answered from a sample

The stage `prepare-images` keeps its two jobs (`split-pages`, `prepare-the-image`) and asks, per project,
with the answers **suggested from a sample of five pages** (first, a quarter in, middle, three quarters,
last) before the person reads them; an answer is suggested when **three of the five** pages agree (owner
2026-10-29). Each answer is stored per folder: a notebook folder and a map folder of the same project can
differ. A fourth question, added 2026-10-29, belongs to Find Lines but is asked here so Set Up stays one
card: whether to check for lines and words the segmenter missed.

| Question | Choices | Suggested when | Default without a sample |
| --- | --- | --- | --- |
| Two pages in one picture? | yes / no | the sample's outlines are wider than tall on 3 of 5 | no |
| Anything beside the page? | ruler · colour card · dark mount or table · nothing | the outline covers under 85 % of the frame on 3 of 5 (the first three are one answer: "find the page"; the ruler and card choices add Leave Out's reasons) | nothing |
| The paper | ruled or graph paper · stained or faded · writing shows through | `recipes/prepare.sample_shows_faded`; a hue mask finds thin regular coloured lines on 3 of 5; a mirrored faint copy of the previous page on 3 of 5 | none |
| Check for missed lines and words? | yes / no | the sample's Find Lines (the bake-off already segments the sample) leaves over 3 % of the ink outside the line boxes on 3 of 5, or any sample line reads under 60 % of the page's characters per width (`source.segment.check-lines.*`) | yes for handwriting, no for typescript |

Below the questions, one line: *Finds each page, turns it upright and straightens it; cuts spreads into
pages; marks blank pages. About 2 min for 374 pages on this Mac. Nothing leaves this Mac.* The time comes
from `prep.estimate.*` below; the sentence is the engine's (`how_it_works`), never the app's.

**What runs by itself, whatever the answers:** find the page and crop to it (a no-op when the page fills
the frame), square a lopsided page from its corners, flatten a page curved toward the gutter, turn
upright by the text, straighten (skipped under 0.3°), mark and hide blank pages. **What the answers
switch on:** split (two pages), contrast and yellowing (faded), ruling, show-through, the check for missed
lines (`image-enhancement.md`, `segments-and-geometry.md`). A step that finds nothing to do writes
nothing.

### The operations, in order

1. **Find the page.** Apple Vision's document outline first; the contour finder (the legacy templates,
   auto-chosen by the border's mean brightness) where Vision answers nothing or under 0.5; the YOLO page
   card where one is installed and the recipe names it. The result is a `page_region` Shape on the image
   (quad, box, method, confidence; `segments-and-geometry.md`) **and** the document's `page_box` metadata
   in fractions, which Leave Out and Find Regions read. The crop is a rendition; the outline maps every
   later shape back to the photograph.
2. **Square the page** (perspective). When the quad's corners are not a rectangle (any side's angle from
   the frame's axes over 1°, or the two opposite sides' lengths differing by over 2 %), the page is warped
   to a rectangle from the four corners: `cv2.getPerspectiveTransform` and `cv2.warpPerspective` to the
   size the longer sides give, white fill. The source quad is the Vision outline or the contour finder's
   polygon (`cv2.approxPolyDP` on the largest contour, four corners), never a hand guess. The result is a
   rendition with the homography on its row, so every later shape maps back to the photograph through it.
   A page whose quad is already a rectangle writes nothing. Below the finder's confidence the quad is a
   proposal: the person drags a corner and Fichero squares from the corrected quad.
3. **Flatten the curve** (dewarp), for a bound book. After squaring, a page whose text lines curve or
   slant toward the gutter is flattened: text lines are found by connected components of the ink mask
   (the legacy `segment.get_connected_component_lines` idea) and each line's baseline is fitted with a
   quadratic; the baselines together give a smooth displacement field (a thin-plate spline through the
   baseline samples, `cv2.remap`) that straightens every baseline to horizontal and evens the stretch
   toward the gutter. The step runs only where the fitted curvature is over 0.5 % of the page height on
   the gutter side (both sides on a spread cut in two) and is skipped otherwise; a page with no text
   lines (blank, a map) is skipped. It is a rendition with the field's control points on its row. Its
   test is reading: lines in the gutter third must read no worse than before and the bake-off keeps the
   step only where it helps (`prep.judged-by-reading`).
4. **Split at the gutter.** An outline wider than tall is a spread; the gutter is the darkest column of
   the middle band, kept only when darker than 180 and 15 darker than its neighbours (the legacy test);
   pages come out in the cascade's reading order as child items. Below the confidence the cut is a
   proposal.
5. **Turn by the text.** One Vision text read on a reduced copy; the orientation is read from the order of the lines it returns (Vision reads every turn equally well, so a word count cannot decide: decided 2026-10-29); skipped under three lines. A
   lossless quarter turn, recorded with its reason.
6. **Straighten.** Hough median, the angle on the row, skipped under 0.3°; a page already squared or
   flattened is usually under that and writes nothing.
7. **Mark blank pages.** A page with no ink beyond its ruling (ink pixels under 0.2 % after the ruling
   mask) is marked blank: kept, dimmed, **hidden in the item view**, skipped by every later step (find
   regions, leave out, read, check), never deleted. A person unhides one with one click, and an unhidden
   page runs through the steps it skipped.
8. **Enhance** where asked: `image-enhancement.md`'s suite (contrast, yellowing, stains, ruling,
   show-through, binarise, denoise, sharpen), each a rendition.

Each operation reports a **confidence** and a **reason**; below its threshold it **proposes** instead of
changing: a dashed page box, dashed corner handles, a dashed gutter line, a turn shown as an arrow. Every applied operation is a
row in the page's edit chain with `method`, `confidence` and `who: run <id>` (`image.enhance.rendition-records-its-steps`).

### Check and correct

After the run, Set Up (and Activity's summary) shows **Pages to check: N**, which opens a worklist in the
Check lens (`checking.md`): every page with a proposal, plus one confident page in twenty as a sample, the
proposals first. Each row says what is unsure in words ("gutter faint", "page box covers 61 %", "turned
180° from its text"). A page opens in Preview's editor with the run's result drawn on the photograph: the
page box with corner handles, the gutter line, the turn. The person drags, or accepts with one key. A
correction **replaces the run's row** with a row `who: person`, keeping the run's values beside it so the
disagreement is a training label. "Apply to the rest of this folder" copies a correction's parameters in
fractions of the frame to the folder's other pages (the same notebook is photographed the same way), as a
batch with its own undo (`image.enhance.batch-preview-undo`). Marking a page as not blank, or blank, is a
correction too, and so is unhiding a blank page in the item view. The tools themselves are `preview.edit.tool.*`.

### Corrections train a detector

Corrected page boxes are labels. When a project holds **30 or more** corrected or accepted pages, Set Up
offers *Train a page finder from your corrections*: a one-class YOLO fine-tune (`training/yolo_set.py`,
`training/yolo_local.py`, the same pipeline as regions, #5525) **on this Mac's GPU, as a Hugging Face
job, or on a cluster through Slurm (ACENET)** through the existing training places and nothing new
(`../compute/training-and-evaluation.md`: `training.place.compared`, `training.place.this-mac-gentle`,
`training.place.hf-priced-first`, `training.place.slurm`; the cluster targets of
`../compute/targets-and-connection.md` and `../compute/hpc-runner-acenet.md`), the cost and time shown
first and the place allowed by Set Up Fichero (`source.onboard.places-cap-projects`). The Kraken
segmenter trained from accepted check-lines corrections (`source.segment.check-lines.corrections-train`)
goes through the same places. The offer appears once at 30 and
again after every 30 more; it is never started by itself. The result is a project card. It replaces the
classical finder **only on evidence**: the bake-off scores every page-finding card on the held-out
corrected pages (one in five, never trained on) by box overlap (mean IoU) and the recipe adopts the best;
a trained card that does not beat Vision and the contour finder stays installed and unused, and the
offer says so in words. Marked ruler and colour-card regions are labels for the layout detector in the
same way (`prep.yolo.fine-tune-from-corrected-regions`).

### Methods are cards, chosen by rule, replaced by evidence

| Job | Cards | Default | Licence |
| --- | --- | --- | --- |
| find the page | Apple Vision outline · contour finder · YOLO page detector (trained) | Vision, then contour | Vision: the OS · OpenCV: Apache-2.0 · Ultralytics: AGPL-3.0 |
| square the page | perspective warp from the quad | itself | OpenCV, Apache-2.0 |
| flatten the curve | baseline-field dewarp | itself | OpenCV, Apache-2.0 |
| split pages | the built-in splitter | itself | — |
| turn by the text | Vision text at four turns | itself | the OS |
| straighten | Hough median | itself | OpenCV, Apache-2.0 |
| find regions | Kraken `blla` · YOLO layout card | `blla` (`prep.regions.open-default`) | Apache-2.0 · AGPL-3.0 |

**Why Vision and OpenCV first.** Both are on every Mac the app runs on, load in well under a second, need
no download and no licence sheet, and found the page on every Sergio photo tried. **Why YOLO third and
optional.** It needs PyTorch resident (seconds and gigabytes), a model on disk, and corrected pages to be
worth training; its value is learning one collection's furniture, which only corrections can teach. **The
licence.** Ultralytics is AGPL-3.0, as Fichero is (`fichero-server/pyproject.toml`, ruled 2026-10-09), so
shipping it is compatible. Two consequences are stated here so nobody is surprised: a detector fine-tuned
with Ultralytics is itself AGPL by Ultralytics' reading, so it can be shared with a recipe but not
relicensed; and the App Store's terms are widely held to conflict with the AGPL, which matters only if
Fichero moves from DMG and TestFlight to the store. Neither default card carries that caution.

### Time and cost, before Start

Every operation here runs on this Mac and costs nothing; the Start sheet says so and gives the time: the
per-page seconds measured on this machine's last run of each card (recorded on the run, `recipes-run.*`),
or, before any run, the seed figure on the card, marked "estimate". Training a detector is the one thing
with a price: a local fine-tune says its minutes; a Hugging Face job says its rate and minutes from the set
size, through the existing estimate (`source.onboard.estimate-before-start`).

### Judged by reading

The bake-off (`source.recipe.*`) treats a preparation operation like any other job: the same sample read
with and without it, character error rate against checked pages, and an operation stays in the recipe only
where it helps. Ruling suppression in particular stays off until the bake-off shows it helps this
collection (ruling 2026-10-04: some models use the ruling as a line guide).

## Behaviors

### The step in Set Up

- `prep.setup.three-questions-suggested-from-a-sample` — **[GAP]** (#5580; owner 2026-10-29: five pages, three of five) the Prepare Images card asks the questions above (the id keeps its name; a fourth, the missed-lines check, was added 2026-10-29) with answers suggested from five sample pages (first, quarter, middle, three quarters, last) when three of the five agree (outline aspect, outline coverage, `sample_shows_faded`, a ruling mask, a mirrored-verso match, the sample's ink-outside and characters-per-width figures), each answer stored per folder; the person changes any. Today `recipes/stages.py` asks two questions with fixed defaults.
- `prep.setup.what-runs-by-itself` — **[GAP]** (#5580) find the page, square, flatten, turn, straighten and mark blanks run on every page whatever the answers; split, contrast, yellowing, ruling, show-through and the missed-lines check run only when their answer says so; a step with nothing to do writes no row. Built 2026-10-29 (partial): the `prepare-the-image` card (`runner._run_prepare`) now runs `crop_pages(prepare=True)` first on every page (find the page, square, flatten, turn, straighten, blanks; account `page_prep`), then the contrast step; `tests/unit/recipes/test_prepare_step_setup.py`. Not built: the answers gating split, contrast, yellowing, ruling, show-through; the five-page suggestions; the card's UX.
- `prep.setup.step-runs-from-the-start-plan` — **[GAP]** (#5580) the Start plan holds a runnable `prepare-the-image` entry naming the operations and their cards, before `find-regions`; its progress line says "Preparing images: 23 of 374 pages, about 2 min left" (`image.enhance.onboarding-step` is this line's twin in the enhancement spec and is retired in favour of it).
- `prep.estimate.time-on-this-mac-before-start` — **[GAP]** (#5580) the Start sheet shows the step's time as the per-page seconds measured on this machine's last run of each card times the page count, or the card's seed figure marked "estimate", and says the step costs nothing and leaves nothing this Mac; a training offer shows its minutes locally or its rate and minutes on Hugging Face.
- `prep.setup.how-it-works-is-the-engines-sentence` — **[PARTIAL]** (#5791) the one-line description under the questions is the job's topic text from the engine (`how_it_works`, `recipes/seed/topics.yaml`), never written in the app. Built: the mechanism. Missing: a topic for `prepare-the-image` that names the operations.

### Finding the page

- `prep.find-the-page` — **[OK]** (#5382, #6188) the page is found on a busy background and the photograph is cropped to it; the outline is kept as a geometry mapping back to the original. Built: `split_pages` finds it with Vision's outline and crops to its box (`media/page_split.py`). Missing: the quad stored, the attribute, the contour fallback, the crop as a rendition of the page. Built 2026-10-29 (lane/image-prep): `media/find_page.find_page` (Vision, then contour), the quad and `page_region` on the document, the crop as a rendition (`recipes/page_crop.py`). Tests: `tests/unit/media/test_find_page.py`, `tests/unit/recipes/test_page_crop_writes_page_region.py`.
- `prep.page.opencv-default-yolo-optional` — **[PARTIAL]** (#6188) `media/find_page.py` tries Vision's outline, then the contour finder (templates auto-chosen by border brightness: dark mount → `dark_background`, light table → `light_background`; largest external contour with area 0.15–0.99 of the frame and aspect 0.5–2.0; pad 30 px), then the YOLO page card only when its model is installed; it returns outline, method and confidence and never alters the original. On EAP1477_GHC_B12_Doc11_IMG_004 and a Sergio photo with no model installed the outline is within 2 % of the hand-drawn box. Built: Vision outline (trusted from 0.5), then the contour finder; both return the quad; the original is never altered; furniture (ruler, colour card) from the contour pass. Not built: the YOLO page card (Step 4.1 trains it) and the legacy templates beyond the auto dark/light choice.
- `prep.page.region-attribute-and-page-box` — **[OK]** (#6187, #6198) finding the page writes a `page_region` Shape (quad, box, method, confidence, `frame: "upright"`) on the image and the document's `page_box` metadata in fractions, the same numbers Leave Out reads (`image.enhance.page-crop-writes-page-box` is this line's twin and defers to it). `page_region` (quad, box, method, confidence, `frame: "upright"`, settings) and `page_box` are written together; a person's box is never replaced. `tests/unit/recipes/test_page_crop_writes_page_region.py`.
- `prep.page.detected-before-lines` — **[OK]** (#6189) when a page has a `page_region`, `recipes.regions.find_regions` gives the segmenter only that crop and maps every region and line back to the page image's frame; a fixture with a ruler strip and a dark border yields no line outside the region. Pinned by `tests/unit/recipes/test_find_regions_inside_page.py`.
- `prep.page.kraken-time-saved-is-reported` — **[PARTIAL]** (#6189) the run summary says per page the seconds with and without the region and the lines inside and outside it, on the Doc10 and Doc11 fixtures. Built: the run account says pages cropped, area saved, seconds and `lines_inside` / `lines_outside` the page box. Not built: the seconds WITHOUT the region on a run (it needs a second Kraken pass); `fichero-server/scripts/measure_page_crop.py` produces the before/after figures on real scans.
- `prep.crop.content-bbox-is-fast` — **[OK]** (#6190) `detect_content_bbox` is a NumPy reduction, under 0.5 s on a 3000×2000 image, with the same answer as today on the fixtures. NumPy reduction; 2400x1700 content in a 3000x2000 frame well under 0.2 s, the loop's answer unchanged (`tests/unit/media/test_image_ops_legacy_port.py`).
- `prep.page.remove-background-is-the-dark-mount-method` — **[PARTIAL]** (#6188) the editor's Remove Background and the `remove_background_images` node become the contour finder's dark-mount method inside find-the-page; the old operation name survives only so an existing chain re-renders unchanged. Built: the old `remove_background` re-renders unchanged (pinned) and the contour finder handles the dark mount. Not built: rewiring the editor's operation and the node onto the finder.

### Squaring and flattening

- `prep.square.perspective-from-the-quad` — **[OK]** (#5382; owner 2026-10-29) a page whose found quad is not a rectangle (a side over 1° off the frame's axes, or opposite sides differing by over 2 %) is warped to a rectangle from its four corners (`cv2.getPerspectiveTransform`, `cv2.warpPerspective`, white fill, the size the longer sides give) as a rendition whose row carries the homography; a rectangular quad writes nothing; the `page_region` and every later shape map back through the homography (`frame` names the rendition). On a fixture photographed at 15° the warped page's edges are within 0.5° of the axes and the hand-drawn box overlaps the result over 0.97. Built 2026-10-29: `media/square_page.py` (`quad_is_rectangular`, `square_page`, `unsquare_points`), the `square` edit operation, a `squared` rendition from `recipes/page_crop.py` with the homography and quad on its `transform`; a flat page writes nothing. `tests/unit/media/test_square_page.py` (a 15° fixture squared within 0.5°). The 0.97 overlap with a hand-drawn box waits for the fixture files.
- `prep.square.corner-handles-correct-it` — **[PARTIAL]** (#5382) below the finder's confidence the quad is a proposal drawn as four dashed corner handles in Crop (`preview.edit.tool.crop-is-a-page-box`); dragging a corner and Return squares the page from the corrected quad with `who: person`. Built 2026-10-29: `POST /api/images/{id}/operations/square` takes a person's four corners and writes the row `who: person`; `PageCorners` and `PageCornerHandlesOverlay` draw four dashed handles over the found page (toolbar button on a page with a `page_region`), drag moves a corner, Return squares (`ImageEditDirectToolsTests.swift`, unrun). Not built: the handles follow the editor's own zoom (they are drawn on the unzoomed fit); the quad of a page the finder was unsure of is not stored yet (Step 3.2), so they show only where a `page_region` exists.
- `prep.flatten.curve-toward-the-gutter` — **[PARTIAL]** (#5382; owner 2026-10-29) a page whose text baselines curve or slant toward the gutter (fitted quadratic curvature over 0.5 % of the page height on the gutter side) is flattened by a displacement field from the baselines (connected-component lines, quadratic baselines, a thin-plate spline, `cv2.remap`) that makes every baseline horizontal and evens the stretch; a straight page, a blank page or a page with no lines writes nothing; the rendition's row carries the control points. On a synthetic page bent by a known curve the recovered baselines are within 2 px of straight. Built 2026-10-29: `media/flatten_curve.py` (connected-component lines, robust quadratic baselines, a smooth displacement field, `cv2.remap`); a `flattened` rendition with the control points on its row from `recipes/page_crop.py`; a bent synthetic page comes out within 2 px (11 px before), straight, blank and one-line pages write nothing (`tests/unit/media/test_flatten_curve.py`). Decided deviation (2026-10-29): linear interpolation between baselines then a blur, not a thin-plate spline, because scipy is not a declared engine dependency and a new heavy dependency needs the owner's word; the baselines come out straight within 2 px, which is what the test asks; a thin-plate spline is the upgrade if real bound volumes show the smooth field is not enough; no even-out of the stretch toward the gutter; whole page, not the gutter side.
- `prep.flatten.judged-by-the-gutter-third` — **[GAP]** (#5382) the bake-off reads the gutter third of the sample with and without the flatten and keeps the step only where its character error rate is no worse; the figures are on the run.

### Splitting, turning, straightening, blanks

- `prep.split-at-the-gutter` — **[PARTIAL]** (#5382) a two-page image is cut at its gutter or spiral, not at the middle, into pages in reading order; a single page is left whole. Built: `split_pages` (Vision outline, darkest column, aspect gate, proposal below 0.15; pinned on 11 Sergio photos, `tests/unit/media/test_page_split.py`). Missing: the neighbour test (darker than 180 and 15 darker than its neighbours), regions as children for several items on one sheet, the recipe calling it from the Start plan (#5390). `image.enhance.split-spread` defers to this line. Built 2026-10-29: the neighbour test in `find_gutter` (under 180 and 15 darker than the columns 60-140 px beside it, else a proposal), pinned in `tests/unit/media/test_page_split.py`. Still missing: regions as children for several items on one sheet, the Start plan calling it.
- `prep.turn-by-the-text` — **[PARTIAL]** (#5382) after cropping, a page is turned 0, 90, 180 or 270 degrees from its text: Vision text recognition at four turns on a reduced copy, the most words wins, skipped when the first try is confident; a lossless quarter turn recorded with its reason. EXIF alone is not enough (`prep.image.one-upright-frame` applies EXIF first). Built 2026-10-29: `media/turn_by_text.py`, a `rotated` rendition from `crop_pages(prepare=True)`. **Decided deviation (2026-10-29, builder, measured):** Apple Vision reads sideways and upside-down text as well as upright (the same 72 words at all four turns, measured), so a word count at four turns cannot decide; the turn is read from the order of the lines Vision returns (first line first: down the picture is upright, up is 180, left to right is 90, right to left is 270) in one read, no turn tried when fewer than three lines. Pinned with the real reader on a drawn page at all four turns (`tests/unit/media/test_turn_straighten_blank.py`). Not built: a page-less photograph of one line.
- `prep.straighten-and-flatten` — **[PARTIAL]** (#5382, #6190) small skew is corrected by Hough median with the angle recorded on the row and skipped under 0.3°. Built: `deskew_images`, the editor's Straighten. Missing: the angle on the row (today `angle: 0` means "auto"). Flattening a curved page is `prep.flatten.curve-toward-the-gutter`; squaring is `prep.square.perspective-from-the-quad`. `image.enhance.rotate-deskew` defers to this line. Built 2026-10-29: the `deskew_images` node writes the angle found on its row (method `hough`) and no row under 0.3 degrees; `auto_straighten_angle`; a `deskewed` rendition from `crop_pages(prepare=True)`. The editor's Straighten already stored its estimate. Flattening is `prep.flatten.curve-toward-the-gutter`.
- `prep.blank-pages-marked` — **[PARTIAL]** (#5382; owner 2026-10-29) a page whose ink pixels are under 0.2 % after the ruling mask is marked blank: imported and kept, dimmed, skipped by every later step (find regions, leave out, read, check), never deleted; a person can mark or unmark any page. The mark is a chain row (`prep.check.blank-mark-is-a-correction`); the skip is Leave Out's page-level reason `blank`, so the reading never sees it. Built 2026-10-29: `media/blank_page.py` (`ink_share` after a ruling mask, `is_blank`, `mark_blank`), a `mark_blank` chain row `who: run <id>`, `crop_pages(prepare=True)` marks and skips; a person's word is kept on a re-run. The skip is the existing exclusion (`Database._UNIT_OF_WORK_WHERE` now leaves excluded pages out of what a recipe runs), not a Leave Out reason `blank`. `tests/unit/media/test_turn_straighten_blank.py`, `tests/unit/api/test_blank_pages_hidden.py`.
- `prep.blank-pages-hidden-in-the-item-view` — **[PARTIAL]** (#5382, #1791; owner 2026-10-29) a blank page is hidden in the item view (the list and the grid) with `exclude_from_processing` set and the row kept, under a "N hidden" line that reveals them dimmed (`library.chrome.excluded-from-processing-treatment`); *Unhide* on one clears the mark, writes the correction row and queues the page through the steps it skipped; a leaf pairing (`finding-documents.md`) still counts a hidden verso. Engine built: `exclude_from_processing` set, row and file kept, `unhide` clears it and writes the person's row and returns the id to queue; `POST /api/images/{id}/operations/mark-blank` (`blank: false` unhides). Swift built 2026-10-29 (unrun): `HiddenPagesLine` ("N hidden" above the rows, reveals the pages dimmed, each with Unhide), the rows leave the hidden pages out (`BlankPagesHiddenTests.swift`). Not built: queueing the unhidden page through the steps it skipped (Step 3.1's plan), the leaf pairing counting a hidden verso (not checked).
- `prep.suppress-ruling` — **[GAP]** (#5382, #6195) ruled and graph-paper lines are removed and the ink kept, off until the bake-off shows it helps; the method is `image.enhance.ruled-lines`.
- `prep.image.one-upright-frame` — **[PARTIAL]** (#5382; Test 14, 2026-10-24; ## 1114) a phone photo carries its rotation as an EXIF Orientation tag, and a page is ONE frame wherever geometry meets its image: the thumbnail, Preview, the reader's line crops (cloud and local, TrOCR, the re-asks), the Inspector's and Reader's segment pictures, the check's and the tie's reads of given lines, a training set's page and lines, and the Kraken segmenter's geometry are all in the upright frame, the tag applied once (`media/upright.py`: `upright`, `upright_size`, `open_in_frame`). New geometry says so (`frame: "upright"`); geometry with no marker was measured on the raw pixels and every consumer reads it so. The marker is on the pass (`media/upright.pass_frame`), inherited by a person's split, create or merge; a region node says `frame` too (`media/region_crops`); the evaluation and the bake-off score on the chosen pass's frame. Built (unrun on a real photo): the helpers, the marker on results, boxes, segments and passes, the consumers above. Not done: a pass not made from a result (a format import, a hand-made pass) reads raw; the live check on a real phone photo. Tests: `tests/unit/llm/test_one_upright_frame_exif_test14.py`, `tests/unit/llm/test_exif_crops_are_upright_1114.py`.

### Check and correct

- `prep.unsure-becomes-a-proposal` — **[PARTIAL]** (#5382) an operation below its confidence proposes (a dashed page box, a dashed gutter, an arrow for a turn) and lists the page for review rather than changing it. Built: `split_pages` returns a proposal below 0.15. Missing: the proposal stored on the page, drawn in Preview, listed anywhere.
- `prep.check.worklist-of-proposals-and-a-sample` — **[GAP]** (#5382) after the run, "Pages to check: N" opens a Check-lens worklist of every page with a proposal plus one confident page in twenty, proposals first, each row saying in words what is unsure; the count is on the Set Up card and in Activity's summary.
- `prep.check.correction-replaces-the-runs-row` — **[GAP]** (#5382) accepting or adjusting a proposal, or changing an applied operation, writes a chain row `who: person` that replaces the run's row and keeps the run's values beside it; the rendition is re-made; the page leaves the worklist.
- `prep.check.apply-correction-to-the-folder` — **[GAP]** (#5382, #6192) a correction's parameters, in fractions of the frame, can be applied to the folder's other pages as one batch with whole-batch and per-page undo; the sheet previews three pages (first, middle, last) before it runs (`prep.cleanup.preview-three-samples-before-batch`, `prep.cleanup.batch-over-a-folder`, `prep.cleanup.per-page-undo` are this line's names in #6192 and resolve to it and to `image.enhance.batch-preview-undo`).
- `prep.check.blank-mark-is-a-correction` — **[PARTIAL]** (#5382) a person marks a page blank or not blank from the worklist or Preview; the mark is a chain row like any other and reading honours it at once. Engine built: marking blank or not blank is a `mark_blank` chain row with `who`, honoured at once by the work-unit filter. Not built: the worklist and Preview buttons (Steps 3.2 and Swift).

### Detectors: cards, training, adoption

- `prep.methods-are-cards-the-recipe-chooses` — **[GAP]** (#5382, #4951) each preparation job has its cards (Vision, contour, YOLO stock or trained, Kraken regions); the recipe names one per step, material kind and folder; onboarding picks the default by rule (built in, local, cheapest first); the bake-off replaces it only on evidence; a shared recipe carries its card choices.
- `prep.judged-by-reading` — **[GAP]** (#5382) each operation's effect on character error rate is measured in the bake-off on the same sample read with and without it; an operation that does not help is left out of the recipe.
- `prep.train.offered-after-thirty-corrections` — **[GAP]** (#5382, #5525; owner 2026-10-29) when a project holds 30 or more corrected or accepted page boxes, Set Up offers "Train a page finder from your corrections", once at 30 and again after every 30 more, with its time (local) or rate and time (Hugging Face) shown first; never started by itself; 29 corrections show no offer.
- `prep.train.runs-locally-or-on-hugging-face` — **[GAP]** (#5382, #5525, #5642; owner 2026-10-29, second ruling) the offer runs through the existing training places and no separate mechanism: this Mac as the regions fine-tune does (`training/yolo_local.py`, `POST /api/training/regions/here` with the page class), a Hugging Face job through the route Kraken training uses, or a cluster through Slurm (ACENET) through the Slurm training place and the lane's cluster targets (`../compute/training-and-evaluation.md`: `training.place.compared`, `training.place.slurm`, `training.place.cost-before-train`; `../compute/hpc-runner-acenet.md`); each place is a row with its time and cost, shown only when Set Up Fichero allows it (`source.onboard.places-cap-projects`) and refused in words otherwise; the Kraken segmenter trained from corrected lines offers the same rows (`source.segment.check-lines.corrections-train`). The id keeps its name; the cluster is in it.
- `prep.train.adopted-only-on-held-out-overlap` — **[GAP]** (#5382; owner 2026-10-29) the trained page card is scored against Vision and the contour finder on the held-out corrected pages (one in five, never trained on) by mean box overlap; the recipe adopts the best and says the figures; a trained card that does not beat the classical finder stays installed, unused, and the offer line says so.
- `prep.yolo-detectors-run-and-train` — **[GAP]** (#5382, #5525) a YOLO page and region detector runs locally and is trainable in Fichero from corrected outlines. Made concrete by the lines below.
- `prep.yolo.regions-card` — **[PARTIAL]** (#5525) **Built 2026-10-10:** `recipes/regions.py`, `llm/yolo_runtime.py`; pinned by `fichero-server/tests/unit/recipes/test_yolo_regions_card.py`. The `find-regions` job has a YOLO card: a layout model runs in the local model lane and writes a region pass (text block, heading, marginal note, page header, page footer, table, picture) with outline and confidence. The stock DocLayNet YOLO11 (`hantian/yolo-doclaynet`, AGPL like Fichero) is downloaded on request, never bundled; measured 2026-10-10 at 0.1 s a page warm, 6 s first load, and on two handwritten Sergio photos it saw one "Picture" at 26–28 %: a starting point for fine-tuning only. *Not yet: a trained model offered as a card by setup.*
- `prep.regions.open-default` — **[PARTIAL]** (#5668 walkthrough section 4) Find Regions' default is Kraken's built-in segmenter (`blla`, Apache-2.0, ships inside the app), kept to its regions; the YOLO DocLayNet model (AGPL-3.0) is a candidate with its licence sheet for pages that need its finer labels. Every page the project holds is found as every step finds it (`sources._resolve_abs_path`). Measured 2026-10-11: on a two-column printed page `blla` found 3 regions and 81 lines in 11 s on the MacBook Air. One pass, not two (#5689): the segmenter finds regions and lines together; Find Lines and Read use them (`fichero-server/tests/unit/recipes/test_regions_one_pass_5689.py`). Built: the bundled card, the rules, `recipes/regions.py` with `provider="kraken"`; pinned by `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py`. Not built: the Start plan still sends a `find-regions` step to YOLO only (`recipes/start.py`).
- `prep.regions.one-find-regions` — **[PARTIAL]** (#5962; owner ruling 2026-10-20: no two Find Regions implementations) finding regions is ONE function, `recipes.regions.find_regions`: the throttle's wait, Stop before each page, the page through the model lane, regions and lines kept together, the saved `regions` artifact; the recipe's step and the workflow node `detect_regions` (provider `kraken`) both call it. Built (unrun): the node calls it with the run's Stop and progress words; the node's Apple and vision-model providers stay in the node; a YOLO provider on the node is held (needs an OpenAPI-visible enum). Tests (unrun, M4): `fichero-server/tests/unit/workflows/test_detect_regions_one_path_5962.py`, `test_kraken_segmenter_node.py`.
- `prep.regions.one-implementation` — **[GAP]** (#5962) a guardrail test names `recipes.regions.find_regions` as the only Find Regions implementation; the recipe step and the node produce the same regions for the same page through it.
- `prep.yolo.fine-tune-from-corrected-regions` — **[PARTIAL]** (#5525, #5397) **Built 2026-10-10 (this Mac):** `training/yolo_set.py`, `training/yolo_local.py`, started by `POST /api/training/regions/here` (so the MCP tool and the CLI command); the trainer ran on the GPU (two epochs, 11 s); pinned by `fichero-server/tests/unit/training/test_yolo_regions_training.py`. Corrected regions become a YOLO label set (`formats/yolo.py`, the same set builder as Kraken's, #5513) and the stock model is fine-tuned on it, on this Mac or as a Hugging Face job; the result is a project card scored by region overlap on held-out pages. *Not yet: the Hugging Face path, the bake-off adopting it, a Train button in the app.*
- `prep.yolo.page-detector` — **[GAP]** (#5382, #6188) the same pipeline with one class, the page, finds and crops the page; its labels are the corrected page boxes; the old `yolov8s-fichero.pt` is the baseline to beat, not a dependency.
- `prep.yolo.quiet-in-the-sandbox` — **[PARTIAL]** (#5525) **Built 2026-10-10:** settings, datasets, weights and runs under the shared models folder, sync and loggers off (`yolo_runtime._quiet`). Ultralytics runs offline in the app; nothing is checked online. *Not yet checked in the sandboxed app.*
- `prep.licence.agpl-stated-on-the-card` — **[GAP]** (#5382) the YOLO cards' licence sheet says AGPL-3.0, that a model trained with it is AGPL too and can be shared with a recipe but not relicensed; the Vision and contour cards say they need no sheet. The sheet is the existing `licence-not-accepted` refusal (`recipes/assemble.py`).

### Renditions and the original

- `prep.never-changes-the-original` — **[OK]** every result is a new rendition in the edit chain (`preview.edit.chain-is-a-separate-row-never-the-source`; `fichero-server/tests/unit/workflows/test_image_prep_source_immutability.py`).
- `prep.prepared-image-attached-as-rendition` — **[OK]** (#5386) the recipe's prepared image is saved as a rendition of the page it prepared, as Split's parts become children, never only as a scratch file the library does not point at. Today JPEG stays JPEG (e62aa3bae) and run scratch is removed (70e882c81), so the result is lost: this contradicts `prep.never-changes-the-original`'s "every result is a rendition". The recipe's prepare step writes a `prepared` rendition inside the library, a JPEG staying a JPEG (PNG otherwise); the workflow node persists through `persist_workflow_renditions`. `tests/unit/workflows/test_prepare_images_rendition_recipe.py`.
- `prep.legacy-reviewed-before-rewrite` — **[OK]** (#5382) a written review compares the legacy tools and today's on the test set before any rewrite (fichero-projects `projects/sergio-notebooks/prep-review.md`, 11 Sergio photos, 2026-10-03; `agent-work/status/briefs/imgprep-review-2026-10-29.md`, this rewrite).
- `prep.enhance.clahe-ported` — **[PARTIAL]** (#6190) is `image.enhance.contrast-clahe`; the id is kept so the issue resolves. Built: `image_ops.apply_clahe_contrast` and the `contrast` operation with `clip`, `tile`, `gain`, `lift`, `profile` (a bare `factor` row is unchanged). Not built: the reference-sample 3/255 check (needs the legacy typed samples) and the editor sliders.

## Test matrix

Fixtures (`tests/fixtures/image_prep/`, to add; reduced to 1500 px on the long side): ten
Sergio notebook photographs with hand-drawn page boxes, gutter positions, blank flags and orientation;
Doc10 and Doc11 reduced with a hand-drawn page box; one photo rotated 90 and one 180 by its content with
EXIF 1; one page photographed at about 15° with its four hand-marked corners; a synthetic text page bent
by a known quadratic toward one edge; a blank graph-paper page; checked transcriptions of the Sergio text
pages for the CER comparison.

| Behaviour | Unit | Click-around | Notes |
| --- | --- | --- | --- |
| `prep.setup.three-questions-suggested-from-a-sample`, `prep.setup.what-runs-by-itself`, `prep.setup.step-runs-from-the-start-plan`, `prep.estimate.time-on-this-mac-before-start` | `tests/unit/recipes/test_prepare_step_setup.py` | needed (`PrepareImagesSetupUITests.swift`) | five sample pages → suggested answers; the plan holds the step; the time line names its basis. |
| `prep.find-the-page`, `prep.page.opencv-default-yolo-optional`, `prep.page.region-attribute-and-page-box` | `tests/unit/media/test_find_page.py` | not needed | outline within 2 % of the hand-drawn box on Doc11 and a Sergio photo; attribute and `page_box` written; YOLO card absent with no model. |
| `prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported` | `tests/unit/recipes/test_find_regions_inside_page.py` | not needed | no line outside the region; the summary's four numbers. |
| `prep.crop.content-bbox-is-fast`, `prep.page.remove-background-is-the-dark-mount-method` | `tests/unit/media/test_image_ops_legacy_port.py` | not needed | under 0.5 s; an old `remove_background` chain re-renders unchanged. |
| `prep.split-at-the-gutter` | `fichero-server/tests/unit/media/test_page_split.py` | not needed | the neighbour test added; 11 photos still pass. |
| `prep.square.perspective-from-the-quad`, `prep.square.corner-handles-correct-it` | `tests/unit/media/test_square_page.py`; `ImageEditDirectToolsTests.swift` | needed | the 15° fixture squared within 0.5°; a rectangular quad writes nothing; a dragged corner re-squares with `who: person`. |
| `prep.flatten.curve-toward-the-gutter`, `prep.flatten.judged-by-the-gutter-third` | `tests/unit/media/test_flatten_curve.py`, `tests/unit/recipes/test_prep_cards_bakeoff.py` | not needed | the bent synthetic page recovers straight baselines within 2 px; a straight page writes nothing; the gutter-third CER on the run. |
| `prep.turn-by-the-text`, `prep.straighten-and-flatten`, `prep.blank-pages-marked` | `tests/unit/media/test_turn_straighten_blank.py` | not needed | the 90 and 180 fixtures turned; the angle on the row; the blank page marked and skipped by find regions and read. |
| `prep.blank-pages-hidden-in-the-item-view` | `tests/unit/api/test_blank_pages_hidden.py`; `BlankPagesHiddenTests.swift` | needed | the blank row is hidden, revealed dimmed under "N hidden", unhidden with one click and queued. |
| `prep.unsure-becomes-a-proposal`, `prep.check.worklist-of-proposals-and-a-sample`, `prep.check.correction-replaces-the-runs-row`, `prep.check.blank-mark-is-a-correction` | `tests/unit/recipes/test_prepare_check_worklist.py` | needed (`PrepareImagesCheckUITests.swift`) | the proposal stored and listed; a correction replaces the row and leaves the worklist. |
| `prep.check.apply-correction-to-the-folder` | `tests/unit/api/test_image_batch_prepare.py`; `ImageBatchPrepareTests.swift` | needed | three previews write no row; batch id on every row; whole and per-page undo. |
| `prep.train.offered-after-thirty-corrections`, `prep.train.runs-locally-or-on-hugging-face`, `prep.train.adopted-only-on-held-out-overlap`, `prep.yolo.page-detector`, `prep.licence.agpl-stated-on-the-card` | `tests/unit/training/test_yolo_page_detector.py` | not needed | 29 corrections: no offer; 30: offered with a time; the local and Hugging Face places offered only when allowed; the trained card adopted only when its IoU is higher; the sheet's words. |
| `prep.methods-are-cards-the-recipe-chooses`, `prep.judged-by-reading` | `tests/unit/recipes/test_prep_cards_bakeoff.py` | not needed | the card per step and folder; CER with and without an operation. |
| `prep.prepared-image-attached-as-rendition` | `tests/unit/workflows/test_prepare_images_rendition_recipe.py` | needed | the prepared image is a rendition the viewer can switch to. |

## Build order

### Stage 1 — The page is found and kept

#### Step 1.1 — Find the page without a model; the attribute and the page box (#6188, #6198)
- Behaviours: `prep.page.opencv-default-yolo-optional`, `prep.page.region-attribute-and-page-box`, `prep.find-the-page`, `prep.crop.content-bbox-is-fast`, `prep.page.remove-background-is-the-dark-mount-method`
- Tests: fichero-server/tests/unit/media/test_find_page.py, fichero-server/tests/unit/media/test_image_ops_legacy_port.py
- Size: M

#### Step 1.2 — Lines only inside the page (#6189)
- Behaviours: `prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported`
- Tests: fichero-server/tests/unit/recipes/test_find_regions_inside_page.py
- Depends on: 1.1
- Size: S

#### Step 1.3 — The prepared image is a rendition (#5386)
- Behaviours: `prep.prepared-image-attached-as-rendition`, `prep.enhance.clahe-ported`
- Tests: fichero-server/tests/unit/workflows/test_prepare_images_rendition_recipe.py
- Depends on: 1.1
- Size: S

### Stage 2 — Square, flatten, split, turn, straighten, blanks

#### Step 2.1 — Square the page from the quad (#5382)
- Behaviours: `prep.square.perspective-from-the-quad`, `prep.square.corner-handles-correct-it`
- Tests: fichero-server/tests/unit/media/test_square_page.py, fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift
- Depends on: 1.1
- Size: M

#### Step 2.2 — Flatten the curve toward the gutter (#5382)
- Behaviours: `prep.flatten.curve-toward-the-gutter`, `prep.flatten.judged-by-the-gutter-third`
- Tests: fichero-server/tests/unit/media/test_flatten_curve.py, fichero-server/tests/unit/recipes/test_prep_cards_bakeoff.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — The gutter's neighbour test; turn by the text; the angle on the row (#5382, #6190)
- Behaviours: `prep.split-at-the-gutter`, `prep.turn-by-the-text`, `prep.straighten-and-flatten`, `prep.image.one-upright-frame`
- Tests: fichero-server/tests/unit/media/test_page_split.py, fichero-server/tests/unit/media/test_turn_straighten_blank.py
- Depends on: 2.1
- Size: M

#### Step 2.4 — Blank pages: marked, skipped, hidden, unhidden (#5382, #1791)
- Behaviours: `prep.blank-pages-marked`, `prep.blank-pages-hidden-in-the-item-view`, `prep.check.blank-mark-is-a-correction`
- Tests: fichero-server/tests/unit/media/test_turn_straighten_blank.py, fichero-server/tests/unit/api/test_blank_pages_hidden.py, fichero/Tests/Unit/general/Views/Preview/BlankPagesHiddenTests.swift
- Depends on: 2.3
- Size: M

### Stage 3 — The Set Up step runs

#### Step 3.1 — Three questions from a sample; what runs by itself; the plan holds the step; the time (#5580)
- Behaviours: `prep.setup.three-questions-suggested-from-a-sample`, `prep.setup.what-runs-by-itself`, `prep.setup.step-runs-from-the-start-plan`, `prep.estimate.time-on-this-mac-before-start`, `prep.setup.how-it-works-is-the-engines-sentence`
- Tests: fichero-server/tests/unit/recipes/test_prepare_step_setup.py, fichero/Tests/UI/general/PrepareImagesSetupUITests.swift
- Depends on: 2.4
- Size: M

#### Step 3.2 — Proposals, the worklist, corrections (#5382)
- Behaviours: `prep.unsure-becomes-a-proposal`, `prep.check.worklist-of-proposals-and-a-sample`, `prep.check.correction-replaces-the-runs-row`
- Tests: fichero-server/tests/unit/recipes/test_prepare_check_worklist.py, fichero/Tests/UI/general/PrepareImagesCheckUITests.swift
- Depends on: 3.1
- Size: M

#### Step 3.3 — A correction applied to the folder (#6192)
- Behaviours: `prep.check.apply-correction-to-the-folder`
- Tests: fichero-server/tests/unit/api/test_image_batch_prepare.py, fichero/Tests/Unit/general/Views/Preview/ImageBatchPrepareTests.swift
- Depends on: 3.2
- Size: M

### Stage 4 — Cards, training, evidence

#### Step 4.1 — The page detector trained from corrections, locally or on Hugging Face, adopted on evidence (#5525, #5382)
- Behaviours: `prep.train.offered-after-thirty-corrections`, `prep.train.runs-locally-or-on-hugging-face`, `prep.train.adopted-only-on-held-out-overlap`, `prep.yolo.page-detector`, `prep.licence.agpl-stated-on-the-card`
- Tests: fichero-server/tests/unit/training/test_yolo_page_detector.py
- Depends on: 3.2
- Size: M

#### Step 4.2 — Cards per step and folder; judged by reading (#4951, #5382)
- Behaviours: `prep.methods-are-cards-the-recipe-chooses`, `prep.judged-by-reading`, `prep.suppress-ruling`
- Tests: fichero-server/tests/unit/recipes/test_prep_cards_bakeoff.py
- Depends on: 4.1
- Size: M

#### Step 4.3 — Find Regions: one implementation, and the Start plan's default (#5962, #5668)
- Behaviours: `prep.regions.one-implementation`, `prep.regions.open-default`, `prep.regions.one-find-regions`
- Tests: fichero-server/tests/unit/workflows/test_detect_regions_one_path_5962.py, fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py
- Depends on: 4.1
- Size: S

#### Step 4.4 — The YOLO region cards: trained, offered, quiet (#5525)
- Behaviours: `prep.yolo.regions-card`, `prep.yolo.fine-tune-from-corrected-regions`, `prep.yolo.quiet-in-the-sandbox`, `prep.yolo-detectors-run-and-train`
- Tests: fichero-server/tests/unit/recipes/test_yolo_regions_card.py, fichero-server/tests/unit/training/test_yolo_regions_training.py
- Depends on: 4.3
- Size: M

## Rulings

- 2026-10-04 (design lead): train in PyTorch, run in Core AI when the conversion exists; built so far is PyTorch on the GPU (`llm/yolo_runtime.py`). Ruling suppression only where the bake-off shows it helps.
- 2026-10-09 (owner): Ultralytics YOLO is in, AGPL-3.0 as Fichero is.
- 2026-10-20 (owner): one Find Regions implementation.
- 2026-10-26 (owner): two steps, prep (pixels, renditions) and Leave Out (decisions); order prep → find regions and lines → leave out → read; the legacy methods and parameters come over, not the old app's shape.
- 2026-10-29 (owner, paraphrased): image preparation is a Set Up step that runs by itself with sensible defaults per collection and a check-and-correct flow; it crops to the page, leaves out the ruler, colour card and dark border, straightens, splits at the gutter and enhances into renditions; the detector may be classical, YOLO or trained from the person's corrections; good manual tools stand beside it.
- 2026-10-29, second round (owner, paraphrased; closes every open question of the morning draft):
  - **Perspective correction is in, now**, in two forms: a lopsided photograph squared from Vision's quad or the contour polygon, and a bound page whose lines curve into the gutter flattened. Both are renditions; the original is never touched (`prep.square.*`, `prep.flatten.*`).
  - **Blank pages are imported**, kept, dimmed and skipped by later steps; they are hidden in the item view and a person can unhide one (`prep.blank-pages-marked`, `prep.blank-pages-hidden-in-the-item-view`).
  - **Training the page finder is offered after 30 corrections**, runs locally, on Hugging Face or on a cluster through Slurm (ACENET) through the existing training places, and is adopted only when it beats the classical finder on held-out pages (`prep.train.*`). The same places serve the Kraken segmenter trained from corrected lines; no separate mechanism (`../compute/training-and-evaluation.md`).
  - **Checking for missed lines** is asked per project in Set Up with a suggested default, runs wherever a model can run, and must catch words dropped inside a line, not only marginalia (`segments-and-geometry.md`, `source.segment.check-lines.*`).
  - **The full OpenCV suite** comes over from the legacy tools, as automatic steps and as editor options with sliders and before/after (`image-enhancement.md`).
  - **Show-through** is one setting from the sample, per region only when the sample is uneven (`image.enhance.bleed-through-suppression`).
  - **Suggested answers** come from a five-page sample with a 3-of-5 rule (`prep.setup.three-questions-suggested-from-a-sample`).

## Open questions

None. The four questions of the morning draft (perspective, blanks, the training threshold, the sample size) were ruled on 2026-10-29 and are written above as decided.

## Future (ideas, not scheduled)
- (#4368) Native Apple image ops (book-spread split, border cleanup, bg removal) replacing OpenCV paths.
- A learned dewarp (DocTr, UVDoc) as a card beside the baseline-field flatten, if the bake-off shows the classical field is not enough on real bound volumes.
