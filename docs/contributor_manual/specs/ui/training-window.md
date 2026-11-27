# UI — The Training window — Design Spec (#5941)

> Milestone: training-window
> Manual: TBD — a "Training a recipe" section: where to see what each stage of a recipe has learned
> from; what its score is and how it has moved; how a small model compares with the large or paid
> one it would replace; how to distil, fine-tune and evaluate one stage or a whole recipe; and that
> a model changes only when you say so, and can be changed back.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — awaiting approval before tests/code.**
> Asked for 2026-11-26 (paraphrased); the choice of a window of its own is the manager's. This file
> is the SURFACE of the training loop and owns nothing of the loop itself. It cites, and repeats
> none of: the loop, its gate, the evaluation job and the bake-off (`../compute/distillation.md`,
> `distill.*`); the contract every step fills, its ground-truth reader, its measure and the switch
> rule (`../compute/correct-measure-distil.md`, `stepcontract.*`, `correct.*`, `measure.*`,
> `loopstate.*`); the start sheet, the places table, the scorers and the A/B table
> (`../compute/training-and-evaluation.md`, `training.*`; `../compute/jobs-and-fine-tuning.md`,
> `compute.tune.*`); what ground truth is (`../source/ground-truth.md`, `truth.*`); and the models
> themselves and their cards, which stay in the Models and Cluster window
> (`models-and-compute-window.md`, `models.*`). Ids here are `training-window.*`.
> Tags: [OK] built · [PARTIAL] exists in part / not wired · [GAP] not built · [BROKEN] seen fail.

## Intent

A researcher who has corrected three hundred lines wants to know four things and has nowhere to
ask them: what has this recipe learned from, how good is each stage now, would a small model on my
own Mac do as well as the paid one, and what happens if I say yes. The pieces of the answer exist
or are specified, in five specs and four places in the app: a count on a correction surface, a
sheet opened from a folder, a row in Models, a card's Inspector, a row in Activity.

The Training window is the one place those meet. Its sidebar is the project's recipes, each
recipe's stages, and the workflows that stand alone; each row says whether it can be trained and
what it last scored. Choosing a stage shows its ground truth, its measure as a number and a trend,
the current model beside every candidate on the same held-out examples, and three actions:
Distil, Fine-tune, Evaluate. When a candidate is good enough the window offers the switch; it is
never made silently and is always undoable. Choosing a recipe shows its stages in order, trains
them in order, and gives the score of the whole recipe from first stage to last.

Two rules hold it:

1. **One mechanism.** Every stage or workflow can be distilled or fine-tuned
   (`stepcontract.every-stage-and-workflow-is-trainable`), by one loop. The window draws the
   engine's one answer per step (`distill.loop.one-answer-per-step`) and computes no count, score,
   verdict or estimate itself. A reader, a segmenter, a names tagger and a canvas recognizer are
   the same kind of row.
2. **Models live in Models.** A trained model is a card in the Models and Cluster window, with
   its files, places and run settings. This window shows a stage's candidates and links to each
   card; it keeps no list of models of its own.

The surface is a new `Views/Training/**` (`TrainingWindow`, `TrainingSidebar`, `TrainingStagePane`,
`TrainingRecipePane`, the pure `TrainingWindowModel`), a window scene beside Activity's and
Models', and in the engine's `training` package the loop answer widened to a tree and the recipe
plan (two new modules).

## What exists today (read on disk 2026-11-26)

| Need | Where it is specified | State |
|---|---|---|
| A step's loop in one read: model, teacher runs, ground truth counted, jobs, candidates with verdicts | `distill.loop.one-answer-per-step` | gap; per recipe step only |
| Every step declares its unit, gestures, ground truth, held-out unit, measure, and whether it trains | `stepcontract.every-step-declares-six` | gap |
| Every stage or workflow trainable, one mechanism | `stepcontract.every-stage-and-workflow-is-trainable` | gap (added 2026-11-26) |
| One reader of a step's ground truth; corrections kept apart and attributed | `correct.truth.one-reader-per-step`, `correct.truth.apart-and-attributed` | gap; built for line readings |
| The error per step with its range; held-out drawn over the declared unit | `measure.error.per-step-hand-project`, `measure.error.range-is-stated`, `measure.heldout.unit-is-declared` | gap |
| Scorers: CER and WER, layout overlap, lines found, names, fields, boundaries | `training.eval.*` | CER and WER built; the rest gaps |
| Evaluations kept on the model's card | `distill.eval.stored-on-the-model-node` | partial |
| The start sheet, places compared, cost before training | `compute.tune.start-sheet`, `training.place.compared`, `training.place.cost-before-train` | gaps; Hugging Face and this Mac partly built |
| Whole, adapter or full fine-tune | `distill.train.lora-or-full` | adapter path built for one case |
| Candidates compared on the same pages, cost and time beside | `training.ab.*` | mostly built for readers |
| The one gate and its verdict in words; the bar against a hosted teacher | `distill.gate.one-rule`, `distill.adopt.within-bar` | gap; one reader path built |
| The switch: one audited, undoable action, only after the gate | `loopstate.switch-only-when-measured-better` | gap |
| The loop's UI: steps as rows, verbs, verdict | `models.loop.*`, `loopstate.models-row-shows-four` | gap; placed in Models, Recipe steps |
| A training run as one Activity row | `training.run.one-row-in-activity` | partial |
| The trained model as a node and a card | `training.model.node-under-models`, `models.trained.are-rows` | partial |
| A progress line on every correction surface | `correct.ui.progress-line` | gap |

What nothing specifies: a recipe trained as a whole, each stage fed by the trained stage before
it; the score of a whole recipe; one held-out set across a recipe's stages; a trend; a single
workflow's loop; and one window that shows these together.

## Prior art (what is adopted, what is done differently)

**Experiment trackers** (Weights & Biases, MLflow, TensorBoard): a run list, a metric as a number
and a line over runs, a table comparing runs on the same evaluation set. Adopted: the trend and
the comparison table. Different: no free-form metrics or dashboards; one measure per stage,
declared by the stage's contract, so two numbers on a row always mean the same thing.

**Hugging Face AutoTrain and model cards.** A task, a dataset, a base, an estimate, a card that
says what it was trained on and how it scored. Adopted: the card stays the record
(`distill.train.card-names-teacher`); the estimate comes before the start. Different: the dataset
is the project's own corrections, never uploaded until the person starts a run that needs it
(`training.place.nothing-leaves-until-train`).

**Transkribus and eScriptorium** (the field's own tools): training a handwriting model from
ground-truth pages, with a validation CER curve and a train/validation split chosen at start; in
eScriptorium, segmentation and recognition are trained separately on corrected pages. Adopted: CER
on held-out pages as the reading measure; segmenting and reading as separate stages each with its
own truth. Different: the split is the project's one held-out set, picked once across the folder
(`training.set.held-out-picked-across-folder`), so a later model is measured on pages no earlier
model learned from; and every stage, not only reading and layout, has the same loop.

**Distillation practice** (Hinton, Vinyals & Dean, "Distilling the Knowledge in a Neural Network",
2015; the loop in `../compute/distillation.md`): a large teacher labels, a small student learns,
and the student is judged against people, never against the teacher alone
(`distill.measure.against-people`). Adopted whole.

**Compound pipelines.** A pipeline's quality is not the product of its stages' scores: an error in
finding lines changes what the reader sees. The usual practice is to measure each stage twice, on
perfect input and on the stage before it, and the pipeline end to end. Adopted for a recipe as a
whole (below).

**Apple's own shape.** Xcode's Organizer and Activity's own window in this app: a source list, a
detail pane, an Inspector. Adopted: the window is Activity's shape
(`models.window.is-activitys-shape`).

## What the window shows

### The sidebar

Three sections, from the engine's tree: **Recipes** (each of the project's recipes, opening to its
stages in run order, a stage opening to its workflow's model-capable nodes where it has more than
one); **Workflows** (workflows that stand alone, each opening to its model-capable nodes); and
**Runs** (training and evaluation jobs in flight, which are Activity's rows). A row shows the
stage's name, its model now, one state, and its last score:

| State (from the engine's answer) | Means |
|---|---|
| Enough to train | the editor-corrected examples meet the kind's minimum and some are new since the last training |
| 40 of 100 corrected | below the minimum; the count and the need, in the stage's own unit |
| Up to date | trained on everything corrected so far |
| Candidate ready | a candidate passed the gate and is not in use |
| Training, Evaluating | a job is running; the phase in words |
| Cannot be trained | the contract says neither, with its reason |

### A stage

Four parts, top to bottom, and an Inspector.

- **Ground truth.** The examples an editor corrected, in the stage's unit, with how many are held
  out, how many are new since the last training, and a list: each row is one example with its
  picture or text, who corrected it and when, and whether it trains or is held out. A click opens
  the example where it is corrected (a line in the Reader, a region in the segment editor, a
  proposal on the canvas). Answers from people who are not editors are counted on one line beneath,
  "kept, not ground truth", and can be listed.
- **Measure.** The stage's own measure, from its contract: character and word error for reading;
  overlap of regions and of lines for segmenting; precision and recall for names, for document
  boundaries, for proposals and joins; exact match and character error for fields. One figure with
  its range and the date and number of held-out examples it was measured on, and a trend: one
  point per evaluation, a mark where the stage's model changed.
- **Teacher and students.** A table on the same held-out ground truth: the stage's current model
  first, then each candidate (distilled, fine-tuned, downloaded). Columns: score with range, the
  difference from the current model, speed, cost per unit, memory, where it can run, how it was
  made, and the gate's verdict in words. A row opens its card in Models.
- **Actions.** Distil…, Fine-tune…, Evaluate, each with its estimate before anything starts, and
  Switch… when a candidate may take over.

### A recipe

The recipe's stages as a row of columns in run order, each with its model, state and score, and
under them the **end score**: the recipe's final output measured against the editor's ground
truth on held-out pages run through every stage. Each stage shows two figures: its score on
editor-corrected input, and its score on the output of the stage before it; the gap between them
is what the earlier stages cost it. Train Recipe… plans the stages in order.

## What the person sees

- **Where it opens.** Window › Training; Train… on a recipe, a stage or a workflow anywhere it has
  a menu; the progress line on a correction surface; a training row in Activity; Recipe steps in
  Models. Each opens the window on that row.
- **Empty.** With no project open, the window says to open one. A project with no recipe lists its
  workflows. A stage with no corrections shows its ground truth as zero with a link to the surface
  where its output is corrected, and its measure as a dash, never a zero.
- **Loading.** The sidebar draws from the tree in one read; a stage's pane shows its counts at
  once and its list and trend as they arrive. A running job's row and the stage's state update
  from Activity's stream.
- **Error.** A stage whose answer cannot be read says so on its row and keeps the last answer,
  marked with its time. A job that failed shows Activity's sentence and Resume. An action that is
  not possible is disabled with its reason as help ("60 more lines needed", "this teacher's terms
  do not allow training on its output").
- **Acceptance.** In a project with a two-stage recipe (find lines, read) and forty pages an
  editor corrected: the window lists both stages as Enough to train; the reading stage shows its
  ground truth with a link that opens a line in the Reader, its character error with a range, and
  the current paid model in the table; Distil… shows an estimate and starts a run that appears in
  Activity; when it lands, the student is a row with its score, cost and speed beside the
  teacher's and a verdict; Switch… names what will change, switches, and Switch Back restores the
  teacher; Train Recipe… trains both stages in order and the end score is shown for both chains.

## Behaviors

Every test named below is owed (none is written). Engine tests go in `fichero-server/tests/unit/training/`,
Swift tests in `fichero/Tests/Unit/general/Views/Training/`; each is named as file, then function.

### A. The engine's tree and the recipe as a whole

- `training-window.tree.one-read` — **[GAP]** (#5941; engine) one read returns the project's training
  tree: recipes with their stages in run order, stand-alone workflows, and each model-capable node,
  every row carrying its loop answer (`distill.loop.one-answer-per-step`) and its contract
  (`stepcontract.every-step-declares-six`); a row that cannot be trained carries its reason. The
  read is bounded and paged. Test: `test_training_tree.py::test_a_recipe_and_a_lone_workflow_read_back_as_one_tree`.
- `training-window.tree.row-state-is-the-engines` — **[GAP]** (#5941; engine) each row's state is one of
  a fixed list worked out in the engine (enough to train, below the minimum with count and need,
  up to date, candidate ready, running with its phase, cannot be trained), from the kind's minimum
  (`training.propose.greyed-until-enough`) and editor-corrected examples only. Test:
  `test_training_tree.py::test_thirty_nine_corrected_of_forty_needed_is_below_the_minimum`.
- `training-window.truth.editors-only` — **[GAP]** (#5404, #5941; engine) the ground truth a stage
  trains on and is measured against is the answers of the project's named editors; other people's
  answers are returned beside it, counted, with who gave each, and are in no training set and no
  held-out set. Test: `test_editor_truth.py::test_a_non_editors_correction_is_listed_and_trains_nothing`.
- `training-window.recipe.plan-in-order` — **[GAP]** (#5941, #5440; engine) a recipe's training plan
  lists its trainable stages in run order, each with its method (distil, fine-tune), place and
  estimate, and the total; each stage's training input is the output of the stage before it as
  trained in this plan, or of that stage's current model where it has no candidate that passed the
  gate, and the plan says which. Test: `test_recipe_plan.py::test_the_reader_trains_on_lines_from_the_retrained_line_finder`.
- `training-window.recipe.runs-as-ordered-jobs` — **[GAP]** (#5941, #5440; engine) starting the plan
  starts one ordinary training job per stage, each waiting on the one before; a stage whose
  candidate fails the gate does not stop the plan, the next stage takes the current model's output
  and the plan's result says so; stopping the plan stops the running job and starts no more. Test:
  `test_recipe_plan.py::test_a_stage_that_fails_the_gate_is_skipped_and_named`.
- `training-window.recipe.one-held-out-set` — **[GAP]** (#5441; engine) within a recipe a held-out
  page is held out for every stage: no stage trains on a page another stage is measured on. Test:
  `test_recipe_held_out.py::test_a_page_held_out_for_reading_trains_no_line_finder`.
- `training-window.recipe.end-score` — **[GAP]** (#5441; engine) the recipe's end score is its final
  stage's measure on held-out pages run through every stage, for the chain in use and for the
  chain of passed candidates; each stage also answers its score on editor-corrected input and on
  the output of the stage before it. Each figure has its range. Test:
  `test_recipe_end_score.py::test_the_end_score_is_worse_than_the_reader_on_perfect_lines`.
- `training-window.trend.from-kept-evaluations` — **[GAP]** (#5441; engine) a stage's trend is its kept
  evaluations (`distill.eval.stored-on-the-model-node`) in time order on the same held-out set,
  each with the model, date, examples and range, and the points where the stage's model was
  switched; an evaluation on a different held-out set starts a new line and says so. Test:
  `test_training_trend.py::test_a_changed_held_out_set_starts_a_new_line`.

### B. The window and its sidebar

- `training-window.window.opens-on-the-row` — **[GAP]** (#5941; app) Window › Training opens one window
  per project, a split view in Activity's shape; Train… on a recipe, stage or workflow, a
  correction surface's progress line, a training row in Activity and Recipe steps in Models each
  open it with that row selected. Test:
  `TrainingWindowTests.swift::trainFromAStageOpensTheWindowOnThatStage`.
- `training-window.sidebar.recipes-stages-workflows` — **[GAP]** (#5941; app) the sidebar lists Recipes
  with their stages in run order, Workflows that stand alone, and Runs in flight, drawn from the
  tree and nothing else; a stage with several model-capable nodes opens to them. Test:
  `TrainingSidebarTests.swift::theSidebarIsTheTreeInRunOrder`.
- `training-window.sidebar.row-says-trainable-and-score` — **[GAP]** (#5941; app) each row shows the
  stage, its model now, its state in the engine's words, and its last score with range and date;
  a dash where nothing was measured; a badge where a candidate is ready. Test:
  `TrainingSidebarTests.swift::eachStateHasItsWordsAndUnmeasuredIsADash`.
- `training-window.one-mechanism` — **[GAP]** (#5941; app) the window has no code per kind of stage
  beyond the measure's label and unit, which come from the contract: a reader, a segmenter, a names
  tagger and a canvas recognizer draw from the same views, and a stage added to the registry
  appears with no change to the app. Test:
  `TrainingWindowTests.swift::aStageKindTheAppHasNeverSeenStillDraws`.

### C. A stage

- `training-window.stage.truth-listed-with-links` — **[GAP]** (#5404, #5941; app) the stage pane lists
  its ground truth: the count in the stage's unit, held out, new since the last training, and each
  example with its picture or text, its editor and date, and train or held out; a click opens the
  example on the surface where it is corrected; non-editors' answers are one line beneath, "kept,
  not ground truth", with their count. Test:
  `TrainingStagePaneTests.swift::aTruthRowOpensItsLineInTheReader`.
- `training-window.stage.measure-fits-the-stage` — **[GAP]** (#5441; app) the measure shown is the one
  the stage's contract declares, by the engine's scorer for it (`training.eval.one-scorer`,
  `training.eval.wer-beside-cer`, `training.eval.layout-overlap`, `training.eval.lines-found`,
  `training.eval.names-precision-recall`, `training.eval.boundaries`, `training.eval.fields-exact-and-cer`):
  one figure with its range (`measure.error.range-is-stated`), the examples and the date. A rate
  that is not an error is never shown as one (`measure.rates-are-not-errors`). Test:
  `TrainingStagePaneTests.swift::aSegmenterShowsOverlapAndAReaderShowsCharacterAndWordError`.
- `training-window.stage.trend` — **[GAP]** (#5441; app) the measure's trend is a line of the stage's
  evaluations with a mark at each switch; hovering a point names its model, date, examples and
  range; a new held-out set starts a new line with its reason. Test:
  `TrainingStagePaneTests.swift::theTrendMarksWhereTheModelChanged`.
- `training-window.stage.teacher-and-students` — **[GAP]** (#4951, #5941; app) one table shows the
  stage's current model and each candidate on the same held-out ground truth: score and range,
  difference from the current model, speed, cost per unit, memory, where it can run, how it was
  made, and the gate's verdict in words (`distill.gate.one-rule`); it is the A/B table's data and
  order (`training.ab.same-pages-one-scorer`, `training.ab.cost-and-time-beside`,
  `training.ab.fixed-order`); a candidate that lost stays, marked; a row opens its card in Models.
  Test: `TrainingStagePaneTests.swift::aCandidateRowShowsScoreCostSpeedAndVerdictBesideTheTeacher`.
- `training-window.stage.worst-first` — **[GAP]** (#5441; app) Show Errors lists the held-out examples
  the chosen model got most wrong, each with its picture, the editor's answer and the model's
  (`training.errors.worst-lines`), and opens one where it is corrected. Test:
  `TrainingStagePaneTests.swift::showErrorsListsTheWorstHeldOutExamplesFirst`.

### D. Actions and the switch

- `training-window.actions.distil-fine-tune-evaluate` — **[GAP]** (#5440, #5337; app) Distil…,
  Fine-tune… and Evaluate each open the existing start (`compute.tune.start-sheet`, the places
  compared, `training.place.compared`; whole, adapter or full, `distill.train.lora-or-full`; the
  evaluation job, `distill.eval.job`) filled for this stage, with its estimate of time, cost and
  what leaves the Mac before anything starts; an action that cannot run is disabled with its
  reason. Test: `TrainingActionsTests.swift::distilIsDisabledWithItsReasonBelowTheMinimum`.
- `training-window.actions.runs-are-activitys` — **[GAP]** (#5439; app) a started run is one Activity
  row (`training.run.one-row-in-activity`) on this Mac or a cluster through the existing runner;
  the window shows its phase on the stage and in Runs, links to it, and offers Activity's own Stop
  and Resume; it keeps no job state of its own. Test:
  `TrainingActionsTests.swift::aStartedRunIsShownFromActivitysRow`.
- `training-window.switch.offered-within-the-margin` — **[GAP]** (#4951, #5337; app) Switch… is offered
  on a candidate only when the gate passed: better than the current model past the noise band, or,
  against a paid or hosted teacher, within the project's bar of it (`distill.adopt.within-bar`);
  the sheet names the stage, both models, both scores, the scope, and what will change in cost and
  speed; otherwise the control's help is the verdict. Test:
  `TrainingSwitchTests.swift::switchIsOfferedOnlyWhenTheGatePassedAndSaysWhy`.
- `training-window.switch.never-silent-always-undoable` — **[GAP]** (#4951; app + engine) a stage's
  model changes only by the one audited action (`loopstate.switch-only-when-measured-better`); a
  switch made here needs the person's click; a switch made by automatic training, where a project
  chose that in setup, is announced in this window and in Activity when it happens; every switch
  is listed on the stage with who or what made it, when, and both scores, and Switch Back restores
  the earlier model, which is kept. Test:
  `test_switch_history.py::test_every_switch_is_listed_and_switch_back_restores_the_earlier_model`.

### E. A recipe in the window

- `training-window.recipe.pane` — **[GAP]** (#5941; app) a recipe shows its stages in run order, each
  with its model, state, its score on editor-corrected input and its score on the output of the
  stage before it, and the end score for the chain in use and for the chain of passed candidates.
  Test: `TrainingRecipePaneTests.swift::eachStageShowsBothScoresAndTheRecipeItsEndScore`.
- `training-window.recipe.train-recipe` — **[GAP]** (#5941, #5440; app) Train Recipe… shows the plan
  (order, method, place and estimate per stage, the total, which stage feeds which) and starts it;
  the stages' runs appear in order; when it ends the pane says which stages have a candidate that
  passed and offers one Switch… for those, listed one by one. Test:
  `TrainingRecipePaneTests.swift::thePlanNamesWhichStageFeedsWhich`.

### F. Other surfaces

- `training-window.models.recipe-steps-opens-training` — **[GAP]** (#6588, #5941; app) the Models and
  Cluster window keeps models, places and cards; its Recipe steps item shows each step's model and
  opens that step here, and the loop's rows, verbs and verdict (`models.loop.steps-are-rows`,
  `models.loop.verbs`, `models.loop.verdict-in-the-inspector`, `loopstate.models-row-shows-four`)
  are drawn in this window. Test:
  `TrainingWindowTests.swift::recipeStepsInModelsOpensTheStepInTraining`.
- `training-window.small-screens` — **[GAP]** (#5941; app) on iPad the window is the same split view;
  on iPhone a stage is a list (state, score, candidates with verdicts) with Evaluate and Switch…,
  and training starts are offered from the Mac or iPad only. Test:
  `TrainingWindowTests.swift::iPhoneOffersEvaluateAndSwitchAndNoTrainingStart`.
- `training-window.mcp-cli` — **[GAP]** (#5941; engine) the tree, a stage's truth list, its trend, the
  recipe plan and its start, the end score and the switch history are MCP tools and CLI commands
  generated from the same routes. Test:
  `test_training_tree.py::test_the_tree_route_is_in_the_generated_surfaces`.

## Build order

Order among milestones (manager default, owner to confirm): `training-window` follows `activity` and
the Models and Cluster window's first stages, since it shows their rows. Stage 1 is engine-only and
can start beside `correct-measure-distil.md` Stage 1, which it reads.

### Stage 1 — Engine: the tree, editor truth, the trend
#### Step 1.1 — The training tree and each row's state (#TBD)
- Behaviours: `training-window.tree.one-read`, `training-window.tree.row-state-is-the-engines`, `training-window.truth.editors-only`
- Tests: test_training_tree.py, test_editor_truth.py
- Size: M
#### Step 1.2 — The trend and the switch history (#TBD)
- Behaviours: `training-window.trend.from-kept-evaluations`, `training-window.switch.never-silent-always-undoable`
- Tests: test_training_trend.py, test_switch_history.py
- Size: M

### Stage 2 — The window and a stage
#### Step 2.1 — The window, the sidebar, one mechanism (#TBD)
- Behaviours: `training-window.window.opens-on-the-row`, `training-window.sidebar.recipes-stages-workflows`, `training-window.sidebar.row-says-trainable-and-score`, `training-window.one-mechanism`
- Tests: TrainingWindowTests.swift, TrainingSidebarTests.swift
- Depends on: 1.1
- Size: M
#### Step 2.2 — A stage: ground truth, measure, trend (#TBD)
- Behaviours: `training-window.stage.truth-listed-with-links`, `training-window.stage.measure-fits-the-stage`, `training-window.stage.trend`
- Tests: TrainingStagePaneTests.swift
- Depends on: 2.1, 1.2
- Size: M
#### Step 2.3 — Teacher and students; the worst examples (#TBD)
- Behaviours: `training-window.stage.teacher-and-students`, `training-window.stage.worst-first`
- Tests: TrainingStagePaneTests.swift
- Size: M

### Stage 3 — Actions and the switch
#### Step 3.1 — Distil, Fine-tune, Evaluate; runs in Activity (#TBD)
- Behaviours: `training-window.actions.distil-fine-tune-evaluate`, `training-window.actions.runs-are-activitys`
- Tests: TrainingActionsTests.swift
- Depends on: 2.3
- Size: M
#### Step 3.2 — The switch, offered and undoable; Models opens Training (#TBD)
- Behaviours: `training-window.switch.offered-within-the-margin`, `training-window.models.recipe-steps-opens-training`
- Tests: TrainingSwitchTests.swift, TrainingWindowTests.swift
- Depends on: 3.1, 1.2
- Size: M

### Stage 4 — A recipe as a whole
#### Step 4.1 — The plan in order, one held-out set, the end score (#TBD)
- Behaviours: `training-window.recipe.plan-in-order`, `training-window.recipe.runs-as-ordered-jobs`, `training-window.recipe.one-held-out-set`, `training-window.recipe.end-score`
- Tests: test_recipe_plan.py, test_recipe_held_out.py, test_recipe_end_score.py
- Depends on: 1.1
- Size: M
#### Step 4.2 — The recipe pane and Train Recipe (#TBD)
- Behaviours: `training-window.recipe.pane`, `training-window.recipe.train-recipe`
- Tests: TrainingRecipePaneTests.swift
- Depends on: 4.1, 3.2
- Size: M

### Stage 5 — Other surfaces
#### Step 5.1 — Small screens, MCP and the command line (#TBD)
- Behaviours: `training-window.small-screens`, `training-window.mcp-cli`
- Tests: TrainingWindowTests.swift, test_training_tree.py
- Depends on: 4.2
- Size: S

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | row states and their words, the measure's label by contract, the trend's marks, the switch sheet's wording | `Training*Tests.swift` |
| Availability (Swift) | y | Train… reachable from a recipe, a stage, a workflow, Activity and Models | `TrainingWindowTests.swift` |
| Backend (pytest) | y | the tree, editor truth, the recipe plan, one held-out set, the end score, the trend, the switch history | `tests/unit/training/` in the engine |
| MCP | y | tools map to routes | `test_training_tree.py` |
| CLI | y | commands wire the same routes | `test_training_tree.py` |
| Click-around (XCUITest, Mac) | y | the acceptance walk in "What the person sees" | `TrainingWindowUITests.swift` |
| iPhone (iOS) | y | a stage as a list; Evaluate and Switch | to write |
| iPad | y | the split view by touch | to write |
| Load (#4634) | y | the tree over fifty stages and a truth list of 100,000 examples, paged and timed | `test_training_tree_bounded.py` |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's "Training a recipe" section |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | generated from the routes |
| Scripter | CLI `--help` | y | generated from the routes |
| Reference | capability/endpoint reference | y | generated |

## Preview harness

`TrainingWindowPreview` beside `TrainingWindowModel` renders from a fixed tree with no engine: a
recipe of three stages (one enough to train, one with a candidate ready, one that cannot be
trained), a lone workflow, a reading stage's pane with ground truth, a trend with one switch and
a three-row table, and the recipe pane with both end scores. It is the source of the manual's
pictures.

## Accessibility identifiers

Each identifier is `training-window.` followed by: `sidebar.row.<id>`, `stage.truth`,
`stage.truth.row.<id>`, `stage.measure`, `stage.trend`, `stage.candidates`,
`stage.candidates.row.<id>`, `action.distil`, `action.fine-tune`, `action.evaluate`,
`action.switch`, `action.switch-back`, `action.show-errors`, `recipe.end-score`,
`recipe.train`. The trend is also a table for VoiceOver (date, model, score, range), and a
candidate row is spoken as a sentence: "Student, 4.1 percent character error, range 3.6 to 4.7,
0.3 points worse than the teacher, within the bar".

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `training-window.action.distil` | Distil… | Teach a small model from this stage's large model and your corrections | `training.window.action.distil` | [MISSING] |
| `training-window.action.fine-tune` | Fine-tune… | Train this stage's model on your corrections | `training.window.action.fine-tune` | [MISSING] |
| `training-window.action.evaluate` | Evaluate | Measure this stage's models on the examples set aside | `training.window.action.evaluate` | [MISSING] |
| `training-window.action.switch` | Switch… | Use this model for the stage; you can switch back | `training.window.action.switch` | [MISSING] |
| `training-window.action.switch-back` | Switch Back | Return to the model this stage used before | `training.window.action.switch-back` | [MISSING] |
| `training-window.action.show-errors` | Show Errors | List the examples this model got most wrong | `training.window.action.show-errors` | [MISSING] |
| `training-window.recipe.train` | Train Recipe… | Train every stage in order, each on the stage before it | `training.window.recipe.train` | [MISSING] |

## Decided by the manager, for the owner to confirm

The owner asked how a recipe is trained or distilled and where its error and ground truth are
shown, and left the choice of window to the manager. Each line below is a default taken so no
step waits; each is changed by one line here.

1. **A window of its own, named Training** *(manager's decision)*.
2. **The loop's rows move here from Models** *(manager default, owner to confirm)*: Models keeps
   models, places and cards; its Recipe steps item opens the step in Training. The `models.loop.*`
   ids and their tests stay and are drawn in this window.
3. **Ground truth is an editor's answer, for every stage** *(manager default, owner to confirm)*:
   the 2026-11-26 ruling, given for the canvas, is applied to the whole loop. An editor is the
   project's owner and anyone the owner marks as one. `correct.truth.*` in
   `../compute/correct-measure-distil.md` speaks of "a person's correction"; it is read here as an
   editor's, and those lines are for the owner to reword or leave.
4. **The switch margin is the project's bar** *(manager default, owner to confirm)*: against a paid
   or hosted teacher, within the bar already specified (`distill.adopt.within-bar`: one point of
   the stage's unit until the project sets its own); against a local model, better past the noise
   band. No new number is added here.
5. **Automatic training may switch, never silently** *(manager default, owner to confirm)*: where a
   project chose automatic training in setup, the general rule still lets a passed candidate take
   over; this window announces it and keeps it undoable. A switch from this window always needs a
   click.
6. **A recipe's plan does not stop at a stage that fails the gate** *(manager default, owner to
   confirm)*: the next stage trains on the current model's output and the result says so.
7. **Enough to train is the kind's existing minimum** *(manager default, owner to confirm)*: no
   per-stage threshold is added; the count is of editor-corrected examples.
8. **iPhone starts no training** *(manager default, owner to confirm)*: it shows scores and offers
   Evaluate and Switch.
9. **A new milestone, `training-window`** *(manager default, owner to confirm)*, after `activity`
   and the Models window's first stages; the line in `../build-order.md` is the owner's to place.
10. **No keyboard chord is assigned** *(manager default, owner to confirm)*: the Window menu item
    ships without one until the menus spec's uniqueness test picks it.

## Open questions for the owner

None open; the ten defaults above are the ones to confirm.
