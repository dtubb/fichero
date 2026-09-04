# Local-Vision Word-Bbox Lab — 2026-09-02 overnight

Daniel asked for empirical work on making the local (Apple Vision) word
bounding boxes better on the handwritten material: a bounding-box review
second pass over sparse areas, preprocessing before OCR, and tiling were the
ideas on the table. This is the measured answer.

**Headline: an ink-driven sparse-area second pass is the win, and it is now
wired into production** (`_escalate_ink_residue` in `vision_base.py`, unit
tests in `test_ink_residue_rects.py`). Text-ink coverage on the worst sample
page went 0.26 → 0.70; the faint-pencil lines Apple missed entirely on
1933_p14 are now boxed; no sample regressed. Preprocessing turned out to be
page-dependent (helps one failure mode, wrecks another) and stays a report
recommendation, not a code change.

## Where Apple Vision actually runs

Engine-side, via pyobjc: `vision_base.apple_vision_ocr_with_geometry` →
`VNRecognizeTextRequest` (revision 3, the max this OS exposes; Accurate
level; language validated). No pivot needed — the lab drives the exact
production code path. The pipeline before tonight: Accurate pass → gap/strip
escalation (full-width bands: 3 overlapping strips + tall-gap heuristics +
transcript-anchored bands) → ink-snap tighten. Word boxes come from
`boundingBoxForRange:` per whitespace token with proportional-slice fallback.

## Method

- 6 sample pages copied read-only out of `~/code/marshall_diaries/_import`
  (originals of the Marshall v3 pages; the library itself untouched) into
  `agent-work/bbox-lab/samples/`: 1913 printed rate tables, 1923 dense
  printed calendar, 1923/1927/1933 cursive+pencil ledger pages.
- Harness: `agent-work/bbox-lab/lab.py`. Metrics per page:
  - **ink_recall** — fraction of TEXT-ink pixels inside any word box. The
    ink mask is background-subtracted (darker than the local median), with
    ruled lines/borders (long straight runs), dark backdrop and page-edge
    junk removed, validated by eyeball renders (`out/*__mask.png`).
  - **box_tightness** — ink pixels ÷ boxed area (how much paper the boxes
    swallow).
  - words / lines / mean measured confidence / seconds.
- Overlays for every run: `agent-work/bbox-lab/out/<page>__<tag>.png`
  (blue = line boxes, green = measured words, orange = interpolated words).

## Baseline (production before tonight)

| page | ink_recall | tightness | words | notes |
|---|---|---|---|---|
| 1913_p05 (print, tables) | 0.802 | 0.253 | 966 | dense but decent |
| 1923_p03 (printed calendar) | **0.258** | 0.396 | 174 | most numerals unboxed |
| 1923_p10 (cursive) | 0.899 | 0.089 | 114 | good |
| 1927_p02 (cursive, faint) | 0.694 | 0.139 | 40 | headers+lines caught |
| 1933_p14 (pencil) | 0.746 | 0.207 | 59 | **two whole pencil lines with zero boxes** ("Mr + Mrs WW Avery returned / from La Vuelta") |
| 1933_p41 (mostly print) | 0.810 | 0.214 | 40 | good |

Two distinct failure modes:
1. **Faint pencil cursive lines return no observation at page scale** even
   with the strip escalation (1933_p14).
2. **Dense small print** — the page-scale pass resolves only scattered
   glyphs (1923 calendar).

## Experiments (one variable at a time)

### Preprocessing before OCR (same-dimension frames, so boxes stay valid)

| page | baseline | CLAHE | adaptive binarize | contrast stretch |
|---|---|---|---|---|
| 1913_p05 | 0.802 | 0.801 | **0.864** | 0.781 |
| 1923_p03 calendar | 0.258 | 0.218 | **0.103** | 0.156 |
| 1923_p10 | 0.899 | 0.891 | 0.809 | 0.882 |
| 1927_p02 | 0.694 | 0.686 | 0.660 | 0.696 |
| 1933_p14 pencil | 0.746 | **0.848** | 0.743 | 0.763 |
| 1933_p41 | 0.810 | 0.810 | 0.795 | 0.809 |

Verdict: **page-dependent, not a global win.** CLAHE rescues faint pencil
(+10pts on 1933_p14) but costs the calendar; binarization helps clean print
and destroys everything else. A global preprocessing step ahead of Vision
would trade one failure mode for another. The safe home for preprocessing is
*inside a retry on a region that already failed* — where it can only add —
or as the existing opt-in image-cleanup workflow tools (the image-quality
lane's OpenCV port), never as a hidden default.

### Ink-driven sparse-area second pass (the winner — SHIPPED)

Mechanism: after the strip escalation, build the text-ink mask of the page
(same numpy/PIL technique as the metric and the existing ink-snap: darker
than local median background, long straight runs and dark regions removed),
erase everything already inside a word box, pool what remains onto an 8×8
grid, merge marked cells into ≤8 crop rects **capped at 3×3 cells** so a
crop always zooms the glyphs (uncapped, the calendar merged into one
near-page rect and recovered half as much — measured), re-OCR each crop
with the same request, map boxes back through the named crop→page frame
transform, dedupe against existing lines, re-sort into reading order.

| page | baseline | shipped (v2) | Δ |
|---|---|---|---|
| 1913_p05 | 0.802 | **0.886** | +0.084 |
| 1923_p03 calendar | 0.258 | **0.696** | +0.438 |
| 1923_p10 | 0.899 | **0.944** | +0.045 |
| 1927_p02 | 0.694 | 0.699 | +0.005 |
| 1933_p14 pencil | 0.746 | **0.821** | +0.075 — the missed pencil lines are boxed now (see overlay) |
| 1933_p41 | 0.810 | 0.811 | 0 (nothing to recover; pass cost ~1.5s) |

Tightness held or improved everywhere (calendar 0.396→0.436). Cost: +1.5–6s
per page (worst 11s on the 1913 table page). No regressions on any sample.
Confidence of recovered lines is Vision's own — measured, not fabricated;
interpolated words keep `confidence=None` per the existing contract.

Evidence renders: compare `out/1933_p14__baseline.png` vs
`out/1933_p14__production_v2.png`, and `out/1923_p03_part1__baseline.png` vs
`out/1923_p03_part1__production_v2.png`.

Also tried: the same pass with CLAHE applied to the crops before re-OCR
(`sparse2_clahe`) — within noise of the plain pass on 5/6 pages, worse on
the pencil page. Not worth the moving part.

### customWords with a known transcript (measured: null for geometry)

The idea: when a page already has good text (cloud transcription), feed its
vocabulary to `VNRecognizeTextRequest.customWords` and re-run Vision for
better word boxes. Measured on the two handwriting pages with a
hand-verified page vocabulary, single Vision pass isolated:

| page | plain | +customWords | correction OFF | custom + corr OFF |
|---|---|---|---|---|
| 1933_p14 | 0.746 / 59w | 0.746 / 59w | 0.751 / 59w | 0.751 / 59w |
| 1927_p02 | 0.696 / 40w | 0.696 / 40w | 0.696 / 40w | 0.696 / 40w |

`customWords` changed nothing but decode confidence (0.72→0.74 on p14):
it biases the language model that picks the TEXT, while boxes come from the
detector — a line Vision cannot see stays unseen whatever the vocabulary.
The transcript's real geometric leverage is already in production in a
stronger form: `_unmatched_reference_bands` (a transcript line with no
fuzzy match in the OCR proves a missed band and targets a re-OCR crop
there), which composes with tonight's ink-residue pass.

### Locked-session check

Measured under a LOCKED GUI session and re-verified: on this machine the
pyobjc `VNRecognizeTextRequest` path returns byte-identical results locked
vs unlocked (sanity page 42w/13l both times) — the locked-session
degradation in memory applies to screenshot/CGEvent verification, not this
OCR path. Every suite tonight was bracketed by a sane-output check.

### What was probed and rejected

- **Vision request tuning**: revision already at max (3); `es-ES` vs `en-US`
  is validated upstream; `minimumTextHeight` already defaults to smallest.
  `automaticallyDetectsLanguage`/`usesLanguageCorrection` affect text, not
  localization, and the boxes are the product here.
- **Denser fixed strip tiling**: the ink-driven pass subsumes it — it tiles
  exactly where tiles pay, instead of everywhere.

## Residuals / next steps (report only, no code)

- 1927_p02 sits at ~0.70 because its remaining "uncovered ink" is mostly
  page-edge texture and ledger-figure fragments; genuine text there is
  boxed. The metric floor, not a miss.
- The pass runs only when `source_path` exists (flat images) — PDF pages
  skip it today, same as ink-snap. Extending both to PDF page renders is
  mechanical (write the rendered CGImage to a temp PNG) if PDF diaries need
  it.
- A second iteration of the pass (re-run on the merged result) could lift
  the calendar further (the lab's uncapped-crop variant reached the same
  0.69 with different rects); one iteration was chosen as the
  cost/benefit point.
- If a page's recovered-line text quality matters (not just boxes), the
  VLM detect-regions path can transcribe the crops the ink pass names —
  a cheap targeted hybrid instead of a whole-page VLM call.

## End-to-end validation (CLI + scratch engine)

Booted an isolated TCP engine from this worktree's source
(`_engine_harness`, own base path/token, `FICHERO_FEATURE_TIER=beta`),
created a fresh scratch library, imported 1933_p14 via the CLI, ran the
**Detect Regions (Apple Vision)** workflow with `--wait`, and read the
persisted `regions` artifact back: **74 word boxes / 24 line boxes,
provider `apple_vision`** — identical to the lab's shipped-path counts,
so the ink-residue pass flows through detect_regions → process_vision →
artifact unchanged. Scratch engine and libraries removed afterwards.
Driver: `agent-work/bbox-lab/e2e_cli.py` + `engine_up.py`.
(Note: `artifacts list` omits `ocr_geometry`; use `artifacts get`.)

## Artifacts

- Lab: `agent-work/bbox-lab/lab.py`; metrics JSON + overlays + masks under
  `agent-work/bbox-lab/out/`; per-run box dumps under `out/boxes_<tag>/`.
- Production change: `_long_run_mask`, `_uncovered_ink_rects`,
  `_escalate_ink_residue` in
  `fichero-server/src/fichero_server/workflows/tools/vision_base.py`.
- Tests: `fichero-server/tests/unit/workflows/test_ink_residue_rects.py`
  (9 cases: placement, coverage, furniture rejection, caps, missing file,
  run-mask behaviour).

---

## Correction 2026-09-03 — "revision already at max (3)" was the wrong conclusion

This lab recorded the recognition revision as already maxed at 3 and moved on.
Measured the next day on six pages: revision 3 is the best READER and not the
best DETECTOR. Revision 1 localizes text revision 3 never reports — most
dramatically on dense small print — and localized less on no sample. It now
runs as an additive second detector after the ink-residue pass
(`_escalate_second_detector`), lifting the printed-calendar page from 0.535 to
0.774 text-ink coverage for about 0.2s, neutral on the other five, no false
boxes anywhere.

Also re-measured here and confirmed: `.fast` is the only variant that puts
boxes on blank paper; whole-page upscaling is worse than not upscaling; denser
strip tiling still loses to the ink-driven pass; and per-line zoom crops cost
1–47s to lose ground on cursive pages.

Full numbers: `vision-region-experiments.md`.
