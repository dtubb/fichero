# Recipe Designer — Fichero helps a person design a good recipe for their material — Design Spec (#6052)

> Milestone: recipe-designer
> Manual: TBD — a "Designing your recipe" chapter in the Projects part, with these sections (each is the
> target of a "Learn more" link named below): **"Ways of working"** (the four paths, what each costs,
> how long, how predictable it is and what happens next); **"Teaching a model as you go"** (distil and
> fine-tune in plain words, when it is offered, where it runs, the teacher's terms); **"How a step picks
> its model"** (the filters, the one rule, measured on your pages, else a measured default, what the
> words on a row mean); **"Comparing models on your pages"** (what Compare shows with and without
> checked lines, when it runs by itself, the caps); **"Checking lines"** (where to correct, how many are
> needed and why); **"Reading the numbers"** (CER, WER, line recall, the noise band, the insertion rate
> and why a large cloud model may invent text); **"Costs while it runs"**; **"Sharing a recipe"** (what a
> recipe file holds and never holds, starting from one, following a published one).
> **Status: APPROVED 2026-10-24 (rulings below).** Create
> `recipe-designer` on approval and point its description here.
> **Added 2026-10-30, DRAFT until the maintainer rules (nothing is built until then):** the condition questions in
> section 3, the "How do you want to run this?" questions and the risks in section 4, the defaults table in
> section 4b, Budget in section 11b, and Stage 18 of the build order (`designer.material.condition-*`,
> `designer.how.*`, `designer.defaults.*`, `designer.budget.*`). The maintainer's request of 2026-10-30, from
> #6295 (no budget control in Set Up) and #6294 (the estimate under-prices a cloud line read). Those lines are
> tagged **[GAP]** meaning nothing is built, as the maintainer asked; each names the test file that would pin it.
> **Ruled 2026-10-30 (the maintainer):** open questions 5, 7, 8 and 9 of the 2026-10-30 additions (page order, the two
> caps, no margin on the estimate, fewer pages as a Start), recorded under "Rulings (the maintainer, 2026-10-30)";
> question 6 (the defaults table's rows) stays open.
> Replaces: `recipe-ranking-and-compare.md` (the 2026-10-24 first draft on this branch, `git mv`'d here).
> Sources: two design briefs of 2026-10-24 (local working notes, not in the repository; their facts are
> inlined in the appendix "Screens review facts") and the owner's directions of 2026-10-24, paraphrased.

Tags: [OK] built · [PARTIAL] exists elsewhere / not wired · [MISSING] not built · [GAP] not built, owned
by another spec · [PROPOSED] a question wearing a behaviour's clothes, not yet ruled. This spec does
**not** replace the Set Up, onboarding or recipe specs: it walks the journey **as the app does it today**,
cites each existing behaviour by its own id (the owning spec stays the place to change it), and attaches
the improvements as new `designer.*` behaviours at the point of the journey where the person meets them.
Under "**Exists**", an id with no mark is [OK]; **(P)** marks PARTIAL, **(G)** GAP, **(B)** BROKEN, so
"exists" never reads as "built". The few real changes to existing behaviours are collected at the end.

## The words (one meaning each)

- **Recipe**: the whole plan for a project: the answers about the material, the path, the chosen stages,
  and for each step its chosen model, place and settings, with the measured results that chose them
  (`source.recipe.is-a-file` (G), `source.recipe.folder-format` (P), `source.recipe.names-models-and-where` (P)).
- **Step**: one job in the recipe (`find-regions`, `find-lines`, `read-a-line`, `review-lines`,
  `find-names`…), from the job registry (`source.recipe.steps-are-jobs` (P), `source.recipe.jobs-are-a-registry` (P),
  `source.recipe.steps-work-alone-in-order`).
- **Workflow**: what carries a step out. Every step runs as a workflow of the visual node-editor
  system: `recipes/start.py` maps each job to a shipped workflow preset (`WORKFLOW_FOR_JOB`, `_shipped`,
  `workflows.default_workflows.preset_workflow_id`) and passes the step's provider and model as the
  override (`source.recipe.makes-a-workflow` (P), `source.recipe.start-runs-the-steps`; the editor is
  `ui/workflows.md` and `ui/workflow-node-config.md`: `workflows.canvas.renders-nodes-edges-ports` (P),
  `workflows.canvas.locked-preset-is-read-only`, `nodeconfig.model.same-list-as-settings`,
  `nodeconfig.prompt.shows-effective-prompt`). **The recipe and the workflows are one system**: the
  recipe is the plan the person reads and chooses in Set Up; a workflow is how one step of it is wired
  and run. Choosing a model on a stage page and in the node's config is the same choice (section 6).
- **Candidate**: a model and the place it runs that a step could use; **pick**: the one it does.
- **Large cloud model**: the on-screen words for what the engine calls a frontier model (Claude, Gemini,
  GPT); "frontier" never appears on a screen.
- **Measure**: a number against ground truth on named pages, with its provenance. **Noise band**: the
  difference below which two measures are the same (0.5 CER points per model kind until measured;
  section 8).
- **Predictability**: how far a reader's output is confined to what is on the line. A CTC reader
  (Kraken) reads only what is on the line and may misread a word; a vision-language model reads fluently
  and may insert, drop or regularise words. Measured as the **insertion rate** (section 7). The label on
  a compare is **most predictable**.
- **Teach**: the on-screen verb for making a model from the person's checked lines, by **distilling**
  (a large cloud model reads first, the person corrects, a small model learns from the corrected lines)
  or **fine-tuning** (a shipped reader learns the hand from the corrected lines). **Train** is the Set
  Up page where the offer appears.
- **Checked line**: a line whose reading a person has confirmed or corrected; the ground truth every
  measure on the person's pages uses.

## Intent (the design)

A person with a box of historical pages should be able to sit down with Fichero and, without knowing
what a Kraken model or a tokenizer is, end up with a recipe that reads their material well, at a cost, in
a time and with a predictability they chose with their eyes open. The designer is the existing journey
(set up the app, start a project, add material, say what it is, choose the stages, a page per stage,
check lines, Train, Ready, Start, the run) made to **explain and measure** at every step: it asks how the
person wants to work and explains each way, with the routes' own figures; it finds the candidates for
each stage, filters out what does not fit or cannot write the script, ranks the rest by one rule the
person can read, runs them on a few of the person's own pages without being asked, shows the readings
side by side beside the page, labels best, cheapest, fastest and most predictable once there is
something to measure against, predicts the cost and time of the whole project, and lets the person
choose. Where a large cloud model reads well but dearly, or well but inventively, it offers to teach a
smaller model from the checked lines and switches only when the measurement says it is as good. Every
number carries its provenance; no model ranks another model; the person is never asked a question the
engine can answer from the files, and never has a question answered for them.

It lives in Set Up (`fichero/fichero/Views/Onboarding/`: `FirstRunWindow`, `SetupFlow`,
`SetupStagePage`, `StageCandidateChooser`, `StageCompareWindow`, `ModelFinderSheet`,
`RecipeMoneyAndPlaceFields`, `RecipeReadyFields`) over the recipe engine
(`fichero-server/src/fichero_server/recipes/`: `assemble.py` `_rank_key`/`_choose`, `bakeoff.py`,
`samples.py`, `stages.py`, `discovery.py`, `step_choices.py`, `places.py`, `routes.py`, `derived.py`,
`regions.py`, `review_profiles.py`, `placement.py`), the evaluation (`training/evaluation.py`,
`transcription_accuracy.py`), the coverage scorers (`llm/language_coverage.py`,
`llm/script_coverage.py`) and a vendored benchmark table (`recipes/seed/measured-defaults.yaml`, to
create). All logic (filters, rank, labels, estimates, caps) is the engine's, served to the app through
the generated client; Swift renders the served order and never ranks.

## Prior art / best practices (don't invent from scratch)

- **Model choice in Transkribus and eScriptorium.** Both make the person pick a public model by its
  card (training data, script, CER on its own validation set) and offer a run on a page before
  committing; Transkribus's public models sort by a self-reported CER and name their ground-truth
  sets. We adopt the card and the try-on-your-pages, and go further: the try is automatic, measured on
  the person's pages and a shared benchmark, and the candidates are ranked by that measurement.
- **CATMuS and HTR-United.** CATMuS (Clérice et al.) gives shared transcription guidelines and a
  multilingual medieval ground truth; HTR-United catalogues ground-truth sets with licence, script and
  period. We read both (`source.find.htr-united-and-tessdata` (P)), score CER under a CATMuS-as-written
  policy beside the diplomatic one (`training.eval.policies-named` (P)), and give every benchmark row the
  provenance fields HTR-United asks of a dataset: set, pages, licence, who made the truth.
- **CER and WER conventions.** Edit distance over the reference length, per named policy, with a noise
  band before a difference counts (ICFHR/ICDAR competitions report both; `ketos test` reports
  character accuracy). One scorer for every measurement (`training.eval.one-scorer`). Insertions are a
  separate term of the same edit distance, which is how an insertion rate is read off it.
- **Hallucination in VLM transcription.** Recent HTR work with vision-language models reports fluent
  readings that match nothing on the page, silent "corrections" of the scribe's spelling, and
  repetition loops; CTC readers cannot emit a word that no part of the line supports, though they can
  misread one and can emit text on decoration. The field measures this as insertion rate and run-to-run
  agreement; we adopt both and the failure-mode flags already specified (`training.errors.failure-modes` (G)).
- **Layout: SegmOnto and YALTAi.** SegmOnto names regions and lines with a controlled vocabulary;
  YALTAi trains YOLO detectors on those zones and runs Kraken's line finder per zone. Region quality is
  mean IoU per ground-truth region plus class recall (DocLayNet, YALTAi).
- **Knowledge distillation.** A large teacher labels data, a small student is trained on it and
  measured against held-out human truth (Hinton et al.; the HTR practice of bootstrapping Kraken from
  a stronger reader and correcting). An option, never a default (`distill.offered-not-default` (G)), with
  the person's corrections outranking the teacher (`training.distil.corrections-outrank-teacher` (G)) and
  the teacher's terms on the card (`distill.licence.teacher-terms` (G)).
- **Tokenizer coverage (Loove).** Andy Janco's Loove publishes per-model tokenizer coverage per
  language and script: a filter on what a text model can write, not a score of how well it reads; a
  Kraken codec is the same kind of fact. Coverage runs before any CER (`source.recipe.loove-tokenizer-only` (G)).
- **What we do differently.** No model is asked to rank models, and models are never ranked by how
  much they agree with each other (shared regularisation would look like quality). A model earns a
  place only as a candidate measured against a person's reading, or as a reviewer whose proposals are so
  measured.

## The journey, as the app does it today, and the improvements at each point

Numbered in the order a person meets them. "Exists" cites the owning specs; "Improves" adds
`designer.*` behaviours, one observable line per id.

### 1. Setting up the app: first launch, what Fichero runs, where models may run

**Exists.** A first launch offers Welcome, What Fichero runs and a hand-off to a project
(`source.onboard.first-launch-offers-setup` (P), `source.onboard.first-launch-three-screens` (P),
`source.onboard.app.steps` (P), `source.onboard.app.what-fichero-runs` (P), `source.onboard.app.one-continue` (P),
`source.onboard.app.provider-sheet-in-step` (P)); where models may run is app-wide, no default, and caps
every project (this Mac, another Mac of mine, the cloud, ACENET, Hugging Face;
`source.onboard.places-cap-projects` (P), `ai.where.one-list-of-places` (G), `ai.where.settings-lists-places` (G));
providers and keys live in Settings (`ai/ai-settings.md`; `source.find.key-offers-frontier-models` (P)).

**Improves.**
- `designer.app.places-say-their-consequence` [MISSING] (#6052) — each place on What Fichero runs
  carries one sentence of consequence for a recipe ("the cloud: large cloud models become candidates,
  and pages leave this Mac only when a project allows it"; "ACENET: long runs and training can be sent
  to the cluster, nothing until you say").

### 2. Starting a project, and adding material

**Exists.** Set Up a Project is one view from every way in (`source.onboard.new-project-offers-setup` (P),
`source.onboard.project.one-view` (P), `source.onboard.project.steps` (P)); Add Material takes folders, files,
a synced folder, a scan or an existing library (`source.onboard.project.add-material` (P),
`source.onboard.five-ways-in` (P), `source.onboard.icloud-pages-warned` (P)); a pass can be marked ground
truth at import or afterwards, in the engine only (`source.onboard.ground-truth-from-files` (P));
text-only material is not read (`source.recipe.text-material-is-not-read` (P)).

**Improves.**
- `designer.material.imported-transcriptions-detected` [MISSING] (#6052) — when the material arrives
  with transcriptions (PAGE, ALTO, hOCR, TEI, plain text named after its image, Tesseract `.box`), Add
  Material says how many pages carry one and from which tool.
- `designer.material.imported-truth-asked-once` [MISSING] (#6052) — one question, default yes: "212 pages
  arrive with a transcription from Transkribus. Use them as the measure every model is compared
  against? You can correct them later; your corrections win." Yes marks the passes ground truth
  through the existing route (one code path); plain text named after its image counts as page truth.
- `designer.material.imported-truth-measures-at-once` [MISSING] (#6052) — with imported truth the
  bake-off readiness passes without waiting for checked lines; every measurement says "measured on 3 of
  your imported pages; ground truth from the files"; a later correction replaces the file's reading as
  the reference.
- `designer.material.glyph-inventory` [MISSING] (#6052) — the project keeps an inventory of the
  characters its ground truth uses (`.box` characters, TEI `<g>`/MUFI, the text of marked passes), read
  by the coverage filter (section 7), the display check (section 3) and the compare's character row.

### 3. About the Material

**Exists.** Languages (as you type, stored as tags), scripts and direction derived from the language,
material (handwriting, print, typescript, any mix), when written and which hand, layout form, nothing
preselected (`source.onboard.project.about-material` (P), `source.onboard.project.language-as-you-type` (P),
`source.onboard.language-stored-as-tag`, `source.onboard.script-from-language` (P),
`source.onboard.material-any-mix` (P), `source.onboard.material.when-written` (P),
`source.onboard.material.which-hand` (P), `source.onboard.material.nothing-preselected` (P),
`source.onboard.stages.layout-forms` (P), `source.onboard.material.feeds-the-reader-search` (P)); derived
facts, including the bundled font for a script macOS lacks, come from `recipes/derived.py`
(`source.onboard.derives-not-asks` (P)).

**Improves.**
- `designer.material.question-names-its-stage` [MISSING] (#6052) — the engine serves, with the
  questions, which stage each one feeds (`GET /api/recipes/questions`, a question → stages map), and
  each question shows it ("the period narrows the readers"); a question no stage reads is not asked.
- `designer.material.script-displays-check` [MISSING] (#6052) — `derived.py` extends its font answer
  with a per-character check of the glyph inventory (or, before any truth, the script's exemplars)
  against the bundled fonts' cmaps; the app adds this device's system fonts and shows the result for
  the device the person is looking at: "all 418 of your characters display", or "14 characters
  (Canadian Syllabics, U+1400…) have no font here and show as boxes until one is added", naming the
  fallback family. The Reader uses the same answer.

**Improves — the condition of the material (the maintainer, 2026-10-30; DRAFT).** Today About the Material asks
what the material is (handwriting, print, typescript, text: `answers.materials`, `recipes/answers.py`) and the
engine measures faded pages from a sample by itself (`source.onboard.auto.prepare-damaged-images` (P),
`recipes/prepare.py`); nothing asks about damage, and the Prepare Images questions are two with fixed defaults
(`recipes/stages.py`; `prep.setup.three-questions-suggested-from-a-sample` (G)).
- `designer.material.condition-asked` [PARTIAL] (#6052, #6295; engine built: `recipes/condition.py`, `answers.condition`, `GET /api/recipes/questions`; the app's tick boxes are built behind `wideSetUp`, `RecipeConditionFields`, not yet seen in a build) — About the Material
  asks, under the kind of material, "What condition are the pages in?": tick boxes, none ticked by default,
  from one engine list (`GET /api/recipes/questions`): faded ink · torn or missing parts · stains · show-through
  from the other side · water damage · tight binding (text curves into the gutter) · ruled or printed lines
  under the writing · poor black-and-white photocopy (a copy of a copy: speckle, broken strokes, text blown out or filled in, dark edges; #6486); with one line of help each, in plain words, saying what Fichero does about it. Saved as
  `answers.condition` (a list, refused in words for an unknown id, kept as a list of none). *Test:*
  `test_condition_answers.py` (the list is the engine's; an unknown id is
  refused; none ticked saves an empty list, never a default).
- `designer.material.condition-suggested-from-a-sample` [PARTIAL] (#6052; engine half built: `prepare_suggest.suggest` answers `condition.faded`, `condition.show-through`, `condition.ruled-lines` with "from N of M sample pages"; tight binding waits for the gutter-curve measure; the app does not show them yet) — the engine ticks a condition
  beforehand only when its sample measure says so (faded from `recipes/prepare.py`'s grey spread; show-through
  from the mirrored-verso match and tight binding from the gutter curve of
  `prep.setup.three-questions-suggested-from-a-sample`, once built), each suggested tick labelled "from 3 of 5
  sample pages"; a condition no measure can see (torn, stains, water damage) is never pre-ticked. The person
  changes any tick. *Test:* `test_condition_suggested_from_a_sample.py`.
- `designer.material.condition-feeds-the-defaults` [PARTIAL] (#6052; engine half built in `recipes/defaults.py`; not yet applied by `assemble.py`) — the condition answers and the kind of
  material are rows of the defaults table (section 4b): they choose the preparation steps (contrast for faded,
  show-through suppression, flattening for a tight binding, ruling removal), the reader kind (a CTC reader on
  clean print; a vision-language reader offered for damaged handwriting), and whether a Review pass is on by
  default; each chosen default says which answer chose it. *Test:*
  `test_defaults_from_condition.py`.

- `designer.material.condition-photocopy` [GAP] (#6486, owner 2026-11-10: poor black-and-white photocopies are common and hard to read) — "poor
  black-and-white photocopy" is one id in the engine's condition list. Its help line says what Fichero does: levels the
  contrast, removes speckle and dark borders, and offers a reader that copes with broken strokes. It is the same
  photocopy whether the page is handwriting or print. Ticking it adds the photocopy preparation to the defaults table (section 4b):
  despeckle, adaptive threshold or contrast levelling, border removal, each a step the person can untick; the
  original image is kept and the prepared one is a new rendition (role `prepared`, as `recipes/prepare.py`). It
  also moves a vision-language reader up for the pages it applies to. *Test:* `test_condition_answers.py` (the id
  is in the list; saved as asked), `test_defaults_from_condition.py` (photocopy chooses the steps and says it did).
- `designer.material.photocopy-suggested-from-a-sample` [GAP] (#6486) — the engine ticks it beforehand only when its
  sample measure says so: a near-bimodal grey histogram (most pixels at the two extremes, few mid-greys) with a high
  count of isolated specks and a dark border band, from 3 or more of the sample pages, labelled "from 3 of 5
  sample pages". A clean modern black-and-white scan is bimodal too, so the speck and border measures must also
  fire, or it is not suggested. The person changes the tick. *Test:* `test_photocopy_suggested_from_a_sample.py`
  (a speckled bilevel fixture is suggested, a clean bilevel scan and a grey scan are not; not yet written).

- `designer.onboarding.metadata-language` [MISSING] (#6180) — onboarding (About the Material) offers the METADATA
  LANGUAGE: the language of the catalogue's field labels and descriptions, which is not necessarily the language
  of the records. It defaults to the project's primary language and the person can choose another separately; the
  choice is saved with the project's answers and read by the Catalogue stage (`catalogue.folder-description-fields`,
  cataloguing.md), which writes labels and descriptions in it. Changing it never re-runs a folder already described.

### 4. How do you want to run this? (new page, after About the Material, before Choose the Stages)

*Page order is ruled (the maintainer's ruling, 2026-10-30): How comes after About the Material and before Choose
the Stages, so the material's facts are known before the models are narrowed.*

**Exists.** The routes: `GET /api/recipes/routes` (`recipes/routes.py`) returns the cloud, this-Mac and
distil routes for the volume with whole-project cost, time and accuracy, each figure marked measured or
estimate or unknown, to be shown **side by side, not as one plan** (`source.onboard.routes-for-the-volume` (P);
no app caller yet). Whether pages may leave this Mac is asked once per project, default nothing leaves
(`source.onboard.pages-may-leave` (P), `source.onboard.cloud-asked-once` (P)); a project may be stricter
than the app's places, never looser (`source.onboard.places-cap-projects` (P)); the Hugging Face monthly
cap, default $0, holds every paid Hugging Face offer (`source.onboard.spend-cap` (P)); a project cloud
cap and an app cap for provider calls are specified, not built (`training.cost.app-and-project-caps` (G),
`ai.where.cloud-spend-cap` (P), `ai.where.one-cloud-cap` (P)); placement by scale
(`source.recipe.placement-by-scale` (P), `compute.job.choose-where` (G)); training places
(`training.place.compared` (G), `training.place.hf-priced-first` (P), `training.place.slurm` (G),
`training.place.other-macs` (G), `training.place.this-mac-gentle` (P), `compute.tune.where-cheapest-first` (G));
the cluster offer, with no live start until the key and sign-in land (#5238;
`source.onboard.cluster-offer` (P), `compute.hpc.plan-before-send` (G), `compute.hpc.slurm-target` (P),
`compute.job.recipe-is-a-slurm-chain` (G)); Hugging Face as a place (`ai.where.hf-endpoint-is-a-place` (G));
training offered from 5,000 pages, teacher-and-student above 100,000 pages or the cost limit
(`source.recipe.volume-rule` (P)).

**Improves — the questions first (the maintainer, 2026-10-30; DRAFT).** The page opens with four short
questions, before the route cards and before Choose the Stages, so the defaults the later pages follow fit the
person; the cards (below) become the engine's answer to them, not a choice made cold. What the person has is
derived, never asked twice (`source.onboard.derives-not-asks` (P): `recipes/derived.py` already reports this
Mac's chip and memory, the providers with a key and the places work can run).
- `designer.how.where` [PARTIAL] (#6052; engine built in `recipes/how.py` and `GET /api/recipes/questions`; the app's page is built behind `wideSetUp` (`RecipeHowFields`, the How step), not yet seen in a build) — "Where should the work run?": this Mac · another machine of mine
  · a cluster · the cloud, each a tick with one sentence of consequence (pages stay here / leave to your own
  machine / to the cluster's administrators / to a company), limited to the places Set Up Fichero allows
  (`source.onboard.places-cap-projects` (P)); a place the app does not allow is shown greyed with the engine's
  reason and a link, never hidden. Saved as `answers.how.places` (a list). *Test:*
  `test_how_questions.py` (the offered places are the app's allowed ones; a
  disallowed place is listed with its reason, not dropped).
- `designer.how.model-kind` [PARTIAL] (#6052; engine built in `recipes/how.py` and `GET /api/recipes/questions`; the app's page is built behind `wideSetUp` (`RecipeHowFields`, the How step), not yet seen in a build) — "Which kind of model?": small local models (Kraken, Apple's
  recognition, small MLX models: read only what is on the line, free, slower, may misread a word) · large
  vision-language models (Claude, Gemini, GPT, or a large local one: read fluently, cost per page, may invent or
  regularise text) · let Fichero compare and choose (the default: the compare of section 8 decides on the
  person's pages). Saved as `answers.how.model_kind`. *Test:* same file (the three options, the default, and
  that the large-model option is greyed with its reason when the cloud is not allowed and this Mac cannot run one).
- `designer.how.cloud-asked-before-any-default` [GAP] (#6489, owner 2026-11-10: the cloud choice came late in the flow; the owner had not chosen cloud, so the PP-OCR default was right for cloud off) —
  whether pages may leave this Mac is asked BEFORE any model is proposed: in the How step's "Where" question (built behind
  `wideSetUp`, not yet in the flow the owner sees; the shown flow asks it late), above "What matters most?", so no default is made
  without it. If it changes later (here or in the plan), every default is worked out again from the new answer and the plan says
  what changed and why ("Read is now Gemini 2.5 Pro: you allowed cloud models and have a Google key"). A saved "no" stays no; an
  unanswered question reads as the app's setting (`places.project_says_cloud`). *Test:* `test_defaults_recomputed_on_cloud_change.py`
  (the same answers give a local Read with cloud off and a keyed frontier Read with it on; the change is named in the plan; not yet written).
- `designer.how.quality-with-cloud-is-a-frontier-reader` [GAP] (#6489, owner 2026-11-10: Gemini is a good default Read when cloud is allowed and we have access; with cloud off PP-OCR was the
  right pick) — "quality" with cloud allowed and a Gemini or Claude key chooses a frontier vision model for Read on any
  material (Gemini Pro first, `discovery.frontier_rank`), not only handwriting (`assemble._frontier_first` stops at anything else
  today); without cloud or a key it chooses the best local reader and the plan says what a key would add. PP-OCR is never the headline
  reader unless it is the best local card for the script. *Test:* `test_read_default_table.py` (one row per material x cloud x key;
  not yet written).
- `designer.setup.close-on-the-left-saves` [GAP] (#6490, owner 2026-11-10: "all screens close on the left; this closes and saves") —
  every Set Up page has Close at the leading edge of its bar (`ToolbarItem(placement: .cancellationAction)`; Esc on the Mac; on
  iPhone and iPad the sheet's leading button, and a swipe down does the same). It saves every answer so far as the project's draft,
  closes, and marks the project "setup not finished"; opening Set Up again returns to the page it was on, and nothing is asked
  again. It never needs the last page. Close is not Cancel: nothing entered is thrown away. *Test:* `SetupCloseSavesTests` (Close
  writes the answers and the page; reopening restores both; not yet written); the button's place is XCUITest #5763.
- `designer.how.what-matters` [PARTIAL] (#6052; engine built in `recipes/how.py` and `GET /api/recipes/questions`; the app's page is built behind `wideSetUp` (`RecipeHowFields`, the How step), not yet seen in a build; extends `designer.path.what-matters-most`) — "What matters
  most?": speed · cost · quality · privacy, one choice, pre-filled from the places answer (privacy when only
  this Mac is ticked). Privacy means nothing leaves this Mac and the cloud question of
  `designer.path.cloud-question-on-the-page` stays unanswered; the other three break ties inside the noise band
  as section 7 says (`designer.path.what-matters-most` keeps predictability as the compare's label). Saved as
  `answers.how.matters`. *Test:* same file (privacy never writes `cloud_allowed`).
- `designer.how.access-derived-and-confirmed` [PARTIAL] (#6052; engine built in `recipes/how.py` and `GET /api/recipes/questions`; the app's page is built behind `wideSetUp` (`RecipeHowFields`, the How step), not yet seen in a build) — "What you have" is shown, not asked: this
  Mac's memory in one sentence (the route's own), the providers with a key saved, the Hugging Face token, each
  cluster signed in, each from `recipes/derived.py` and the places route, with Add a Key…, Add a Token…, Sign
  In… beside what is missing (the existing sheets). The person confirms with Continue; nothing on this line is
  stored in the project. *Test:* `test_how_access_is_derived.py` (the line is
  the derived route's; a saved key changes it; nothing is written to the answers).
- `designer.how.answers-pick-the-card` [PARTIAL] (#6052; engine built in `recipes/how.py` and `GET /api/recipes/questions`; the app's page is built behind `wideSetUp` (`RecipeHowFields`, the How step), not yet seen in a build) — the four answers choose which route card is
  proposed (`designer.path.choosing-is-a-default`): this Mac + privacy → (d); cloud + quality → (c); a cluster
  or Hugging Face + cost → (b); cloud allowed + a large archive (the volume rule) → (a). The chosen card says
  "proposed from your answers; change here"; the other cards stay. Changing an answer re-proposes; a card the
  person chose by hand is never re-proposed over. *Test:* `test_how_answers_pick_the_card.py`.
- `designer.how.teach-as-you-go` [GAP] (#6407, #6406, #5692; owner scenario 2026-11-08: the first 100 pages with Gemini, fine-tune a model on Hugging Face from those readings, then the rest with Kraken and MLX models on Hugging Face; manager rulings 2026-11-08) — How offers one more card beside the four questions' routes: **Teach as you go**, a staged plan across MANY pages, the distil route of `routes.py` made a plan with its gate: (a) N pages read with model A, the teacher (the How answers' cloud model); the person chooses PER RUN a covering sample or the first N in order, default covering, N editable, 100 proposed (`distill.collect.first-n-or-covering-sample` in `compute/distillation.md`); (b) fine-tune from those readings on the target the How "where" answer and the app's allowances give, this Mac or Hugging Face Jobs (`designer.teach.asks-whether-and-where-at-the-offer`, Step 16.3's place rule; provisional, owner to confirm: a transformers base on Hugging Face with an MLX copy for this Mac, `distill.student.transformers-base-on-hf-mlx-copy-local`); (c) a gate before the switch: the student's CER AND WER (`source.train.wer-beside-cer`, #6395) on held-out checked pages against the person's corrections as truth (Step 3.1, `designer.check.corrections-become-the-reference`) within the project's noise band (Step 6.1, `designer.teach.switch-within-band`); (d) the remaining pages read with the student on its place; never a model pass rerun (`activity.read.page-read-once`: the N teacher-read pages are not read again). The card shows the four stages with their figures from the route (`sample_pages` × the teacher's per-page price; the target's price per hour; zero for the rest on this Mac) and the gate's bar, and says the risk in plain words (Step 18.7). Everything happens in the app: no hand-built sets or files; the set is `training/kraken_set.py`'s, the start is `train_offers.start_when_ready`'s, the spend is under the project's Hugging Face cap (`spend_this_month`). No new route: the plan is the recipe's steps with places and a gate step, run by the recipe runner. Acceptance: choosing Teach as you go with "first 100" on a 1,000-page project shows the four stages priced; Start reads pages 1–100 with the teacher and no other page, trains, measures, and either switches (the switch recorded, `designer.run.switch-recorded`) and reads 101–1,000 with the student, or stops at the gate saying which measure fell short and offers to read on with the teacher at its cost. *Test:* `test_teach_as_you_go_end_to_end.py` (not yet written, one test with `compute/distillation.md` Stage 1), `test_how_offers_teach_as_you_go.py` (not yet written).
- `designer.how.teach-as-you-go-gate-says-both-measures` [GAP] (#6407, #6395) — the gate's verdict names CER and WER side by side with the bar ("3.1% characters, 9.8% words; the bar is the current reader's 4.0% ± 0.6"), passes only when CER clears the band (WER shown, as `source.train.wer-beside-cer` rules), and a fall-short says which and offers the two ways on: more labelled pages (another N with the teacher, priced) or the teacher for the rest (priced). *Test:* `test_teach_as_you_go_end_to_end.py` (not yet written).

**Improves — the risks in plain words (the maintainer, 2026-10-30; DRAFT).** `designer.rank.predictability-in-words`
says a model's trade-off on its row; these say the same once, where the choice is made, and on the plan.
- `designer.how.risks-in-plain-words` [PARTIAL] (#6052; engine half built: the `how-risks` topic in `topics.yaml`, served by `GET /api/topics`; the page's block is not) — the page carries one short block, the engine's
  text (`recipes/seed/topics.yaml`, as `prep.setup.how-it-works-is-the-engines-sentence` does), with "Learn more"
  → manual "Reading the numbers": *"Some steps are deterministic tools: given the same page they do the same thing
  every time, and when they are wrong they are wrong in plain sight (a line missed, a word misread). Models that
  read fluently can also invent: a word that is not on the page, a spelling 'corrected', a line skipped without
  a gap. Fichero measures this as the insertion rate and shows it beside accuracy. Steps feed each other: a
  line the layout step missed is never read, a name the reader got wrong is the name the Names step finds, so
  an early error carries through the chain. Check the earliest steps first."* Shown on every project, not only
  when a large model is chosen. *Test:* `test_risks_text_is_the_engines.py`
  (the text is served by the engine; the app has no copy).
- `designer.how.chain-risk-on-ready` [PARTIAL] (#6052; engine half built in `recipes/chain_risk.py`, `GET /api/recipes/chain-risk`; Ready shows it, 2026-11-04) — Ready says, in one line per model step, what feeds *Built (app, 2026-11-04, Swift not compiled here): Ready reads `GET /api/recipes/chain-risk` for the plan's steps (`RecipeSetupStore.loadChainRisk`, `RecipeStepChainLine`) and shows the engine's line under each step, with "Check first" where it says so.*
  it and what it feeds ("Read takes the lines Find Lines found; Names, Dates and Statements take what Read
  wrote"), and marks the steps whose errors carry furthest (the earliest model steps) with "check first". The
  line is the engine's, from the job registry's reads and writes (`source.recipe.steps-work-alone-in-order`).
  *Test:* `test_chain_risk_on_ready.py`.
- `designer.how.what-to-check` [PARTIAL] (#6052; issue to file on approval) — the run's summary (`recipes-run.journey.finish-summary`)
  gains one block, "What to check": for each model step that ran, the pages the engine is least sure of (lowest
  certainty for a CTC reader; highest insertion rate against Kraken's reading, or the lines the order check
  re-asked, for a vision-language reader), at most five, opened in the Reader by one press; a deterministic step
  lists its proposals instead (`prep.check.worklist-of-proposals-and-a-sample` (G)). *Test:*
  `test_what_to_check_after_a_run.py`. Built 2026-11-02 (engine): `recipes/what_to_check.least_sure` names up to five pages by the lowest mean
  certainty of their read lines, in the run summary's `what_to_check`, when Read ran; a vision-language reader's pages (insertion rate, order check)
  and a deterministic step's proposals have no figure yet and are not listed. The app (Swift, not compiled): the Read card lists them as buttons that open the page (`ActivityDetails+ToCheck.swift`, `ToCheckRowsTests.swift`). Left: the other readers' figures.

**Improves.**
- `designer.path.cards-are-the-routes` [MISSING] (#6052) — the page shows the routes from `routes.py`
  as cards, side by side, extended with two routes (Hugging Face then cluster; local only), each with
  the routes' own cost, time and accuracy figures and their measured / estimate / unknown marks; there
  is no second estimator. A figure the routes cannot give reads "not measured for this language yet".
- `designer.path.choosing-is-a-default` [MISSING] (#6052) — choosing a card makes that route the
  project's path: a set of defaults the later pages follow and say they follow ("from your path; change
  here"); the other routes stay visible on this page. Projects that predate the page have no path,
  nothing is detached, and the page is offered once.
- `designer.path.cloud-question-on-the-page` [MISSING] (#6052) — the existing pages-may-leave question
  is shown on the page itself, unanswered; a path never answers it. A card that needs pages to leave
  stays incomplete, with "answer above to use this path", until the person answers yes.
- `designer.path.card-live-only-where-allowed` [MISSING] (#6052) — a card whose places the app does
  not allow, or that are not set up (no cluster key and sign-in, #5238; Hugging Face at a $0 cap; no
  provider key), is greyed with the engine's reason and a link to What Fichero runs or Settings; a
  project is never made looser than the app.
- `designer.path.caps-proposed-not-written` [MISSING] (#6052) — a path proposes a spend figure beside
  its estimate; the cap is written only when the person confirms the typed figure (the Hugging Face cap
  stays $0 until then; the project cloud cap, once built, the same).
- `designer.path.sets-teaching-defaults` [MISSING] (#6052) — a path sets the teaching defaults
  (whether, after how many checked lines, where) without asking; they are shown and asked only at the
  offer (section 10). Paths (a) and (d) default to teach; (b) and (c) to not.
- `designer.path.what-matters-most` [MISSING] (#6052) — one choice, pre-filled from the path: speed ·
  cost · quality · predictability; it breaks ties inside the noise band (section 7) and picks the label
  the compare leads with (section 8).
- `designer.path.card-text` [MISSING] (#6052) — each card shows the wording below, then its figures, and
  "Learn more" → manual "Ways of working". Proposed wording (String Catalog; the figures are the routes'):
  - **(a) Start with a large model, then a small one.** *"A large cloud model (Claude, Gemini, GPT)
    reads your first pages. You check them. Fichero teaches a small model on your checked lines and
    switches to it when it reads as well; the long runs can then go to a cluster (ACENET) or to Hugging
    Face Jobs. Suits a large archive in a hand no shipped reader knows. Cost: highest at the start,
    then no cloud fees per page. Time: your checking of the first pages, then fast. Predictability: the
    cloud model may insert or 'correct' words on the first pages, so checking them matters; the model
    you teach reads only what is on the line. The teacher's terms of use are shown before training.
    Next: Compare runs on three pages, then the first paid pages, then a Teach a model… offer."*
  - **(b) Start on Hugging Face, move to the cluster.** *"Your readers run on Hugging Face from the
    start (by the hour, under your cap), and the whole run moves to ACENET when the recipe is settled.
    Suits a project with an ACENET allocation and no wish to run on this Mac. Cost: hourly on Hugging
    Face, then your allocation. Time: depends on the queue; Fichero shows it. Predictability: that of
    the models you choose. Next: the Hugging Face place is checked, then Compare."*
  - **(c) A large cloud model throughout.** *"Every page is read by a large cloud model. Suits a small
    project, or a hand where a cloud model wins the comparison by a wide margin. Cost: per page,
    predicted before Start and watched against your cap. Time: minutes per hundred pages.
    Predictability: lowest; a cloud model reads fluently and sometimes inserts or regularises text; the
    insertion rate is shown beside its CER. Next: Compare, then Start."*
  - **(d) This Mac only.** *"Nothing leaves this Mac. Kraken and the small models that ship with
    Fichero or that you download do the reading. Suits material you may not send away, or a script with
    a good shipped reader. Cost: no fees; this Mac's time and power. Time: hours per thousand pages on
    this Mac. Predictability: highest; a Kraken reader reads only what is on the line, though it may
    misread a word. Next: Compare the shipped readers, then Start; you can teach a better local model
    on your corrections later."*

### 4b. The defaults table: from the answers to the recipe's steps, models and caps (the maintainer, 2026-10-30; DRAFT)

**Exists.** Setup's rules choose a card per step from the material (`source.recipe.reader-pick-from-the-material` (P),
`assemble._rank_key`/`_choose`), the volume rule places training (`source.recipe.volume-rule` (P)), faded pages add
the preparation step (`source.onboard.auto.prepare-damaged-images` (P)), and a path sets teaching defaults
(`designer.path.sets-teaching-defaults`). The rules are spread over `assemble.py`, `prepare.py`, `start.py` and
`routes.py`, and none says on screen *why* a default was chosen.

**Improves.**
- `designer.defaults.table` [PARTIAL] (#6052; engine half built in `recipes/defaults.py`, `GET /api/recipes/defaults`; not yet applied by `assemble.py`; Ready shows the reasons (app, 2026-11-04), the stage pages do not yet) — one vendored table, `recipes/seed/defaults-by-answers.yaml`, *Built (app, 2026-11-04, Swift not compiled here): Ready reads `GET /api/recipes/defaults` (`RecipeSetupStore.loadDefaultsWhy`) and lists each default's reason and the answers that chose it under "Chosen because" (`DefaultWhy`, `ReadyReadsTests.swift`); the stage pages do not show it yet, and nothing is applied or written.*
  maps the answers (kind of material, condition, where, model kind, what matters, the volume) to the recipe's
  defaults: which stages are ticked, each step's default candidate kind (CTC reader, vision-language reader,
  Apple's recognition, a cloud or local place), whether Review is on, the preparation steps, and the proposed caps.
  Each row has a `why` sentence. The engine applies it in one place (`assemble.py`), after the filters and before
  the rank, so `source.recipe.reader-pick-from-the-material` and the prepare-step rule become rows of it. The
  first rows (to be checked against the maintainer's judgement, open question 6):

  | Answers | Default steps | Default model kind | Cap proposed | Why (as shown) |
  |---|---|---|---|---|
  | print or typescript, clean, this Mac | Find the layout, Read, Search | Apple's recognition or a shipped Kraken print reader; no Review | none (free) | "clean print reads well with a free reader that never invents text" |
  | handwriting, clean, this Mac, privacy | Find the layout, Read, Review (unsure lines only), Search | Kraken reader for the script and period; Review by a local model if one fits | none (free) | "nothing leaves this Mac; the unsure lines are checked again" |
  | handwriting, faded or stained | + Prepare Images (contrast, stain flattening) | as above | as above | "faded ink reads better after contrast; the original is kept" |
  | handwriting, show-through | + Prepare Images (show-through suppression) | as above | as above | "writing from the other side is dimmed before reading" |
  | handwriting, tight binding | + Prepare Images (flatten toward the gutter) | as above | as above | "text that curves into the gutter is flattened first" |
  | handwriting, torn or water damage | + Leave Out (damaged areas), Review on | vision-language reader offered beside the CTC one, compared | the route's estimate | "a damaged page needs a reader that uses context, and a check for what it invents" |
  | cloud allowed, quality | Read by a large cloud model; Review off | large vision-language model | the route's estimate, rounded up to the dollar | "a large model reads a hard hand best; the cap is Fichero's best estimate of the cost, and it learns from what your project has booked" |
  | cloud allowed, cost, large archive | path (a): cloud first pages, then Teach | as the path | the first pages' estimate | "the cloud reads the first pages, your corrections teach a free model for the rest" |
  | a cluster or Hugging Face, cost | path (b) | the person's readers there | the Hugging Face cap at the route's estimate | "long runs go where your allocation is" |

  *Test:* `test_defaults_table.py` (every row loads; every answer combination
  the questions can produce hits exactly one row or the fallback row; the chosen defaults match the table for
  each row above).
- `designer.defaults.says-why` [PARTIAL] (#6052; engine half built in `recipes/defaults.py`, `GET /api/recipes/defaults`; not yet applied by `assemble.py`; Ready shows the reasons (app, 2026-11-04), the stage pages do not yet) — every default a stage page or Ready shows carries the
  table row's `why` in grey under it ("chosen because: faded ink, this Mac only"), served by the engine with
  the plan; a default with no row says "Fichero's usual default". *Test:*
  `test_defaults_say_why.py`. Built (app, 2026-11-04, Swift not compiled here): Ready lists each default's reason and the answers that chose it under "Chosen because" (`RecipeDefaultsWhyView`, `DefaultWhy`, `ReadyReadsTests.swift`); the stage pages do not show it yet.
- `designer.defaults.person-wins` [PARTIAL] (#6052; engine half built in `recipes/defaults.py`, `GET /api/recipes/defaults`; not yet applied by `assemble.py` or shown in the app) — a choice the person made on a stage page, in the
  finder or on Ready is never replaced by the table when an answer changes; the changed default is offered
  beside it ("your answers now suggest X; keep Y?"), as `source.onboard.step-choice-overrides-the-pick` keeps a
  choice over the rules. *Test:* `test_defaults_never_override_a_choice.py`.
- `designer.defaults.caps-proposed-from-the-table` [PARTIAL] (#6052; engine half built in `recipes/defaults.py`, `GET /api/recipes/defaults`; not yet applied by `assemble.py` or shown in the app) — the table's cap column is what
  `designer.path.caps-proposed-not-written` proposes; it is written only on the person's confirmation of the
  typed figure (section 11b). *Test:* in `test_defaults_table.py` (a proposal writes nothing).

### 5. Choose the Stages

**Exists.** Stages are chosen first; goals are shortcuts; needed stages are ticked and say why; the
list is the engine's (`source.onboard.stages.choose-first` (P), `source.onboard.stages.stages-list-from-the-engine` (P),
`source.onboard.stages.goals-are-shortcuts` (P), `source.onboard.stages.needs-are-ticked` (P),
`source.onboard.stages.train-and-ready-last` (P)). The stages today: Clean Up Images · Find Regions · Find
Lines · Read · Translate · Organise · Names · Statements · Dates & Times · Passages · Structured Data ·
Search, then Train and Ready. No change proposed to the list, except the Review stage below.

### 6. The stage pages: what each stage produces, and the workflow that does it

**Exists.** Each page says what it does, who runs it, asks its own questions and shows its result on 3 to
5 of the person's pages (`source.onboard.stages.page-says-what-it-does` (P), `source.onboard.stages.page-who-runs-it` (P),
`source.onboard.stages.page-asks-its-questions` (P), `source.onboard.stages.samples-proposed` (P),
`source.onboard.stages.sample-result` (P), `source.onboard.stages.explanation-always-shown` (P)).

**Every step is a workflow; a person's own workflow can be a step.** Exists: each job runs its shipped
preset with the step's model as the override (`source.recipe.makes-a-workflow` (P), `WORKFLOW_FOR_JOB`);
presets are locked in the editor (`workflows.canvas.locked-preset-is-read-only`); a node's model list is
Settings' (`nodeconfig.model.same-list-as-settings`); recipes should run library-pinned
(`workflows.defaults.recipes-user-level-runs-library-pinned` (G)); duplicating a preset
(`workflows.defaults.duplication-regrown` (G)); a node shows what it reads and writes
(`workflows.canvas.node-shows-reads-and-writes` (G), `workflows.bar.selection-projected-through-accepted-inputs`).
Improves:
- `designer.step.names-its-workflow` [MISSING] (#6052) — each stage page says in one grey line which
  workflow carries the step ("runs as the shipped workflow Read lines with Kraken") with "Open in the
  editor", read-only for a preset; the node's config shows the same model and settings as the page.
- `designer.step.own-workflow-as-a-candidate` [MISSING] (#6052) — a workflow the person built is listed
  under "Your workflows" for a step when its accepted inputs and declared writes fit the job's registry
  record, with the fit in words ("takes lines, writes a reading pass: fits Read"); one that does not fit
  is under Other with the reason; a fitting one is measured and compared like any candidate.
- `designer.step.adjust-in-the-editor` [MISSING] (#6052) — "Adjust in the editor" copies the preset
  into the project's library (not user-level, so the recipe travels with the project), opens it
  editable, and the step points at the copy by id; Ready names the copy.

**Clean Up Images.** Exists: `prep.find-the-page` (P), `prep.split-at-the-gutter` (P),
`prep.straighten-and-flatten` (P), `prep.never-changes-the-original`, `prep.methods-are-cards-the-recipe-chooses` (G).
No change proposed.

Improves (leave-out, #6070):
- `designer.clean.leaves-out-non-text` [PARTIAL] (#6070; first slice built: the Leave Out stage between Find Lines and Read, on by default in a plan that finds and reads lines, free and on this Mac; its rules are too small / off the page / likely bleed-through in `recipes/leave_out.py` (`test_leave_out.py`), each mark says why in the segment's `left_out` metadata and sets `is_furniture`, the one left-out flag Read and the Reader skip. *Not built:* the page MASK from find-the-page (a document's own `page_box` metadata is the page, and with none nothing is off the page), a cloud vision check per region, stamps and decoration, an account of the stage in the run's status) — a Set Up stage leaves out segments that are not text of the page: off the page edge (the scanner bed or black background), bleed-through from the other side, damaged or torn areas, and stamps or decoration if asked. Lines are kept but marked left out, never deleted, so Read skips them and a person can bring one back. Candidates: geometry rules from the page mask (`prep.find-the-page`), Kraken baseline confidence, a vision model asked per region; measured like the other stages.
- `designer.clean.damaged-mark` [MISSING] (#6070) — a page or region can carry a 'damaged' mark, linked to Certainty and Damage in the Inspector (already exists there).

**Find Regions and Find Lines.** Exists: both default to Kraken `blla` (`prep.regions.open-default` (P),
`prep.regions.one-find-regions` (P)); the YOLO DocLayNet card (`prep.yolo.regions-card` (P)); line finders
are a candidate list (`source.recipe.line-finders-are-a-candidate-list` (P),
`source.recipe.apple-finds-lines-on-print`); mixed writing per region
(`source.onboard.stages.mixed-writing-per-region` (P)). Improves:
- `designer.layout.one-kraken-pass` [PARTIAL] (#6052, #6014) — when both finders are Kraken, one `blla`
  segmentation gives regions and lines; Find Lines and Read never segment again. (Built: one call
  returns both and each line keeps its region; not built: the bake-off and runner re-call the segmenter.)
- `designer.layout.region-model-row` [MISSING] (#6052) — Find Regions gets one row, "Blocks found by":
  Kraken (one pass, default), the YOLO layout model already selectable as a card, or a cloud vision
  model with its cost per page.
- `designer.layout.vlm-finds-regions-and-lines` [GAP] (#6487, #6403, owner 2026-11-10: choose a vision-language model for Find
  Regions and Find Lines) — each step has its OWN model list, drawn from the one catalog (#4307), with the cloud permission and spend
  rules and a cost per page: Find Regions offers Kraken, YOLO layout models and vision-language models; Find Lines offers Kraken,
  Apple's finder where it applies and vision-language models. "Find models" lists the vision-language ones for both,
  each said in plain words ("a large model finds the lines; it may miss faint ones; US$ per page"). The picked model is
  recorded on the regions and lines it made. *Test:* `test_layout_models_per_step.py` (each step's list holds only what it can take;
  a cloud model is offered only when cloud is allowed; not yet written).
- `designer.layout.vlm-corrects-regions-and-lines` [GAP] (#6487, #6284) — two optional steps after Find Lines, Correct Regions and
  Correct Lines, each with its own model list as above. A free measure comes first (ink outside the boxes, overlaps, a
  line crossing a region edge); a vision-language model is asked only about the pages the measure flags. It PROPOSES edits (add,
  remove, merge, split, move) shown in the Preview as a pending set the person accepts or rejects as a whole or one at a time;
  nothing is changed silently, an accepted edit is one audited, undoable change, and the model is recorded. A page with no
  flag costs nothing. *Test:* `test_layout_corrections_are_proposals.py` (a proposal changes nothing until accepted; one undo
  reverts it; an unflagged page makes no model call; not yet written).
- `designer.layout.lines-per-block` [MISSING] (#6052, #6014) — with a YOLO or cloud region model, each
  block is cropped and Kraken's line finder runs per block; lines keep their block; reading order is
  blocks in the model's order then lines top-down, blocks right to left for right-to-left scripts.
- `designer.layout.segmenters-searched` [MISSING] (#6052) — the online search for these stages includes
  Kraken segmentation models (Zenodo through htrmopo, `kind: segmentation`) and object-detection
  models with a `.pt`/ONNX file as runnable YOLO cards; where nothing can run, the engine's sentence
  says so (appendix, fact 3).
- `designer.layout.measures` [MISSING] (#6052) — the measures are line recall and extra lines
  (`bakeoff.score_lines`) and, where region truth exists, mean best IoU per region with a class recall;
  the compare says "lines found 212 of 218 · 3 extra · blocks IoU 0.81 · 4 s/page".
- `designer.layout.one-page` [MISSING] (#6052) — Find Regions and Find Lines are one page, "Find the
  layout", with one drawn result (ruled 2026-10-24).

**Read.** Exists: one candidate list per step, a step lists only what it can take, and **a page reader on
this Mac (a local vision model) is not a line step's candidate, but Apple's recognition is: it reads single lines (#6071)**
(`source.find.one-candidate-source` (P), owner ruling B 2026-10-24, `discovery.does_the_step`); scripts
first (`source.recipe.script-reader-first`, `source.recipe.no-cross-script-reader`); period weighs
(`source.recipe.period-weighs-in-the-reader-rank`); cloud readers get Kraken's line pictures, one call a
page (`source.recipe.cloud-reads-lines-per-page` (P)); large cloud readers are compared on the try pages
(`source.recipe.reader-tiers.frontier-on-the-try-pages` (P)); the tier order with no measurement
(`source.recipe.reader-tiers` (P)); Apple's recognition is for modern writing
(`source.recipe.apple-vision-is-for-modern-writing`); the certainty bar and the unsure-lines variant
(`source.recipe.kraken-reads-cloud-corrects-unsure` (P), `source.recipe.kraken-then-cloud-unsure-lines` (P),
`source.recipe.certainty-is-calibrated` (G)). Improves:
- `designer.read.measures` [PARTIAL] (#6052) — Read's measures are CER (WER beside it) on the checked
  or imported lines under the project's policy, the diplomatic policy beside the headline
  (`training.eval.policies-named` (P), `training.eval.wer-beside-cer` (P)), and the insertion rate (section 7).
- `designer.read.certainty-question-stays-here` [PARTIAL] (#6052) — the certainty bar stays Read's one
  question; the "a cloud model corrects the unsure lines" choice is offered once, on the Review page,
  not also on Read's menu (appendix, fact 5).

**Review (proposed new stage, after Read, before Translate).** Exists: Correct is a job inside Read with
a page-level prompt and no reasons (`source.recipe.kraken-reads-cloud-corrects-unsure` (P);
`review_profiles.py`, shipped profiles with three lenses); reviews get the project's names
(`source.job.review-uses-the-projects-names-and-places` (P)); a correction lands on lines
(`source.job.correct-onto-lines`, `source.job.correct-re-asks-per-line-when-it-does-not-tie`). Improves,
first slice:
- `designer.review.own-stage` [MISSING] (#6052) — Review is a stage of its own (job `review-lines`);
  `correct` and the unsure-lines variant move into it; spelling regularisation stays Translate's.
- `designer.review.proposals-are-a-separate-pass` [MISSING] (#6052) — the reviewer writes a separate
  pass (`provenance_kind=model`, `transformation="review:<kind>"`) holding per line the proposed text, a
  reason in a few words, a confidence and the unsure spans; the person's reading is never overwritten;
  the Inspector shows the proposal beside the reading with Accept per line.
- `designer.review.one-shipped-kind` [MISSING] (#6052) — the first slice ships one kind, the
  palaeographer's review (line level, from `seed/review-profiles`), chosen by `review_profiles.choose`.
- `designer.review.measure-is-gain` [MISSING] (#6052) — Review's measures are the CER gain of the
  reading with every proposal accepted against the reading alone, and the precision of the proposals.
Later slices (not the first): more kinds (proof-reader against an edition, letter forms and
abbreviations; the person's own as YAML in the library), a page level, editable instructions seeded
from the kind, a default kind per kind of project; each will be its own id when scheduled.

**Translate, Organise, Names, Statements, Dates & Times, Passages, Structured Data, Search.** Exists:
`source.onboard.stages.normalise-and-translate` (P), `source.onboard.stages.organise-tried-on-a-run` (P),
`source.onboard.stages.kinds-are-open-ended` (P), `source.onboard.stages.passages-says-what-it-does` (P),
`source.job.find-statements.candidates` (P). Improves:
- `designer.stage.measure-table` [MISSING] (#6052) — one short table, served with the stages, names
  each stage's measure and ground truth: Find Regions → region IoU and class recall against marked
  layout; Find Lines → line recall and extras; Read → CER, WER, insertion rate against checked or
  imported lines; Review → CER gain and precision; Translate → agreement with checked lines; Names →
  precision and recall against checked names; Statements → F1 against checked triples; a stage with no
  measure yet says so.

### 7. On every stage page: candidates found, filtered, then ranked by one rule

**Exists.** One candidate list per step from the shipped cards, the models here, Kraken's repository,
HTR-United, Hugging Face and remote endpoints (`source.find.by-need` (P), `source.find.wide-every-time` (P),
`source.find.one-candidate-source` (P), `source.find.zenodo-through-htrmopo`,
`source.find.htr-united-and-tessdata` (P), `source.find.key-offers-frontier-models` (P),
`source.find.models-that-run-remotely` (P), `source.find.worth-listing-engine` (P),
`source.find.online-search-is-a-job` (P), `source.find.online-search-per-step` (P)); filters then a rank
(`source.recipe.candidates-filtered-then-ranked`, `source.recipe.script-reader-first`,
`source.recipe.period-weighs-in-the-reader-rank`, `source.recipe.reader-pick-from-the-material` (P),
`source.recipe.candidates-fallback-chain` (P)); model and place ranked as a pair (`ai.where.rank-pairs` (P),
`ai.where.step-names-a-pair` (P)); cloud cards need permission until allowed (`source.onboard.pages-may-leave` (P),
`source.find.cloud-card-says-it-once` (P)); Loove coverage is a Settings matrix with no link to recipes
(`source.recipe.loove-tokenizer-only` (G); `ai/ai-settings.md`, "Language coverage"); the finder opens
from a step (`source.find.choose-a-model-opens-the-finder` (P), `source.onboard.stages.page-lists-found-models` (P),
`source.onboard.stages.step-names-its-model` (P)); nothing dropped silently (`ai.where.never-dropped-silently` (P)).

**Improves — filters (before any rank).**
- `designer.filter.fit-first` [PARTIAL] (#6052) — script, language, period and material are filters,
  applied before the rank as today: a candidate made for another script is out; one made for another
  period is listed under "Other periods", never ranked among the fits. A benchmark row never lifts a
  candidate past these filters.
- `designer.filter.coverage-band` [MISSING] (#6052) — a text or vision-language model's Loove coverage
  for the project's languages and scripts, and a Kraken codec against the glyph inventory, become a
  `Card.coverage` band (covered · unknown · poor) at discovery; the heuristic coverage is "unknown".
- `designer.filter.refuses-unwritable-characters` [MISSING] (#6052) — a candidate that can never output
  characters the ground truth actually uses (MUFI private-use, Newa outside the BMP, polytonic
  combining marks) is refused by the hard constraints with the count said ("cannot write 14 of your
  characters"), before any paid call.
- `designer.filter.ruling-b-every-local-page-reader` [PARTIAL] (#6052) — every page reader on this Mac
  (Apple's recognition, the MLX vision model, and Tesseract where its card names only the page job) is
  measured and listed on the page-reading step only, never on `read-a-line`; `does_the_step` is the one
  rule for the list, the compare and the benchmark alike.

**Improves — the rank.**
- `designer.rank.one-rule-every-stage` [PARTIAL] (#6052) — among the candidates that pass the filters,
  every stage ranks by the same order: (1) measured on the person's pages, (2) the vendored measured
  default for this language, script, period and material (section 8), (3) coverage band, (4) tier,
  (5) what matters most from the path, then cost and speed. The rule is `assemble._rank_key`, extended;
  the stage's measure (`designer.stage.measure-table`) fills slot 1 and its table slot 2.
- `designer.rank.frontier-order-is-the-fallback` [PARTIAL] (#6052) — the hand order of large cloud
  model families (`discovery.frontier_rank`) is used only for a candidate with neither a measurement
  nor a benchmark row.
- `designer.rank.insertion-rate` [MISSING] (#6052) — the insertion rate is inserted **characters** per
  hundred reference characters, from the same edit distance as CER, computed for every reader
  (Kraken included) wherever CER is, and shown beside it ("CER 4.2% · inserts 0.1%").
- `designer.rank.run-to-run-agreement` [MISSING] (#6052) — the same lines read twice and compared, as a
  benchmark-table column only (it doubles a cloud candidate's cost, so the auto-compare never measures
  it); a row with it says "agrees with itself on 99% of lines".
- `designer.rank.lines-changed-beyond-cer` [PROPOSED] (#6052) — the share of lines whose edits form a
  dictionary word absent from the truth; waits on word lists per language (open question 4).
- `designer.rank.predictability-in-words` [MISSING] (#6052) — every candidate row states the trade-off
  in words from its kind ("reads only what is on the line; may misread a word" for a CTC reader; "reads
  fluently; may insert or regularise text" for a vision-language model) and, unmeasured, "not measured
  for predictability".
- `designer.rank.reasons-in-words` [PARTIAL] (#6052) — every row says why it sits where it sits, with
  provenance: "CER 4.2% on your 3 pages · inserts 0.1%"; "CER 6.1% on BnF fr. 412, a different
  manuscript in the same language; not yet measured on your pages"; "coverage good, from Loove"; "made
  for Gothic cursiva, 15th c.".
- `designer.rank.labels-from-the-engine` [MISSING] (#6052) — best, cheapest, fastest and most
  predictable are fields of the served candidate list, set only where measured against a person's
  reading (section 8); the app renders them and never computes them.
- `designer.rank.one-visible-selection` [PARTIAL] (#6052) — the chosen row stays in its tier with a
  leading radio mark and a tinted row, not moved to a head group (appendix, fact 6).
- `designer.rank.cloud-permission-said-once` [PARTIAL] (#6052) — the cloud-permission line is shown once
  above the cloud tier, not on every card (appendix, fact 7).
- `designer.rank.nothing-found-from-the-engine` [PARTIAL] (#6052) — the nothing-found sentence comes
  from the engine for every job, never hard-coded in the app (appendix, fact 8).
- `designer.rank.finder-for-every-model-step` [PARTIAL] (#6052) — "Choose a model…" opens the finder
  for any step whose job needs a model, not only the reading jobs; the download / choose-cloud /
  choose-model fix buttons collapse into that one press (appendix, facts 1, 4, 5).
- `designer.rank.searches-on-open` [PARTIAL] (#6052) — the finder searches online by itself when it
  opens for a step that has a search (as integration builds it, 1c008843d, d9a1cd231) and says what it
  found; the press is "Search again"; a job with no search disables the press with the reason.

- `designer.model.every-model-step-chooses` [PARTIAL] (#6168, #6167, #6173; #6254, #6258) — built (41ad5eec9, 575cdb87b): every step whose job
  `needs_a_model` offers Choose a Model… (engine test `test_every_model_step_says_it_needs_a_model_and_the_finder_lists_more_than_one`; the Swift
  test is written but not yet run). Not built: the chooser showing each way's cost, time and place for Statements, Entities and Leave out, and the
  walk-the-registry test. Full text: the shared "Which model does it"
  chooser is offered for EVERY stage that runs a model, none left out (Statements, Entities and Leave out
  included): the ways to do the stage, each with its cost, its time and where it runs (this Mac with Apple or
  MLX, Kraken, a local model, a cloud model, Hugging Face Jobs, a cluster), the default marked, the choice
  saved in the plan and used by the run. A stage with no model (pure rules) says so. Pinned by a test that
  walks the jobs registry and fails for any model-capable job without a chooser.
- `designer.model.chooser-is-one-component` [MISSING] (#6168) — there is ONE chooser, engine list and app
  view, shared by every stage; a stage does not carry its own copy, so a new way to run a job appears in
  every stage that can use it at once.
- `designer.model.one-resident-local-model` [MISSING] (#6167, #6168) — never two local models loaded at
  once: a stage that needs another local model swaps (or waits for the stage before it) and the run says
  so in words; two stages that choose the same local model share it.
- `designer.model.where-it-runs-is-part-of-the-choice` [MISSING] (#6173) — where a stage runs (this Mac,
  Hugging Face Jobs, a cluster, a cloud model) is chosen in the same chooser as the model, never
  separately; pages leave this Mac only where the project allows and the cap holds, and a place that is
  not allowed is listed with the reason, never hidden.

### 8. On every stage page: measured on your pages, measured on the benchmark, compared by itself

**Exists.** The bake-off scores CER, WER and line recall on marked or person-made passes under named
policies, needs 100 checked lines on two pages and says so, and is the same tool as a stage's Compare
(`source.try.bakeoff-is-the-same-tool` (P), `source.try.bakeoff-hidden-until-corrected` (P),
`training.eval.one-scorer`, `training.eval.not-read-is-not-100`, `source.onboard.stages.compares-candidates` (P),
`source.onboard.stages.compare-results-per-model` (P), `source.onboard.stages.compare-names-its-models` (P)
(three compared, `COMPARED = 3`), `source.onboard.stages.try-progress-in-place` (P),
`source.onboard.stages.try-waiting-says-why` (P), `source.onboard.stages.samples-are-not-the-work` (P),
`source.try.never-over-existing` (P), `source.try.kept-and-rerunnable` (P), `source.try.use-this-scope` (P),
`source.try.compare-in-setup-works` (P), `ai.where.bakeoff-scores-any-place` (G)); the noise band is **0.5
CER points per model kind until measured** from three held-out splits of 15 or more pages, labelled
(`source.train.noise-band-per-project`, ruled Q6 2026-10-17; `training.regression.noise-band-one-number` (P));
the Try is pressed (`source.try.any-time` (G), `source.find.try-before-default` (G)); failure modes
(`training.errors.failure-modes` (G)). Nothing measured ships with the app.

**Improves — measuring.**
- `designer.measure.on-your-pages-first` [PARTIAL] (#6052) — a measurement on the person's pages
  (imported truth or checked lines) is slot 1 of the rank, labelled with its page count.
- `designer.measure.noise-band` [PARTIAL] (#6052) — the project's band is 0.5 CER points per model
  kind, said so, until measured; candidates inside the band are "as good as each other", and what
  matters most decides, in words. (The bake-off's one-point constant is the defect the training spec
  lists; this spec adopts the ruling.)
- `designer.measure.benchmark-table` [MISSING] (#6052) — `recipes/seed/measured-defaults.yaml` holds,
  per language, script, period and material row of the Test Corpus, for each candidate `does_the_step`
  allows on that step (the shipped Kraken readers that fit, the local page readers on the page step,
  Tesseract where its card names the job, the newest model of each keyed large-cloud family): CER
  (headline and diplomatic), WER, insertion rate, run-to-run agreement, seconds a page, measured spend;
  layout rows (line recall, region IoU); review rows (gain, precision). Loaded as `Card.cer_benchmark`;
  no default for a language without a row.
- `designer.measure.benchmark-provenance` [MISSING] (#6052) — every row names its set, page count,
  licence, policy, model id and version, date, price-list version and **who checked the truth**
  (`checked_by: person | model:<id>`; a model-checked set reads "against a model-checked reading").
- `designer.measure.benchmark-licence-gate` [MISSING] (#6052) — only sets whose licence allows it are
  vendored (the corpus rule: nothing NonCommercial or NoDerivatives ships in this AGPL repository);
  NonCommercial rows are measured locally and never shipped; images never leave the Mac for a set whose
  licence forbids it. The first four rows: Old French BnF fr. 412 (CC-BY-4.0), Medieval Spanish BnF
  Esp. 33 (CC-BY-4.0), NZZ Fraktur (Zenodo 3333627, CC-BY-4.0), Arabic Maghrebi RASAM/BULAC (Apache-2.0).
- `designer.measure.benchmark-built-by-script` [MISSING] (#6052) — the table is rebuilt by a script
  through the MCP/CLI tools on a test engine, never by hand; about US$15–30 for a full table, US$3–5 per
  family refresh.
- `designer.measure.says-what-it-cannot-measure` [PARTIAL] (#6052) — a stage that cannot measure says
  so plainly and names what would let it ("Compare measures against lines you have checked. Read a few
  pages first, then check about 100 lines on two pages"), never a count of corrected lines in a project
  with nothing read (appendix, fact 11).

**Improves — comparing.**
- `designer.compare.runs-by-itself` [MISSING] (#6052) — when a stage page opens with two or more
  listed candidates (not under Other), the engine starts that stage's try once, by itself, on the first 3
  sample pages with 3 candidates (`COMPARED`, unchanged); the press is "Compare again…".
- `designer.compare.local-only-until-truth` [MISSING] (#6052) — with no ground truth on the pages
  (neither imported nor checked lines), the automatic run includes **local candidates only**; a cloud
  candidate runs only on the person's press, with its cost said first. Cloud money is never spent by
  itself to buy readings that cannot be measured.
- `designer.compare.without-truth-shows-readings-only` [MISSING] (#6052) — without truth the result is
  the readings side by side, measured cost and time, and the predictability words; **no best label**,
  no agreement figure, and the line "Not measured against your reading yet; check lines to compare".
- `designer.compare.re-runs-when-answers-change` [MISSING] (#6052) — a change to the material answers
  re-runs the compare once the person leaves the page, counted against the same caps.
- `designer.compare.capped` [MISSING] (#6052) — a compare that includes a cloud candidate is priced first
  (`bakeoff.next_run`) and spends from the project cloud cap (`training.cost.app-and-project-caps` (G),
  build order step 6), with no cap of its own; the automatic run leaves out, and names, the dearest
  cloud candidate that would pass what is left, and a pressed Compare that would pass it asks first in
  a confirming dialog (ruled 2026-10-24).
- `designer.compare.side-by-side-text` [MISSING] (#6052) — the page image beside one column per
  candidate, text aligned to Kraken's lines, lines differing from the best highlighted and inserted
  words marked where there is truth; for the layout stages the blocks and lines drawn; the caption
  lines of counts go (appendix, fact 10).
- `designer.compare.labels-where-measured` [PARTIAL] (#6052) — with truth, the summary labels best
  (lowest CER beyond the band), cheapest, fastest and most predictable (lowest insertion rate); the
  path's what-matters-most is the lead label. (Built: best and cheapest in `bakeoff.recommend`.)
- `designer.compare.row-sentence` [MISSING] (#6052) — each row reads "CER 4.2% on your 3 pages ·
  inserts 0.1% · $0.02/page · 6 s/page · whole project $18, 2 h", each figure with its basis.
- `designer.compare.predicts-cost-and-time` [PARTIAL] (#6052) — the whole-project cost and hours are
  the measured per-page figures times the project's pages, basis said ("measured on 3 pages"); local
  candidates predict time from measured pages an hour (`training.ab.cost-and-time-beside` (P),
  `ai.where.estimate-names-the-place` (P)); the routes' estimate (section 4) is replaced by this.
- `designer.compare.person-chooses` [PARTIAL] (#6052) — the compare proposes; the person chooses with
  Use This One per column (`use-candidate`, unchanged); a step lists only what that press accepts.

### 9. Checking lines (new journey point; the step every measure depends on)

**Exists.** A line is corrected in place from the Reader or the Inspector with Correct this line
(`source.lines.correct-this-line-verb` (P), `reader.page.inline-transcription-editing` (G)); a reading is
checked against the page (`source.lines.reading-checked-against-the-page` (P)); a person's correction is
a pass of its own and is the training data (`source.train.on-the-persons-corrections`,
`source.train.human-checked-by-default` (G), `source.train.ground-truth` (G)); a check is a job and a
person checks the same way a model does (`source.check.run-is-a-job` (P), `source.check.person-checks-the-same-way`,
`source.check.model-never-a-person`); the bake-off counts checked lines (`source.try.bakeoff-hidden-until-corrected` (P)).

**Improves.**
- `designer.check.progress-in-words` [MISSING] (#6052) — the Read and Train pages, and Ready, show one
  line of progress toward each threshold: "62 of 100 lines checked on 1 of 2 pages; Compare can measure
  at 100", "62 of 500 for Teach a model…".
- `designer.check.which-pages` [MISSING] (#6052) — the sample pages the compare ran on are proposed
  first for checking ("check these 3 pages: every candidate has read them"), opened in the Reader from
  the stage page.
- `designer.check.corrections-become-the-reference` [PARTIAL] (#6052) — a checked line replaces any
  imported or model reading as the reference at once; the next compare and every row's slot 1 use it.

### 10. Train: the offer, as the project goes

**Exists.** Train is its own page, offered later and never automatic
(`source.onboard.stages.page-trains` (P), `source.recipe.train-never-automatic` (P),
`source.recipe.train-offered-once-ready` (P), `source.recipe.train-offered-per-step` (P),
`source.recipe.volume-rule` (P)); distillation (`distill.offered-not-default` (G),
`distill.collect.sample-covers-scope` (G), `distill.train.card-names-teacher` (G),
`distill.measure.against-people` (G), `distill.adopt.within-bar` (G), `distill.retrain.must-beat` (G),
`distill.licence.teacher-terms` (G), `distill.eval.held-out-checked-pages` (P), `distill.eval.cer-variants` (P));
trainers and places (`compute.tune.one-trainer-three-places` (G), `compute.tune.kraken-recognition` (P),
`compute.tune.lora` (P), `compute.tune.on-this-mac` (P), `compute.tune.input-is-a-training-set` (P),
`compute.tune.bakeoff-reads-become-training-lines` (G)); the model comes back as a card, adopted only when
chosen (`compute.tune.model-comes-back-as-a-card` (P), `compute.tune.not-default-until-chosen` (G),
`compute.tune.adopted-by-the-recipe` (G), `compute.tune.loop-is-one-visible-cycle` (G)); costs before
training (`training.place.cost-before-train` (G), `training.place.nothing-leaves-until-train`); A/B
(`training.ab.beats-current-by-noise-band` (G), `training.model.compare-on-more-pages` (P)).

**Improves.**
- `designer.teach.offer-when-ready` [MISSING] (#6052) — when the path's threshold is reached (default
  500 checked lines for a Kraken fine-tune, lines of 200 pages for a LoRA; or the volume rule's 5,000
  pages, whichever first), the Train page and a line on the stage page offer "Teach a model…" with the
  two candidates priced (distil from the cloud pick · fine-tune the shipped pick), the place from the
  path, the predicted saving, and the teacher's terms where a cloud model is the teacher.
- `designer.teach.asks-whether-and-where-at-the-offer` [MISSING] (#6052) — whether and where are asked
  here, once, pre-filled from the path; nothing trains until the person says yes.
- `designer.teach.explained` [MISSING] (#6052) — the offer's text, with "Learn more" → manual "Teaching
  a model as you go": *"As you check lines, Fichero can teach a smaller model from them. **Distil**: a
  large cloud model reads first, you correct, and a small model learns from the corrected lines; good
  when no shipped reader knows your hand. **Fine-tune**: a shipped Kraken reader learns your hand from
  your corrected lines; good when a shipped reader is close. Either way the new model is measured on
  pages it never saw, against the model you use now, and is offered, never switched in by itself. Cost:
  a cloud read of the first pages (distil only) plus training time: free and slow on this Mac, by the
  hour on Hugging Face, your allocation on ACENET. Predictability: a Kraken model you teach reads only
  what is on the line; a small vision model's insertion rate is measured before it is offered."*
- `designer.teach.measured-against-current-and-shipped` [MISSING] (#6052) — the taught model is
  measured on held-out checked pages against the current pick, the cloud model and the shipped
  readers, with the same scorer, band and insertion rate as section 8.
- `designer.teach.switch-within-band` [MISSING] (#6052) — within the band of the current pick the
  person is offered the switch for the rest of the run; otherwise the offer says why not.
- `designer.teach.costs-before-and-after` [MISSING] (#6052) — before: the cloud spend on the first
  pages, training time and place, the predicted saving ("no cloud fees for the remaining 3,400 pages;
  about 3 h of training on this Mac"); after: the taught model's cost per page and the measured spend.

### 11. Ready

**Exists.** Ready lists the plan plainly, grouped, naming each step's model and place, what runs by
itself and what will not run (`source.onboard.ready-speaks-plainly` (P), `source.onboard.ready.grouped-sections` (P),
`source.onboard.ready.words-not-engine-errors` (P), `source.onboard.ready.will-not-run-when-chosen` (P),
`source.onboard.auto.plan-shows-what-will-not-run` (P), `source.onboard.stages.step-names-its-model` (P),
`source.onboard.step-candidates-on-the-plan` (P), `source.onboard.step-choice-overrides-the-pick` (P),
`source.recipe.missing-model-offered` (P), `ai.where.ready-shows-the-pair` (G)).

**Improves.**
- `designer.ready.one-line-per-step-with-change` [PARTIAL] (#6052) — each step is one line: the chosen
  model, its place, its measured figure with provenance, its predictability words, the predicted cost
  and time, and Change… opening the one finder. The per-step candidate menus on Ready go (appendix,
  fact 9).
- `designer.ready.totals-against-the-route` [MISSING] (#6052) — Ready's total predicted cost and hours
  is the sum of the stages' predictions, shown against the route's figure in one line ("your path
  estimated US$120; measured on your pages, US$96").

### 11b. Budget (the maintainer, 2026-10-30, #6295, #6294; DRAFT)

**Exists.** Every project has a cloud spend cap, US$10 a month unless set (`ai.where.cloud-spend-cap` (P), #5943,
`answers.cloud_spend_cap_usd`, booked in `recipe/cloud-spend.json`); a cap below $0 is refused by
`answers.normalise`; the Start plan carries `cloud_cap` (`CloudCapLine`: cap, spent, remaining, estimate, `over`,
the unpriced models) and Start is refused while the estimate is over what the cap leaves, with one sentence,
"Raise the cap in Set Up, or choose a cheaper model" (`_cap_refusals`, `api/routes/system/recipes.py`); the app's
`RecipeCloudCapRow` on Ready holds the cap field and the words (uncompiled, 2026-10-28); the Hugging Face cap is
a second field (`source.onboard.spend-cap` (P)); the cap is saved through `project.save_setup` (audited,
undoable); the estimate prices a cloud line read at assumed tokens (`start.LINE_TOKENS_IN/OUT`, the page image
per provider `source.onboard.estimate-counts-the-image` (P), #6265) and nothing reads what the project has
already booked for the same model and job; a run at the cap is asked to pause and the person resumes
(`ai.where.cloud-spend-cap`, `designer.run.cap-stops-and-says`). **Found 2026-10-29 (#6295):** the refusal
reaches the last screen with no control that fixes it; the cap is changed outside the app. **Found 2026-10-28
(#6294):** a 16-page folder estimated $0.33 booked about 2.5× that, so a cap set at the estimate paused the run
at 9 of 16 pages.

**Ruled (the maintainer's ruling, 2026-10-30).** A Start may be blocked by either of two caps, the project cap or
the monthly cap, and the experience must let a person update **both** in place: in the Budget block on Ready, and
on the refusal and the paused-at-cap screens. Today a Start is blocked with no way to change either cap in the app.
There is **no margin multiplier**: the estimate says what Fichero thinks the run will cost, its best estimate with
its basis, and it learns from the project's booked costs (`designer.budget.estimate-from-booked-usage`).

**Improves.**
- `designer.budget.beside-the-estimate` [PARTIAL] (#6295) — Ready has one Budget block, above Start: the estimate
  for this run (`estimate.total_cost_usd`), Fichero's best estimate, with its basis, the project's cap for the month with what is spent
  and what is left (the `CloudCapLine` figures), and two editable fields, both changeable in place, so that
  whichever cap would block Start can be updated from the block: **this run, at most** and **this
  project a month, at most**. The Hugging Face cap joins the block as a third line when a Hugging Face place is
  in the plan. One block, not a field under a question. *Test:* `BudgetBlockTests.swift`
  (pure: the block's lines from a served plan; the fields hold the served caps; a cap below 0 cannot be typed),
  `test_budget_in_the_plan.py` (the plan carries both caps and the basis). Found partly built 2026-11-02 (#6295): the plan's `cloud_cap` line carries the monthly cap, spent, remaining, the project cap and its remaining, and the caps are changeable in place (`CloudCapLine`, `changeCloudCaps`). Built 2026-11-02 (engine): the cloud line also serves `proposed_run_cap_usd` (the estimate, no margin) beside `StartRequest.run_cap_usd` (`test_budget_in_the_plan.py`). Built 2026-11-02 (app, uncompiled): the cap row on Ready carries "This run, at most" (`RecipeRunCapField`, `RecipeSetupStore.runCapUsd` sent with Start, the engine's proposal as the prompt with "Use $N") and names the dearest step beside the refusal (`BudgetBlock`; `BudgetBlockTests.swift`). Built (app, 2026-11-04, Swift not compiled here): the block is one view above Start (`RecipeCloudCapRow`): both cap fields, "This run, at most", the words for what the caps leave, the basis rows, the fixes and "Change the model for <step>". Left: the Hugging Face line (the plan carries no Hugging Face cap yet; its field sits beside it in `RecipeMoneyAndPlaceFields`).
- `designer.budget.basis-per-step` [PARTIAL] (#6295) — the estimate is shown per step and per page, each with its
  basis in words: "Read: 16 pages × $0.021 a page, measured on 9 pages of this project" or "… assumed: one call
  a page of about 16 line pictures at Claude's listed rate"; the sum is the run's estimate. The basis is a
  field of the served estimate (`measured` · `assumed` · `unpriced`), never worked out in the app. *Test:*
  `test_estimate_basis_per_step.py`. Built 2026-11-02 (engine): each `StartEstimateRun` carries `basis_kind` (measured · assumed · free · unpriced), `basis_words`, `cost_per_page_usd` and `measured_pages` (`start._basis_words`; `test_estimate_basis_per_step.py`); the app words nothing. Built (app, 2026-11-04, Swift not compiled here): the per-step basis rows are in the Budget block (`CloudCapFix.basisLines`, shown by `RecipeCloudCapRow`).

- `designer.budget.estimate-from-booked-usage` [PARTIAL] (#6294) — once the project has booked calls for the same
  model and job (the usage rows `_record_usage` keeps, with their `place`), the per-page figure is the median
  booked cost a page over those calls, labelled measured with the page count; until then the token assumption,
  labelled assumed. A run's own booked cost replaces the assumption for its remaining pages, so a cap set at
  the estimate lets a run finish (#6294's case: after the first pages the estimate reads the booked figure). No
  margin is applied on top (the maintainer's ruling, 2026-10-30): the figure shown is Fichero's best estimate, its
  basis beside it, and the booked costs are how it improves.
  *Test:* `test_estimate_learns_from_booked_usage_6294.py` (fake usage rows
  at 2.5× the assumption: the estimate reads the measured figure, says "measured on N pages", and a cap set at
  the new estimate is not refused). Built 2026-11-02 (engine): `recipes/booked_cost.per_page` takes the median booked cost a page over the pages whose job rows booked priced calls of the same model and job; the estimate uses it (`measured`, with the page count) before the token assumption (`test_estimate_learns_from_booked_usage_6294.py`). Left: a run's own booked cost replacing the assumption for its remaining pages, mid-run.

- `designer.budget.run-cap` [PARTIAL] (#6295) — Start takes a cap for this run (`StartRequest.run_cap_usd`, kept on
  the run's row); the run's cloud calls are held against **both** the run cap and the project cap, the lower
  deciding, through the one spend hold (`llm/spend.py`); a run with no run cap is held by the project cap alone.
  The run cap is proposed at the estimate (the defaults table's cap column: the best estimate, assumed or
  measured, with no margin multiplier, the maintainer's ruling, 2026-10-30) and written only when the person confirms the typed figure
  (`designer.path.caps-proposed-not-written`). *Test:*
  `test_run_cap_holds_with_the_project_cap.py` (a run cap below the project's
  remaining refuses at the run cap; the project cap still refuses first when lower). Built (engine, 2026-11-04): `StartRequest.run_cap_usd` is kept on the run's row; the cap is held from the moment `_run` starts the run (not while it waits in the queue, so a run cancelled before it starts leaves none) and cleared at its end, or by Stop on its waiting row, unless it is deferred, which keeps the cap as changed and its baseline: `test_run_cap_is_held_from_the_run_start.py`, and that Start carries it from the request to the row: `test_start_carries_the_run_cap_6295.py`.
- `designer.budget.refusal-offers-the-fix` [PARTIAL] (#6295) — a Start refused for the cap says, in plain words,
  which cap refused (the project cap or the monthly cap), what the estimate is, what that cap leaves, and which step costs most; and the refusal carries typed fixes
  the app shows as buttons in the Budget block, each one press, with **both** cap fields editable in place on the
  same screen (the maintainer's ruling, 2026-10-30): **Raise the cap to $N** (N = the estimate, rounded up to the
  dollar, with no margin; the cap that is refusing, project or monthly);
  **Change the model for <step>** (opens the one finder on that step, `designer.rank.finder-for-every-model-step`,
  the cheaper candidates first with their cost a page); **Run fewer pages** (the number of pages that fit what
  the cap leaves, sent as a Start of the first N pages in Finder order, the maintainer's ruling, 2026-10-30: the
  pages are named as `documents` in the existing Start request, `source.recipe.folder-scoped-start`, with no new
  request field; offering "the folders that fit" is a later slice). The engine
  serves the fixes (`refusal.fixes[]`: `kind`, `step`, `raise_to_usd`, `pages_that_fit`); the app computes none.
  *Test:* `test_cap_refusal_offers_the_fix_6295.py` (each fix is served with
  its figure; the refusal names which cap refused; raising to N clears the refusal; the fewer-pages count fits what is left,
  and the Start it makes names the first N pages in Finder order as `documents`, nothing more),
  `BudgetRefusalFixTests.swift` (the three buttons from a served refusal). Built (engine, 2026-11-04): the refusal carries typed `fixes[]` (`CapFix`: kind, step, `raise_to_usd`, `pages_that_fit`) and the dearest step: `test_cap_refusal_offers_the_fix_6295.py`. Found partly built 2026-11-02 (#6295): the cap line serves `needed_cap_usd`, `needed_project_cap_usd`, `fewer_pages` and the refusal's own sentence naming which cap refused. Built since (engine, 2026-11-04): the typed `refusal.fixes[]` and the dearest step. Built (app, 2026-11-04, Swift not compiled here): the raise amounts and the first pages that fit are read from `fixes[]` (an engine that serves none is read from the line's figures), and "Change the model for <step>" opens that step's model finder (`CloudCapOffers`, `BudgetRefusalFixTests.swift`).
- `designer.budget.change-is-audited-and-undoable` [PARTIAL] (#6295) — raising or lowering either cap, from the
  field or from a fix button, is one audited action, `project.set_budget` (project, which cap, from, to, who,
  when), undoable through Edit › Undo, the same write permission as any change to the project; it reuses
  `project.save_setup`'s audit and invert, so a cap change never writes any other answer. A cap raised during a
  paused run (`designer.budget.fix-during-the-run`) is the same action. *Test:*
  `test_set_budget_is_audited_and_undoable.py` (the audit row names the cap and
  both figures; undo restores the old cap and nothing else; MCP and the command line reach it through the regen). Found built 2026-11-02 (#6295): `PUT /api/recipes/project/cloud-cap` is one `project.save_setup` writing only the caps, audited, one Undo puts both back (`test_raise_the_cap_in_place_6295.py::test_changing_the_caps_is_audited_keeps_the_rest_and_one_undo_puts_both_back`; the app: `RecipeSetupStore+CloudCaps.changeCloudCaps`). Left: an action of its own named `project.set_budget` (the audit row names `project.save_setup`), and the run cap.
- `designer.budget.fix-during-the-run` [PARTIAL] (#6295; extends `designer.run.cap-stops-and-says`) — when a run is
  paused at the cap, the run's Activity row and the project's run strip show the same three fixes, and both cap
  fields editable in place (the maintainer's ruling, 2026-10-30) (raise to $N,
  change the step's model for the remaining pages, stop here and keep what is done), with the booked figure so
  far; pressing raise sets the cap and resumes the run (the run's own Resume, #5932/#5933), never silently.
  *Test:* `test_run_cap_fix_in_place.py` (a paused run resumes after the cap is
  raised through the action; a stop keeps the finished pages). Built 2026-11-02 (engine, one path): the cap hold pauses the step's run and the recipe parks on it (`spend._STOPPED_AT_CAP`, which now records the caps it stopped under); a raised cap resumes it by the one Resume (`runner.resume_capped_runs` → `pause_recipe`, called after the cap route writes), from the run's own checkpoint, no page read again; a lowered or unchanged cap never does (`spend.raised_cap_stops`; `test_run_pauses_at_the_cap_6295.py`). Left: the Activity row and run strip fixes with the booked figure, Stop here is the run's own Stop (a run paused at the cap waits off the lane, so Stop ends it now with its finished pages kept; `test_stop_here_ends_a_run_paused_at_the_cap_and_keeps_what_is_done`).

### 12. Start, and the run

**Exists.** Start runs the steps in order, in batches, resumable, status in Activity, each step counting
its pages and saying why it was skipped (`source.recipe.start-runs-the-steps`,
`source.recipe.batch-at-archive-scale`, `source.recipe.batch-checkpoint`, `source.recipe.run-status-is-activity`,
`source.recipe.step-counts-its-pages`, `source.recipe.step-skipped-says-why`,
`source.recipe.failed-step-offered-again`); costs shown where known (`compute.job.costs-shown-where-known` (P),
`ai.where.one-pricer-every-place` (P), `ai.where.one-cloud-cap` (P), `ai.where.activity-shows-the-place` (G));
no silent fallback (`ai.where.no-first-provider-fallback`, `source.egress.no-silent-cloud-fallback` (P));
a run on the cluster, not yet startable (`compute.job.recipe-is-a-slurm-chain` (G), #5238).

**Improves.**
- `designer.run.predicted-then-measured` [MISSING] (#6052) — the predicted totals are kept with the run;
  Activity shows spend and elapsed time against them per stage; the run's end writes the measured totals
  beside the prediction and the route's estimate.
- `designer.run.cap-stops-and-says` [MISSING] (#6052) — a run that reaches the **project cloud cap**
  (`training.cost.app-and-project-caps` (G); until it is built, the Hugging Face cap for Hugging Face
  places) stops the paid step, keeps what is done, and offers the next candidate from the stage's
  compare or a raised cap; never another provider by itself.
- `designer.run.switch-recorded` [MISSING] (#6052) — a taught-model switch mid-run is recorded on the
  pages it changed, so a page's reading says which model made it (`source.recipe.recorded-on-what-it-made` (G)).
- `designer.run.path-moves-are-offers` [MISSING] (#6052) — the later moves of a path (to the taught
  model, to Hugging Face Jobs, to ACENET) appear as offers in Activity when their condition is met and
  their place is set up and allowed, each with its cost and time; a move whose place is not ready
  (the cluster before #5238) is shown greyed with the reason, never started.

### 13. Sharing a recipe: built-in, export, import, start from a recipe, search

**Exists.** Sharing is specified in section 12 of `models-chains-and-projects.md` and largely unbuilt:
`source.recipe.is-a-file` (G), `source.recipe.folder-format` (P), `source.recipe.schema-versioned`,
`source.recipe.travels-with-export` (G), `source.recipe.never-holds-keys` (P), `source.recipe.data-not-code` (P),
`source.recipe.prompt-files` (G); publish, follow, update, override and fork (`source.recipe.publish` (G),
`source.recipe.follow-and-update` (G), `source.recipe.update-is-clicked-not-applied` (G),
`source.recipe.update-measured-here` (G), `source.recipe.overrides-kept` (G), `source.recipe.fork` (G)); a
shipped flagship recipe for historical Spanish hands (`source.onboard.flagship-recipe` (G)); taking a
recipe whose step is missing here (`source.recipe.take-without-missing-step` (P)); a missing key never
substitutes (`source.recipe.missing-key-never-substitutes` (P)); a pinned model gone is said
(`source.recipe.pinned-model-gone` (P)); Fichero's own fetches are listed and gated
(`source.egress.fichero-own-fetches-listed` (G), `source.egress.every-call-site`).

**Improves — first slice (built-in, export, import).**
- `designer.share.built-in-recipes` [MISSING] (#6052) — extends `source.onboard.flagship-recipe`:
  Fichero ships a few starting recipes per kind of project, vendored in `recipes/seed/recipes/*.yaml`
  (a medieval Latin manuscript, an early modern Spanish notarial register, a 19th-century English
  logbook, a Fraktur newspaper, an Arabic manuscript, to begin), each from a **public** Test Corpus set
  with its licence and its benchmark rows' provenance; **no built-in recipe is made from a private
  corpus** (private pages train, never release). Listed first under "Start from a recipe" with the set
  and CER ("Medieval Latin manuscript · CER 5.8% on Clm 13027"); read-only until taken; a later
  release's change is an offer, never a silent update.
- `designer.share.export-is-the-whole-plan` [MISSING] (#6052) — Project › Share Recipe… writes one
  file: the material answers, the path and what matters most, the stages and each step's job, workflow
  id (a shipped preset by name; a person's own workflow embedded), model by provider and model id,
  place kind, settings and instructions, and the measured results with provenance.
- `designer.share.export-holds-nothing-private` [MISSING] (#6052) — never keys, pages, the person's
  paths or names, endpoint addresses or account names; embedded workflow node configs are stripped of
  endpoints and accounts; the prompts and instructions about to be exported are shown before the file
  is written; the file's header says what it holds. Pinned by a test over a recipe with every such field.
- `designer.share.import-checks-at-the-door` [MISSING] (#6052) — Project › Use a Recipe… reads a file
  into an open project through the recipe check (`source.recipe.checked-at-every-door` (P),
  `source.recipe.check-names-every-fault`); a model not here is offered for download or the same rank
  slot's candidate proposed; a cloud model with no key is listed needs-a-key, never swapped.
- `designer.share.imported-measures-are-the-authors` [MISSING] (#6052) — imported measurements are
  shown as "measured by the recipe's author on their pages"; the compare re-measures on this project's
  pages and those figures then outrank them.
- `designer.share.start-from-a-recipe` [MISSING] (#6052) — the path page offers "Start from a recipe"
  beside the route cards: a built-in one, a file, or a recipe from another project on this Mac; its
  answers pre-fill About the Material, the path and the stages, each marked "from the recipe" and
  editable; what does not fit the new material is said and left unticked, never applied silently.

**Later slice (a later milestone; specified here so the first slice leaves room).**
- `designer.share.recipe-search` [MISSING] (#6052) — "Start from a recipe" searches online, on the model
  finder's pattern (`source.find.online-search-is-a-job` (P), `source.find.wide-every-time` (P),
  `source.find.reason-names-fit`): a background `find-recipes` job, gated by the list of Fichero's own
  fetches (`source.egress.fichero-own-fetches-listed`; a metadata fetch, not the pages-may-leave
  answer), reading **first the `fichero-recipes` community catalogue** named by section 12 (one GitHub
  repository, one folder per recipe, every submission checked for schema, resolving pins, prompts and
  workflows present, licence; mirrored to Zenodo for a DOI; `source.recipe.publish`,
  `source.recipe.follow-and-update`, `source.recipe.is-a-file`), which does not exist yet (open question
  9); second, recipes published elsewhere by convention (files named `*.fichero-recipe.yaml`, or the
  `fichero-recipe` GitHub topic), marked "not checked by the catalogue".
- `designer.share.search-results-say-their-source` [MISSING] (#6052) — results are cached beside the
  finder's, ranked by fit to the material answers with the fit in words, each naming where it came
  from, its author, its licence and the measurements it claims ("measured by the author on their
  pages"); taking one only fills Set Up through the import door; nothing runs; with no network the
  built-in recipes are always there.
- `designer.share.publish-is-an-offer` [MISSING] (#6052) — publishing to the catalogue is the export
  plus a licence line and a public name; following a published recipe checks for updates, shown and
  clicked, never applied.

## Changes to existing behaviours

The few places where this spec asks an existing behaviour to change. Each owning spec is edited only
on approval; nothing else above alters an existing line.

1. **Search Online: on open, not only on a press.** `source.find.online-search-is-a-job`,
   `source.find.app-searching-line`, `source.find.online-search-per-step` describe a search the person
   starts. Integration (1c008843d, d9a1cd231) searches when the finder opens; this spec adopts that
   (`designer.rank.searches-on-open`) and keeps the press as "Search again".
2. **Ready's per-step menus.** `source.onboard.step-candidates-on-the-plan` and
   `source.onboard.step-choice-overrides-the-pick` give Ready a menu of candidates per step
   (`step_choices.py`, `StepChoiceMenusView`). This spec reduces Ready to one line per step with
   Change… (`designer.ready.one-line-per-step-with-change`); `_offered_cards` and `step_candidates`
   become one answer (appendix, facts 4, 9).
3. **Correct moves out of Read.** `source.recipe.kraken-reads-cloud-corrects-unsure` and
   `source.recipe.kraken-then-cloud-unsure-lines` put the unsure-lines correction on Read's menu. This
   spec moves it into a Review stage with line-level proposals in a separate pass (`designer.review.*`);
   the certainty bar stays Read's. The page-level "output the complete corrected transcription" prompt goes.
4. **The compare starts by itself, local candidates first.** `source.try.any-time`,
   `source.find.try-before-default`, `source.onboard.stages.compares-candidates` describe a compare the
   person starts. This spec starts it once by itself with local candidates, cloud ones on a press until
   there is truth, capped (`designer.compare.runs-by-itself`, `local-only-until-truth`, `capped`); the
   press remains; three compared, as today.
5. **The hand order of cloud families becomes the last fallback.** `_frontier_first` and
   `discovery.frontier_rank` order large cloud readers by family; here that order is used only for a
   candidate with neither a measurement nor a benchmark row (`designer.rank.frontier-order-is-the-fallback`).
   `source.recipe.reader-tiers` keeps its tier order as a later slot. Script and period stay filters
   before any of it (`designer.filter.fit-first`), as `script-reader-first` and
   `period-weighs-in-the-reader-rank` already say.
6. **Ruling B applied to every local page reader.** The ranking brief listed Apple Vision as a benchmark
   candidate for every row and the MLX vision model among Read's. `source.find.one-candidate-source`
   (owner ruling B 2026-10-24) says a page reader on this Mac is not a line step's candidate; this spec
   measures and lists all of them on the page-reading step only (`designer.filter.ruling-b-every-local-page-reader`).
7. **The noise band default.** The bake-off's one-point constant is replaced by the ruled 0.5 CER
   points per model kind (`source.train.noise-band-per-project`, `designer.measure.noise-band`).
8. **The first draft's ids.** `recipe.rank.*`, `recipe.compare.*`, `recipe.review.*`, `recipe.coverage.*`,
   `recipe.regions.*` and `source.recipe.distil-*` from `recipe-ranking-and-compare.md` are retired for
   the `designer.*` ids above; no test cited them.

Not changed: the stage names and order (a one-page "Find the layout" is only `[PROPOSED]`); the places
setting, the pages-may-leave question and the spend caps (a path shows them and proposes, it never
answers or writes them); training never automatic; three candidates compared; every existing
`source.onboard.stages.*` page behaviour; the routes as the one estimator.

## Test matrix (paste from `../TEST-TEMPLATE.md`, tick the legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | rendering only: the served route cards, served candidate order and labels drawn as served, radio selection, the Ready line, the String Catalog keys of the card texts | `fichero/Tests/Unit/general/Models/RecipeDesignerRenderingTests.swift` (to write) |
| Availability (Swift) | y | the path page in the flow after About the Material; Compare and Choose a model… on every model step; Start from a recipe reachable | `fichero/Tests/Unit/general/Views/Onboarding/SetupStagePageTests.swift` (to write) |
| Backend (pytest) | y | all logic: routes extended with two cards and their marks; a path sets defaults and never writes the cloud answer or a cap; greyed cards by places; filters before rank (script, period, coverage, unwritable characters, ruling B for every local page reader); one rank rule and the fallback; benchmark table load, provenance with `checked_by`, licence gate; insertion rate; noise band 0.5 per kind; auto-compare trigger, local-only without truth, no label without truth, cap; labels and predictions served; review pass shape and gain; one Kraken pass; lines per block; imported truth readiness; glyph inventory and display check; checking progress; teach offer, measurement, switch and costs; own workflow fits or not; export holds nothing private; import faults named | `fichero-server/tests/unit/recipes/test_recipe_designer_*.py` (to write) |
| MCP | y | `fichero_recipes_*` and the bake-off tools drive the benchmark run; the served labels reach the tools | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | the benchmark script runs through the CLI, never by hand | `fichero-cli/tests/test_recipes_*.py` (to write) |
| Click-around (XCUITest, Mac) | y | choose a path → open a stage page → compare runs by itself → check lines → Use This One → Ready names it | `fichero/Tests/UI/Onboarding/RecipeDesignerUITests.swift` (to write) |
| iPhone (iOS) | n | Set Up is a Mac surface today | — |
| iPad | n | — | — |
| Load (#4634) | y | an auto-compare never exceeds its cap, 3 pages or 3 candidates; a benchmark run is bounded per family | `fichero-server/tests/perf/test_auto_compare_bounded.py` (to write) |

Hard-gate: the cross-surface invariant (stage page, finder, Compare, Ready and the MCP tools answer
from one candidate list, one filter set and one rank rule, served by the engine through the generated
client) + capability availability (Choose a model… and Compare on every model step; the path page in
the flow).

## Documentation matrix (paste from `../DOC-TEMPLATE.md`, tick the audiences this reaches)

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | `docs/user_manual/guide/` "Designing your recipe" with the eight sections named under Manual (TBD) |
| Contributor | developer docs | y | `docs/contributor_manual/architecture/` recipes + this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/**` (`fichero_recipes_*`, bake-off tools: the filters, the rule, the caps, the measures) |
| Scripter | CLI `--help` | y | `fichero-cli/**` (benchmark run, compare, use-candidate, share and use a recipe) |
| Reference | capability/endpoint reference | y | generated (`check_capability_reference_current`) |

The card and offer texts above are the facts the maintainer's manual documents; the spec holds the
on-screen wording, the manual the longer "Learn more" text.

## Preview harness (fast visual verification + doc screenshots)

`RecipeDesignerPreview` (`#if DEBUG`) renders from recorded served data, no engine: the route cards with
their marks and one greyed; a stage page with a ranked list (measured row, benchmark row, a row under
Other periods, a coverage-refused row, predictability words on each); the compare in its modes (counts,
lines on the page, text beside the page with and without labels); the checking progress line; the Teach
a model… offer; a Ready line with Change…; Start from a recipe. It is the source of the manual's
screenshots (`docs/assets/recipe-designer/`).

## Accessibility identifiers (required for the click-around leg)

| Surface | Identifiers (a11y, not behaviours) |
|---|---|
| Path page | `designer.path.card.<route>` · `designer.path.learn-more.<route>` · `designer.path.cloud-question` · `designer.path.matters.<speed|cost|quality|predictability>` · `designer.path.start-from-recipe` |
| Candidates | `designer.stage.<stage>.candidates` · `designer.candidate.row.<id>` · `designer.candidate.radio.<id>` · `designer.candidate.reason.<id>` · `designer.candidate.own-workflow.<id>` |
| Finder | `designer.finder.open` · `designer.finder.search-again` |
| Compare | `designer.compare.again` · `designer.compare.column.<id>` · `designer.compare.use.<id>` · `designer.compare.badge.<best|cheapest|fastest|predictable>` · `designer.compare.prediction` · `designer.compare.not-measured` |
| Checking | `designer.check.progress` · `designer.check.open-pages` |
| Review, layout | `designer.review.kind` · `designer.layout.region-model` |
| Workflow | `designer.step.open-in-editor.<job>` · `designer.step.adjust-in-editor.<job>` |
| Teach | `designer.teach.offer` · `designer.teach.candidate.<distil|fine-tune>` · `designer.teach.where` · `designer.teach.learn-more` |
| Ready | `designer.ready.step.<job>` · `designer.ready.change.<job>` · `designer.ready.totals` · `designer.ready.chain.<job>` |
| How (2026-10-30) | `designer.how.where.<place>` · `designer.how.model-kind.<kind>` · `designer.how.matters.<speed|cost|quality|privacy>` · `designer.how.access` · `designer.how.risks` · `designer.how.learn-more` |
| Condition | `designer.material.condition.<id>` |
| Budget | `designer.budget.run-cap` · `designer.budget.project-cap` · `designer.budget.step.<job>` · `designer.budget.fix.<raise|change-model|fewer-pages>` |
| Material | `designer.material.imported-truth` · `designer.material.script-display` |
| Sharing | `designer.share.export` · `designer.share.import` |

## UX completeness (required on EVERY surface)

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `designer.path.card.<route>` | the route's title | Choose how this project works; every default can be changed later | `designer.path.card.<route>` | [MISSING] |
| `designer.path.matters.<x>` | What matters most | Breaks ties between models that read equally well | `designer.path.matters` | [MISSING] |
| `designer.finder.open` | Choose a model… | Lists every model that can do this step, in the order Fichero ranks them | `designer.finder.open` | [MISSING] |
| `designer.candidate.radio.<id>` | Use This One | Makes this the step's model | `designer.candidate.use` | [MISSING] |
| `designer.compare.again` | Compare again… | Runs the candidates on your sample pages; the cost is shown first | `designer.compare.again` | [MISSING] |
| `designer.compare.use.<id>` | Use This One | Makes this the step's model | `designer.candidate.use` | [MISSING] |
| `designer.check.open-pages` | Check these pages | Opens the compared pages in the Reader to confirm or correct lines | `designer.check.open-pages` | [MISSING] |
| `designer.review.kind` | Review kind | What the reviewer looks for on each line | `designer.review.kind` | [MISSING] |
| `designer.layout.region-model` | Blocks found by | Which model finds the blocks on each page | `designer.layout.region-model` | [MISSING] |
| `designer.teach.offer` | Teach a model… | Train a smaller model on your checked lines; offered, never started by itself | `designer.teach.offer` | [MISSING] |
| `designer.ready.change.<job>` | Change… | Choose another model for this step | `designer.ready.change` | [MISSING] |
| `designer.material.imported-truth` | Use as the measure | Your imported transcriptions become the reference every comparison is measured against | `designer.material.imported-truth` | [MISSING] |
| `designer.material.condition.<id>` | the condition's name | What Fichero does about it, in one line (the engine's) | `designer.material.condition` | [GAP] |
| `designer.how.where.<place>` | the place's name | Where this project's work may run; pages leave this Mac only for a place you tick | `designer.how.where` | [GAP] |
| `designer.how.model-kind.<kind>` | the kind's name | Small local models read only what is on the line; large models read fluently and may invent | `designer.how.model-kind` | [GAP] |
| `designer.how.matters.<x>` | What matters most | Picks the defaults and breaks ties between models that read equally well | `designer.how.matters` | [GAP] |
| `designer.budget.run-cap` | This run, at most | Cloud spending this run may reach; the run pauses at it and asks | `designer.budget.run-cap` | [GAP] |
| `designer.budget.project-cap` | This project a month, at most | Cloud spending this project may reach in a month; audited and undoable | `designer.budget.project-cap` | [GAP] |
| `designer.budget.fix.<kind>` | Raise the cap to $N · Change the model… · Run fewer pages | The fix in place for a Start the cap refused | `designer.budget.fix` | [GAP] |

All strings through the String Catalog; no `Text(verbatim:)`. Presence scans are not behavioural tests;
every row is [MISSING] until a spec-pinned test or `performAccessibilityAudit()` covers it.

## Order of value (a summary of the build order below)

0. **Screens-review fixes** (app and engine, all PARTIAL today): one visible selection, cloud permission
   said once, nothing-found from the engine, Choose a model… on every model step, says-what-it-cannot-
   measure wording, Ready as one line per step with Change…, search on open. (Appendix, facts 1–13.)
1. One Kraken pass (engine, #6014). Lines per block waits for step 11.
2. Imported transcriptions detected and asked once; imported truth measures at once; then the glyph
   inventory and the display check through `derived.py`.
3. Checking lines: progress in words, which pages, corrections become the reference.
4. Filters: coverage band, the refusal, ruling B for every local page reader.
5. The path page from `routes.py`: cards, cloud question on the page, greyed cards, caps proposed not
   written, teaching defaults, what matters most. Cards (a) and (d) live at once; (c) when a key is
   set; (b) when the Hugging Face cap is raised and the cluster sign-in lands (#5238).
6. **The project and app cloud caps** (`training.cost.app-and-project-caps`, #5440), before any
   automatic spend.
7. Auto-compare on open: local only without truth, readings-only result, labels and predictions where
   measured, the compare cap; then text beside the page.
8. Benchmark harness and the first four rows (licence-gated, `checked_by`), insertion rate; about US$5.
9. Rank by the table; the fallback; reasons and predictability in words; labels served.
10. Review stage, first slice (one shipped kind, proposals as a separate pass, gain).
11. Region-model row with lines per block, segmenter search, layout rows; the one-page layout stage if ruled.
11b. Leave out non-text segments and the damaged mark (#6070): the Clean Up / Find the layout stage marks left-out lines (kept, never deleted) and a damaged mark on a page or region, measured like the other stages.
12. Teach a model… offer, measurement, switch, costs; the run's offers and the recorded switch.
13. The workflow line, Open in the editor, a person's workflow as a candidate, Adjust in the editor.
14. Share Recipe…, Use a Recipe…, the built-in recipes and Start from a recipe.
15. Later milestone: the recipe search (catalogue first, then the convention), publish and follow.
16. Fill the rest of the table; refresh one family at a time per model release.

## Rulings (owner, 2026-10-24)

The spec is approved to build in the build order. Benchmark spend: the first four rows (about US$5)
only. Questions 1–3 and 5–9 are ruled as follows; question 4 stays open.

1. One page, "Find the layout" (`designer.layout.one-page` is ruled; build it at step 11).
2. The automatic compare spends from the project cloud cap, not a cap of its own; a press of
   Compare that would go past what is left asks first, in a confirming dialog.
3. 500 checked lines for a Kraken fine-tune, the lines of 200 pages for a LoRA, or the volume rule's
   5,000 pages, whichever comes first.
5. NonCommercial sets are measured locally and never shipped.
6. The four card texts and the teaching offer are approved as written.
7. The first draft's ids are retired once the clerk confirms nothing cites them.
8. The five built-in recipes are approved, each from a public set.
9. The `fichero-recipes` catalogue waits; the recipe search stays a later milestone.

Set Up screens items 5, 9 and 13 (appendix): one "Choose a model…" on every model step; Ready as one
line per step with Change…; the duplicate grey example line removed (one is kept).

## Rulings (the maintainer, 2026-10-30)

On the open questions of the 2026-10-30 additions; question 6 (the defaults table's rows) stays open.

5. **Page order.** How do you want to run this? comes after About the Material and before Choose the Stages
   (section 4, as drafted).
7. **Caps.** A Start may be blocked by either the project cap or the monthly cap, and the experience lets a person
   update both in place: in the Budget block on Ready and on the refusal and the paused-at-cap screens
   (`designer.budget.beside-the-estimate`, `designer.budget.refusal-offers-the-fix`,
   `designer.budget.fix-during-the-run`). Today a Start is blocked with no way to change either cap in the app.
8. **Margin.** There is no margin multiplier. The estimate says what Fichero thinks it will cost, its best
   estimate with its basis, and it learns from the project's booked costs
   (`designer.budget.estimate-from-booked-usage`).
9. **Fewer pages.** The "Run fewer pages" fix starts the first N pages, in Finder order
   (`designer.budget.refusal-offers-the-fix`).

## Open question for the creative director

4. The dictionary-word rule for "lines changed beyond the CER" (needs a word list per language; none
   for Latin abbreviations); until ruled it stays [PROPOSED] and the insertion rate is the one number.

## Open question for the maintainer (the 2026-10-30 additions; a recommendation)

6. **The defaults table's rows.** The nine rows in section 4b are a first draft from the specs' own rules;
   the maintainer's judgement on each cell (which reader for damaged handwriting; whether Review defaults on
   for a large cloud model) is what makes the table right. *Recommend:* rule row by row on approval; the
   table is data, so a changed row is a one-line change and a test.

## Appendix: screens review facts (2026-10-24, read from the code; inlined so nothing cites a local note)

1. Find a Reader… shows only for reading jobs (`RecipeStepsView` checks `readsMaterial`), so Find
   Regions and Correct have no way into the finder.
2. The stage chooser draws nothing when the recipe has no step for the job; it should say so.
3. Search Online for Find Regions can never add a row: every Hub hit is `object-detection`, marked
   cannot-run, and dropped as not worth listing.
4. Correct's finder lists no cloud models (the text branch is not taken for `correct`), while Ready's
   step menu does: two lists, two answers.
5. "Use a cloud model…" is a fix button that opens a finder with no cloud model: a dead end; the
   unsure-lines rows on Ready repeat the certainty-bar choice.
6. The chosen card is moved to a head group and loses its tier; no radio mark.
7. "Allow Cloud Models" repeats on every cloud card.
8. The nothing-found wording is hard-coded in the app and wrong for Regions.
9. Ready's `StepChoiceMenusView` is a third UI for the same choice.
10. Compare results are caption rows of counts; the side-by-side view is reached only when every
    candidate has a showcase.
11. The readiness sentence counts corrected lines in a project with nothing read.
12. Only Find Lines has a "who does it" note; one engine sentence per sampleable stage is wanted.
13. The grey stage example line is drawn twice.

## Build order (person-visible value first; each step shippable alone)

### Stage 1 — Screens-review fixes (app and engine)

#### Step 1.1 — One selection, one cloud line, nothing-found from the engine, one finder (#6053)
- Behaviours: `designer.rank.one-visible-selection`, `designer.rank.cloud-permission-said-once`, `designer.rank.nothing-found-from-the-engine`, `designer.rank.finder-for-every-model-step`, `designer.rank.searches-on-open`
- Tests: fichero-server/tests/unit/recipes/test_cloud_text_pick_and_every_step_chooses_6088.py, RecipeFinderTests.swift (not yet written), test_finder_nothing_found.py (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** every step that needs a model can choose one in the engine (`source.find.every-step-lists-models`, #6088, `test_cloud_text_pick_and_every_step_chooses_6088.py`); the steps page offers "Choose a Model…" beside a non-reading step and "Find a Reader…" beside a reading one (`RecipeStepsView.swift:60`); the engine has one nothing-found sentence, `discovery.nothing_found_words(languages)`, sent as a row's `detail`. **Left:** the two button names become one, "Choose a model…", and the download / choose-cloud / choose-model fix buttons (`RecipeStepsView.swift:246-250`) collapse into that one press (fact 1, 4, 5); the finder's chosen row keeps its tier with a leading radio mark and a tinted row (fact 6); the "Allow Cloud Models" line is drawn once above the cloud tier (fact 7); the app's own nothing-found strings go and every job's sentence is the engine's `detail`, Find Regions included (fact 8); the finder searches online by itself when it opens for a step that has a search, says what it found, the press reads "Search again", and a job with no search shows the press disabled with the engine's reason. **Acceptance (app, by test):** opening the finder for Find Regions and for Correct shows the same list the engine returns for that job and no second list; choosing a row leaves it in its tier with the radio mark; a sheet with three cloud cards shows the permission line once; with the engine answering no candidates for Regions the sheet shows the engine's sentence verbatim and no app string; opening the finder for a step with a search sends one search request before any press, and "Search again" sends another; for a step with no search the press is disabled with the reason. **Acceptance (engine):** `nothing_found_words` is served for every job in the finder's answer (`detail`), Regions and Correct included, and a test asserts no job answers with an empty list and no detail.

- test (to write): `RecipeFinderTests.swift` in fichero/Tests/Unit/general/Models/ (beside `RecipeSetupStoreTests.swift`: one button name; the radio mark and tier kept; the permission line once; the engine's sentence shown verbatim; search on open, Search again, disabled with reason)
- test (to write): `test_finder_nothing_found.py` in fichero-server/tests/unit/recipes/ (every job's empty answer carries `detail` from `nothing_found_words`; Regions' sentence names regions, not readers)

#### Step 1.2 — Plain wording on Read and Ready (#6053)
- Behaviours: `designer.measure.says-what-it-cannot-measure`, `designer.ready.one-line-per-step-with-change`, `designer.read.certainty-question-stays-here`
- Tests: RecipeReadyTests.swift (not yet written), test_cannot_measure_wording.py (not yet written)
- Size: S

Written for the builder 2026-11-07 (spec-writer). **Built:** the bake-off's readiness check counts corrected lines on the sample pages and says what it needs ("Needs N corrected lines on at least 2 pages; this project has …", `recipes/bakeoff.py:354-366`); Ready has one line per step. **Left:** (engine, slice 1) when the project has NOTHING read yet the sentence is "Compare measures against lines you have checked. Read a few pages first, then check about 100 lines on two pages" and no count of corrected lines is shown (fact 11); the same wording reaches every stage that cannot measure, through one function. (App, slice 2) Ready's `StepChoiceMenusView` (fact 9, `RecipeReadyFields.swift:102`) goes; each step's one line carries the chosen model, its place, its measured figure with provenance, its predictability words, the predicted cost and time, and Change…, which opens the one finder of Step 1.1; the "a cloud model corrects the unsure lines" choice leaves Read's menu and is offered once on the Review page (fact 5; the Review stage itself is Step 10.1, so until it lands the choice stays where the certainty bar is, said once). **Acceptance (engine):** a project with zero pages read answers the cannot-measure sentence above and `corrected_lines` is absent; a project with pages read but under the threshold keeps today's "Needs N corrected lines" sentence; the same function serves Read, Correct and Find Lines. **Acceptance (app):** the Ready page mounts no `StepChoiceMenusView`; each step row shows the six parts and a Change… button whose identifier is `recipe.ready.change.<job>`; pressing it opens `ModelFinderSheet` for that job; Read's menu has no unsure-lines item.

- test (to write): `test_cannot_measure_wording.py` in fichero-server/tests/unit/recipes/ (zero read → the sentence and no count; under threshold → the count sentence; one function for three stages)
- test (to write): `RecipeReadyTests.swift` in fichero/Tests/Unit/general/Models/ (no step menus on Ready; the six parts per row; Change… opens the finder for the row's job; Read's menu without the unsure-lines item)

### Stage 2 — Material, imported truth and one Kraken pass

#### Step 2.1 — One Kraken pass (#6054)
- Behaviours: `designer.layout.one-kraken-pass`
- Tests: fichero-server/tests/unit/recipes/test_regions_one_pass_5689.py, test_one_kraken_pass.py (not yet written)
- Size: S

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built (#5689):** one `blla` call returns regions and lines and each line keeps its region (`kraken_runtime._segment_raw`, `geometry_from_segmentation`); Find Regions stores both (`recipes/regions.py:283`) and Read reads the stored lines instead of segmenting again (`test_regions_one_pass_5689.py`). **Left:** the two re-calls the bullet names: (1) the bake-off's `find_lines_with("kraken", photo)` (`recipes/bakeoff.py:771-777`) calls `kraken_runtime.segment_to_geometry(photo)` for every sample page even when Find Regions has stored that page's lines; it reads the stored geometry first and segments only a page with none; (2) the runner's Find Lines step, when Find Regions ran Kraken on the page in the same plan, takes the stored lines and makes no call (today the `find-lines` job may segment again where the finder is Kraken and the regions pass already holds the lines). The one seam stays `segment_lines`, as the 5689 test stubs it. **Acceptance (engine):** with Find Regions and Find Lines both Kraken on a 3-page fixture, a counting stub on the segmenter sees exactly 3 calls across Find Regions, Find Lines, Read and a bake-off over those pages (today 6 or 9); a page whose stored lines were deleted is segmented once more and no other page is; with Find Regions on Apple Vision and Find Lines on Kraken the count is unchanged from today (the lines are Kraken's own pass); the bake-off's figures on the fixture are identical before and after (the same lines read).

- test (to write): `test_one_kraken_pass.py` in fichero-server/tests/unit/recipes/ (the counting stub across the four callers; the deleted-lines page segmented once; the mixed-finder case unchanged; identical bake-off figures)

#### Step 2.2 — Imported transcriptions detected, asked once, measured at once (#6055)
- Behaviours: `designer.material.imported-transcriptions-detected`, `designer.material.imported-truth-asked-once`, `designer.material.imported-truth-measures-at-once`
- Tests: fichero-server/tests/unit/recipes/test_import_ground_truth.py, test_imported_truth.py (not yet written), AddMaterialImportedTruthTests.swift (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built (#5513):** corrected transcriptions given at setup come in through the one import path as person-made passes marked ground truth, and the bake-off counts them (`bakeoff.ground_truth`, `made_by_a_person`, `test_import_ground_truth.py`); the readiness sentence names the pages that hold imported transcriptions nobody has marked (`bakeoff.unmarked_import_pages`); the importers pair interchange files with their images (`importers/interchange_pairing.py`). **Left:** (1) engine: Add Material's answer counts the pages that arrived with a transcription and names the tool, per format (PAGE, ALTO, hOCR, TEI, plain text named after its image, Tesseract `.box`), read from the paired files' producer fields (PAGE's `Creator`, ALTO's `processingSoftware`, hOCR's `ocr-system`, TEI's `<application>`) with "a text file" when none says; (2) engine: ONE question on the material page, default yes, with the count and the tool ("212 pages arrive with a transcription from Transkribus. Use them as the measure every model is compared against? You can correct them later; your corrections win."); yes marks the passes ground truth through the existing route (`PUT` on the pass's `ground_truth`, one code path), a plain text file named after its image counting as page truth; asked once per project and remembered in `setup.yaml`; (3) engine: with imported truth the bake-off's readiness passes without checked lines, every measurement says "measured on N of your imported pages; ground truth from the files", and a person's later correction on a line replaces the file's reading as that line's reference (the existing rule, `made_by_a_person` outranks the import); (4) app: the sentence and the one question on Add Material, the measurement label on Compare and Ready. **Acceptance (engine):** a fixture folder with 212 images, 212 PAGE files from Transkribus and 3 `.box` files answers "212 pages arrive with a transcription from Transkribus; 3 from Tesseract"; the question appears once and `setup.yaml` records the answer; yes marks every imported pass `ground_truth` and the bake-off's readiness is true with zero checked lines, its label the sentence above; a correction on one line makes that line's reference the person's and the label "measured on N of your imported pages and 1 corrected line"; no marks the passes nothing and the readiness sentence names the unmarked pages as today. **Acceptance (app, by test):** Add Material shows the count sentence and the yes/no once; Compare's rows carry the imported-truth label.

- test (to write): `test_imported_truth.py` in fichero-server/tests/unit/recipes/ (the per-format count and tool; the one question and its memory; yes marks through the one route; readiness true with imported truth; the correction wins; no leaves the unmarked sentence)
- test (to write): `AddMaterialImportedTruthTests.swift` in fichero/Tests/Unit/general/Models/ (the sentence and question once; the label on Compare and Ready)

#### Step 2.3 — Glyph inventory, display check, questions name their stage (#6055)
- Behaviours: `designer.material.glyph-inventory`, `designer.material.script-displays-check`, `designer.material.question-names-its-stage`
- Tests: fichero-server/tests/unit/recipes/test_transcription_font_from_script_and_period.py, test_glyph_inventory.py (not yet written), test_derived_display_check.py (not yet written), test_questions_stage_map.py (not yet written), ScriptDisplaysCheckTests.swift (not yet written)
- Depends on: 2.2
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built (#5438):** `derived.py` answers the font a transcription is drawn in from the script and period, remembered per library (`test_transcription_font_from_script_and_period.py`); the stage questions exist and are open-ended (#5805). **Left:** (1) engine: the project's glyph inventory, `recipes/glyphs.py`: the set of characters its ground truth uses (`.box` characters, TEI `<g>` and MUFI code points, the text of passes marked ground truth or made by a person), rebuilt when a pass changes and stored in the project folder (`recipe/glyphs.json`, counts per code point), read by the coverage filter (Step 4.1), the display check and the compare's character row; (2) engine: `derived.py` extends its font answer with a per-character check of the inventory (or, before any truth, the script's exemplars from `seed/iso15924.txt`'s ranges) against the bundled fonts' cmaps, answering the count that displays and the list that does not with their block names; (3) app: adds this device's system fonts to the check and shows the result for the device the person looks at ("all 418 of your characters display", or "14 characters (Canadian Syllabics, U+1400…) have no font here and show as boxes until one is added", naming the fallback family), on Add Material and in the Reader's font menu; (4) engine: `GET /api/recipes/questions` serves, with each question, the stages it feeds; a question no stage reads is not served; the app shows the stage under the question ("the period narrows the readers"). **Acceptance (engine):** a fixture with 40 `.box` characters, a TEI file with two MUFI glyphs and one person-made pass yields an inventory of exactly their code points with counts; the check against the bundled fonts reports the two MUFI glyphs as not displayed with the block named and everything else displayed; before any truth the check runs on the script's exemplars; every served question names at least one stage and a question that feeds none is absent. **Acceptance (app, by test):** the device's fonts change the answer shown (a stubbed font list with Junicode displays the MUFI glyphs; without it the sentence names them); each question shows its stage words.

- test (to write): `test_glyph_inventory.py` in fichero-server/tests/unit/recipes/ (the inventory's code points and counts from the three sources; rebuilt on a pass change)
- test (to write): `test_derived_display_check.py` in fichero-server/tests/unit/recipes/ (the per-character check against bundled cmaps; the exemplars before truth; the two sentences)
- test (to write): `test_questions_stage_map.py` in fichero-server/tests/unit/recipes/ (every question names a stage; a stage-less question is not served)
- test (to write): `ScriptDisplaysCheckTests.swift` in fichero/Tests/Unit/general/Models/ (the device fonts added; the sentence per case; the stage words under a question)

### Stage 3 — Checking lines

#### Step 3.1 — Progress in words; corrections become the reference (#6056)
- Behaviours: `designer.check.progress-in-words`, `designer.check.corrections-become-the-reference`
- Tests: fichero-server/tests/unit/recipes/test_import_ground_truth.py, test_check_progress.py (not yet written), test_corrections_replace_reference.py (not yet written), CheckProgressLineTests.swift (not yet written)
- Depends on: 2.2
- Size: S

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** the thresholds and the counts exist in the engine: the bake-off needs `MIN_LINES = 100` checked lines on `MIN_PAGES = 2` pages (`bakeoff.py:52-53`, `bakeoff.readiness`, its sentence "Needs N corrected lines on at least 2 pages; this project has …"), Teach a model has its own count and threshold (`train_offers.py:178-184`, regions on pages; the lines threshold per job from `at_least`); a person-made pass already outranks an imported or model reading as the reference (`bakeoff.ground_truth`, `made_by_a_person`; `test_import_ground_truth.py`); the pages to check are proposed least-sure first (`what_to_check.least_sure`). **Left:** (1) engine: one progress line per threshold, served with the readiness (`GET /api/recipes/project/start` and the bake-off's readiness answer): "62 of 100 lines checked on 1 of 2 pages; Compare can measure at 100" and "62 of 500 for Teach a model…", the numbers the engine's own counts and thresholds, the words from one function so Read, Train and Ready cannot differ; (2) engine: a checked line replaces the reference at once: the next compare and every candidate row's slot 1 (Step 8.2) read it without a re-import or a restart, and the measurement label says "on N checked lines" when the reference holds any; (3) app: the Read and Train pages and Ready show the engine's line verbatim under their heading, and nothing else counts lines in the app. **Acceptance (engine):** with 62 person-checked lines on one page the readiness answer carries exactly "62 of 100 lines checked on 1 of 2 pages; Compare can measure at 100" and the Teach line "62 of 500 for Teach a model…"; with 100 lines on two pages the Compare line reads "Compare can measure now"; checking one more line on a page with an imported reading changes that line's reference to the person's in the very next bake-off run, with no other call. **Acceptance (app, by test):** Read, Train and Ready each mount the engine's line and hold no counting of their own.

- test (to write): `test_check_progress.py` in fichero-server/tests/unit/recipes/ (the two lines from fixtures at 62/1, 100/2 and 0/0; one function; the Teach line's threshold from `at_least`)
- test (to write): `test_corrections_replace_reference.py` in fichero-server/tests/unit/recipes/ (a check replaces the reference at once; the label names checked lines)
- test (to write): `CheckProgressLineTests.swift` in fichero/Tests/Unit/general/Models/ (the three pages mount the engine's line; no app-side count)

### Stage 4 — Filters

#### Step 4.1 — Fit first, coverage band, refusal, ruling B (#6057)
- Behaviours: `designer.filter.fit-first`, `designer.filter.coverage-band`, `designer.filter.refuses-unwritable-characters`, `designer.filter.ruling-b-every-local-page-reader`
- Tests: fichero-server/tests/unit/recipes/test_candidates_filtered_then_ranked_4950.py, fichero-server/tests/unit/recipes/test_unrunnable_reader_refused_5800.py, test_filters_fit_first.py (not yet written), test_coverage_band.py (not yet written), test_refuses_unwritable.py (not yet written)
- Depends on: 2.3
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** the filters run before the rank in `assemble._refusal` (`assemble.py:326`): job, script (Fraktur and Gaelic as Latin, Han variants apart), language, material, licence, each with a code and a plain reason (`test_candidates_filtered_then_ranked_4950.py`, `test_unrunnable_reader_refused_5800.py`); a period is never a refusal, only a lower rank (ruled 2026-10-17, `_period_rank`); `does_the_step` names the jobs a card does. **Left:** (1) fit first: a candidate of another period is listed under "Other periods" and never ranked among the fits, and a benchmark row (Step 8.1) never lifts a candidate past any filter: the filters run first and the rank sees only what passed; (2) `Card.coverage` as a band (covered, unknown, poor) set at discovery: a text or vision-language model's Loove coverage for the project's languages and scripts, a Kraken reader's codec against the project's glyph inventory (Step 2.3), and the heuristic coverage "unknown"; the band is a rank slot (3) and a row word, never a refusal by itself; (3) the refusal of unwritable characters: a candidate whose codec (Kraken) or declared alphabet (a text model's card) can never output a character the ground truth uses (MUFI private-use, Newa outside the BMP, polytonic combining marks) is refused by `_refusal` with a new code `cannot-write-characters` and the count in the reason ("cannot write 14 of your characters"), before any paid call; (4) ruling B: every page reader on this Mac (Apple's recognition, the MLX vision model, Tesseract where its card names only the page job) is listed, compared and benchmarked on the page-reading step only and never on `read-a-line`, with `does_the_step` the one rule the list, the compare and the benchmark table all read. **Acceptance (engine):** a Kraken reader made for another period is returned under `other_periods` and absent from the ranked list even with the best benchmark row; a card with Loove coverage for the project's language gets `coverage: covered`, one with none `unknown`, a Kraken codec missing three inventory characters `poor`; a candidate whose codec lacks 14 of the inventory's characters is refused with `cannot-write-characters` and "cannot write 14 of your characters", and no call is made for it; Apple's recognition appears for `read-a-page` and never for `read-a-line` in the candidates, the compare's set and the benchmark's rows alike, one function deciding. **Acceptance (app, by test):** the finder shows "Other periods" as its own tier below the fits, and a refused row's reason verbatim.

- test (to write): `test_filters_fit_first.py` in fichero-server/tests/unit/recipes/ (other period under its tier, never lifted by a row; the filter before the rank)
- test (to write): `test_coverage_band.py` in fichero-server/tests/unit/recipes/ (the three bands from Loove, a codec and the heuristic; the band as a slot, not a refusal)
- test (to write): `test_refuses_unwritable.py` in fichero-server/tests/unit/recipes/ (the code and the count; no call made; ruling B across the list, the compare and the table)

### Stage 5 — The path page

#### Step 5.1 — Route cards, cloud question, greyed cards, card text (#6058)
- Behaviours: `designer.path.cards-are-the-routes`, `designer.path.cloud-question-on-the-page`, `designer.path.card-live-only-where-allowed`, `designer.app.places-say-their-consequence`, `designer.path.card-text`
- Tests: fichero-server/tests/unit/recipes/test_routes_for_the_volume.py, fichero-server/tests/unit/recipes/test_places_cap_the_routes_5831.py, test_path_cards.py (not yet written), PathPageTests.swift (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** the routes exist with their figures and each figure's basis (`recipes/routes.py` `routes_for_volume`, cost, time and accuracy marked measured, estimate or unknown; `test_routes_for_the_volume.py`); a route that would send pages asks the app's places and refuses in words when a place is off (`test_places_cap_the_routes_5831.py`); the How step (`RecipeHowFields`, behind `wideSetUp`) holds the "what matters" and "what you have" questions (`recipes/how.py`); the places page exists (`WhatFicheroRunsFields`) with one body sentence per place. **Left:** (1) engine: `GET /api/recipes/project/paths` answers the path page: the routes of `routes_for_volume` extended to the four paths of the card text (a: large model then a small one; b: Hugging Face then cluster; c: cloud throughout; d: local only), each carrying the routes' own figures and marks, "not measured for this language yet" where the routes cannot give one, the pages-may-leave question UNANSWERED on the page's own answer (a path never answers it), and per card `live: true` or `greyed_because: <the engine's reason>` with `fix: places | settings` when the app does not allow a place or it is not set up (no cluster key and sign-in, Hugging Face at a $0 cap, no provider key); a project is never made looser than the app; (2) engine: each place on What Fichero runs gains one consequence sentence for a recipe, served with the places ("the cloud: large cloud models become candidates, and pages leave this Mac only when a project allows it"; "ACENET: long runs and training can be sent to the cluster, nothing until you say"); (3) app: the path page draws the cards side by side from the one answer, with the card text of the bullet (String Catalog) above the figures and "Learn more" to the manual's "Ways of working"; the cloud question sits on the page and a card that needs pages to leave stays incomplete ("answer above to use this path") until the person says yes; a greyed card shows the engine's reason and a link to What Fichero runs or Settings. **Acceptance (engine):** for 2,000 pages with a cloud key and no cluster, the answer holds four cards, (b) greyed with "no cluster key and sign-in" and `fix: settings`, (a) and (c) incomplete until the cloud question is yes, (d) live; every figure carries its basis or the not-measured sentence; the cloud question is present and unanswered; the places answer carries one consequence sentence per place. **Acceptance (app, by test):** the page mounts four cards from the answer, the question above them, a greyed card's reason and link, the incomplete sentence until yes; the card text comes from the catalogue, not the engine.

- test (to write): `test_path_cards.py` in fichero-server/tests/unit/recipes/ (the four cards from the routes; the unanswered question; greyed with reason and fix; the not-measured sentence; the consequence sentences)
- test (to write): `PathPageTests.swift` in fichero/Tests/Unit/general/Models/ (cards from the answer; the question on the page; incomplete until yes; greyed reason and link; Learn more)

#### Step 5.2 — Choosing a path: defaults, proposed caps, teaching defaults, what matters most (#6058)
- Behaviours: `designer.path.choosing-is-a-default`, `designer.path.caps-proposed-not-written`, `designer.path.sets-teaching-defaults`, `designer.path.what-matters-most`
- Tests: fichero-server/tests/unit/recipes/test_how_questions.py, test_path_defaults.py (not yet written), PathChoiceTests.swift (not yet written)
- Depends on: 5.1
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built:** "What matters most?" exists as a How question in the engine (`recipes/how.py`, `GET /api/recipes/questions`, saved as `answers.how.matters`, `test_how_questions.py`), pre-filled from the places answer; the caps exist (the project cloud cap `PUT /api/recipes/project/cloud-cap`, the Hugging Face cap, `cloud_cap.py` with `fixes_for` and `cap_refusals`). **Left:** (1) engine: `POST /api/recipes/project/path` records the chosen card as the recipe's default path: it sets the steps' defaults (the stage set and each step's model slot the path implies), proposes a spend figure beside the estimate and WRITES NO CAP (the Hugging Face cap stays $0 and the project cloud cap untouched until the person confirms a typed figure through the existing cap routes), sets the teaching defaults without asking (whether, after how many checked lines, where: paths (a) and (d) teach, (b) and (c) do not; shown and asked only at the offer, Step 11.1), and pre-fills "what matters most" from the path (speed, cost, quality, predictability) while keeping it one choice the person may change; a card the person chose by hand is never re-proposed over when an answer changes (`test_how_answers_pick_the_card.py` is the pick rule's test, named by `designer.how.what-matters`). (2) app: choosing a card marks it "proposed from your answers; change here", keeps the other cards, shows the proposed spend with a field that writes the cap only on confirm, and shows the pre-filled "what matters most". **Acceptance (engine):** choosing (a) on a project with a cloud key sets the stages and slots of (a), answers `proposed_spend` and leaves both caps as they were; confirming a typed figure writes the cap through the cap route; the teaching defaults read teach-yes for (a) and (d) and teach-no for (b) and (c); `answers.how.matters` is pre-filled per path and a later hand choice is kept across a re-proposal; changing the places answer re-proposes a card only when none was chosen by hand. **Acceptance (app, by test):** the chosen card's sentence, the other cards still shown, the spend field writing nothing until confirm, the pre-filled choice editable.

- test (to write): `test_path_defaults.py` in fichero-server/tests/unit/recipes/ (the defaults per path; no cap written until confirm; the teaching defaults; what matters pre-filled and the hand choice kept)
- test (to write): `PathChoiceTests.swift` in fichero/Tests/Unit/general/Models/ (the sentence; the spend field; the choice editable)

### Stage 6 — Measures

#### Step 6.1 — Insertion rate, noise band, measures on the person's pages, the measure table
- Behaviours: `designer.rank.insertion-rate`, `designer.read.measures`, `designer.measure.on-your-pages-first`, `designer.measure.noise-band`, `designer.stage.measure-table`
- Tests: fichero-server/tests/unit/recipes/test_insertion_rate.py, fichero-server/tests/unit/recipes/test_noise_band.py, fichero-server/tests/unit/recipes/test_stage_measure_table.py
- Depends on: 2.2, 3.1
- Size: M

### Stage 7 — Auto-compare on open

Needs the project and app cloud caps (`training.cost.app-and-project-caps`, #5440) built first.

#### Step 7.1 — The compare runs by itself, capped, local only without truth (#6060)
- Behaviours: `designer.compare.runs-by-itself`, `designer.compare.local-only-until-truth`, `designer.compare.capped`, `designer.compare.without-truth-shows-readings-only`, `designer.compare.re-runs-when-answers-change`
- Tests: test_compare_runs_by_itself.py (not yet written), fichero-server/tests/unit/recipes/test_stage_compares_candidates_5668.py, fichero-server/tests/unit/recipes/test_bakeoff_offered_on_start_plan.py
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** a stage's try compares two or three candidates side by side (#5668, `test_stage_compares_candidates_5668.py`); Compare in Set Up works end to end on a scratch project with corrected lines, priced first (`bakeoff.next_run`), and Use This sets the winner (#5727, `test_compare_in_setup_works_5727.py`); the Start plan OFFERS the comparison and never runs it by itself (#5660 item 7, `test_bakeoff_offered_on_start_plan.py`); cloud models are compared for reading (#5718); asking granularity is measured (#5722). **Left:** (1) engine: when a stage page opens with two or more listed candidates (not under Other) the engine starts that stage's try ONCE by itself on the first three sample pages with three candidates (`COMPARED` unchanged) and the press becomes "Compare again…"; this replaces the offer-only rule for the stage page (the Start plan keeps offering); (2) with no ground truth on the pages the automatic run includes local candidates only; a cloud candidate runs on the person's press with its cost said first; (3) the compare spends from the project cloud cap with no cap of its own (Step 18.2): the automatic run leaves out and names the dearest cloud candidate that would pass what is left, and a pressed Compare that would pass it asks first; (4) without truth the result is the readings side by side, measured cost and time and the predictability words, no best label, no agreement figure, and the line "Not measured against your reading yet; check lines to compare"; (5) a change to the material answers re-runs the compare once the person leaves the page, against the same caps. **Acceptance (engine):** opening a Read page with three listed candidates and no truth starts one try with the local ones only and `auto: true`; a cloud candidate is in the answer as "press to run, $0.06"; with truth and a cap of $0.10 left, a cloud candidate priced at $0.12 is left out by name; the result without truth has no `best` and carries the not-measured line; changing the material answers and leaving the page runs one more try and no more; the Start plan's offer is unchanged (`test_bakeoff_offered_on_start_plan.py` stays green).

- test (to write): `test_compare_runs_by_itself.py` in fichero-server/tests/unit/recipes/ (once on open; local only without truth; the cloud press priced first; the dearest left out by name; readings-only result; the re-run on leaving)

#### Step 7.2 — Labels, row sentence, predicted cost and time, Use This One (#6060)
- Behaviours: `designer.compare.person-chooses`, `designer.compare.predicts-cost-and-time`, `designer.compare.row-sentence`, `designer.compare.labels-where-measured`, `designer.rank.labels-from-the-engine`
- Tests: fichero-server/tests/unit/recipes/test_compare_in_setup_works_5727.py, test_compare_labels.py (not yet written), test_compare_row_sentence.py (not yet written), test_compare_predicts_cost.py (not yet written), CompareLabelsTests.swift (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built:** `bakeoff.recommend` labels best and cheapest; Use This One per column (`use-candidate`); whole-project cost and hours from measured per-page figures in part (`routes.py` `_figure` carries a basis). **Left:** (1) engine: the served candidate list carries `labels` (best: lowest CER beyond the band; cheapest; fastest; most predictable: lowest insertion rate), set only where measured against a person's reading, with the path's what-matters-most as the lead label; the app renders them and computes none; (2) engine: each row's sentence, one string with every figure's basis: "CER 4.2% on your 3 pages · inserts 0.1% · $0.02/page · 6 s/page · whole project $18, 2 h"; (3) engine: the whole-project cost and hours as the measured per-page figures times the project's pages, basis said ("measured on 3 pages"), local candidates predicting time from measured pages an hour, replacing the routes' estimate where a measure exists; (4) app: the compare table shows the labels and the row sentence verbatim and Use This One per column. **Acceptance (engine):** with truth, the list's labels name one best, one cheapest, one fastest and one most predictable and no label where nothing is measured against a person's reading; the row sentence of a fixture candidate is exactly the string above with its numbers; the whole-project figures equal per-page × pages with the basis; the lead label follows `answers.how.matters`. **Acceptance (app, by test):** the table renders the labels and sentences from the answer and holds no CER or cost arithmetic of its own.

- test (to write): `test_compare_labels.py`, `test_compare_row_sentence.py`, `test_compare_predicts_cost.py` in fichero-server/tests/unit/recipes/ (the four labels only where measured; the lead label; the exact row sentence; the whole-project arithmetic with its basis)
- test (to write): `CompareLabelsTests.swift` in fichero/Tests/Unit/general/Models/ (beside `CompareViewTests.swift`: labels and sentences rendered from the answer, no arithmetic in the app)

#### Step 7.3 — Text beside the page; which pages to check (#6060)
- Behaviours: `designer.compare.side-by-side-text`, `designer.check.which-pages`
- Tests: fichero/Tests/Unit/general/Models/CompareViewTests.swift, CompareSideBySideTests.swift (not yet written), test_check_which_pages.py (not yet written)
- Depends on: 7.1
- Size: S

Written for the builder 2026-11-07 (spec-writer). **Built:** `StageCompareWindow` shows the compare; results today are caption rows of counts, and the side-by-side view is reached only when every candidate has a showcase (appendix, fact 10). **Left:** (1) app: the page image beside one column per candidate, the text aligned to Kraken's lines, the lines that differ from the best highlighted and inserted words marked where there is truth; for the layout stages the blocks and lines drawn over the page; the caption lines of counts go; (2) engine: the compare answer carries, per candidate and page, the lines in reading order with their line ids so the columns align, and per line `differs_from_best` and `inserted` where there is truth; (3) engine and app: the sample pages the compare ran on are proposed first for checking ("check these 3 pages: every candidate has read them"), served with the result and opened in the Reader from the stage page. **Acceptance (engine):** the result for a page carries each candidate's lines keyed by the same line ids, and with truth the per-line marks; `check_first` names the three sample pages. **Acceptance (app, by test):** the side-by-side view mounts for every result, image beside columns, aligned by line id, with the marks drawn and no caption rows; "check these 3 pages" opens the first in the Reader.

- test (to write): `test_check_which_pages.py` in fichero-server/tests/unit/recipes/ (lines keyed by id per candidate; the per-line marks with truth; `check_first`)
- test (to write): `CompareSideBySideTests.swift` in fichero/Tests/Unit/general/Models/ (the view for every result; alignment by line id; marks; no caption rows; the Reader open)

### Stage 8 — Benchmark table and the one rank rule

#### Step 8.1 — Benchmark harness and the first four rows (#6061)
- Behaviours: `designer.measure.benchmark-table`, `designer.measure.benchmark-provenance`, `designer.measure.benchmark-licence-gate`, `designer.measure.benchmark-built-by-script`, `designer.rank.run-to-run-agreement`
- Tests: fichero-server/tests/unit/recipes/test_candidates_filtered_then_ranked_4950.py, test_measured_defaults_table.py (not yet written), test_benchmark_licence_gate.py (not yet written), test_benchmark_script.py (not yet written)
- Depends on: 6.1
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** nothing of the table: `recipes/seed/` holds `cards.yaml`, `defaults-by-answers.yaml` and the language and script lists, no `measured-defaults.yaml`; `Card` has no `cer_benchmark`; the only bench script, `fichero-server/scripts/bench_reading.py`, measures speed (seconds a page), not CER; the licence words exist (`cards.is_open_licence`, `OPEN_LICENCES`) and the noise band and insertion rate are Step 6.1's (`designer.measure.noise-band`, `designer.rank.insertion-rate`), which this step depends on and does not redo. **Left, in order:** (1) the file `recipes/seed/measured-defaults.yaml` and its loader onto `Card.cer_benchmark`: one row per (language, script, period, material) of the Test Corpus × candidate, with CER headline and diplomatic, WER, insertion rate, run-to-run agreement, seconds a page, measured spend, and the provenance fields (set, page count, licence, policy, model id and version, date, price-list version, `checked_by`); (2) the licence gate as data and a guard: a set's licence is one of the vendorable classes (CC-BY, CC-BY-SA, Apache-2.0, MIT) or the row is marked `local-only` and its images are never fetched by the script for a cloud candidate; a NonCommercial or NoDerivatives set is never vendored (the guard fails the tree); (3) the script `fichero-server/scripts/bench_measured_defaults.py` that rebuilds the table through the CLI and MCP tools against a scratch engine, one family or the whole table, printing its spend and refusing to run against a library's real engine (`FICHERO_BASE_PATH` must be a scratch path); (4) the first four rows: Old French BnF fr. 412 (CC-BY-4.0), Medieval Spanish BnF Esp. 33 (CC-BY-4.0), NZZ Fraktur (Zenodo 3333627, CC-BY-4.0), Arabic Maghrebi RASAM/BULAC (Apache-2.0), measured for the shipped Kraken readers that fit and the newest model of each keyed large-cloud family, run-to-run agreement included; (5) the run-to-run column computed by reading the same lines twice, as a table column only. **Acceptance (engine):** the loader rejects a row missing any provenance field or `checked_by`, naming it; a candidate with a row for the project's language, script, period and material gets `cer_benchmark` and a candidate without gets none; a NonCommercial set in the seed fails `scripts/check_benchmark_licences.py`; the script with `--family kraken` on a scratch engine writes rows only for that family and prints the spend; the script refuses a non-scratch base path; a row with run-to-run agreement reads "agrees with itself on 99% of lines" in the row sentence; the four rows' values are present with their dates. *Decided here:* the benchmark set list beyond the first four is the open-corpora inventory the memory holds (AMSMB, HTRomance, IRHAS, FoNDUE, iForal, BADAM, Syriac, CHI-KNOW-PO, GT4HistCommentLayout; the NonCommercial Girona and Castilian sets local-only), added one family refresh at a time, never all at once; the spend figures in the bullet (US$15-30 a table) are the ceiling the script prints before it runs.

- test (to write): `test_measured_defaults_table.py` in fichero-server/tests/unit/recipes/ (the loader's shape and provenance checks; `cer_benchmark` on a matching card and none otherwise; run-to-run sentence)
- test (to write): `test_benchmark_licence_gate.py` in fichero-server/tests/unit/recipes/ (a NonCommercial row fails the guard; a local-only row never fetches images for a cloud candidate)
- test (to write): `test_benchmark_script.py` in fichero-server/tests/unit/recipes/ (a fake engine: one family writes only its rows; the spend line; the refusal of a non-scratch base path)

#### Step 8.2 — Rank by the table; fallback; reasons and predictability in words (#6062; the labels the engine serves are `designer.rank.labels-from-the-engine`, Step 7.2, which this rank feeds)
- Behaviours: `designer.rank.one-rule-every-stage`, `designer.rank.frontier-order-is-the-fallback`, `designer.rank.reasons-in-words`, `designer.rank.predictability-in-words`
- Tests: fichero-server/tests/unit/recipes/test_candidates_filtered_then_ranked_4950.py, fichero-server/tests/unit/recipes/test_period_ranks_readers_5683.py, test_rank_one_rule.py (not yet written), test_rank_reasons.py (not yet written)
- Depends on: 8.1, 6.1
- Size: M

Written for the builder 2026-11-07 (spec-writer; the harness filed this step as #6062, "step 9", and the benchmark table before it as #6061). **Built:** the rank is `assemble._rank_key(card, material, answers)` (`assemble.py:584`), filtered then ranked (`test_candidates_filtered_then_ranked_4950.py`), with period ranking readers (`test_period_ranks_readers_5683.py`); the hand order of cloud families is `discovery.frontier_rank` (`discovery.py:478`); rows carry a reason today in part (coverage, period). **Left:** `_rank_key` takes the five slots in the order the bullet states, slot 1 the measure on the person's pages (Step 6.1's table), slot 2 `Card.cer_benchmark` from Step 8.1, then coverage band, tier, what matters most, then cost and speed; `frontier_rank` is consulted only when a candidate has neither slot 1 nor slot 2; every row's reason is one sentence with its provenance, built by the engine from the slot that placed it ("CER 4.2% on your 3 pages · inserts 0.1%", "CER 6.1% on BnF fr. 412, a different manuscript in the same language; not yet measured on your pages", "coverage good, from Loove", "made for Gothic cursiva, 15th c."); every row states its predictability in words from its kind, and "not measured for predictability" when unmeasured; the app shows both sentences and writes none of its own. **Acceptance (engine):** two candidates where one has a measure on the person's pages and the other a better benchmark row rank the measured one first; two with benchmark rows only rank by the row; two with neither rank by `frontier_rank`; the reason sentence of each of the four cases is the one quoted above, with the page count or the set named; a CTC reader's row says "reads only what is on the line; may misread a word", a vision-language model's "reads fluently; may insert or regularise text", an unmeasured one "not measured for predictability"; inside the noise band (Step 6.1) two rows say "as good as each other" and what matters most decides, in words. **Acceptance (app, by test):** the candidate row shows the engine's reason and predictability sentences verbatim and holds no string of its own for either.

- test (to write): `test_rank_one_rule.py` in fichero-server/tests/unit/recipes/ (the five slots in order on fixtures; the fallback only with neither measure nor row; the band tie)
- test (to write): `test_rank_reasons.py` in fichero-server/tests/unit/recipes/ (the four reason sentences with provenance; the three predictability sentences)

### Stage 9 — Review stage

#### Step 9.1 — Review as its own stage, first slice (#6063)
- Behaviours: `designer.review.own-stage`, `designer.review.one-shipped-kind`, `designer.review.proposals-are-a-separate-pass`, `designer.review.measure-is-gain`
- Tests: fichero-server/tests/unit/recipes/test_review_preset_runs_every_lens_5723.py, fichero-server/tests/unit/recipes/test_review_follows_script_language_and_date_6128.py, test_review_stage.py (not yet written), test_review_proposals_pass.py (not yet written), ReviewProposalRowTests.swift (not yet written)
- Depends on: 6.1
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built since the spec was approved (#5723, #6128):** the palaeographer's review exists as data and nodes: profiles in `recipes/seed/review-profiles/` (`generic`, `latin`, `es-colonial`, `es-moderna`, `de-kurrent`, `en-secretary`, `aramaic`, `zh`, the shared `_frame`), each with lenses (abbreviations, orthography, names and dates); `review_profiles.choose(answers)` picks the profile by the reader-card rules and says when it fell back to the generic one; the preset `transcribe_paleography_review` runs one pass per lens (`review_passes`), its instructions are editable per project (`with_instructions`), lenses turn on and off, and the review is priced by its passes; the Reader has `ReviewAcceptAllButton`. So `designer.review.one-shipped-kind` is largely built as the profile set, and what the bullet calls "chosen by `review_profiles.choose`" is in. **Left:** (1) Review as a stage of its own in `recipes/stages.py` with the job `review-lines`, after Read and before Translate; `correct` and the unsure-lines variant become that stage's two settings (the certainty bar stays Read's one question, `designer.read.certainty-question-stays-here`, Step 1.2); spelling regularisation stays Translate's; (2) the review's output as a SEPARATE pass per line: `provenance_kind=model`, `transformation="review:<profile>"`, holding the proposed text, a reason in a few words, a confidence and the unsure spans; the person's reading is never overwritten (today the review node writes into the reading's own passes); (3) the Inspector shows the proposal beside the reading with Accept per line (`ReviewAcceptAllButton` stays as the page-level act); (4) the stage's measures: the CER gain of the reading with every proposal accepted against the reading alone, and the proposals' precision (accepted ÷ proposed), both on the checked lines, with the noise band from Step 6.1 deciding whether the gain is real (`training/reasons_ab.py:170` already computes a gain against a band for the reasons A/B: the same arithmetic, reused). **Acceptance (engine):** a plan for a project with reading and a cloud key lists `review-lines` as its own stage between Read and Translate, with the chosen profile named and "generic, no profile fits yet" when so; running it on a page writes one pass with `transformation` `review:es-colonial` whose lines each carry text, reason, confidence and spans, and the reading's passes are byte-for-byte unchanged; the stage's measure on a fixture with 100 checked lines reports gain in CER points and precision, and says "within the noise band" when the gain is under it; `correct` no longer appears as a Read job. **Acceptance (app, by test):** the Inspector's line row shows the proposal beside the reading with an Accept button per line (`inspector.review.accept.<lineId>`) that runs the existing accept action for that line only; Accept All stays.

- test (to write): `test_review_stage.py` in fichero-server/tests/unit/recipes/ (the stage in the plan between Read and Translate; the profile named or generic said; `correct` folded in; the gain and precision measure with the band)
- test (to write): `test_review_proposals_pass.py` in fichero-server/tests/unit/recipes/ (the separate pass's shape per line; the reading unchanged byte for byte)
- test (to write): `ReviewProposalRowTests.swift` in fichero/Tests/Unit/general/Views/Inspector/ (the proposal beside the reading; Accept per line acts on one line; Accept All kept)

### Stage 10 — Layout stages

#### Step 10.1 — Region-model row, lines per block, segmenter search, layout measures (#6064)
- Behaviours: `designer.layout.region-model-row`, `designer.layout.lines-per-block`, `designer.layout.segmenters-searched`, `designer.layout.measures`
- Tests: fichero-server/tests/unit/recipes/test_bakeoff_contenders_5660.py, fichero-server/tests/unit/recipes/test_regions_one_pass_5689.py, test_region_model_row.py (not yet written), test_lines_per_block.py (not yet written)
- Depends on: 2.1
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** Find Regions runs Kraken's segmenter by default or a YOLO layout model chosen as a card (`recipes/regions.py`, `prep.regions.open-default`, `prep.yolo.regions-card`, #5525), and the bake-off has contenders per stage (`test_bakeoff_contenders_5660.py`); one Kraken pass keeps lines with regions (Step 2.1). **Left:** (1) engine: Find Regions gets one row "Blocks found by" with three choices: Kraken (one pass, default), the YOLO layout model already a card, a cloud vision model with its cost per page; (2) with a YOLO or cloud region model each block's lines still come from Kraken's line finder inside the block (`lines-per-block`), so a region model never changes which lines are read, only how they are grouped; (3) the finder searches segmenters online as it does readers (the Hub's `image-segmentation` and layout cards that name regions), so Find Regions can gain a candidate (appendix, fact 3); (4) the layout stage's measures: line recall and region IoU against a person's regions on the sample pages, in the stage's measure table with the same band words as Read's. **Acceptance (engine):** the Find Regions candidates answer holds the three kinds with the cloud one priced; a plan with YOLO regions and Kraken lines segments lines per block and the line set equals Kraken's own on the same page within the blocks; a finder search for `find-regions` returns a Hub layout model as a listable row, not "cannot run"; the measure table for the stage reports line recall and region IoU on a fixture with hand-drawn regions. **Acceptance (app, by test):** the row shows the three choices and the stage page the two measures with their basis.

- test (to write): `test_region_model_row.py` in fichero-server/tests/unit/recipes/ (the three kinds priced; the finder search lists a layout model)
- test (to write): `test_lines_per_block.py` in fichero-server/tests/unit/recipes/ (lines per block equal Kraken's within the blocks; the two measures on the fixture)

#### Step 10.2 — Find the layout as one page (#6064)
- Behaviours: `designer.layout.one-page`
- Tests: FindLayoutPageTests.swift (not yet written)
- Size: S

Written for the builder 2026-11-07 (spec-writer). **Built:** Find Regions and Find Lines are two stage pages, each with its own try and result. **Left:** one page, "Find the layout", holding the region-model row (10.1), the line finder's row and ONE drawn result (blocks and lines over the sample page, Step 7.3's drawing); the two jobs stay two jobs in the recipe (`find-regions`, `find-lines`), so a recipe file is unchanged; the page's try runs both and draws once. **Acceptance (app, by test):** the stage list shows "Find the layout" once where it showed two pages; the page mounts the two rows and one drawing; the recipe written holds both jobs as before.

- test (to write): `FindLayoutPageTests.swift` in fichero/Tests/Unit/general/Models/ (one page, two rows, one drawing; the recipe's two jobs unchanged)

#### Step 10.3 — Leave out non-text segments; damaged mark (#6064)
- Behaviours: `designer.clean.leaves-out-non-text`, `designer.clean.damaged-mark`
- Tests: fichero-server/tests/unit/recipes/test_leave_out.py, test_damaged_mark.py (not yet written)
- Depends on: 6.1
- Size: S

Written for the builder 2026-11-07 (spec-writer). **Built (#6070, first slice):** the Leave Out stage between Find Lines and Read, on by default in a plan that finds and reads lines, free and on this Mac, with the rules too small, off the page and likely bleed-through (`recipes/leave_out.py`, `test_leave_out.py`), each mark saying why in `left_out` and setting `is_furniture`; the page-box, ruler and colour-card reasons (`source/image-enhancement.md` Step 3.1); the Inspector's Certainty and Damage. **Left:** (1) engine: the non-text rules the bullet still owes (a drawing or seal, a stamp, a printed form line) as reasons in the same vocabulary, each off by default until the bake-off shows it helps; (2) engine: a page or a region can carry a `damaged` mark (a person's, or a model's as a proposal), stored as the segment's or page's metadata, read by the Inspector's Certainty and Damage and by Leave Out (a damaged region's lines are left out with the reason "damaged"); (3) app: the mark in the editor's Mark tool (`preview.edit.tool.mark-ruler-card-blank`'s set gains Damaged) and the Inspector row. **Acceptance (engine):** a fixture with a seal region leaves its lines out with reason "seal" when the rule is on and keeps them when off; marking a region damaged leaves its lines out with "damaged" and the Inspector's Damage reads it; the mark is undoable. **Acceptance (app, by test):** Mark offers Damaged; the Inspector shows it.

- test (to write): `test_damaged_mark.py` in fichero-server/tests/unit/recipes/ (the mark stored and read; Leave Out's "damaged"; undo; the new non-text reasons on and off)

### Stage 11 — Teach a model

#### Step 11.1 — The offer: when, whether and where, explained (#6065)
- Behaviours: `designer.teach.offer-when-ready`, `designer.teach.asks-whether-and-where-at-the-offer`, `designer.teach.explained`
- Tests: fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py, test_teach_offer.py (not yet written), TeachOfferTests.swift (not yet written)
- Depends on: 6.1, 5.2
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** the Train page exists and the offers are computed in the engine (`recipes/train_offers.py`: readiness per job from `at_least`, the regions threshold `MIN_PAGES`, the teacher as the model that read the most pages; distillation from a teacher's passes, `training/kraken_set.py`; where it runs, local or Hugging Face, `compute/jobs-and-fine-tuning.md`). **Left:** (1) engine: the offer appears when the path's threshold is reached (default 500 checked lines for a Kraken fine-tune, the lines of 200 pages for a LoRA, or the volume rule's 5,000 pages, whichever first), served on the Train page's answer and as one line on the stage page ("Teach a model… 512 of 500 lines"); the path's teaching default (Step 5.2) decides whether it is offered pre-ticked; (2) engine: whether and where are asked AT the offer and nowhere earlier: the places the app allows, each with its time and cost from the routes, the Hugging Face cap shown; (3) app: the offer explained in plain words with "Learn more" to the manual's "Teaching a model as you go", the whether and where as one question each. **Acceptance (engine):** with 512 checked lines on a path that teaches, the Train answer carries the offer with the threshold sentence and the places; with 300 it carries the progress line (Step 3.1) and no offer; on a path that does not teach the offer is present and unticked; the places listed are only those the app allows. **Acceptance (app, by test):** the stage page's line and the Train page's offer read from the answer; the two questions appear only at the offer.

- test (to write): `test_teach_offer.py` in fichero-server/tests/unit/recipes/ (the three thresholds, whichever first; the path's default; the places from the app's allowance)
- test (to write): `TeachOfferTests.swift` in fichero/Tests/Unit/general/Models/ (the line and the offer from the answer; the two questions at the offer only)

#### Step 11.2 — Measurement, the switch, costs, the recorded switch (#6065)
- Behaviours: `designer.teach.measured-against-current-and-shipped`, `designer.teach.switch-within-band`, `designer.teach.costs-before-and-after`, `designer.run.switch-recorded`
- Tests: fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py, fichero-server/tests/unit/training/test_noise_band_per_project_5692.py, test_teach_measure_and_switch.py (not yet written), test_switch_recorded.py (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built:** a taught model is adopted only when it beats the current one past the project's noise band on held-out pages (`test_adopt_past_the_noise_band_5700.py`, `test_noise_band_per_project_5692.py`); the reasons A/B measures a student against the answer-only one with a gain and a band (`training/reasons_ab.py`). **Left:** (1) engine: the taught model is measured on held-out checked pages against the current pick, the cloud teacher and the shipped readers with the same scorer, band and insertion rate as Step 6.1, in one table; (2) the switch happens only within the band's rule (better past the band, or as good and cheaper when cost matters most), and the run records it (`designer.run.switch-recorded`: which step, from which model to which, on what figures, when; shown in Activity and on Ready's step line); (3) costs before and after the switch, predicted then measured, on the Train page. **Acceptance (engine):** a taught model at CER 4.0 against a current 4.4 with a band of 0.5 is not switched; at 3.8 it is, the switch row recorded with both figures; the table holds the current pick, the teacher and the shipped readers with insertion rate; the cost line shows before and after. **Acceptance (app, by test):** the Train page renders the table and the cost line from the answer; Ready's step line shows "switched from … on …".

- test (to write): `test_teach_measure_and_switch.py` in fichero-server/tests/unit/recipes/ (the table against the three; the band rule both ways; costs before and after)
- test (to write): `test_switch_recorded.py` in fichero-server/tests/unit/recipes/ (the switch row's fields; shown on the run and the step)

### Stage 12 — Ready and the run

#### Step 12.1 — Totals against the route; predicted then measured; cap stops; path moves as offers (#6065)
- Behaviours: `designer.ready.totals-against-the-route`, `designer.run.predicted-then-measured`, `designer.run.cap-stops-and-says`, `designer.run.path-moves-are-offers`
- Tests: fichero-server/tests/unit/recipes/test_routes_for_the_volume.py, fichero-server/tests/unit/recipes/test_cap_refusal_offers_the_fix_6295.py, test_ready_totals.py (not yet written), test_run_predicted_measured.py (not yet written), test_run_cap_stops.py (not yet written)
- Depends on: 7.2, 11.2
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built:** the routes' figures with their basis (`routes.py`), the plan's estimate and the cap refusal with fixes (Step 18.2), the run's summary with pace and cost (`activity-and-automatic-work.md` Step 2.1). **Left:** (1) engine: Ready's total predicted cost and hours as the sum of the stages' predictions (Step 7.2), shown against the route's figure in one line ("your path estimated US$120; measured on your pages, US$96"); (2) the run carries predicted then measured per stage, the summary saying both; (3) a cap that stops a run says so in the run's words with the fix (18.2's) and the pages done; (4) a path move during a run (a Teach switch, a cheaper step) is an offer on the run, clicked, never applied by itself. **Acceptance (engine):** the Ready answer's total equals the sum of the stage predictions and names the route's figure; a run's summary carries predicted and measured per stage; a run stopped by the cap says the cap, the pages done and the fixes; a switch during the run appears as an offer row and changes nothing until taken. **Acceptance (app, by test):** Ready shows the one line; Activity's row shows the offer.

- test (to write): `test_ready_totals.py`, `test_run_predicted_measured.py`, `test_run_cap_stops.py` in fichero-server/tests/unit/recipes/ (the sum against the route; predicted then measured; the stop's words; the offer row)

### Stage 13 — Workflows

#### Step 13.1 — Workflow line, Open in the editor, own workflow as a candidate, Adjust in the editor (#6066)
- Behaviours: `designer.step.names-its-workflow`, `designer.step.adjust-in-the-editor`, `designer.step.own-workflow-as-a-candidate`
- Tests: fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py, test_step_workflow_fit.py (not yet written), StepWorkflowTests.swift (not yet written)
- Depends on: 7.1
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** every recipe step runs as a workflow (a shipped preset by name or a person's own, `recipes/recipe.py` `source.recipe.steps-are-jobs`, `test_recipe_execution_to_spec.py`); the review preset is one (`REVIEW_PRESET`); the workflow editor exists (`WorkflowEditor`) and node configs hold the model and settings. **Left:** (1) engine: the stage's answer names the workflow that carries the step (`workflow: {id, kind: preset | own, name}`) and whether its node config agrees with the page's model and settings (`agrees: true` or the differing fields named); (2) engine: a person's own workflow that fits the step (its ports and its job) is listed as a candidate on the stage page with the reason "your workflow Read with notes", ranked by the same rule once it has a measure and under the fits otherwise; (3) app: one grey line on each stage page ("runs as the shipped workflow Read lines with Kraken") with "Open in the editor" (read-only for a preset), the node's config showing the same model and settings as the page, and "Adjust in the editor" on a person's own workflow writing back through the one route (`PUT /api/recipes/project`), never a second config. **Acceptance (engine):** a plan's stage answer names its preset and `agrees: true`; after a person's edit of their own workflow's model the answer names the field that differs; a person's workflow with the step's ports appears in the candidates with the reason sentence and the fit; one without the ports does not. **Acceptance (app, by test):** the grey line and Open in the editor on every stage page; a preset opens read-only; Adjust writes through the one route and the page shows the change.

- test (to write): `test_step_workflow_fit.py` in fichero-server/tests/unit/recipes/ (the named workflow and `agrees`; the differing field; the own-workflow candidate by ports)
- test (to write): `StepWorkflowTests.swift` in fichero/Tests/Unit/general/Models/ (the grey line; read-only preset; Adjust through the one route)

### Stage 14 — Sharing recipes

#### Step 14.1 — Share Recipe… and Use a Recipe… (#6067)
- Behaviours: `designer.share.export-is-the-whole-plan`, `designer.share.export-holds-nothing-private`, `designer.share.import-checks-at-the-door`, `designer.share.imported-measures-are-the-authors`
- Tests: fichero-server/tests/unit/recipes/test_check_names_every_fault_5364.py, test_recipe_export.py (not yet written), test_recipe_export_private_fields.py (not yet written), test_recipe_import.py (not yet written), ShareAndUseRecipeTests.swift (not yet written)
- Size: M

Written for the builder 2026-11-07 (spec-writer, from the code and the contract at origin/integration). **Built:** the recipe IS already a shareable file: a project holds `recipe/recipe.yaml` and `recipe/setup.yaml` (`recipes/project.py`), read by a loader that cannot run code (`recipes/recipe.py`, `SCHEMA_VERSION = 1`, `PLACES` never a person's own cluster account), checked at every door by `check_recipe` (`POST /api/recipes/check`, `test_check_names_every_fault_5364.py`), served and saved by `GET`/`PUT /api/recipes/project`; `assemble()` produces recipe.yaml data with each step's reasons. **Left:** (1) engine: `GET /api/recipes/project/export` returns the one file: the material answers, the path and what matters most, the stages and each step's job, workflow (a shipped preset by name, a person's own workflow embedded), model by provider and model id, place kind, settings and instructions, and the measured results with provenance, with a header saying what it holds and the schema version; a strip pass removes every private field (keys, pages, the person's paths and names, endpoint addresses, account names, the embedded workflow's endpoints and accounts) and a guardrail test over a recipe seeded with every such field asserts none survive; (2) engine: `POST /api/recipes/project/import` takes the file, runs `check_recipe`, and answers the check's sentences plus, per step, what this Mac does about a model not here (offer to download; or the same rank slot's candidate proposed), a cloud model with no key listed "needs a key" and never swapped, and imported measurements marked `measured_by: author`; the project's recipe is written only when the person confirms; (3) app: Project › Share Recipe… shows the prompts and instructions about to leave before writing the file (a sheet, then a save panel); Project › Use a Recipe… opens a file, shows the check's sentences and the per-step offers, and confirms; imported figures read "measured by the recipe's author on their pages" until the compare re-measures here, after which this project's figures outrank them in the rank (Step 8.2's slot 1). **Acceptance (engine):** the export of a fixture project holds every section named above and no key, path, name, endpoint or account (the guardrail's seeded recipe comes back clean); the import of that file into an empty project lists one "needs a key" step for a cloud model with no key here, one download offer for a Kraken model not installed, and writes nothing until confirmed; after confirmation `GET /api/recipes/project` returns the imported recipe with `measured_by: author` on its figures. **Acceptance (app, by test):** Share Recipe… shows the prompts before the save panel; Use a Recipe… shows the check sentences and offers; the Ready page labels an imported figure as the author's and a re-measured one by its page count.

- Build note (manager 2026-11-07, on approving 14.1): the export and the import REUSE the existing `GET`/`PUT /api/recipes/project` path where it fits (a query or a body field on it), and a new route is added only where none fits; the step text above names new routes as the shape of the answer, not as a licence to add an API.
- test (to write): `test_recipe_export.py` in fichero-server/tests/unit/recipes/ (every section present; the header; the schema version)
- test (to write): `test_recipe_export_private_fields.py` in fichero-server/tests/unit/recipes/ (a recipe seeded with every private field exports clean)
- test (to write): `test_recipe_import.py` in fichero-server/tests/unit/recipes/ (the check at the door; download offer; needs-a-key never swapped; `measured_by: author`; nothing written before confirm)
- test (to write): `ShareAndUseRecipeTests.swift` in fichero/Tests/Unit/general/Models/ (the prompts shown before the save; the check sentences and offers shown; the author's label and the re-measured label)

#### Step 14.2 — Built-in recipes and Start from a recipe (#6067)
- Behaviours: `designer.share.built-in-recipes`, `designer.share.start-from-a-recipe`
- Tests: test_builtin_recipes.py (not yet written), StartFromRecipeTests.swift (not yet written)
- Depends on: 14.1
- Size: M

Written for the builder 2026-11-07 (spec-writer). **Built:** nothing: `recipes/seed/` has no `recipes/` folder, and the path page offers the route cards only. **Left:** (1) engine: `recipes/seed/recipes/*.yaml`, the first five (a medieval Latin manuscript, an early modern Spanish notarial register, a 19th-century English logbook, a Fraktur newspaper, an Arabic manuscript), each made from a PUBLIC Test Corpus set (Step 8.1's licence gate applies: its licence and benchmark provenance in the file; the guard fails a built-in whose set is not in the vendorable list, so no private corpus ever becomes a built-in); `GET /api/recipes/builtin` lists them with set and CER ("Medieval Latin manuscript · CER 5.8% on Clm 13027"), read-only; a built-in changed by a later release is shown as an offer on a project that took it, never applied; (2) engine: `POST /api/recipes/project/start-from` takes a built-in id, a file, or another project's id on this Mac, and answers the pre-fill: the material answers, the path and the stages, each field marked `from_recipe: true`, with the fields that do not fit the new material listed as "left unticked: <why>" and not applied; (3) app: "Start from a recipe" beside the route cards offers the three sources, pre-fills About the Material, the path and the stages with each field marked "from the recipe" and editable, and says what was left unticked. **Acceptance (engine):** the five seed files load and pass `check_recipe`; a seed naming a NonCommercial set fails the guard; `start-from` with the Fraktur recipe on a project whose material answer is "manuscript" leaves the newspaper-only stage unticked and says why; another project's recipe on this Mac pre-fills the same way. **Acceptance (app, by test):** the path page shows "Start from a recipe" with built-in, file and another-project choices; after choosing, each pre-filled field carries the "from the recipe" mark and stays editable; the unticked list is shown in words.

- test (to write): `test_builtin_recipes.py` in fichero-server/tests/unit/recipes/ (the five load and check clean; the licence guard; the list's sentence; the release-change offer; `start-from` for the three sources with the unticked list)
- test (to write): `StartFromRecipeTests.swift` in fichero/Tests/Unit/general/Models/ (the three choices; the marks; editable; the unticked words)

### Stage 15 — Later milestone: recipe search and publishing

#### Step 15.1 — Recipe search (catalogue first), results with their source, publish and follow (#6068)
- Behaviours: `designer.share.recipe-search`, `designer.share.search-results-say-their-source`, `designer.share.publish-is-an-offer`
- Tests: fichero-server/tests/unit/recipes/test_check_names_every_fault_5364.py, test_find_recipes_job.py (not yet written), test_recipe_publish.py (not yet written), RecipeSearchResultsTests.swift (not yet written)
- Depends on: 14.2
- Size: M

Written for the builder 2026-11-07 (spec-writer). A later milestone (the spec's own words); specified so Stage 14 leaves room, and not for the Monday build. **Built:** nothing of it; the model finder's online search is the pattern to copy (`source.find.online-search-is-a-job`, the `find-models` job and its cache). **Left, in order:** (1) the community catalogue `fichero-recipes` does not exist (open question 9): this step builds the client side against its agreed shape (one GitHub repository, one folder per recipe holding `recipe.yaml`, `README.md` with the licence line and the public name, and `provenance.yaml`; every submission checked for schema, resolving pins, prompts and workflows present, licence) and a fixture catalogue in the tests, so the first real catalogue needs no engine change; (2) engine: a background `find-recipes` job, gated by Fichero's own-fetches list (a metadata fetch, never pages), reading the catalogue first and then recipes published by convention (`*.fichero-recipe.yaml`, the `fichero-recipe` GitHub topic) marked "not checked by the catalogue"; results cached beside the finder's, ranked by fit to the material answers with the fit in words, each naming its source, author, licence and the measurements it claims ("measured by the author on their pages"); taking one goes through Step 14.1's import door and runs nothing; with no network the built-in recipes are there and the job says it could not search; (3) engine: publish is Step 14.1's export plus a licence line and a public name, written as a pull request to the catalogue repository (through the person's own GitHub account, never Fichero's), and nothing else; following a published recipe records its catalogue id and version, and a later version is shown as an offer on the project, clicked, never applied (the same offer shape as a changed built-in, Step 14.2); (4) app: "Start from a recipe" gains the search's results below the built-ins with their source, author, licence and claimed figures, and a Publish… item in Project › Share Recipe… **Acceptance (engine):** against the fixture catalogue the `find-recipes` job returns rows ranked by fit with the fit sentence, each with source, author, licence and `measured_by: author`; a convention-found recipe is marked "not checked by the catalogue"; taking a row calls the import door and starts no run; with the network off the job answers "could not search; the built-in recipes are here" and the built-ins list is unchanged; publish produces the export plus the licence line and name, and a follow records id and version; a newer version is an offer row, not a change. **Acceptance (app, by test):** results show below the built-ins with the four facts each; Publish… is offered only after an export passes the private-fields guard.

- test (to write): `test_find_recipes_job.py` in fichero-server/tests/unit/recipes/ (the fixture catalogue; the rank and fit words; the source marks; the import door; offline)
- test (to write): `test_recipe_publish.py` in fichero-server/tests/unit/recipes/ (export plus licence and name; follow records id and version; a newer version is an offer)
- test (to write): `RecipeSearchResultsTests.swift` in fichero/Tests/Unit/general/Models/ (results below the built-ins with their four facts; Publish… gated by the guard)

### Stage 16 — A model chooser for every model-run stage (owner, 2026-10-26)

#### Step 16.1 — One shared chooser, offered by every model-run stage (#6168)
- Behaviours: `designer.model.chooser-is-one-component`, `designer.model.every-model-step-chooses`
- Tests: fichero-server/tests/unit/recipes/test_model_chooser_every_job.py, fichero/Tests/Unit/general/Recipes/StageModelChooserTests.swift
- Size: M

#### Step 16.2 — One resident local model; Leave out chooses a model (#6167)
- Behaviours: `designer.model.one-resident-local-model`
- Tests: fichero-server/tests/unit/recipes/test_one_resident_local_model.py, fichero-server/tests/unit/recipes/test_leave_out.py, fichero/Tests/Unit/general/Recipes/LeaveOutModelChoiceTests.swift
- Depends on: 16.1
- Size: M

#### Step 16.3 — Where it runs is part of the choice: Hugging Face Jobs first (#6173)
- Behaviours: `designer.model.where-it-runs-is-part-of-the-choice`
- Tests: fichero-server/tests/unit/recipes/test_recipe_remote_placement.py
- Depends on: 16.1
- Size: M

### Stage 17 — Onboarding offers the metadata language (owner, 2026-10-26)

#### Step 17.1 — The metadata language question, defaulted to the primary language
- Behaviours: `designer.onboarding.metadata-language`
- Tests: fichero-server/tests/unit/recipes/test_metadata_language_answer.py, fichero/Tests/Unit/general/Recipes/MetadataLanguageTests.swift
- Size: S

### Stage 18 — Set Up asks how, asks about the condition, and has a Budget (the maintainer, 2026-10-30; DRAFT until ruled)

Engine before app in every step; the Budget steps first because #6295 and #6294 stop runs today.

#### Step 18.1 — The estimate's basis per step; the estimate learns from booked usage (#6294)
- Behaviours: `designer.budget.basis-per-step`, `designer.budget.estimate-from-booked-usage`
- Tests: fichero-server/tests/unit/recipes/test_estimate_basis_per_step.py, fichero-server/tests/unit/recipes/test_estimate_learns_from_booked_usage_6294.py
- Size: M

#### Step 18.2 — The run cap, the audited cap action, the refusal's fixes (#6295, #6059)
- Behaviours: `designer.budget.run-cap`, `designer.budget.change-is-audited-and-undoable`, `designer.budget.refusal-offers-the-fix`
- Tests: fichero-server/tests/unit/recipes/test_run_cap_holds_with_the_project_cap.py, fichero-server/tests/unit/recipes/test_set_budget_is_audited_and_undoable.py, fichero-server/tests/unit/recipes/test_cap_refusal_offers_the_fix_6295.py, fichero-server/tests/unit/recipes/test_daily_cap_paths_6347.py, fichero-server/tests/unit/recipes/test_places_cap_projects_5828.py
- Depends on: 18.1
- Size: M

#6059 ("Recipe Designer step 6: the project and app cloud caps before any automatic spend") is this step and 18.3, not a step of its own: the harness filed it from the build order's "step 6" of the owner's summary, and the caps' behaviours live here. Written for the builder 2026-11-07 (spec-writer, from the code at origin/integration). **Built:** a Start refused for a cloud spend cap names which cap (the monthly one, the project's total one, the daily one) and the amount it needs, and offers the fixes as typed buttons (raise the cap to the dollar, change the dearest step's model, run the first N pages that fit in Finder order), the engine serving them (`cloud_cap.cap_refusals`, `fixes_for`, `first_pages_that_fit`; `test_cap_refusal_offers_the_fix_6295.py`, `test_raise_the_cap_in_place_6295.py`); both caps are changed by one audited, undoable action; the daily cap exists on every path the monthly one has (`test_daily_cap_paths_6347.py`); the app's places cap every project at use (`test_places_cap_projects_5828.py`); a raise resumes a paused run. **Left for #6059's acceptance:** (1) engine: the refusal is checked before ANY automatic spend, not only a Start: the automatic compare (Step 7.1), a re-run after an answer change, a Teach offer's measurement and a scheduled run each ask `cap_refusals` first and refuse with the same sentence and fixes; (2) engine: the plan and the run's summary carry `spent` against both caps (`spent_month`, `spent_project`, each with its cap and what this run would add), one answer the Budget block (18.3) and Activity read; (3) app (18.3): the Budget block on Ready shows spent against both caps and the refusal's fixes in place. **Acceptance (engine):** an automatic compare whose priced cloud candidate would pass what is left of the project cap is refused before it starts with the cap named, the spent figure, the run's addition and the three fixes, and the local candidates still run; the same for a Teach measurement; the plan's answer carries both `spent_*` figures with their caps; a run that fits spends and the figures move. Nothing of this reaches a second estimator: the figures are `bakeoff.next_run`'s and `cloud_cap.estimate_on`'s.

- test (to write): `test_caps_before_any_automatic_spend.py` in fichero-server/tests/unit/recipes/ (the automatic compare, a re-run, a Teach measurement and a scheduled run each refused before start with the same sentence and fixes; the two spent figures in the plan and the summary; local candidates still run)

#### Step 18.3 — The Budget block on Ready; the fix in place during a run (#6295)
- Behaviours: `designer.budget.beside-the-estimate`, `designer.budget.fix-during-the-run`
- Tests: fichero/Tests/Unit/general/Models/BudgetBlockTests.swift, fichero/Tests/Unit/general/Models/BudgetRefusalFixTests.swift, fichero-server/tests/unit/recipes/test_budget_in_the_plan.py, fichero-server/tests/unit/recipes/test_run_cap_fix_in_place.py
- Depends on: 18.2
- Size: M

#### Step 18.4 — The condition of the material: asked, suggested from a sample
- Behaviours: `designer.material.condition-asked`, `designer.material.condition-suggested-from-a-sample`
- Tests: fichero-server/tests/unit/recipes/test_condition_answers.py, fichero-server/tests/unit/recipes/test_condition_suggested_from_a_sample.py
- Size: S

#### Step 18.5 — How do you want to run this: the four questions, and the card they pick
- Behaviours: `designer.how.where`, `designer.how.model-kind`, `designer.how.what-matters`, `designer.how.access-derived-and-confirmed`, `designer.how.answers-pick-the-card`
- Tests: fichero-server/tests/unit/recipes/test_how_questions.py, fichero-server/tests/unit/recipes/test_how_access_is_derived.py, fichero-server/tests/unit/recipes/test_how_answers_pick_the_card.py
- Depends on: 5.2
- Size: M

#### Step 18.6 — The defaults table, saying why, the person wins
- Behaviours: `designer.defaults.table`, `designer.defaults.says-why`, `designer.defaults.person-wins`, `designer.defaults.caps-proposed-from-the-table`, `designer.material.condition-feeds-the-defaults`
- Tests: fichero-server/tests/unit/recipes/test_defaults_table.py, fichero-server/tests/unit/recipes/test_defaults_say_why.py, fichero-server/tests/unit/recipes/test_defaults_never_override_a_choice.py, fichero-server/tests/unit/recipes/test_defaults_from_condition.py
- Depends on: 18.4, 18.5
- Size: M

#### Step 18.7 — The risks in plain words: on the page, on Ready, after the run
- Behaviours: `designer.how.risks-in-plain-words`, `designer.how.chain-risk-on-ready`, `designer.how.what-to-check`
- Tests: fichero-server/tests/unit/recipes/test_risks_text_is_the_engines.py, fichero-server/tests/unit/recipes/test_chain_risk_on_ready.py, fichero-server/tests/unit/recipes/test_what_to_check_after_a_run.py
- Depends on: 18.5
- Size: M

### Stage 19 — Teach as you go: the staged plan across many pages (owner scenario 2026-11-08; #6407, #6406)

One answer for the owner's scenario and the Hugging Face story: the How card of `designer.how.teach-as-you-go`, built on what exists (Stage 11's offer and switch, `train_offers.py`, the distil route's `sample_pages`, `compute/distillation.md` Steps 1.1–1.3, Step 16.3's place, Step 6.1's band, Step 3.1's truth). The MLX-on-Hugging-Face line is provisional until the owner confirms.

#### Step 19.1 — The card in How: the four stages priced, the per-run sample choice, the place (#6407)
- Behaviours: `designer.how.teach-as-you-go`
- Tests: fichero-server/tests/unit/recipes/test_how_answers_pick_the_card.py, fichero-server/tests/unit/recipes/test_routes_for_the_volume.py, fichero-server/tests/unit/recipes/test_train_offers_5660.py, test_how_offers_teach_as_you_go.py (not yet written), test_teach_as_you_go_end_to_end.py (not yet written)
- Depends on: 18.5, 16.3
- Size: M

Engine: the distil route becomes a plan (steps with places and a gate step) the recipe runner takes; the sample choice (`first-n` with N, or `covering`) is a setting on the plan read by `distill.collect.first-n-or-covering-sample`; the target from the How "where" answer and the allowances. Swift: the card beside the route cards, its four stages and figures from the engine's route, the N field, the sample choice. Nothing hand-built, no new API.

- test (to write): `test_how_offers_teach_as_you_go.py` in fichero-server/tests/unit/recipes/ (the card appears with a teacher and a trainable step; its four figures and their bases; first-n and covering reach the plan; the place follows the answer and the allowances)

#### Step 19.2 — The gate with both measures, the switch, the rest on the student, never a pass rerun (#6407, #6395)
- Behaviours: `designer.how.teach-as-you-go-gate-says-both-measures`
- Tests: fichero-server/tests/unit/remote_read/test_reading_at_scale.py, fichero-server/tests/unit/training/test_noise_band_per_project_5692.py, fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py, test_teach_as_you_go_end_to_end.py (not yet written)
- Depends on: 19.1
- Size: M

The gate step measures CER and WER on the held-out checked pages (the measure of `training/evaluation.py`), decides by the band, records the switch, and the runner reads the remaining pages with the student on its place, skipping every page a model pass already read. The one end-to-end test lives in fichero-server/tests/unit/training/ and is named on `compute/distillation.md` Steps 1.1–1.3 as well.

- test (to write): `test_teach_as_you_go_end_to_end.py` in fichero-server/tests/unit/training/ (a fake Gemini labels the first 100 of 1,000 pages, and a covering sample in a second case; a fake Job returns a student; CER and WER on the held-out pages; the switch recorded; the 900 remaining run on the student on a fake Hugging Face target; a counting fake sees zero repeated passes)
