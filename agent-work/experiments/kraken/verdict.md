# Kraken segmenter vs Apple Vision (old + macOS 26) — verdict

Run 2026-09-04, macOS **27.0**, 16 GB M1, full resolution, CPU, one job at a
time. Six pages, three arms. Kraken's `blla` finds LINES (polygon + baseline)
and reads nothing; Apple's old `VNRecognizeTextRequest` reads and returns word
boxes; macOS 26's `RecognizeDocumentsRequest` returns line/word regions.

Overlays (three panels each — Kraken blue/red · old Vision green · macOS 26
orange). Contact sheets in this directory as `<page>.overlay.png`; full-res
single-engine panels as `<page>.kraken.png` / `<page>.vision.png` for zooming.
PNGs are not committed (57 MB); they regenerate from the committed JSON.

| page | kind | frame | Kraken lines | Kraken s | old-Vision words | old-Vision s | macOS26 lines | macOS26 words | macOS26 s (cold) |
|---|---|---|---|---|---|---|---|---|---|
| caciques_533r.jpg | **handwritten, 17th c. secretary** | 929x1346 | **33** | 13.4 | 45 | 8.1 | **6** | 7 | 168.1 |
| 1923_p10.jpg | handwritten, 1923 cursive (dense) | 3132x2000 | 28 | 26.7 | 134 | 12.8 | 29 | 115 | 38.9 |
| 1927_p02_part2.png | handwritten, 1927 cursive (moderate) | 1994x2338 | **12** | 11.2 | 59 | 8.2 | **1** | 2 | 0.4 |
| 1933_p14.jpg | handwritten, sparse | 3063x2000 | 17 | 19.7 | 79 | 3.9 | 18 | 58 | 0.6 |
| 1913_p05.jpg | PRINTED table | 2017x2000 | 212 | 26.1 | 1519 | 7.6 | 442 | 973 | 146.4 |
| 1923_p03_part1.png | PRINTED calendar | 2090x2418 | 200 | 19.2 | 788 | 9.8 | 166 | 163 | 0.9 |

## The finding

**On 17th-century secretary hand, the macOS 26 document API finds almost
nothing.** On Caciques 533r — roughly thirty lines of dense colonial Spanish —
it returned **6 lines and 7 words**, and the overlay shows what that means: a
box on the "00533" archival stamp and three fragments near the signature. The
entire body of the document is unfound. Kraken segmented the same page into
**33 line polygons with baselines, in 13.4 seconds**, and the overlay shows
them tracking every written line including the ones that drift and overlap.

The same collapse repeats on 1927_p02_part2: **1 line found against Kraken's
12.**

**This is the direct answer to the working ruling.** Option (b) makes
`RecognizeDocumentsRequest` the automatic built-in geometry layer. On modern
material that is defensible — see below. On the archival core this product
exists for, it would ship a layer that returns nothing and reports success.

## Where each engine wins, per page

**Modern legible cursive (1923_p10, 1933_p14): all three work, Apple is
faster.** Counts agree closely (Kraken 28 / macOS26 29; Kraken 17 / macOS26
18), and the overlays show all three arms tracking the lines cleanly. Warm,
Apple costs ~2s where Kraken costs 20-27s. If the corpus were modern diaries,
Apple would be the obvious automatic layer and Kraken would be hard to justify.

**Colonial secretary hand (533r): only Kraken works.** 33 lines vs 6. Old
Vision is in between and structurally wrong — 45 word boxes, several of them
lumping whole paragraphs into one rectangle, most lines unboxed entirely.
Note lane-svo-quality's audit: this page's stored Vision readings include
"ralezeralпововатос", Cyrillic on a Spanish flourish, so its *labels* are not
ground truth even where its boxes land. Kraken reads nothing at all, by
design, which is why it is unembarrassed by the hand.

**Printed matter (1913_p05, 1923_p03_part1): old Vision wins.** 1519 word
boxes on the postage table against Kraken's 212 row-grouping polygons. Kraken
segments a table into rows, which is the wrong unit for a grid. Apple should
own printed pages.

**Baselines are Kraken's alone.** Neither Apple arm produces a baseline at any
setting, on any page. For force-aligning a VLM transcription to lines — the
90e4bda24 program — that is not a quality difference but a capability that
only one engine has.

## Wall-time instability: explained, not disqualifying

Earlier I flagged the macOS 26 arm's 0.6s-to-168s spread as needing explanation
before anything scheduled it. Characterized:

| | cold | warm |
|---|---|---|
| caciques_533r | 168.1s | 1.7s, then 0.7s |
| 1913_p05 | 146.4s | 2.0s |
| blank synthetic probe | 45.0s | 0.4s, then 0.3s |

The multi-minute costs are a **one-time, system-wide cold start** — not
per-process (a fresh process is fast once the system is warm), not per-page,
and they do not recur. Warm inference is 0.3-2.0s, several times faster than
Kraken. My earlier "disqualified regardless of quality" was wrong and is
withdrawn: the cost model is fine. What disqualifies it as a *sole* automatic
layer is the 533r result, not the clock.

One caveat retained: the same page returned 973 words cold and 964 warm.
Small, but it means the API is not bit-deterministic across runs.

## Footprint (unchanged from phase 1)

Full `pip install kraken` venv **1.19 GB**; trimmed inference-only venv,
verified to segment identically, **996 MB**, of which torch is 596 MB. There is
no 127 MB tier — that figure was the compressed wheel. Stubbing kraken's
training-only pyarrow import (a one-line upstream lazy-import patch) is worth
129 MB; everything after that is torch.

## Blocker (unchanged)

kraken 7.1.1 pins `scipy~=1.15.3`, whose PROPACK binary this macOS refuses to
dlopen (`__DATA/__thread_bss has a zero-fill section type`). Every result here
required forcing `scipy>=1.16` against kraken's own pin — a permanent
maintenance liability, not a one-off.

## Script coverage

Apple supports exactly **33 recognition languages** here (measured): no Greek,
Hebrew, Syriac, Ge'ez, Coptic, Armenian or Georgian. Both Apple arms share that
engine and that ceiling.

Kraken's Zenodo `ocr_models` community holds 79 models — Hebrew 10 (MiDRASH
Geniza, Ashkenazi bookhand), Arabic 9 (Christian Arabic, OpenITI), Greek 7
(CLLG polytonic), Syriac 6, plus CATMuS medieval Latin, Old Norse, Fraktur, and
dedicated segmentation models (Leibniz baselines, LADaS regions, Orli
baseline+reading-order).

**Ge'ez and cuneiform have zero dedicated models** (the "ethiopic" hits are
generic multilingual PP-OCR). Coptic zero, Sanskrit zero. The argument that
survives evidence is therefore: the recognition ecosystem covers scripts Apple
never will *today* (Hebrew, Syriac, Greek, Judeo-Arabic), and the segmenter is
script-agnostic by construction — it finds ink, not language, which is what
would carry Ge'ez or cuneiform line geometry with no recognition model in
existence.

## Recommendation

The evidence supports a **split by material, not a single default**:

- Apple (`RecognizeDocumentsRequest`) as the automatic zero-byte layer for
  printed and modern-hand pages, where it is both adequate and fast.
- Kraken as the user-chosen tier, surfaced for exactly the pages Apple cannot
  see — historical hands and non-Latin scripts — where it is the difference
  between thirty-three lines and six.

What would change this: a dense-handwriting page where Apple performs well, or
a Kraken failure on a page Apple handles. Neither appeared across six pages.
