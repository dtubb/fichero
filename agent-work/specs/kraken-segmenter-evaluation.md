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
runtime install (PyTorch ~2GB — Install Tools window, like MLX), never
bundled.

## The experiment

1. Scratch venv: `pip install kraken` (pin torch CPU wheel; no MPS
   assumptions). Record install size + import time.
2. Segment (blla default model) three pages: Caciques 533r + two
   Marshall diary pages. Record wall time per page (CPU).
3. Render overlays: line polygons + baselines drawn on the page image,
   side by side with Apple Vision's word boxes on the same pages.
   Output PNGs into agent-work/experiments/kraken/ for Daniel to eyeball.
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
