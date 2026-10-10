# Compute — Training, evaluating and choosing models — Design Spec (#5440)

> Milestone: remote-compute
> Manual: TBD — "Training your own model, and knowing whether it helped": Train a Model… on a
> folder; what is proposed from what you corrected; where it trains and what it costs; watching
> the run; the model's card and its error rate; comparing models on your own pages; choosing
> which model a step uses; what distilling means.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-10-10, from the wireframe
> the maintainer approved and the compute set.** This is the one spec for how a person trains,
> evaluates and chooses models. It turns the wireframe into behaviours and owns accuracy (CER and
> WER), error testing and the A/B (bake-off) that decides which model a recipe step uses. It builds
> on `compute/jobs-and-fine-tuning.md` (the job, the trainers, the landed card),
> `compute/distillation.md` (the teacher → student loop and the evaluation job),
> `compute/remote-compute.md`, `compute/targets-and-connection.md`, `compute/hpc-runner-acenet.md`,
> `ai/where-models-run.md`, `ai/local-runtimes.md` and `source/image-preparation.md`; it cites
> their behaviours and does not restate them. Claims about our code are **VERIFIED** (with a path).
> Figures that have not been measured say "to be measured".

## Intent

A researcher corrects lines, regions and names while reading. From those corrections Fichero
proposes what can be trained, says which pages will teach and which will be kept back to score the
result, names the base model and its error rate on those pages, shows where the training can run
and what each place costs, and sends nothing off the Mac until Train is pressed. While it trains,
Activity shows one row with the run's phases. When it lands, the model is a node under the
project's Models with an Inspector: its error rate on the held-out pages beside its base's, how it
was made, and what can be done with it. Every model, trained or downloaded, is judged by one scorer
on the same held-out pages; a comparison is a ranked table with cost and time beside accuracy; "Use
this" is an audited choice for a scope; a winner must beat the current choice by more than the
noise; and the person's corrections of the new model's output feed the next training.

## Prior art

- **Kraken** reports character and word accuracy on a validation set after every epoch and keeps
  the best epoch (`ketos train`, `ketos test`). Fichero fixes the schedule and epoch ceiling
  (`compute.tune.kraken-schedule-is-fixed`).
- **HTR-United / eScriptorium** publish CER and WER per model with the normalisation stated; a
  score without its normalisation is not comparable. Fichero's named policies
  (`distill.eval.cer-variants`) follow that.
- **Ultralytics** reports mAP50 and mAP50-95, with per-class precision and recall and a confusion
  matrix, on a validation split; Fichero adopts those figures for layout rather than invent a score.
- **spaCy** reports precision, recall and F1 per entity label; Create ML word taggers report the
  same. Fichero adopts those for names.
- **Distillation** practice (the student checked against people, not only against the teacher;
  dev and test sets kept apart; repeat and report the spread) is in `compute/distillation.md`
  "Best practice the loop enforces" (#5538). This spec does not restate it.
- **A/B discipline:** the same test set for every candidate, a stated noise band, a fixed tie-break
  order and a kept record. The project's ruling on Sergio's data is a noise band of 0.5 CER points
  (ruled 2026-10-03).

## What exists today (VERIFIED on disk 2026-10-10)

- **One scorer.** `fichero-server/src/fichero_server/workflows/transcription_accuracy.py`:
  `character_error_rate` under four named policies (`diplomatic`, `layout-insensitive` (default),
  `lenient`, `accent-blind`) with an optional abbreviation table (`with_expansions`; none shipped).
  Tested in `fichero-server/tests/unit/workflows/test_transcription_accuracy.py`. No WER there.
- **The evaluation job.** `fichero-server/src/fichero_server/training/evaluation.py`
  (`evaluate-models`, local model lane): candidates (Kraken readers on this Mac, and vision models
  through the local `omlx` provider only — a remote provider is refused in words) read the checked
  pass's lines on the held-out pages; each page and model scored under every policy by the one
  CER; a candidate that returned under a tenth of the reference's characters is "not read"
  (`READ_SHARE`), one that read under 80% of the pages is "not measured" (`MEASURED_SHARE`), and a
  sole measured candidate gets no winner (`no_winner_why`). Speed is pages an hour measured in the
  run. Scores are appended to the model's card and read back by
  `fichero-server/src/fichero_server/api/routes/evaluation.py` (`POST /api/evaluation/runs`,
  `GET /api/evaluation/runs/{id}`, `GET /api/evaluation/scores`). Tested in
  `fichero-server/tests/unit/training/test_evaluation_job.py` and
  `fichero-server/tests/unit/recipes/test_bakeoff_not_read.py`.
- **The bake-off.** `fichero-server/src/fichero_server/recipes/bakeoff.py`: the top three
  `read-a-line` readers by the rules' rank, plus Tesseract for print or typescript when its card has
  the language, scored by the evaluation job on the corrected sample pages (each page's newest pass a
  person made); readiness of 100 corrected lines on two pages, said before anything is pressed; a
  table ranked by the fixed order (accuracy in one-point bands from the best, then local, cheaper,
  faster, lower carbon, trainable, smaller, card id); kept in `recipe/bakeoffs/<id>.yaml`; `use_this`
  writes an override on the recipe for the project or a folder, with the reason in words, through the
  audited `project.save_setup`. Routes in
  `fichero-server/src/fichero_server/api/routes/system/recipes.py` (`/api/recipes/project/bakeoffs`,
  list, result, `/use`); CLI and MCP generated (`fichero_recipes_start_bakeoff`,
  `fichero_recipes_use_bakeoff_choice`). Tested in
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`. App:
  `fichero/fichero/Models/BakeoffStore.swift`, `fichero/fichero/Views/Onboarding/BakeoffSection.swift`
  (onboarding only), tested in `fichero/Tests/Unit/general/Models/BakeoffStoreTests.swift`.
- **The reasons A/B.** `fichero-server/src/fichero_server/training/reasons_ab.py`: answer-only
  against reasoning students on held-out checked pages; CER, a word edit distance (WER), seconds a
  line, errors on uncertain lines; a reasoning student is adopted only when its gain is beyond
  `NOISE_BAND = 0.005`; the verdict recorded on the cards. `POST /api/training/reasons-ab`. Tested in
  `fichero-server/tests/unit/training/test_distill_reasoning_to_spec.py`.
- **Training jobs.** `fichero-server/src/fichero_server/training/job.py` (`train-a-model` on Hugging
  Face Jobs: Kraken reader and vision LoRA; phases waiting → preparing → sending → submitted → queued
  → fetching → landing → done, or failed or cancelled; Stop cancels the Job there; the hourly price
  returned at start) and `fichero-server/src/fichero_server/training/local.py`
  (`train-on-this-mac`, Kraken reader only, CPU, gentle: holds while the Mac is in use, hot or on
  battery; resumes from `last.ckpt` without repeating an epoch). Requests in
  `fichero-server/src/fichero_server/models/compute_requests.py`: `held_out_ids` (never sent),
  `pages_may_leave` (false by default), `not_for_release` (true by default), base, epochs, rank,
  batch size, hardware flavour, time limit. Tested in
  `fichero-server/tests/unit/training/test_training_job.py` and
  `fichero-server/tests/unit/jobs/test_training_on_this_mac.py`.
- **The set.** `fichero-server/src/fichero_server/training/kraken_set.py` leaves held-out pages out
  and leaves out flagged lines (empty, null, rejected by a check), counted by flag; previewed by
  `GET /api/training/set` without sending. Tested in
  `fichero-server/tests/unit/training/test_kraken_training_set.py` and
  `fichero-server/tests/unit/training/test_set_excludes_flagged_lines.py`.
- **Landing and the node.** `fichero-server/src/fichero_server/training/landing.py`,
  `fichero-server/src/fichero_server/training/project_models.py` (the model inside the project's
  package; Make Global copies it and keeps `not_for_release`),
  `fichero-server/src/fichero_server/training/model_nodes.py` and
  `fichero-server/src/fichero_server/api/routes/training.py` (`GET /api/training/models`,
  `GET /api/training/model`, `POST /api/training/models/make-global`). App: the sidebar's
  **Training** node (`fichero/fichero/Views/Sidebar/Sections/SidebarTrainingNode.swift`,
  `fichero/fichero/Models/TrainedModelsStore.swift`) and the read-only
  `fichero/fichero/Views/Inspector/Model/ModelNodeInspector.swift` (provenance, held-out CER per
  policy, size, where it runs, licence, may-publish). Tested in
  `fichero-server/tests/unit/training/test_trained_model_nodes.py`,
  `fichero-server/tests/unit/training/test_models_live_in_the_project.py` and
  `fichero/Tests/Unit/general/Models/TrainedModelsStoreTests.swift`.
- **Activity.** A training job is a row with the graduation-cap icon
  (`fichero/fichero/Views/Activity/Monitor/ActivityMonitorModel.swift`, `engineKind` containing
  "train"); no phase words beyond the job's state.
- **YOLO.** The recipe's `find-regions` step runs a YOLO layout model
  (`fichero-server/src/fichero_server/recipes/regions.py`, #5525). No YOLO training, no region
  overlap scorer. (`runtime.yolo.none-yet` in `ai/local-runtimes.md` is now stale: see
  "Requests to other specs".)
- **Not built anywhere:** a Train a Model… sheet in the app (the training routes have no caller in
  the app; runs are by API, CLI and MCP); proposals from what was corrected; a hold-out picked by
  Fichero; the base's error rate shown before Train; a place comparison; other Macs or a provider's
  fine-tuning as places; a names tagger, a text LoRA, Kraken segmentation or YOLO training; WER in
  the evaluation job; per-character confusion, worst lines, error by hand or failure modes; a gold
  regression set; a bake-off run from a model's node or re-run when a model lands; Core ML conversion.

## The design

### Screen 1 — Train a Model… (a folder's context menu)

One sheet, in the engine's words, built from one `GET` plan before anything is pressed.

1. **What to train**, proposed from what the person corrected in the folder, each with its count:
   corrected lines → a Kraken reader; the same lines → a vision LoRA; corrected regions → YOLO
   layout; confirmed names → a names tagger (spaCy, or Create ML, #5556). A row below its minimum is
   greyed, with its count and how many more it needs (the bake-off's readiness sentence is the
   model). Only what the folder's corrections support is offered; nothing is invented.
2. **Which pages teach, and which are held out.** Fichero picks the held-out pages across the
   folder (stratified by hand, page kind and sub-folder where the project knows them; a stated share,
   at least two pages), never a page any candidate trained on, and lists them; the person can swap a
   page. Flagged lines are left out and counted by flag with why
   (`compute.tune.set-excludes-flagged-lines`). The three sets of #5538 (train, dev, test) are the
   held-out pages' two halves plus the training set; the sheet says which is which.
3. **The base model** the recipe picks (`source.recipe.picks-the-tuning-base`), and **its error rate
   on the held-out pages** (the evaluation job, run before Train on the base alone, so the person
   knows what the training must beat). "Not measured yet" with a Measure button when it has not run.
4. **Where it trains**, with the cost shown before Train (Screen 2); nothing leaves the Mac until
   Train is pressed; a **Not for release** badge whenever the folder's rights say the pages may not
   be released (the Sergio rule), carried onto the card.

### Screen 2 — Where it trains, compared

One table, every place a row, each row saying whether the job fits, estimated time, cost and what
leaves the Mac; a place that cannot run the job is greyed with why, never hidden
(`ai.where.never-dropped-silently`).

| Place | Fits | Time | Cost | Leaves the Mac |
| --- | --- | --- | --- | --- |
| This Mac (gentle) | Kraken, YOLO, spaCy, a small LoRA; by memory | slow, measured as it goes | free | nothing |
| The person's other Macs (an M4 with 16 GB, an M4 iMac with 24 GB), over Tailscale, when idle or on power | by that Mac's memory | to be measured | free | pages and the set, to a Mac the person owns |
| Hugging Face Jobs | any; GPU by flavour | estimate from measured runs | hourly price, read first (`compute.tune.hf-token-checked-first`) | pages, the set, the base |
| ACENET or any Slurm cluster | big runs | queue plus run | allocation hours (`compute.hpc.plan-before-send`) | as above, to the cluster |
| A provider's fine-tuning (OpenAI; Gemini on Vertex) | text; which accept images is TO CONFIRM | the provider's | the provider's price | pages and text; the model stays there |
| No training: call a provider (OpenRouter, Claude, Gemini) to read or to teach | always | per page | per call | every page read |

Ruled 2026-10-04: no training defaults to this Mac (`compute.tune.local-mlx-shown-never-default`);
this Mac is a row, with its time, never the default. The default row is the cheapest that fits,
by the rules of `compute.tune.where-cheapest-first`, and is explained in one sentence.

### Screen 3 — While it trains (Activity)

Activity shows **only the run**: one row, its phase in words — *set checked* → *sent* →
*training, epoch N of M* → *scored* → *back in the project* — with why it waits (queue, memory,
battery, the Mac in use), Stop at every phase, and a failure in words with the resume from the last
epoch. The model's own facts (its base, its set, its scores) are never in Activity: they belong to
the model's Inspector (`activity.jobs-are-a-tree`; Activity shows runs, Inspectors show things).

### Screen 4 — The model it made

A node under the project's Models in the sidebar, with an Inspector. The Inspector shows: its error
rate on the held-out pages **beside its base model's** on the same pages and policy; time, cost and
epochs; how it was made (pages, teacher, flagged lines left out by flag, settings, place; the card
of `distill.train.card-names-teacher`). Buttons, each one audited action: **Use it to read this
folder** (the bake-off's folder-scope override); **Compare on more pages** (an evaluation job on
named pages); **Make it available in every project** (`compute.model.make-global`); **Run it on the
Neural Engine** (a Core ML conversion, scored against the original on the held-out pages before it
replaces it, #5556).

### Screen 5 — The full flow

what you corrected (lines, regions, names, fields, documents and their kinds, normalised text,
statements) → what gets trained (Kraken reader, Kraken line finder, YOLO layout, vision LoRA, text
LoRA, names tagger, a provider's hosted fine-tune) → where (Screen 2, plus "no training: call a
provider") → what comes back (a Kraken model, YOLO weights, an MLX model, a spaCy or Create ML
model, all inside the project; or a model id that stays at the provider, where every call leaves the
Mac; plus the model's card) → checked, then used (scored on held-out pages; the bake-off; used by a
recipe step; small first and big when unsure; people correct its output) → those corrections feed
the next training.

### Screen 6 — Distilling, and where a model can run

Distilling is `compute/distillation.md`'s loop: a big teacher (a fine-tuned Qwen VL 32B on Hugging
Face or ACENET, or a provider model) reads many pages; its answers, and a thinking model's reasons,
train a small student; a person's corrections outrank the teacher; the student is checked against
both on held-out pages and adopted only within the step's bar; in use, the student reads every page
and the teacher only the pages it doubts. Each recipe step distils its own way (readers, names,
layout, fields, documents: the table in #5538). Restricted data trains but is never released.

Where a model can run is decided by its size against that machine's memory, before it starts:

| Machine | Runs |
| --- | --- |
| This 8 GB Mac | Kraken; YOLO (through Core ML); spaCy; Apple's models; a 3B vision model |
| 16 GB and 24 GB Macs | the above plus 7–8B |
| Hugging Face with vLLM | 32B and above |
| ACENET with vLLM offline | 32B–70B, in batches |
| A provider API | any, every call leaves the Mac |

A model too big for a machine is refused before it starts, naming where it does fit
(`compute.memory.too-big-refused-up-front`, `runtime.mlx.offer-a-way-to-fit`).

### Evaluation: one scorer, the right metric per kind

**Readers (lines and pages).** CER = character edits (insert, delete, substitute) over reference
characters; WER the same over words, each distinct word one symbol. Both by the one function and
under a named policy, never a second implementation. The policies, each named on every figure:

| Policy | Case | Punctuation | Accents | Whitespace and line breaks | Long s, u/v, i/j | Abbreviations |
| --- | --- | --- | --- | --- | --- | --- |
| `diplomatic` | counts | counts | counts | counts | count | kept |
| `layout-insensitive` (default) | counts | counts | counts | collapsed | count | kept |
| `lenient` | folded | removed | counts | collapsed | count | kept |
| `accent-blind` | folded | removed | removed | collapsed | count | kept |
| `graphemic` (proposed) | folded | removed | removed | collapsed | ſ→s, u/v and i/j folded | kept |
| `expanded` (proposed) | as `layout-insensitive` | | | | | expanded by the project's table |

The first four are built; the last two are proposed (#5441). "Diplomatic" and "normalised" in the
manual mean `diplomatic` and `expanded`. Every table shows the default policy and offers the rest.

**Other kinds.** Layout: mAP50 and per-kind precision and recall at IoU 0.5 against corrected
regions. Names: precision, recall and F1 per kind of name against confirmed mentions (#5545).
Structured fields: exact match per field, and CER of the field's text. Document finding
(`finddocs.*`): boundary precision and recall against accepted boundaries, and the kind's accuracy.
Each is the kind's standard figure; none is invented here.

**Not read is not 100%.** A candidate that returned no text, or read fewer than the stated share of
pages, is "not read" or "not measured" with why, and never sums as a 100% error (#5531, built).

### Error testing: which errors, not only how many

Every evaluation keeps, beside its totals, the material to see what went wrong:

- **Confusions:** per-character substitution pairs (what was read as what), counted, with the top
  pairs shown; and the insertions and deletions by character.
- **Distributions:** CER per line and per page, as a histogram, so one bad page is seen as one bad
  page and not as a mean.
- **Worst lines:** the lines with the most edits, shown with the line's picture beside the reference
  and the reading, diff-marked; opening one goes to the line in the segment editor.
- **By facet:** error by hand, period, script, page kind and sub-folder, where the project records
  them (`source.train.rows-keep-context`); a model is judged where it differs.
- **Failure modes,** each flagged on the line or page it hit: hallucinated text (a reading whose
  characters far exceed the reference's, or that matches nothing on the page), repetition loops
  (#5522), truncation (the reading stops short), skipped lines (a line with no reading), wrong
  reading order (lines read but out of order; scored by Kendall tau against the page's order).
- **Regression:** a gold set per project — person-checked pages the person marks (at least the
  bake-off's minimum) — that every new model is scored on before it can be chosen; a model worse
  than the current choice on the gold set by more than the tolerance is shown as worse and is not
  proposed. The tolerance is the project's noise band.
- **The noise band:** one number per project, in CER points, default 0.5 (the Sergio ruling); a
  difference smaller than it is not a win, and the table says "too close to call". The same band
  serves the bake-off's ranking bands, the reasons A/B and regression. Today the bake-off uses one
  point and the reasons A/B 0.5 (see "Contradictions").

### A/B testing (the bake-off) decides what a step uses

- **Candidates:** installed models, catalogue models not yet downloaded (named, not scored, until
  fetched), trained models, provider models, a student and its teacher — for the step's kind, from
  any place (`ai.where.bakeoff-scores-any-place`). All read the **same held-out pages**, scored by
  the **one scorer** under the same policy.
- **The table:** one row a candidate, ranked in the **fixed order** (accuracy in noise-band bands
  from the best, then local, cheaper, faster, lower carbon, trainable, smaller, card id), with cost
  per page and time per page beside accuracy, each figure marked measured or estimated with its
  basis; "not measured" rows with why; a winner only among measured rows.
- **A winner must beat the current choice** by more than the noise band; otherwise the current
  choice stays and the table says so. A sole measured candidate gets no winner.
- **Use this** writes one audited choice for a scope (the project or one folder) as an override on
  the recipe, with the reason in words, undoable; a later Use this for the same step and scope
  replaces it.
- **Kept:** the comparison is kept with its pages, candidates, policy and figures, listed and
  readable later, and can be re-run on the same pages.
- **Re-run when a model lands:** a landed or downloaded model of the step's kind is offered a re-run
  against the current choice on the kept pages; never run by itself unless the person chose
  automatic training in setup (`source.recipe.train-never-automatic`).
- **The reasons A/B:** answer-only against reasoning students, the same pages and scorer, with
  seconds a line and errors on uncertain lines beside CER and WER; adopted only beyond the band.

## Behaviors

### Proposing (Screen 1)

- `training.propose.from-corrections` — **[GAP]** (#5440) Train a Model… on a folder opens one sheet whose
  rows are what the folder's corrections support: corrected lines → Kraken reader and vision LoRA; corrected
  regions → YOLO layout; confirmed names → names tagger; each with its count. The plan comes from one engine
  `GET`; the app draws it (`compute.tune.start-sheet` is the sheet's home; this line is what fills it).
- `training.propose.greyed-until-enough` — **[GAP]** (#5536, #5440) a row below its kind's minimum is greyed
  with its count and how many more it needs, in the readiness sentence's form (`bakeoff.readiness`); it is
  offered again when there are enough.
- `training.propose.names-tagger` — **[GAP]** (#5536, #5556) the names row trains spaCy on confirmed mentions
  on this Mac or on Hugging Face, or a Create ML word tagger, and is scored by precision and recall per kind.
- `training.set.held-out-picked-across-folder` — **[GAP]** (#5441) Fichero picks the held-out pages across
  the folder — stratified by hand, page kind and sub-folder where known, at least two pages, a stated
  share — lists them on the sheet, lets the person swap one, and never picks a page any candidate trained
  on. Today the person names them (`distill.eval.held-out-checked-pages`).
- `training.set.held-out-never-trained` — **[OK]** (#5398) a held-out page is never written to the set nor
  sent. Built: `fichero-server/src/fichero_server/training/kraken_set.py`; tested in
  `fichero-server/tests/unit/training/test_kraken_training_set.py`
  (`test_held_out_pages_are_never_written`) and `fichero-server/tests/unit/training/test_evaluation_job.py`.
- `training.set.flagged-left-out-with-why` — **[PARTIAL]** (#5446) the sheet lists flagged lines left out,
  by flag, with why; the engine counts them (`compute.tune.set-excludes-flagged-lines`); the sheet is not
  built.
- `training.set.three-sets-named` — **[GAP]** (#5538) the sheet says which pages train, which are the dev
  set and which the test set, and the card records all three with who checked each.
- `training.propose.base-and-its-error` — **[GAP]** (#5441, #5440) the sheet names the base the recipe picks
  and its error rate on the held-out pages under the default policy, measured by the evaluation job on the
  base alone; "Not measured yet" with Measure until it has; a trained model's error is shown beside it later.

### Where it trains (Screen 2)

- `training.place.compared` — **[GAP]** (#5440) every place is a row with fits, time, cost and what leaves
  the Mac; a place that cannot run the job is greyed with why, never hidden; the default row is the cheapest
  that fits and says why in one sentence; this Mac is never the default
  (`compute.tune.local-mlx-shown-never-default`).
- `training.place.this-mac-gentle` — **[PARTIAL]** (#5397) training on this Mac is a row with its time;
  Kraken readers are built (`compute.tune.on-this-mac`); YOLO, spaCy and a small LoRA on this Mac are not.
- `training.place.other-macs` — **[GAP]** (#5238) the person's other Macs reached over Tailscale (an M4 with
  16 GB, an M4 iMac with 24 GB) are places, each with its measured memory, used when idle or on power;
  `compute/targets-and-connection.md` lists Linux machines and clusters and no Mac.
- `training.place.hf-priced-first` — **[PARTIAL]** (#5398) the Hugging Face row shows the hardware's hourly
  price and an estimated time before Train; built: the price is read at start
  (`compute.job.costs-shown-where-known`); not shown before.
- `training.place.slurm` — **[GAP]** (#5642) ACENET or any Slurm cluster is a row with GPU hours against the
  allocation (`compute.hpc.plan-before-send`).
- `training.place.provider-fine-tune` — **[GAP]** (#5440) a provider's fine-tuning (OpenAI; Gemini on Vertex)
  is a row for text; which providers accept images is TO CONFIRM and the row says so; the result is a model
  id that stays at the provider and every call leaves the Mac, said on the row and the card.
- `training.place.nothing-leaves-until-train` — **[OK]** (#5398) nothing leaves the Mac until Train is
  pressed with the person's yes for these pages (`pages_may_leave`, false by default; `PagesMayNotLeave`).
  Built: `fichero-server/src/fichero_server/training/job.py`; tested in
  `fichero-server/tests/unit/training/test_training_job.py`.
- `training.place.cost-before-train` — **[GAP]** (#5440) the sheet's total (time, money, hours of allocation,
  greenhouse gas with its basis, `activity.ghg.estimate-with-its-basis`) is shown before Train, each figure
  measured, estimated or unknown.
- `training.place.not-for-release-badge` — **[PARTIAL]** (#5539) a folder whose rights forbid release shows
  a Not for release badge on the sheet and the card carries it; built: `not_for_release` (true by default),
  the Inspector's may-publish with reason, Make Global keeps it
  (`compute.model.never-publishable-stays-so`); the badge and reading the folder's rights are not.

### While it trains (Screen 3)

- `training.run.one-row-in-activity` — **[PARTIAL]** (#5439, #5398) Activity shows only the run: one row,
  its phase in words — set checked → sent → training, epoch N of M → scored → back in the project — with
  why it waits; built: the row with the training icon and the job's phases (waiting, preparing, sending,
  submitted, queued, fetching, landing, done); not built: epoch N of M, scored, the waits in words.
- `training.run.facts-in-inspector-not-activity` — **[GAP]** (#5439) the model's base, set, scores and
  settings are never shown in Activity; the row links to the model's node once it lands.
- `training.run.stop-at-every-phase` — **[OK]** (#5398, #5397) Stop works at every phase: a waiting job
  stops at once; a running Job is cancelled on Hugging Face; a training on this Mac stops at its next step.
  Built: `fichero-server/src/fichero_server/training/job.py` `request_cancel`,
  `fichero-server/src/fichero_server/training/local.py`; tested in
  `fichero-server/tests/unit/training/test_training_job.py` and
  `fichero-server/tests/unit/jobs/test_training_on_this_mac.py`.
- `training.run.failure-in-words-resumes` — **[PARTIAL]** (#5398) a failure is a sentence from a fixed list
  (`compute.job.fails-with-a-reason`) and the run resumes from the last epoch; built on this Mac
  (`last.ckpt`, no epoch repeated); not on Hugging Face or a cluster (`compute.tune.survives-the-time-limit`,
  `compute.hpc.resume-long-training`).

### The model it made (Screen 4)

- `training.model.node-under-models` — **[PARTIAL]** (#5439) the model is a node under the project's Models
  in the sidebar with an Inspector; built as a **Training** node (`source.model.node-in-sidebar`,
  `source.model.node-inspector`); the wireframe names the node Models (see "Contradictions").
- `training.model.error-beside-base` — **[GAP]** (#5439, #5441) the Inspector shows the model's held-out
  error rate beside its base's on the same pages and policy, and time, cost and epochs from the run; today
  it shows the model's CER per policy and the base's name only.
- `training.model.how-it-was-made` — **[PARTIAL]** (#5439, #5538) the Inspector shows pages, teacher,
  flagged lines left out by flag, settings and place; built: base, teacher, set, job, where and when; not:
  flags by kind, settings, the three sets.
- `training.model.use-for-this-folder` — **[PARTIAL]** (#5439) Use it to read this folder writes the
  bake-off's folder-scope override; built in the engine (`bakeoff.use_this`, scope `folder`), not from the
  node.
- `training.model.compare-on-more-pages` — **[PARTIAL]** (#5439) Compare on more pages starts an evaluation
  job on named pages against the current choice; built in the engine (`distill.eval.job`), not from the node.
- `training.model.make-global` — **[PARTIAL]** (#5539) Make it available in every project is the audited
  `training.make_model_global`; built in the engine (`compute.model.make-global`), not from the node.
- `training.model.neural-engine` — **[GAP]** (#5556) Run it on the Neural Engine converts to Core ML, scores
  the conversion against the original on the held-out pages, and replaces it only within the noise band.

### The flow and distilling (Screens 5 and 6)

- `training.flow.every-correction-is-data` — **[GAP]** (#5404) corrections of lines, regions, names, fields,
  documents and kinds, normalised text and statements are each a labelled example for their kind of model
  (`distill.scale.everyday-corrections-are-data`, `finddocs.corrections-teach`).
- `training.flow.what-comes-back` — **[PARTIAL]** (#5398, #5525) what comes back lands inside the project
  with its card: built for a Kraken reader and an MLX vision model
  (`compute.tune.model-comes-back-as-a-card`); not for YOLO weights, a spaCy or Create ML model, or a
  provider's model id.
- `training.flow.provider-model-stays-there` — **[GAP]** (#5440) a provider's fine-tuned model is a card
  whose weights are not here; its row and every call say the page leaves the Mac; it is never publishable
  by Fichero.
- `training.flow.corrections-feed-next` — **[GAP]** (#5404) corrections of a model's output join the next
  training round and the dev set, never the test set (#5538 rule 6), and the sheet's counts rise with them.
- `training.distil.per-step` — **[GAP]** (#5337) each recipe step distils its own way, by the table in
  `compute/distillation.md` (#5538): what the teacher produces, what the neutral check is, what the set
  holds and what scores it; a step with no row there cannot be distilled and says so.
- `training.distil.corrections-outrank-teacher` — **[GAP]** (#5337) where a person corrected a line the
  teacher read, the person's reading is the lesson and the teacher's is dropped from the set, counted.
- `training.distil.checked-against-both` — **[GAP]** (#5337) a student is scored against the person-checked
  pages and against the teacher on the same pages, both figures on the card; only the first is called
  accuracy (`distill.measure.against-people`).
- `training.fit.by-memory-before-start` — **[PARTIAL]** (#5641) where a model can run is decided by its
  resident size against the machine's memory before it starts; built for this Mac
  (`compute.memory.too-big-refused-up-front`); naming where it does fit (another Mac, Hugging Face, a
  cluster, a provider) is not built.
- `training.fit.restricted-trains-never-released` — **[OK]** (#5539) restricted data trains and the model
  is never publishable wherever it is copied. Built:
  `fichero-server/src/fichero_server/training/project_models.py` `make_global`; tested in
  `fichero-server/tests/unit/training/test_models_live_in_the_project.py`
  (`test_make_global_keeps_a_model_that_may_not_be_released_unreleasable`).

### Evaluation

- `training.eval.one-scorer` — **[OK]** (#5441) every reader score is the one `character_error_rate`
  under a named policy; the evaluation job, the bake-off and the reasons A/B call it and no second scorer
  exists. Built: `fichero-server/src/fichero_server/workflows/transcription_accuracy.py`,
  `fichero-server/src/fichero_server/training/evaluation.py` `score_page`; tested in
  `fichero-server/tests/unit/workflows/test_transcription_accuracy.py` and
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`
  (`test_every_candidate_is_scored_by_the_one_cer_on_the_same_pages`).
- `training.eval.policies-named` — **[PARTIAL]** (#5441) each figure names its policy; the four shipped
  policies are built; `graphemic` (long s, u/v, i/j folded) and `expanded` (the project's abbreviation
  table) are not, and no table ships.
- `training.eval.wer-beside-cer` — **[PARTIAL]** (#5545) WER is reported beside CER under the same policy by
  the one word edit distance; built in the reasons A/B only
  (`fichero-server/src/fichero_server/training/reasons_ab.py` `_word_edits`); not in the evaluation job,
  the bake-off or the card.
- `training.eval.not-read-is-not-100` — **[OK]** (#5531) a candidate that returned no text or too little is
  "not read" with why, one that read too few pages "not measured", and neither sums as 100% error or wins.
  Built: `fichero-server/src/fichero_server/training/evaluation.py` `judge_page`, `measured`,
  `no_winner_why`; tested in `fichero-server/tests/unit/recipes/test_bakeoff_not_read.py`.
- `training.eval.layout-overlap` — **[GAP]** (#5525) a layout model is scored by mAP50 and per-kind
  precision and recall at IoU 0.5 against corrected regions on held-out pages, by Ultralytics' own
  validation, never a scorer of ours (`prep.yolo.fine-tune-from-corrected-regions`).
- `training.eval.names-precision-recall` — **[GAP]** (#5545, #5536) a names model is scored by precision,
  recall and F1 per kind of name against confirmed mentions on held-out pages.
- `training.eval.fields-exact-and-cer` — **[GAP]** (#5545) a structured-fields model is scored by exact
  match per field and the CER of each field's text.
- `training.eval.boundaries` — **[GAP]** (#5550) a document-finding model is scored by boundary precision
  and recall against accepted boundaries, and its kinds by accuracy.
- `training.eval.per-facet` — **[GAP]** (#5441, #5538) scores are kept per hand, period, script, page kind
  and sub-folder where the project records them, and the table can be cut by any of them.

### Error testing

- `training.errors.confusions` — **[GAP]** (#5441) every evaluation keeps per-character substitution,
  insertion and deletion counts, and shows the top pairs (what was read as what).
- `training.errors.distributions` — **[GAP]** (#5441) CER per line and per page is kept and shown as a
  histogram beside the mean.
- `training.errors.worst-lines` — **[GAP]** (#5441) the worst lines are shown with the line's picture
  beside the reference and the reading, diff-marked; opening one goes to the line.
- `training.errors.failure-modes` — **[GAP]** (#5522, #5441) hallucinated text, repetition loops,
  truncation, skipped lines and wrong reading order are each detected by a stated rule and flagged on the
  line or page; counts per candidate are on the table.
- `training.regression.gold-set` — **[GAP]** (#5538) a project has a gold set of person-checked pages the
  person marks; every new model of a kind is scored on it before it can be chosen, and one worse than the
  current choice by more than the noise band is shown as worse and not proposed.
- `training.regression.noise-band-one-number` — **[PARTIAL]** (#4951, #5531) the project has one noise
  band in CER points, default 0.5 (ruled 2026-10-03), used by the bake-off's bands, the reasons A/B and
  regression, and shown on every table; built as two constants (bake-off one point; reasons A/B 0.005)
  and a request field on the reasons A/B.

### A/B testing (the bake-off)

- `training.ab.candidates-every-kind` — **[PARTIAL]** (#5533, #5442) the candidates are installed models,
  catalogue models (named, not scored, until fetched), trained models, provider models, a student and its
  teacher, for the step's kind, from any place; built: the top three Kraken readers by rule, Tesseract for
  print, out-of-the-box readers on this Mac, local MLX vision models; a remote provider is refused in words.
- `training.ab.same-pages-one-scorer` — **[OK]** (#4951) every candidate reads the same held-out pages and
  is scored by the one scorer under the same policy. Built:
  `fichero-server/src/fichero_server/recipes/bakeoff.py`; tested in
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`.
- `training.ab.cost-and-time-beside` — **[PARTIAL]** (#4951, #5582) each row shows cost per page and time
  per page beside accuracy, each marked measured or estimated with its basis; built: `cost_usd` with basis
  and pages an hour measured on this Mac; a remote place's time and price per page are not.
- `training.ab.fixed-order` — **[OK]** (#4951) the table is ranked in the fixed order: accuracy in bands
  from the best, then local, cheaper, faster, lower carbon, trainable, smaller, card id. Built:
  `fichero-server/src/fichero_server/recipes/bakeoff.py` `_rank`; tested in
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py` (`test_the_table_is_ranked_by_the_fixed_order`).
- `training.ab.use-this-audited` — **[OK]** (#4950) Use this writes one audited, undoable override for the
  project or one folder, with the reason in words, replacing an earlier one for the same step and scope.
  Built: `bakeoff.use_this` through `project.save_setup`; tested in
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`
  (`test_use_this_writes_an_audited_override_for_the_chosen_scope`).
- `training.ab.kept-and-readable` — **[OK]** (#4950) the comparison is kept with its pages, candidates and
  figures, listed and readable later. Built: `recipe/bakeoffs/<id>.yaml`,
  `GET /api/recipes/project/bakeoffs`; tested in `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`
  (`test_the_comparison_is_kept_and_readable_later`).
- `training.ab.sole-candidate-no-winner` — **[OK]** (#5531) a sole measured candidate gets no winner and
  the sentence says why. Built: `no_winner_why`; tested in
  `fichero-server/tests/unit/recipes/test_bakeoff_not_read.py`
  (`test_a_sole_measured_reader_gets_no_winner_and_the_sentence_says_why`).
- `training.ab.beats-current-by-noise-band` — **[GAP]** (#4951) a winner must beat the step's current
  choice by more than the noise band on the same pages; within it the current choice stays and the table
  says "too close to call"; today the best measured row is the winner whatever the current choice.
- `training.ab.rerun-when-a-model-lands` — **[GAP]** (#4951, #5439) when a model of a step's kind lands or
  is downloaded, a re-run of the kept comparison against the current choice is offered, from the model's
  node and from the step; it runs by itself only when the person chose automatic training in setup.
- `training.ab.from-anywhere` — **[GAP]** (#5439, #4950) the bake-off runs from a model's node, from a
  recipe step's Inspector and from a folder's Try Another Option…, not only from onboarding
  (`source.try.bakeoff-is-the-same-tool`).
- `training.ab.reasons` — **[PARTIAL]** (#4642) answer-only against reasoning students on the same pages
  and scorer, with seconds a line and errors on uncertain lines beside CER and WER, adopted only beyond
  the band; built in the engine (`distill.reasoning.ab-decides`); not in the one bake-off table nor the app.

## Test matrix

| Leg | This surface? | Pins | File |
| --- | --- | --- | --- |
| Backend (pytest) | y | one scorer, policies, not-read, fixed order, Use this, kept, no sole winner | `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`, `fichero-server/tests/unit/recipes/test_bakeoff_not_read.py`, `fichero-server/tests/unit/training/test_evaluation_job.py`, `fichero-server/tests/unit/workflows/test_transcription_accuracy.py` |
| Backend (pytest) | y | held-out never sent, consent, stop at every phase, resume without repeating an epoch, restricted stays unreleasable | `fichero-server/tests/unit/training/test_training_job.py`, `fichero-server/tests/unit/jobs/test_training_on_this_mac.py`, `fichero-server/tests/unit/training/test_models_live_in_the_project.py` |
| Backend (pytest), to write | y | WER beside CER; noise band one number; beats-current rule; confusions, distributions, worst lines, failure modes; gold set; hold-out picked; layout, names, fields and boundary scorers | `fichero-server/tests/unit/training/` (new, named for the behaviour) |
| App (Swift Testing) | y | the sheet from the plan; place table greyed with why; Activity phases; the node's buttons | `fichero/Tests/Unit/general/Models/` (new beside `BakeoffStoreTests.swift`, `TrainedModelsStoreTests.swift`) |
| Named machine | y | a tiny Kraken set trains on this Mac and on Hugging Face and lands with the same card shape; a YOLO fine-tune on corrected regions; a Core ML conversion scored against its original | the maintainer's run; recorded on the recipe (`compute.tune.proven-on-huggingface-first`) |
| MCP / CLI | y | start, status, bake-off, Use this, evaluation, through the generated tools | `fichero-mcp/tests/` |

## Open questions (each with a recommendation)

1. **One noise band or one per kind?** CER points fit readers; layout and names use precision and
   recall. *Recommend:* one band per project expressed in the kind's unit (0.5 CER points for
   readers; 1 point of F1 or mAP50 for the rest, to be measured), one setting, one sentence.
2. **Who picks the held-out pages?** Fichero's stratified pick against the person's own choice.
   *Recommend:* Fichero picks and shows; the person may swap; the pick is recorded on the card so a
   later comparison uses the same pages.
3. **Models or Training as the sidebar node's name?** The maintainer corrected 2026-10-04 that
   models do not generally live in the sidebar, and the wireframe says "under the project's Models".
   *Recommend:* keep one node, named Models, holding the project's trained models and their bases;
   downloaded models stay in Settings.
4. **Which providers' fine-tuning accepts images?** TO CONFIRM. *Recommend:* offer text fine-tuning
   only until confirmed; the row says so.
5. **Other Macs as a place.** Over Tailscale to the person's own Macs, when idle or on power.
   *Recommend:* treat a Mac as a target of kind `mac` in the one list
   (`compute.target.one-list`), reached by the same engine over the tailnet, with the
   `activity.throttle.power-heat-memory` rules on that Mac; file the issue.
6. **Core ML conversion of Kraken.** Whether Kraken's reader converts cleanly is to be measured.
   *Recommend:* YOLO first (#5556), Kraken when measured.
7. **Should the base's error rate run before Train by itself?** It costs an evaluation run.
   *Recommend:* yes on this Mac for Kraken (seconds); a Measure button for vision models.

## Requests to other specs (for the manager to route; nothing edited there from here)

- `ai/local-runtimes.md`: `runtime.yolo.none-yet` is stale since the `find-regions` step runs YOLO
  (`fichero-server/src/fichero_server/recipes/regions.py`, #5525); retag.
- `source/image-preparation.md`: `prep.yolo.regions-card` is at least PARTIAL for the same reason;
  `prep.yolo.fine-tune-from-corrected-regions` should point here for its scoring
  (`training.eval.layout-overlap`).
- `compute/distillation.md`: `distill.eval.cer-variants` should point to `training.eval.policies-named`
  for the two proposed policies and to `training.eval.wer-beside-cer`; the bake-off lines
  (`source.onboard.bakeoff*`) gain the beats-current rule (`training.ab.beats-current-by-noise-band`).
- `compute/jobs-and-fine-tuning.md`: `compute.tune.yolo-layout` says "on this Mac first (16 GB)";
  `compute.tune.local-mlx-shown-never-default` rules nothing trains on this Mac by default. Align
  the YOLO line with the ruling (offered, never default).
- `compute/targets-and-connection.md`: add a Mac as a target kind (`training.place.other-macs`).
- `source/models-chains-and-projects.md`: `source.model.node-actions` points here for the four buttons;
  the node's name (Models or Training) follows open question 3.
- `ui/activity-and-automatic-work.md`: a training row's phases in words
  (`training.run.one-row-in-activity`).

## Contradictions with existing specs (noted, not resolved here)

- **Noise band.** The ruling is 0.5 CER points; `recipes/bakeoff.py` bands by one point
  (`source.onboard.bakeoff-random-sample` says "within one CER point"); `reasons_ab.py` uses 0.005.
  This spec asks for one number (`training.regression.noise-band-one-number`).
- **Sidebar node.** `source.model.node-in-sidebar` (corrected 2026-10-04) names the node Training;
  the wireframe names it Models (open question 3).
- **YOLO on this Mac.** `compute.tune.yolo-layout` ("on this Mac first") against the 2026-10-04 ruling
  that nothing trains on this Mac by default.
- **YOLO exists.** `runtime.yolo.none-yet` [GAP] against the built `find-regions` step.
- **Held-out pages.** `distill.eval.held-out-checked-pages` has the person name them; the wireframe has
  Fichero pick them across the folder (`training.set.held-out-picked-across-folder`).

## Issues to file

1. Train a Model… sheet: proposals from the folder's corrections, hold-out picked across the folder,
   the base's error rate before Train, the place table, cost before Train, the Not for release badge
   (`training.propose.*`, `training.set.held-out-picked-across-folder`, `training.place.compared`,
   `training.place.cost-before-train`) — or widen #5440.
2. Error testing: confusions, distributions, worst lines with pictures, per-facet scores, failure-mode
   rules (`training.errors.*`, `training.eval.per-facet`) — or widen #5441.
3. One noise band per project, the beats-current rule, re-run when a model lands, the bake-off from
   anywhere (`training.regression.noise-band-one-number`, `training.ab.beats-current-by-noise-band`,
   `training.ab.rerun-when-a-model-lands`, `training.ab.from-anywhere`) — or widen #4951.
4. A gold regression set per project (`training.regression.gold-set`) — or widen #5538.
5. Other Macs over Tailscale as training and reading places (`training.place.other-macs`).
6. A provider's hosted fine-tuning as a place and a card whose weights stay there
   (`training.place.provider-fine-tune`, `training.flow.provider-model-stays-there`).
7. WER in the evaluation job, the bake-off and the card; the `graphemic` and `expanded` policies
   (`training.eval.wer-beside-cer`, `training.eval.policies-named`) — or widen #5545 and #5441.
8. Scorers for fields and document boundaries (`training.eval.fields-exact-and-cer`,
   `training.eval.boundaries`).
