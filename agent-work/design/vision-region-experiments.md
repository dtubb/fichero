# Apple Vision regions — text→boxes backfill, and a better free detector

2026-09-03. Started from Daniel's question — *"Can we get much better results
from the Apple Vision detect regions? Like, could giving it the actual text
improve results?"* — and reframed mid-session into the product it was really
asking for: **thousands of documents have text and no boxes**, and a second,
co-equal goal — *"Apple Vision is free; if we can get that better, locally,
that's really central."*

Two tracks, both measured on real Marshall diary pages, zero cloud calls.

## What shipped

| # | change | why | evidence |
|---|---|---|---|
| 1 | `geometry_merge` guards made directional + a strong-match floor | the backfill's alignment refused 5 of 6 real pages | 5/6 now merge, hit_rate 1.00; the bad page still refused |
| 2 | merged geometry reports `aligned:<engine>`, never the OCR engine | a backfilled page must not pass for a measured one | provenance tests |
| 3 | `_owning_line` disambiguates colliding char spans by position | escalated words carried spans pointing at the wrong text | word spans that read back correctly: 29–72% → **84–99%** |
| 4 | escalation bands must contribute only where the page was unread | strips re-read lines and BOTH readings entered the transcript | paleography gold page: intermittent 0.88 CER → stable 0.42, 5/5 runs |
| 5 | revision-1 second detector folded in after the ink-residue pass | an older revision localizes text the newest never reports | dense print 0.535 → **0.769** ink coverage, +0.2s, no false boxes |
| 6 | `detect_regions` declares the pass-through ports it already returns | a preset could not chain anything after it | preset gate passes |
| 7 | **"Backfill Text Geometry" preset** — Files → Detect Regions → Merge Geometry | the batch shape for the 1000s-of-pages corpus | preset execution gate |

---

# Track A — the text→boxes backfill

The input is a page image plus text nobody has boxes for. The output is
word and line boxes **for that text**, persisted through the existing geometry
artifact, honest about which boxes were measured and which were interpolated.

## The parts already existed; two of them were broken

`merge_reviewed_text_onto_geometry` (shipped 2026-08-28) is the forced
alignment: reviewed lines are matched to measured lines by a monotonic DP on
folded text, each reviewed word takes the measured box that read it, and the
rest are interpolated across the anchored line. `merge_geometry` is the batch
tool around it, already `supports_batch=True`.

**It refused 5 of 6 real pages.**

| page | reviewed / measured lines | before | after |
|---|---|---|---|
| 1923_p03a (printed calendar) | 40 / 485 | REFUSED (12.1×) | REFUSED — correctly, see below |
| 1923_p10a | 12 / 40 | REFUSED (3.3×) | **merged, coverage 1.00** |
| 1927_p02b | 9 / 26 | REFUSED (2.9×) | **merged, coverage 1.00** |
| 1933_p14a | 5 / 12 | merged | merged, coverage 1.00 |
| 1933_p14b | 9 / 28 | REFUSED (3.1×) | **merged, coverage 1.00** |
| 1933_p41a | 3 / 9 | REFUSED (3.0×) | **merged, coverage 1.00** |

The refusals were an artefact. Inspected pairing by pairing, every one of those
alignments is correct — including where the OCR text is unreadable:

```
1923_p10a   Came Assiga here on way to Fatmina  <-  Cesse Arrega hue ou way to Jatrinar
            towed back.                         <-  tomed ba c
1933_p14b   Replied in odolfo Ortiz case        <-  MCP- Rodolfo Orty cane
            from La Vuelta.                     <-  from Sa Vuel
```

`MAX_LINE_COUNT_RATIO` was symmetric (`max/min > 2.5` refuses). The two
imbalances are different defects:

- **reviewed ≫ measured** — Vision did not see most of the page; the skeleton
  is missing. Refuse. This is the merged-columns case the guard was written
  for, and it stays.
- **measured ≫ reviewed** — Vision saw *more* than the transcript covers. On a
  printed diary this is the **ordinary case**: preprinted day headers, folio
  numbers and ruled-line fragments are lines no transcript transcribes, and the
  monotonic alignment already skips them.

Making the ratio directional needed a real replacement for the accident that
caught the calendar page — whose merge really is garbage
(`out2/1923_p03a__merge_relaxed.png`: date numerals scattered into unrelated
cells). Coverage cannot catch it: it counts pairings, and `MIN_LINE_SCORE` is
deliberately low (0.30) so a badly-read line can still find its own
transcription. A page of short repetitive lines fills its coverage at that
floor. The separation is clean on match STRENGTH:

| page | coverage | median match similarity | share ≥ 0.60 |
|---|---|---|---|
| 1923_p03a (calendar) | 0.82 | 0.444 | **0.30** |
| 1923_p10a | 1.00 | 0.795 | 0.92 |
| 1927_p02b | 1.00 | 0.800 | 0.89 |
| 1933_p14a | 1.00 | 1.000 | 1.00 |
| 1933_p14b | 1.00 | 0.818 | 0.78 |
| 1933_p41a | 1.00 | 1.000 | 1.00 |

So: at least half the reviewed lines must pair at ≥ 0.60 similarity
(`MIN_STRONG_LINE_SCORE` / `MIN_STRONG_LINE_COVERAGE`). Calendar scores 0.25
and refuses; the prose pages run 0.78–1.00 and pass.

Alignment cost is not a concern at corpus scale: 200 reviewed lines against
2000 measured ones aligns in 1.5s, and real pages are two orders of magnitude
smaller (40 × 485 → 0.17s).

## How good are the boxes? (E8 — the success metric)

Ground truth is the hard part: no Marshall page ships hand-drawn word
rectangles. So the truth is manufactured honestly — **Vision's own measured
boxes are ground truth for Vision's own text**. Hide some of them, hand the
alignment the text, and measure what comes back against what was hidden. Two
knobs, matching the two hardships the backfill actually faces:

- **ablation** — the transcript names words this page's OCR never boxed. That
  is what interpolation has to cover.
- **corruption** — the transcript disagrees with the OCR's reading (character
  substitutions, length preserved so the truth stays addressable). That is what
  the alignment has to survive on an old hand.

**Mean IoU of recovered boxes against the hidden truth:**

| page | a0/c0 | a0/c30 | a25/c15 | a50/c0 | a50/c30 |
|---|---|---|---|---|---|
| 1923_p03a | 0.821 | 0.787 | 0.846 | 0.850 | 0.785 |
| 1923_p10a | 0.794 | 0.737 | 0.720 | 0.696 | 0.664 |
| 1927_p02b | 0.996 | 0.859 | 0.828 | 0.845 | 0.769 |
| 1933_p14a | 0.799 | 0.793 | 0.777 | 0.785 | 0.775 |
| 1933_p14b | 0.894 | 0.858 | 0.847 | 0.840 | 0.844 |
| 1933_p41a | 0.862 | 0.897 | 0.887 | 0.870 | 0.897 |

*(a = % of boxes ablated, c = % of characters corrupted)*

**Share of words recovered at IoU ≥ 0.5:** 0.77–1.00, typically ~0.87 — and
flat across the grid. **Word coverage** (reviewed words that got a box at all):
0.73–0.90, unchanged by ablation or corruption, because the shortfall is lines
that found no partner, not words that found no box. **Interpolated boxes
alone** score IoU 0.46–0.96, typically ~0.7 — interpolation is doing real work,
not decorating.

The headline for the backfill: **degrading gracefully is the result.** Hiding
half the measured boxes and corrupting a third of the characters costs about
0.05–0.13 mean IoU. That is the regime a real corpus lives in.

## Provenance

The merged artifact now reports `provider: "aligned:apple_vision"`, not
`apple_vision`. A merged page is not an OCR result — its text came from a
person or a stronger model, its anchored boxes were measured by the engine
named after the colon, and the rest were interpolated. Per-box `provenance`
(`measured` / `derived`) was already recorded; the artifact-level provider now
agrees with it.

Against the authority ladder (`OCRGeometrySelection.ranked`, commit
70051fa51): hand-drawn geometry is `provider: "user"` at rank −1, and every
machine artifact sits below it. `aligned:*` is not `user`, so a backfilled page
can never outrank a person's own regions — checked and pinned by a test. It
does rank in the `text_geometry` tier, above `regions`/`transcription`, which
is correct for the page's reviewed text but is worth Daniel's eye: that tier's
comment describes a PDF's own text layer ("exact coordinates, not an
estimate"), and a backfilled page is partly estimate. Flagged, not changed —
the ladder is Swift-side and belongs to another lane.

## The batch shape

`merge_geometry` needs measured boxes, and the corpus has none — so the batch
is not one tool but the two-node chain that already exists, now shippable:

**Preset "Backfill Text Geometry"** (`/Detect Regions` folder):
`Files → Detect Regions (Apple Vision) → Merge Geometry`, with
`text_artifact_type: "transcription"`. Batch over any selection, local, free,
no LLM. Documents missing either half are reported, never silently skipped.

Making it shippable needed one fix: `detect_regions` returns `files` and
`documents` pass-through (its body always did — the comment says "so a
transcriber chains directly after this node") but never DECLARED those output
ports, so any preset drawing that edge failed validation with
`Edge references unknown source port 'documents'`. Declared now.

**Runtime per page**, measured: Detect Regions ≈ 5–11s (a dense printed page is
the slow end), Merge Geometry ≈ 0.2s. So a 10,000-page library is roughly
15–30 machine-hours of free local compute, embarrassingly parallel per page,
and nothing to pay a provider.

---

# Track B — making the free detector better

## E4 — recognition level, revision, language

Boxes only, one isolated pass, no escalation ladder. `ink_recall` / box count:

| variant | 1923_p03a | 1923_p10a | 1927_p02b | 1933_p14a | 1933_p14b | 1933_p41a |
|---|---|---|---|---|---|---|
| accurate en (default = rev 3) | 0.142/46 | 0.488/59 | 0.696/40 | 0.695/25 | 0.455/30 | 0.436/15 |
| **revision 1** | **0.765**/167 | **0.564**/65 | **0.703**/42 | 0.695/25 | **0.590**/35 | 0.436/15 |
| revision 2 | identical to revision 1 on every page |
| fast en | 0.698/560 | 0.140/13 | 0.291/15 | 0.425/15 | 0.178/14 | 0.416/15 |
| no language correction | 0.180/51 | 0.561/63 | 0.696/40 | 0.695/25 | 0.591/35 | 0.436/15 |
| automatic language detect | 0.558/101 | 0.488/59 | 0.696/40 | 0.695/25 | 0.455/30 | 0.436/15 |
| languages `es` / `es,en` | identical to `en` on every page |
| `minimumTextHeight = 0` | identical to default on every page |

**Revision 1 localizes more text than revision 3 on five of six pages and less
on none**, at hit_rate 1.00. The 2026-09-02 lab recorded "revision already at
max (3)" — true, and the wrong conclusion: newest is the best *reader*, not the
best *detector*. Text quality is a wash on this material; revision 1 even
catches the notorious "Mr & Mrs WW Avery returned" line revision 3 drops.

`.fast` finds the dense calendar print but wrecks handwriting, and is the only
variant that puts boxes on blank paper (hit_rate 0.857–0.993). Rejected.
Languages and `minimumTextHeight` confirm the prior lab: no geometric effect.

### Shipping it revealed a bug older than the experiment

Folded in naively, the second detector sent the paleography gold page from 0.40
to **1.16** character error: on a dense manuscript the older revision re-reads
every line, `_is_duplicate_line` compares TEXT, and a re-reading that disagrees
by one character is not "the same text" — so both readings entered the
transcription.

The same hazard was **already in production**, in the systematic strip bands of
`_escalate_gaps`: they cover the whole page and dedupe on text alone. It showed
up as an intermittent failure of the gold-page CER test — 0.8827 against a 0.45
ceiling, reproducing with the new detector *disabled*. Fixed by asking the
right question: a band or a second opinion may contribute only where the page
has **not been read at all** (`_overlaps_existing_area`, 30% of the candidate's
own rect). Gold page: stable 0.419 across 5/5 runs, and identical output to the
detector being off. Marshall pages: no box lost.

### What the second detector is worth, through the shipped path

Clean A/B, same process, same machine:

| page | off | on | Δ | added lines | cost |
|---|---|---|---|---|---|
| 1923_p03a | 0.535 | **0.769** | +0.234 | +73 | ~0.2s |
| 1923_p10a | 0.594 | 0.594 | 0 | 0 | ~0 |
| 1927_p02b | 0.706 | 0.706 | 0 | 0 | ~0 |
| 1933_p14a | 0.680 | 0.680 | 0 | 0 | ~0 |
| 1933_p14b | 0.612 | 0.613 | +0.001 | +1 | ~0 |
| 1933_p41a | 0.434 | 0.434 | 0 | 0 | ~0 |

hit_rate 1.00 on every page, before and after. The handwriting pages gain
nothing because the ink-residue pass (2026-09-02) already recovered what was
there; the gain is concentrated exactly where that pass struggles.

## E2 — Two-pass zoom (REJECTED)

Re-OCR every detected line on a 2×/3×/4× upscaled crop, boxes mapped back.

| variant | 1923_p03a | 1923_p10a | 1927_p02b | 1933_p14a | 1933_p14b | 1933_p41a |
|---|---|---|---|---|---|---|
| production | 0.535 | 0.594 | 0.706 | 0.680 | 0.613 | 0.434 |
| zoom 2× | 0.627 | 0.578 | 0.702 | 0.682 | 0.583 | 0.441 |
| zoom 3× | 0.624 | 0.549 | 0.695 | 0.680 | 0.550 | 0.434 |
| zoom 4× | 0.636 | 0.512 | 0.694 | 0.651 | 0.550 | 0.434 |
| whole page 2× | 0.130 | 0.578 | 0.709 | 0.682 | 0.420 | 0.436 |
| cost (3×) | 47s | 10s | 6s | 4s | 7s | 1s |

Gains only on the calendar — where the second detector gains more, for 0.2s
instead of 47s — and **loses** on cursive pages, whose page-scale escalations it
discards. **Upscaling the whole page is worse than not**: Vision normalizes
scale internally, so resampling only adds interpolation noise. (This variant
replaced the production boxes rather than folding in; E7 below tests the fold.)

## E3 — Tiling / strips (REJECTED — confirms 2026-09-02)

| variant | 1923_p03a | 1923_p10a | 1927_p02b | 1933_p14a | 1933_p14b | 1933_p41a |
|---|---|---|---|---|---|---|
| single pass | 0.142 | 0.488 | 0.696 | 0.695 | 0.455 | 0.436 |
| production | 0.535 | 0.594 | 0.706 | 0.680 | 0.613 | 0.434 |
| 3 strips | 0.518 | 0.593 | 0.705 | 0.682 | 0.594 | 0.435 |
| 6 strips | 0.535 | 0.475 | 0.705 | 0.683 | 0.582 | 0.434 |
| 10 strips | 0.270 | 0.586 | 0.694 | 0.681 | 0.591 | 0.434 |

Strip-wise detection never beats production, and denser is worse — 10 strips
halves the calendar, because a strip boundary through a row of numerals
destroys the line. The ink-driven pass tiles where tiling pays.

## E6 — Preprocessing before detection (NOT RUN — stopped for the gate window)

Harness written and ready (`lab2.py preprocess`): deskew via the server's own
`image_ops.detect_deskew_angle`, illumination flattening via
`image_ops._flatten_illumination`, and the enhance path's contrast 1.25 +
sharpness 1.1 — each run through the full production ladder, so a win here is
a win we could ship by reusing code that already exists. The run was killed
mid-flight when the gate window opened; no numbers, so no verdict.

One methodological note for whoever runs it: deskew ROTATES the page, so its
boxes live in a rotated frame and the metric must be computed against that
frame's own ink mask. Comparing coverage FRACTIONS across frames is legitimate
(rotation preserves ink); comparing rectangles is not. The harness already does
this and records the estimated angle per page, which is the first thing to
read — if the Marshall scans sit near 0°, deskew answers itself.

Prior art bounds the expectation: the 2026-09-02 lab measured CLAHE, adaptive
binarization and contrast stretch as **page-dependent, not a global win**
(CLAHE +10pts on faint pencil, −4pts on the calendar; binarization +6pts on
clean print and destructive everywhere else). The open question E6 adds is
whether deskew and illumination flattening behave differently — they are
geometric and photometric corrections rather than contrast gambles, so they
have a better prior.

## E7 — Multi-scale merge with NMS (NOT RUN — stopped for the gate window)

Harness written and ready (`lab2.py multiscale`): union the word boxes from
full page + 3 strips + 3× line-zoom crops, dedupe with confidence-ordered NMS
at IoU 0.5, and compare against each single pass. Killed with E6; no numbers.

What the parts already say, and why this is still worth running: strips alone
lose to production (E3) and zoom alone loses on cursive (E2), but both of those
REPLACED the production boxes. E7 is the additive form, which is the shape that
has worked twice now — the ink-residue pass and the revision-1 detector both
win precisely because they only add. The cost is the reason to measure rather
than assume: the union costs the sum of its passes, so on the numbers in E2/E3
that is roughly 50s per page against production's 5–11s. A gain would have to
be large to justify that in a library-wide pass.

## E5 — Region derivation: clustered lines vs Vision's observations (PROPOSAL)

Vision's "line" observations are fragments, not lines: 26 of them on a page
with 9 written lines, 485 on the calendar. Clustering word boxes into lines by
vertical band, and lines into blocks by vertical proximity:

| page | Vision lines | clustered lines | blocks | recall: Vision / clustered / blocks |
|---|---|---|---|---|
| 1923_p03a | 485 | 61 | 3 | 0.537 / 0.733 / 0.860 |
| 1923_p10a | 40 | 10 | 4 | 0.621 / 0.650 / 0.720 |
| 1927_p02b | 26 | 9 | 3 | 0.715 / 0.778 / 0.818 |
| 1933_p14a | 12 | 6 | 3 | 0.692 / 0.681 / 0.729 |
| 1933_p14b | 32 | 9 | 3 | 0.630 / 0.633 / 0.691 |
| 1933_p41a | 9 | 4 | 3 | 0.436 / 0.434 / 0.475 |

hit_rate 1.00 at all three levels. Clustered lines land much closer to what a
reader would call a line (9 for 9 on 1927_p02b), and blocks land on the diary's
day entries.

**Not shipped — a design decision, not a patch.** What `regions` carries is a
downstream-visible contract: the annotation surface, crop substitution and the
region-review workflow all read those boxes, and "line" changing meaning
changes all of them. Overlays: `out2/*__regions.png` (blue = Vision, green =
clustered lines, magenta = blocks). If Daniel wants it, the natural shape is an
ADDITIONAL level (word / line / block), not a redefinition of the existing one.

---

## A bug the metric work uncovered: word spans pointed at the wrong text

Building the IoU harness needed to pair a recovered box to its truth box by
char span, and the spans would not pair. Three word boxes at opposite ends of a
page all claimed `char_start` 0.

`_owning_line` returned the FIRST line whose char span contains the word's.
Lines recovered from a CROP carry the crop's own offsets — a crop's first line
starts at 0, exactly like the page's first line — so after any escalation
several lines claim the same span, and words were assigned to whichever line
came earlier in the list. `_rebase_geometry_reading_order` then rebased those
words relative to the wrong line, and every char-span consumer (span → region
resolution, entry matching, clicking a word in a transcript) inherited it.

Fixed by disambiguating with vertical position when the span is ambiguous —
not circular, because a word derived from its own line's rect sits inside that
line, so position and span agree wherever the span is trustworthy.

**Word spans that read back as their own word, before → after:**

| page | before | after |
|---|---|---|
| 1923_p03a | 177/613 (29%) | **604/613 (99%)** |
| 1923_p10a | 78/164 (48%) | **145/164 (88%)** |
| 1927_p02b | 44/80 (55%) | **73/80 (91%)** |
| 1933_p14a | 28/43 (65%) | **36/43 (84%)** |
| 1933_p14b | 38/98 (39%) | **84/98 (86%)** |
| 1933_p41a | 18/25 (72%) | **23/25 (92%)** |

The residual 1–16% are words whose span stays genuinely ambiguous; worth a
follow-up (allocating non-overlapping provisional spans at fold time would
close it), not a blocker.

---

## Answer to the question

Giving Apple Vision the text does not improve detection. Using the text to
**produce** boxes works well: mean IoU ~0.8 against hidden ground truth,
holding up under half the boxes ablated and a third of the characters wrong,
with every box saying whether it was measured or interpolated. The machinery
mostly existed; it was refusing almost every real page because its trust check
compared line COUNTS instead of asking whether the alignment was EVIDENCED.

And Apple Vision has a **second detector hiding inside it** — an older
recognition revision that sees text the newest one misses, for a fifth of a
second. Wiring it in exposed an older bug of the same family that had been
intermittently doubling transcriptions on dense pages; that is now fixed too.

## Residuals

- The calendar page still refuses the merge, correctly, on this transcript: a
  numeric table wants cell-aware alignment, not line-aware.
- Word coverage tops out at 0.73–0.90 because lines that find no partner emit
  no boxes at all. Deliberate (a box for a line we could not locate is a
  guess), but it means a backfill leaves ~15% of words unplaced on a typical
  page.
- The `text_geometry` authority tier deserves Daniel's eye now that backfilled
  pages land in it (see Provenance above).
- `_fold_unseen_lines` / `_overlaps_existing_area` are now the named, tested
  seam for any future second-opinion pass; nothing should re-implement the
  dedupe.

## Artifacts

- Harness: `agent-work/bbox-lab/lab2.py` (extends `lab.py`), samples with
  transcripts in `agent-work/bbox-lab/samples_text/` (scratch copies), metrics
  and overlays in `agent-work/bbox-lab/out2/`.
- Code: `media/geometry_merge.py`, `workflows/tools/vision_base.py`,
  `workflows/tools/merge_geometry.py`, `workflows/tools/detect_regions.py`,
  `resources/default_workflows/backfill_text_geometry.json`.
- Tests: `tests/unit/media/test_geometry_merge.py` (+5),
  `tests/unit/workflows/test_vision_second_detector.py` (new, 11).
