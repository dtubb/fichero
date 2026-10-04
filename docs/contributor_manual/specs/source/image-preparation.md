# Source Model — Image preparation: from a photograph to pages a model can read — Design Spec (#5382)

> Milestone: source-model
> Manual: TBD — a section, "Preparing images", explaining what Fichero does to a photograph before
> reading it (find the page, split, turn, straighten, clean), that the original is never changed,
> and how to see whether a step helped.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-03). Stage 1 to 2 of
> `../../roadmap/research-pipeline.md`. Builds on the edit chain (`../ui/preview-image-editing.md`,
> mostly [OK]), the prepare tools in `workflows/tools/` (split, deskew, crop, binarize, denoise,
> enhance, remove background) and `media/image_ops.py`, and the `prepare-the-image` and
> `split-pages` jobs in the registry (`recipes/jobs.py`).

## Intent

Archives are photographed, not scanned: a book open on a table, two pages at once, a ruler and a
colour card beside it, the camera a little turned. Models read single, upright, flat, clean pages.
Image preparation turns the one into the other, **automatically, for a whole folder**, as the first
steps of a recipe; it keeps every result as a new version beside the original, and it is judged by
whether reading improves, not by how the picture looks.

The first test set is Sergio Mosquera's notebooks (`fichero-projects/projects/sergio-notebooks`):
374 photographs, 3000x2000, of open spiral notebooks on a dark table with a ruler along the top;
the left page is often blank graph paper and the right page carries the text in one hand.

## What exists today

- **The edit chain** (`preview.edit.*`): every edit is a separate, reversible row; crop and split
  are reversible; quarter turns are lossless; the editor compares original and edited.
- **Prepare tools**, each runnable on a folder: `split_images` (a **fixed grid**, equal columns),
  `rotate_images` (**EXIF or an explicit angle** only), `deskew_images` (`detect_deskew_angle`),
  `auto_crop_border_images` (`detect_content_bbox`), `remove_background_images`,
  `adaptive_binarize_images`, `denoise_images`, `enhance_images`, `fuzzy_clean_images`,
  `prepare_images` (a fixed sequence for OCR).
- **The legacy tools** (`fichero_archive/_archive/fichero_legacy/tools/`) did more and, by the
  maintainer's account, did it better: `split.py` (detects spiral notebooks, spreads, covers and
  labels; finds the split point from the binding's periodic pattern), `crop.py` (crops with a
  **YOLOv8 page model** (`fichero_resources/yolo_models/yolov8s-fichero.pt`, in the old
  `fichero_archive` tree, not in this repository), falling back to
  contours), `rotate.py` (Hough-line straightening), `segment.py` (deskew from text baselines, safe
  cut points). The move to today's tools kept the heuristics in `media/image_ops.py` and dropped
  the YOLO model; Apple Vision is used only to read text, not to find the page.
- **How they come over: reviewed, then rewritten better, never copied.** Before any code, a written
  review sets the legacy tools beside today's on the Sergio test set: what each does, where each
  fails, which ideas are worth keeping. The rewrite keeps those ideas in today's structure (the
  edit chain, the job registry, one code path) with tests, and must beat both on the test set.
- **Detectors to compare** for finding the page: the YOLOv8 page model (retrained on corrected
  outlines if it falls short), Apple Vision's document detection
  (`VNDetectDocumentSegmentationRequest`), and the classical contour method. For regions on the
  page: YOLO against Kraken's region segmenter (`blla`), which also gives baselines and reading
  order.
- **Missing:** finding the page on a busy background, splitting at the real gutter or spiral,
  turning by the text, knowing a page is blank, suppressing ruled or graph paper, flattening a
  curved page, and any measure of whether a step helped.

## The design

**One preparation step, made of operations in order,** each recorded in the page's edit chain
with its settings and reason, each skippable:

**The goal is automatic, proper cropping:** a photograph goes in and its **pages** come out (one,
or two for an open book, notebook or spread), or its **regions** where the thing photographed is
not a page sequence (several letters or cards on one sheet, a newspaper's articles, a map's
cartouche and legend). Each page also comes out **upright and straight**: turned the right way up from its text, and deskewed where it is tilted (the outline Vision finds already corrects perspective; a small residual tilt is measured from the lines). Each of these runs only when needed: a page already straight is left alone. No setting is needed for the common cases; a person only corrects.

1. **Find the page(s).** Locate the document in the photograph and crop away the table, ruler,
   colour card and hands. **Apple Vision first** (`VNDetectDocumentSegmentationRequest` for the
   document's outline, `VNDetectRectanglesRequest` for the pages inside it; Core Image for the
   perspective correction): built in, local, no training. Tried on two Sergio photographs
   (2026-10-03): the notebook found at 0.99 on both, the table and ruler excluded, and the left
   page returned as its own rectangle. The classical contour method and a YOLO page detector are
   fall-backs; the existing YOLOv8 model was trained on pages on black backgrounds, so it is
   retrained on corrected outlines before it is used on material like this. The page outline is
   kept as a geometry, so a reading can still be mapped back to the photograph.
2. **Split into pages or regions.** Decide whether the image holds one page, two, or several
   regions (Vision's page rectangles, the aspect ratio, a gutter or spiral found as a vertical band
   of dark or repeated shapes), and cut **at the gutter, not at the middle**. Pages come out in
   reading order (left then right for a left-to-right script; the cascade's direction decides);
   regions come out as child items of the photograph. The existing grid split stays for regular
   grids.
3. **Drop or mark blank pages.** A page with no ink beyond its ruling is marked **blank**: kept,
   shown dimmed, skipped by reading. Never deleted.
4. **Turn by the text.** Decide 0, 90, 180 or 270 degrees from the text itself (line direction and
   which way the letters stand: Apple Vision's orientation, or a reading attempted at each turn and
   the most confident kept), then a lossless quarter turn.
5. **Straighten and flatten.** Small-angle deskew from the lines (`detect_deskew_angle`). Then,
   where a page is curved, **flatten** it: a bound book photographed or scanned open curls toward
   its spine, so the lines nearest the gutter bend, crowd together and darken while the rest of the
   page is straight. Detected from the text lines' curvature (straight lines need nothing), and
   corrected by dewarping cards: a text-line model (fit the lines, then unwarp the page as a
   curved sheet, as Leptonica's dewarp and page-dewarp do), and learned unwarpers (DocTr, UVDoc)
   compared in the A/B. The gutter's shadow is evened out with the light. Measured like everything
   else: by whether the lines near the gutter read better.
6. **Clean.** Flatten the light, raise faded ink, and, where the paper is ruled or graph paper,
   **suppress the ruling** (thin, regular, coloured lines) without touching the ink. Binarize only
   for engines that want it; VLMs usually read better from the cleaned colour image.

**Automatic, with proposals where unsure.** Each operation reports a confidence; below a threshold
it proposes (a dashed outline, a suggested cut) and the page shows in the worklist instead of
being changed silently. A person's correction on one page can be applied to the rest of the folder
(the same notebook is photographed the same way).

**Judged by reading.** The bake-off (`source.recipe.*`) treats preparation like any other job: the
same sample of pages read with and without each operation, character error rate against checked
pages, and an operation stays in the recipe only where it helps. The renditions are shown side by
side for a person to look at too.

**Fichero is the harness; the recipe chooses.** Every operation above is a job in the registry
(`split-pages`, `prepare-the-image`, `find-regions`), and every way of doing it is a **card**:
Apple Vision, the contour method, a YOLO model (the stock one, or one trained on this project's
corrected outlines), Kraken's region segmenter. No method is hard-wired. The recipe names the
card per step, per material kind and per folder (a notebook folder and a map folder of the same
project can differ); onboarding picks the default by rule (local, built in, cheapest first), and
"Try Another Option…" runs the bake-off between cards on a sample, so a better card replaces the
default only on evidence. When no card is good enough on the sample, Fichero offers to **train** one (a YOLO detector from the pages a person has corrected, locally or on remote compute); the trained model becomes a new card, enters the same A/B, and the recipe can adopt it, and
a shared recipe carries its card choices with it.

**YOLO models must work.** A small page detector and a region detector (text block, marginal note,
heading, ruler, colour card) run locally (Core ML or PyTorch MPS), are trainable inside Fichero from
a few dozen corrected outlines (`train-a-model`), and appear as cards in the recipe.

## Behaviors

- `prep.legacy-reviewed-before-rewrite` — **[OK]** (#5382) a written review compares the legacy tools and today's on the test set before any rewrite; the rewrite beats both. The review: fichero-projects `projects/sergio-notebooks/prep-review.md` (11 Sergio photos, 2026-10-03).
- `prep.find-the-page` — **[PARTIAL]** (#5382) the page is found on a busy background and the photograph
  is cropped to it; the outline is kept as a geometry mapping back to the original. `split_pages` finds it with Apple Vision's document outline and crops to its box (`media/page_split.py`); the four-corner outline is reported but not yet stored as a geometry, and no perspective correction is applied.
- `prep.split-at-the-gutter` — **[PARTIAL]** (#5382) a photograph is cropped automatically into its pages or regions; a two-page image is cut at its gutter or spiral, not
  at the middle, into pages in reading order; a single page is left whole. `split_pages` cuts spreads at the darkest column of the outline's middle band, keeps an outline narrower than tall whole, and proposes rather than cuts below its confidence (pinned on 11 Sergio photos, `tests/unit/media/test_page_split.py`); regions, and the recipe calling it (#5390), are not built.
- `prep.blank-pages-marked` — **[GAP]** (#5382) a page with no ink beyond its ruling is marked blank,
  kept, and skipped by reading.
- `prep.turn-by-the-text` — **[GAP]** (#5382) automatically, after cropping, a page is turned by 0, 90, 180 or 270 degrees from its
  text, not only from EXIF.
- `prep.straighten-and-flatten` — **[PARTIAL]** (#5382) small skew is corrected from the lines
  (`deskew_images`); flattening a page curved toward the spine (lines bending near the gutter) is a gap.
- `prep.suppress-ruling` — **[GAP]** (#5382) ruled and graph-paper lines are removed and the ink kept.
- `prep.unsure-becomes-a-proposal` — **[GAP]** (#5382) an operation below its confidence proposes and
  lists the page for review rather than changing it; a correction can apply to the folder.
- `prep.judged-by-reading` — **[GAP]** (#5382) each operation's effect on character error rate is
  measured in the bake-off; an operation that does not help is left out of the recipe.
- `prep.never-changes-the-original` — **[OK]** every result is a new rendition in the edit chain
  (`preview.edit.chain-is-a-separate-row-never-the-source`).
- `prep.methods-are-cards-the-recipe-chooses` — **[GAP]** (#5382, #4951) each preparation job has several cards (Apple Vision, contour, YOLO stock or trained, Kraken regions); the recipe names one per step, material kind and folder; the bake-off replaces it only on evidence.
- `prep.yolo-detectors-run-and-train` — **[GAP]** (#5382) a YOLO page and region detector runs
  locally and is trainable in Fichero from corrected outlines.

## Test matrix

To be filled at approval. Fixtures: ten Sergio notebook photographs with hand-drawn page outlines,
gutter positions, blank flags and orientation; checked transcriptions of their text pages for the
CER comparison. Later: a bound volume (curved pages) and a damaged Istmina page.

## Open questions

1. **Blank pages:** kept and marked (recommended) or not imported at all?
2. **Ruling suppression before every engine, or only where the bake-off shows it helps?**
   Recommendation: only where it helps; some models use the ruling as a line guide.
3. **The YOLO runtime:** Core ML export (fast, on the Neural Engine) or PyTorch on MPS (one
   runtime for inference and training). Recommendation: train in PyTorch, run in Core ML.

## Future (ideas, not scheduled)
- (#4368) Native Apple image ops (book-spread split, border cleanup, bg removal) replacing OpenCV paths

## Triaged from the backlog (2026-10-04)
- `prep.prepared-image-attached-as-rendition` **[BROKEN]** (#5386): Prepare Images for OCR saves its result as a rendition of the page it prepared, as Split's parts become children, never only as a scratch file the library does not point at. (JPEG stays JPEG, e62aa3bae, and run scratch is removed, 70e882c81. Contradicts the [OK] `prep.never-changes-the-original`, which says every result is a rendition.)
