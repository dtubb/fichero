# Readers — which exist, which one a script gets, and how they are measured — Design Spec (#6752)

> Milestone: recipes-run (the catalogue and the measured defaults, #6752); the bake-off's lines also sit in `recipe-designer` and `remote-compute`
> Manual: TBD — a "Which reader reads my pages" section: the kinds of reader, the reader a script starts with and why,
> what the bake-off measures (error, time, memory) and what "as good as the best, and cheapest" means on a Mac.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-20** (a review of the readers end to end; the owner approves).
> Facts read from `origin/integration` 6192c54e5e, file and function, and RUN: the unit tests named below, and the
> engine's own calls on ground-truth pages on an M4 with 24 GB (section "Measured"). A COMPANION of
> `source/models-chains-and-projects.md` (the cards, the rules' order, the bake-off's screens), `compute/training-and-evaluation.md`
> (the one scorer, the policies, the table's order: `training.eval.*`, `training.ab.*`), `ai/local-runtimes.md` (the runtimes),
> `source/ground-truth.md` (what counts as truth) and `source/segments-and-geometry.md` (reading order). This file owns
> THREE things: the list of reader kinds and what each can be asked; the reader a script starts with, from measurement;
> and what a comparison of readers must measure beside the error rate (time, memory, the whole page).
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue; "→ #NEW" marks one the manager files.

## Intent (the design)

A person with pages in any script gets, with no choice to make, the reader that was MEASURED best for that script and
material, on a Mac that can hold it; a comparison on their own corrected pages can replace it, and that comparison
measures the same three things for every kind of reader: how wrong it is (CER and WER under a named policy), how long
a page takes, and how much memory it needs. When two readers are as good as each other (inside the project's noise
band), the cheaper one wins, and on a Mac "cheaper" means faster and smaller, not only dollars. The number a person
is shown is the number they will live with: the error of the transcript of a page (lines found by the line finder,
read, and put in order), not only of lines already drawn.

## Prior art

- **Kraken's model repository (HTRMoPo on Zenodo)** and **HTR-United**: readers and ground truth carry script, licence
  and a card; we adopt the DOI as the pin and the card's script list as a filter, and add what they lack: a measurement
  per script on pages the model did not train on.
- **eScriptorium, Transkribus**: a model is chosen from a list by the person; a "CER on validation" is the model's
  own. We keep the person's choice and add a default by measurement.
- **CATMuS guidelines**: a reader trained to a transcription convention is scored against text in that convention
  (`training.eval.policies-named`, the `catmus-as-written` policy).
- **OCR-D and the ICDAR reading-order evaluations**: recognition error on given lines and error of the page text are
  two measures; a page's order is scored apart from its lines. We adopt both measures (section "The whole page").
- **LM Studio / mlx-vlm**: a model's fit is weights plus context against the machine's memory
  (`ai.where.one-memory-number`); we adopt the estimate and replace it with the measured peak once a model has run.

## What exists today (read and run 2026-11-20)

| Kind | Runs through | Is asked | In the read step | Scored by the bake-off |
|---|---|---|---|---|
| Kraken recognition, LSTM (`.mlmodel`: CATMuS, McCATMuS, any repository reader) | `llm/kraken_runtime.py` `read_given_lines`, `recognize_to_geometry` | a line on its baseline and outline | yes | yes (`training/evaluation.py` `read_with_kraken`) |
| PP-OCRv6 (tiny, small, medium), through Kraken (`.safetensors`) | the same | the same | yes | yes |
| Apple Vision | `workflows/tools/vision_base.py` `apple_vision_ocr` | each line's picture, or a page | yes | yes, a line at a time (`read_with_vision`, provider `apple`) |
| A vision-language model on this Mac (MLX, `mlx-vlm`) | `llm/line_reader.py` `read_lines`, the in-process MLX server | line pictures cut by `llm/line_cut.py` `crop_line`, 1 to 40 a request | yes | yes, asked by line, by region and by page (`requests_for`) |
| A cloud vision-language model | the same reader, a remote provider | the same | yes, where pages may leave | yes, where pages may leave |
| TrOCR (Hugging Face, safetensors only) | `llm/trocr_runtime.py` `read_lines` | a line's bounding box plus 6 px, 8 lines a batch | yes (`tests/unit/recipes/test_trocr_runs_here_5981.py`) | **no**: its pin has no family (`recipes/bakeoff.py` `_family`, `_reader_of`) |
| A Kraken reader on Hugging Face, a reader Fichero trained | Kraken, as above | a line | yes | **no** for the same reason (their pins `kraken_hf`, `trained` have no family) |
| A page-level OCR model (GLM-OCR, DeepSeek-OCR and the like) | not built | the whole page picture | no | no |
| Tesseract | not bundled (`recipes/seed/cards.yaml`, `runs_here: false`) | a line | no | named, not scored |

- **The catalogue** is `recipes/seed/cards.yaml`: three Kraken readers (McCATMuS, CATMuS Medieval, PP-OCRv6 medium),
  Apple Vision, one small historical vision model for medieval Latin, and two general MLX vision models. Kraken's
  repository and the Hub are searched live by the finder (`recipes/discovery.py`) when the Mac is online.
- **The rules** choose by fit, in a fixed order (`recipes/assemble.py` `_rank_key`): a measurement on the project's own
  pages, then period, material, a reader made for the script, languages, the card's PUBLISHED error rate, then
  installed, local, cheaper, faster, smaller.
- **The bake-off** (`recipes/bakeoff.py`, `training/evaluation.py`) reads the checked lines of the sample pages on
  their OWN geometry with at most two readers of each kind (Kraken, Apple Vision, MLX, cloud), scores each page by
  the one scorer under every policy, records CER, WER and the seconds spent, and ranks in one-point bands.
- **Batching.** The Kraken reader sends one line at a time (`kraken_runtime.reader_batch_size`, `source.read.batch-of-one`);
  the person can set 1 to 64 in Models and Compute (`llm/model_run_settings.py`). TrOCR's batch is a fixed 8
  (`workflows/tools/economy_htr.py` `trocr_transcribe_lines`).
- **The line finder's measured defaults per script** exist as a table with a test and no caller
  (`llm/kraken_script_defaults.py`, `tests/unit/llm/test_kraken_script_defaults_6752.py`).

## Measured (2026-11-20, an M4 with 24 GB; the engine's own calls)

Method. Ten scripts from the test corpus, three pages each (one for the notarial hand), at most 40 ground-truth
lines a page for line readers. Each reader in a fresh process, peak memory from the process's own high-water mark,
time is the reading call (the first page includes loading the model). CER is the engine's `score_page` under the
default policy (`layout-insensitive`), WER its `word_errors`. "On given lines" is what the bake-off measures (the
ground truth's line shapes); "whole page" is what a run produces (`recognize_to_geometry`: bundled line finder at
1800, reader, the engine's reading order) scored against the page's whole text. Kraken at the engine's defaults
(batch 1, CPU). Earlier and wider: the 37-set evaluation of 2026-11-19 behind #6752.

### On given lines (CER %, seconds a line, peak GB)

| Script and material | PP-OCRv6 medium | PP-OCRv6 small | The specialist | Apple Vision (line pictures) |
|---|---|---|---|---|
| Old French, Gothic bookhand | 4.6 · 0.15 · 1.6 | 5.9 · 0.07 · 1.3 | CATMuS Medieval 4.2 · 0.06 · 2.7; CREMMA 4.3 · 0.06 · 1.4 | 58 |
| Medieval Spanish bookhand | **3.0** · 0.12 · 1.3 | 5.7 · 0.06 · 1.0 | CATMuS Medieval 7.5 · 0.05 · 2.3 | 65 |
| Spanish early-modern notarial hand | 64 · 0.38 · 2.1 | 49 · 0.19 · 1.6 | McCATMuS 86 · 0.17 · 5.7; CATMuS 76 · 5.7; Tridis (documentary cursive) 72 · 0.24 · **10.7** | 76 |
| French 19th-century register, a printed form filled by hand | 25 (7 without case and punctuation) · 0.09 · 2.0 | 23 · 0.05 · 1.6 | LECTAUREP **2.0** · 0.07 · 3.6; McCATMuS 2.9 · 0.07 · 3.6 | 24 |
| German Fraktur newspaper | **1.6** · 0.18 · 1.4 | 3.0 · 0.08 · 1.1 | german_print 6.6 · 0.07 · 3.5; McCATMuS 24 · 3.5 | 33 |
| Arabic, Maghrebi manuscript | **9.6** · 0.15 · 1.2 | 19 · 0.10 · 0.9 | the printed Arabic-script reader 62 · 0.13 · 1.8 | refused: no Arabic on this Mac |
| Urdu, nastaliq print | **6.3** · 0.16 · 1.5 | 13 · 0.10 · 1.2 | the printed-Urdu reader 24 · 0.17 · 3.2 | refused |
| Syriac, estrangela manuscript | **12.7** · 0.19 · 1.9 | 17 · 0.11 · 1.6 | the printed-Syriac reader 71 · 0.11 · 4.3 | refused |
| Hebrew, medieval Bibles | 4.0 · 0.10 · 1.5 | 5.2 · 0.06 · 1.1 | BiblIA **1.5** · 0.10 · 2.8 | refused |
| Greek, polytonic minuscule manuscript | 57 · 0.31 · 2.2 | 62 · 0.15 · 1.7 | the polytonic-Greek print reader 85 · 0.32 · 6.6 | refused |

- PP-OCRv6 medium is best or within a point of the best on six of ten; a specialist wins on modern French hands (2.0
  against 25) and medieval Hebrew (1.5 against 4.0); nothing reads the notarial hand or the Greek minuscule (the train path).
- The rules today pick McCATMuS first for Fraktur (24%) where PP-OCRv6 reads 1.6%, and offer NO reader for nastaliq
  (`Aran`) where PP-OCRv6 reads 6.3%.
- **Memory is the batch AND the reader.** The same lines, batch 8 against batch 1: CATMuS 10.7 GB against 2.7,
  PP-OCRv6 4.0 against 1.6, with no gain in speed or accuracy. At batch 1 PP-OCRv6 medium peaks at 1.2 to 2.2 GB, the 16 MB LSTM
  readers at 1.4 to 5.7 GB and Tridis (25 MB) at 4.1 to 10.7 GB, the most on the page with the widest line shapes.
  Every Kraken card says 1.0.
- Apple Vision on a hand or on Fraktur is 24 to 76% wrong and refuses five of the ten languages; it is a print and
  modern-typescript reader.

### The whole page (what a run produces)

| Script and material | CER % on given lines | CER % of the page text | With lines matched (order set aside) | What happened |
|---|---|---|---|---|
| Medieval Spanish, two columns | 3.0 | 26 (pages: 3, 2, **69**) | 4.5 | one page of three read across the columns, line by line |
| Old French, two columns | 4.6 | 31 (40, 50, 5) | 5.0 | two pages of three read half a column at a time |
| Fraktur newspaper, two columns | 1.6 | 26 (**72**, 6, 6) | 10 | one page of three read across the columns |
| Urdu, nastaliq print | 6.3 | 11 | 12 | order kept; a heading missed |
| Arabic, Maghrebi manuscript | 9.6 | 49 | 21 | 60 lines found for 40: margins and fragments |
| Syriac, estrangela | 12.7 | 38 | 39 | 14 of 51 lines not found |
| Hebrew, medieval Bibles | 4.0 | 90 | 52 | 293 lines found for 143: lines found in pieces at 1800 with the bundled base (the ground truth leaves out the marginal notes, so part of the excess is real text) |
| Spanish notarial hand | 64 | 41 | 42 | Kraken's own line shapes read BETTER than the ground truth's wide ones |

- A reader measured at 3 to 5% on given lines gives a page that is 26 to 32% wrong when the columns interleave; the
  bake-off cannot see it. The line finder's measured defaults (the 2026 base at 1200 for Hebrew and Arabic) are not
  applied by any run, which is most of the Hebrew and Arabic gap.

### Vision-language models and TrOCR on this Mac (MLX, `mlx-vlm` 0.6.17)

Each in a fresh process on the GPU; memory is the process's peak footprint (a GPU reader's resident size
understates it); "a line" and "a page" are reading time with the model loaded. The line requests use the engine's own
cut (`crop_line`) and instruction; the page requests send the page reduced to 1,600 px on its long side.

| Reader | Asked | Material | CER % | Time | Peak GB |
|---|---|---|---|---|---|
| A 0.9B page-level OCR model (GLM-OCR, 8-bit) | the page picture | Fraktur newspaper | **4.6** for the page, in order | 24 s a page | 5.0 |
| | | Old French bookhand | 28 | 22 s | 5.0 |
| | | medieval Spanish bookhand | 60 | 11 s | 4.7 |
| | | Spanish notarial hand | 53 | 14 s | 4.5 |
| | | French register, form filled by hand | 99 | 42 s | 5.4 |
| | | Arabic manuscript | ran on: an answer 25 times the page's length | 66 s | 5.2 |
| Qwen2.5-VL 3B, 4-bit (a seed card) | the page picture | Fraktur newspaper | **4.0** for the page, in order | 33 s a page | 6.3 |
| | the page picture | Spanish notarial hand | ran on: 6 times the page's length | 96 s | 5.3 |
| | 4 line pictures a request (its card's way) | Fraktur newspaper | 55: 61 of 120 lines lost, 14 of 30 answers were not the list asked for | 0.7 s a line | 5.1 |
| | | Old French bookhand | 28 | 1.6 s a line | 6.2 |
| | | Spanish notarial hand | 69 | 1.5 s a line | 5.7 |
| | | Arabic manuscript | 81 | 3.4 s a line | 6.1 |
| Qwen2.5-VL 7B, 4-bit (a seed card) | 4 line pictures a request | Fraktur newspaper | 6.5 (every answer readable) | 1.3 s a line | 7.6 |
| | | Spanish notarial hand | 66 | 3.2 s a line | 8.4 |
| The medieval-Latin vision model of the seed catalogue (0.8B) | the page picture | Old French bookhand | **12.4** for the page, in order (its card's published figure) | 25 s a page | 6.0 |
| | one line picture a request, the engine's instruction | Old French bookhand | not read: 0 of 120 answers were the list asked for | 2.4 s a line | 4.5 |
| TrOCR (the documentary-hands model the engine defaults to) | a line's box, 8 a batch | Spanish notarial hand | **44** (the best reader measured on this hand) | 0.9 s a line | 3.9 |
| | | Old French bookhand | 8.5 | 0.85 s a line | 4.1 |
| | | medieval Spanish bookhand | 24 | 0.76 s a line | 3.9 |
| | | French register | 41 | 1.1 s a line | 5.5 |

- **Line or page.** The same 3B model reads a printed page at 4.0% when given the page and at 55% when given four
  line pictures a request, the only way the engine asks it; its page comes out in the right order where the line
  reader's page is 26% wrong from the columns. On a hand the general model is poor either way (by line 28 to 81%, by
  page it runs on). The seed catalogue's own medieval-Latin model reads a page at 12.4% when given the page and
  NOTHING when asked the engine's way: its card names reading jobs the engine cannot ask it.
  For comparison PP-OCRv6 medium reads a line in 0.1 to 0.2 s on the CPU in 1.2 to 2.2 GB.
- The 7B model asked by lines reads Fraktur at 6.5% where the 3B loses half its lines; neither reads the notarial hand.
- TrOCR's batch (8 or 1) changed neither its text nor its memory here; it is 5 to 10 times slower a line than Kraken.
- An answer that runs on (a loop) is scored today as a reading: 620% and 2,400% CER.

## Behaviours

### The kinds of reader

- `readers.kinds.one-table` — **[PARTIAL]** (#5533, #5981) every kind of reader the engine can run is one row of one
  list with what it is asked (a line on its baseline, a line's picture, a region's lines, a page), and every row can
  be read with in a recipe AND measured by the bake-off. Built: Kraken (LSTM and PP-OCRv6), Apple Vision, MLX and cloud
  vision models, in both (`tests/unit/recipes/test_bakeoff_readers.py`, `tests/unit/recipes/test_bakeoff_granularity_5722.py`).
  Not built: the bake-off gives no place to a TrOCR pin, a Kraken reader on the Hub or a reader Fichero trained
  (`bakeoff._family` and `_reader_of` answer nothing for `trocr`, `kraken_hf` and `trained` pins, checked 2026-11-20),
  so a reader the recipe can run cannot be compared.
- `readers.kinds.trocr-is-measured-and-bounded` — **[GAP]** (#5981 → #NEW) TrOCR takes part in the bake-off as its own
  kind, reads through `trocr_runtime.read_lines` there as in a run, and its batch is a run setting with the Kraken
  default of one (today a fixed 8 in `economy_htr.trocr_transcribe_lines`, with no knob in `model_run_settings.KNOBS`).
- `readers.kinds.page-reader-reads-the-page` — **[GAP]** (#5980) a page-level OCR model is given the page's picture
  (reduced to the model's own limit) and answers the page's text; its lines are tied to the found lines by the tie
  step. Today "asked by page" is every line's picture in one request (`evaluation.requests_for`), which such a model
  was not made for. Measured (the table above): a 0.9B page reader reads Fraktur print at 4.6% for the whole page,
  in order, where the line reader's page comes out 26% wrong; on a hand it reads 28 to 99%, so it is a print reader.
- `readers.kinds.prompt-names-the-material` — **[GAP]** (#5533 → #NEW) the instruction to a vision model says what the
  page is from the project's answers (print, typescript or a hand; the script; the direction). Today it always says
  "a photographed handwritten page" (`line_reader.PROMPT`), for a newspaper too.
- `readers.kinds.apple-vision-says-what-it-reads` — **[PARTIAL]** (#5715) Apple Vision is offered for the languages
  this Mac's Vision lists and refused in words for the rest (built: `VisionLocaleRefused`, "Apple Vision can't read
  Arabic on this Mac"; `tests/unit/workflows/test_refusal_for_every_page_fails_the_node_at_once_2026_10_19.py`). Not built: its card still lists
  Arabic, Thai, Han and Hangul for every Mac, and its measured error on a hand (24 to 76%) and on Fraktur (33%) is on
  no card, so it is still a contender there.

### The reader a script starts with

- `readers.catalogue.measured-per-script` — **[GAP]** (#6752) a card carries, per script and material, the error
  measured on the test corpus (pages the model did not train on where that is known), with the date and the pages; the
  rules read THAT before the card's published average (`assemble._rank_key` reads `cer_published` only), and Set Up
  says "measured 3.0% on medieval Spanish bookhand" as the reason.
- `readers.catalogue.ppocr-first-then-the-specialist` — **[GAP]** (#6752) the seed catalogue holds, beside PP-OCRv6
  medium, the specialists that won a script or a hand, each pinned by DOI with its licence: BiblIA for medieval Hebrew
  (10.5281/zenodo.5468286, CC-BY-SA-4.0), LECTAUREP for modern French hands (10.5281/zenodo.6542744, CC-BY-4.0),
  Tridis for late-medieval documentary cursive (10.5281/zenodo.10788591, MIT), CREMMA beside CATMuS for medieval
  French and Latin (10.5281/zenodo.7631619, CC-BY-4.0), and PP-OCRv6 small as the fast choice
  (10.5281/zenodo.21788405, Apache-2.0; half the time a line, 1 to 9 points worse). The printed Arabic-script, printed Syriac and printed Greek
  readers are not seeded: they read manuscripts at 60 to 85%. Today: three Kraken readers
  (`recipes/seed/cards.yaml`); the rest are found only online.
- `readers.catalogue.fraktur-and-nastaliq-get-ppocr` — **[BROKEN]** (#5516, #6752) Fraktur print starts with the reader
  measured best on it and a nastaliq page is offered a reader. Today (rules run on the seed cards 2026-11-20): Fraktur
  gets McCATMuS first (measured 24% against 1.6% for PP-OCRv6, whose card does not list `Latf`), and `Aran` gets "no
  model fits" (`assemble._OTHER_STYLES` refuses an `Arab` card) though PP-OCRv6 reads nastaliq print at 6.3% and a
  nastaliq hand at 18%. The fix is on the card (it lists `Latf` and `Aran`, each with its measurement), not a new rule.
- `readers.catalogue.not-usable-is-said` — **[GAP]** (#6752 → #NEW) where the best measured reader for a script is
  worse than a bar (30% CER), the plan says so before anything runs ("no reader reads this hand yet: 57% on Greek
  minuscule; correct some pages and train") and offers the train path first. Today PP-OCRv6 is proposed for Armenian
  (82% on the 2026-11-19 corpus), Greek minuscule (57%) and the notarial hand (64%) with its 3.9% published average
  as the reason.
- `readers.catalogue.card-memory-is-measured` — **[BROKEN]** (#6752, #6212 → #NEW) a reader's card states the peak
  memory measured reading a page at the engine's batch, and the rule that keeps a reader off a small Mac
  (`assemble._refusal`, `memory_gb` against the Mac's memory less 2 GB) reads it. Today every Kraken reader's card
  says 1.0 GB; measured at batch 1: PP-OCRv6 medium 1.2 to 2.2, the LSTM readers 1.4 to 5.7, Tridis 4.1 to
  10.7. An 8 GB Mac is offered all of them.
- `readers.catalogue.segmenter-defaults-are-applied` — **[PARTIAL]** (#6752, #6751) the line finder's base and height
  follow the page's script (the 2026 base at 1200 for Hebrew, Arabic and Devanagari; the bundled base at 1200 for
  Syriac and nastaliq; 1800 for Latin book pages). Built: the table and its test
  (`tests/unit/llm/test_kraken_script_defaults_6752.py`). Not built: nothing calls `segmenter_defaults`, so every run
  uses the bundled base at 1800; measured cost, Hebrew: 4% on given lines, 90% for the page.

### What a comparison measures

- `readers.bakeoff.time-and-memory-beside-error` — **[PARTIAL]** (#6710, #6212 → #NEW) each candidate's row carries
  seconds a page (the model's load apart from the reading), and the peak memory of the reading, measured in the run,
  beside CER and WER. Built: the seconds, load included (`evaluation.speed`, `tests/unit/training/test_evaluation_job.py`).
  Not built: no memory is measured or kept; the load is not apart.
- `readers.bakeoff.cheapest-among-equals-on-a-mac` — **[BROKEN]** (#5582 → #NEW) among readers within the noise band
  of the best, the recommendation is the cheapest, and for readers that cost nothing "cheapest" is the faster, then
  the one needing less memory, and never one whose measured peak does not fit this Mac. Today `bakeoff.recommend`
  compares price, then local, then CER: of two free readers inside the band it names the lower CER even when the
  other is fifty times faster (checked 2026-11-20). The table's order (`_rank`, `training.ab.fixed-order`) already
  breaks ties by speed and size; the recommendation does not follow it.
- `readers.bakeoff.every-measured-specialist-takes-part` — **[GAP]** (#5533 → #NEW) every seeded reader measured for the
  project's script and material takes part (they read a page in seconds); the limit of two a kind stays for the slow
  kinds (MLX, cloud). Today `PER_KIND = 2` for Kraken too, so of five Latin-script readers the rules' order admits
  two, and the reader that would have won (LECTAUREP at 2.0% on the register) may not be one of them.
- `readers.bakeoff.the-whole-page-is-measured` — **[GAP]** (#5441, #6080 → #NEW) beside the error on given lines, the
  bake-off measures the page as a run would make it (the project's line finder, the reader, the reading order)
  against the page's checked text, and shows three figures: on given lines, the page text, and the page with its
  lines matched (so a bad order is told from bad reading). `training.eval.lines-found` scores the finder alone; this
  line scores the chain. Today only given lines are read (`evaluation.read_with_kraken`).
- `readers.bakeoff.policy-follows-the-convention` — **[GAP]** (#5441 → #NEW) the ranking uses the policy that matches
  how the project's checked text is written, and the row shows every policy. A reader trained to a convention is not
  ranked down for it: the same reading scores 25% under the default policy and 7% without case and punctuation
  (PP-OCRv6 on the hand-filled register). Today the rank is always `layout-insensitive` (`evaluation.evaluate`,
  `ranked_by`); the per-policy figures are kept (`training.eval.policies-named`).
- `readers.bakeoff.batch-does-not-change-the-answer` — **[GAP]** (#6752 → #NEW) a reader's text for a line is the same
  at any batch size, or the bake-off and the run use the same one and say which. Measured through the engine: PP-OCRv6
  on one page, 63.7% at batch 1 and 67.2% at batch 8 (padding to the widest line changes the reading). The engine's
  default is one in both places; a person's batch setting changes a run and not the stored measurement.
- `readers.bakeoff.imported-line-shapes-are-said` — **[GAP]** (#5441 → #NEW) when the checked lines' shapes were
  imported (drawn by another tool) the row says so, because the reading and the memory follow the shape: on the
  notarial page the imported shapes read at 64% and peaked at 2.1 to 10.7 GB; Kraken's own lines on the same page read
  at 41% in 2.2 GB.

### The whole page

- `readers.page.columns-are-read-one-after-the-other` — **[BROKEN]** (#6080) a two-column page's transcript reads the
  first column to its foot, then the second (right to left: the right column first). Built: an XY-cut order
  (`media/layout_order.py` `order_payload`, `tests/unit/media/test_layout_order.py`). Measured on nine two-column pages
  of three sets: four came out across the columns (line by line, or half a column at a time), so the page text is
  40 to 72% wrong while every line is read at 2 to 10%. The corpus measure the module's own note asks for now
  exists: order by regions where the finder gives a region a column, and adopt a learned order (the 2026 segmentation
  base carries one) where the cut finds no gutter.
- `readers.page.order-is-scored` — **[GAP]** (#6080 → #NEW) the test corpus scores reading order as a figure (the share
  of ground-truth neighbours kept in order) per set, in the perf baseline, so a change to the order rule is measured.

### Memory and batching

- `readers.memory.one-line-at-a-time-everywhere` — **[PARTIAL]** (#5854, #6752) every line reader's default batch is
  one and is a setting. Built for Kraken (`source.read.batch-of-one`,
  `tests/unit/llm/test_kraken_batch_bounded_5758.py`); re-measured 2026-11-20: batch 8 is four times the memory for the
  LSTM readers and no faster. Not built for TrOCR (`readers.kinds.trocr-is-measured-and-bounded`).
- `readers.memory.guard-knows-the-reader` — **[GAP]** (#6212 → #NEW) the memory a Kraken page asks for before it starts
  counts the reader, from its measured peak (`readers.catalogue.card-memory-is-measured`); today the guard is sized for the
  line finder (`kraken_runtime.kraken_need_bytes`: 0.5 GB plus 0.6 GB a megapixel of the network's input) and a
  reading of given lines asks 2.5 GB cold, 0.8 GB with the models loaded, whatever the reader: a reader that peaks at
  10.7 GB is let in on 2.5.
- `readers.memory.wide-line-shapes-are-bounded` — **[GAP]** (#6212 → #NEW) a line whose outline is far taller than its
  writing (an imported shape, a merged line) is read from a bounded cut, so one page cannot take ten times the
  memory of its neighbours. Cause to confirm in the build: the LSTM readers' line extractor on the notarial page's
  shapes.

### Vision-language models on a Mac

- `readers.vlm.asked-the-way-it-reads-best` — **[GAP]** (#5722, #5980) a vision-language model is measured asked by the
  page PICTURE as well as by line pictures, and the recipe keeps the way that measured best per material; a card's
  `lines_per_request` limits the line requests, never the page picture. Today a card that states `lines_per_request`
  is never tried by page (`evaluation.granularities_for`), and "by page" is line pictures in one request. The cost,
  measured: the catalogue's medieval-Latin model answers no line request in the form asked (0 of 120) and reads the
  page picture at 12.4%; a 3B general model reads print at 4.0% by page and 55% by lines.
- `readers.vlm.answer-that-runs-on-is-not-read` — **[GAP]** (#5441 → #NEW) a page whose answer is many times longer than
  its reference (three times) is "not read: the answer ran on (N characters against M)", as a too-short one is
  (`training.eval.not-read-is-not-100`); it is never summed. Today `evaluation.judge_page` judges only too little text
  (`READ_SHARE`), so one looping page puts a reader at 600% or more.
- `readers.vlm.unreadable-answers-are-counted` — **[GAP]** (#5722 → #NEW) a row says how many requests came back as
  something other than the list asked for ("14 of 30 answers not readable"), beside its CER. Today those lines are
  empty readings inside the CER (`evaluation.read_with_vision` says why only when EVERY answer failed).
- `readers.vlm.memory-is-the-measured-peak` — **[PARTIAL]** (#5641) a local model's memory on its card is the peak
  measured reading on this Mac once it has read, the estimate before (`ai.where.one-memory-number`). Built: the
  estimate (`llm/local_inference.py` `fit_estimate`, `fichero-server/tests/unit/llm/test_mlx_fit_estimate_5641.py`).
  Measured 2026-11-20 against the seed cards: Qwen2.5-VL 3B 4-bit, card 3.5 GB, the model's own peak 3.8 to 4.3 GB
  reading (5.1 to 6.3 for a whole process); Qwen2.5-VL 7B 4-bit, card 24 GB "until measured"
  (`runtime.mlx.seven-b-reader-needs-24gb`), the model's own peak 6.3 to 6.7 GB reading four line pictures a request
  on a 24 GB M4 (7.6 to 8.4 for a whole process), not measured by page or on a 16 GB Mac. Not built: no measured peak is kept.
- `readers.vlm.speed-on-this-mac-is-on-the-card` — **[PARTIAL]** (#5582, #6710) seconds a page (or a line) measured on
  this Mac is kept on the card and shown before a run is started, so "read 10,000 pages with this" is a time, not a
  guess. Built: pages an hour from a bake-off (`evaluation.speed`,
  `fichero-server/tests/unit/training/test_evaluation_job.py`). Not built: nothing is kept from an ordinary run, and
  the load time is inside the figure.

## Build order

### Stage 1 — The catalogue says what was measured

#### Step 1.1 — Cards carry the corpus measurement; Fraktur and nastaliq get PP-OCRv6; the specialists are seeded (#6752)
- Behaviours: `readers.catalogue.measured-per-script`, `readers.catalogue.ppocr-first-then-the-specialist`, `readers.catalogue.fraktur-and-nastaliq-get-ppocr`, `readers.catalogue.not-usable-is-said`
- Tests: fichero-server/tests/unit/recipes/test_reader_choice_for_scripts_to_spec.py (extended: the ten measured scripts each get the reader measured best; `Aran` and `Latf` get PP-OCRv6; Armenian and Greek minuscule say "train"), fichero-server/tests/unit/recipes/test_fraktur_gets_a_reader_5516.py (extended), fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py
- Size: M

#### Step 1.2 — Measured memory on every reader card, read by the small-Mac rule and the page guard (#6752)
- Behaviours: `readers.catalogue.card-memory-is-measured`, `readers.memory.guard-knows-the-reader`, `readers.memory.wide-line-shapes-are-bounded`
- Tests: fichero-server/tests/unit/recipes/test_reader_fit_5516.py (extended: an 8 GB Mac is not offered a reader measured over 6 GB), fichero-server/tests/unit/llm/test_kraken_guard_sized_by_the_page_perf1.py (extended: the reader's peak is counted)
- Depends on: 1.1
- Size: M

#### Step 1.3 — The line finder's measured defaults reach every run (#6752)
- Behaviours: `readers.catalogue.segmenter-defaults-are-applied`
- Tests: fichero-server/tests/unit/llm/test_kraken_script_defaults_6752.py (extended: a Hebrew page's run loads the 2026 base at 1200)
- Size: S

### Stage 2 — The comparison measures what a Mac pays

#### Step 2.1 — Seconds and peak memory per candidate; the cheapest among equals is the faster and smaller (#5582)
- Behaviours: `readers.bakeoff.time-and-memory-beside-error`, `readers.bakeoff.cheapest-among-equals-on-a-mac`
- Tests: fichero-server/tests/unit/training/test_evaluation_job.py (extended: a row keeps load seconds, read seconds and peak bytes), fichero-server/tests/unit/recipes/test_reader_tiers_recommendation_5922.py (extended: two free readers in the band, the faster is named and the sentence says why)
- Size: M

#### Step 2.2 — Every kind takes part: TrOCR, a Kraken reader on the Hub, a trained reader; every measured specialist (#5533)
- Behaviours: `readers.kinds.one-table`, `readers.kinds.trocr-is-measured-and-bounded`, `readers.bakeoff.every-measured-specialist-takes-part`, `readers.memory.one-line-at-a-time-everywhere`
- Tests: fichero-server/tests/unit/recipes/test_bakeoff_readers.py (extended: a `trocr`, a `kraken_hf` and a `trained` pin each get a family and are scored), fichero-server/tests/unit/recipes/test_trocr_runs_here_5981.py (extended: the batch is the run setting)
- Size: M

#### Step 2.3 — The whole page beside the given lines (#5441)
- Behaviours: `readers.bakeoff.the-whole-page-is-measured`
- Tests: fichero-server/tests/unit/recipes/test_bakeoff_readers.py (extended: three figures a row; interleaved columns show as a page figure far from the matched one)
- Depends on: 2.1
- Size: M

#### Step 2.4 — The policy that fits the project; the batch and the line shapes said on the row (#5441)
- Behaviours: `readers.bakeoff.policy-follows-the-convention`, `readers.bakeoff.batch-does-not-change-the-answer`, `readers.bakeoff.imported-line-shapes-are-said`
- Tests: fichero-server/tests/unit/workflows/test_transcription_accuracy.py (extended), fichero-server/tests/unit/training/test_evaluation_job.py (extended: the row names the batch and where the line shapes came from)
- Depends on: 2.3
- Size: M

#### Step 2.5 — A vision model's row: answers that ran on, answers not readable, measured memory and speed kept on the card (#5722)
- Behaviours: `readers.vlm.answer-that-runs-on-is-not-read`, `readers.vlm.unreadable-answers-are-counted`, `readers.vlm.memory-is-the-measured-peak`, `readers.vlm.speed-on-this-mac-is-on-the-card`
- Tests: fichero-server/tests/unit/recipes/test_bakeoff_not_read.py (extended: an answer three times the reference is not read, with why), fichero-server/tests/unit/recipes/test_bakeoff_granularity_5722.py (extended: the count of unreadable answers), fichero-server/tests/unit/llm/test_mlx_fit_estimate_5641.py (extended: a measured peak replaces the estimate)
- Depends on: 2.1
- Size: M

### Stage 3 — The page a person reads

#### Step 3.1 — Columns read one after the other, and the order is a measured figure (#6080)
- Behaviours: `readers.page.columns-are-read-one-after-the-other`, `readers.page.order-is-scored`
- Tests: fichero-server/tests/unit/media/test_layout_order.py (extended with the three measured page layouts as box fixtures: line-by-line across two columns, half a column at a time, right-to-left columns)
- Size: M

#### Step 3.2 — Page-level OCR models read the page; the prompt names the material; Apple's card says what it reads (#5980)
- Behaviours: `readers.kinds.page-reader-reads-the-page`, `readers.kinds.prompt-names-the-material`, `readers.kinds.apple-vision-says-what-it-reads`, `readers.vlm.asked-the-way-it-reads-best`
- Tests: fichero-server/tests/unit/recipes/test_bakeoff_granularity_5722.py (extended: a page reader's request is one page picture), fichero-server/tests/unit/llm/test_line_reader_refusal.py (extended: the prompt for print says print)
- Depends on: 2.2
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | — (the rows render what the engine serves; the Models and Compute rows are `ui/models-and-compute-window.md`'s) | — |
| Backend (pytest) | y | the reader per script from the cards; memory on the card and in the guard; the recommendation among free readers; every pin has a family; the whole-page figures; the order of columns | the files named in the build order |
| MCP | y | `fichero_models_catalog` carries a card's measurements and memory; `fichero_check_*` carries the three figures | `fichero-mcp/tests/test_mcp_generated.py` |
| Perf (run on purpose) | y | the corpus measure itself: CER on given lines, of the page, order kept, seconds and peak memory per script and reader, kept as a baseline that a model or rule change is compared with | `fichero-server/tests/perf/` (to write; the scripts of 2026-11-19 and 2026-11-20 are the start) |

## Open questions for the owner

1. **Nastaliq.** The ruling of `models-chains-and-projects.md` section 8b says a nastaliq hand gets "needs a model" and
   no naskh reader in its place. PP-OCRv6 is not a naskh reader and measures 6.3% on nastaliq print and 18% on a
   nastaliq hand. Recommended: its card lists `Aran` with those figures, the row in 8b is amended, and the bake-off
   decides.
2. **The bar for "no reader reads this yet".** Recommended: 30% CER on the corpus for the script and material, shown
   with the figure; under it the reader is proposed, over it the train path is proposed first and the reader is
   offered as a draft to correct.
3. **Which policy ranks.** Recommended: `layout-insensitive` stays the default; a project whose checked text is in
   the CATMuS convention ranks by `catmus-as-written`; the row always shows both.
4. **The whole page in the bake-off** costs a line-finder pass per page per finder (seconds each). Recommended: on by
   default for the winner and the runner-up only.
