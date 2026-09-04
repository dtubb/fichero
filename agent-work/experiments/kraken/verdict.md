# Kraken segmenter vs Apple Vision (old + macOS 26 document API) — verdict

Run 2026-09-04, this machine (macOS **27.0**, 16 GB M1), full resolution, CPU,
one job at a time. Kraken's `blla` segmenter finds LINES (polygon + baseline)
and reads nothing. Apple Vision reads and returns word boxes. The baseline
columns are the bbox lab's earlier Vision run on these same pages
(`agent-work/bbox-lab/out/metrics_baseline.json`).

Overlays (contact sheets, three panels each — Kraken blue/red · old Vision
green · macOS 26 documents orange):

- `agent-work/experiments/kraken/1913_p05.overlay.png`
- `agent-work/experiments/kraken/1923_p03_part1.overlay.png`
- `agent-work/experiments/kraken/1933_p14.overlay.png`

Full-resolution single-engine panels sit beside them as `*.kraken.png` and
`*.vision.png` for zooming into one line. They are NOT committed (57 MB of
PNGs); they regenerate from the committed JSON in seconds via
`overlay_report.py`.

| page | frame | Kraken lines | Kraken secs | old-Vision words | old-Vision secs | macOS26 doc lines | macOS26 doc words | macOS26 secs | baseline lines | baseline words |
|---|---|---|---|---|---|---|---|---|---|---|
| 1913_p05.jpg | 2017x2000 | 212 | 26.1 | 1519 | 7.6 | 442 | 973 | 146.4 | 403 | 966 |
| 1923_p03_part1.png | 2090x2418 | 200 | 19.2 | 788 | 9.8 | 166 | 163 | 0.9 | 163 | 174 |
| 1933_p14.jpg | 3063x2000 | 17 | 19.7 | 79 | 3.9 | 18 | 58 | 0.6 | 17 | 59 |

## Read this first: the corpus does not test what we thought

**Two of the three pages are PRINTED, not handwritten.** 1913_p05 is a printed
postage-rate and stock-yield reference table from a diary's endpapers;
1923_p03_part1 is a printed Counting-House calendar grid. Only **1933_p14** is
Marshall's actual hand — and it is a sparse spread, six lines of cursive
against printed date headers.

That reframes the number this experiment was launched over. "403 lines for 966
words" on 1913_p05 was never evidence of a segmenter failing on handwriting: on
a dense printed table, hundreds of short line-boxes is close to *correct*. The
fragmentation story needs a dense handwritten page to be tested at all, and
Caciques 533r — the page the spec named for exactly that job — could not be
located on this machine.

**So: no verdict on dense secretary hand is available from this run.** What
follows is honest about the three pages we have.

## Per page, where each engine wins

**1933_p14 (the only real handwriting) — Kraken wins on kind, not on count.**
All three arms agree on the count (17 / 18 / 17 lines), so nothing separates
them numerically. The overlay separates them completely. Kraken draws ONE
polygon around each written line and a baseline under the ink, following the
line's drift across the page. Old Vision draws a box per word and no line at
all. The macOS 26 arm draws line regions like Kraken's but no baseline. On the
crop of the "…proposing / exeption" entry this is unmistakable: Kraken has a
line, Vision has three words. Neither Apple arm produces a baseline at any
setting — that is not a quality gap, it is a capability Apple does not offer.

**1913_p05 (printed tables) — old Vision wins on completeness.** 1519 word
boxes against Kraken's 212 line polygons, over dense numeric columns. Kraken's
polygons group table rows rather than cells, which is the wrong unit for a
table. If the goal is reading a printed table, Vision is the right tool and
Kraken adds nothing.

**1923_p03_part1 (printed calendar) — nobody covers it well.** Kraken finds 200
line polygons over a grid whose real structure is columns, not lines. Old
Vision finds 788 words against a baseline run's 174, so the two Vision runs
disagree with each other by 4.5x on the same page — worth a separate look,
since one of those numbers is wrong. The macOS 26 arm is the worst here: it
missed the page's largest text entirely (no "Counting-House Calendar for 1923",
no JANUARY, no DECEMBER) and placed the labels it did find where the ink is
not.

## The macOS 26 document API: instrument verified, results still suspect

Because a wrong answer here would kill the Kraken case for the wrong reason,
the harness was validated before its output was believed. A synthetic probe
with text at known positions round-trips correctly (TOP marker reported at
y=0.040 against a true 0.030; BOTTOM at 0.896 against 0.886), so the
coordinate mapping and the lower-left→top-left flip are right.

With the instrument cleared, two facts stand:

1. **It does not fix fragmentation on this corpus.** 442 lines on 1913_p05
   against old Vision's 403 — the same order, not a structural improvement.
2. **Its wall time is wildly unstable:** 146.4s, 67.5s, 0.9s, 0.6s on real
   pages, and 45s on a BLANK synthetic probe. A blank page costing 45 seconds
   and a dense page costing 0.9 is not a cost model anything can be scheduled
   around, and it needs explaining before this API is trusted in a pipeline.

## Footprint — the number the tiering ruling needs

**The 127 MB figure is the compressed wheel, not the install.** Measured:

| | installed |
|---|---|
| Full `pip install kraken` venv | **1.19 GB** |
| Trimmed inference-only venv (verified: segments 1933_p14 to the identical 17 lines) | **996 MB** |
| — of which torch | 596 MB |
| — scipy 100 MB · sympy 74 MB · numpy 34 MB · skimage 29 MB · coremltools 26 MB · lxml 20 MB | |

Install wall time 688s with a warm pip cache. First `import kraken.blla` takes
**34s** (torch 3.4s + kraken 30.5s); warm runs 6-9s. That import cost matters
for "runs automatically at import" — it is per-process, and the segmenter is a
subprocess.

**There is no 127 MB tier.** Trimming removed 200 MB and stopped: kraken's own
import graph reaches training code (`kraken/lib/dataset/recognition.py` imports
pyarrow for dataset reading), and `blla` needs torchvision, skimage,
coremltools and lightning to import at all. Stubbing pyarrow — modelling a
one-line upstream lazy-import patch — saves 129 MB and changes no output, which
is the only cheap win available. Everything after that is torch, and torch is
irreducible for a neural segmenter.

If ~1 GB cannot be built in, Kraken belongs entirely in the user-chosen
download tier. The macOS 26 API is the only zero-byte option, and on this
evidence it is not yet good enough to be the built-in answer.

## Blocker: kraken does not run on this OS as shipped

`kraken 7.1.1` pins `scipy~=1.15.3`, and that scipy's PROPACK binary is
rejected by this macOS's dyld:

    ImportError: dlopen(.../_propack.cpython-312-darwin.so):
    section '__DATA/__thread_bss' has a zero-fill section type,
    but offset field is not zero

Every result above required forcing `scipy>=1.16` (1.18.1 used), which violates
kraken's own pin. Shipping Kraken therefore means overriding an upstream
dependency constraint and owning that decision — a standing maintenance
liability, not a one-off.

## Script coverage — the durable argument, on the right ground

Apple Vision on this machine supports exactly **33 recognition languages**
(measured, `supportedRecognitionLanguages`): Latin-script European, CJK, Thai,
Vietnamese, Hindi/Marathi, Arabic, Russian/Ukrainian. Absent: **Greek (ancient
or modern), Hebrew, Syriac, Ge'ez, Coptic, Armenian, Georgian.** The macOS 26
document request sits on the same recognition engine, so the ceiling binds both
Apple arms.

The Kraken model ecosystem (Zenodo `ocr_models` community, 79 records, queried
by metadata — no downloads): Hebrew 10 (MiDRASH Geniza, Ashkenazi bookhand),
Arabic 9 (Christian Arabic manuscripts, OpenITI), Greek 7 (CLLG Polytonic),
Syriac 6, plus medieval Latin (CATMuS), Old Norse law manuscripts, German and
Swedish Fraktur, and dedicated SEGMENTATION models (Leibniz baselines,
two-column Reichstagsprotokolle, LADaS regions, Orli baseline+reading-order).

**But the two scripts named in the ask both miss:** Ge'ez has zero dedicated
models (the three "ethiopic" hits are generic multilingual PP-OCR), and
cuneiform has zero. Coptic zero, Sanskrit zero.

The honest form of the argument is therefore not "Kraken covers Ethiopia and
Mesopotamia" — today it does not. It is:

1. The recognition ecosystem covers scripts Apple never will (Hebrew, Syriac,
   Greek, Judeo-Arabic — real, cited, available now), and
2. the SEGMENTER is script-agnostic by construction: it finds ink and
   baselines and does not know what writing is. That is what would carry Ge'ez
   or cuneiform line geometry with no recognition model in existence, and it is
   the claim that survives contact with the evidence.

## What this run does not answer

- Dense secretary hand. The corpus had none. Caciques 533r, or any dense
  handwritten page, would settle it in one more slot.
- Why the two Vision runs disagree 4.5x on 1923_p03_part1 word counts.
- Why the macOS 26 request costs 45s on a blank image.
