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
> Status: APPROVED 2026-10-24 (rulings below). Create
> `recipe-designer` on approval and point its description here.
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

### 4. How do you want to work? (new page, after About the Material, before Choose the Stages)

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
- `designer.clean.leaves-out-non-text` [MISSING] (#6070) — a Set Up stage leaves out segments that are not text of the page: off the page edge (the scanner bed or black background), bleed-through from the other side, damaged or torn areas, and stamps or decoration if asked. Lines are kept but marked left out, never deleted, so Read skips them and a person can bring one back. Candidates: geometry rules from the page mask (`prep.find-the-page`), Kraken baseline confidence, a vision model asked per region; measured like the other stages.
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
this Mac (Apple's recognition, a local vision model) is not a line step's candidate**
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
| Ready | `designer.ready.step.<job>` · `designer.ready.change.<job>` · `designer.ready.totals` |
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

All strings through the String Catalog; no `Text(verbatim:)`. Presence scans are not behavioural tests;
every row is [MISSING] until a spec-pinned test or `performAccessibilityAudit()` covers it.

## Build order (person-visible value first; each step shippable alone)

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

## Open question for the creative director

4. The dictionary-word rule for "lines changed beyond the CER" (needs a word list per language; none
   for Latin abbreviations); until ruled it stays [PROPOSED] and the insertion rate is the one number.

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
