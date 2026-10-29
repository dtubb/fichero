# Source Model — Image preparation: the Set Up step that turns photographs into pages a model can read — Design Spec (#5382)

> Milestone: source-model
> Manual: TBD — a section, "Preparing images", explaining what Fichero does to a photograph before
> reading it (find the page, split, turn, straighten, clean), that the original is never changed,
> how to check and correct what it did, and how to see whether a step helped.
>
> Design-led (Testing Constitution). **Status: DRAFT — rewritten 2026-10-29 for approval** (first draft
> 2026-10-03; the owner's direction of 2026-10-29 paraphrased throughout). Review:
> `agent-work/status/briefs/imgprep-review-2026-10-29.md`. Stage 1 to 2 of `../../roadmap/research-pipeline.md`.
>
> **Three specs, one line between them.** This spec owns the **Set Up step**: the questions and their
> defaults, what runs by itself, finding the page, splitting, turning, blank pages, the check-and-correct
> flow, the detectors as cards, how corrections train a detector, and the time and cost shown before Start
> (`prep.*`). `image-enhancement.md` (#6185) owns the **pixel steps that write renditions** (contrast,
> stains, ruling, show-through, the working rendition, `image.enhance.*`) and the one function behind every
> door. `../ui/preview-image-editing.md` owns the **editor** a person corrects with (`preview.edit.*`,
> its tools in section C). Where two specs could say one thing, this spec cites the owner and does not
> restate it. The `prep.*` ids of 2026-10-03 are kept; the ids four issues cite but no spec carried
> (#6188, #6189, #6190, #6192) are added below with their tags.
>
> Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built · [BROKEN] built, wrong.

## Intent

Archives are photographed, not scanned: a book open on a table, two pages at once, a ruler and a colour
card beside the paper, a dark mount, the camera a little turned. Models read single, upright, flat, clean
pages. Image preparation turns the one into the other **by itself, for a whole collection**, as the first
step of a recipe, and a person **checks and corrects** it instead of doing it. Every result is a new
rendition beside the original, which is never changed. The step is judged by whether reading improves, not
by how the picture looks.

What the person sees: in Set Up, one card, "Prepare Images", with three short questions already answered
from a sample of their pages, and a line saying how long the step takes on this Mac. After Start, a short
list of pages to check: the ones Fichero was unsure about, and a few it was sure about, so the person sees
both. Each opens in Preview with the page box, the cut and the turn drawn on the photograph, ready to be
dragged. A correction on one page can be applied to the rest of its folder. Enough corrections, and Fichero
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
last) before the person reads them. Each answer is stored per folder: a notebook folder and a map folder of
the same project can differ.

| Question | Choices | Suggested when | Default without a sample |
| --- | --- | --- | --- |
| Two pages in one picture? | yes / no | the sample's outlines are wider than tall on 3 of 5 | no |
| Anything beside the page? | ruler · colour card · dark mount or table · nothing | the outline covers under 85 % of the frame on 3 of 5 (the first three are one answer: "find the page"; the ruler and card choices add Leave Out's reasons) | nothing |
| The paper | ruled or graph paper · stained or faded · writing shows through | `recipes/prepare.sample_shows_faded`; a hue mask finds thin regular coloured lines on 3 of 5; a mirrored faint copy of the previous page on 3 of 5 | none |

Below the questions, one line: *Finds each page, turns it upright and straightens it; cuts spreads into
pages; marks blank pages. About 2 min for 374 pages on this Mac. Nothing leaves this Mac.* The time comes
from `prep.estimate.*` below; the sentence is the engine's (`how_it_works`), never the app's.

**What runs by itself, whatever the answers:** find the page and crop to it (a no-op when the page fills
the frame), turn upright by the text, straighten (skipped under 0.3°), mark blank pages. **What the
answers switch on:** split (two pages), contrast (faded), ruling, show-through
(`image-enhancement.md`). A step that finds nothing to do writes nothing.

### The operations, in order

1. **Find the page.** Apple Vision's document outline first; the contour finder (the legacy templates,
   auto-chosen by the border's mean brightness) where Vision answers nothing or under 0.5; the YOLO page
   card where one is installed and the recipe names it. The result is a `page_region` Shape on the image
   (quad, box, method, confidence; `segments-and-geometry.md`) **and** the document's `page_box` metadata
   in fractions, which Leave Out and Find Regions read. The crop is a rendition; the outline maps every
   later shape back to the photograph. Perspective correction from the quad is a later step (open
   question 1).
2. **Split at the gutter.** An outline wider than tall is a spread; the gutter is the darkest column of
   the middle band, kept only when darker than 180 and 15 darker than its neighbours (the legacy test);
   pages come out in the cascade's reading order as child items. Below the confidence the cut is a
   proposal.
3. **Turn by the text.** Vision text recognition on a reduced copy at 0, 90, 180 and 270; the orientation
   with the most recognised words wins; skipped when the first try already recognises most of them. A
   lossless quarter turn, recorded with its reason.
4. **Straighten.** Hough median, the angle on the row, skipped under 0.3°. Flattening a page curved toward
   the spine stays a gap (`prep.straighten-and-flatten`).
5. **Mark blank pages.** A page with no ink beyond its ruling (ink pixels under 0.2 % after the ruling
   mask) is marked blank: kept, dimmed, skipped by reading, never deleted.
6. **Enhance** where asked: `image-enhancement.md`'s contrast, stains, ruling, show-through, each a
   rendition.

Each operation reports a **confidence** and a **reason**; below its threshold it **proposes** instead of
changing: a dashed page box, a dashed gutter line, a turn shown as an arrow. Every applied operation is a
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
correction too. The tools themselves are `preview.edit.tool.*`.

### Corrections train a detector

Corrected page boxes are labels. When a project holds **30 or more** corrected or accepted pages, Set Up
offers *Train a page finder from your corrections*: a one-class YOLO fine-tune (`training/yolo_set.py`,
`training/yolo_local.py`, the same pipeline as regions, #5525) on this Mac's GPU or as a Hugging Face job,
the cost and time shown first. The result is a project card. It replaces the default **only on evidence**:
the bake-off scores every page-finding card on the held-out corrected pages by box overlap (mean IoU) and
the recipe adopts the best. Marked ruler and colour-card regions are labels for the layout detector in the
same way (`prep.yolo.fine-tune-from-corrected-regions`).

### Methods are cards, chosen by rule, replaced by evidence

| Job | Cards | Default | Licence |
| --- | --- | --- | --- |
| find the page | Apple Vision outline · contour finder · YOLO page detector (trained) | Vision, then contour | Vision: the OS · OpenCV: Apache-2.0 · Ultralytics: AGPL-3.0 |
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

- `prep.setup.three-questions-suggested-from-a-sample` — **[GAP]** (#5580) the Prepare Images card asks the three questions above with answers suggested from five sample pages (outline aspect, outline coverage, `sample_shows_faded`, a ruling mask, a mirrored-verso match), each answer stored per folder; the person changes any. Today `recipes/stages.py` asks two questions with fixed defaults.
- `prep.setup.what-runs-by-itself` — **[GAP]** (#5580) find the page, turn, straighten and mark blanks run on every page whatever the answers; split, contrast, ruling and show-through run only when their answer says so; a step with nothing to do writes no row. Today the answers are stored and only `split-pages` runs (`recipes/start.py`).
- `prep.setup.step-runs-from-the-start-plan` — **[GAP]** (#5580) the Start plan holds a runnable `prepare-the-image` entry naming the operations and their cards, before `find-regions`; its progress line says "Preparing images: 23 of 374 pages, about 2 min left" (`image.enhance.onboarding-step` is this line's twin in the enhancement spec and is retired in favour of it).
- `prep.estimate.time-on-this-mac-before-start` — **[GAP]** (#5580) the Start sheet shows the step's time as the per-page seconds measured on this machine's last run of each card times the page count, or the card's seed figure marked "estimate", and says the step costs nothing and leaves nothing this Mac; a training offer shows its minutes locally or its rate and minutes on Hugging Face.
- `prep.setup.how-it-works-is-the-engines-sentence` — **[PARTIAL]** (#5791) the one-line description under the questions is the job's topic text from the engine (`how_it_works`, `recipes/seed/topics.yaml`), never written in the app. Built: the mechanism. Missing: a topic for `prepare-the-image` that names the operations.

### Finding the page

- `prep.find-the-page` — **[PARTIAL]** (#5382, #6188) the page is found on a busy background and the photograph is cropped to it; the outline is kept as a geometry mapping back to the original. Built: `split_pages` finds it with Vision's outline and crops to its box (`media/page_split.py`). Missing: the quad stored, the attribute, the contour fallback, the crop as a rendition of the page.
- `prep.page.opencv-default-yolo-optional` — **[GAP]** (#6188) `media/find_page.py` tries Vision's outline, then the contour finder (templates auto-chosen by border brightness: dark mount → `dark_background`, light table → `light_background`; largest external contour with area 0.15–0.99 of the frame and aspect 0.5–2.0; pad 30 px), then the YOLO page card only when its model is installed; it returns outline, method and confidence and never alters the original. On EAP1477_GHC_B12_Doc11_IMG_004 and a Sergio photo with no model installed the outline is within 2 % of the hand-drawn box.
- `prep.page.region-attribute-and-page-box` — **[GAP]** (#6187, #6198) finding the page writes a `page_region` Shape (quad, box, method, confidence, `frame: "upright"`) on the image and the document's `page_box` metadata in fractions, the same numbers Leave Out reads (`image.enhance.page-crop-writes-page-box` is this line's twin and defers to it).
- `prep.page.detected-before-lines` — **[GAP]** (#6189) when a page has a `page_region`, `recipes.regions.find_regions` gives the segmenter only that crop and maps every region and line back to the page image's frame; a fixture with a ruler strip and a dark border yields no line outside the region.
- `prep.page.kraken-time-saved-is-reported` — **[GAP]** (#6189) the run summary says per page the seconds with and without the region and the lines inside and outside it, on the Doc10 and Doc11 fixtures.
- `prep.crop.content-bbox-is-fast` — **[GAP]** (#6190) `detect_content_bbox` is a NumPy reduction, under 0.5 s on a 3000×2000 image, with the same answer as today on the fixtures.
- `prep.page.remove-background-is-the-dark-mount-method` — **[GAP]** (#6188) the editor's Remove Background and the `remove_background_images` node become the contour finder's dark-mount method inside find-the-page; the old operation name survives only so an existing chain re-renders unchanged.

### Splitting, turning, straightening, blanks

- `prep.split-at-the-gutter` — **[PARTIAL]** (#5382) a two-page image is cut at its gutter or spiral, not at the middle, into pages in reading order; a single page is left whole. Built: `split_pages` (Vision outline, darkest column, aspect gate, proposal below 0.15; pinned on 11 Sergio photos, `tests/unit/media/test_page_split.py`). Missing: the neighbour test (darker than 180 and 15 darker than its neighbours), regions as children for several items on one sheet, the recipe calling it from the Start plan (#5390). `image.enhance.split-spread` defers to this line.
- `prep.turn-by-the-text` — **[GAP]** (#5382) after cropping, a page is turned 0, 90, 180 or 270 degrees from its text: Vision text recognition at four turns on a reduced copy, the most words wins, skipped when the first try is confident; a lossless quarter turn recorded with its reason. EXIF alone is not enough (`prep.image.one-upright-frame` applies EXIF first).
- `prep.straighten-and-flatten` — **[PARTIAL]** (#5382, #6190) small skew is corrected by Hough median with the angle recorded on the row and skipped under 0.3°. Built: `deskew_images`, the editor's Straighten. Missing: the angle on the row (today `angle: 0` means "auto"); flattening a page curved toward the spine is a gap and stays one. `image.enhance.rotate-deskew` defers to this line.
- `prep.blank-pages-marked` — **[GAP]** (#5382) a page whose ink pixels are under 0.2 % after the ruling mask is marked blank: kept, dimmed, skipped by reading, never deleted; a person can mark or unmark any page. Open question 2 asks whether to import blanks at all.
- `prep.suppress-ruling` — **[GAP]** (#5382, #6195) ruled and graph-paper lines are removed and the ink kept, off until the bake-off shows it helps; the method is `image.enhance.ruled-lines`.
- `prep.image.one-upright-frame` — **[PARTIAL]** (#5382; Test 14, 2026-10-24; ## 1114) a phone photo carries its rotation as an EXIF Orientation tag, and a page is ONE frame wherever geometry meets its image: the thumbnail, Preview, the reader's line crops (cloud and local, TrOCR, the re-asks), the Inspector's and Reader's segment pictures, the check's and the tie's reads of given lines, a training set's page and lines, and the Kraken segmenter's geometry are all in the upright frame, the tag applied once (`media/upright.py`: `upright`, `upright_size`, `open_in_frame`). New geometry says so (`frame: "upright"`); geometry with no marker was measured on the raw pixels and every consumer reads it so. The marker is on the pass (`media/upright.pass_frame`), inherited by a person's split, create or merge; a region node says `frame` too (`media/region_crops`); the evaluation and the bake-off score on the chosen pass's frame. Built (unrun on a real photo): the helpers, the marker on results, boxes, segments and passes, the consumers above. Not done: a pass not made from a result (a format import, a hand-made pass) reads raw; the live check on a real phone photo. Tests: `tests/unit/llm/test_one_upright_frame_exif_test14.py`, `tests/unit/llm/test_exif_crops_are_upright_1114.py`.

### Check and correct

- `prep.unsure-becomes-a-proposal` — **[PARTIAL]** (#5382) an operation below its confidence proposes (a dashed page box, a dashed gutter, an arrow for a turn) and lists the page for review rather than changing it. Built: `split_pages` returns a proposal below 0.15. Missing: the proposal stored on the page, drawn in Preview, listed anywhere.
- `prep.check.worklist-of-proposals-and-a-sample` — **[GAP]** (#5382) after the run, "Pages to check: N" opens a Check-lens worklist of every page with a proposal plus one confident page in twenty, proposals first, each row saying in words what is unsure; the count is on the Set Up card and in Activity's summary.
- `prep.check.correction-replaces-the-runs-row` — **[GAP]** (#5382) accepting or adjusting a proposal, or changing an applied operation, writes a chain row `who: person` that replaces the run's row and keeps the run's values beside it; the rendition is re-made; the page leaves the worklist.
- `prep.check.apply-correction-to-the-folder` — **[GAP]** (#5382, #6192) a correction's parameters, in fractions of the frame, can be applied to the folder's other pages as one batch with whole-batch and per-page undo; the sheet previews three pages (first, middle, last) before it runs (`prep.cleanup.preview-three-samples-before-batch`, `prep.cleanup.batch-over-a-folder`, `prep.cleanup.per-page-undo` are this line's names in #6192 and resolve to it and to `image.enhance.batch-preview-undo`).
- `prep.check.blank-mark-is-a-correction` — **[GAP]** (#5382) a person marks a page blank or not blank from the worklist or Preview; the mark is a chain row like any other and reading honours it at once.

### Detectors: cards, training, adoption

- `prep.methods-are-cards-the-recipe-chooses` — **[GAP]** (#5382, #4951) each preparation job has its cards (Vision, contour, YOLO stock or trained, Kraken regions); the recipe names one per step, material kind and folder; onboarding picks the default by rule (built in, local, cheapest first); the bake-off replaces it only on evidence; a shared recipe carries its card choices.
- `prep.judged-by-reading` — **[GAP]** (#5382) each operation's effect on character error rate is measured in the bake-off on the same sample read with and without it; an operation that does not help is left out of the recipe.
- `prep.train.offered-after-thirty-corrections` — **[GAP]** (#5382, #5525) when a project holds 30 or more corrected or accepted page boxes, Set Up offers "Train a page finder from your corrections", with its time (local) or rate and time (Hugging Face) shown first; never started by itself.
- `prep.train.adopted-only-on-held-out-overlap` — **[GAP]** (#5382) the trained page card is scored against Vision and the contour finder on held-out corrected pages by mean box overlap; the recipe adopts the best and says the figures; a worse model stays available, unused.
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
- `prep.prepared-image-attached-as-rendition` — **[BROKEN]** (#5386) the recipe's prepared image is saved as a rendition of the page it prepared, as Split's parts become children, never only as a scratch file the library does not point at. Today JPEG stays JPEG (e62aa3bae) and run scratch is removed (70e882c81), so the result is lost: this contradicts `prep.never-changes-the-original`'s "every result is a rendition".
- `prep.legacy-reviewed-before-rewrite` — **[OK]** (#5382) a written review compares the legacy tools and today's on the test set before any rewrite (fichero-projects `projects/sergio-notebooks/prep-review.md`, 11 Sergio photos, 2026-10-03; `agent-work/status/briefs/imgprep-review-2026-10-29.md`, this rewrite).
- `prep.enhance.clahe-ported` — **[GAP]** (#6190) is `image.enhance.contrast-clahe`; the id is kept so the issue resolves.

## Test matrix

Fixtures (`tests/fixtures/image_prep/`, to add; reduced to 1500 px on the long side): ten
Sergio notebook photographs with hand-drawn page boxes, gutter positions, blank flags and orientation;
Doc10 and Doc11 reduced with a hand-drawn page box; one photo rotated 90 and one 180 by its content with
EXIF 1; a blank graph-paper page; checked transcriptions of the Sergio text pages for the CER comparison.

| Behaviour | Unit | Click-around | Notes |
| --- | --- | --- | --- |
| `prep.setup.three-questions-suggested-from-a-sample`, `prep.setup.what-runs-by-itself`, `prep.setup.step-runs-from-the-start-plan`, `prep.estimate.time-on-this-mac-before-start` | `tests/unit/recipes/test_prepare_step_setup.py` | needed (`PrepareImagesSetupUITests.swift`) | five sample pages → suggested answers; the plan holds the step; the time line names its basis. |
| `prep.find-the-page`, `prep.page.opencv-default-yolo-optional`, `prep.page.region-attribute-and-page-box` | `tests/unit/media/test_find_page.py` | not needed | outline within 2 % of the hand-drawn box on Doc11 and a Sergio photo; attribute and `page_box` written; YOLO card absent with no model. |
| `prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported` | `tests/unit/recipes/test_find_regions_inside_page.py` | not needed | no line outside the region; the summary's four numbers. |
| `prep.crop.content-bbox-is-fast`, `prep.page.remove-background-is-the-dark-mount-method` | `tests/unit/media/test_image_ops_legacy_port.py` | not needed | under 0.5 s; an old `remove_background` chain re-renders unchanged. |
| `prep.split-at-the-gutter` | `fichero-server/tests/unit/media/test_page_split.py` | not needed | the neighbour test added; 11 photos still pass. |
| `prep.turn-by-the-text`, `prep.straighten-and-flatten`, `prep.blank-pages-marked` | `tests/unit/media/test_turn_straighten_blank.py` | not needed | the 90 and 180 fixtures turned; the angle on the row; the blank page marked and skipped. |
| `prep.unsure-becomes-a-proposal`, `prep.check.worklist-of-proposals-and-a-sample`, `prep.check.correction-replaces-the-runs-row`, `prep.check.blank-mark-is-a-correction` | `tests/unit/recipes/test_prepare_check_worklist.py` | needed (`PrepareImagesCheckUITests.swift`) | the proposal stored and listed; a correction replaces the row and leaves the worklist. |
| `prep.check.apply-correction-to-the-folder` | `tests/unit/api/test_image_batch_prepare.py`; `ImageBatchPrepareTests.swift` | needed | three previews write no row; batch id on every row; whole and per-page undo. |
| `prep.train.offered-after-thirty-corrections`, `prep.train.adopted-only-on-held-out-overlap`, `prep.yolo.page-detector`, `prep.licence.agpl-stated-on-the-card` | `tests/unit/training/test_yolo_page_detector.py` | not needed | 29 corrections: no offer; 30: offered with a time; the trained card adopted only when its IoU is higher; the sheet's words. |
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

### Stage 2 — Split, turn, straighten, blanks

#### Step 2.1 — The gutter's neighbour test; turn by the text; the angle on the row; blank pages (#5382, #6190)
- Behaviours: `prep.split-at-the-gutter`, `prep.turn-by-the-text`, `prep.straighten-and-flatten`, `prep.blank-pages-marked`, `prep.image.one-upright-frame`
- Tests: fichero-server/tests/unit/media/test_page_split.py, fichero-server/tests/unit/media/test_turn_straighten_blank.py
- Depends on: 1.1
- Size: M

### Stage 3 — The Set Up step runs

#### Step 3.1 — Three questions from a sample; what runs by itself; the plan holds the step; the time (#5580)
- Behaviours: `prep.setup.three-questions-suggested-from-a-sample`, `prep.setup.what-runs-by-itself`, `prep.setup.step-runs-from-the-start-plan`, `prep.estimate.time-on-this-mac-before-start`, `prep.setup.how-it-works-is-the-engines-sentence`
- Tests: fichero-server/tests/unit/recipes/test_prepare_step_setup.py, fichero/Tests/UI/general/PrepareImagesSetupUITests.swift
- Depends on: 2.1
- Size: M

#### Step 3.2 — Proposals, the worklist, corrections (#5382)
- Behaviours: `prep.unsure-becomes-a-proposal`, `prep.check.worklist-of-proposals-and-a-sample`, `prep.check.correction-replaces-the-runs-row`, `prep.check.blank-mark-is-a-correction`
- Tests: fichero-server/tests/unit/recipes/test_prepare_check_worklist.py, fichero/Tests/UI/general/PrepareImagesCheckUITests.swift
- Depends on: 3.1
- Size: M

#### Step 3.3 — A correction applied to the folder (#6192)
- Behaviours: `prep.check.apply-correction-to-the-folder`
- Tests: fichero-server/tests/unit/api/test_image_batch_prepare.py, fichero/Tests/Unit/general/Views/Preview/ImageBatchPrepareTests.swift
- Depends on: 3.2
- Size: M

### Stage 4 — Cards, training, evidence

#### Step 4.1 — The page detector trained from corrections, adopted on evidence (#5525, #5382)
- Behaviours: `prep.train.offered-after-thirty-corrections`, `prep.train.adopted-only-on-held-out-overlap`, `prep.yolo.page-detector`, `prep.licence.agpl-stated-on-the-card`
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

## Open questions

1. **Perspective correction from the quad.** Vision gives four corners; a warp makes a flatter page but a
   new frame every later shape must map through. Recommended: not in this spec; the box crop first, the
   warp as a later rendition step once the frame marker (`prep.image.one-upright-frame`) has run on real
   photos.
2. **Blank pages: imported and marked, or not imported?** Recommended: imported and marked (kept, dimmed,
   skipped by reading), so a verso that only looks blank can be brought back and the leaf pairing of
   `finding-documents.md` still holds.
3. **How many corrections before Fichero offers to train?** Recommended: 30 corrected or accepted page
   boxes; below that the offer is noise, above it a one-class fine-tune has been enough on the regions
   pipeline.
4. **The sample size for suggested answers.** Recommended: five pages (first, quarter, middle, three
   quarters, last) and a 3-of-5 rule; a larger sample delays Set Up for little.

## Future (ideas, not scheduled)
- (#4368) Native Apple image ops (book-spread split, border cleanup, bg removal) replacing OpenCV paths.
- Dewarping a curved page (Leptonica-style text-line model, DocTr, UVDoc), measured by whether lines near the gutter read better.
