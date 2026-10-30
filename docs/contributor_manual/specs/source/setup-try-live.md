# Set Up tries live — every step tried on a real page, seen, edited and kept — Design Spec

> Milestone: setup-try-live (to create on approval; point its description here)
> Manual: TBD — the "Designing your recipe" chapter (`recipe-designer.md`) gains a section **"Trying a step on
> your pages"**: pick a page, run the step, what each step draws, how to correct it on the page, what a try
> costs and why the same page is never paid for twice, Compare, and Keep.
> **Status: DRAFT — awaiting the maintainer's rulings (open questions at the end).** Written from the
> maintainer's direction of 2026-10-30 (paraphrased): every Set Up step needs a way to test its models and
> settings live on real pages and SEE the output, not only compare scores; embed Preview with an item list in
> Set Up so the window grows and scrolls less; run the step on a page, see it drawn, edit it with the same
> Preview tools, change the model or settings and run again, step left and right through pages, keep what
> works. Facts read from the code of `spec/setup-try-live` at its base (origin/integration, 2026-10-30).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built · [BROKEN] the
code contradicts the intent · [PROPOSED] waits on a ruling. This spec does **not** replace
`recipe-designer.md` (the journey and the compare's measures), `../ui/preview-image-editing.md` (the image
tools), `segment-editor.md` (editing shapes), `line-editor.md` (editing a line's text) or
`models-chains-and-projects.md` (the try route, `source.onboard.stages.*`, `source.try.*`). It states the ONE
surface where they meet, cites each existing behaviour by its id (the owning spec stays the place to change
it) and adds `setup-try.*` lines only for what no spec said. Under "Exists", an id with no mark is [OK];
**(P)** PARTIAL, **(G)** GAP, **(B)** BROKEN.

## Intent (the design)

A person on a stage page of Set Up sees one of their own pages in Preview, with the project's pages listed
beside it. They press Try on This Page and the step runs on that page with the model and settings shown
beside it; the output is drawn on the page as the step's own kind of thing (lines with baselines, regions in
colours, a crop box, a reading beside the ink, a reviewer's proposals, names lit in the text). What is wrong
they fix there, with the tools Preview already has (drag a line, redraw a region, type the right word, move the
crop corner), and the fix is real: a row in the page's edit chain, a segment edit, a person's reading, each
audited and undoable, each a checked line or a corrected box the measures use from then on. They change the
model or a setting and press again; they press → and do it on the next page; they press Keep and the step's
choice is made. A try of a paid model shows its price on the button and counts against the project's cap. The
same model on the same input is never run twice: a second press shows what is kept, free, at once. Compare is
the same page with two or three candidates' tries on it, their measures beside; it is a mode of this one
Preview, not a window of its own.

It lives in Set Up (`fichero/fichero/Views/Onboarding/FirstRun/FirstRunWindow.swift` `windowSize`,
`Stages/SetupStagePage.swift`, `Stages/SetupStageSamples.swift`, `Stages/StageCompareWindow.swift`,
`Stages/StageCandidateChooser.swift`, `Stages/Showcase/`), the Preview it embeds
(`fichero/fichero/Views/Preview/DocumentCanvas.swift`, `ImageViewer/ZoomableImagePreviewMac*.swift`,
`ImageViewer/Regions/*`, `ImageEditor/*`, `Segments/CorrectThisLine.swift`) and the try engine
(`fichero-server/src/fichero_server/recipes/samples.py` `start_try`, `_run_one`, `read_result`;
`recipes/bakeoff.py`; `api/routes/system/recipes.py` `try_stage`, `stage_try_result`, `use_candidate_for_step`;
`api/routes/document/compare_readings.py` `try_compare`; the MCP tools `fichero_recipes_try_stage`,
`fichero_recipes_stage_try_result`, `fichero_recipes_bakeoff_result`). The logic (what a try is keyed on,
whether it is reused, what it costs, what it measures) is the engine's; Swift lays out and draws what is
served.

## Prior art / best practices (don't invent from scratch)

- **Transkribus and eScriptorium: run a model on one page, correct in place.** Both let a person run layout
  analysis or a recogniser on the open page, see the result drawn, and correct it with the same editor the
  final transcription uses; the correction is the ground truth. We adopt exactly this and add the model
  chooser beside the page, the measure on that page, and the rule that a page is never run twice with the
  same model.
- **Lightroom and Photos: the develop loop.** One image, the adjustments beside it, every change previewed on
  the picture, a before/after hold, the result kept as a non-destructive recipe you copy to the other frames.
  Prepare Images' try is that loop on the edit chain (`preview.edit.tool.*`, `prep.check.apply-correction-to-the-folder`).
- **Memoisation by content hash (Make, Bazel, DVC).** A step's output is keyed on its inputs and its
  parameters; the same key never runs twice. We key a try on the job, the model's identity and version, the
  settings and the input the step reads (the page's edited image, or the pass it works from).
- **What we do differently.** No separate "sandbox" copy to try on: the try's output is a pass of the
  page's own, marked as a try, so an edit on it is real and a later Start need not redo it. Agreement is not a
  check (`source.disagree.agreement-not-accuracy`); only a person's correction is.

## The words (one meaning each)

- **Try**: one run of one step, with one model and one set of settings, on one page. Its **key** is
  (job, card id and model version, settings hash, input hash). Its output is a **try pass** on the page.
- **Try pass**: a pass (`provenance_kind=model`) on the real page, carrying its key and `try: <stage>` in its
  metadata; never the page's working pass by itself. For Prepare Images the "pass" is a set of proposed
  rows on the edit chain (dashed until accepted).
- **Input**: what the step reads: the page's current edited image (the chain's `updated_at`, #6296) for
  the image and layout steps; the pass it works from (its id and version) for a step on lines or text.
- **Keep**: make the tried model and settings the step's choice (the existing `use-candidate`).
- **Compare**: two or three tries of different candidates on the same page, shown together with measures.

## The journey on a stage page

A stage page opens with the item list on the left, the selected page in Preview in the middle, the step's
settings on the right. The first sample page is selected. If the step has a kept try for it (section C) its
output is drawn; else the page is bare and the Try button reads with its price. The person presses Try, the
Preview says what the step is doing in words, the output lands drawn. The right column shows the measure on
this page where there is truth, and the words where there is not. The person corrects on the page, changes a
setting or the model and presses again (a new key, a new try pass beside the old one; the old one is still
listed under "Tried on this page"). → steps to the next page; the same step, the same settings, one press.
Compare toggles two or three candidates on the page. Keep makes the choice; Ready names it and the page it
was kept from.

## Behaviours (each → one pinning test)

### A. Layout: the window, the item list, the Preview, the settings beside it

**Exists.** Set Up is one fixed window of 820×600 with a 260-point step list (`FirstRunWindow.windowSize`,
`sidebarWidth`); a stage page is one scrolling column: the showcase picture, the example, who runs it, the
left-off rows, the questions, the candidate chooser and the samples with Compare on These Pages
(`SetupStagePage`, `source.onboard.stages.page-says-what-it-does` (P), `.page-asks-its-questions` (P),
`.samples-proposed` (P)); the compare opens a sheet per page (`StageCompareWindow`,
`source.onboard.stages.compare-results-per-model` (P)); Preview's canvas is one component dispatched by kind
(`preview.canvas.every-content-case-is-mounted` (P), `../ui/preview-surface.md`), with its region overlay and editing mode
(`source.editor.one-overlay` (P), `source.editor.segment-focus`), its line correction
(`source.reading.correct-a-line`), its image editor (`preview.edit.mounted-from-the-edits-facet` (P)) and
its stepping to the neighbour (`preview.swipe.shows-the-neighbour-at-once` (P)).

- `setup-try.window.larger-and-resizable` — **[GAP]** (#6052) Set Up opens at 1200×760 on a Mac whose screen allows
  it (else the largest that fits, never under 1040×680), is resizable, and remembers its size; the step list
  stays 260 wide; nothing is cut off at the minimum. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/SetupWindowLayoutTests.swift`
  (the size rule from a screen size; the minimum).
- `setup-try.layout.three-columns-on-a-stage-page` — **[GAP]** (#6052) a sampleable stage page is three columns
  beside the step list: the item list (200, 160 to 280), the Preview (the rest, never under 420) and the
  step's column (320, 280 to 400); the two dividers drag; a non-sampleable stage keeps its one column with
  its "cannot be tried" words (`source.try.every-job` (G)). *Test:* `SetupWindowLayoutTests` (the column
  widths at the default and the minimum).
- `setup-try.layout.settings-beside-the-page` — **[GAP]** (#6052) the step's column holds, top to bottom: the one
  model chooser (`designer.model.chooser-is-one-component` (G)), the step's questions
  (`source.onboard.stages.page-asks-its-questions` (P)), Try on This Page with its price, the step's words
  while it runs with Stop, the measure on this page (section E), "Tried on this page" (section C), Compare
  (section G) and Keep (section F); what it does and who runs it become one grey line under the title, and
  the animated showcase is shown only for a project with no pages. The column scrolls by itself; the page
  does not. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/SetupStageColumnTests.swift` (the order;
  the showcase hidden when a page is selected).
- `setup-try.items.project-pages-samples-first` — **[GAP]** (#5668) the item list is the project's pages in sidebar
  order (`source.recipe.pages-in-finder-order`), the sample pages pinned first with their why
  (`source.onboard.stages.samples-proposed` (P)), each row a thumbnail and the engine's name for the page;
  a filter switches between the samples and every page; the list is served by the engine (`GET
  /api/recipes/samples?all=true`, a page list with the sample marks), never built in Swift from the
  outline. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_items.py` (order, the samples first,
  the marks); `SetupItemListTests.swift` (renders as served).
- `setup-try.items.row-says-what-was-tried` — **[GAP]** (#5668) each row carries, from the engine, one dot per
  step that has a kept try on that page and a mark for a page with checked lines, so the person sees where
  truth is and where nothing has run; the dots are the try list's (section C), not a Swift scan. *Test:*
  `test_setup_try_items.py` (a try adds its dot; a correction adds the mark).
- `setup-try.items.arrows-step-pages` — **[GAP]** (#5462) ← and → (and ⌘[ / ⌘]) select the previous and next page
  in the list, through Preview's own stepping (`preview.swipe.shows-the-neighbour-at-once` (P)), warming the
  neighbours with the image the canvas will show; the step's column follows the selection at once and never
  holds the step. *Test:* `fichero/Tests/Unit/general/Views/Preview/SiblingStepTests.swift` (one more case:
  the Set Up host's selection moves in the same write).
- `setup-try.preview.is-the-one-preview` — **[GAP]** (#6296) the embedded pane is `DocumentCanvas` with the
  overlays, the segment editing mode, the line correction and the image editor Preview already has; no
  try-only canvas, overlay or editor is written; the showcase's `StagePageLayer` is not used for a real
  page. Pinned by an availability test that the same view types mount in Set Up and in the project
  window. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/SetupPreviewMountTests.swift`.
- `setup-try.preview.selection-is-the-windows` — **[GAP]** (#4941) the selected page and the selected segment in
  Set Up's Preview are the Set Up window's selection, so the Inspector verbs that act on a selection (Correct
  this line, Mark as Ground Truth, Accept a proposal) act on it; the project window's selection is untouched.
  *Test:* `SetupPreviewMountTests` (the focused values).

### B. Running a step on a page

**Exists.** `POST /api/recipes/stages/{stage}/try` takes `page_ids`, `candidates` and `cost_ok`, runs the
stage's own steps on a COPY of the pages in a scratch project and keeps one result per stage, replaced by the
next try (`samples.start_try`, `_run_one`, `source.onboard.stages.sample-run-reuses` (P),
`source.onboard.stages.samples-are-not-the-work` (P), `recipes-run.journey.try-is-not-the-work`); Read and
Find Lines go to the bake-off when the samples hold truth (`source.try.bakeoff-is-the-same-tool` (P)); the
try says what it is doing and waits for in words (`source.onboard.stages.try-progress-in-place` (P),
`source.onboard.stages.try-waiting-says-why` (P)); a cloud step is refused 402 without `cost_ok`; the try
reads the screen's saved choices (`source.onboard.stages.try-reads-the-screen` (P)); readers read the
original file, not the edited image (#6296, `preview.edit.model-steps-read-the-edited-image` (B)).

- `setup-try.run.one-page-one-candidate` — **[PARTIAL]** (#5668) Try on This Page is the same route with one page,
  one candidate (the chooser's) and the settings as on screen (`settings` on the body: the step's job
  answers and the node's config overrides, saved first as today); the answer names the try pass it made or
  reused. Built: the route and the body's `page_ids` and `candidates`; not built: `settings`, the pass.
  *Test:* `fichero-server/tests/unit/recipes/test_setup_try_live_run.py` (one page, one card, settings
  reach the workflow's override).
- `setup-try.run.lands-on-the-page-as-a-try-pass` — **[GAP]** (#4950) the try's output is written on the real page
  as a try pass of its own (`provenance_kind=model`, provider and model from the card, `metadata.try` with
  the stage and the key), beside the page's other passes and never over them
  (`source.try.never-over-existing` (P) is kept by being additive); for Prepare Images it is proposed rows on
  the edit chain, dashed until accepted (`prep.unsure-becomes-a-proposal`,
  `preview.edit.tool.proposal-is-the-tools-handles` (G)); no scratch copy is made. The page's working pass
  and drawn pass do not change by the try; Set Up's Preview draws the try pass because it asks for it. *Test:*
  `test_setup_try_live_run.py` (a try adds one pass and changes no existing row; the working pass is the
  same before and after; Prepare writes proposals only).
- `setup-try.run.reads-the-edited-image` — **[BROKEN]** (#6296) a try (and the run) reads the page's
  current edited image: the edit chain, then the Prepare Images renditions, the original only with neither;
  line pictures are cut from that image in that frame; Undo in Preview changes what the next try reads.
  Owned by `preview.edit.model-steps-read-the-edited-image` (B); cited here because the key (section C)
  depends on it. *Test:* `fichero-server/tests/unit/recipes/test_try_reads_the_edited_image_6296.py`.
- `setup-try.run.words-on-the-page` — **[PARTIAL]** (#5855) while a try runs the Preview shows a thin bar with the
  engine's words ("Finding lines", "Waiting for the model lane: …", `waiting_for`) and Stop; the output
  lands drawn as soon as the pass is written; a failure is one sentence in the same bar, never a blank.
  Built: the words and Stop under the samples; not built: on the page. *Test:*
  `fichero/Tests/Unit/general/Views/Onboarding/SetupStageTryStoreTests.swift` (the bar's text from the
  served states).
- `setup-try.run.needs-offer-the-step-before` — **[PARTIAL]** (#5668) a step that needs what an earlier step makes
  (Read needs lines; Review, Names, Translate need a reading) and finds none on this page says so in the
  step's column and offers one press that tries the earlier step on this page with its current choice,
  then this one (the engine's `needs` from `stages.py`); the refusal is never a bare 422. Built: the
  refusal in words for Read; not built: the offer. *Test:* `test_setup_try_live_run.py` (the answer names the
  step to try first; the chained press runs both).
- `setup-try.run.settings-are-the-steps-own` — **[GAP]** (#6052) a setting changed in the step's column is the
  step's own job answer or node config (`nodeconfig.model.same-list-as-settings`,
  `designer.step.names-its-workflow` (G)), saved with the recipe; there is no try-only settings store, so
  what was tried is what Start runs. *Test:* `test_setup_try_live_run.py` (the saved recipe carries the
  setting; `plan_start` reads it).
- `setup-try.run.try-is-watched-work` — **[OK]** a try is a person-started job ahead of bulk work on the
  lanes (`activity.throttle.try-ahead-of-bulk`), one page at a time; pinned by
  `fichero-server/tests/unit/recipes/test_stage_try_does_not_wait_or_hide_5806.py`.

### C. Kept and reused: the same model never runs twice on the same input

**Exists.** The bake-off's record is kept and readable later (`source.try.kept-and-rerunnable` (P)); a stage's
try result is one file per stage, replaced by the next try (`samples._write`, `read_result`); Start does not
redo what is done (`source.recipe.done-is-not-redone`); a reading records the model that made it
(`PassRead.provider`, `model`, `run_id`).

- `setup-try.reuse.key` — **[GAP]** (#4950) every try pass carries its key: the job, the card id and the model's
  version (a Kraken model's file hash, a cloud model's id as the provider names it, a YOLO weights hash,
  the enhancement suite's version), the hash of the settings that reach the step, and the input hash (the
  edited image's chain `updated_at` and rendition id for an image step; the pass id and version it works
  from for a step on lines or text). The key is the engine's one function (`recipes/try_key.py`), served
  on the pass. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_key.py` (two settings orders hash
  the same; a changed crop changes the key; a cloud model's version is its id).
- `setup-try.reuse.never-the-same-model-on-the-same-input` — **[GAP]** (#4950) (the maintainer's rule, 2026-10-30)
  a try whose key matches a try pass on the page runs nothing: the answer is that pass, `reused: true`, at
  once and free; there is no force flag on the route, the CLI or the tool. A failed try leaves no pass, so
  it may be tried again. *Test:* `test_setup_try_key.py` (second press returns the same pass id, the
  workflow is not called, no model call is priced).
- `setup-try.reuse.changed-input-is-a-new-try` — **[GAP]** (#4950) a correction on the page that changes a step's
  input (a crop moved, a line reshaped, a reading corrected) changes the key of every step downstream, so
  the next press runs those again and the old try passes stay listed; nothing upstream re-runs. *Test:*
  `test_setup_try_key.py` (a moved line re-keys Read, not Find Lines).
- `setup-try.reuse.listed-per-page` — **[GAP]** (#4950) `GET /api/recipes/stages/{stage}/try?page=<id>` lists that
  page's try passes for the stage (card, model version, settings in words, when, cost, measure, reused
  count), newest first; the step's column shows them under "Tried on this page" and clicking one draws it;
  the stage-wide result file goes. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_list.py`.
- `setup-try.reuse.compare-and-bakeoff-reuse-tries` — **[GAP]** (#4950) Compare (section G), the automatic compare
  (`designer.compare.runs-by-itself` (G)) and the bake-off's evaluation read a candidate's try pass when its
  key matches instead of reading the page again; a bake-off row says "from the try of <date>" in its
  provenance; one scorer measures both (`training.eval.one-scorer`). *Test:*
  `fichero-server/tests/unit/recipes/test_bakeoff_reuses_tries.py` (a candidate with a matching try pass
  makes no model call; its CER equals the try's).
- `setup-try.reuse.start-counts-a-try-as-done` — **[PROPOSED]** (open question 1) when Start runs a step on
  a page whose try pass has the same key as the step's kept choice, `done-is-not-redone` counts the page
  done and the try pass loses its `try` mark and becomes the step's pass; a try of another model stays
  beside as a try. Until ruled, Start runs the page again and the try pass stays a try.
- `setup-try.reuse.survives-the-pass-rules` — **[GAP]** (#4950) a try pass is ranked by the working-pass rules like
  any model pass (`rank_passes`), so a page with only a try pass reads it in the Reader and draws it in
  Preview with "a try of <model>, not yet the step's choice" in the pass's basis; marking it ground truth
  or correcting a line on it follows the ordinary rules. *Test:*
  `fichero-server/tests/unit/segments/test_try_pass_ranks.py`.

### D. Cost: the price first, against the budget, never twice

**Exists.** A cloud try says its cost and is refused without `cost_ok` (402, `samples.start_try`); what a
run really spent is read from its usage (`samples._spent`, `TryCost.measured`); the compare's cost is shown
first (`bakeoff.next_run`, `designer.compare.capped` (G)); the project and app cloud caps are specified, not
built (`training.cost.app-and-project-caps` (G), #5440); the Hugging Face cap holds Hugging Face offers
(`source.onboard.spend-cap` (P)).

- `setup-try.cost.price-on-the-button` — **[GAP]** (#6295) the Try button of a paid candidate reads its price for
  this one page before it is pressed ("Try on This Page · about $0.03"), from the engine's estimate served
  with the candidate (`GET /api/recipes/stages/{stage}/try/price?page=&candidate=`, the same pricer as the
  compare, `ai.where.one-pricer-every-place` (P)); pressing it is the yes (`cost_ok` sent); a local
  candidate's button reads "Try on This Page" and nothing else; a candidate whose price is unknown says
  "price not known" and asks on press. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_price.py`;
  `SetupStageTryStoreTests` (the button text from the served price).
- `setup-try.cost.counts-toward-the-cap` — **[GAP]** (#5440) a paid try spends from the project cloud cap
  (`training.cost.app-and-project-caps` (G)) like the compare; a try that would pass what is left is refused
  before it starts, naming the cap, what is spent and what this page would add, with Raise the cap… ;
  until the cap is built, the Hugging Face cap holds Hugging Face places and other providers are not
  capped, and the button says so once. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_capped.py`.
- `setup-try.cost.reuse-is-free-and-said` — **[GAP]** (#4950) a reused try's button reads "Show the try of <date> ·
  free" and the listed try carries what it cost when it ran; the page is never paid for twice for the same
  key. *Test:* `test_setup_try_key.py` (the price route answers 0 and `reused: true` for a matching key).
- `setup-try.cost.measured-after` — **[PARTIAL]** (#5922) once a paid try ends, its measured spend replaces the
  estimate on the listed try and on the step's column ("cost $0.028, measured"); unmeasurable spend says
  why, never $0. Built: `_spent` and `TryCost`; not built: per-page on the try pass. *Test:*
  `test_setup_try_list.py` (the measured figure on the listed try).

### E. What each step draws, and how it is corrected on the page

**Exists.** Regions and lines are drawn by the one overlay in kinds and colours
(`source.editor.one-overlay` (P), `source.editor.regions-under-lines`, `source.editor.regions-in-colours` (P))
and edited by reshape, draw, delete, join, set kind, in the editing mode (`source.editor.reshape` (P),
`source.editor.draw-shapes` (P), `source.editor.join-group` (P), `source.editor.set-kind` (P),
`source.editor.edits-are-actions` (P)); a line's reading is corrected through one path
(`source.reading.correct-a-line`, `source.lineeditor.one-path` (G), `source.lineeditor.on-the-image` (G));
inline text in its direction (`source.editor.inline-text-in-its-direction` (P)); the image tools act on
the picture with the proposal as handles (`preview.edit.tool.crop-is-a-page-box` (G),
`.straighten-is-a-dial` (G), `.split-is-a-gutter-line` (G), `.adjust-previews-live-before-after` (G),
`.proposal-is-the-tools-handles` (G)); a correction replaces the run's row
(`prep.check.correction-replaces-the-runs-row` (G)); a review's proposals are a separate pass with Accept per
line (`designer.review.proposals-are-a-separate-pass` (G)); Leave Out marks `is_furniture` with its reason
(`designer.clean.leaves-out-non-text` (P)); names and statements are accepted or rejected in the Inspector
(`kg/*`); Organise's try is a strip of a run of pages (`OrganiseTryStrip`,
`source.onboard.stages.organise-tried-on-a-run` (P)).

Each line below names the output drawn, the edit that corrects it, and the measure the step's column shows
for this page (the measures are `designer.stage.measure-table` (G), per page here).

- `setup-try.show.prepare-images` — **[GAP]** (#5382) the try's proposals come up as the tools' own dashed handles
  (the page box as the Crop quad, the gutter as the Split line, the angle in the Straighten dial, the suite's
  values in Adjust) with the Before hold showing the original; Return accepts, a drag corrects, either writes
  the `who: person` row that replaces the proposal; "Apply to the folder" is the batch sheet
  (`prep.check.apply-correction-to-the-folder` (G)). Measure: none; the column says "judged by reading:
  try Find Lines on this page next" (`prep.judged-by-reading`). *Test:*
  `fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift` (a try's proposal seeds the
  handles; Return writes the person's row).
- `setup-try.show.find-regions` — **[GAP]** (#6052) the try pass's regions drawn in their kind colours with labels on
  hover; the editing mode on, so a region is reshaped, redrawn, deleted or re-kinded through
  `segment.update`; a region added by hand is the person's and the detector's label when exported
  (`prep.yolo.fine-tune-from-corrected-regions`). Measure: with marked layout, "blocks IoU 0.81 · 3 of 4
  kinds found"; without, "n blocks found; correct them here to measure". *Test:*
  `fichero-server/tests/unit/recipes/test_setup_try_measures_per_page.py` (region IoU on one page).
- `setup-try.show.find-lines` — **[GAP]** (#5668) lines with baselines, regions dimmed under them; a line is moved,
  reshaped, split (Return on the picture), joined or deleted in the editing mode; "Lines only inside the
  page" draws the page box faintly (`prep.page.detected-before-lines`). Measure: with checked lines on the
  page, "42 of 44 lines found · 1 extra" (`bakeoff.score_lines`); without, the count and "correct the lines
  here to measure". *Test:* `test_setup_try_measures_per_page.py` (line recall on one page from the person's
  boxes).
- `setup-try.show.leave-out` — **[GAP]** (#6070) left-out lines drawn hatched with the reason on hover and in the
  Inspector; a click toggles `is_furniture` (the person's mark wins and is kept across tries); the page box,
  ruler and colour card drawn faintly as what the rule read. Measure: "6 lines left out: 4 off the page, 2
  too small". *Test:* `test_setup_try_measures_per_page.py` (the count by reason; a person's toggle holds).
- `setup-try.show.read` — **[GAP]** (#5211) the try pass's reading shown inline on each line in its direction and
  font, and as a text column beside the page (the Reader's lines mode, not a third view), low-certainty
  lines tinted (`source.recipe.certainty-is-calibrated` (G)); double-click or Return on a line opens the
  field over it (`source.lineeditor.on-the-image` (G)); the correction is the person's reading through the
  one path and the line becomes a checked line. Measure: with checked lines on this page, "CER 3.1% · WER
  9% · inserts 0.2% on the 12 lines you checked"; without, "not measured against your reading yet: correct
  a few lines here". *Test:* `test_setup_try_measures_per_page.py` (CER on one page's checked lines);
  `fichero/Tests/Unit/general/Views/Onboarding/SetupStageReadOutputTests.swift` (inline and column from the
  same pass).
- `setup-try.show.review` — **[GAP]** (#6052) the reviewer's proposals drawn beside each line it would change
  (the proposed text, the reason, the confidence), unchanged lines quiet; Accept per line writes the
  person's reading; Reject leaves the reading; Accept all is not offered. Measure: "would change 7 of 44
  lines; on the 12 you checked, CER 4.0% → 3.4%" (`designer.review.measure-is-gain` (G)). *Test:*
  `test_setup_try_measures_per_page.py` (the gain on one page).
- `setup-try.show.normalise-translate` — **[GAP]** (#6052) the derived text in a column beside the page, aligned to
  the lines, the source reading above each; a correction edits the derived pass through the one path.
  Measure: agreement with checked lines of that pass where any; else the words. *Test:*
  `SetupStageReadOutputTests` (the derived column aligns by line).
- `setup-try.show.names-statements-dates` — **[GAP]** (#6052) the found items lit in the text column (names by
  kind colour, statements as their spans, dates on the lines that carry them) and listed under it with
  Accept and Reject as the Inspector offers them; a rejected item is a person's judgement the measure uses.
  Measure: "11 names found; on your checked names, precision 0.9, recall 0.8", else the count. *Test:*
  `test_setup_try_measures_per_page.py` (precision and recall on one page from accepted and rejected).
- `setup-try.show.organise-and-the-rest` — **[PARTIAL]** (#5668) Organise shows its run of pages as the strip under
  the Preview with the proposed documents bracketed (built: `OrganiseTryStrip`); Passages, Structured Data,
  Search and Catalogue show what their try made in the step's column in words and are not drawn on the page;
  a stage with nothing to draw says so (`stages.NOT_TRIED`). *Test:*
  `fichero/Tests/Unit/general/Views/Onboarding/SetupStageColumnTests.swift` (each stage's output kind).
- `setup-try.edit.is-the-pages-real-edit` — **[GAP]** (#6296) every correction made while trying is the page's
  real edit: a chain row (`preview.edit.chain-is-a-separate-row-never-the-source`), a `segment.update`, a
  person's reading, an accept or reject, each audited, each ⌘Z-able (`source.editor.system-undo` (P),
  `undo.*`), each visible in the project window the moment Set Up closes; no edit is held in a try's
  store. Pinned by a test that makes one edit of each kind in Set Up's Preview and reads it back through the
  project's routes. *Test:* `fichero-server/tests/unit/recipes/test_setup_try_edits_are_real.py`.
- `setup-try.edit.corrections-are-checked-lines` — **[GAP]** (#5900) a line corrected or confirmed on a try pass
  is a checked line (`designer.check.corrections-become-the-reference` (P),
  `source.compare.pick-is-a-training-line`), counted toward the compare and teach thresholds
  (`designer.check.progress-in-words` (G)) and used by every measure from then on. *Test:*
  `test_setup_try_edits_are_real.py` (one correction raises the checked count and changes the CER).
- `setup-try.edit.measure-updates-on-the-page` — **[GAP]** (#6052) the step's column re-reads the page's measure
  after each correction without a re-run (the try pass is unchanged; the truth changed), within a second;
  the measure names its basis ("on the 13 lines you checked"). *Test:* `test_setup_try_measures_per_page.py`
  (the measure route answers from the pass and the truth).

### F. Keep what works

**Exists.** Use This One per column sets the step's model through `use-candidate`
(`designer.compare.person-chooses` (P), `source.try.use-this-scope` (P)); the choice is marked in the list
(`designer.rank.one-visible-selection` (P)); Ready names each step's model and place
(`designer.ready.one-line-per-step-with-change` (P)).

- `setup-try.keep.is-use-candidate` — **[PARTIAL]** (#4950) Keep in the step's column is `use-candidate` for the
  tried card with the settings as tried (`settings` on the body; the recipe step keeps them), for the
  project or for the page's folder (`source.try.use-this-scope` (P)); the chooser marks it at once; there is
  no second keep. Built: the route for the card; not built: settings, the folder scope from here. *Test:*
  `fichero-server/tests/unit/recipes/test_setup_try_keep.py`.
- `setup-try.keep.ready-names-the-page` — **[GAP]** (#6052) Ready's line for the step says which page it was kept
  from and the measure there ("kept after trying f. 12r: CER 3.1% on 13 checked lines"); Change… opens the
  chooser. *Test:* `test_setup_try_keep.py` (the recipe step carries `kept_from`; Ready renders it).
- `setup-try.keep.unkept-tries-stay` — **[GAP]** (#4950) tries of other candidates stay listed and drawable on the
  page after Keep; nothing is deleted by a choice. *Test:* `test_setup_try_keep.py`.

### G. Compare is a mode of the same Preview

**Exists.** Compare on These Pages runs 2 or 3 candidates on the samples and shows counts per model, a
side-by-side sheet per page with each model's lines drawn and its reading under (`StageCompareWindow`,
`StageCompareColumns`, `source.onboard.stages.compares-candidates` (P), `.compare-results-per-model` (P));
the candidates compared are chosen in `StageCandidateChooser`; the text comparison of a try's candidates
is the same answer as the readers' compare (`source.compare.try-candidates-same-shape`, `try_compare`); the
Segments pane's Compare mode (`source.compare.segments-mode` (G)); labels, row sentences and predictions
(`designer.compare.*`).

- `setup-try.compare.is-a-mode-of-the-same-preview` — **[GAP]** (#5900) Compare toggles the Preview into a compare
  mode on the selected page: for the layout steps the candidates' shapes drawn in one colour per candidate
  with a legend and a per-candidate show/hide; for the text steps the Segments pane's Compare rows under the
  page (`source.compare.segments-mode` (G), fed by `try_compare`) with the page above; Use This One per
  candidate is Keep. No sheet, no window. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/SetupCompareModeTests.swift`.
- `setup-try.compare.runs-only-what-is-missing` — **[GAP]** (#4950) Compare runs a try for each chosen candidate
  that has no try pass of the matching key on this page and reuses the rest
  (`setup-try.reuse.compare-and-bakeoff-reuse-tries`); its price is the sum of the missing paid ones, on
  the button. *Test:* `test_bakeoff_reuses_tries.py`.
- `setup-try.compare.measures-beside` — **[PARTIAL]** (#6052) the candidates' measures on this page and on all
  tried pages sit in the step's column as the compare's rows (`designer.compare.row-sentence` (G),
  `designer.compare.labels-where-measured` (P)); without truth, the readings and the predictability words
  only (`designer.compare.without-truth-shows-readings-only` (G)). Built: the rows under the samples.
  *Test:* `SetupCompareModeTests` (renders as served).
- `setup-try.compare.window-retired` — **[GAP]** (#5856) `StageCompareWindow` and the per-page sheet are removed;
  `StageCompareColumns`'s drawing moves into the compare mode's legend; the Compare on These Pages button
  becomes Compare in the step's column; `designer.compare.side-by-side-text` (G) is met by this mode.
  *Test:* `fichero/Tests/Unit/general/Views/Onboarding/SetupCompareModeTests.swift` (availability: no sheet).
- `setup-try.compare.auto-run-makes-tries` — **[GAP]** (#6052) the automatic compare (`designer.compare.runs-by-itself`
  (G), local candidates only without truth, capped) makes ordinary try passes on the first 3 sample pages,
  listed per page like a pressed try, so nothing it reads is read again. *Test:*
  `fichero-server/tests/unit/recipes/test_compare_auto_run.py` (one more case: the passes are tries).

### H. Agent parity

- `setup-try.agent.tool-and-cli` — **[PARTIAL]** (#4950) `fichero_recipes_try_stage` and `fichero recipes try
  <stage> --page <id> --model <card> [--set key=value]` do what the button does (one page, one candidate,
  settings, the price first, the reuse) and `fichero_recipes_stage_try_result` / `fichero recipes tries
  <stage> --page <id>` list the page's tries; the corrections are the existing audited actions
  (`source.editor.agent-parity` (P), `source.lineeditor.agent-parity` (G)). Built: the two tools from the
  route; not built: the page list, the price, settings. *Test:* `fichero-mcp/tests/test_mcp_generated.py`;
  `fichero-cli/tests/test_recipes_try.py`.

## Changes to existing behaviours

Each owning spec is edited only on approval.

1. **A try lands on the page, not on a copy.** `source.onboard.stages.sample-run-reuses` (P),
   `source.onboard.stages.samples-are-not-the-work` (P) and `recipes-run.journey.try-is-not-the-work` run a
   try on a scratch copy and keep one result per stage. This spec writes a try pass on the real page, kept
   per page and per key (`setup-try.run.lands-on-the-page-as-a-try-pass`, `setup-try.reuse.listed-per-page`).
   "Not the work" stays true in the sense that matters: the try never changes an existing pass, never
   becomes the working pass by itself and is never counted as the run's; whether Start counts it as done
   is open question 1.
2. **The compare window goes.** `source.onboard.stages.compare-results-per-model` (P) names
   `StageCompareWindow`; `designer.compare.side-by-side-text` (G) asks for text beside the page. Both are
   met by the compare mode of the embedded Preview (`setup-try.compare.*`); the sheet is retired.
3. **The stage page's shape.** `source.onboard.stages.page-says-what-it-does` (P) and
   `.page-asks-its-questions` (P) keep their content; it moves into the step's column
   (`setup-try.layout.settings-beside-the-page`). The showcase (`source.onboard.stages.shows-what-it-does` (P))
   is kept for a project with no pages only.
4. **The window's size.** `FirstRunWindow.windowSize` 820×600 becomes 1200×760, resizable
   (`setup-try.window.larger-and-resizable`); the onboarding screenshots re-record.
5. **Cost asked on the button, not after.** `source.onboard.stages.samples-proposed` (P) asks the cost after
   a refused press ("Compare, at That Cost"); here the price is on the button and the press is the yes
   (`setup-try.cost.price-on-the-button`); the 402 stays for a caller that sends no `cost_ok`.
6. **The edited image is what a model reads.** #6296 (`preview.edit.model-steps-read-the-edited-image` (B))
   is a precondition of the try key; the try spec does not re-specify it.

Not changed: three candidates compared; the bake-off's readiness and scorer; the noise band; Use This
through `use-candidate`; every `source.editor.*`, `preview.edit.*` and `source.lineeditor.*` edit (this
spec adds no editor); the recipe runs' lanes and throttle.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | layout sizes; the column's order; the button text from the served price; the compare legend; rendering of the try list | `fichero/Tests/Unit/general/Views/Onboarding/SetupWindowLayoutTests.swift`, `SetupStageColumnTests.swift`, `SetupStageTryStoreTests.swift`, `SetupCompareModeTests.swift` (to write) |
| Availability (Swift) | y | the one Preview mounts in Set Up with its overlay, editor and correction; no sheet; Keep and Compare on every sampleable stage | `fichero/Tests/Unit/general/Views/Onboarding/SetupPreviewMountTests.swift` (to write) |
| Backend (pytest) | y | one page one candidate with settings; the try pass; the key; reuse with no model call; changed input re-keys downstream; the per-page list; the price; the cap; measured spend; per-page measures for each step; edits are real and become checked lines; Keep with settings and `kept_from`; the bake-off reuses tries | `fichero-server/tests/unit/recipes/test_setup_try_live_run.py`, `test_setup_try_key.py`, `test_setup_try_list.py`, `test_setup_try_price.py`, `test_setup_try_capped.py`, `test_setup_try_measures_per_page.py`, `test_setup_try_edits_are_real.py`, `test_setup_try_keep.py`, `test_bakeoff_reuses_tries.py`, `test_try_reads_the_edited_image_6296.py` (to write) |
| MCP | y | `fichero_recipes_try_stage` with one page, settings and the reuse; the try list | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | `fichero recipes try` and `fichero recipes tries` | `fichero-cli/tests/test_recipes_try.py` (to write) |
| Click-around (XCUITest, Mac) | y | select a page → Try → lines drawn → drag a line → CER line updates → change model → Try (price on the button) → Compare → Keep → Ready names the page | `fichero/Tests/UI/Onboarding/SetupTryLiveUITests.swift` (to write) |
| iPhone (iOS) | n | Set Up is a Mac surface | — |
| iPad | n | — | — |
| Load (#4634) | y | a try on one page of 10.7 MP stays under the per-page memory ceiling and answers Activity within 1 s; a reused try makes 0 model calls | `fichero-server/tests/perf/test_setup_try_bounded.py` (to write) |

Hard-gate: the cross-surface invariant (the button, the tool and the CLI run the same route, key the same
way and reuse the same pass; the edits are the project's own actions) + availability (the one Preview, Try,
Compare and Keep on every sampleable stage).

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | "Designing your recipe" → "Trying a step on your pages" (TBD; the facts are the lines above) |
| Contributor | developer docs | y | `docs/contributor_manual/architecture/` recipes (the try key and try pass) + this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/**` (`fichero_recipes_try_stage`: one page, settings, the price, the reuse; the try list) |
| Scripter | CLI `--help` | y | `fichero-cli/**` (`recipes try`, `recipes tries`) |
| Reference | capability/endpoint reference | y | generated (`check_capability_reference_current`) |

## Preview harness

`SetupTryLivePreview` (`#if DEBUG`) renders from recorded served data, no engine: the three columns at the
default and the minimum size; a page with a Find Lines try drawn and one line selected; the Read try inline
and in its column with a tinted line; a Prepare try's dashed handles; the step's column with a priced
button, a running bar, a measure line and three listed tries (one reused); the compare mode with two
candidates' lines in two colours. It is the source of the manual's screenshots
(`docs/assets/setup-try-live/`).

## Accessibility identifiers

| Surface | Identifiers |
|---|---|
| Items | `setup.try.items` · `setup.try.item.<page>` · `setup.try.items.filter` · `setup.try.item.dot.<stage>` |
| Preview | `setup.try.preview` · `setup.try.preview.bar` · `setup.try.preview.stop` |
| Column | `setup.try.chooser` · `setup.try.question.<key>` · `setup.try.run` · `setup.try.price` · `setup.try.measure` · `setup.try.tried.<pass>` · `setup.try.compare` · `setup.try.keep` · `setup.try.keep.scope` · `setup.try.needs-first` |
| Compare | `setup.try.compare.legend.<card>` · `setup.try.compare.use.<card>` |

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `setup.try.run` | Try on This Page (· about $N) | Runs this step on the selected page with the model and settings shown; a paid model's price is on the button; the same model on the same page is never run twice | `setup.try.run` | [GAP] |
| `setup.try.preview.stop` | Stop | Stops this try; what it made so far is kept | `setup.try.stop` | [GAP] |
| `setup.try.items.filter` | Samples / All pages | Which pages the list shows | `setup.try.items.filter` | [GAP] |
| `setup.try.tried.<pass>` | the model and when | Shows this try on the page | `setup.try.tried` | [GAP] |
| `setup.try.compare` | Compare | Shows two or three models' tries on this page together, with their measures | `setup.try.compare` | [GAP] |
| `setup.try.keep` | Keep | Makes this model and these settings the step's choice | `setup.try.keep` | [GAP] |
| `setup.try.keep.scope` | For the project / For this folder | Where the choice applies | `setup.try.keep.scope` | [GAP] |
| `setup.try.needs-first` | Try <step> on this page first | This step needs what an earlier step makes; runs it, then this one | `setup.try.needs-first` | [GAP] |

All strings through the String Catalog; no `Text(verbatim:)`. Every row is [GAP] until a spec-pinned test
or `performAccessibilityAudit()` covers it.

## Build order

Engine before app; each step shippable alone.

### Stage 1 — The try lands on the page and is keyed

#### Step 1.1 — Models read the edited image (#6296)
- Behaviours: `setup-try.run.reads-the-edited-image`
- Tests: fichero-server/tests/unit/recipes/test_try_reads_the_edited_image_6296.py
- Size: M

#### Step 1.2 — One page, one candidate, settings; the try pass
- Behaviours: `setup-try.run.one-page-one-candidate`, `setup-try.run.lands-on-the-page-as-a-try-pass`, `setup-try.run.settings-are-the-steps-own`, `setup-try.reuse.survives-the-pass-rules`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_live_run.py, fichero-server/tests/unit/segments/test_try_pass_ranks.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — The key, the reuse, the per-page list
- Behaviours: `setup-try.reuse.key`, `setup-try.reuse.never-the-same-model-on-the-same-input`, `setup-try.reuse.changed-input-is-a-new-try`, `setup-try.reuse.listed-per-page`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_key.py, fichero-server/tests/unit/recipes/test_setup_try_list.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — The price first, the cap, the measured spend
- Behaviours: `setup-try.cost.price-on-the-button`, `setup-try.cost.counts-toward-the-cap`, `setup-try.cost.reuse-is-free-and-said`, `setup-try.cost.measured-after`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_price.py, fichero-server/tests/unit/recipes/test_setup_try_capped.py
- Depends on: 1.3
- Size: M

### Stage 2 — Measures per page; edits are real; Keep

#### Step 2.1 — Each step's measure on one page
- Behaviours: `setup-try.edit.measure-updates-on-the-page`, `setup-try.run.needs-offer-the-step-before`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_measures_per_page.py
- Depends on: 1.3
- Size: M

#### Step 2.2 — Edits made while trying are the page's edits and checked lines
- Behaviours: `setup-try.edit.is-the-pages-real-edit`, `setup-try.edit.corrections-are-checked-lines`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_edits_are_real.py
- Depends on: 1.2
- Size: M

#### Step 2.3 — Keep with settings; Ready names the page; the bake-off reuses tries
- Behaviours: `setup-try.keep.is-use-candidate`, `setup-try.keep.ready-names-the-page`, `setup-try.keep.unkept-tries-stay`, `setup-try.reuse.compare-and-bakeoff-reuse-tries`, `setup-try.compare.auto-run-makes-tries`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_keep.py, fichero-server/tests/unit/recipes/test_bakeoff_reuses_tries.py, fichero-server/tests/unit/recipes/test_compare_auto_run.py
- Depends on: 1.3
- Size: M

#### Step 2.4 — The tool and the CLI
- Behaviours: `setup-try.agent.tool-and-cli`
- Tests: fichero-mcp/tests/test_mcp_generated.py, fichero-cli/tests/test_recipes_try.py
- Depends on: 1.4
- Size: S

### Stage 3 — The window: item list, Preview, the step's column

#### Step 3.1 — The larger window and the three columns
- Behaviours: `setup-try.window.larger-and-resizable`, `setup-try.layout.three-columns-on-a-stage-page`, `setup-try.layout.settings-beside-the-page`
- Tests: fichero/Tests/Unit/general/Views/Onboarding/SetupWindowLayoutTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupStageColumnTests.swift
- Size: M

#### Step 3.2 — The item list and stepping
- Behaviours: `setup-try.items.project-pages-samples-first`, `setup-try.items.row-says-what-was-tried`, `setup-try.items.arrows-step-pages`
- Tests: fichero-server/tests/unit/recipes/test_setup_try_items.py, fichero/Tests/Unit/general/Views/Preview/SiblingStepTests.swift
- Depends on: 3.1
- Size: M

#### Step 3.3 — The one Preview embedded; Try with words on the page
- Behaviours: `setup-try.preview.is-the-one-preview`, `setup-try.preview.selection-is-the-windows`, `setup-try.run.words-on-the-page`
- Tests: fichero/Tests/Unit/general/Views/Onboarding/SetupPreviewMountTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupStageTryStoreTests.swift
- Depends on: 3.1, 1.3
- Size: M

### Stage 4 — What each step draws

#### Step 4.1 — Layout steps: Prepare Images, Find Regions, Find Lines, Leave Out
- Behaviours: `setup-try.show.prepare-images`, `setup-try.show.find-regions`, `setup-try.show.find-lines`, `setup-try.show.leave-out`
- Tests: fichero/Tests/Unit/general/Views/Preview/ImageEditDirectToolsTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupStageColumnTests.swift
- Depends on: 3.3, 2.1
- Size: M

#### Step 4.2 — Text steps: Read, Review, Normalise and Translate, Names, Statements, Dates, the rest
- Behaviours: `setup-try.show.read`, `setup-try.show.review`, `setup-try.show.normalise-translate`, `setup-try.show.names-statements-dates`, `setup-try.show.organise-and-the-rest`
- Tests: fichero/Tests/Unit/general/Views/Onboarding/SetupStageReadOutputTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupStageColumnTests.swift
- Depends on: 3.3, 2.1
- Size: M

### Stage 5 — Compare as a mode; the window retired

#### Step 5.1 — Compare mode, runs only what is missing, measures beside, the sheet goes
- Behaviours: `setup-try.compare.is-a-mode-of-the-same-preview`, `setup-try.compare.runs-only-what-is-missing`, `setup-try.compare.measures-beside`, `setup-try.compare.window-retired`
- Tests: fichero/Tests/Unit/general/Views/Onboarding/SetupCompareModeTests.swift, fichero-server/tests/unit/recipes/test_bakeoff_reuses_tries.py
- Depends on: 4.1, 4.2, 2.3
- Size: M

#### Step 5.2 — The click-around and the load leg
- Behaviours: `setup-try.run.try-is-watched-work`
- Tests: fichero/Tests/UI/Onboarding/SetupTryLiveUITests.swift, fichero-server/tests/perf/test_setup_try_bounded.py
- Depends on: 5.1
- Size: S

## Open questions for the maintainer

1. **Does Start count a try as done?** When the kept choice's key matches a page's try pass, should Start skip
   that page for that step and promote the try pass to the step's pass (`setup-try.reuse.start-counts-a-try-as-done`,
   [PROPOSED])? Yes honours "never the same model on the same input" at Start too and saves the paid pages;
   no keeps "a try is never the run's" exactly as ruled before.
2. **The page's working pass while trying.** A page whose only reading is a try pass: should the Reader and
   the project's Preview show it (ranked like any model pass, with "a try of <model>" as its basis,
   `setup-try.reuse.survives-the-pass-rules`), or should a try pass stay invisible outside Set Up until kept?
   The spec proposes visible, because a correction on it must be a real reading.
3. **Window size.** 1200×760 default, 1040×680 minimum, resizable and remembered, is proposed; the earlier
   pages (Welcome, About the Material, the path) keep one column in the same window.
4. **The Review stage's Accept.** Per line only, no Accept all (as the compare's pick rule, `source.compare.pick`).
   Confirm or allow Accept all for a review the person trusts.
5. **The Hugging Face and provider caps before #5440.** Until the project cloud cap is built, a paid try on a
   provider is uncapped and the button says so once; or hold paid tries to Hugging Face places only. The
   spec proposes the former, with the sentence.
