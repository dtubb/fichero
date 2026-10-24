# Recipe Designer — Fichero helps a person design a good recipe for their material — Design Spec (#6052)

> Milestone: recipe-designer
> Manual: TBD — a "Designing your recipe" chapter in the Projects part, with these sections (each is the
> target of a "Learn more" link named below): **"Ways of working"** (the four paths, what each costs,
> how long, how predictable it is and what happens next); **"Teaching a model as you go"** (distil and
> fine-tune in plain words, when it is offered, where it runs); **"How a step picks its model"** (the one
> rule, measured on your pages, else a measured default, and what the words on a row mean);
> **"Comparing models on your pages"** (what Compare shows, when it runs by itself, the caps);
> **"Reading the numbers"** (CER, WER, line recall, the noise band, the insertion rate and why a
> frontier model may invent text); **"Costs while it runs"**; **"Sharing a recipe"** (what a recipe file
> holds and never holds, starting a project from one, following a published one).
> Status: DRAFT — awaiting the owner's approval before tests or code. No milestone exists yet; create
> `recipe-designer` on approval and point its description here.
> Replaces: `recipe-ranking-and-compare.md` (the 2026-10-24 first draft on this branch, `git mv`'d here).
> Sources: `agent-work/status/briefs/ranking-and-auto-compare-design.md`,
> `agent-work/status/briefs/setup-stage-screens-review-2026-10-24.md` (both 2026-10-24); the owner's
> directions of 2026-10-24, paraphrased.

Tags: [OK] built · [MISSING] not built · [PARTIAL] exists elsewhere / not wired. This spec does **not**
replace the Set Up, onboarding or recipe specs: it walks the journey **as the app does it today**, cites
each existing behaviour by its own id and tag (the owning spec stays the place to change it), and
attaches the improvements as new `designer.*` behaviours at the point of the journey where the person
meets them. The few real changes to existing behaviours are collected at the end.

## Intent (the design)

A person with a box of historical pages should be able to sit down with Fichero and, without knowing
what a Kraken model or a tokenizer is, end up with a recipe that reads their material well, at a cost,
in a time and with a predictability they chose with their eyes open. The designer is the existing
journey (set up the app, start a project, add material, say what it is, choose the stages, a page per
stage, Ready, Start, the run) made to **explain and measure** at every step: it asks how the person
wants to work and explains each path; it finds the candidates for each stage, drops the ones that
cannot write the script, ranks the rest by one rule the person can read, measures them on a few of the
person's own pages without being asked, shows the readings side by side beside the page with best,
cheapest, fastest and most predictable labelled, predicts the cost and time of the whole project, and
lets the person choose. Where a frontier model reads well but dearly, or well but inventively, it offers
to teach a smaller model from the checked lines and switches only when the measurement says it is as
good. Every number carries its provenance; no model ranks another model; the person is never asked a
question the engine can answer from the files.

It lives in Set Up (`fichero/fichero/Views/Onboarding/`: `FirstRunWindow`, `SetupFlow`,
`SetupStagePage`, `StageCandidateChooser`, `StageCompareWindow`, `ModelFinderSheet`,
`RecipeMoneyAndPlaceFields`, `RecipeReadyFields`) over the recipe engine
(`fichero-server/src/fichero_server/recipes/`: `assemble.py` `_rank_key`/`_choose`, `bakeoff.py`,
`samples.py`, `stages.py`, `discovery.py`, `step_choices.py`, `places.py`, `regions.py`,
`review_profiles.py`, `placement.py`), the evaluation (`training/evaluation.py`,
`transcription_accuracy.py`), the coverage scorers (`llm/language_coverage.py`,
`llm/script_coverage.py`) and a vendored benchmark table (`recipes/seed/measured-defaults.yaml`, to
create).

## The words (one meaning each)

- **Recipe**: the whole plan for a project: the answers about the material, the path (section 4), the
  teaching defaults (section 5), the chosen stages, and for each step its chosen model, place and
  settings, with the measured results that chose them (`source.recipe.is-a-file`,
  `source.recipe.folder-format`, `source.recipe.names-models-and-where`, section 9 of
  `models-chains-and-projects.md`).
- **Step**: one job in the recipe (`find-regions`, `find-lines`, `read-a-line`, `review-lines`,
  `find-names`…), from the job registry (`source.recipe.steps-are-jobs`, `source.recipe.jobs-are-a-registry`,
  `source.recipe.steps-work-alone-in-order`).
- **Workflow**: the thing that carries a step out. Every step runs as a workflow of the visual
  node-editor system: `recipes/start.py` maps each job to a shipped workflow preset
  (`WORKFLOW_FOR_JOB`, `_shipped`, `workflows.default_workflows.preset_workflow_id`) and passes the
  step's provider and model as the override (`source.recipe.makes-a-workflow`,
  `source.recipe.start-runs-the-steps`; the editor itself is `ui/workflows.md` and
  `ui/workflow-node-config.md`: `workflows.canvas.renders-nodes-edges-ports`,
  `workflows.canvas.locked-preset-is-read-only`, `nodeconfig.model.same-list-as-settings`,
  `nodeconfig.prompt.shows-effective-prompt`). **The recipe and the workflows are one system**: the
  recipe is the plan the person reads and chooses in Set Up; a workflow is how one step of it is wired
  and run. Choosing a model on a stage page and choosing it in the node's config are the same choice
  (`designer.step.is-a-workflow`, section 6).
- **Candidate**: a model (and the place it runs) that a step could use; **pick**: the one it does.
- **Measure**: a number against ground truth on named pages, with its provenance; **noise band**: the
  difference below which two measures are the same.

## Prior art / best practices (don't invent from scratch)

- **Model choice in Transkribus and eScriptorium.** Both make the person pick a public model by its
  card (training data, script, CER on its own validation set) and offer a run on a page before
  committing; Transkribus's public models sort by a self-reported CER and name their ground-truth
  sets. We adopt the card and the try-on-your-pages, and go further: the try is automatic, measured on
  the person's pages and a shared benchmark, and the candidates are ranked by that measurement.
- **CATMuS and HTR-United.** CATMuS (Clérice et al.) gives shared transcription guidelines and a
  multilingual medieval ground truth; HTR-United catalogues ground-truth sets with licence, script and
  period. We read both (`source.find.htr-united-and-tessdata`), score CER under a CATMuS-as-written
  policy beside the diplomatic one (`training.eval.policies-named`), and give every benchmark row the
  provenance fields HTR-United asks of a dataset: set, pages, licence.
- **CER and WER conventions.** Edit distance over the reference length, per named policy, with a noise
  band before a difference counts (ICFHR/ICDAR competitions report both; `ketos test` reports
  character accuracy). One scorer for every measurement (`training.eval.one-scorer`). Insertions are a
  separate term of the same edit distance, which is how an invented-text rate is read off it.
- **Hallucination in VLM transcription.** Recent HTR work with vision-language models reports fluent
  readings that match nothing on the page, silent "corrections" of the scribe's spelling, and
  repetition loops; CTC readers such as Kraken cannot insert words that are not on the line. The field
  measures this as insertion rate, lines changed beyond the CER, and run-to-run agreement; we adopt
  those three and the failure-mode flags already specified (`training.errors.failure-modes`).
- **Layout: SegmOnto and YALTAi.** SegmOnto names regions and lines with a controlled vocabulary;
  YALTAi trains YOLO detectors on those zones and runs Kraken's line finder per zone. Region quality is
  mean IoU per ground-truth region plus class recall (DocLayNet, YALTAi).
- **Knowledge distillation.** A large teacher labels data, a small student is trained on it and
  measured against held-out human truth (Hinton et al.; the HTR practice of bootstrapping Kraken from
  a stronger reader and correcting). An option, never a default (`distill.offered-not-default`), with
  the person's corrections outranking the teacher (`training.distil.corrections-outrank-teacher`).
- **Tokenizer coverage (Loove).** Andy Janco's Loove publishes per-model tokenizer coverage per
  language and script: a filter on what a text model can write, not a score of how well it reads; a
  Kraken codec is the same kind of fact. Coverage runs before any CER (`source.recipe.loove-tokenizer-only`).
- **What we do differently.** No model is asked to rank models: a sentence it writes carries no
  provenance. A model earns a place only as a candidate that is measured, or as a reviewer whose
  proposals are measured.

## The journey, as the app does it today, and the improvements at each point

Numbered in the order a person meets them. "Exists" cites the owning specs; "Improves" adds
`designer.*` behaviours.

### 1. Setting up the app: first launch, what Fichero runs, where models may run

**Exists.** A first launch offers Welcome, What Fichero runs and a hand-off to a project
(`source.onboard.first-launch-offers-setup`, `source.onboard.first-launch-three-screens`,
`source.onboard.app.steps`, `source.onboard.app.what-fichero-runs`, `source.onboard.app.one-continue`,
`source.onboard.app.provider-sheet-in-step`); where models may run is app-wide with no default (this
Mac, another Mac of mine, the cloud, ACENET, Hugging Face; `source.onboard.places-cap-projects`,
`ai.where.one-list-of-places`, `ai.where.settings-lists-places`); providers and keys live in Settings
(`ai/ai-settings.md`; `source.find.key-offers-frontier-models`).

**Improves.**
- `designer.app.places-say-their-consequence` [MISSING] (#6052) — each place on What Fichero runs
  carries one sentence of consequence for a recipe ("the cloud: frontier readers become candidates, and
  pages leave this Mac only when a project allows it"; "ACENET: long runs and training can be sent to
  the cluster, nothing until you say"), so the choice is made knowing what it opens.

### 2. Starting a project, and adding material

**Exists.** Set Up a Project is one view from every way in (`source.onboard.new-project-offers-setup`,
`source.onboard.project.one-view`, `source.onboard.project.steps`); Add Material takes folders, files,
a synced folder, a scan or an existing library (`source.onboard.project.add-material`,
`source.onboard.five-ways-in`, `source.onboard.icloud-pages-warned`); a pass can be marked ground
truth at import or afterwards, in the engine only (`source.onboard.ground-truth-from-files`);
text-only material is not read (`source.recipe.text-material-is-not-read`).

**Improves.**
- `designer.material.imported-transcriptions-detected` [MISSING] (#6052) — when the material arrives
  with transcriptions (PAGE, ALTO, hOCR, TEI, plain text named after its image, Tesseract `.box`), Add
  Material says how many pages carry one and from which tool, and asks once, default yes, whether they
  are this project's measure. Yes marks the passes ground truth through the existing route (one code
  path). Wording: "212 pages arrive with a transcription from Transkribus. Use them as the measure
  every model is compared against? You can correct them later; your corrections win."
- `designer.material.imported-truth-measures-at-once` [MISSING] (#6052) — with imported truth the
  bake-off readiness passes without waiting for corrected lines; every measurement in sections 7 and 8
  runs on those pages and says so ("measured on 3 of your imported pages; ground truth from the
  files"); a later correction replaces the file's reading as the reference.
- `designer.material.glyph-inventory` [MISSING] (#6052) — the project keeps an inventory of the
  characters its ground truth uses (`.box` characters, TEI `<g>`/MUFI, the text of marked passes); it
  feeds the coverage filter (section 7), the display check (section 3) and the compare's
  character-level row (the ten worst glyphs).

### 3. About the Material

**Exists.** Languages (as you type, stored as tags), scripts and direction derived from the language,
material (handwriting, print, typescript, any mix), when written and which hand, layout form, nothing
preselected (`source.onboard.project.about-material`, `source.onboard.project.language-as-you-type`,
`source.onboard.language-stored-as-tag`, `source.onboard.script-from-language`,
`source.onboard.material-any-mix`, `source.onboard.material.when-written`,
`source.onboard.material.which-hand`, `source.onboard.material.nothing-preselected`,
`source.onboard.stages.layout-forms`, `source.onboard.material.feeds-the-reader-search`).

**Improves.**
- `designer.material.questions-are-the-fit-facts` [PARTIAL] (#6052) — each question says which stage
  it feeds ("the period narrows the readers"; "the layout form decides whether blocks are found
  first"); Set Up asks no question no stage reads.
- `designer.material.script-displays-check` [MISSING] (#6052) — the script page says whether every
  character of the inventory (or, before any truth, the script's exemplars) has a bundled or system
  font: "all 418 of your characters display", or "14 characters (Canadian Syllabics, U+1400…) have no
  bundled font and show as boxes until one is added", naming the fallback family
  (`GET /api/recipes/project/script-display` over `api/routes/system/fonts.py`); the Reader uses the same
  answer.

### 4. How do you want to work? (new step, after About the Material, before Choose the Stages)

**Exists.** The pieces a path is made of: whether pages may leave this Mac, asked once
(`source.onboard.pages-may-leave`, `source.onboard.cloud-asked-once`, `source.onboard.egress-asked-twice`);
the spend cap (`source.onboard.spend-cap`, `ai.where.cloud-spend-cap`, `training.cost.app-and-project-caps`);
routes for the volume with time, cost and GHG, engine only (`source.onboard.routes-for-the-volume`);
placement of a step by scale (`source.recipe.placement-by-scale`, `compute.job.choose-where`); the
training places and their order (`training.place.compared`, `training.place.hf-priced-first`,
`training.place.slurm`, `training.place.other-macs`, `training.place.this-mac-gentle`,
`compute.tune.where-cheapest-first`); the ACENET runner (`compute/hpc-runner-acenet.md`:
`compute.hpc.plan-before-send`, `compute.hpc.slurm-target`, `compute.job.recipe-is-a-slurm-chain`);
Hugging Face Jobs as a place (`ai.where.hf-endpoint-is-a-place`, `compute.tune.proven-on-huggingface-first`).
Today these are asked in pieces across the material page, Ready and Train, with no path chosen.

**Improves.**
- `designer.path.step-exists` [MISSING] (#6052) — one page, "How do you want to work?", asks the
  person's goal and offers four paths, each a preset of defaults the later stages follow and the person
  can change at any point later (the stage pages and Ready say "from your path; change here").
- `designer.path.what-matters-most` [MISSING] (#6052) — the same page asks what matters most, one of:
  **speed**, **cost**, **quality**, **predictability** (a reading that never invents text), **running
  on a cluster**. The answer breaks ties in the rank (section 7, slot 6) and picks the label the compare
  leads with (section 8).
- `designer.path.each-path-explained` [MISSING] (#6052) — each path is shown as a card with the text
  below, followed by an estimate for this project ("about US$X and Y hours for your N pages, from the
  benchmark; measured on your pages once Compare has run") and "Learn more" → manual "Ways of working".
  The proposed wording (short enough for a Set Up page; strings through the String Catalog):
  - **(a) Start big, then teach a small model, then send the heavy runs away.** *"A frontier model
    (Claude, Gemini, GPT) reads your first pages. You check them. Fichero teaches a small model on your
    checked lines and switches to it when it reads as well; the long runs can then go to a cluster
    (ACENET) or to Hugging Face Jobs. Suits: a large archive in a hand no shipped reader knows. Cost:
    highest at the start, then near zero per page. Time: days for the first pages, then fast.
    Predictability: the frontier model may invent or 'correct' words on the first pages, so checking
    them matters; the small model never invents. Next: Compare runs on three pages, then the first
    paid pages, then a Teach a model… offer."*
  - **(b) Start on Hugging Face, move to the cluster.** *"Your readers run on Hugging Face from the
    start (paid by the hour, under your cap), and the whole run moves to ACENET when the recipe is
    settled. Suits: a project with an ACENET allocation and no wish to run on this Mac. Cost: hourly on
    Hugging Face, then your allocation. Time: depends on the queue; Fichero shows it. Predictability:
    the same as the models you choose. Next: the Hugging Face place is checked, then Compare."*
  - **(c) Frontier models throughout.** *"Every page is read by a frontier model. Suits: a small
    project, or a hand where a frontier model wins the comparison by a wide margin. Cost: per page,
    predicted before Start and watched against your cap. Time: minutes per hundred pages.
    Predictability: lowest; a frontier model reads fluently and sometimes invents or regularises
    text. The Review stage can flag what it changed. Next: Compare, then Start."*
  - **(d) Local only.** *"Nothing leaves this Mac. Kraken and the small models that ship with
    Fichero or that you download do the reading. Suits: material you may not send away, or a script
    with a good shipped reader. Cost: electricity. Time: hours per thousand pages on this Mac.
    Predictability: highest; Kraken never invents a word, though it may misread one. Next: Compare the
    shipped readers, then Start; you can teach a better local model on your corrections later."*
- `designer.path.sets-the-defaults` [MISSING] (#6052) — a path writes the existing answers rather than
  new ones: pages-may-leave (a, b, c yes; d no), the places a step may run, the spend caps proposed
  with the estimate, the teaching defaults of section 5, and the rank's tie-breaker. Changing any
  answer later detaches that answer from the path and says so; nothing else changes.
- `designer.path.estimate-is-honest` [MISSING] (#6052) — the estimate names its basis (the benchmark
  row for the language, the project's page count, the price-list version) and is replaced by the
  measured figures once Compare has run (section 8); with no benchmark row it says "no measured figure
  for this language yet" rather than a number.

### 5. Teaching a model as the project goes (new step, after the path)

**Exists.** Training is never automatic and is offered once ready, per step
(`source.recipe.train-never-automatic`, `source.recipe.train-offered-once-ready`,
`source.recipe.train-offered-per-step`); distillation is specified (`distill.offered-not-default`,
`distill.collect.sample-covers-scope`, `distill.train.card-names-teacher`,
`distill.measure.against-people`, `distill.adopt.within-bar`, `distill.retrain.must-beat`,
`distill.licence.teacher-terms`); the trainers and their places (`compute.tune.one-trainer-three-places`,
`compute.tune.kraken-recognition`, `compute.tune.lora`, `compute.tune.on-this-mac`,
`compute.tune.input-is-a-training-set`, `compute.tune.bakeoff-reads-become-training-lines`);
the model comes back as a card and is adopted only when chosen (`compute.tune.model-comes-back-as-a-card`,
`compute.tune.not-default-until-chosen`, `compute.tune.adopted-by-the-recipe`,
`compute.tune.loop-is-one-visible-cycle`); costs before training (`training.place.cost-before-train`,
`training.place.nothing-leaves-until-train`).

**Improves.**
- `designer.teach.step-exists` [MISSING] (#6052) — one early page, "Teaching a model as you go",
  seeded by the path, with three questions and an explanation: **whether** to teach (distil from the
  frontier pick, fine-tune the shipped pick, or not), **when** (after N checked lines; default 500 for a
  Kraken fine-tune, 200 pages' lines for a LoRA, editable), and **where** it runs (this Mac gently,
  another Mac of mine, Hugging Face under the cap, ACENET). Nothing trains until the person says yes
  at the offer (`source.recipe.train-never-automatic` stands).
- `designer.teach.explained` [MISSING] (#6052) — the page's text, with "Learn more" → manual "Teaching
  a model as you go": *"As you check lines, Fichero can teach a smaller model from them. **Distil**: a
  frontier model reads first, you correct, and a small model learns from the corrected lines; good when
  no shipped reader knows your hand. **Fine-tune**: a shipped Kraken reader learns your hand from your
  corrected lines; good when a shipped reader is close. Either way the new model is measured on pages
  it never saw, against the model you use now, and is offered, never switched in by itself. Cost: a
  frontier read of the first pages (distil only) plus training time; on this Mac it is free and slow,
  on Hugging Face about US$X an hour, on ACENET your allocation. Predictability: a Kraken model you
  teach never invents words; a small vision model is checked for that before it is offered."*
- `designer.teach.estimate` [MISSING] (#6052) — the page shows the predicted saving for this project
  on each choice ("after about 500 checked lines, the rest of your 4,000 pages would cost US$0 instead
  of US$140; training about 3 h on this Mac"), from the benchmark and the path's estimate, replaced by
  the measured figures after the first compare.

### 6. Choose the Stages, and the stage pages: what each stage produces

**Exists.** Stages are chosen first; each has a page that says what it does, who runs it, asks its own
questions and shows its result on 3 to 5 of the person's pages; the list is the engine's
(`source.onboard.stages.choose-first`, `source.onboard.stages.stages-list-from-the-engine`,
`source.onboard.stages.goals-are-shortcuts`, `source.onboard.stages.needs-are-ticked`,
`source.onboard.stages.page-says-what-it-does`, `source.onboard.stages.page-who-runs-it`,
`source.onboard.stages.page-asks-its-questions`, `source.onboard.stages.samples-proposed`,
`source.onboard.stages.sample-result`, `source.onboard.stages.explanation-always-shown`,
`source.onboard.stages.train-and-ready-last`). The stages today: Clean Up Images · Find Regions · Find
Lines · Read · Translate · Organise · Names · Statements · Dates & Times · Passages · Structured Data ·
Search, then Train and Ready.

**Clean Up Images.** Exists: `prep.find-the-page`, `prep.split-at-the-gutter`,
`prep.straighten-and-flatten`, `prep.never-changes-the-original`, `prep.methods-are-cards-the-recipe-chooses`.
No change proposed here.

**Find Regions and Find Lines.** Exists: both default to Kraken `blla` (`prep.regions.open-default`,
`prep.regions.one-find-regions`, `prep.yolo.regions-card`); line finders are a candidate list
(`source.recipe.line-finders-are-a-candidate-list`, `source.recipe.apple-finds-lines-on-print`); mixed
writing per region (`source.onboard.stages.mixed-writing-per-region`). Improves:
- `designer.layout.one-kraken-pass` [PARTIAL] (#6052, #6014) — when both finders are Kraken, one `blla`
  segmentation gives regions and lines; Find Lines and Read never segment again. (Built: one call
  returns both and each line keeps its region; not built: the bake-off and runner re-call the segmenter.)
- `designer.layout.region-model-optional` [MISSING] (#6052) — Find Regions gets one row, "Blocks found
  by": Kraken (one pass, default), a YOLO layout model (DocLayNet now; a SegmOnto-trained YALTAi model
  first to add), or a cloud vision model with its cost per page.
- `designer.layout.lines-per-block` [MISSING] (#6052, #6014) — with a YOLO or cloud region model, each
  block is cropped and Kraken's line finder runs per block; lines keep their block; reading order is
  blocks in the model's order then lines top-down, blocks right to left for right-to-left scripts.
- `designer.layout.segmenters-searched` [MISSING] (#6052) — the online search for these stages includes
  Kraken segmentation models (Zenodo through htrmopo, `kind: segmentation`) and object-detection
  models with a `.pt`/ONNX file as runnable YOLO cards; where nothing can run, the engine's sentence
  says so (review item 3).
- `designer.layout.measures` [MISSING] (#6052) — the measures are line recall and extra lines
  (`bakeoff.score_lines`) and, where region truth exists, mean best IoU per region with a class recall;
  the compare says "lines found 212 of 218 · 3 extra · blocks IoU 0.81 · 4 s/page".
- `designer.layout.one-stage-proposal` [MISSING] (#6052; **a proposal, not a given**) — merge the two
  pages into one, "Find the layout", explained as finding the blocks, then the lines in each block and
  their order, with one drawn result. Everything above works with two pages; this line only asks the
  owner whether one page reads better (open question 1).

**Read.** Exists: one candidate list per step and a step lists only what it can take
(`source.find.one-candidate-source`, owner ruling 2026-10-24); scripts first
(`source.recipe.script-reader-first`, `source.recipe.no-cross-script-reader`); cloud readers get Kraken's
line pictures, one call a page (`source.recipe.cloud-reads-lines-per-page`); frontier readers are
compared on the try pages (`source.recipe.reader-tiers.frontier-on-the-try-pages`); the tier order with
no measurement (`source.recipe.reader-tiers`); Apple's recognition is for modern writing
(`source.recipe.apple-vision-is-for-modern-writing`); the certainty bar and the unsure-lines variant
(`source.recipe.kraken-reads-cloud-corrects-unsure`, `source.recipe.kraken-then-cloud-unsure-lines`,
`source.recipe.certainty-is-calibrated`). Improves:
- `designer.read.measures` [PARTIAL] (#6052) — Read's measures are CER (WER beside it) on the checked
  or imported lines under the project's policy, the diplomatic policy beside the headline
  (`training.eval.policies-named`, `training.eval.wer-beside-cer`), and the **insertion rate** of
  section 7.
- `designer.read.certainty-question-stays-here` [PARTIAL] (#6052) — the certainty bar stays Read's one
  question; the "a cloud model corrects the unsure lines" choice is offered once, on the Review page
  below, not also on Read's menu (review item 5).

**Review (proposed new stage, after Read, before Translate).** Exists: Correct is a job inside Read
with a page-level prompt and no reasons (`source.recipe.kraken-reads-cloud-corrects-unsure`;
`review_profiles.py`, shipped profiles with three lenses); reviews get the project's names
(`source.job.review-uses-the-projects-names-and-places`). Improves:
- `designer.review.own-stage` [MISSING] (#6052) — Review is a stage of its own (job `review-lines`);
  `correct` and the unsure-lines variant move into it. Spelling regularisation is Translate /
  Normalise's, not Review's.
- `designer.review.kind-level-instructions` [MISSING] (#6052) — a review has a **kind** (shipped YAML in
  `seed/review-kinds/`: palaeographer, proof-reader against an edition, letter forms and abbreviations;
  the person's own in the library), a **level** (line or page), and editable **instructions** seeded
  from the kind; kinds that suit the material are listed first (`review_profiles.choose`), with a
  default per kind of project (palaeographer for handwriting before 1800; proof-reader for print with an
  edition at hand; none for typescript).
- `designer.review.proposals-are-a-separate-pass` [MISSING] (#6052) — the reviewer writes a separate
  pass (`provenance_kind=model`, `transformation="review:<kind>"`) holding per line the proposed text, a
  reason in a few words, a confidence and the unsure spans; the person's reading is never overwritten;
  the Inspector shows the proposal beside the reading with Accept per line. A review therefore also
  shows what a frontier reader changed, which is the predictability check of path (c).
- `designer.review.measure-is-gain` [MISSING] (#6052) — Review's measures are the CER gain of the
  reading with every proposal accepted against the reading alone, the precision of the proposals, and
  the share of proposals that insert text absent from the truth.

**Translate, Organise, Names, Statements, Dates & Times, Passages, Structured Data, Search.** Exists:
`source.onboard.stages.normalise-and-translate`, `source.onboard.stages.organise-tried-on-a-run`,
`source.onboard.stages.kinds-are-open-ended`, `source.onboard.stages.passages-says-what-it-does`,
`source.job.find-statements.candidates`. Improves:
- `designer.stage.measure-table` [MISSING] (#6052) — one short table, served with the stages, names
  each stage's measure and ground truth: Find Regions → region IoU and class recall against marked
  layout; Find Lines → line recall and extras; Read → CER, WER, insertion rate against checked or
  imported lines; Review → CER gain, precision, insertions; Translate/Normalise → agreement with checked
  lines; Names → precision and recall against checked names; Statements → F1 against checked triples;
  a stage with no measure yet says so.

**Every step is a workflow; a person's own workflow can be a step.** Exists: each job runs its
shipped preset with the step's model as the override (`source.recipe.makes-a-workflow`,
`source.recipe.start-runs-the-steps`, `WORKFLOW_FOR_JOB`); presets are locked in the editor
(`workflows.canvas.locked-preset-is-read-only`); a node's model list is Settings' list
(`nodeconfig.model.same-list-as-settings`); recipes run library-pinned
(`workflows.defaults.recipes-user-level-runs-library-pinned`, GAP). Improves:
- `designer.step.is-a-workflow` [PARTIAL] (#6052) — every stage page says, in one grey line, which
  workflow carries the step ("runs as the shipped workflow Read lines with Kraken") with "Open in the
  editor", which opens that workflow read-only for a preset, showing the step's model and settings in
  the node's config; the two views never disagree because both read the recipe's step.
- `designer.step.own-workflow-as-a-step` [MISSING] (#6052) — a workflow the person built in the node
  editor is offered as a candidate for a step when its inputs and outputs fit the job (the job registry
  says what goes in and what comes out, `source.recipe.jobs-are-a-registry`; the workflow's accepted
  inputs and declared writes, `workflows.bar.selection-projected-through-accepted-inputs`,
  `workflows.canvas.node-shows-reads-and-writes`); it is listed under "Your workflows" with the fit said
  in words ("takes lines, writes a reading pass: fits Read"), is measured and compared like any other
  candidate, and a workflow that does not fit is listed under Other with the reason.
- `designer.step.adjust-in-the-editor` [MISSING] (#6052) — "Adjust in the editor" copies a shipped
  preset into the person's workflows (`workflows.defaults.duplication-regrown`), opens it editable, and
  the step then points at the copy; Ready names the copy and the recipe records it as the step's
  workflow by id, so a shared recipe (section 12) carries it.

### 7. On every stage page: candidates found, filtered, ranked by one rule

**Exists.** One candidate list per step from the shipped cards, the models here, Kraken's repository,
HTR-United, Hugging Face and remote endpoints (`source.find.by-need`, `source.find.wide-every-time`,
`source.find.one-candidate-source`, `source.find.zenodo-through-htrmopo`,
`source.find.htr-united-and-tessdata`, `source.find.key-offers-frontier-models`,
`source.find.models-that-run-remotely`, `source.find.worth-listing-engine`,
`source.find.online-search-is-a-job`, `source.find.online-search-per-step`); fit filters then a rank
(`source.recipe.candidates-filtered-then-ranked`, `source.recipe.period-weighs-in-the-reader-rank`,
`source.recipe.reader-pick-from-the-material`, `source.recipe.candidates-fallback-chain`); model and
place ranked as a pair (`ai.where.rank-pairs`, `ai.where.step-names-a-pair`); cloud cards need
permission until allowed (`source.onboard.pages-may-leave`, `source.find.cloud-card-says-it-once`);
Loove coverage is a Settings matrix with no link to recipes (`source.recipe.loove-tokenizer-only`;
`ai/ai-settings.md`, "Language coverage"); the finder opens from a step (`source.find.choose-a-model-opens-the-finder`,
`source.onboard.stages.page-lists-found-models`, `source.onboard.stages.step-names-its-model`).

**Improves.**
- `designer.rank.one-rule-every-stage` [PARTIAL] (#6052) — every stage ranks by the same order:
  (1) measured on the person's pages, (2) the vendored measured default for this language and script
  (section 8), (3) coverage band, (4) card fit (script, language, period, material, hand), (5) tier,
  (6) what matters most from the path (speed · cost · quality · predictability · cluster), then cost and
  speed. The frontier family order (`discovery.frontier_rank`) is only the fallback for a model with no
  benchmark row. The rule is `assemble._rank_key`, extended; what differs by stage is which measure
  fills slot 1 and which table slot 2 (`designer.stage.measure-table`).
- `designer.rank.predictability-is-a-fact` [MISSING] (#6052) — every candidate row states the
  trade-off in words ("never invents words; may misread one" for a CTC reader; "reads fluently; may
  invent or regularise text" for a vision-language model) and, where measured, as numbers: the
  **insertion rate** (inserted characters and words not in the ground truth, per hundred reference
  characters), the **share of lines changed beyond the CER** (lines whose edit distance is dominated by
  insertions or by substitutions that form a dictionary word the truth does not have), and
  **run-to-run agreement** (the same lines read twice). A candidate with no measurement yet says
  "not measured for predictability".
- `designer.rank.coverage-filters-before-cer` [MISSING] (#6052) — a text or vision-language model's
  Loove coverage for the project's languages and scripts, and a Kraken codec against the glyph
  inventory, become a `Card.coverage` band (covered · unknown · poor) at discovery, a slot ahead of card
  fit; the heuristic coverage is never ranked (it is "unknown").
- `designer.rank.refuses-unwritable-characters` [MISSING] (#6052) — a candidate that can never output
  characters the ground truth actually uses (MUFI private-use, Newa outside the BMP, polytonic
  combining marks) is refused by the hard constraints with the count said ("cannot write 14 of your
  characters"), before any paid call.
- `designer.rank.reasons-in-words` [PARTIAL] (#6052) — every row says why it sits where it sits, with
  provenance: "CER 4.2% on your 3 pages · inserts 0.1%", "CER 6.1% on BnF fr. 412 (Old French), not yet
  measured on your pages", "coverage good, from Loove", "made for Gothic cursiva, 15th c."; best,
  cheapest, fastest and most predictable are labelled.
- `designer.rank.one-visible-selection` [PARTIAL] (#6052) — the chosen row stays in its tier with a
  leading radio mark and a tinted row, not moved to a head group; the cloud-permission line is shown
  once above the cloud tier; the nothing-found sentence comes from the engine for every job (review
  items 6, 7, 8).
- `designer.rank.finder-for-every-model-step` [PARTIAL] (#6052) — "Choose a model…" opens the finder
  for any step whose job needs a model, not only the reading jobs; the download / choose-cloud /
  choose-model fix buttons collapse into that one press (review items 1, 4, 5).
- `designer.rank.searches-on-open` [PARTIAL] (#6052) — the finder searches online by itself when it
  opens for a step that has a search (as integration builds it, 1c008843d, d9a1cd231), says it is
  searching and what it found; the press is "Search again"; a job with no online search disables the
  press with the reason.

### 8. On every stage page: measured on your pages, measured on the benchmark, compared by itself

**Exists.** The bake-off scores CER, WER and line recall on marked or person-made passes under named
policies with a noise band, needs 100 corrected lines on two pages and says so, and is the same tool as
a stage's Compare (`source.try.bakeoff-is-the-same-tool`, `source.train.noise-band-per-project`,
`training.eval.one-scorer`, `training.eval.not-read-is-not-100`, `training.regression.noise-band-one-number`,
`source.try.bakeoff-hidden-until-corrected`, `source.onboard.stages.compares-candidates`,
`source.onboard.stages.compare-results-per-model`, `source.onboard.stages.compare-names-its-models`,
`source.onboard.stages.try-progress-in-place`, `source.onboard.stages.try-waiting-says-why`,
`source.onboard.stages.samples-are-not-the-work`, `source.try.never-over-existing`,
`source.try.kept-and-rerunnable`, `source.try.use-this-scope`, `source.try.compare-in-setup-works`,
`ai.where.bakeoff-scores-any-place`); the Try is pressed (`source.try.any-time`,
`source.find.try-before-default`); failure modes are specified (`training.errors.failure-modes`).
Nothing measured ships with the app.

**Improves — measuring.**
- `designer.measure.on-your-pages-first` [PARTIAL] (#6052) — a measurement on the person's pages
  (imported truth or corrected lines) is slot 1 of the rank, labelled with its page count; a project
  with neither falls to the benchmark table and says so.
- `designer.measure.benchmark-table` [MISSING] (#6052) — `recipes/seed/measured-defaults.yaml` holds,
  per language and script row of the Test Corpus, for each candidate (the shipped Kraken readers that
  fit, Apple's recognition on the page step, Tesseract for print rows, the MLX small VLM, the newest
  model of each keyed frontier family): CER (headline and diplomatic), WER, **insertion rate**, lines
  changed beyond the CER, run-to-run agreement, seconds a page, measured spend; layout rows (line
  recall, region IoU); review rows (gain, precision, insertions). Loaded as `Card.cer_benchmark`; no
  default for a language without a row.
- `designer.measure.benchmark-provenance` [MISSING] (#6052) — every row names its set, page count,
  licence, policy, model id and version, date and price-list version; the Set Up reason repeats the set
  and language. Sets are the Test Corpus folders with their README licences; images never leave the
  Mac for a set whose licence forbids it; the table is rebuilt by a script through the MCP/CLI tools on
  a test engine, never by hand; about US$15–30 for the first full table, US$3–5 per family refresh.
- `designer.measure.noise-band` [PARTIAL] (#6052) — one band per project (default one CER point;
  measured from 15 or more pages when there are enough); candidates inside the band are "as good as
  each other", and then what matters most decides, in words.
- `designer.measure.says-what-it-cannot-measure` [PARTIAL] (#6052) — a stage that cannot measure says
  so plainly and names what would let it ("Compare measures against lines you have corrected. Read a
  few pages first, then correct about 100 lines on two pages"), never a count of corrected lines in a
  project with nothing read (review item 11).

**Improves — comparing.**
- `designer.compare.runs-by-itself` [MISSING] (#6052) — when a stage page opens with two or more
  candidates worth comparing (or the material answers change), the engine starts that stage's try once,
  by itself, on the first 3 sample pages; the press becomes "Compare again…" (up to 5 candidates, the
  full samples). Nothing runs when the cap is reached, or pages may not leave and every candidate is
  cloud, and the page says which.
- `designer.compare.capped` [MISSING] (#6052) — an automatic compare is priced first (`bakeoff.next_run`)
  and held under `places.auto_compare_cap_usd` (default US$0.50 a stage, US$2 a project, inside the
  project's cloud cap); the dearest cloud candidate over the cap is left out and named; local
  candidates always run.
- `designer.compare.side-by-side-text` [MISSING] (#6052) — the page image beside one column per
  candidate, text aligned to Kraken's lines, lines differing from the best highlighted and inserted
  words marked; for the layout stages the blocks and lines drawn; the caption lines of counts go
  (review item 10).
- `designer.compare.best-cheapest-fastest-steadiest` [PARTIAL] (#6052) — the summary labels best
  (lowest CER beyond the band, else agreement), cheapest, fastest and **most predictable** (lowest
  insertion rate and highest run-to-run agreement); the path's "what matters most" is the lead label;
  each row reads "CER 4.2% on your 3 pages · inserts 0.1% · $0.02/page · 6 s/page · whole project $18,
  2 h". (Built: best and cheapest in `bakeoff.recommend`; not built: the rest.)
- `designer.compare.predicts-cost-and-time` [PARTIAL] (#6052) — the predicted cost and hours for the
  whole project are the measured per-page figures times the project's pages, basis said ("measured on 3
  pages"); local candidates predict time from measured pages an hour (`training.ab.cost-and-time-beside`,
  `ai.where.estimate-names-the-place`); the path's estimate (section 4) is replaced by this.
- `designer.compare.person-chooses` [PARTIAL] (#6052) — the compare proposes; the person chooses with
  Use This One per column (`use-candidate`, unchanged; `source.find.one-candidate-source`); Ready names
  the pick (section 10).

### 9. Train: the offer, as the project goes

**Exists.** Train is its own page, offered later (`source.onboard.stages.page-trains`,
`source.recipe.train-offered-per-step`); the training loop, places and A/B (`compute.tune.*` and
`training.*` cited in section 5; `training.ab.beats-current-by-noise-band`, `training.model.compare-on-more-pages`,
`distill.eval.held-out-checked-pages`, `distill.eval.cer-variants`).

**Improves.**
- `designer.teach.offer-when-ready` [MISSING] (#6052) — when the count from section 5 is reached, the
  Train page (and a line on the stage page) offers "Teach a model…" with the two candidates priced
  (distil from the frontier pick · fine-tune the shipped pick), the place from section 5, the predicted
  saving, and the explanation of section 5 repeated in one sentence.
- `designer.teach.measured-against-frontier-and-shipped` [MISSING] (#6052) — the trained model is
  measured on held-out checked pages against the current pick, the frontier model and the shipped
  Kraken and small readers, with the same scorer, noise band and insertion rate as section 8.
- `designer.teach.switch-within-band` [MISSING] (#6052) — within the noise band of the current pick the
  rest of the run switches to the taught model (with the person's yes, per
  `compute.tune.not-default-until-chosen`); otherwise the run carries on and says why.
- `designer.teach.costs-before-and-after` [MISSING] (#6052) — before: the frontier spend on the first
  pages, training time and place, the predicted saving; after: the taught model's cost per page and the
  measured spend, on the Train page and at Ready.

### 10. Ready

**Exists.** Ready lists the plan plainly, grouped, naming each step's model and place, what runs by
itself and what will not run (`source.onboard.ready-speaks-plainly`, `source.onboard.ready.grouped-sections`,
`source.onboard.ready.words-not-engine-errors`, `source.onboard.ready.will-not-run-when-chosen`,
`source.onboard.auto.plan-shows-what-will-not-run`, `source.onboard.stages.step-names-its-model`,
`source.onboard.step-candidates-on-the-plan`, `source.onboard.step-choice-overrides-the-pick`,
`source.recipe.missing-model-offered`, `ai.where.ready-shows-the-pair`).

**Improves.**
- `designer.ready.one-line-per-step-with-change` [PARTIAL] (#6052) — each step is one line: the chosen
  model, its place, its measured figure with provenance, its predictability words, the predicted cost
  and time, and Change… opening the one finder. The per-step candidate menus on Ready go (review item 9).
- `designer.ready.totals-from-the-path` [MISSING] (#6052) — Ready's total predicted cost and hours is
  the sum of the stages' predictions and is compared with the path's estimate in one line ("your path
  estimated US$120; measured on your pages, US$96").

### 11. Start, and the run

**Exists.** Start runs the steps in order, in batches, resumable, status in Activity, each step counting
its pages and saying why it was skipped (`source.recipe.start-runs-the-steps`,
`source.recipe.batch-at-archive-scale`, `source.recipe.batch-checkpoint`, `source.recipe.run-status-is-activity`,
`source.recipe.step-counts-its-pages`, `source.recipe.step-skipped-says-why`,
`source.recipe.failed-step-offered-again`); costs are shown where known (`compute.job.costs-shown-where-known`,
`ai.where.one-pricer-every-place`, `ai.where.one-cloud-cap`, `ai.where.activity-shows-the-place`);
no silent fallback (`ai.where.no-first-provider-fallback`, `source.egress.no-silent-cloud-fallback`);
a run can be sent to the cluster (`compute.job.recipe-is-a-slurm-chain`, `compute.hpc.plan-before-send`).

**Improves.**
- `designer.run.predicted-then-measured` [MISSING] (#6052) — the predicted totals are kept with the run;
  Activity shows spend and elapsed time against them per stage; the run's end writes the measured totals
  beside the prediction and the path's estimate.
- `designer.run.cap-stops-and-says` [PARTIAL] (#6052) — a run that reaches the project's cloud cap
  stops the paid step, keeps what is done, and offers the next candidate from the stage's compare or a
  raised cap; never another provider by itself.
- `designer.run.switch-recorded` [MISSING] (#6052) — a taught-model switch mid-run is recorded on the
  pages it changed, so a page's reading says which model made it (`source.recipe.recorded-on-what-it-made`).
- `designer.run.path-moves-are-offers` [MISSING] (#6052) — the later moves of a path (to the taught
  model, to Hugging Face Jobs, to ACENET) appear as offers in Activity when their condition is met,
  each with its cost and time, never started by themselves.

### 12. Sharing a recipe: export, import, start from a recipe

**Exists.** Sharing is specified in section 12 of `models-chains-and-projects.md` and largely unbuilt:
the recipe as a file in a folder format, schema-versioned, travelling with an export, never holding keys
(`source.recipe.is-a-file` GAP, `source.recipe.folder-format` PARTIAL, `source.recipe.schema-versioned` OK,
`source.recipe.travels-with-export` GAP, `source.recipe.never-holds-keys` PARTIAL,
`source.recipe.data-not-code` PARTIAL, `source.recipe.prompt-files` GAP); publish, follow, update,
override and fork (`source.recipe.publish` GAP, `source.recipe.follow-and-update` GAP,
`source.recipe.update-is-clicked-not-applied` GAP, `source.recipe.update-measured-here` GAP,
`source.recipe.overrides-kept` GAP, `source.recipe.fork` GAP); taking a recipe whose step is missing here
(`source.recipe.take-without-missing-step` PARTIAL); a missing key never substitutes
(`source.recipe.missing-key-never-substitutes`); a pinned model gone is said
(`source.recipe.pinned-model-gone`).

**Improves.**
- `designer.share.export-is-the-whole-plan` [MISSING] (#6052) — Project › Share Recipe… writes one
  file holding the answers about the material, the path and what matters most, the teaching defaults,
  the stages and each step's job, workflow id (a shipped preset by name, a person's own workflow
  embedded), model by provider and model id, place kind (never an address or account), settings and
  instructions, and the measured results with their provenance (measure, value, page count, policy,
  date). Never keys, never pages, never the person's paths or names; the file says so in its header.
- `designer.share.import-into-a-project` [MISSING] (#6052) — Project › Use a Recipe… reads a file
  into an open project: the steps and models are checked at the door (`source.recipe.checked-at-every-door`,
  `source.recipe.check-names-every-fault`); a model not here is offered for download or a candidate
  from the same rank slot proposed (`source.recipe.missing-model-offered`,
  `source.recipe.take-without-missing-step`); a cloud model with no key here is listed needs-a-key, never
  swapped; the imported measurements are shown as "measured by the recipe's author on their pages", and
  the auto-compare re-measures on this project's pages, which then outrank them.
- `designer.share.start-from-a-recipe` [MISSING] (#6052) — Set Up's first page offers "Start from a
  recipe" beside the four paths: a file, or a recipe from another project on this Mac; the answers it
  carries pre-fill About the Material, the path and the stages, each marked "from the recipe" and
  editable; what does not fit the new material (another script, another period) is said and left
  unticked, never applied silently.
- `designer.share.built-in-recipes` [MISSING] (#6052) — Fichero ships a few good starting recipes
  per kind of project, vendored in `recipes/seed/recipes/*.yaml` in the export format above (a medieval
  Latin manuscript, an early modern Spanish notarial register, a 19th-century English logbook, a Fraktur
  newspaper, an Arabic manuscript, to begin), each carrying the measured results and provenance of the
  Test Corpus benchmark rows it was chosen from (`designer.measure.benchmark-table`,
  `designer.measure.benchmark-provenance`). "Start from a recipe" lists them first, titled by the kind
  of material with the set and CER beside ("Medieval Latin manuscript · CER 5.8% on Clm 13027"); a
  built-in recipe is read-only until taken into a project, and the one taken is marked "from Fichero's
  recipe, <version>" so a later release's change is an offer, not a silent update
  (`source.recipe.update-is-clicked-not-applied`, `source.recipe.data-not-code`).
- `designer.share.recipe-search` [MISSING] (#6052) — "Start from a recipe" also searches online for
  published recipes, on the pattern of the model finder's searches (`source.find.online-search-is-a-job`,
  `source.find.wide-every-time`, `source.find.zenodo-through-htrmopo`, `source.find.htr-united-and-tessdata`,
  `source.find.reason-names-fit`): a background `find-recipes` job, egress-gated like every other fetch
  (`source.egress.every-call-site`, `source.egress.fichero-own-fetches-listed`), that reads **first the
  `fichero-recipes` community catalogue** already named by section 12 of `models-chains-and-projects.md`
  (ruled 2026-10-01; open question 6 there): one GitHub repository, one folder per recipe, every
  submission checked (schema, pins resolve, prompts and workflows present, licence), mirrored to Zenodo
  for a DOI (`source.recipe.publish`, `source.recipe.follow-and-update`, `source.recipe.is-a-file`,
  `source.recipe.schema-versioned`). The repository does not exist yet (no `dtubb/fichero-recipes` as of
  2026-10-24; open question 9). Second, recipes published elsewhere by a convention (files named
  `*.fichero-recipe.yaml`, or the `fichero-recipe` GitHub topic), listed after the catalogue's and
  marked "not checked by the catalogue". Results are cached beside the finder's
  (`hugging-face-steps.json`'s neighbour), ranked by fit to the
  material answers (script, language, period, material) with the fit said in words, each result naming
  where it came from, its author, its licence and the measured results it claims (marked "measured by
  the author on their pages"). It never runs anything: taking a result only fills Set Up's answers and
  steps through the import door above (`designer.share.import-into-a-project`), and the auto-compare
  re-measures here. With no network, or pages-may-leave unanswered, the search is not started and the
  page says so; the built-in recipes are always there.
- `designer.share.publish-is-an-offer` [MISSING] (#6052) — publishing (to a folder, a Hugging Face
  dataset or a URL the person names) is the export plus a licence line and a public name; following a
  published recipe checks for updates, which are shown and clicked, never applied
  (`source.recipe.update-is-clicked-not-applied`, `source.recipe.publish`, `source.recipe.follow-and-update`
  stand as the owning lines).

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
   become one answer (review items 4, 9).
3. **Correct moves out of Read.** `source.recipe.kraken-reads-cloud-corrects-unsure` and
   `source.recipe.kraken-then-cloud-unsure-lines` put the unsure-lines correction on Read's menu. This
   spec moves it into a Review stage with line-level proposals in a separate pass
   (`designer.review.*`); the certainty bar stays Read's. The page-level "output the complete corrected
   transcription" prompt goes.
4. **The compare starts by itself.** `source.try.any-time`, `source.find.try-before-default`,
   `source.onboard.stages.compares-candidates` describe a compare the person starts. This spec starts
   it once by itself, capped (`designer.compare.runs-by-itself`, `designer.compare.capped`); the press
   remains.
5. **Frontier order becomes the last fallback.** `_frontier_first` and `discovery.frontier_rank` order
   frontier readers by a hand list of families; here that order is used only for a model with no
   benchmark row (`designer.rank.one-rule-every-stage`). `source.recipe.reader-tiers` keeps its tier
   order as a later slot.
6. **Apple's recognition on the line step.** The ranking brief listed Apple Vision as a benchmark
   candidate for every row; the owner's ruling B of 2026-10-24 (`source.find.one-candidate-source`)
   says the line step lists only what `use-candidate` accepts, and a page reader on this Mac is not a
   line step's candidate. This spec follows the ruling: Apple's recognition is measured on the
   page-reading step and the print line-finding row only.
7. **The first draft's ids.** `recipe.rank.*`, `recipe.compare.*`, `recipe.review.*`, `recipe.coverage.*`,
   `recipe.regions.*` and `source.recipe.distil-*` from `recipe-ranking-and-compare.md` are retired for
   the `designer.*` ids above; no test cited them.

Not changed: the stage names and order (a one-page "Find the layout" is only proposed,
`designer.layout.one-stage-proposal`); the places setting, the pages-may-leave question and the spend
cap (the path writes them, it does not replace them); training never automatic; every existing
`source.onboard.stages.*` page behaviour.

## Test matrix (paste from `../TEST-TEMPLATE.md`, tick the legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | path cards and their wording keys, candidate row order and labels, radio selection, Ready line | `fichero/Tests/Unit/general/Models/RecipeDesignerTests.swift` (to write) |
| Availability (Swift) | y | How do you want to work? and Teaching pages reachable in order; Compare and Choose a model… on every model step | `fichero/Tests/Unit/general/Views/Onboarding/SetupStagePageTests.swift` (to write) |
| Backend (pytest) | y | path presets write the existing answers; one rank rule with the tie-breaker; coverage filter and refusal; benchmark table load with provenance and insertion rate; auto-compare trigger and cap; summary (best/cheapest/fastest/most predictable, predictions); review pass shape and gain; one Kraken pass and lines per block; imported truth readiness; glyph inventory and display check; teach offer, switch and costs; a person's workflow fits or does not fit a job; recipe export holds no key, path or page and imports with its faults named | `fichero-server/tests/unit/recipes/test_recipe_designer_*.py` (to write) |
| MCP | y | `fichero_recipes_*` and the bake-off tools drive the benchmark run | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | the benchmark script runs through the CLI, never by hand | `fichero-cli/tests/test_recipes_*.py` (to write) |
| Click-around (XCUITest, Mac) | y | choose a path → open a stage page → compare runs by itself → Use This One → Ready names it | `fichero/Tests/UI/Onboarding/RecipeDesignerUITests.swift` (to write) |
| iPhone (iOS) | n | Set Up is a Mac surface today | — |
| iPad | n | — | — |
| Load (#4634) | y | an auto-compare never exceeds its cap or 3 pages; a benchmark run is bounded per family | `fichero-server/tests/perf/test_auto_compare_bounded.py` (to write) |

Hard-gate: the cross-surface invariant (stage page, finder, Compare, Ready and the MCP tools answer
from one candidate list and one rank rule) + capability availability (Choose a model… and Compare on
every model step; the path and teaching pages in the flow).

## Documentation matrix (paste from `../DOC-TEMPLATE.md`, tick the audiences this reaches)

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | `docs/user_manual/guide/` "Designing your recipe" with the six sections named under Manual (TBD) |
| Contributor | developer docs | y | `docs/contributor_manual/architecture/` recipes + this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/**` (`fichero_recipes_*`, bake-off tools: the rank rule, the cap, the measures) |
| Scripter | CLI `--help` | y | `fichero-cli/**` (benchmark run, compare, use-candidate) |
| Reference | capability/endpoint reference | y | generated (`check_capability_reference_current`) |

The path and teaching explanations above are the facts the maintainer's manual documents; the spec
holds the on-screen wording, the manual the longer "Learn more" text.

## Preview harness (fast visual verification + doc screenshots)

`RecipeDesignerPreview` (`#if DEBUG`) renders from recorded data, no engine: the four path cards with
their estimates; the teaching page; a stage page with a ranked list (measured row, benchmark row,
coverage-refused row under Other, predictability words on each); the compare in its three modes
(counts, lines on the page, text beside the page with Best · Cheapest · Fastest · Most predictable);
the Teach a model… offer; a Ready line with Change…. It is the source of the manual's screenshots
(`docs/assets/recipe-designer/`).

## Accessibility identifiers (required for the click-around leg)

- `designer.path.card.<a|b|c|d>` · `designer.path.learn-more.<a|b|c|d>` · `designer.path.matters.<speed|cost|quality|predictability|cluster>`
- `designer.teach.whether` · `designer.teach.when` · `designer.teach.where` · `designer.teach.learn-more`
- `designer.stage.<stage>.candidates` · `designer.candidate.row.<id>` · `designer.candidate.radio.<id>` · `designer.candidate.reason.<id>`
- `designer.finder.open` · `designer.finder.search-again`
- `designer.compare.again` · `designer.compare.column.<id>` · `designer.compare.use.<id>` · `designer.compare.badge.<best|cheapest|fastest|predictable>` · `designer.compare.prediction`
- `designer.review.kind` · `designer.review.level` · `designer.review.instructions`
- `designer.layout.region-model`
- `designer.teach.offer` · `designer.teach.candidate.<distil|fine-tune>`
- `designer.ready.step.<job>` · `designer.ready.change.<job>` · `designer.ready.totals`
- `designer.material.imported-truth` · `designer.material.script-display`
- `designer.step.open-in-editor.<job>` · `designer.step.adjust-in-editor.<job>` · `designer.candidate.own-workflow.<id>`
- `designer.share.export` · `designer.share.import` · `designer.share.start-from-recipe`

## UX completeness (required on EVERY surface)

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `designer.path.card.<x>` | the path's title | Choose how this project works; every default can be changed later | `designer.path.card.<x>` | [MISSING] |
| `designer.path.matters.<x>` | What matters most | Breaks ties between models that read equally well | `designer.path.matters` | [MISSING] |
| `designer.teach.whether` | Teach a model as you go | Train a smaller model on your checked lines; offered, never started by itself | `designer.teach.whether` | [MISSING] |
| `designer.finder.open` | Choose a model… | Lists every model that can do this step, best first | `designer.finder.open` | [MISSING] |
| `designer.candidate.radio.<id>` | Use this model | Chosen for this step | `designer.candidate.use` | [MISSING] |
| `designer.compare.again` | Compare again… | Runs the candidates on your sample pages; the cost is shown first | `designer.compare.again` | [MISSING] |
| `designer.compare.use.<id>` | Use This One | Makes this the step's model | `designer.compare.use` | [MISSING] |
| `designer.review.kind` | Review kind | What the reviewer looks for on each line | `designer.review.kind` | [MISSING] |
| `designer.layout.region-model` | Blocks found by | Which model finds the blocks on each page | `designer.layout.region-model` | [MISSING] |
| `designer.ready.change.<job>` | Change… | Choose another model for this step | `designer.ready.change` | [MISSING] |
| `designer.material.imported-truth` | Use as the measure | Your imported transcriptions become the reference every comparison is measured against | `designer.material.imported-truth` | [MISSING] |

All strings through the String Catalog; no `Text(verbatim:)`. Presence scans are not behavioural tests;
every row is [MISSING] until a spec-pinned test or `performAccessibilityAudit()` covers it.

## Build order (smallest valuable slice first)

1. One Kraken pass and lines per block (engine, #6014).
2. Imported transcriptions are the measure; then the glyph inventory and the display check.
3. Benchmark harness and the first four rows (Old French, Medieval Spanish, NZZ Fraktur, Arabic
   Maghrebi) with the insertion rate, about US$5.
4. Rank by the table; reasons and predictability in words; frontier order as fallback.
5. Coverage as a filter and the refusal.
6. The path page and the teaching page (they write existing answers; no new engine state beyond the
   path id, the tie-breaker and the teaching defaults).
7. Auto-compare on open, capped, with the four labels and predictions; then text beside the page.
8. Review stage; then its rows in the table.
9. Teach a model… offer, measurement, switch, costs; the run's offers and the recorded switch.
10. Ready as one line per step with Change…; predicted-then-measured totals.
11. Region-model row, segmenter search, layout rows; the one-page layout stage if ruled.
12. The workflow line on each stage page, Open in the editor, a person's workflow as a candidate,
    Adjust in the editor.
13. Share Recipe… and Use a Recipe…; the built-in recipes and Start from a recipe; the recipe search (catalogue first, then the topic convention); then publish and follow.
14. Fill the rest of the table; refresh one family at a time per model release.

## Open questions for the creative director

1. One page "Find the layout" or the two pages as today (`designer.layout.one-stage-proposal`).
2. The auto-compare caps: US$0.50 a stage and US$2 a project, or a share of the project cloud cap.
3. The teaching thresholds: 500 checked lines for a Kraken fine-tune, 200 pages' lines for a LoRA.
4. The predictability numbers: insertion rate alone as the headline, or the three together; and the
   dictionary-word rule for "changed beyond the CER" (needs a word list per language; none for Latin
   abbreviations).
5. Whether a NonCommercial Test Corpus set may feed a vendored table in a public repository (numbers
   only, never images or text); if not, those rows are measured locally and never shipped.
6. The default review kind per kind of project (palaeographer before 1800, proof-reader for print with
   an edition, none for typescript).
7. The on-screen wording of the four paths and the teaching page: approve, or edit here before the
   String Catalog takes it.
8. The retired ids of the first draft (change 7): confirm no test or issue cites them.
9. The `fichero-recipes` catalogue repository: create it under which GitHub account or organisation
   (the owner's own, or a Fichero organisation), and who checks submissions; until it exists the recipe
   search has only the topic convention and the built-in recipes.
10. The first built-in recipes: confirm the five kinds (medieval Latin manuscript, early modern Spanish
    notarial register, 19th-century English logbook, Fraktur newspaper, Arabic manuscript) or name others.
