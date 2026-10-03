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
- **Missing:** finding the page on a busy background, splitting at the real gutter or spiral,
  turning by the text, knowing a page is blank, suppressing ruled or graph paper, flattening a
  curved page, and any measure of whether a step helped.

## The design

**One preparation step, made of operations in order,** each recorded in the page's edit chain
with its settings and reason, each skippable:

1. **Find the page(s).** Locate the document in the photograph and crop away the table, ruler,
   colour card and hands. Classical first (edges and the largest light quadrilateral); a YOLO page
   detector (one class: page) where that fails. The page outline is kept as a geometry, so a
   reading can still be mapped back to the photograph.
2. **Split spreads.** Decide whether the image holds one page or two (aspect ratio, a gutter or
   spiral found as a vertical band of dark or repeated shapes), and cut **at the gutter, not at the
   middle**. Pages come out in reading order (left then right for a left-to-right script; the
   cascade's direction decides). The existing grid split stays for regular grids.
3. **Drop or mark blank pages.** A page with no ink beyond its ruling is marked **blank**: kept,
   shown dimmed, skipped by reading. Never deleted.
4. **Turn by the text.** Decide 0, 90, 180 or 270 degrees from the text itself (line direction and
   which way the letters stand: Apple Vision's orientation, or a reading attempted at each turn and
   the most confident kept), then a lossless quarter turn.
5. **Straighten.** Small-angle deskew from the lines (`detect_deskew_angle`), then, optionally,
   **flatten** a curved page (dewarp from the text lines' curvature).
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

**YOLO models must work.** A small page detector and a region detector (text block, marginal note,
heading, ruler, colour card) run locally (Core ML or PyTorch MPS), are trainable inside Fichero from
a few dozen corrected outlines (`train-a-model`), and appear as cards in the recipe.

## Behaviors

- `prep.find-the-page` — **[GAP]** (#5382) the page is found on a busy background and the photograph
  is cropped to it; the outline is kept as a geometry mapping back to the original.
- `prep.split-at-the-gutter` — **[GAP]** (#5382) a two-page image is cut at its gutter or spiral, not
  at the middle, into pages in reading order; a single page is left whole.
- `prep.blank-pages-marked` — **[GAP]** (#5382) a page with no ink beyond its ruling is marked blank,
  kept, and skipped by reading.
- `prep.turn-by-the-text` — **[GAP]** (#5382) a page is turned by 0, 90, 180 or 270 degrees from its
  text, not only from EXIF.
- `prep.straighten-and-flatten` — **[PARTIAL]** (#5382) small skew is corrected from the lines
  (`deskew_images`); flattening a curved page is a gap.
- `prep.suppress-ruling` — **[GAP]** (#5382) ruled and graph-paper lines are removed and the ink kept.
- `prep.unsure-becomes-a-proposal` — **[GAP]** (#5382) an operation below its confidence proposes and
  lists the page for review rather than changing it; a correction can apply to the folder.
- `prep.judged-by-reading` — **[GAP]** (#5382) each operation's effect on character error rate is
  measured in the bake-off; an operation that does not help is left out of the recipe.
- `prep.never-changes-the-original` — **[OK]** every result is a new rendition in the edit chain
  (`preview.edit.chain-is-a-separate-row-never-the-source`).
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
