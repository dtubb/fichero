# Correct, measure, distil — the contract every machine step fills — Design Spec (#5336, #5941)

> Milestone: read-any-hand
> Manual: TBD — a "Teaching Fichero as you work" section, written for a historian: that every fix you make (a line's
> reading, a name, a link, a yes or no on a passage) is kept as your word, apart from the machine's; that a small share
> is set aside to measure with and never taught from; what "N corrected, error now X% (range)" means; and that a
> better model takes over a step only when it measures better on your own material.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-22** (from the owner's direction of 2026-11-22; the owner
> approves). Nothing here is built unless tagged [OK] or [PARTIAL]. This file is CROSS-CUTTING and owns ONE thing: the
> contract a machine step fills so that its output can be corrected, measured and taught from, and the rules every
> correction surface and every loop display follows. It does NOT own, and only cites:
> the loop's six stages and the one gate (`compute/distillation.md`, `distill.*`); the scorers, the Train sheet and the
> bake-off (`compute/training-and-evaluation.md`, `training.*`); what ground truth is and how it is marked
> (`source/ground-truth.md`, `truth.*`); verdicts (`source/checking.md`, `source.check.*`); the held-out draw and
> calibration (`source/read-any-hand.md`, `hands.heldout.*`, `hands.calib.*`); the check set of decisions
> (`kg/reconstruct-the-record.md`, `record.check.*`); the sets and scorers for names, statements and links
> (`kg/kg-confidence-and-provenance.md`, `kg.teach.*`); the review surface (`ui/review-names-and-statements.md`,
> `review.*`); the Models window's loop rows (`ui/models-and-compute-window.md`, `models.loop.*`); and Activity
> (`ui/activity-pane.md`, `activity.*`). The milestone is `read-any-hand` because the shared core lands with the first
> flagship lane; each flagship spec holds its own steps (see "Steps in the flagship specs").
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built. Every non-[OK] line
> cites an issue.

## Intent (the design)

The flagship work rests on machine steps: reading a hand, finding names, linking mentions to one person, extracting
statements and relations, finding passages for a concept, grouping spellings. Each step is wrong some of the time. So
each step must be three things. **Correctable:** the historian fixes what the step produced, where they see it, in one
gesture. **Measured:** each fix is ground truth, kept apart from the machine's output and attributed to the person; a
share is held out, and from it comes an error rate per step, per hand and per project. **Distillable:** the same ground
truth teaches a small local model, and the small model takes over only when it measures better on the held-out share.
The historian sees one line while working ("212 corrected, error now 6.1% (4.8 to 7.6)") and one row per step in
Models and in Activity. A step that cannot say how it is corrected and measured cannot be added to a recipe.

## Prior art (what we adopt)

- **Active learning** (Settles, *Active Learning Literature Survey*; Prodigy; Label Studio): ask about the items the
  model is least sure of first, one decision a keystroke. We adopt uncertainty sampling for the queue, and keep a
  random held-out draw apart from it, because a queue chosen by the model is a biased sample and cannot measure.
- **Transkribus and eScriptorium:** correct in place on the page; ground truth is a status a person sets; a model is
  trained from it and its CER on a validation set is shown. We adopt all three, and add the gate
  (`distill.gate.one-rule`).
- **Knowledge distillation** (Hinton, Vinyals and Dean, 2015) and its use for labelling: a large teacher labels, a
  person corrects, a small student learns. Already this project's loop (`compute/distillation.md`).
- **Evaluation practice:** a test set never trains (Hastie, Tibshirani and Friedman, ch. 7); a rate is reported with
  an interval (Wilson's interval for a share; a bootstrap over pages for CER). CER and WER, precision, recall and F1,
  pairwise and B-cubed scores are each field's standard figure; none is invented here.
- **Photos' People album:** one face at a time, yes or no, undo. The model for the link and name queues
  (`kg.confidence.review-least-sure-and-most-used-first`).

What we do differently: one contract for every kind of step, so a new step is correctable and measured from its first
day; and figures that stay on the historian's machine.

## What exists today (read 2026-11-22, from the specs named above; nothing run)

- **The loop** is specified for every step in `compute/distillation.md` (the six stages, the one table, the one gate).
  Built for reading a line; not for names, statements, links or normalising.
- **Ground truth** has one rule (`truth.rule.one-function`, [PARTIAL]): built for a page's pass and a corrected line;
  the reading and region grains, and the sidebar folders, are not built.
- **Correcting a line** is built in the engine (`source.reading.correct-a-line`, [OK]). Name and statement verbs exist
  in part (`review.verbs-in-place`, [PARTIAL]); the keyboard flow and the progress line are not built
  (`review.keyboard-flow`, `review.progress-line`).
- **The held-out draw** (one in ten, silently, by a hash) is specified for pages (`hands.heldout.one-in-ten-silently`)
  and for decisions (`record.check.one-in-ten-held-out`); neither is built.
- **Scorers:** one CER and WER ([OK], `training.eval.one-scorer`). The names, statements and linking scorers are
  specified, not built (`kg.teach.names-scorer`, `kg.teach.statements-set-and-scorer`, `kg.teach.linking-set-and-scorer`).
- **The loop's display** is specified as one engine answer (`distill.loop.one-answer-per-step`) and the Models
  window's rows (`models.loop.steps-are-rows`); neither is built.
- **Missing everywhere:** a declared contract per step; one queue rule; the progress line with the error and its
  range; an error figure per step, per hand and per project in one shape; the loop in Activity; a rule that refuses a
  step with no contract; correction and measurement for concept passages and for spelling groups as steps.

## The design

### The step contract

Every machine step declares six things, as one typed record beside its entry in the job registry
(`source.recipe.jobs-are-a-registry`, `source/recipe-designer.md`):

1. **Output unit.** The smallest thing the step produces that can be right or wrong: a line's reading, a mention, a
   link between two mentions.
2. **Correction gestures and surface.** What the historian can do to one unit, each as one audited, undoable action,
   and where in the app they do it.
3. **Ground-truth store.** Where a person's correction is kept: always a record of its own with who and when, beside
   the machine's output and never over it.
4. **Held-out unit.** What the one-in-ten draw is made over: the page, for anything read from a page's pixels; the
   decision, for names, pairs, statements, marks and groupings.
5. **Error measure.** The figure, its scorer, and what it is cut by (hand, project, kind).
6. **Teachable.** Whether the step can be distilled from a teacher, trained from corrections, both, or neither with
   the reason in words.

### The one table

One row a flagship step. The teacher, the small model and the neutral check of each step stay in the table of
`compute/distillation.md`; this table adds what the historian does and what is measured.

| Step | Output unit | Correction gestures (surface) | Ground truth kept as | Held-out unit | Error measure | Distil or train |
| --- | --- | --- | --- | --- | --- | --- |
| Read handwriting | a line's reading | confirm the line as read; type a fix in place; mark not readable (the Reader and the segment editor, on the line) | a person's reading naming the one it corrects (`source.reading.correct-a-line`, `truth.mark.on-a-reading`) | the page, 1 in 10 (`hands.heldout.one-in-ten-silently`) | CER and WER by the one scorer, per hand and per project (`training.eval.one-scorer`) | both: a per-hand Kraken adapter trained from corrections (`hands.adapter.per-hand-on-the-measured-base`); a student distilled from a hosted reader |
| Find entities | a mention: a stretch and its kind | confirm; delete (not a name); mark its kind; fix its ends (the review surface and on the page, `review.marks-on-the-page`) | a person's ruling on the span, and the page marked checked for names (`kg.teach.page-is-checked-for-names`) | the decision, 1 in 10; a page checked through for names is drawn whole (`record.check.one-in-ten-held-out`) | precision, recall and F1 per kind (`kg.teach.names-scorer`); recall only from pages checked through | both: a tagger trained here (`kg.teach.spacy-trained-on-this-mac`); a hosted model as teacher |
| Link mentions to one person | a link between two mentions or two persons | accept (same); reject (different); cannot tell; cut an accepted link; undo (the stitch bench, the biography page, the Inspector) | the link's state with who and when (`people.record.person-decides`, `kg.confidence.decision-is-a-state`) | the decision, 1 in 10 | pairwise precision and recall and B-cubed (`record.measure.pairs-and-clusters`); beside them the accept rate and the undo rate | train: the matcher's weights and line fitted from decisions (`kg.teach.linking-set-and-scorer`); a hosted model may propose, never accept |
| Extract claims and relations | a statement (subject, relation, object) on its stretch | accept; reject; fix a part; open its line (the review surface and the biography page) | the statement's curation state, and a correction held as the person's (`source.check.correction-names-the-first`) | the decision, 1 in 10 | the share supported by their stretch, and precision per relation (`kg.teach.statements-set-and-scorer`, `record.measure.statements-stand-on-their-stretch`) | both: a small language model by adapter (`kg.teach.extractor-lora-on-this-mac`); a hosted model as teacher |
| Find concept passages | a candidate passage for one concept | yes; no; unsure (the concept sheet, on the passage, `concepts.marks.yes-no-unsure`) | the mark, by the person, on the concept's version | the mark, 1 in 10 (`concepts.marks.sharpen-the-search-locally`) | of held-out yes marks, the share found in the first hundred; beside it the yes-rate of what was offered | train: a small ranker fitted on this machine; no teacher, and no model proposes a concept (`concepts.never-proposed-by-a-model`) |
| Group spellings | a grouping of two written forms | accept the grouping; cut one form out; undo (the attestation sheet's Forms part, `terms.forms.variants-are-proposals`) | the grouping's state with who and when | the decision, 1 in 10 | pairwise precision and recall of proposed groupings against decided ones | both: the grouping method's line fitted from decisions; a normaliser by adapter where a hosted model taught (`compute/distillation.md`, "Normalise spelling") |
| Any new step | declared | declared | declared | declared | declared | declared, or "neither" with why |

Three notes on the table.

- **A rate of decisions is not an error.** The accept rate, the undo rate and the yes-rate count what the person did
  with what was offered. They are shown and named as rates. The error figure of a step comes only from held-out
  ground truth.
- **Unsure teaches nothing.** "Cannot tell" and "unsure" are kept and counted, are in no training set, and are scored
  as neither right nor wrong (`record.check.seeded-with-hard-cases`, `concepts.marks.yes-no-unsure`).
- **A step that cannot be trained is still corrected and measured.** Its row says "neither" and why, as Apple Vision's
  does in `compute/distillation.md`.

### The correction UI rules

Four rules hold on every surface where a step's output is corrected.

1. **One gesture.** A correction is one keystroke or one click where the unit allows it: confirm, reject, cut, yes,
   no, unsure, mark the kind. Only a fix that needs words (a reading, a name's text) needs typing, and then Return
   saves and moves on. The keys are the same on every surface: Return or Y confirms, N rejects, U is unsure or cannot
   tell, E edits, ⌘Z undoes, and the arrows move (`review.keyboard-flow`).
2. **In place, on the page.** The historian corrects where they are reading: the line in the Reader, the mark on the
   page, the stitch on the biography page, the passage on the concept sheet. No surface asks them to leave the page
   to fix what is on it. A queue surface always shows the unit's own picture or stretch.
3. **Least sure first.** Each step has one queue: the items whose answer the step is least sure of, weighted by how
   much rests on them, so each minute teaches most (`kg.confidence.review-least-sure-and-most-used-first`,
   `hands.calib.four-bands-in-the-reader`). The queue says how it is ordered and can be reordered. Whether a unit is
   held out never changes its place.
4. **Progress in one line.** The surface says "N corrected, error now X% (a to b)" for the step and the scope: N from
   the ground truth, X from the report half of the held-out share, the range at the app's one level. Below the minimum
   it says "N corrected, 12 of 50 needed to measure". It never says which units were held out.

### The loop's state, in Activity and in Models

The loop is the one of `compute/distillation.md`: (1) the big model reads; (2) the historian corrects; (3) a model is
trained or distilled; (4) it is measured on held-out material; (5) it takes over only when it measures better. The
engine's one answer per step (`distill.loop.one-answer-per-step`) carries its state, and two places show it.

- **Models** (the step's row, `models.loop.steps-are-rows`): the data so far, in the step's unit and by trust level;
  the last measurement (the figure, its range, how many held-out units, when, and per hand where the step has hands);
  whether a better model is ready, with the gate's verdict in words; and the switch rule in one sentence.
- **Activity:** each teach, train and measure job of a step is a row under one group named for the step, in the one
  job model (`activity.one-job-model`). When a candidate passes the gate, a standing line says "A better reader for
  this hand is ready" and opens the step's row. Nothing switches from Activity.

**The switch rule.** A model takes over a step only when the one gate passes on the report half
(`distill.gate.one-rule`): better than the current model by more than the project's noise band, or within the bar of
a hosted teacher. Then the person presses Use for This Step, or it switches by itself only where automatic training
was chosen in setup (`source.recipe.train-never-automatic`). The switch is one audited, undoable action for a scope
(the project, a folder, a hand). The earlier model is kept. With too few held-out units there is no verdict and no
switch.

Rulings in force that this design keeps, each owned elsewhere: a held-out unit never trains, fits or prompts
(`hands.heldout.every-builder-refuses`); a model is never run again on the same input (`activity.read.page-read-once`);
per-hand adapters may be reused across projects, and lines are shared only from openly licensed material
(`hands.share.adapters-by-consent`); a project's figures stay on its machine
(`people.quality.nothing-is-published-or-compared`).

### The step rule

A model-capable job cannot be added to the registry, and so to a recipe, without a filled contract. The engine refuses
it in words that name the missing part. A test walks the registry, as the model-chooser walk does
(`source/recipe-designer.md`), and fails for any model-capable job with none.

## Behaviours

Tests to write sit in `fichero-server/tests/unit/training/` unless a path says otherwise.

### A. The contract

- `stepcontract.every-step-declares-six` — **[GAP]** (#5941, #5337) every model-capable job in the job registry
  carries one typed contract with six parts: its output unit; its correction gestures, each naming the audited action
  and the surface; where its ground truth is kept; its held-out unit (page or decision); its error measure and the
  scorer that computes it; and whether it can be distilled, trained, both, or neither with the reason in words. One
  read returns every step's contract. *Test (to write):* test_step_contract.py (each of the six flagship steps reads
  back with six filled parts; "neither" without a reason is refused).
- `stepcontract.recipe-refuses-a-step-without-one` — **[GAP]** (#5941) a model-capable job with no contract, or with a
  part left empty, cannot be registered or added to a recipe: the engine refuses in words that name the job and the
  missing part, and a test walks the registry and fails for any such job. *Test (to write):*
  test_step_contract_walk.py (a planted job with no held-out unit is refused; the walk names it).
- `stepcontract.table-matches-the-registry` — **[GAP]** (#5941) the table in this spec and the registry agree: every
  row names a registered step and every model-capable step has a row, or the walk fails naming the difference.
  *Test (to write):* test_step_contract_walk.py.

### B. Ground truth, kept apart

- `correct.truth.apart-and-attributed` — **[GAP]** (#5404, #4947) for every step, a person's correction is a record of
  its own with the person, the time and the unit it corrects; the machine's output it corrects is left as it was; and
  no model call, check or run writes one (`truth.mark.never-by-a-model`). Built for a line's reading
  (`source.reading.correct-a-line`) and for verdicts (`source.check.verdict-recorded`); not for link decisions,
  concept marks or spelling groupings. *Test (to write):* test_corrections_are_apart.py (one correction per step: the
  machine's row is byte-equal after it; a machine actor's write is refused).
- `correct.truth.one-reader-per-step` — **[GAP]** (#5404, #5545) one function returns a step's ground truth for a
  project, cut by hand where the step has hands, with each unit's held-out half or none. Every scorer, every set
  builder, the queue and the progress line call it; it reads the states and audit rows a person's actions leave, and
  no second store (`record.check.is-read-from-decisions`, `truth.rule.one-function`). *Test (to write):*
  test_step_ground_truth_reader.py (six steps, one function; a builder that reads another path fails a guard).
- `correct.truth.unsure-teaches-nothing` — **[GAP]** (#5545, #4692) for every step, "cannot tell" and "unsure" are
  kept and counted, are in no training set and no fit, and are scored as neither right nor wrong. *Test (to write):*
  test_unsure_teaches_nothing.py.

### C. The correction UI rules

- `correct.ui.one-gesture` — **[GAP]** (#4794) on every correction surface a correction that needs no words is one
  keystroke or one click, and the same keys mean the same thing everywhere: Return or Y confirms, N rejects, U is
  unsure or cannot tell, E edits, ⌘Z undoes the last correction, the arrows move; after a correction the focus moves
  to the next item of the queue. Each is one audited action with undo. *Test (to write):* CorrectionKeysTests.swift
  (one key table; every correction surface reads it; no surface binds a second meaning).
- `correct.ui.in-place` — **[GAP]** (#4794, #5417) every unit a step produced can be corrected on the surface that
  shows it on the page: a line in the Reader, a name's mark on the page, a link where it is drawn, a passage on the
  concept sheet, a form in the Forms part. A queue row shows the unit's own picture or stretch, and opens its page in
  one gesture. *Test (to write):* CorrectionInPlaceTests.swift (each contract's surface offers each of its gestures).
- `correct.ui.least-sure-first` — **[GAP]** (#6280, #5338) each step has one queue from one engine function: items
  ordered by how unsure the step is (the calibrated probability nearest the step's line; the raw figure, labelled,
  where no fit exists), weighted by how many pages and statements rest on the item. The queue states its order and
  the person can change it. A unit's held-out status never changes its place, and an item resting on words read in
  the unsure band is held back and counted (`record.confidence.unsure-readings-seed-nothing`). *Test (to write):*
  test_correction_queue.py (planted confidences give the order; flipping held-out leaves it unchanged).
- `correct.ui.progress-line` — **[GAP]** (#6283, #5441) every correction surface shows one line for the step and the
  scope: "N corrected, error now X% (a to b)", where N is the count of ground-truth units, X the step's error on the
  report half and (a to b) its range. Below the minimum of held-out units it reads "N corrected, k of m needed to
  measure". The line updates as corrections land, and no response says which units were held out. *Test (to write):*
  test_progress_line.py; CorrectionProgressLineTests.swift (the three wordings from a stub answer).

### D. The measure

- `measure.heldout.unit-is-declared` — **[GAP]** (#5441, #5545) the held-out draw is made over the unit the step's
  contract declares, by the one hash and the one function: one in ten pages for a step that reads a page's pixels
  (`hands.heldout.one-in-ten-silently`), one in ten decisions for names, pairs, statements, marks and groupings
  (`record.check.one-in-ten-held-out`). A page checked through for names is drawn whole. *Test (to write):*
  test_held_out_unit_per_step.py (each step draws over its declared unit; the same unit draws the same way twice).
- `measure.error.per-step-hand-project` — **[GAP]** (#5441, #5545) one engine answer gives, for a step, its error by
  the contract's scorer on the report half: for the project, and per hand where the step has hands, each with its
  range, the number of held-out units behind it, the reference's kind (a person's, or a model's and then called
  agreement, `hands.truth.every-figure-says-its-reference`) and the date. Under the minimum the answer is "too few to
  say" with the count. *Test (to write):* test_step_error_answer.py (two hands, one under the minimum: one figure
  with a range, one "too few").
- `measure.error.range-is-stated` — **[GAP]** (#5441, #6763) every error figure carries a range at the app's one
  level: Wilson's interval for a share, a bootstrap over held-out pages for CER and WER. A figure is never shown
  without it. *Test (to write):* test_error_range.py (known counts give the known interval; a single page gives "too
  few to say").
- `measure.rates-are-not-errors` — **[GAP]** (#5545) the accept rate and the undo rate of links and the yes-rate of
  concept passages are computed from the person's decisions on what was offered, are labelled as rates, and are never
  shown as an error or used by the gate. *Test (to write):* test_rates_are_not_errors.py.
- `measure.stays-on-this-machine` — **[GAP]** (#5545) a project's error figures, rates and held-out sets are computed
  on the person's machine and are in no export, publish, shared file or telemetry; no surface ranks a project or a
  person by them. *Test (to write):* test_step_figures_in_no_export.py.

### E. The loop's state

- `loopstate.answer-carries-the-measure` — **[GAP]** (#5941) the engine's one answer per step
  (`distill.loop.one-answer-per-step`) also carries: the last measurement (`measure.error.per-step-hand-project`);
  whether a better model is ready, with the gate's verdict in words; and the switch rule as one sentence. Models and
  Activity read this answer and compute none of it. *Test (to write):* test_step_loop_answer.py (extended: a candidate
  that passed reads "ready"; one with too few held-out units reads "not measured").
- `loopstate.models-row-shows-four` — **[GAP]** (#5941, #6588) a step's row in Models shows four things from that
  answer: the data so far; the last measurement with its range and date; whether a better model is ready; and the
  switch rule. *Test (to write):* ModelLoopRowTests.swift (extended: the four parts from a stub answer).
- `loopstate.activity-groups-the-loop` — **[GAP]** (#5359, #5941) Activity shows each teach, train and measure job of
  a step as a row under one group named for the step, and a standing line when a candidate has passed the gate; the
  line opens the step's row in Models. Nothing switches a model from Activity. *Test (to write):*
  ActivityLoopGroupTests.swift; test_loop_jobs_are_grouped.py.
- `loopstate.switch-only-when-measured-better` — **[GAP]** (#4951, #5337) a trained or distilled model takes over a
  step, for a scope, only after the one gate passed on the report half (`distill.gate.one-rule`), and then by the
  person's Use for This Step, or by itself only where automatic training was chosen in setup. The switch is one
  audited, undoable action; the earlier model is kept; with no verdict there is no switch. *Test (to write):*
  test_switch_rule.py (a better, a too-close and an unmeasured candidate: only the first can be switched to; undo
  restores the earlier model).

## Steps in the flagship specs

Each flagship spec fills its steps' contract rows and builds its own surfaces, in its own build order and milestone:

| Milestone | Spec | Steps added 2026-11-22 |
| --- | --- | --- |
| `read-any-hand` | `source/read-any-hand.md` | Step 1.5 (correct a line in place, the unsure queue, the progress line), Step 2.6 (the better reader takes over when it measures better) |
| `reconstruct-the-record` | `kg/reconstruct-the-record.md` | Step 0.4 (the error per step with its range), Step 2.4 (names and statements corrected in one gesture) |
| `people-and-lives` | `kg/people-and-lives.md` | Step 3.4 (a link accepted, cut or undone where it is drawn; the progress line), Step 5.2 (the matcher refitted from decisions, behind the gate) |
| `concepts-and-terms` | `explore/concepts-and-terms.md` | Step 1.6 (spelling groups corrected and measured), Step 3.7 (the concept sheet's progress line) |

## Build order

The shared core, in the `read-any-hand` milestone. Engine before app. Each step is 25 files or fewer.

### Stage 1 — The contract and the ground truth

#### Step 1.1 — Every step declares its contract; a step without one is refused
- Behaviours: `stepcontract.every-step-declares-six`, `stepcontract.recipe-refuses-a-step-without-one`, `stepcontract.table-matches-the-registry`
- Tests: test_step_contract.py, test_step_contract_walk.py
- Size: M

#### Step 1.2 — One reader of a step's ground truth; corrections apart; unsure teaches nothing
- Behaviours: `correct.truth.apart-and-attributed`, `correct.truth.one-reader-per-step`, `correct.truth.unsure-teaches-nothing`
- Tests: test_corrections_are_apart.py, test_step_ground_truth_reader.py, test_unsure_teaches_nothing.py
- Depends on: 1.1
- Size: M

### Stage 2 — The measure

#### Step 2.1 — The held-out unit per step, the error per step, hand and project, with its range
- Behaviours: `measure.heldout.unit-is-declared`, `measure.error.per-step-hand-project`, `measure.error.range-is-stated`
- Tests: test_held_out_unit_per_step.py, test_step_error_answer.py, test_error_range.py
- Depends on: 1.2
- Size: M

Needs the draw of `source/read-any-hand.md` Step 1.1 or `kg/reconstruct-the-record.md` Step 0.2, whichever landed.

#### Step 2.2 — Rates are not errors; the figures stay on this machine
- Behaviours: `measure.rates-are-not-errors`, `measure.stays-on-this-machine`
- Tests: test_rates_are_not_errors.py, test_step_figures_in_no_export.py
- Depends on: 2.1
- Size: S

### Stage 3 — The correction rules

#### Step 3.1 — The queue and the progress line, in the engine
- Behaviours: `correct.ui.least-sure-first`, `correct.ui.progress-line`
- Tests: test_correction_queue.py, test_progress_line.py, CorrectionProgressLineTests.swift
- Depends on: 2.1
- Size: M

#### Step 3.2 — One key table, and every unit corrected in place
- Behaviours: `correct.ui.one-gesture`, `correct.ui.in-place`
- Tests: CorrectionKeysTests.swift, CorrectionInPlaceTests.swift
- Depends on: 3.1
- Size: M

### Stage 4 — The loop's state

#### Step 4.1 — The answer carries the measure; the switch rule
- Behaviours: `loopstate.answer-carries-the-measure`, `loopstate.switch-only-when-measured-better`
- Tests: test_step_loop_answer.py, test_switch_rule.py
- Depends on: 2.1
- Size: M

Needs `compute/distillation.md` Steps 2.2 and 2.3 (the one gate, the one answer per step).

#### Step 4.2 — The loop in Models and in Activity
- Behaviours: `loopstate.models-row-shows-four`, `loopstate.activity-groups-the-loop`
- Tests: ModelLoopRowTests.swift, ActivityLoopGroupTests.swift, test_loop_jobs_are_grouped.py
- Depends on: 4.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the one key table; the progress line's three wordings; the loop row's four parts | `fichero/Tests/Unit/general/` (to write: CorrectionKeysTests.swift, CorrectionProgressLineTests.swift) |
| Availability (Swift) | y | every contract's surface offers each of its gestures | CorrectionInPlaceTests.swift (to write) |
| Backend (pytest) | y | the contract and the walk; one ground-truth reader; the held-out unit; the error with its range; the queue; the switch rule | `fichero-server/tests/unit/training/` (to write, the files named above) |
| MCP | y | a step's contract, its error answer and its queue read back | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | the same three reads | `fichero-cli/tests/` (to write) |
| Click-around (XCUITest, Mac) | y | correct three queue items by key; the line counts up | to write |
| iPhone (iOS) | y | one card per queue item, the same gestures by tap | to write |
| iPad | y | as the Mac, with touch | to write |
| Load (#4634) | y | the queue and the error answer over 100,000 units, bounded and timed | `fichero-server/tests/perf/` (to write) |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's manual; Manual: TBD above |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/` (the three reads) |
| Scripter | CLI `--help` | y | `fichero-cli/` |
| Reference | capability/endpoint reference | y | generated |

## Preview harness

`CorrectionProgressLinePreview` renders the line's three wordings, and `ModelLoopRowPreview` a step's row in its
states (data only, measured, a better model ready, switched), each from stub answers.

## Accessibility identifiers

| Id | What it is |
|---|---|
| `correct.progress-line` | the progress line on a correction surface |
| `correct.queue.next`, `correct.queue.previous` | the queue's moves |
| `correct.queue.order` | the control that says and changes the queue's order |
| `models.loop.row.<step>.measure` | the last measurement on a step's row |
| `models.loop.row.<step>.ready` | the "better model ready" line |
| `activity.loop.group.<step>` | the step's group in Activity |

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `correct.progress-line` | "N corrected, error now X% (a to b)" | "Measured on the share of your corrections set aside. It never trains a model." | `correct.progress.line` | [MISSING] |
| `correct.queue.next` | Next Unsure | "Go to the next item Fichero is least sure of" | `correct.queue.next` | [MISSING] |
| `correct.queue.order` | Order | "Least sure first. Change the order." | `correct.queue.order` | [MISSING] |
| `models.loop.row.<step>.ready` | A Better Model Is Ready | "It measured better on your held-out material. Choose Use for This Step to switch." | `models.loop.ready` | [MISSING] |

## Rules set by the owner's answers

- **Entity recall.** One in ten per decision measures precision. Recall for names is measured apart: now and then a
  held-out page is drawn whole and checked for every name, so the names the step missed are counted.
- **No public board.** The open manifest stays as a test fixture and no score board is published
  (`hands.share.open-manifest-is-a-fixture-no-board` in `source/read-any-hand.md`).
- **One range level.** Ranges use one 90% level across the app, as `explore/concepts-and-terms.md` states.
- **Enough to show a figure.** A figure is shown only after 100 held-out decisions, or 5 held-out pages in each half.
  Below that the line says "not enough checked yet" and shows no number.
- **Milestone.** The shared core sits in the milestone `read-any-hand`; there is no new milestone.
