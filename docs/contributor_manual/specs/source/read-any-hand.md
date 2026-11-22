# Read any hand — a blind benchmark, calibrated confidence and a reader that learns a hand from a few corrected lines — Design Spec (#5441, #5338)

> Milestone: read-any-hand
> Spec: source/read-any-hand.md
> Manual: TBD — a "How well is this hand read" section: what the two figures mean (how many corrected lines a hand needs,
> and what share of lines can be trusted unseen), what the four confidence bands in the Reader are, why some of a person's
> corrected pages are kept aside and never trained on, and what the Train offer's curve promises.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's ruling of 2026-11-21 on the flagship
> review; the owner approves). One of two flagship goals that run in parallel; the other is
> `kg/reconstruct-the-record.md`. Facts read from `origin/integration` 2b271cfbc5, file and function; the figures quoted
> are the "Measured" sections of `source/readers.md`, not new runs. A COMPANION of `source/readers.md` (which reader a
> script starts with, the bake-off's rows), `source/ground-truth.md` (what counts as truth), `source/checking.md`
> (verdicts), `compute/training-and-evaluation.md` (the one scorer, held-out pages), `compute/distillation.md` (the loop,
> the gate, the cascade). This file owns FOUR things: the blind-hands benchmark; the two headline figures; calibration
> (how a stored confidence becomes a probability a person can rely on); and the measurement lane that stands beside
> Activity and the runner. It does not restate the lines those specs own: it cites them, and section "Lines this spec
> amends" says which it changes.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line · **[PROPOSED]** waits on an owner's answer. Every non-[OK] line cites an issue; "→ #N" is an
> issue filed on this milestone.

## Ruled 2026-11-21 (owner; paraphrased)

1. **Two flagship goals, in parallel.** Read any hand (this spec) and Reconstruct the record
   (`kg/reconstruct-the-record.md`). Neither waits for the other; each has its own check set and its own Stage 0.
2. **Ground truth is what people correct as they work.** No paid palaeographer. A page a model transcribed and a
   research assistant then corrected by hand is ground truth; so are the owner's and students' corrections. Where no
   person has checked a page, a frontier model's reading may stand in, and is labelled as that.
3. **The held-out split stays honest.** One in ten of a person's decisions is set aside, silently, and never trained on.
4. **Measurement moves up.** The benchmark and calibration are one small standing lane beside Activity and the runner
   (`build-order.md`). Its first stage is two weeks of measurement with no product code.
5. **The ceiling run.** Open-licensed pages may be read once by a frontier cloud model to learn what "good" is for
   each hand, under a cap of 25 USD that a script enforces: the run stops at the cap.

## Intent (the design)

A historian with pages in a hand no model has seen corrects about fifty lines and gets a reader that is useful on that
hand, on their own Mac, and that says word by word how far to trust it. They do not need a perfect transcript. They
need to know which seven lines in ten they can cite without looking, and which three to look at. Two figures say whether
Fichero does this, per hand:

- **lines-to-target**: how many corrected lines the hand needs before the page error falls to 10%, and to 5%;
- **trusted coverage**: the share of lines that can be accepted unseen while the accepted lines stay at 2% error or less.

Both are measured on whole pages as a run produces them (lines found, read, put in order), on pages no model, prompt
or threshold was tuned on. `source/readers.md` shows why the grain matters: 3 to 5% on given lines becomes 26 to 90% for
the page when columns interleave or lines are found in pieces, and the best local reader on an early-modern notarial
hand is at 44%. Until this works, names, statements, links and search are computed on noise.

The unsolved part is not reading as such (frontier cloud models read many hands well) but reading that is few-shot,
private, calibrated and at archive scale: a small local model that reaches the frontier's level on this hand after
fifty to four hundred corrected lines, and knows when it is wrong.

## Prior art (what we adopt)

- **CASP and the protein structure archive.** A fixed blind test, scored by one method, rerun each round, beside a
  growing public set of solved cases. The blind-hands benchmark is the first; corrections that people share are the
  second. A blind round is scored once, before anyone tunes on it.
- **Per-residue confidence.** A model that reports its own reliability changed daily practice more than its mean
  accuracy did. Calibration here is the standard kind: temperature scaling (Guo et al. 2017) or isotonic regression on
  held-out data, reported as expected calibration error with a reliability diagram, and used as a risk-coverage curve
  (selective prediction, El-Yaniv and Wiener 2010).
- **HTR practice.** Transkribus and eScriptorium train a model per hand from a few thousand lines; CATMuS and
  HTR-United publish hands with their licences; Kraken fine-tunes a base on a few hundred lines. We adopt per-hand
  adaptation on a strong base and measure it as a curve, which those tools do not report.
- **Splits by manuscript.** Lines of one page, and pages of one manuscript, share a hand, ink and scanner; a split by
  line flatters every model. HTR-United's guidance and `kg.teach.one-set-three-writers`
  (`kg/kg-confidence-and-provenance.md`) split by volume; so does this benchmark.

## What exists today (read 2026-11-21)

- **One rule for truth.** `models/segments.py` `made_by_a_person`, read by the bake-off, the evaluation and the person
  training set (`truth.rule.one-function` [PARTIAL]). The line-grain mark is not built (`truth.mark.on-a-reading`
  [GAP] #4947).
- **One scorer.** `training/evaluation.py` `score_page` and `judge_page`; `training.eval.one-scorer` [OK]. It scores
  given lines; the whole page is `readers.bakeoff.the-whole-page-is-measured` [GAP] (#6822).
- **Held-out pages are never trained on** when a person names them (`training.set.held-out-never-trained` [OK]);
  nothing picks them (`training.set.held-out-picked-across-folder` [GAP] #5441).
- **Confidences are stored and unused.** `llm/kraken_runtime.py` keeps `confidence` and `char_confidences` on each
  reading. Nothing fits them, shows them as bands or checks them against error (`distill.cascade.calibrated` [GAP]
  #5338; `source.recipe.certainty-is-calibrated` [GAP] #5894).
- **A training loop exists for Kraken readers** with an adopt-past-the-noise-band gate
  (`source.train.adopt-only-past-the-noise-band` [PARTIAL]); `recipes/train_offers.py` counts corrected lines.
- **No standing benchmark.** The "Measured" tables of `source/readers.md` are one review, three pages a script (one
  for the notarial hand), run once. Nothing reruns them.
- **A cloud cap exists per project** (`recipes/cloud_cap.py`, `recipes/runner.py`), and one egress gate
  (`llm/egress.py` `require_project_yes`). Neither knows a page's licence.

## The design

### The benchmark: blind hands

A **hand** is a set of pages in one writer's or one workshop's script, from manuscripts that can be told apart. The
benchmark is a versioned manifest of hands. Each hand has an **adaptation pool** (pages whose corrected lines a model
may learn from, up to 400 lines) and **held-out pages** (never seen by a model, a prompt or a threshold), and the two
never share a manuscript. Version 0 is built from what exists: the ten scripts of the open test corpus behind
`source/readers.md`, the non-commercial sets (scored locally, never sent anywhere), and two private hands that never
leave the Macs they are on. The manifest holds ids, licences and counts, never pixels or text; the private hands sit
in a second manifest that is not committed.

Per hand and per configuration (a base reader, an adaptation method), a round reports: the page error at 0, 50, 100,
200 and 400 corrected lines; lines-to-target at 10% and 5%; expected calibration error; the risk-coverage curve and
trusted coverage at 2%; seconds a page and peak memory. A new hand is added each quarter and scored once before anyone
tunes on it.

### Ground truth

The reference for a page is a person's word about it. Who the person is does not matter (the owner, a student, a
research assistant), and neither does what they started from: a model's transcription that a person corrected line by
line is a person's page once every line was corrected or confirmed. This is `source/ground-truth.md`'s one rule, with
no second rule here. Where no person has checked a held-out page, a frontier model's reading may be the reference; the
figure is then called *agreement*, never error, and is never averaged with person-checked figures. Every figure says
which kind of reference it had and how many lines of each.

### The held-out split

Two splits, both honest:

- **In the benchmark**, by manuscript, fixed in the manifest.
- **In a working project**, one in ten of a person's decisions is set aside as they work, silently: nothing in the app
  marks the page, asks or slows the person. For readings the draw is made per page, the first time a correction lands
  on it, because lines of one page share everything a model could overfit to; every line of a held-out page is held
  out. The draw is a hash of the page's id and a per-project salt, so it is stable, repeatable and cannot be steered.

Held-out pages are then cut in two by the same hash: a **fit half**, on which calibration and thresholds are fitted,
and a **report half**, which nothing is fitted on and every published figure comes from. No training set, name list,
prompt example or rescoring table is built from either half.

### Calibration

A reader gives a confidence per character. It is pooled to the word and the line, mapped to a probability by a fit on
the fit half (temperature scaling by default, isotonic where there are enough lines), and shown as four bands. "90%"
must be right nine times in ten on this hand; the calibration error is shown beside the fit, and a model whose error
is over the project's limit is not routed on (`distill.cascade.calibrated`). Agreement between two independent readers
(a line reader and a page-level vision model) is a second signal and is fitted the same way. The figure then travels:
it is question 2 of `kg/kg-confidence-and-provenance.md` ("is the page read right?") and caps what rests on the line
(`record.confidence.capped-by-the-reading`).

### The model, on our hardware

What a protein model exploited was that other sequences constrain this one. The archive's equivalent is redundancy:
the same scribe, the same legal formulae and the same few hundred names recur thousands of times. In order of cost:
per-hand adapters on the measured-best base; a hand index that starts a new hand from its nearest known hand rather
than from a script label; the corpus as context (rescoring a reader's candidates with the project's own accepted
formulae and names); two independent readers compared; and, on a large-memory Mac, a page-level vision student taught
by a frontier teacher's checked output. Which of these is worth building is what Stage 0 measures.

### The measurement lane

Stage 0 is two weeks and no product code: scripts that call the engine's own functions on a scratch library, and a
report. It answers three questions. (a) What do the learning curves look like at 0, 50, 100, 200 and 400 lines, for two
bases, on eight open hands and two private ones? (b) What is the ceiling: one frontier model on the open pages only,
under 25 USD? (c) Is what is already stored reliable: Kraken's line confidence against line error, and two-reader
agreement against error? **Go** if some configuration brings the notarial hand under 15% page error with 400 lines or
fewer, and confidence separates right lines from wrong (AUROC 0.85 or better). If not, the report says which of the two
failed, and Stage 2's order changes accordingly.

After Stage 0 the lane stands: the benchmark reruns on every adopted reader and every new base, as a job.

## Behaviours

### A. The benchmark

- `hands.bench.manifest-is-fixed-and-versioned` — **[GAP]** (#5441 → #6966) the benchmark is one manifest file with a
  version: per hand its script, period, licence, whether its pages may leave this Mac, the page ids of its adaptation
  pool and of its held-out pages, and the manuscript each page belongs to. A script refuses a manifest in which a
  manuscript has pages on both sides, a hand has no held-out page, or a page has no licence. The committed manifest
  lists open-licensed and non-commercial hands only; private hands are in a second manifest, read from outside the
  repository, and a guard refuses a commit that names one. A changed page list is a new version; figures of two
  versions are never shown in one column. *Test (to write):* test_blind_hands_manifest.py (a manuscript on both sides
  refuses; a missing licence refuses; a private id in the committed file refuses).
- `hands.bench.learning-curve-at-five-points` — **[GAP]** (#5441 → #6967) per hand and configuration the round
  measures the page error with 0, 50, 100, 200 and 400 corrected lines from the adaptation pool. The subsets are
  nested (the 50 are among the 100, and so on) and drawn by a seed kept in the report, so two configurations learn
  from the same lines. A hand whose pool holds fewer lines than a point reports that point as "not measured: N lines
  in the pool", never as a number. The error is the whole page as a run produces it, scored by the one scorer
  (`training.eval.one-scorer`); the figure on given lines is kept beside it, as
  `readers.bakeoff.the-whole-page-is-measured` rules for the bake-off. *Test (to write):* test_blind_hands_curve.py
  (nested subsets from one seed; a short pool gives "not measured"; a fake reader's known errors give the known curve).
- `hands.bench.round-report-is-one-table` — **[GAP]** (#5441 → #6967) a round writes one machine-readable file and
  one page a person reads: per hand and configuration the five points, lines-to-target, trusted coverage, calibration
  error, seconds a page, peak memory, the reference kind and the manifest version, with the commit and the seed. It
  holds no page text and no line picture of a hand that may not leave this Mac. *Test (to write):*
  test_blind_hands_report.py (the table's columns; a private hand's row carries figures and no text).
- `hands.bench.blind-round-is-scored-once` — **[GAP]** (#5441 → #6968) each quarter a hand is added whose held-out
  pages no configuration has been run on. Its first scoring is stamped blind with the commit it ran at; any later
  scoring of that hand is stamped "not blind", and only blind rows count in a published comparison. *Test (to
  write):* test_blind_round_once.py (a second scoring of the same hand and version is stamped not blind).
- `hands.bench.runs-as-a-standing-job` — **[GAP]** (#5441 → #6968) after Stage 0 a round is a job in the one job model
  (`ui/activity-pane.md`), started on purpose or when a reader is adopted or a base is added, resumable, with its
  report kept on the model's node beside its evaluations (`distill.eval.stored-on-the-model-node`). It never runs in a
  gate: it needs the corpus on the machine. *Test (to write):* test_blind_round_is_a_job.py.

### B. Ground truth for the benchmark

- `hands.truth.reference-is-a-persons-or-says-so` — **[GAP]** (#4947 → #6966) a held-out page's reference is the
  reading a person made or confirmed, by `made_by_a_person` and no other rule, whoever the person is and whatever
  text they started from: a model's transcription corrected by hand counts once every line of the page was corrected
  or confirmed (`truth.mark.on-a-reading`, `truth.mark.on-a-page`). Where no person checked the page, a frontier
  model's reading may be the reference; the row is labelled model-checked, its figure is called agreement
  (`distill.measure.against-people`), and it is never summed or averaged with person-checked rows. No figure depends
  on a paid expert. *Test (to write):* test_blind_hands_reference_kind.py (a model-checked page is never in a
  person-checked mean; a half-corrected page is not person-checked).
- `hands.truth.every-figure-says-its-reference` — **[GAP]** (#4947 → #6966) every figure this spec defines carries
  the count of person-checked and of model-checked lines behind it, and a figure resting on fewer than 100 lines or
  two pages (the bake-off's own floor, `recipes/bakeoff.py` `MIN_LINES`, `MIN_PAGES`) is shown as "too few to say".

### C. The held-out split in a working project

- `hands.heldout.one-in-ten-silently` — **[GAP]** (#5441 → #6969) one in ten of a person's decisions is held out as
  they work (owner 2026-11-21: one in ten is chosen per page for readings, so a page's lines are never in both
  training and test; per decision for names, pairs and claims). For readings the unit is the page: the first time a correction lands on a page the engine draws from a
  hash of the page id and a per-project salt, and a page drawn held-out has every line held out, then and later.
  Nothing in the app marks it, asks about it or changes what the person can do with it. A page a person names as
  held out (`distill.eval.held-out-checked-pages`) stays so; a page any adopted model was already trained on is never
  drawn. This is the automatic picker `training.set.held-out-picked-across-folder` asks for, with the share ruled.
  *Test (to write):* test_held_out_one_in_ten.py (1,000 pages give 100 within the binomial band; the same page draws
  the same way twice; a trained-on page is never drawn; no response of a correction route says which way it fell).
- `hands.heldout.fit-half-and-report-half` — **[GAP]** (#5441 → #6969) held-out pages are cut in two by the same
  hash. Calibration, thresholds and the noise band are fitted on the fit half only; every figure shown or published
  comes from the report half only. With fewer than two pages in either half the figure is "too few to say".
  *Test (to write):* test_held_out_two_halves.py (a fit never reads a report-half page; a figure never reads a
  fit-half page).
- `hands.heldout.every-builder-refuses` — **[GAP]** (#5441 → #6969) every builder of something a model learns from
  refuses a held-out page: the Kraken and vision training sets (built, `training.set.held-out-never-trained`), the
  YOLO set, the rescoring tables of section F, prompt examples, and a set packed for another place. One function
  answers "is this page held out" and a guard finds no builder that does not call it. *Test (to write):*
  test_every_set_builder_refuses_held_out.py.

### D. The two figures

- `hands.metric.lines-to-target` — **[GAP]** (#5441 → #6967) lines-to-target is the smallest number of corrected
  lines at which the page error on the report half is at or under 10%, and the same for 5%, interpolated between the
  measured points; where 400 lines do not reach it the figure is "not reached at 400 (N%)". *Test (to write):*
  test_lines_to_target.py (a known curve gives the known figure; a flat curve gives "not reached").
- `hands.metric.trusted-coverage` — **[GAP]** (#5338 → #6970) trusted coverage is the largest share of the report
  half's lines, taken in order of confidence, whose pooled character error is 2% or less; the whole risk-coverage
  curve is kept beside it. A reader with no confidence has no trusted coverage, said as that. *Test (to write):*
  test_trusted_coverage.py (a confidence that ranks perfectly gives the share of lines under 2%; a random one gives
  nearly none).

A looping answer, an unreadable answer and a too-short answer are failures, not readings, by
`readers.vlm.answer-that-runs-on-is-not-read`, `readers.vlm.unreadable-answers-are-counted` and
`training.eval.not-read-is-not-100`; reading order is scored by `readers.page.order-is-scored`; time and memory beside
error by `readers.bakeoff.time-and-memory-beside-error`. Those lines are theirs and are built in their steps.

### E. Calibration

- `hands.calib.stored-confidence-is-measured` — **[GAP]** (#5894 → #6970) Stage 0 measures what is already stored,
  with no fit: for each hand, the line confidence a Kraken reader wrote against that line's error, and the agreement
  of two readers against error, each as AUROC (right against wrong lines at 10% line error), a ten-bin reliability
  table and a risk-coverage curve. This is the measurement `source.recipe.certainty-is-calibrated` asks for. *Test (to
  write):* test_stored_confidence_reliability.py (the maths on made-up lines).
- `hands.calib.fitted-per-hand-and-shown` — **[GAP]** (#5338 → #6971) a reader's character confidences are pooled to
  the word and the line and mapped to a probability by a fit on the fit half, per hand and reader (temperature
  scaling; isotonic from 500 lines up). The fit, its expected calibration error on the report half and its ten-bin
  table are kept with the reader's evaluation and shown on its card. A reading written after the fit carries the
  probability beside the raw figure, and a refit never rewrites a reading: it is a new mapping with its date. This is
  the fit `distill.cascade.calibrated` routes on. *Test (to write):* test_calibration_fit.py (an over-confident fake
  reader is brought within 0.03; the fit never reads the report half).
- `hands.calib.four-bands-in-the-reader` — **[GAP]** (#5338 → #6972) the Reader tints each word by one of four bands
  of calibrated probability (trusted, likely, unsure, not read), with the bands' bounds and this hand's calibration
  error in the legend; one key moves to the next unsure word and one to the previous; the tint is a layer that can be
  turned off and is never the only signal (a mark as well as a colour). A reader with no fit shows no bands and says
  why. *Test (to write):* ReaderConfidenceBandsTests.swift (band from probability; no fit, no tint; the next-unsure
  command's order).
- `hands.calib.agreement-of-two-readers` — **[GAP]** (#5894 → #6973) where a line reader and a page-level vision
  model both read a page, their agreement per line (aligned by the one scorer) is stored as a second signal and
  fitted as the first is; the two are combined only by a fit on the fit half, never by a constant. A reading for the
  same page, model and prompt is reused, never run again. *Test (to write):* test_two_reader_agreement.py.

### F. The reader that learns a hand

- `hands.adapter.per-hand-on-the-measured-base` — **[GAP]** (#5337 → #6974) a hand gets an adapter: the
  measured-best base for its script fine-tuned on the hand's corrected lines, trained on this Mac or another place
  (`compute.job.*`), measured on the report half and adopted only past the noise band
  (`source.train.adopt-only-past-the-noise-band`). Its card carries the base, the line count, the curve point it
  stands at and the calibration fit. *Test (to write):* test_hand_adapter_card.py.
- `hands.index.nearest-hand-starts-the-new-one` — **[GAP]** (#5341 → #6975) line pictures are embedded and a new
  hand starts from the adapter of the nearest known hand in the project (and, where shared, beyond it), not from its
  script label; the choice and its distance are on the reading's maker. The same vectors are
  `xcorpus.link.same-hand`'s. *Test (to write):* test_hand_index_start.py (two fake hands; a page nearer the second
  starts from the second's adapter).
- `hands.context.the-corpus-rescoring` — **[GAP]** (#5337 → #6975) a line reader's candidate readings are rescored
  with the project's own formulae and name list (`kg/project-gazetteer-and-names.md`), built only from text a person
  accepted and never from a held-out page; the rescored reading names the table's version, and the raw reading is
  kept. *Test (to write):* test_corpus_rescoring.py (a name on the list wins a tie; a held-out page adds nothing to
  the table).
- `hands.student.page-vision-on-a-large-mac` — **[GAP]** (#5337 → #6976) a page-level vision student (a 7B-class
  model with a low-rank adapter) is trained on a large-memory Mac from a frontier teacher's readings that a person
  or a check passed (`distill.licence.teacher-terms`), asked by the page, and measured on the benchmark as any
  configuration is. *Test (to write):* test_vision_student_on_the_benchmark.py.

### G. In the app

- `hands.app.train-offer-shows-the-curve` — **[GAP]** (#5440 → #6977) the Train offer says where the hand stands
  on its curve and what more lines should buy, from this hand's measured points or, before it has any, the nearest
  hand's: the count of corrected lines, the page error now, and the expected error after a named number more. An
  estimate is labelled as one. *Test (to write):* test_train_offer_curve.py.
- `hands.app.folder-says-its-trusted-share` — **[GAP]** (#5338 → #6977) a folder's Inspector says what share of its
  lines are in the trusted band at 2%, by reader; search matches an unsure word through its stored alternatives and
  marks the hit as resting on an unsure reading. *Test (to write):* test_trusted_share_of_a_folder.py.

The review queue ordered by what a correction would teach is `distill.queue.uncertainty-first` and is built in
`compute/distillation.md`'s order once `hands.calib.fitted-per-hand-and-shown` exists.

### H. Stage 0's fences

- `hands.stage0.no-product-code-scratch-only` — **[GAP]** (#5441 → #6966) Stage 0 adds scripts under
  `scripts/blind_hands/`, their tests and a report, and nothing else: no route, model, migration, recipe step or app
  file. Every script refuses to start unless the engine's base path is a fresh scratch directory it was given, so it
  can never open a person's library, and it calls the engine's own functions (the line finder, the readers, the one
  scorer), never a copy of them. *Test (to write):* test_blind_hands_refuses_a_real_library.py (no scratch path
  refuses; a path holding a library the script did not make refuses).
- `hands.ceiling.open-pages-only` — **[GAP]** (#5368 → #6978) the ceiling run sends a page to a cloud model only when
  its manifest row has an open licence and says the page may leave this Mac; a non-commercial or private hand refuses
  before any request is built, and the private manifest is never loaded by this script. The run goes through the one
  egress gate under a scratch project that said yes to the cloud. *Test (to write):* test_ceiling_open_pages_only.py
  (a private row and a non-commercial row each refuse with no request made).
- `hands.ceiling.cap-is-enforced-by-the-script` — **[GAP]** (#5368 → #6978) the ceiling run has a cap of 25 USD that
  the script enforces: before each request it prices the request from a committed price table (an unpriced model
  refuses), adds it to a ledger file, and stops before the request that would pass the cap, exiting with "stopped at
  the cap: N of M pages read". The ledger survives a restart and counts every earlier run, so a rerun cannot spend
  the cap twice; a page already read by the same model and prompt is reused, never sent again; the actual cost
  returned by the provider replaces the estimate in the ledger. No flag raises the cap: it is a constant changed by a
  commit. *Test (to write):* test_ceiling_cap_stops_the_run.py (the request that would pass the cap is not made; a
  second start with a full ledger makes none; an unpriced model refuses).
- `hands.stage0.go-rule-is-in-the-report` — **[GAP]** (#5441 → #6967) the Stage 0 report ends with the two tests and
  their answers: some configuration brings the notarial hand to under 15% page error with 400 lines or fewer; and
  confidence separates right lines from wrong at AUROC 0.85 or better. With both met it says go; otherwise it names
  the one that failed and the figure it reached. *Test (to write):* test_blind_hands_go_rule.py.

### I. Sharing what was learned

- `hands.share.adapters-by-consent` — **[GAP]** (#5343; owner 2026-11-21) trained per-hand adapters may be reused
  across projects: a project may publish a hand's adapter with its card, licence and curve, so a later project with a
  near hand starts further along its curve. Actual lines are shared only from openly licensed material; a corpus
  ruled local stays local.
- `hands.share.open-benchmark-and-board` — **[GAP]** (#5343; owner 2026-11-21) the open part of the benchmark and
  its board are published with the manifest version, the scorer and the blind stamps.

## Lines this spec amends (cited, not copied)

| Line | Spec | What changes |
|---|---|---|
| `truth.mark.on-a-reading` (#4947) | `source/ground-truth.md` | who may make truth is ruled: any person correcting as they work, over any starting text; the benchmark reads it (section B) |
| `training.set.held-out-picked-across-folder` (#5441) | `compute/training-and-evaluation.md` | the picker is ruled: one in ten, silently, by a hash; built as `hands.heldout.one-in-ten-silently` |
| `distill.cascade.calibrated` (#5338) | `compute/distillation.md` | keeps the routing rule; the fit, its error and the bands are `hands.calib.*` here, and no longer "later" |
| `source.recipe.certainty-is-calibrated` (#5894) | `source/models-chains-and-projects.md` | its measurement is `hands.calib.stored-confidence-is-measured`, Stage 0 |
| `readers.bakeoff.the-whole-page-is-measured` (#6822), `readers.page.order-is-scored` (#6865) | `source/readers.md` | unchanged; the benchmark's headline grain, built in that spec's Steps 2.3 and 3.3, which this lane needs by Stage 1 |
| `distill.measure.against-people` (#5337) | `compute/distillation.md` | unchanged; "agreement" where no person checked is the word used here |

## Build order

Stage 0 is measurement only and starts now, beside Activity and the runner. Stages 1 and 2 are product code, each step
25 files or fewer. A step that names a line of another spec in its text waits for that spec's step; it does not
rebuild it.

### Stage 0 — The measurement (two weeks, no product code)

#### Step 0.1 — The manifest, the reference rule and the scratch fence
- Behaviours: `hands.bench.manifest-is-fixed-and-versioned`, `hands.truth.reference-is-a-persons-or-says-so`, `hands.truth.every-figure-says-its-reference`, `hands.stage0.no-product-code-scratch-only`
- Tests: test_blind_hands_manifest.py, test_blind_hands_reference_kind.py, test_blind_hands_refuses_a_real_library.py
- Size: M

The manifest for version 0 (eight open hands; the two private ones in the uncommitted file), the split guard, the
loader that makes a scratch library from a hand's pages, and the refusal to run anywhere else. About 10 files, all under
`scripts/blind_hands/` and its tests.

#### Step 0.2 — Learning curves at 0, 50, 100, 200 and 400 lines, on whole pages; the report and the go rule
- Behaviours: `hands.bench.learning-curve-at-five-points`, `hands.bench.round-report-is-one-table`, `hands.metric.lines-to-target`, `hands.stage0.go-rule-is-in-the-report`
- Tests: test_blind_hands_curve.py, test_blind_hands_report.py, test_lines_to_target.py, test_blind_hands_go_rule.py
- Depends on: 0.1
- Size: M

Two bases (the measured-best line reader and a second), fine-tuned by the engine's own training calls at each point,
each scored on the hand's held-out pages as a run produces them. The whole-page figure is computed by the script from
the one scorer until `source/readers.md` Step 2.3 lands. Runs on the build Macs, not on a laptop. About 12 files.

#### Step 0.3 — How reliable the stored confidences are
- Behaviours: `hands.calib.stored-confidence-is-measured`, `hands.metric.trusted-coverage`
- Tests: test_stored_confidence_reliability.py, test_trusted_coverage.py
- Depends on: 0.1
- Size: S

One reliability table, one AUROC and one risk-coverage curve per hand, for Kraken's line confidence and for two-reader
agreement, from the readings Step 0.2 already made. About 6 files.

#### Step 0.4 — The ceiling: one frontier model on open pages, stopped at 25 USD
- Behaviours: `hands.ceiling.open-pages-only`, `hands.ceiling.cap-is-enforced-by-the-script`
- Tests: test_ceiling_open_pages_only.py, test_ceiling_cap_stops_the_run.py
- Depends on: 0.1
- Size: S

The price table, the ledger, the licence refusal, the reuse of a reading already made; the ceiling row joins the
report of Step 0.2. The tests run with a fake provider and spend nothing. About 7 files.

### Stage 1 — Calibration, fitted and shown (weeks 3 to 6)

#### Step 1.1 — One in ten held out, silently; two halves; every builder refuses
- Behaviours: `hands.heldout.one-in-ten-silently`, `hands.heldout.fit-half-and-report-half`, `hands.heldout.every-builder-refuses`
- Tests: test_held_out_one_in_ten.py, test_held_out_two_halves.py, test_every_set_builder_refuses_held_out.py, fichero-server/tests/unit/training/test_kraken_training_set.py
- Size: M

#### Step 1.2 — The fit per hand and reader, kept with the evaluation
- Behaviours: `hands.calib.fitted-per-hand-and-shown`
- Tests: test_calibration_fit.py, fichero-server/tests/unit/training/test_evaluation_job.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — Four bands in the Reader, and the next unsure word
- Behaviours: `hands.calib.four-bands-in-the-reader`
- Tests: ReaderConfidenceBandsTests.swift, test_reading_carries_its_probability.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — The round as a standing job; the blind round
- Behaviours: `hands.bench.runs-as-a-standing-job`, `hands.bench.blind-round-is-scored-once`
- Tests: test_blind_round_is_a_job.py, test_blind_round_once.py
- Depends on: 1.2
- Size: M

### Stage 2 — The reader that learns a hand (weeks 6 to 12; order set by Stage 0's report)

#### Step 2.1 — Per-hand adapters on the measured base
- Behaviours: `hands.adapter.per-hand-on-the-measured-base`
- Tests: test_hand_adapter_card.py, fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py
- Depends on: 1.2
- Size: M

#### Step 2.2 — The hand index, and the corpus as context
- Behaviours: `hands.index.nearest-hand-starts-the-new-one`, `hands.context.the-corpus-rescoring`
- Tests: test_hand_index_start.py, test_corpus_rescoring.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — Two readers compared
- Behaviours: `hands.calib.agreement-of-two-readers`
- Tests: test_two_reader_agreement.py
- Depends on: 1.2
- Size: M

#### Step 2.4 — The page-level vision student
- Behaviours: `hands.student.page-vision-on-a-large-mac`
- Tests: test_vision_student_on_the_benchmark.py, fichero-server/tests/unit/training/test_vision_lora_trainer.py
- Depends on: 2.3
- Size: M

#### Step 2.5 — The curve in the Train offer; a folder's trusted share
- Behaviours: `hands.app.train-offer-shows-the-curve`, `hands.app.folder-says-its-trusted-share`
- Tests: test_train_offer_curve.py, test_trusted_share_of_a_folder.py
- Depends on: 2.1
- Size: M

### Stage 3 — The open release (the quarter after)

#### Step 3.1 — Adapters are reused across projects; the open benchmark and board
- Behaviours: `hands.share.adapters-by-consent`, `hands.share.open-benchmark-and-board`
- Tests: test_adapter_sharing.py (to write), test_open_release_licence.py (to write)
- Depends on: 2.5
- Size: M

Per the owner's answer: adapters pool across projects; lines only from openly licensed material, and a corpus ruled
local is refused by the publish step; the open benchmark and board go out with the manifest version and the scorer.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Scripts (pytest, no engine) | y | the manifest guard, the curve maths, the two figures, the cap ledger, the licence refusal, the go rule | the Stage 0 files named above |
| Backend (pytest) | y | the one-in-ten draw, the two halves, every builder's refusal, the fit, the round as a job | the Stage 1 and 2 files named above |
| Pure rule (Swift) | y | band from probability; the next-unsure order; no fit, no tint | ReaderConfidenceBandsTests.swift (to write) |
| Perf (run on purpose) | y | a round on the corpus on a build Mac | with `readers.page.order-is-scored`'s corpus measure |
| MCP / CLI | n | no new tool; a round is a job and is read as one | — |

## Open questions for the owner

1. **Answered** (owner 2026-11-21): per page for readings; per decision for names, pairs and claims. **The unit of "one in ten" for readings.** This spec draws per page (every line of a drawn page is held out),
   because lines of one page leak into each other. The other reading is one corrected line in ten. Recommended: per
   page.
2. **Answered** (owner 2026-11-21): (b) adapters only, and lines only from openly licensed material. **What may be pooled across projects?** (a) Nothing; (b) adapters only, per consenting project; (c) lines too,
   where their licence is open. Recommended: (b) now and (c) for open-licensed material; a corpus ruled local stays
   local. Section I waits on this.
3. **The two private hands.** Their held-out pages need about 400 corrected lines each. Recommended: whoever is
   already correcting those pages; the benchmark takes what exists and says "too few to say" until then.
4. **Which frontier model for the ceiling?** One, named in the price table before the run. Recommended: the one the
   cloud bake-off (`recipes/bakeoff.py`) already ranks first on print.
