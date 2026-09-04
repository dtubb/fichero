# Kraken segmenter evaluation (queued run — Daniel, 2026-09-04)

**RATIFIED 2026-09-04 evening**: Daniel approved the direction before the
experiment ran — Kraken ships as an OPTIONAL INSTALL like MLX (Install
Tools window), and the SEGMENTER is the prize (line geometry, not
recognition). The evaluation below is still the gate on quality: overlay
evidence first, wiring second.

Daniel asked whether Kraken can supply automatic bounding boxes for OCR
("it's not always very good, but might be okay? it'd be great to have
bounding boxes automatically").

## Framing

The geometry gap: Apple Vision gives boxes but misreads colonial hands;
VLMs read well but return no geometry. Kraken's neural **segmenter**
(the eScriptorium engine, Apache-2.0, local/free) produces baselines +
line polygons without reading — the missing third piece. Recognition
quality is a separate question and NOT what we are evaluating first.

Fits ratified NLP ruling #1 (2026-09-04): free layers run automatically
at import as a draft the VLM refines. Distribution would be an optional
runtime install (Install Tools window, like MLX), never bundled.

**Sizing corrected 2026-09-04, from PyPI metadata (no download).** The
"PyTorch ~2GB" this was ratified on is a CUDA/Linux figure and does not
apply here: the macOS arm64 wheel for torch 2.14.0 is **127 MB**. kraken
7.1.1 also pulls torchvision, torchmetrics, lightning, coremltools,
scikit-image, scikit-learn, scipy, pyarrow and shapely, so the estimate
to beat is **~600-800 MB downloaded, ~1.5-2.5 GB installed** — measured
for real in step 1 below and reported as actual-vs-estimate. Kraken is
therefore a materially cheaper optional install than the decision
assumed. One constraint for the runtime provisioner: kraken 7.1.1
requires Python **>=3.10 and <3.14**, so the venv interpreter is pinned
by that ceiling.

## The experiment

1. Scratch venv: `pip install kraken` (pin torch CPU wheel; no MPS
   assumptions). Record install size + import time, actual vs the
   estimate above.
2. Segment (blla default model) three pages: Caciques 533r + two
   Marshall diary pages. Record wall time per page (CPU).

   Pages come from `agent-work/bbox-lab/samples/` (2026-09-04): six real
   Marshall diary pages at full resolution, committed, and already the
   corpus the bbox lab measured Apple Vision on — so the overlays are
   directly comparable to numbers we already hold. Those numbers are
   themselves the case for this experiment: on 1913_p05 Vision returned
   403 "lines" for 966 words, and on 1923_p03_part1, 163 lines for 174
   words. Roughly one "line" per word is the fragmentation Kraken's
   segmenter is meant to replace.
3. Render overlays: line polygons + baselines drawn on the page image,
   side by side with Apple Vision's word boxes on the same pages.
   Output PNGs into agent-work/experiments/kraken/ for Daniel to eyeball.

   Harness (2026-09-04, `agent-work/experiments/kraken/`): two stages,
   because the two halves cannot share an interpreter.
   `kraken_segment.py` runs under the scratch venv and imports only
   kraken; `overlay_report.py` runs under the engine venv and calls
   `apple_vision_ocr_with_geometry`, the product's own path, so the
   comparison is against what Fichero shows users today. They meet
   through JSON in which every record NAMES ITS PIXEL FRAME — Kraken's
   coordinates are absolute pixels of one exact image, and per the bbox
   program a box that does not name its frame is a box nobody can place.
   Geometry is drawn at full resolution and only the composed sheet is
   thumbnailed; coordinates are never scaled.
4. Count: lines found vs lines a human sees; gross failures (merged
   lines, phantom regions, margins swallowed).
5. ONLY IF segmentation looks good: note (do not build) the alignment
   path — VLM transcription force-aligned to Kraken lines per the
   90e4bda24 program, and optionally a pretrained Spanish model from
   HTR United/Zenodo for a recognition taste test.

## Constraints

- Scratch venv + scratch copies of images; never against a real library.
- CPU only; serial with other heavy jobs (machine rule).
- No model downloads beyond kraken's default segmenter + at most one
  pretrained recognition model; log sizes first.
- Deliverable: overlay PNGs + a one-page verdict table (per page: lines
  found/expected, time, failure notes) — Daniel decides from evidence.
