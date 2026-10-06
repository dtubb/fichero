# Source Model — Models, recipes, projects and setup — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Setting up a project" section: the purpose question and what each purpose
> runs by itself; what setup asks and what it works out; the recipe it makes, and how to see
> and change it in the Inspector; checking models on your own corrected pages; taking,
> following, updating and publishing a recipe; finding a better model; how to see how any
> reading was made.
> Facts for the maintainer to write it from (no user-manual page yet): `docs/contributor_manual/manual-facts/2026-10-05.md`, section 1.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Every behaviour below carries its state tag and its issue; everything under "The design"
> is unbuilt design. Reorganised on 2026-10-01 into one design (it had grown by accretion); no
> behaviour id was removed or renamed.
>
> **See also, and do not duplicate.** Neighbouring specs own neighbouring ground. This slice
> builds on them and restates none of them:
> `ai/ai-settings.md` (ratified: provider rows as peers, downloads inside each row, ONE
> catalogue; its `settings.one-catalog-unification` is the catalogue whose *contents* this slice
> describes); `ai/ai-settings.md` (section K) (where keys live); `ai/ai-settings.md` (section M)
> (pickers list configured models and role defaults from one list builder); `ui/workflows.md`
> and `ui/workflow-node-config.md` (a workflow is a saved graph of tool nodes; the workflow bar;
> the locked default workflows); `ui/activity-and-automatic-work.md` (the one job model that
> **runs** a recipe, #5352); `compute/remote-compute.md`, `compute/jobs-and-fine-tuning.md` and
> `compute/distillation.md` (where work runs; training; teaching a small model from a big one);
> `source/formats-and-training.md` (ground truth, measuring, training sets);
> `source/synced-folder.md` (a folder kept in step with a project); `source/iiif.md`;
> `export/exporter.md`. Where this slice needs one of them to change, that is listed under
> "Requests to other specs", not done here.

## The golden path (north star, ruled 2026-10-04)

The Mosquera goal is a recipe that anyone can run through the app, not a model made by hand. This is
that path, end to end, as one behaviour. Each step names its card, its screen, its engine route, its
Activity rows and its state. A step marked ✱ is one that Sergio's project does today by API or CLI,
so it is a gap in the app, whatever the engine has. Each step also names the MCP tool that drives it:
all Fichero work, by a person or an agent, goes through the app or its MCP tools and API, and a
missing tool is written (spec, test, code) before the step is done another way (ruled 2026-10-04).

Mosquera is practice. The target the path is built for is an archive of about 80,000 images with
many scripts and hands and many damaged pages; the scale behaviours below the table say what that
asks of every step. Two rulings of 2026-10-04 are being written up in Sergio's specs and are only
cited here: Mosquera is not split, and whether a volume is split or read by page regions is an open
question (leaning to regions); and an import has no rank of its own (`source/source-model.md`, the
readings).

- `recipe.distil.golden-path` — **[PARTIAL]** (#4951, #5440, #5441, #5442) a person runs the distil
  recipe from setup to publish without leaving the app. The steps: setup (what you have, what you
  want) → split → Kraken lines → a teacher reads a sample → check (Fable or a person) → a clean set →
  train small models (choosing where, with time, cost and greenhouse gas) → evaluate against
  out-of-the-box small OCR models → choose → read the archive (this Mac, Hugging Face or ACENET) →
  names and statements → check → publish. Every step is a job with its rows in Activity
  (`activity.jobs-are-a-tree`), and every figure says whether it is measured, an estimate or unknown.
  Built: one Start runs split, lines, read, check, names, statements, export and publish as one
  `run-a-recipe` job (`recipes/runner.py`). Not built: a sample scope, the clean-set, training,
  evaluation and choose steps as recipe steps, reading away from this Mac, and screens for the ✱
  steps. *Test:* a named-machine journey (`source.onboard.*` journeys, section 14) on a small Mosquera
  volume, with the engine half driven through the public routes in automation.

| # | Step | Card | Screen | Engine route | MCP tool | Activity rows | State |
|---|---|---|---|---|---|---|---|
| 1 | Setup: what you have, what you want | project setup, purpose | first-run recipe screens (`FirstRunWindow+Recipe`, `RecipeSetupFields`) | `GET`/`PUT /api/recipes/project`, `/purposes`, `/languages`, `/scripts`, `/derived`, `POST /api/recipes/assemble` | missing (#5455) | none (no job) | PARTIAL (#4951; `source.onboard.five-questions`) |
| 2 ✱ | Choose a route: cloud, this Mac or distil, with time, cost, GHG for the whole archive | the routes | none | `GET /api/recipes/routes` (no app caller) | missing (#5455) | none | GAP in the app (#4951, #5404; `source.onboard.routes-for-the-volume`); GHG #5420 |
| 3 | Split, or page regions | `split-pages`, or regions | Start (`RecipeStepsView`) | `POST /api/recipes/project/start` | `fichero_workflow_run` (a step, not the recipe) | `run-a-recipe` → step → workflow run → pages | OPEN QUESTION: Mosquera is not split and its recipe drops the step; split against page regions is open (Sergio's spec, leaning to regions; #4951) |
| 4 | Kraken lines | `find-lines` | Start | the same | `fichero_workflow_run` | pages on the local-model lane | PARTIAL (Kraken provisioned automatically) |
| 5 ✱ | A teacher reads a sample | `read-a-line` / `read-a-page`, sample scope | none | none: Start reads every page | missing: a sample scope (#5455) | none | GAP (`source.onboard.samples-first`, `distill.collect.sample-covers-scope`, #5337) |
| 6 ✱ | Check, by Fable or a person | `check` | no start or results screen | `POST /api/check/runs` (`check: line-against-page` for the teacher-line check) | `fichero_check_run`, `_status`, `_verdicts` | a `check` job; the teacher-line check a `check-lines` job | PARTIAL (#5404, #5446; `source.check.run-is-a-job`, `source.lines.reading-checked-against-the-page`) |
| 7 ✱ | A clean set | training set | none | `GET /api/training/set` (counts; the training job builds the same set) | `fichero_training_preview_set` | none | PARTIAL: null, empty and rejected lines left out and counted, the teacher-line check's flags among the rejected (`compute.tune.set-excludes-flagged-lines`); the person-checked split missing (#4947, #5446; `source.train.human-checked-by-default`, `recipe.distil.damaged-text-stays-out-of-training`) |
| 8 ✱ | Train small models, choosing where | `train-a-model`, base from the catalogue | the start sheet (`compute.tune.start-sheet`), not built | `POST /api/training/kraken`, `/vision-lora`, `/reasons` (Hugging Face); Rorqual not yet | `fichero_train_kraken`, `fichero_train_vision_lora`, `fichero_training_status`, `_cancel`, `fichero_gather_reasons` | `train-a-model`, `convert-a-model`, `gather-reasons` | engine PARTIAL, app GAP (#5440, #5119, #5240); base Qwen3-VL-4B (#5442); nothing trains on this Mac by default |
| 9 ✱ | Evaluate against out-of-the-box small OCR models, per script and hand | the evaluation job | none | `POST /api/evaluation/runs`, `GET /api/evaluation/runs/{id}`, `GET /api/evaluation/scores` (this Mac's models; no remote target yet) | `fichero_evaluation_start`, `fichero_evaluation_status`, `fichero_evaluation_model_scores` | one `evaluate-models` job on the local model lane; its scores by model and page in its result, not yet as child rows | engine PARTIAL, app GAP (#5441, #5439; `distill.eval.job`); per script and hand not built |
| 10 ✱ | Choose | the recipe's pin | none | none | missing (#5455, #5429) | none | GAP (`compute.tune.not-default-until-chosen` #5240; pinning #5429) |
| 11 | Read the archive | the chosen reader | Start | Start, on this Mac; Hugging Face Jobs by shard; ✱ no route for Rorqual | `fichero_read_at_scale` (Hugging Face), `fichero_reading_status`; Rorqual missing (#5457, #5454) | pages on the lanes; shards as rows | this Mac PARTIAL; Hugging Face PARTIAL; Rorqual GAP (#5457, #5238) |
| 12 | Names and statements | `find-names-tag-words`, `find-statements` | Start | Start | `fichero_workflow_run` | workflow runs | PARTIAL (`source.job.find-statements`) |
| 13 | Check | `check` | as step 6 | as step 6 | as step 6 | as step 6 | PARTIAL (#5404) |
| 14 | Publish | `publish` | Start | Start (an 11ty site); ✱ a Hugging Face dataset or model: no screen | missing for the Hub (#5455) | the recipe's step | site PARTIAL (`source.job.publish`); Hub GAP (`compute.publish.*`). Sergio's data: train yes, release no |

At the scale of the real archive (about 80,000 images, many scripts and hands, many damaged pages),
ruled 2026-10-04:

- `recipe.distil.script-and-hand-routed-per-region` — **[GAP]** (#5456) script and hand are detected
  per page and per region, not set once per project, and each region goes to the reader (later the
  trained model) that suits its script and hand. The detection is a job with its rows; it says how
  sure it is, and a person's correction of it is kept.
- `recipe.distil.damaged-text-stays-out-of-training` — **[GAP]** (#4947, #5446) text a person, Fable or
  the teacher-line check marks as damaged, uncertain or illegible is kept out of every training set
  and every held-out set; the set's manifest counts what was left out and why.
- `recipe.distil.teacher-samples-small-models-read-the-bulk` — **[GAP]** (#5337, #5457) the teacher
  reads only a sample, drawn across the scripts and hands found; the small models read the bulk.
  Reading the bulk on the maintainer's cluster, Rorqual, is the scale route: Fichero stages the
  image and the model, submits by shard, watches the shards as rows, fetches and lands the results,
  and cleans up (`compute/targets-and-connection.md`).
- `recipe.distil.whole-archive-estimate-first` — **[GAP]** (#5440, #4951) before anything starts, the
  start sheet's estimate covers the whole archive (every image, every step, on the route chosen):
  time, cost and greenhouse gas, each measured, an estimate or unknown.
- `recipe.distil.every-step-has-an-mcp-tool` — **[PARTIAL]** (#5455, #5454, #5441, #5446) every step
  in the table has an MCP tool that drives it, named in its row, so an agent drives Fichero as a
  person does through the screens and never drives Kraken, ketos or the engine's insides directly.
  Built: the tools named in the table. Missing: those marked missing.

## Intent

The source model makes a page rich. This slice is about how that richness gets *made*, with the
least effort and the most honesty: which model does which job, how jobs chain into a recipe,
how a project says what it is for so Fichero can set itself up, and how recipes are shared so
the next project on the same material starts from the best measured one.

Setup is **opinionated**. The first question is what the person is trying to do. On the common
paths Fichero then just does it: it picks the models by rule, measures them on the person's own
corrected pages, and runs the work by itself as material arrives. On unusual paths it does not
pretend to know; it offers the tools. Historical Spanish hands, the material of the app's two
heaviest users, get a **flagship recipe** tuned and measured end to end. Any other language and
script (Cherokee in its syllabary, say) goes through **the same flow**, which finds what models
exist, says plainly where none does, and leads into training one.

## The words (one meaning each)

These terms are used in this slice and nowhere with another meaning. They refine the glossary in
`source-model.md` ("The words"); where that table is shorter, this one is the detail.

| Word | Means |
|---|---|
| **project** | what the app still calls a library: one research undertaking with its own file and settings |
| **purpose** | the answer to setup's first question: what the person is trying to do (one of a fixed list, below). It decides which **layers** run by themselves. Stored on the project |
| **layer** | a family of work that a purpose switches on or off at import: lines and regions, reading, entities, search vectors, knowledge graph (plus `prepare` and `output`, which follow the others) |
| **job** | one kind of work, registered by name with what it **takes** and **gives** ("find lines", "read a line"). The registry is open |
| **model card** | the one description Fichero keeps of a model: what it does, what it suits, how it runs, how far to trust it |
| **workflow** | a saved graph of tools, as `ui/workflows.md` defines it. What runs is always a workflow |
| **chain** | jobs in order. A chain is a workflow; there is no second kind of thing |
| **recipe** | how a project's material is processed: its steps in order, and for each step the job, where it applies, the model, the settings, the prompt and where it runs; plus its **defaults** (below). It refers to workflows by name and may carry its own. It is data, never code |
| **step** | one entry in a recipe: one job, one layer, one model (or none yet), its settings and prompt, where it runs |
| **profile** | the **defaults** section of a recipe: what a project *is* (languages, scripts, period, direction, guideline, level of normalisation, record rule, fonts, metadata fields, views that open first). Stored as a prototype the project inherits from. There is no separate profile file |
| **project defaults** | the values setup writes at the project rung of the cascade, from the answers and the recipe's profile |
| **flagship recipe** | the recipe for historical Spanish hands, shipped with Fichero, measured end to end on real pages of that material |
| **generated recipe** | a recipe assembled by rules at setup, for material no shipped or published recipe fits |
| **follow / override / fork** | a project **follows** a published recipe at a version; its own changes are **overrides** on top; a **fork** makes the recipe the project's own, no longer following |
| **bake-off** | candidates for a step read the person's corrected pages and are ranked by error |
| **ground truth** | pages, or lines, a person has fully corrected, trusted to test or teach a model (`formats-and-training.md`) |
| **compute target** | a place work can run besides this Mac: a cluster, a Linux machine, a GPU service (`compute/remote-compute.md`) |

How they relate: **setup** asks the purpose and a few facts; from them and the model cards it
**assembles a recipe by rule** (or takes a published one that fits); the recipe's **profile**
becomes the project defaults; the purpose picks which of the recipe's **steps** run by themselves;
each step's **job** declares what it takes and gives, which lets the recipe be checked before it
runs and lets the activity system remake exactly what a correction touched.

## What exists today (read on disk 2026-09-19 by a code worker; to be re-read before tagging)

- **Models are described in several shapes, partly unified already.** The four local runtimes
  (MLX, spaCy, Kraken, Whisper) are folded into one catalogue entry and one download path
  (`llm/local_model_catalog.py`, `/api/local-inference/catalog`). Still separate: providers
  (`llm/providers.py`); cloud model prices and abilities from a vendored list
  (`llm/model_types.py`); a separate list of embedding models (`llm/local_models.py`); and named
  model profiles in the app database (`llm/model_profiles.py`; a local-runtime configuration,
  not a project profile). None says what a model **takes in and gives out**; the nearest thing
  is a free list of words such as "segmentation" or "recognition".
- **Two families of engine routes** (one for MLX, one for spaCy, Kraken and Whisper) carry
  through into two families of MCP tools. **The command line already has about twenty-five
  model commands**, because it is generated from the OpenAPI contract. Anything this slice adds
  as a route reaches the command line for nothing.
- **A model recommender and a language-fit score exist** (`llm/model_recommendations.py`,
  `llm/language_coverage.py`, `llm/script_coverage.py`). The score is LOOVE-style **tokenizer
  coverage**: a script's exemplar characters are sorted into four tiers (a token of their own,
  reachable only by merges, byte fallback, unreachable), with a coverage score and token
  fertility, worked out offline from the model's tokenizer files only. With no tokenizer it says
  "unknown"; it says of itself that it measures coverage, not the quality of the model's work.
- **Tesseract is read, not run.** Its TSV output and box files are parsed
  (`media/ocr_geometry.py` `parse_tesseract_tsv`, the `tesseract_box` format), but no Tesseract
  runtime ships and it is not a provider.
- **A second chaining mechanism ships** beside workflows: chains of workflows with conditions
  and their own routes (`execution/chaining.py`, `api/routes/workflow/chains.py`).
- **One place already refuses cloud use for privacy** (`enforce_model_profile_privacy`).
- **Role defaults** (`$small`, `$large`, vision tiers) are app-wide. A workflow node can store
  an alias, resolved when it runs. There is no default at the level of a project, a folder or
  a document.
- **Kraken's reading models are a hard-coded shortlist of two**, fetched from Zenodo by DOI and
  marked in the code as provisional. There is no browsing of Kraken's repository or of
  Hugging Face.
- **Chains.** Workflow tools declare typed ports, and about fifty locked default workflows ship
  (`workflows/default_workflows.py`). The paleography ones are a single transcribe step with a
  tuned prompt, not real chains. "Find the lines with one engine, read them with another"
  exists **four separate ways** with no shared part. VERIFIED on disk, 2026-09-19:
  (1) `llm/kraken_runtime.py` `recognize_lines` / `recognize_to_geometry`: Kraken segments
  (`blla.segment`) and reads (`rpred.rpred`) in one script; (2)
  `workflows/tools/economy_htr.py`, tool `economy_htr`: `crop_line_strips` cuts line pictures,
  then `trocr_transcribe_lines` or `kraken_transcribe_page` reads them, inside one function;
  (3) `workflows/tools/align_transcript.py`, tool `align_transcript`: puts a transcript's lines
  on Kraken's baselines only when the line counts match, and writes nothing otherwise
  (`media/transcript_alignment.py`); (4) `workflows/tools/merge_geometry.py`, tool
  `merge_geometry`: lays a reviewed transcript over measured word boxes, records for every word
  whether its box was measured or worked out, and refuses a page whose line structure cannot be
  trusted (`media/geometry_merge.py`). **Kraken's baselines cropped and handed to Apple Vision
  or a local vision model does not exist**, though every piece it needs does.
- **How a result was made** is partly recorded: an artifact names its provider, model, run,
  step and the artifact it came from. It is not shown as a chain anywhere.
- **A prototype system exists** (`models/node_prototypes.py`, `models/prototype_schema.py`): a
  node can name a prototype; prototypes inherit from a parent and carry attributes that a node
  of that prototype takes on, in the manner of Tinderbox. It is used for kinds of document
  today. It is the natural base for a recipe's profile and for overrides.
- **Fichero's own licence is the GNU Affero GPL, version 3** (`LICENSE` at the root).
- **No project settings.** Nothing between the app and a document carries settings. First-run
  onboarding (`fichero/fichero/Views/Onboarding/FirstRunWindow.swift`) makes a library and asks
  about permissions and AI providers; it asks nothing about purpose, languages, scripts or
  period.
- **Folder watching exists** for automation triggers (`workflows/file_watcher.py`, on
  `watchdog`), the base the synced folder's intake grows from.
- **Apple Vision** runs in the engine, takes a language from a supported list, and returns line
  and word boxes.
- **Two Readers exist**: a native one, and an engine-made HTML page that declares itself
  English. Neither handles direction, script or vertical writing.
- **Embeddings** use one multilingual model for everything; the alternative is chosen by an
  environment variable, not in Settings.
- **spaCy** knows five languages. For any other it used to fall back to English without
  saying so; fixed on 2026-09-19 (`7c04953cf`, #4914): it now declines, by name.

## What the field does (survey, 2026-09-19; sources at the end)

- **Kraken's model repository** (the `ocr_models` community on Zenodo, read through the
  HTRMoPo project that `kraken list` uses) publishes a machine-readable model card: task,
  script, language, characters covered, accuracy, licence, authors, a DOI for the version and
  one for the family. It covers segmentation, reading, reading order and correction.
- **HTR-United** catalogues *training sets*, not models: one YAML description per set, in a
  GitHub repository, checked against a schema by continuous integration on every submission.
- **Hugging Face** hosts most other models. A model card is a README with a YAML header
  (licence, languages, task, datasets, evaluation results). Period and script appear only in
  free text, so Fichero must read the page to find "seventeenth-century Spanish". Teklia
  publishes permissively licensed PyLaia readers there; the CATMuS sets are there.
- **Transkribus** has hundreds of public models, usable only inside Transkribus.
- **OCR-D** describes every tool in one machine-readable file with typed inputs, outputs and
  parameters: the closest prior art to describing jobs one way.
- **Arkindex** signs every result with the run that made it, from which the tool version, its
  settings and the model version can be recovered: the closest prior art to "how was this made".
- **Onboarding elsewhere is tiny.** eScriptorium insists on two things: reading direction and
  where the line sits (on the baseline, or hanging from a top line as in Hebrew). Transkribus
  asks nothing until a job is run.
- **Vision-language models** now beat older recognisers on modern hands and do well on
  historical print; a small open model trained on historical text (CHURRO) beats much larger
  ones. But they invent plausible readings and quietly modernise spelling, which a faithful
  transcription must not do. No fair comparison of reading each cut-out line against reading
  the whole page was found: Fichero measures that on its own sources (the bake-off).
- **Licences.** The YOLO family (Ultralytics, DocLayout-YOLO, YALTAi) is under the AGPL, and
  its publisher holds that this covers trained weights. Fichero is itself AGPL, so these are
  compatible, with one caution not yet checked with anyone qualified: the Mac App Store build.
  So such models are **downloaded on request, not bundled**. Surya's weights carry a revenue
  cap. One well-known embedding model (jina-embeddings-v3) is non-commercial; the two Fichero
  uses or offers (multilingual-e5, BGE-M3) are permissive.
- **Apple's frameworks cover none of the hard cases** (early-modern hands, Syriac, woodblock
  Chinese, Indigenous orthographies). Their language lists must be asked for at run time.

### Prior art for the recipe format (2026-10-01)

There is no standard for "an HTR recipe". Fichero uses standards for the wrapper and its own
published schema for the inside:

- **RO-Crate, and its Workflow RO-Crate profile**, is a JSON-LD metadata file
  (`ro-crate-metadata.json`) that describes a folder of files, their authors, licence and
  provenance. WorkflowHub accepts workflows packaged this way, and Zenodo takes any deposit and
  gives it a DOI. **Adopted** as the wrapper, so a recipe can be deposited and cited. A Fichero
  recipe would be a workflow type WorkflowHub does not yet know; registering it there is
  optional.
- **CWL** (Common Workflow Language) describes command-line tools and workflows in YAML, with
  typed inputs and outputs, and runs them in containers. **Not adopted** for the inside: a CWL
  step runs an arbitrary command, and a recipe must never run code (`source.recipe.data-not-code`);
  Fichero's steps are its own registered jobs, not programs. CWL's typed inputs and outputs are
  the model for a job's declared *takes* and *gives*.
- **HTR-United** is the precedent for the **catalogue**: one folder per entry in a public
  GitHub repository, a published schema, and automatic checks on every submission.
- **Hugging Face model cards and Kraken's HTRMoPo cards** are what a recipe **points at**: a
  step pins a model by Hugging Face repository and revision, or by Zenodo DOI, and Fichero reads
  the card behind the pin. HTRMoPo cards carry the model type, script (ISO 15924), language,
  metrics including CER, licence and creators, but no period (2026-10-01 search).
- **OCR-D** and **Arkindex**, above, are the precedents for typed tool descriptions and for
  recording the run behind every result.

## The design (proposed)

### 1. One card for every model

Every model Fichero can use has one **model card**, in one shape, whatever it is: a cloud
vision-language model, a local one, Apple Vision, a Kraken segmenter or reader, a Tesseract
language model, a layout detector, a spaCy or Stanza pipeline, an embedding model, a speech
recogniser.

**Tesseract becomes a provider** (2026-10-01), a peer of the others in the AI settings. Its
binary is built into the app at build time (a sandboxed app cannot run code it downloads); its
per-language data files (`traineddata`) are downloaded on demand as data, each with a card of its
own. It is fast, local, Apache-licensed and covers many scripts in print and typescript, so it is
the **local baseline in every bake-off for print and typescript**, and it can read cut lines
handed to it by another finder (its single-line mode).

The cards are the **contents of the one catalogue** the AI settings spec already calls for.
They are what the shared picker lists and what a role default resolves to. A card says:

- **What it is**: name, version, who made it, where it came from (a DOI, a Hugging Face
  repository and revision, a provider and model id), how to cite it.
- **What it does**: one or more **jobs** from the registry.
- **What it suits**: scripts (ISO 15924), languages (BCP 47, with a Glottolog code where there
  is one), a period (from year, to year), print or hand or typescript, reading direction, where
  the line sits, the characters it knows.
- **How it runs**: on this machine, in the cloud, or on a compute target; the engine it needs;
  its size; the memory it needs; whether this Mac can run it; its **speed** (pages or lines per
  hour, measured on this Mac where it has run, otherwise published and marked an estimate); its
  **price** per page for a cloud model (from the vendored price list); and an **energy estimate**
  per page, marked as an estimate (below).
- **Whether it can be trained**: yes, and how (Kraken by `ketos`, LoRA on a small open
  vision-language model, Tesseract's own training), or no (a closed hosted model).
- **How far to trust it**: its licence and **licence class** (open, non-commercial, gated,
  special terms); its published accuracy, on what data; what it was trained on; its known
  limits; its **coverage** of the project's script (below); and **this project's own
  measurements** of it against ground truth.
- **Where else it is**: the compute targets it is present on, and the training job that made it,
  if any (asked for by `compute/remote-compute.md`).

**Coverage, two ways.** For a model that reads through a tokenizer (a language or
vision-language model), coverage is the LOOVE tier score that exists today. For a model that
reads through a fixed character set (Kraken's codec, Tesseract's character set), coverage is the
share of the script's exemplar characters in that set. Neither says how well the model reads;
both say when it cannot (a reader whose set lacks half the syllabary is excluded, not ranked).

**Energy is an estimate, and says so.** Local: the measured time per page times a typical power
draw for this Mac's chip class. A compute target: GPU hours times the card's rated power times
the site's published overhead, where known. Cloud: a published per-request figure where the
provider gives one, otherwise "unknown". Shown in grams of CO2 per thousand pages using the
grid figure for the place it runs, where one is known, always labelled "estimate".

The same card is what the app shows, what MCP returns and what the command line prints.

**Where a card's facts come from** (from the 2026-10-01 search). Script, language, task and
licence are usually structured at the source (HTRMoPo cards on Zenodo, Hugging Face tags), and
are read as they are. Accuracy is structured mainly in HTRMoPo cards, so Kraken's repository is
read through the `htrmopo` library, which parses each record's card, not through Zenodo's plain
search (which returns titles and descriptions only). **Period is structured nowhere** on model
cards: it comes from the HTR-United record of the card's named training set, where there is one
(HTR-United records carry typed dates), or a language model reads it from the card's prose and a
person confirms it. **Whether a reader reads lines or pages** is rarely stated: it is worked out
from the architecture (a CTC reader such as Kraken's reads lines; a vision-language model reads
pages unless its card says it reads lines), shown as "worked out from the architecture", and
correctable. Trainability is worked out from the runtime (Kraken, TrOCR, Tesseract and open
vision-language models can be trained; a closed hosted model cannot).

A fact proposed by a language model is marked unconfirmed until a person confirms it, and the
rules that assemble a recipe ignore unconfirmed facts.

### 2. Jobs: a registry of what goes in and what comes out

A job is registered by name with what it **takes**, what it **gives**, its **settings**, the
**layer** it belongs to, **how its outputs are compared** (section 8a), and a **plain
description with an example**: what it does, why a recipe would include it, and the trade-offs
between its usual options, in a researcher's words. That description is what setup, the
Inspector, the recipe's README and the user manual show, so a new job explains itself everywhere
with no extra writing. This is what makes chaining safe: a step can only follow a step
that gives what it needs. The registry is **open**: a new feature adds a job (or an export
format) by registering it, and from then on recipes can name it, setup can offer it, the
activity queue can run it and the recipe check knows where it may go, with no other change.
Each entry records the Fichero version that added it, so a recipe naming a job this copy lacks
can say which version has it.

**Reading jobs**

| Job | Takes | Gives | Layer |
|---|---|---|---|
| prepare the image | a page image | a new rendition (cropped, deskewed, rotated, dewarped, adjusted); the original untouched | prepare |
| split pages | a scan or PDF page holding two pages, or a strip of frames | page segments, each a page of its own, in order | prepare |
| find regions | a page image | a pass of regions, with kinds | lines |
| find lines | a page image (and regions, if any) | a pass of lines with baselines and polygons | lines |
| put in order | a pass | a named reading order | lines |
| refine shapes | a page image + a pass | a new pass with the same segments' shapes adjusted (a detector tightening a vision model's rough boxes) | lines |
| find signs | a page or line image | sign segments, for scripts read sign by sign (cuneiform, hieroglyphs, Linear B, undeciphered scripts) | lines |
| propose a shape | a page image + a click | one shape | lines |
| find a table's cells | a table segment's picture (and its lines) | cell segments with rows, columns, spans and headers | lines |
| read a line | a line's picture | a reading of that line | reading |
| read a page | a page image | a reading of the page, with or without shapes | reading |
| tie text to lines | a reading of the page + a pass of lines | readings on those lines | reading |
| correct | a reading + the picture it was read from | a new reading that names the first | reading |
| trace a drawing | a segment's picture | a drawing (SVG) as a reading of that segment | reading |
| identify signs | sign segments + a sign list | proposed identifications with certainty, for a person to confirm (`undeciphered-scripts.md`, `languages-scripts-signs.md`) | reading |
| describe / classify a picture | a segment's picture | a description, or classes | reading |
| translate / transliterate / normalise | a reading | a reading | reading |
| transcribe speech | a stretch of a recording | a reading, with timings | reading |
| find names; tag words | a reading, of the lines or of the whole page | mentions on stretches of it; word-level analysis | entities |
| make a vector | a reading, or a picture | a vector | vectors |
| find statements | readings, of the lines or of the whole page (with their mentions) | claims: subject, relation, object, each naming the stretch of text it came from | graph |
| describe for the catalogue | a page or document | proposed values for the project's metadata fields, for a person to confirm | catalogue |
| train a model | a training set of checked work | a model card for a new detector or reader, measured on held-out pages | train |
| find documents in a folder | the pages of a folder, in order | proposed groupings: which pages make one document (a letter of three pages in an archive bundle), for a person to confirm with Group | prepare |
| split into entries | a reading of a diary, register or ledger | entries (a dated diary entry, a register line), each a segment with its date | structure |
| extract to a table | documents and the project's metadata fields (from their prototype) | one row per document or entry (seller, buyer, the person sold, price, date, place, for a sale record), each value tied to the text it came from, exportable as a spreadsheet | structure |
| check | the proposals of one layer (readings, mentions, claims, links) + what they came from (readings of the lines or of the whole page) | for each proposal: confirmed, corrected (a new proposal naming the first) or rejected, with the checker's reasons, recorded at the checker's trust level (a person; a model checker such as Fable; never a person's level for a model) | the layer checked |
| pull out passages | readings and a question or theme | excerpts, each with its source and place, gathered into a note or a collection | knowledge |

"Read a page" is kept apart from "read a line" on purpose. Vision-language models mostly do the
first, and cannot be trusted to keep shapes; Kraken and its kin do the second.

**Knowledge and output jobs.** Each is defined in the spec that owns it; a recipe only names it.

| Job | Takes | Gives | Layer | Owned by |
|---|---|---|---|---|
| link to authorities | entities | proposed links to Wikidata, VIAF, GeoNames, Pleiades or a project's own authority, for a person to confirm | graph | `kg/kg-enrichment.md` |
| place in a gazetteer | place entities and mentions | coordinates and a gazetteer identifier, with the gazetteer named | places | `kg/kg-enrichment.md`, `maps-and-georeference.md` |
| enrich from linked data | linked entities | facts fetched from a SPARQL endpoint, as claims whose source is that endpoint, kept apart from what the pages say | graph | `kg/kg-enrichment.md` |
| work out dates | readings and mentions of dates | normalised dates (any calendar, as a day count) with the text they came from | graph | `historical-text-normalization.md` |
| attribute hands | segments and their pictures | proposed hand attributions with certainty | reading | `readings-and-apparatus.md` |
| export | a project, folder or selection (its readings, of the lines or of the whole page) | files in the formats the step names, all from the one export stream (PAGE, ALTO, TEI, hOCR, plain text, IIIF, Markdown, Word, PDF, Excel, CSV, Parquet, JSONL, RDF, a static Eleventy site, training sets), with provenance and, if asked, the recipe | output | `formats-and-training.md`, `export/exporter.md` |
| publish | a folder | a IIIF published folder, a static site, or RDF behind the SPARQL console | output | `iiif.md`, `explore/networks.md` |

SPARQL itself is a way of **asking** the knowledge graph, not a step that changes anything; a
recipe can only make sure the graph it queries is filled and published.

An export step can write to a **synced folder** that is kept current as the work changes, and
that can work both ways; that is specified in `synced-folder.md`.

### 3. One way to say "find here, read there"

A single general step replaces today's four special ones: **take the segments of a pass, cut
each one's picture (to its polygon, straightened on its baseline), hand each to any model that
can do the next job, and write what comes back as readings on those same segments.** Because it
works on any pass and any reader, **recipes mix runtimes step by step**: any finder can feed any
reader, and any reader any corrector. With it:

- Kraken finds the baselines; Tesseract reads each cut line in its single-line mode.
- Kraken finds the baselines; Apple Vision reads each line.
- A vision-language model proposes regions or lines; a YOLO detector (or Kraken) refines their
  shapes; a reader reads them.
- YOLO finds the regions, Kraken the lines in them; a small local vision-language model reads
  each line; a large one corrects only the lines read with low confidence.
- A person draws the lines by hand for a script no segmenter knows; any reader reads them.
- A layout detector finds the regions; each kind of region goes to a different reader (a table
  to one, a marginal gloss in another language to another).

So a recipe's choice is a **combination**, one model per step, and that is what is measured and
recorded (section 8).

`economy_htr`, `align_transcript`, `merge_geometry` and Kraken's own segment-and-read are
**retired into it**, keeping what they do well (refusing a page rather than guessing;
recording measured against worked-out boxes).

### 4. Chains are workflows, and every result says how it was made

A **chain** is a workflow. Today there is a second kind (`execution/chaining.py`), so this is a
migration: its conditions fold into the workflow graph and it is retired. What this slice adds:

- steps declare their job, so a chain is checked before it runs;
- a step's model is a **model card or a role default**, chosen with the one shared picker;
- a chain can be made of **jobs with no model named**, resolved against the project's recipe
  when it runs, so one chain can serve many projects;
- the **workflow bar** offers the project's recipe first, on whatever is selected, then the
  workflows the selection can feed;
- machine output arrives as a **new pass or new readings**, never over a person's work.

**How was this made.** Every pass and every reading carries its **making**: the run; the step;
the recipe and its version; the model card and its exact version; the settings and prompt used;
what it was given (which pass, which reading, which image rendition); and whether a person or a
machine made it, set by the engine. Because each reading names what it was made from, the chain
can be walked back. The **Inspector** shows it for the selected segment as a short readable
chain ("Lines found by Kraken (blla 5.2) → read by the CATMuS reader → corrected by Qwen (local)
→ corrected by you, 3 May"); the workflow bar and the Activity row show the same for a run; MCP
and the command line return the same answer. Two chains run on one page can be **compared** and
scored against ground truth.

### 5. A project, its settings and the cascade

**A project is what Fichero has called a library** (the rename is decided, not yet carried
through the app, and not this spec's to carry). It is one research undertaking with its own
file. What is new is that **a project has settings of its own**: its purpose, its recipe and its
defaults. Until now almost every such setting has been one value for the whole app.

Project settings sit **inside the cascade already ruled** for language and other attributes:

```
app  >  project  >  folder  >  source  >  page  >  region  >  line  >  word  >  character
```

Each level inherits from the one above unless it says otherwise, and every shown value says
where it came from. So a project of Spanish deeds can hold one folder of Nahuatl papers, or one
folder of maps, set on that folder, without becoming two projects. **A folder can follow a
different recipe** (a IIIF folder of Persian manuscripts, a folder of maps), and **a single step's
model can be overridden lower down** (one folder of Latin charters names a different reader)
without a second recipe. A project whose settings were never filled in behaves exactly as today.

A project's settings:

- **Its purpose** (below), and any layers added since.
- **Its recipe**: the published recipe it follows and the version, its overrides, and which
  compute target each "runs on a cluster" step is bound to; or a recipe of its own.
- **Its defaults** (the recipe's profile, as overridden): languages, scripts, period, direction,
  where the line sits, guideline and level of normalisation, fonts, metadata fields, the views
  that open first.
- **Its rules**: whether pages may leave this machine (`source.project.stays-local`); what counts
  as the record, strict or relaxed (a new project is strict); rights defaults
  (`rights-and-access.md`).
- **Its synced folders**, if any (`synced-folder.md`).

**One settings surface: the Inspector** (ruled 2026-10-01). Everything setup set is shown and
edited in the **Inspector when the library is selected**, with an easy way to add a language or a
layer. "Project Settings…" in the File menu and on the library's context menu selects the library
and opens that Inspector section; it is not a second window. A folder's own settings are edited in
the same Inspector when the folder is selected. (This settles the 2026-09-20 direction, which had
left open a separate project settings window: there is none.)

### 6. Purposes and the layers they turn on

Setup's first question is the purpose, in plain words. "AUTO" means the layer runs by itself on
material added to this project. "off" means it does not run by itself; it is still there to run
by hand or to add later. A purpose changes **what is offered first and what runs by itself,
never what can be reached** (ruled 2026-10-01: offer first, never hide). **Ruled 2026-10-05
(#5478): purposes are checkboxes, any combination, each a set of jobs; a project's layers are the
union of its ticked purposes'.** The purposes setup offers, and the jobs each proposes, are in
section 7b, screen 2; the table below is the layer view of the original eight.

| Purpose | Lines and regions | Reading | Entities | Search vectors | Knowledge graph | Kind |
|---|---|---|---|---|---|---|
| Just transcribe | AUTO | AUTO | off | off | off | just do it |
| People, places and things | AUTO | AUTO | AUTO | off | off | just do it |
| Search my sources | AUTO | AUTO | off | AUTO | off | just do it |
| The full knowledge graph | AUTO | AUTO | AUTO | AUTO | AUTO | just do it |
| Map places | AUTO | AUTO | AUTO (places) | AUTO | places | just do it |
| Edit a corpus | AUTO | AUTO | off | off | off | tools (apparatus, comparison) |
| Decipher a script | off (drawn or checked by hand) | off | off | off | off | tools (`undeciphered-scripts.md`) |
| Train my own model | as its base purpose | AUTO (the teacher) | as its base | as its base | as its base | tools (`compute/distillation.md`) |
| Not sure yet | off | off | off | off | off | everything on demand |

"Train my own model" asks for a **base purpose** (Just transcribe unless changed): it runs that
purpose's layers, with reading done by the best available teacher, and offers the distillation
tools first. The `prepare` layer runs whenever a later layer that needs it runs; the `output`
layer runs when the project has a synced folder or a published folder. `train` steps run by
themselves only if the person chose that in setup (`source.recipe.train-never-automatic`).

**This refines two rulings, it does not reverse them** (ruled 2026-10-01): the free NLP layer runs
automatically at import **in projects whose purpose uses entities**, not in every project; and
Kraken segments automatically at import in projects whose purpose includes lines. Neither gains a
toggle: the purpose decides. Adding a layer later (Inspector, "Add Layer…") turns on the recipe's
steps of that layer and runs them over everything already in the project, as one job.

### 7. Setup, screen by screen

**Superseded for the screens and their order by section 7b (ruled 2026-10-05, #5477 to
#5482).** The table below is the original proposal, kept for what each screen works out rather
than asks. What is fixed
is what the steps must collectively do: ask the purpose first, count or ask the volume, ask at
most five facts, show the recipe with its reasons and estimates, offer the bake-off, and run
nothing before Start.

Setup is a window with a form and search, not a conversation. It grows from today's first-run
window (`FirstRunWindow.swift`). It opens when a **new project** is made, and from **Set Up…** in
the library's Inspector for an existing one. It can be closed at any point: the answers so far are
kept as a draft on the project, and **nothing runs until Start**. "Set up later" makes a project
with no settings, which behaves as today.

| # | Screen | What it asks | What it works out and shows instead of asking |
|---|---|---|---|
| 1 | **What are you doing?** | the purpose (and, for "Train my own model", its base purpose) | — |
| 2 | **Your material** | a folder, files, a IIIF manifest or collection, recordings, or "later"; **how much**, only when it cannot be counted (under 100 pages; 100 to 5,000; 5,000 to 100,000; more); and, optionally, where corrected transcriptions are | the page count (counted from the folder, the PDFs' pages or the manifest); the sample pages: up to ten, spread across the material (first, last, evenly spaced, and the largest and smallest images), which the person can swap |
| 3 | **What it is** | at most five things, each pre-filled where it can be: **scripts**; **languages**; **print, handwriting or typescript, and roughly when**; **how complex the pages are** (one column; columns or tables; margins and glosses); **may pages leave this Mac** (asked here only if a step would use the cloud; see screen 4) | reading direction and where the line sits (from the script); the fonts the script needs (from the shipped fonts and the script); this Mac's chip, memory and free disk; which providers have keys; which compute targets exist |
| 4 | **How it will be done** | nothing, unless the person wants to change something | the recipe: a published one that fits, or one generated by rule; each step's model, where it runs, download size, licence class, published and local measurements, and why it was chosen; steps with no fitting model; total download size against free disk; the estimate for the whole volume |
| 5 | **Check on your pages** | which corrected pages to use, or "skip" | the bake-off: candidate combinations ranked on those pages |
| 6 | **Ready** | **Start** (the first yes for automatic work) | a summary: purpose, defaults, recipe, downloads, and what will run by itself on the material now, with the whole volume's estimate, and the main alternative's beside it ("about 1,200 pages: about 3 hours on this Mac, $0; or about 40 minutes in the cloud, about $18") |

**Setup teaches the method.** Every screen, and every step of the proposed recipe, explains itself
in plain words: what the step does, why it is in this recipe, what the options are and their
trade-offs (accuracy, cost, speed, carbon, trainability), with a small example drawn from the
person's own sample pages where there are some (the lines Kraken found on page 3; the names found
in one of its lines). The words come from the job registry's descriptions, so the same
explanation appears in setup, in the Inspector and in the recipe's README, and the user manual is
written from the same source.

**Pre-filled from the sample pages.** Where a local model is available to look, Fichero suggests
scripts, languages, material, period and layout from the samples, and labels each suggested value
"suggested from your pages" until the person accepts or changes it. With no local model available
the fields start empty and nothing is downloaded just to make a suggestion. Each field has search
(scripts by name or ISO 15924 code; languages by name, BCP 47 tag or Glottolog code; periods by
years or by a named period).

**Recordings, and languages with no script.** When the material is recordings, the scripts field
becomes **how to write it**: a practical orthography (a script and its conventions), IPA, or a
transcription system of the project's own. The reading step becomes "transcribe speech", and the
reading's script is the one chosen. The language itself may have no script (`Zxxx` in ISO 15924);
that is recorded, not treated as an error.

**Folders that differ.** Where the material's folders differ (print in one, handwriting in
another; a second language in one), screen 3's answers can be given per folder, and the rules
assemble a folder override for each step that differs, not a second recipe.

**Corrected transcriptions given at setup** come in through the one import path as person-made
passes marked as ground truth: PAGE, ALTO or TEI with their transcriptions, or plain text files
named after their images (page-level ground truth, with no lines). Pages already in an existing
library with person-made readings can be chosen instead. Without any, screen 5 offers to correct
two or three sample pages now, starting from the recommended reader's draft.

**An existing library** (the two historians already have one) runs the same setup from its
Inspector. Samples and ground truth come from its own pages. Start applies the recipe to material
added from then on; running it over the pages already there is offered as a separate choice with
its page count and estimate, and its output arrives as new passes and readings, never over what a
person made.

### 7a. What onboarding teaches

Setup is the method, explained as it goes. Each relevant step explains its topic in plain words,
with an example from the person's own pages where there are some, and says what the choice
changes. The **step order is to be aligned with the maintainer's step document (2026-10-02)**;
the topics are what must be covered somewhere along the way.

| Topic | What it explains | An example from the person's own material |
|---|---|---|
| **Languages** | language tags and Glottolog; that a document can hold several; how the language cascades to folders, pages and lines | "Page 12 has a Latin formula inside Spanish text" |
| **Scripts** | ISO 15924; direction; where the line sits; style variants of one script (naskh and nastaliq) | the script and direction worked out for a sample |
| **Fonts** | why a script needs a font that has its characters; the fonts Fichero ships and how to add one | a sample line shown in the chosen font |
| **Glyphs and Unicode** | characters, glyphs and code points; combining marks; private-use characters and their risks | a sample word broken into its characters |
| **A faithful way to write the script** | working out a graphemic representation: graphemes against allographs, what to keep distinct, abbreviations, private-use characters, declared signs | two letterforms on a sample page that are one grapheme |
| **Finding sources** | IIIF collections and archives that publish pages; adding them by reference | a manifest link pasted in, its pages shown |
| **Models and memory** | what a model is; why size and memory decide what runs on this Mac; local against cloud | "This Mac has 8 GB: the 3B corrector fits, the 7B does not" |
| **Kraken** | finding lines and reading them; segmentation and recognition models; training | the lines Kraken found on a sample page |
| **YOLO and layout** | detecting regions by kind; when a layout detector helps | regions found on a sample page |
| **Forms and tables** | finding cells, rows and columns; reading each cell | a table on a sample page |
| **Workflows and recipes** | a workflow is a few tools chained; a recipe is the steps, models, settings and places to run; following, overriding and sharing | the proposed recipe, step by step |
| **Entities** | people, places, things and their mentions; what a tagger can and cannot do in this language | names found in a sample line |
| **Statements** | subject, relation, object, each tied to the text it came from | "A sold B to C", found in a sample |
| **Maps** | georeferencing and gazetteers; places on a map | a place in a sample placed on a map |
| **Time and calendars** | dating systems, calendar changes, uncertain dates, one timeline | a date in a sample, normalised |
| **Normalisation** | as written, expanded, normalised; why the record keeps what was written | an abbreviation in a sample, three ways |
| **Output formats** | PAGE, ALTO, TEI, IIIF and the rest; what each is for; the synced folder | a sample page's TEI |
| **Fine-tuning and distilling** | training a small model on the project's corrections; teacher and student; when it pays | the corrected-line count so far, against the threshold |
| **HPC and remote compute** | clusters, GPU services, what they cost, what leaves the Mac | the estimate for training here and there |

**Written once.** Each explanation lives with its job or topic in the registry (section 2): the
plain description, its example's recipe (which sample to show and how), and its trade-offs. The
same text appears in setup, in the Inspector beside the setting it explains, in the recipe's
README and in the user manual. A new job or topic explains itself in all four by being registered.

### 7b. Setup, round 2: the screens as the next build makes them (ruled 2026-10-05)

The maintainer tested the five-screen setup built on 2026-10-04 and 2026-10-05 and ruled on it
(#5477 to #5482). **This section is the one home for setup's screens**: it supersedes the
provisional table of section 7 and the order in `source.onboard.screens-in-order`; other specs
link here and do not restate it. Each screen's behaviours are the `source.onboard.*` lines under
"Setup" below, each citing its issue.

**Ruled by the maintainer 2026-10-05 (answers to this section's questions).**
- **Every purpose and every job is a checkbox, and ticking one adds its own screen.** Each screen
  explains that job in plain words and asks its questions: transcription, search, entities (and
  their kinds), statements (SVO) and the knowledge graph, maps, Wikidata, training models,
  fine-tuning models, and the rest the jobs registry offers. Unticked jobs add no screen. This
  replaces the narrower "job details" screen proposed above. Statements, Translate and normalise,
  Quotations, Catalogue and Tables are among the checkboxes.
- **Where it lives (revised the same day):** a new project is made through **Set Up New Project…**
  (the File menu and first run both lead there), which opens setup; the location is a simple
  choice: **Inside Fichero** (the default: the app's own container, managed for the person) or
  **Choose a location…** (a folder picker, e.g. `~/Fichero`). Most people should not have to
  decide where a project lives.
- **Languages and scripts are type-to-find only** (later the same day): typing shows matching
  languages or scripts in a dropdown as you type; a pick becomes a token. No Browse… button or
  alphabetical list.
- **The order is: where the project lives, then its files, then keeping it exported**, then the
  purposes and the rest (later the same day).
- **Kept exported**: setup can set up exports that stay current, to a folder, in a chosen format
  (Word, Markdown, ALTO XML and the others) and one file per page or per document (screen 3).
- **Keep arranged** arranges the folder by the project's own structure (its folders), so Fichero
  keeps the material organised. A file a person moves by hand inside the folder stays where they
  put it, and Fichero's records follow the move (the folder and the project stay in sync).

**Setup in four steps (maintainer's direction 2026-10-05 evening, #5492; ruled yes 2026-10-06;
built 2026-10-06, app, not yet seen).** This supersedes the screens and their order in "The
screens, in order" below; what each screen asked is kept, now on the step named here. Setup was
still too many screens (nine, plus one per ticked job). Four steps, and a question appears only
under the choice that needs it:
1. **Your project**: its name, and where it lives (Inside Fichero, or Choose a location…).
2. **Your material**: how it comes in (Link, Copy, Move, Index, Keep arranged) and Add a Folder…;
   what it is (handwriting, print, typescript; languages and scripts as tokens; direction filled in
   from the scripts, changeable).
3. **What you want to do**: the purposes as checkboxes; ticking one opens its one or two questions
   in place under it (People, places and things: which kinds; Map places: which gazetteer), with
   one sentence saying what it does. Nothing for an unticked purpose is shown.
4. **Ready**: the plan as one list, what runs by itself (one choice), optional rows for Check on
   your pages and Keep an export…, and Start.
The per-job screens go; their explanations become the sentence under each checkbox. Anything
optional can also be done later from the Inspector.

*Built 2026-10-06 (app, not yet seen):* `FirstRunStep` is welcome, permissions, AI, then
`.project`, `.material`, `.purpose`, `.ready`; Set Up… runs `.material`, `.purpose`, `.ready`.
Your material hosts the ways-in control, Add a Folder… with a tied folder's intake, the page count,
and the language, script, direction and material fields on one card. What you want to do ticks
purposes; a ticked one shows its description and the questions of its jobs
(`RecipeSetupStore.questions(under:)`: which kinds of names, which gazetteer, into what form; a
question shared by two ticked purposes is asked once, under the first). Ready
(`RecipeReadyFields`) shows the recipe's rows with the one cloud question and Also on hand, the
estimate, What runs by itself as one choice (`setRunsByItself`), Check on your pages
(`BakeoffSection`) and Keep an export (`KeptExportFields`) marked optional; the plan is saved
whenever it changes so the estimate and Start follow it; Start keeps the export rows, saves, then
starts. Continue on Your material and What you want to do saves the draft. Deleted: the per-job
screens (`SetupPage`, `SetupJobFields`), the Kept exported, What it is, How it will be done, What
runs by itself and Start screens as separate steps, and the jobs checklist (a job is added on
Ready). Pinned by `fichero/Tests/Unit/general/Models/SetupFourStepsTests.swift`. *Not built:*
"into which language" for Translate or normalise (only how far is asked); "roughly when".

**What is built today, read on disk 2026-10-05.** First run's setup store is the app-wide one
(`AppState` makes `RecipeSetupStore(client: ficheroClient)`), whose client sends no project path,
so `GET`/`PUT /api/recipes/project` answer 400 and Start never enables (#5477). A project made from
File › New Library… goes through `LibraryManager.createProject(at:)` (a save panel, then
`POST /api/library` when the engine first opens it); first run has no such step (#5482). The
engine's `assemble()` takes one purpose and one material (`Answers.purpose`, `Answers.material`
in `recipes/assemble.py`); the Purpose screen is a single choice and the material a single-choice
menu. Languages and scripts are searched (`GET /api/recipes/languages`, `/scripts`) but a typed
word is kept as typed, so "spanish" reached the rules and every reader was refused because cards
list tags ("es") (#5479). Direction is shown, worked out from the script, never chosen. Each
step's topic sentence has its paragraph behind a disclosure, and a step with no model shows the
rules' raw reason, model ids and all, twice (#5481). Setup offers Link, Copy, Move and Index; the
engine's folder import with `mode: index` adopts the folder as a synced folder (#4952), but the
app never calls `/api/sync-folders`, so an indexed folder's intake is never shown or switched on
(#5480).

**Rulings (2026-10-05, the maintainer, testing setup):**
- First run asks where the project lives, makes it there, and saves everything after into it
  (#5482, #5477).
- Purposes are checkboxes: a project can be for any combination; each purpose is a set of jobs
  (#5478).
- "Nothing runs automatically" is a screen of its own (#5478).
- A fifth way in, **Keep arranged**: like Index, the folder stays where it is, but Fichero manages
  the whole folder and keeps the files in it stored logically (#5480).
- Languages, scripts **and direction** are chosen in setup; languages and scripts each have type-to-find
  search (no browse menu, revised the same day); several at once, shown as tokens; a language is stored as
  its tag (#5479).
- Material (handwriting, print, typescript) is checkboxes, any mix; the recipe proposes a reader
  for each kind present (#5478).
- No More or Advanced disclosure chevrons anywhere in setup; one sentence per step; a step's
  problem is shown once, in words a historian reads, with the fix as a button; never a raw model
  id (#5481).

**The screens, in order.** Back and Continue on every screen; Continue saves the answers so far
into the project as a draft (`PUT /api/recipes/project`, through the project's own client);
nothing runs before Start. Set Up… on an existing project starts at screen 2 (the project already
lives somewhere).

1. **Where it lives** (#5482). The project's name (default "My Project") and where it lives: **Inside
   Fichero** (the default, the app's own container) or **Choose a location…**, which opens a save
   panel (ruled 2026-10-05, revised the same day). Continue makes the `.fichero` package there through the one create path
   (`LibraryManager.createProject(at:)`, which grants the folder and has the engine open it with
   `POST /api/library`), and from then on setup reads and writes through **that project's**
   client, the same path as Set Up… from a project. A location that cannot be written is refused
   on this screen in words ("Fichero can't write to that folder. Choose another."), and the
   person stays on it. This is what fixes the first-run 400 (#5477): there is always a project to
   save to.
2. **Your material** (#5480). How material comes in, five ways, each with one sentence of what it
   does to the originals: **Link** (default; read where they are, never changed), **Copy** (the
   project keeps its own copy), **Move** (the files move into the project; the originals go),
   **Index** (the folder stays where it is; Fichero writes its changes back into it and takes in
   files added to it after a preview), and **Keep arranged** (as Index, and Fichero also keeps the
   files in the folder arranged; below). Then Add a Folder… or Add Files…, a IIIF manifest, or
   "later"; the page count (counted, or asked in bands only when it cannot be counted). Choosing
   Index or Keep arranged with a folder ties that folder through `/api/sync-folders` and shows it
   (its path, how many files, intake on or off with the preview's count), so Index is whole, not
   only a recorded mode.
3. **Kept exported** (#5485). Optional, and skipped with Continue. The project can keep an
   up-to-date copy of its work in a folder outside it, written again as the work changes, so a
   person always has the files they hand on. One row per export: the **folder** (Choose…), the
   **format** (Word, Markdown, plain text, ALTO XML, PAGE XML, TEI, hOCR), and **one file per
   page or per document**; more than one export may be kept (Word per document for reading and
   ALTO per page for another tool). It is one-way: Fichero writes the folder and never reads it
   back; a file changed there by hand is overwritten at the next write and the person is told so
   once, when the export is set up. Writing goes through the one export path
   (`page_export.py` and `formats/` for page formats, `export_service.py` for Word), as a
   background job that waits while the person works (`user-machine-always-useful`). **Engine
   built 2026-10-05** (`source.onboard.kept-exported`, `/api/export/kept`, with a Markdown writer);
   the screen built the same day (app, not yet seen).
4. **What it is for** (#5478). The engine's purposes as **checkboxes**, any combination; none
   ticked is "Not sure yet" (the tools are offered when wanted; nothing is proposed). Under each
   ticked purpose, its jobs in one line each, by their topic titles ("Find lines · Read each line ·
   Correct"). The recipe is the union of the ticked purposes' jobs, each once, in the registry's
   step order. The purposes and their jobs:

   | Purpose (checkbox) | Jobs it proposes (registry ids) |
   |---|---|
   | Transcribe | `find-lines`, `read-a-line`, `correct` |
   | People, places and things | the above + `find-names-tag-words` (entity kinds chosen on screen 6) |
   | Search my sources | the above transcribe jobs + `make-a-vector` |
   | Statements (who did what to whom) | transcribe jobs + `find-names-tag-words`, `find-statements` (subject, verb, object) |
   | The full knowledge graph | transcribe jobs + `find-names-tag-words`, `work-out-dates`, `find-statements`, `link-to-authorities`, `make-a-vector` |
   | Map places | transcribe jobs + `find-names-tag-words`, `place-in-a-gazetteer` (checks each place against the gazetteer), shown on the map |
   | Translate or normalise | transcribe jobs + `translate-transliterate-normalise` |
   | Gather quotations | transcribe jobs + `pull-out-passages` |
   | Catalogue my sources | transcribe jobs + `describe-for-the-catalogue`, `work-out-dates` |
   | Tables and forms | `find-regions`, `find-a-tables-cells`, `read-a-line`, `extract-to-a-table` |
   | Edit a corpus | `find-lines`, `read-a-line` (then tools, nothing more by itself) |
   | Decipher a script | `find-signs`, `identify-signs` offered as tools; nothing proposed to run |

   Jobs any purpose may add, offered on screen 7 as "Also on hand" (never hidden, as
   `source.onboard.offers-never-hides`): `prepare-the-image` (clean up images: crop, straighten,
   brighten), `split-pages`, `put-in-order` (reading order), `refine-shapes`, `check`, `export`,
   `publish`, `train-a-model`. **Hands** (telling one writer's hand from another) has no job in the
   registry today (`recipes/seed/topics.yaml`), so setup does not offer it; see Open questions.
   The five new purposes (Statements, Translate or normalise, Gather quotations, Catalogue, Tables
   and forms) are proposed by this spec, not yet ruled (Open questions). The engine's `assemble()`
   and the saved answers take a **list** of purposes (`answers.purposes`); a project saved with one
   `purpose` reads as a list of one.
5. **What it is** (#5479, #5478). Four rows, each pre-filled where the samples or the engine can
   say, each changeable:
   - **Languages**: type to find (ruled 2026-10-05): typing shows the matching languages from the
     engine's language registry (ISO 639-3 joined with Glottolog; "spanish" offers Spanish `es`,
     and its dialects with whose dialect each is) in a dropdown under the field as you type; no
     Browse… menu or alphabetical list. Each chosen language is a token (a lozenge with its name;
     its tag shown on hover); several at once; a token is removed with its ×. What is saved is the
     **tag** (`es`, `la`, a private-use tag for a Glottolog-only language), never the typed word.
   - **Scripts**: the same, from ISO 15924 (type to find by name or code, as languages),
     tokens, the code saved (`Latn`, `Arab`).
   - **Direction**: chosen, pre-filled from the scripts (the engine's derived fact, with where it
     came from): left to right, right to left, top to bottom (columns right to left), top to bottom
     (columns left to right). With several scripts, one direction per script.
   - **Material**: checkboxes **Handwriting**, **Print**, **Typescript**, any mix (at least one,
     default Handwriting), with "roughly when" beside them. The recipe proposes a reader for each
     kind ticked, and a project with more than one kind gets one reader per kind (a folder or page
     override says which applies where; until it is known, the handwriting reader is the default).
   The derived facts (fonts a script needs, may-be-vertical) stay as one line under the script
   row.
6. **The details a job needs** (#5478). One short screen for each ticked job that needs an answer
   the engine cannot work out, and only for those; none of them appears for a job not ticked:
   - **Entities** (`find-names-tag-words`): which kinds to find, as checkboxes: people, places,
     organisations, dates, things (objects, goods), events, and the project's own kinds; default
     people and places.
   - **Translate or normalise** (`translate-transliterate-normalise`): into which language (the
     same language field as screen 5) and how far: as written, abbreviations expanded, or
     normalised spelling.
   - **Gazetteer** (`place-in-a-gazetteer`, Map places): which gazetteer (GeoNames, Wikidata, the
     project's own list) and the region and period to favour.
   - **Catalogue** (`describe-for-the-catalogue`): which catalogue fields, from the project's
     metadata fields.
   - **Tables** (`extract-to-a-table`): the columns, from the project's metadata fields or typed.
   Cleaning up images, reading order, dates and statements need no screen: their settings have
   defaults and live in the Inspector.
7. **How it will be done** (#5481). The proposed recipe, one row per step: the step's title and
   **one sentence** from its topic in the registry (`GET /api/topics`), where it runs, and the
   model by its card's display name (never its id, pin or repository path). **No disclosure
   chevrons**: no More, no Advanced; the topic's paragraph and example belong in the Inspector and
   the manual. A step that cannot run shows its problem **once**, on its own row, in words built
   from the rule that refused it ("No reading model here knows Spanish yet."), with the fix as
   a button ("Download a Spanish reader…", "Use a cloud model…", "Choose a model…"); the reason as
   the rules wrote it goes to the log and the Inspector, not here. The cloud question is here, once,
   only when a step would use the cloud. "Also on hand" lists the other jobs (screen 4) as rows the
   person can add.
8. **What runs by itself** (#5478). Its own screen. At the top, one choice: **Nothing runs
   automatically** (new material waits for a run by hand) or **New material runs through
   the ticked steps**. Below, each step of the recipe with a checkbox, pre-ticked by the purposes'
   kind (a just-do-it purpose ticks its steps; Edit a corpus, Decipher and none ticked tick
   nothing). It says plainly what Start does and what import does: **Start** runs the recipe once
   over the material already in the project (the first yes; screen 9 lists what that is); **after
   Start**, each import runs only the ticked steps over the pages it brought, and with Nothing runs
   automatically, an import runs nothing; an unticked step runs only when the person runs it.
   A train step is ticked only if the person ticks it (`source.recipe.train-never-automatic`).
9. **Start** (#5477). Unchanged from today (the summary, the plan's pages and cost, Start as the
   first yes), with one requirement: it works in first run, through the project made on screen 1.

**Keep arranged (#5480, specified here; its questions are under Open questions).** Keep arranged
is Index plus arrangement: the folder is tied as a synced folder (as Index), and Fichero also owns
where files sit inside it. It arranges by a rule chosen in setup (see Open questions: the
project's structure, date, or a written rule); it **moves and renames files only inside that
folder**, never out of it and never deletes one; each arrangement is one audited, undoable action
listing every move (old path, new path), and undo puts every file back; a file added from outside
(Finder, a scanner) is taken in by intake after its preview and then moved into place by the same
rule; a file the person moves by hand is left where they put it and recorded as placed by hand
(Fichero does not fight the person). Before the first arrangement, setup shows how many files
would move and a sample of the new paths, and nothing moves until the person says yes.

### 8. How the recipe is assembled: rules first, measurement second

**By rule, and deterministic** (ruled 2026-10-01). The recipe is assembled from the answers and
the confirmed facts on model cards. The same answers and the same catalogue always give the same
recipe, so it is reproducible, explainable and testable. In order:

1. **Look for a published recipe that fits.** The shipped and catalogue recipes whose `suits`
   cover the scripts, languages, material and period, and whose steps serve the purpose, are
   listed; the flagship comes first where it fits. If one fits, it is proposed as the recipe to
   follow, and the rest of this list fills only the steps it leaves without a model this Mac can
   use.
2. **Otherwise, generate one.** The purpose gives the steps (a template per purpose: which jobs,
   in which layers, in which order). For each step, candidates come from the catalogue and from
   the model finder (`source.find.by-need`), which searches Hugging Face, Kraken's Zenodo
   repository and the open list of sources by job, script, language and period.
3. **Filter by hard constraints.** A candidate is kept only if its card names the step's job;
   covers the project's script (the coverage measure in section 1; a reader whose character set
   lacks the script is out; a finder whose card says "any script" stays in, marked "not measured
   on this script") and, for a language-dependent job, its language; can run on this Mac
   or on a bound compute target; has an open licence class, or one the person has accepted; and,
   if it runs in the cloud, the project allows pages to leave. A **correction or normalising step
   by a language model** is kept only if the model's card lists the project's language: a model
   that does not know the language would turn it into one it does (a Cherokee or Nahuatl text into
   English or Spanish), so it is left out, and the recipe says why; in a mixed document it may
   still correct the segments whose language its card lists. A reader made for **another style of
   the same script** (naskh for a nastaliq hand, ISO 15924 `Aran`) is not proposed as a substitute;
   the gap is named. Material (print, handwriting, typescript) and period are otherwise **soft**:
   a handwriting reader may be proposed for print, ranked after print readers; a print-only reader
   (Tesseract) is never proposed for handwriting. An unknown period counts as neither a match nor a
   mismatch.
4. **Rank what is left** (below), per step, and then as **combinations** across the steps of a
   chain.
5. **Explain each choice** in the facts it rests on: "chosen because its card says Latin script,
   Spanish, 1500–1700, handwriting; CER 6.1% on your 12 pages; local, free, about 400 pages an
   hour on this Mac; trainable".

**The ranking signals** (2026-10-01). Each candidate, and each combination, carries six numbers
or facts, shown in the bake-off table and on screen 4:

| Signal | From | Notes |
|---|---|---|
| **Accuracy** | this project's measurement; else the published measurement on matching material; else the coverage tier | character and word error rate per hand and page kind; coverage is a floor, not a score of quality |
| **Cost** | the vendored price list times the whole volume; compute-target hours for a cluster | estimated for the whole volume before anything runs |
| **Local or remote** | the card and the project's egress rule | this Mac, a compute target, or a cloud provider |
| **Speed** | measured on this Mac where it has run; else published, marked as an estimate | pages per hour, and the time for the whole volume |
| **Carbon** | the energy estimate in section 1 | always labelled an estimate; "unknown" where no figure exists |
| **Trainability** | the card | whether the project can later fine-tune it on its own corrections |

The order is fixed, so the ranking stays deterministic: **accuracy first, in bands** (candidates
within one point of character error rate of the best are tied on accuracy); within a band,
**local before remote**, then **cheaper**, then **faster**, then **lower carbon**, then
**trainable before not**, then smaller size, then the card id. The **volume** sets one more rule:

| Volume | Rule | What it usually means (2026-10-01 search) |
|---|---|---|
| Under 100 pages | start cheap and local; if the A/B shows it misses the bar, a cloud model the project allows is the first escalation, because its whole cost is small | Tesseract or Kraken first, then a cloud vision model if needed |
| 100 to 5,000 | the fixed order | a local specialist reader or a small historical vision model on this Mac, at no cost |
| 5,000 to 100,000 | the fixed order, and the train step is offered from the start, because a fine-tuned fast reader repays its training | a Kraken reader fine-tuned on the project's corrections, or a distilled adapter |
| More than 100,000 | as above, and a candidate whose whole-volume cost or time is beyond the limits (engine constants; by default more than 500 dollars in the cloud, or more than 30 days of background work on this Mac) is shown but not chosen; the recipe proposes the teacher-and-student path (`compute/distillation.md`): the best model reads a sample as teacher, people correct it, and a small trainable model is fine-tuned, on a cluster where needed, for the rest | training on a cluster, then a fast student on this Mac or a cluster |

**Cheapest and local first; escalate on evidence** (ruled 2026-10-01). Whatever the volume, a
step's **starting** choice is the cheapest local candidate that passes the hard constraints:
Tesseract for print and typescript where it has the script, Kraken (a specialist reader, or the
multi-script PP-OCRv6 readers) for handwriting, or a local open OCR model where neither fits (for
example Chandra, or a small historical vision model such as CHURRO). The first A/B test then puts
that choice beside the costlier options (a larger local model, a cloud model, a combination) on
the person's own pages, showing **accuracy, cost and environmental cost side by side**. The
recipe moves to a costlier option only when that comparison shows the cheap one misses the
project's bar, and the person confirms. **Distilling and fine-tuning are options**, offered when
the comparison or the volume makes them worth it, never the default. The volume table below
says when each escalation is worth offering; it no longer lets a cloud model be the starting
choice.

**Reader tiers, when nothing is measured.** Accuracy without a measurement falls back to the
reader's tier, from the 2026-10-01 search: **specialist line readers** (Kraken models, including
the multi-script PP-OCRv6 readers; TrOCR fine-tunes) above **small historical vision-language
models** (CHURRO-class, a few billion parameters, trained on historical documents) above
**general vision-language models**. **Tesseract** is a tier of its own for print and typescript
only; it is never proposed for handwriting (it can still be tried by hand). Fine-tuned adapters
(LoRA) are found as their own tier, with their base model, and are scarce today. Within a tier,
coverage orders the candidates.

**LOOVE coverage applies to tokenizer models only.** For cloud and local language and
vision-language models it is a filter (unreachable characters exclude) and the last accuracy
signal when nothing is measured. For Kraken and Tesseract, which read through a fixed character
set, the character-set coverage in section 1 does that job instead. For a measured candidate,
measurement outranks both.

**A language model helps, never decides.** It can fill in a prose-only card (facts marked
unconfirmed), explain a choice in plain words, or suggest answers from sample pages. It runs on
the Mac, or in the cloud only where the project allows. The rules still assemble the recipe.

**Where no model fits** a step, setup says so in words ("No reader is known for this script"),
keeps the step in the recipe marked **needs a model**, and offers what does work: draw or check
lines by hand, transcribe by hand, draft with a vision model the project allows and correct, and
then the train-your-own path (`compute/distillation.md`). Steps that do not depend on it run;
steps that do wait, saying why. Never a quiet substitute.

**The flagship and the generated path are one flow.** The flagship recipe is simply the published
recipe that step 1 finds for historical Spanish hands; it has been tuned and measured end to end
on real pages of that material, and its defaults need no adjusting. A generated recipe is what the
same flow makes when step 1 finds nothing. Either can be followed, overridden, forked and
published.

### 8a. Trying another option, at any time (and the bake-off)

The bake-off is the evaluation job run at setup; its behaviours live in `compute/distillation.md`, "Evaluation against out-of-the-box models" (moved 2026-10-04).

A person can **compare options whenever they like**, not only during setup, and **for every job**,
not only reading. On any selection (a few pages, one region, some lines, a document),
**Try Another Option…** (Inspector and context menu) offers, for a step or a run of steps, one or
two alternatives: another reader; Kraken lines read by Tesseract against a vision model reading
the page; a different prompt; another corrector; spaCy pipeline A against B against a language
model extractor for entities; another model or prompt for statements; another authority for
linking; another date rule; another layout detector; another embedding model for search. Then:

- Each alternative runs on the selection as a job in Activity, after showing its cost and time,
  and lands as **new passes, readings, mentions or claims**, never over existing work. (A search
  vector alternative is built beside the current index and does not replace it.)
- The results open **side by side in panes** (Source view panes for shapes, Reader panes for
  text, lists for entities and statements), compared **the way the job declares**:

  | Job family | How outputs are compared |
  |---|---|
  | shapes (regions, lines, signs) | overlaid on the same image; where a person drew or confirmed shapes, overlap scores (precision and recall at a stated overlap) |
  | readings | a text diff with differences highlighted (the diff lens); character and word error rate where the selection has corrected text |
  | entities, statements, authority links, dates | precision and recall against what a person has confirmed, where there is some; otherwise side-by-side lists with what only one side found marked |
  | search vectors | a few queries the person types (or the project's saved searches), with each option's top results side by side, and which results the person marks relevant |

  Each option also shows its cost, speed and carbon estimate.
- **Use This** makes the winner the step's choice (or the combination's) **for a scope the person
  picks**: the project, or just this folder. It is stored as an override on the recipe, like any
  other.
- The comparison is **kept**, with its selection and options, and can be run again later (after
  more corrections, or a new model).

**The bake-off is this same tool**, run by setup on the sample ground-truth pages, over the
combinations the rules propose:

- **Combinations, not single models.** For each chain of steps (find lines then read; read then
  correct), the bake-off ranks whole candidate pipelines: for example three line finders by three
  readers. The rules prune first, so it stays small: the top three per step by rule rank, then at
  most **nine combinations**, keeping those with the best summed rule rank. All run on the same
  pages.
- **Tesseract is in every bake-off for print and typescript**, as the fast local baseline, when it
  has data for the language; never for handwriting.
- The table shows, per combination: accuracy per hand and page kind, cost for the whole volume,
  local or remote, speed, carbon estimate and trainability, ranked by the fixed order above.
- **The winning combination is what the recipe records**: each step's model is set from it, and
  the measurement goes on the cards and into the recipe's measurements.
- It needs at least **100 corrected lines on at least two pages** (an engine constant); below that
  it says how many more are needed and is offered again when there are enough. It runs as a job in
  Activity, so the person can leave setup while it runs; the first automatic run waits until the
  winner is confirmed or the bake-off is skipped. Cloud candidates take part only where the
  project allows the cloud, and their cost is shown first.
- **Skipping** keeps the rule-ranked recommendation. Each such step shows "not measured on this
  project" in the Inspector, and the bake-off is offered there once enough ground truth exists.

### 8b. Scripts and material the flow must handle

The flow has no special case for any script; these are the cases it is checked against, so that
"any language" is tested, not assumed. The verdicts come from the search in 8c.

| Material | What the rules and setup do |
|---|---|
| **Latin-script hands** (the flagship; early-modern English, French, German Kurrent) | specialist readers and a small historical vision model exist but rarely for the exact period and hand; the bake-off on the person's pages decides; the flagship fits Spanish |
| **Print and typescript in any script** | Tesseract's data for the language (the print baseline), Apple's document reader where its run-time list has the language, and Kraken print models (PP-OCRv6 covers ten scripts) compete |
| **Hebrew, Armenian, Greek print, Syriac, Georgian, Ge'ez** | multi-script Kraken readers with published per-script error rates; where the published rate is high (Georgian), the train step is offered from the start |
| **Arabic-script hands** | naskh readers exist; a **nastaliq** hand (Persian, Ottoman) has none, and a naskh reader is not proposed in its place: "needs a model" |
| **Chinese, Japanese and Korean, including vertical text** | direction (top to bottom, columns right to left) follows from the script; finders and readers that declare vertical text only; general vision models as candidates where the project allows the cloud |
| **Kuzushiji** (cursive Japanese) | a few new open readers (a fine-tuned small vision model; a Zenodo model): candidates for the bake-off |
| **Chữ Nôm, Coptic, Tibetan** | no open reader passes (some exist only inside closed platforms): "needs a model", and Tesseract only for print where it has data |
| **Palm-leaf manuscripts** (Khmer, Balinese and others) | long, narrow, damaged leaves with curving lines: a prepare step and a finder that keeps curved baselines; no open reader: "needs a model" |
| **Indigenous languages in Latin letters** (colonial Nahuatl, Quechua) and **syllabaries** (Cherokee) | readers exist only in closed platforms, or not at all; a letter-faithful Latin-script reader can draft with the person correcting; no language-model correction unless its card lists the language; no fake lemmas; usually the train path |
| **Scripts read sign by sign** (cuneiform, Egyptian hieroglyphs and hieratic, Linear B, Maya) | "find signs" and "identify signs" against a sign list replace "find lines" and "read a line"; specialist pipelines found are shown but are not runnable until a job runs them; a general vision model is never proposed in their place; the purpose offered first is "Decipher a script" or "Edit a corpus" (`undeciphered-scripts.md`) |
| **Undeciphered scripts** | the "Decipher a script" purpose: tools, not automation |
| **Languages with no script** (oral recordings) | "transcribe speech" with Whisper (about a hundred languages) or MMS (over a thousand, under a non-commercial licence, so a deliberate choice), chosen by the language lists on their cards, into the orthography or IPA chosen at setup; LOOVE coverage does not apply; where no speech model lists the language, transcribe by hand and train |

### 8c. Evidence from the 2026-10-01 model search

A search of Hugging Face, Kraken's Zenodo repository, HTR-United and Tesseract's data across 31
cases, made to test this design before it is built. **GOOD**: structured facts are enough for a
rule to choose. **PARTIAL**: something usable exists, but period or hand is in prose only, so the
bake-off decides. **NONE**: no open model; the train path. Model names are examples found, not
choices made.

| Case | Verdict | Found (examples) |
|---|---|---|
| 16th-century Spanish secretary and procesal hands | PARTIAL | TRIDIS v2 (Zenodo), PP-OCRv6, CHURRO 3B; spaCy Spanish; Tesseract `spa` for print |
| Early-modern Latin, print / hand | GOOD / PARTIAL | CATMuS and medieval TrOCR families, TRIDIS; LatinCy; Tesseract `lat` |
| Medieval Latin (Caroline, Gothic) | GOOD | TrOCR per script style; a CATMuS-trained Qwen vision model |
| German Kurrent (19th century) | PARTIAL | a Kraken Kurrent model; Tesseract Fraktur data for print |
| German Fraktur print | GOOD | PP-OCRv6; Tesseract `frak2021` |
| Early-modern English secretary hand | PARTIAL | TRIDIS v2; CHURRO |
| French 18th-century hand | PARTIAL | McCATMuS (16th–21st c.); medieval French TrOCR and one LoRA adapter |
| Arabic manuscript (naskh) | PARTIAL | Muharaf recogniser and segmenter (Zenodo) |
| Persian and Ottoman nastaliq | NONE | — |
| Hebrew, print / cursive hand | GOOD / PARTIAL | PP-OCRv6 (published CER 1.47%) |
| Yiddish | PARTIAL | PP-OCRv6; Tesseract `yid` |
| Syriac | PARTIAL | PP-OCRv6 (published CER 4.8%) |
| Coptic | NONE | Tesseract `cop` for print only |
| Greek polytonic, print / manuscript | GOOD / PARTIAL | CLLG polytonic Greek (HTRMoPo card); greCy |
| Church Slavonic, Old Cyrillic | PARTIAL | Old Cyrillic uncial model (Zenodo); a 1B line reader |
| Armenian | GOOD | PP-OCRv6 |
| Georgian | PARTIAL | PP-OCRv6, published CER high (12.75%): fine-tune |
| Ge'ez and Amharic | PARTIAL | a pre-alpha Ethiopic fine-tune of PP-OCRv6 |
| Sanskrit in Devanagari | PARTIAL | TrOCR and PP-OCRv6 fine-tunes; a curved-line segmenter |
| Tamil, historical | PARTIAL, near NONE | a multi-script Indic research model |
| Classical Chinese woodblock | PARTIAL | research models; general vision models; layout detectors |
| Japanese kuzushiji | PARTIAL | a 2B vision model fine-tune; a Zenodo model |
| Vietnamese chữ Nôm | NONE (open) | a PaddleOCR fine-tune outside these ecosystems |
| Colonial Nahuatl and Quechua | NONE (open) | closed platform models only |
| Cuneiform | NONE (HTR ecosystems) | a specialist sign detector (code and weights on Zenodo) |
| Tibetan | NONE (open) | closed platform models only; Tesseract `bod` for print |
| Khmer palm-leaf | NONE | research models and data only |
| Egyptian hieroglyphs and hieratic | NONE | a specialist sign pipeline |
| Linear B, Old Turkic, Maya | NONE | — |
| Speech, major / low-resource / unwritten languages | GOOD / PARTIAL / NONE | Whisper; MMS; fine-tunes |

Of 30 written cases: 6 GOOD, 16 PARTIAL, 8 NONE. So the bake-off decides about half the time, and
the honest "needs a model" path is needed for about a quarter. That is why both are part of
setup, not exceptions to it.

What the search changed in the rules above: period is never structured on model cards (it is
confirmed by a person, or taken from a training set's HTR-United record); accuracy is structured
mainly in HTRMoPo cards (read through `htrmopo`); line or page reading is worked out from the
architecture; reader tiers order unmeasured candidates; LOOVE coverage applies to tokenizer
models only; fine-tuned adapters are a tier of their own and scarce; the volume bands change the
recommendation; Tesseract is a print baseline and never a handwriting reader; and the NONE cases
are named, never filled with a model for another style or a general vision model.

**Not verified by the search**: whether Tesseract has data for the Cherokee syllabary (the search
reports none; Tesseract's own published list is to be checked when the provider is built).

### 9. The recipe: what it holds, and its file format

A **workflow** is a few tools chained. A **recipe** is bigger (ruled 2026-10-01): the steps a
project runs, in order, each with its job, where it applies (which segments: pages, regions of a
kind, lines, words), its model, its settings, its prompt, its layer and where it runs; plus its
profile. A recipe refers to workflows by name and may carry its own; it never copies one the
workflow store already holds. **The locked default workflows stay in the workflow store**; shipped
recipes refer to them by name, so each chain exists once (`source.recipe.holds-no-second-copy`).
Applying a recipe's steps makes and runs workflows: what runs is always a workflow.

**Where it lives.** A project's recipe lives in the project's database, as data the engine owns:
the followed recipe and version, the project's overrides, its purpose and added layers, and its
compute-target bindings. The Inspector, MCP and the command line all read the same **resolved
recipe** from the engine. The resolved recipe has an `automatic` section, worked out from the
purpose and the steps' layers, listing what runs by itself on add (and so is kept current on
change) and whether each may use the cloud; this is the section the activity spec asks for, and
it is never written by hand. The folder below is what **Export Recipe** writes and what the
catalogue holds.

**A recipe is a folder.**

```
spanish-hands/
  recipe.yaml              what it suits, its profile, its steps in order
  prompts/*.prompt.md      every prompt, one file each, with a small header
  workflows/*.json         any workflows the recipe carries (built only from Fichero's tools)
  measurements.yaml        results: error rates per step, hand and page kind, on what, when
  ro-crate-metadata.json   the Workflow RO-Crate wrapper, generated by Fichero
  LICENSE                  the recipe's own licence (CC BY 4.0 for the shipped ones)
  README.md                plain words for a person deciding whether to use it
```

**The flagship's `recipe.yaml`, as an example of the schema.** The model pins below are
**illustrative**: the real ones are set by the flagship's own measurement (#4950), and a DOI shown
as `NNNNNNN` is a placeholder.

```yaml
fichero_recipe: 1                       # schema version; a newer one than this Fichero knows is refused
id: fichero/spanish-hands
version: 1.2.0
title: Historical Spanish hands, 1500-1800
authors: [{name: Fichero maintainers}]
licence: CC-BY-4.0
suits:
  scripts: [Latn]
  languages: [es]                       # BCP 47; Glottolog stan1288
  material: [handwriting]
  period: {from: 1500, to: 1800}
  kinds: [letters, notarial, administrative]
purposes: [transcribe, entities, search, knowledge-graph, map-places]
defaults:                               # the profile
  direction: ltr
  line_position: baseline
  guideline: diplomatic                 # abbreviations kept as written; expansions are a second reading
  normalisation: as-written
  record_rule: strict
  fonts: [Junicode]
  views_first: [source, reader]
steps:
  - id: split
    job: split-pages
    layer: prepare
    applies_to: pages
    when: {spreads_detected: true}
    model: {builtin: page-splitter}
    runs_on: this-mac
  - id: lines
    job: find-lines
    layer: lines
    applies_to: pages
    model: {kraken: blla, kraken_version: "5.2"}
    runs_on: this-mac
  - id: read
    job: read-a-line
    layer: reading
    applies_to: {lines_in: [main-text, margin]}
    model: {zenodo: 10.5281/zenodo.NNNNNNN}          # a Kraken reader, pinned by version DOI
    runs_on: this-mac
  - id: correct
    job: correct
    layer: reading
    applies_to: lines
    when: {confidence_below: 0.90}      # small first, big when unsure
    model: {hf: mlx-community/Qwen2.5-VL-7B-Instruct-4bit, revision: 1a2b3c4}
    alternatives:                       # used in order when this Mac cannot run the pin
      - {hf: mlx-community/Qwen2.5-VL-3B-Instruct-4bit, revision: 5d6e7f8}
    prompt: prompts/correct-line.prompt.md
    settings: {temperature: 0, keep_spelling: true}
    runs_on: this-mac
  - id: names
    job: find-names-tag-words
    layer: entities
    applies_to: readings
    model: {spacy: es_core_news_md, version: "3.8.0"}
    runs_on: this-mac
  - id: dates
    job: work-out-dates
    layer: graph
    applies_to: readings
    settings: {calendars: [julian, gregorian], switch: 1582-10-15}
    runs_on: this-mac
  - id: statements
    job: find-statements
    layer: graph
    applies_to: readings
    model: {role: $large}               # resolved by the project; a shared recipe may name a role
    prompt: prompts/statements.prompt.md
    settings: {check_transfer_verbs: true}
    runs_on: this-mac
  - id: vectors
    job: make-a-vector
    layer: vectors
    applies_to: readings
    model: {hf: intfloat/multilingual-e5-large, revision: 0dc5580}
    runs_on: this-mac
  - id: tei
    job: export
    layer: output
    settings: {formats: [tei, page], to: synced-folder}
  - id: train-reader
    job: train-a-model
    layer: train
    offered_when: {corrected_lines_at_least: 2000}
    settings: {kind: kraken-recognition, base: read}
    runs_on: cluster                    # bound by the project to one of its compute targets
```

Rules the schema enforces:

- **Models are pinned**: a Hugging Face repository and revision; a Zenodo version DOI; a spaCy
  package and version; a Kraken built-in and Kraken's version; or, for a cloud model, the provider
  and its model id (a hosted model's weights cannot be pinned, so the recipe also records the date
  it was measured). A shared recipe may name a **role default** (`$large`) instead, resolved by
  the project.
- **`runs_on`** is a kind of place: `this-mac`, `cloud: <provider>`, `cluster` or `gpu-service`.
  A shared recipe never names a person's own cluster account; the project binds each kind to one
  of its compute targets.
- **`alternatives`** are tried in order when the pin cannot run here (too little memory, wrong
  chip); the one used is recorded on the project and shown.
- **`when`** and **`offered_when`** are the only conditions, from a short fixed list (spreads
  detected, a confidence threshold, a count of corrected lines). There are no expressions.
- **Every job named must be in this Fichero's registry**, and every step's input must be given by
  an earlier step or by the source itself.

**A prompt is a file** with a small header, so prompts are reviewed like code:

```markdown
---
for_job: correct
written_for: {hf: mlx-community/Qwen2.5-VL-7B-Instruct-4bit}
version: 3
variables: [reading, guideline]
---
You are checking a transcription of one line of a historical Spanish hand...
```

A variable the step does not supply is refused when the recipe is checked.

**`measurements.yaml`** records, per step: the model pin; character and word error rate per hand
and per page kind; how many lines and pages; which pages (IIIF links to public pages, or "private:
N pages" where they cannot be shared); the Fichero version; and the date. The flagship publishes
its measurements; a project's own bake-off results are kept on the cards and are added to the file
only when the person exports or publishes.

**A recipe is data, never code.** It names models, prompts, settings and workflows built from
Fichero's own tools. It cannot carry scripts, cannot grant a model tools or network access, and
cannot reach anything outside the registered jobs. Importing a recipe that tries is refused,
naming the offending entry. **A recipe never holds a key**: it names providers and models; keys
stay in the Keychain (`ai/ai-settings.md` (section K)).

**A recipe is checked before anything runs**: at setup, when taken from the catalogue, when an
update is offered, and before each run. The check reports, step by step: unknown jobs (with the
Fichero version that has them); a newer schema version; inputs no earlier step gives; pinned
models that cannot be found; models this Mac cannot run and no alternative can; cloud steps in a
project whose pages may not leave; cloud steps whose provider has no key; `cluster` steps with no
bound target; missing prompt files or variables.

### 10. Where the recipe sits

The recipe is the one description of **how a project's material is processed**. Everything else
writes it, runs it, records it, or carries it:

| Part | Its relation to the recipe |
|---|---|
| **Setup** (above) | **Writes** it: the purpose picks the steps; the answers and model cards pick the models by rule; the bake-off confirms them. |
| **Activity and automatic work** (`ui/activity-and-automatic-work.md`, #5352) | **Runs** it: new material goes through the resolved recipe's automatic steps as jobs; because each job declares what it takes and gives, a correction re-queues exactly the later steps that depend on it (#5360, #5361). |
| **The archive format** (`source-model.md`) | **Records** it: every pass, segment, reading and claim a step makes names the recipe and version that ran it, beside its maker, model and run, and lands as new work, never over a person's. |
| **Export** (`formats-and-training.md`, `export/exporter.md`) | **Carries** it: an export package can include the recipe that made it, in the same RO-Crate. |
| **The synced folder** (`synced-folder.md`) | Is an **output step's** destination, kept current as the work changes, and can work both ways. |
| **IIIF** (`iiif.md`) | Runs **on** IIIF pages kept by reference; results leave **as** IIIF annotations. A shared recipe's measurement pages can be IIIF links to public pages. |
| **Fine-tuning** (`compute/distillation.md`, `compute/jobs-and-fine-tuning.md`) | Is **a step and a version**: a `train-a-model` step runs where the recipe says; the trained student's card is pinned into the project's next recipe version only where it clears the bar. A training job's "recipe file" (`compute.tune.lora`) is the settings of that step. |
| **Decipherment and connections across corpora** | Use the same folder format for **analysis recipes** (`undeciphered-scripts.md`). |
| **Sharing a library** (`transport/library-sharing.md`) | Everyone in a shared library works under its one recipe; jobs run on the host; every reading still names who or what made it. |
| **API keys** (`ai/ai-settings.md` (section K)) | A recipe names providers, **never keys**. |
| **Cataloguing** (#5365) | A recipe's profile can declare the project's **metadata fields** (typed, with controlled vocabularies, mapped to Dublin Core or ISAD(G) where one fits), inherited like language through the prototypes; a "describe for the catalogue" step proposes values. |
| **Image editing** (`ui/preview-image-editing.md`) | "Prepare the image" is a step that makes a new rendition; later steps read it, and every segment records which rendition its coordinates belong to. |

So the order of building is: the job registry with declared inputs and outputs; the recipe format
and the one job system that runs it; setup, which writes it; then export, IIIF, fine-tuning and
sharing attach to it rather than each inventing their own.

### 11. Running: the hand-off to Activity

Setup ends at **Start**, which is the project's **first yes** for automatic work
(`source.project.automatic-after-first-yes`). From then on the activity spec owns the running:

- **On add**, each new source goes through the resolved recipe's automatic steps, as jobs in the
  one Activity table, throttled like all background work.
- **On change**, whatever a correction touched is marked out of date and remade through the jobs'
  declared inputs, and a person's work is never overwritten (`activity.derived.*`).
- **One pause** (*Pause Background Work*) stops all of it; a hand run still runs.
- **What it makes counts as the record only as the project's rule allows**: in a strict project,
  machine work is a pass and readings to review; in a relaxed one the newest counts, and a
  person's reading always outranks a machine's. Who made it never changes.
- Model downloads the recipe needs are jobs too, so a multi-gigabyte download is visible.

### 12. Sharing recipes: publish, follow, update, override, fork (ruled 2026-10-01)

**Publish.** From the library's Inspector, **Export Recipe** writes the folder. **Publish
Recipe…** offers the community catalogue (a `fichero-recipes` repository on GitHub, one folder per
recipe, checked automatically on every submission: the schema, that pinned models still resolve,
that referenced prompts and workflows are present, that a licence is given), or Zenodo for a DOI.
Publishing is its own act, asked every time, and nothing of the project's pages leaves with it
unless the person adds sample pages, each listed before sending.

**Find.** Setup and the Inspector search the catalogue by script, language, period and purpose,
and show each recipe's measurements. Fichero checks the catalogue for updates to followed recipes
at most once a day, sending only the recipe ids; offline, nothing is offered and nothing breaks.

**One guided path to a good model, for any language and any step (maintainer's direction, 2026-10-06).** It is the same for every model a recipe runs — readers, names (spaCy, #5536), layout (YOLO, #5525), vision models (LoRA): distil from a strong teacher (Gemini or whatever is best), check the teacher's output, fine-tune locally or on Hugging Face, measure, use. For readers: The
app decides among Kraken readers, Hugging Face models run on this Mac, and cloud models; it does
not stop at "no reader fits". For a project's scripts and languages it walks the person through one
path, each step a job they can watch and stop:
1. **Find** every candidate (installed, the Kraken repository, Hugging Face by tags, cloud) — #5519.
2. **Compare** them on the project's own corrected pages: error, time per page, cost for the volume,
   local or cloud, with the not-read rule (#5531) — #5533.
3. **If none is good enough, teach one:** a strong reader reads the lines as teacher, the
   teacher-line check removes lines it misread (#5446), a local reader is fine-tuned (Hugging Face or
   this Mac) and measured on the same pages — #5526, #5527, #5444.
4. **Use the winner** with the person's yes, and keep measuring as corrections arrive.
Proved by hand on 2026-10-05/06 (Mosquera notebooks): the check removed 34% of Gemini's teacher lines
(about 700 read the line above); fine-tuning cut McCATMuS from 40.4% to 19.6% and PP-OCRv6 from 24.6%
to 18.4% on ten checked pages, for about $1.15. Each hand step that night is a gap the issues close.

**Finding models beyond the shipped cards (maintainer's direction 2026-10-05: less hardcoded;
look models up; design proposed, #5519).** The shipped cards are a seed, not the list. For a
project's scripts, languages, material and period, discovery gathers candidates for each job from:
1. **What is installed** on this engine (Kraken readers, MLX vision models, spaCy pipelines, YOLO
   weights), each given a card made from its own metadata when none ships (`made_from: metadata`),
   so an installed model is never invisible to the rules.
2. **The Kraken model repository** (HTRMoPo on Zenodo, the one `ketos list` reads), by script and
   language tags.
3. **Hugging Face**, by task and by language and script tags (image-to-text, token-classification,
   object-detection for layout), never by keyword; a GGUF chat model is not a reader.
4. **spaCy's published pipelines** and the named community ones (LatinCy, greCy), by language.
Each candidate becomes a card that says where it came from, its licence, size, what it claims to
cover and what was measured; the same rules rank it; it is offered for download through the one
model path; and it can enter the bake-off like any other. Rules stay data: no candidate is named
in code. Offline, discovery offers only what is installed. A "no model fits" problem names what
was searched and the nearest candidates, and offers Train a Model where none exists.
Known gaps that discovery must close (corpus run 2026-10-06, #5519): Fraktur (UB Mannheim, Tesseract
`frk`), Japanese (NDLOCR), traditional Chinese (PaddleOCR `chinese_cht`), Hebrew (BiblIA Kraken),
Syriac (eScriptorium, Calamari), Latin and Ancient Greek spaCy (LatinCy, greCy).

**Training layout models (YOLO) and tables (proposed, maintainer 2026-10-05, #5525).**
Fichero reads and writes YOLO labels today (`formats/yolo.py`) but has no YOLO training. The
proposal: a `train-a-model` kind for layout, using the same training set builder as Kraken (pages
with person-made regions, or imported PAGE regions marked as ground truth, #5513) exported as YOLO
labels, trained on Hugging Face Jobs (private bucket, as Kraken) or on this Mac gently, coming home
as a layout card measured in the bake-off by region overlap. Tables follow the same path with
table and cell regions (corpus: USS Albatross logbooks, Reichsanzeiger, Paris notaries' forms).

**Follow and update.** A project that takes a published recipe **follows** it at a version. When
a new version appears, the Inspector says an update is available and shows exactly what would
change, step by step: steps added and removed, a model's old and new pin, a prompt's text
difference, settings changed, and the new version's published measurements beside the old. Where
the changed steps run on this Mac and the project has ground truth, Fichero **measures the new
version on the project's own pages** in the background and shows that too. Taking it is the
person's choice. A taken update changes **new work**; running the changed steps over existing
pages is offered as one job with its page count and estimate, and its output arrives as new passes
and readings.

**Overrides are kept.** A project can change anything in the recipe it follows: a prompt, a model
for one step, a setting, an extra step, a removed step. Those are stored as **overrides on top of**
the followed version, like values set lower in the cascade (the prototype system: the followed
version is the parent, the project's overrides its own values). An update replaces only what the
project did not override. Where the author changed something the project also changed, the update
lists that step with both versions, and the project's own is kept unless the person takes the
author's.

**Fork.** A project can **fork** a recipe (make it its own, no longer following) and publish the
fork, which names the recipe and version it came from and credits its authors.

### 13. When things go wrong

| Situation | What the person sees | What runs |
|---|---|---|
| A model download fails | The download job in Activity says why ("connection lost at 1.2 of 3.1 GB"); it is retried three times with back-off, then the steps that need the model wait with "Model download failed" and **Retry** or **Use the next candidate** (the bake-off's runner-up, or the rule's next) | Every step that does not need that model |
| A cloud step has no key | At the check: "Step *correct* needs a key for Anthropic". At run time the step waits with "Needs a key for Anthropic", and **Add Key…** opens Settings. Choosing a local candidate instead is an explicit change, kept as an override | The other steps; never another model in its place |
| A cloud step in a project whose pages may not leave | The check says the step is refused and why; the Inspector offers the best local candidate or **Allow for this provider** | The other steps |
| The first cloud call | Asked once per provider per project: what is sent (page images, or text), to whom, how many pages, the estimated cost; **Allow** or **Keep on this Mac** | Nothing for that step until answered |
| No model fits a step | "No reader is known for this script", the step marked **needs a model**, and the hand-transcribe, draft-and-correct and train-your-own routes | Steps that do not depend on it |
| The bake-off is skipped | Each step shows "not measured on this project"; the bake-off is offered once 100 corrected lines on two pages exist | The rule-ranked recommendation |
| Not enough ground truth | "Needs 64 more corrected lines" | The recommendation |
| A recipe names a job this Fichero lacks | "This recipe needs *trace a drawing*, added in Fichero 1.6. Update Fichero, or take it without that step." Taking it without records an override "step removed: job not available" | The other steps |
| A newer schema version | "This recipe needs a newer Fichero (recipe format 2)"; nothing is taken | Nothing |
| A pinned model no longer exists | The check names the step and the missing pin, and offers the rule's next candidate | The other steps |
| This Mac cannot run a pinned model | The first `alternatives` entry that can is used and shown; with none, as "no model fits" | As left |
| A `cluster` step with no bound target | "No cluster is set up"; **Add a Place to Run…** opens the compute settings | Everything else; train steps are never automatic anyway |

### 14. Journeys, end to end, and the real projects they are tested against

**The real projects** (2026-10-01). Onboarding and the recipes are tested against these, the
maintainer's own corpora; the journeys above are their shape, and each is checked on its real
pages before a behaviour is tagged [OK]:

| Project | Material | What the recipe must handle |
|---|---|---|
| **Jesuit letters** (the flagship) | 18th- and 19th-century Spanish letters by Jesuits, handwritten | Spanish hands of two centuries; the flagship recipe, measured on the corrected letters; entities and statements for the correspondence network |
| **1740 slave sale records** | Spanish colonial sale records of enslaved people, 1740 | formulaic notarial structure (who sold whom to whom, for how much): statements with transfer verbs checked; dates and places; people named with care |
| **Istmina archive** | Istmina (Chocó, Colombia), 1870s to 1980s: heavily damaged and faded, many hands and kinds of writing | image preparation first (contrast, deskew); readers measured per hand and per decade; honest "illegible" and damage marks; a mix of print, typescript and manuscript |
| **The Marshall diary** | one hand, handwritten diary | the clearest case for **fine-tuning Kraken** on the person's own corrections: one hand, many pages |
| **Colombian maps** | Spanish colonial-period maps of Colombia, handwritten labels | the map recipe: regions and labels, place names linked to a gazetteer, georeferencing |

Libraries for several of these exist on the maintainer's Macs (Istmina, the Marshall diaries,
Black Pacific); a recipe is measured on them through the running app's engine, never by reading
the library files directly.

**Choosing the embedding model for search** (2026-10-01). Like every step it is chosen by the
rules, starts cheap and local, and is one A/B away from an alternative:
- The rules take the project's languages and scripts and pick the smallest local multilingual
  embedder whose card covers them all (a small or base multilingual E5 for most projects; BGE-M3,
  2.3 GB, when the project mixes many languages or has long documents, and only on a Mac that
  holds it).
- The A/B for embeddings is a search test: the person types a few questions they actually ask of
  their material, and sees each model's top results side by side; the one that finds what they
  meant wins. With no questions yet, the rules' choice stands.
- Changing the embedder re-embeds the project as one background job with its estimate.

**Every step has an Advanced section.** The defaults come from the rules, and the setup and the
Inspector show each step in plain words; an **Advanced** disclosure on every step shows and lets
a person change its model, settings and prompt, with the A/B one click away. Nothing in Advanced is
needed for the common paths.

**Mixed material in one project** (2026-10-01). A real project rarely holds one kind of thing.
A database on the Jesuits holds handwritten letters, printed books, maps and more, often in the
same folders. So a project can follow **several recipes at once**, routed by material:

- By **place**: a folder follows its own recipe (`source.recipe.per-folder`).
- By **kind**, where folders are mixed: a cheap first step, **sort by material**, tags each page
  (handwritten, printed, typescript, map, drawing, photograph) from the image itself (a small local
  classifier or a quick look by a local vision model), and each kind follows the recipe the project
  names for it: Kraken and the letters' reader for handwriting, Tesseract for print, the map
  recipe for maps. A person can correct a page's kind, and the correction is kept and re-routes the
  page.
- The setup form asks what kinds of material the project holds, and proposes one recipe per kind;
  the sample pages' sorting shows the proportions.

**(a) A historian of historical Spanish letters**, with a folder of 3,000 page
images on an 8 GB MacBook Air and forty pages already corrected in an earlier tool (exported as
PAGE XML).

1. **What are you doing?** The full knowledge graph.
2. **Your material.** The folder; corrected transcriptions: the PAGE folder. Fichero shows ten
   sample pages and imports the forty corrected pages as ground truth.
3. **What it is.** Pre-filled from the samples and confirmed: Latin script; Spanish (plus Latin,
   added by search, for formulae); handwriting, 1550–1600; one column with margins. Pages may
   leave this Mac: not asked, because no step uses the cloud. Shown, not asked: left to right,
   on the baseline, Junicode, "8 GB, Apple M2".
4. **How it will be done.** The flagship `spanish-hands` 1.2.0 fits and is proposed to follow.
   The 7B corrector cannot run in 8 GB, so its 3B alternative is used, and said. Downloads: about
   2.6 GB, all open licences. The `train-reader` step shows "offered after 2,000 corrected lines;
   no cluster set up".
5. **Check on your pages.** The rules propose two line finders (Kraken's default, and the
   flagship's tuned segmenter) and three readers (the flagship's Kraken reader, another Kraken
   reader, Tesseract's Spanish data as the baseline): six combinations, run on the forty pages in
   Activity (about twenty minutes). The flagship's pair wins at CER 7.4% against 9.8% for the
   next and 31% for Tesseract on this hand, all local, free and trainable; the table shows each
   one's pages per hour and carbon estimate. The person confirms; the recipe records the pair.
6. **Ready.** "3,000 pages will be split where needed, lined, read, corrected where unsure,
   searched, and mined for people, places, dates and statements: about 30 hours of background
   work on this Mac, $0. (Reading in the cloud instead: not allowed in this project.)" **Start.**

Then: the work grinds through Activity over days, pausing on battery. The historian corrects a
line; its page's entities, claims and vectors are remade (activity spec). They change the
correction prompt to keep a notary's abbreviations as written: an override. Version 1.3.0 of the
flagship is published with a new reader; the Inspector shows the diff, the published CER, and
"on your pages: 6.2% against 7.4%"; the prompt conflict is listed and theirs is kept. They take
it; re-running the reader over the 3,000 pages is offered as one job. On a few pages of a
different notary, they use **Try Another Option…** to compare the corrector's prompt against
their own; theirs wins there, and **Use This** for that folder only records a folder override.
Later they export the recipe with their measurements, so a colleague starts from it.

**(b) An invented case: a researcher in Cherokee** (no such project exists; it stands for a language and script no shipped recipe covers), on a 16 GB Mac, with two folders: printed issues of a
newspaper in the syllabary (about 400 pages) and handwritten letters (about 900 pages). There are
no corrected pages.

1. **What are you doing?** Just transcribe.
2. **Your material.** Both folders; no corrected transcriptions. Counted: about 1,300 pages.
3. **What it is.** No local model is installed to suggest, so the fields start empty. Script:
   "Cherokee" found by search (`Cher`); language: Cherokee (`chr`); print and handwriting,
   1820–1900; columns (the newspaper), one column (the letters). Shown: left to right, on the
   baseline, Noto Sans Cherokee (shipped).
4. **How it will be done.** No published recipe fits, so one is generated, and because the
   folders differ in material it proposes the print folder its own reading step. Find lines:
   Kraken's default segmenter, whose card does not name the script, marked "not measured on this
   script". **Printed folder**: if Tesseract has Cherokee data (unverified, 8c), it passes on
   coverage and is the reader, its small download shown; if not, the printed folder is "needs a
   model" too, and the paragraph below starts from the printed pages, which are quicker to
   correct. **Letters**: no reader passes (no card made for Cherokee handwriting; Tesseract is
   never proposed for handwriting; Apple Vision's run-time list lacks Cherokee). Correct: left
   out, because no language model's card lists Cherokee. Whether
   pages may leave is asked now, because a cloud vision model could draft letters for correction;
   the researcher answers no (the community's material stays here), and the recipe is assembled
   again without it. Each step's explanation shows a line Kraken found on one of their own pages.
5. **Check on your pages.** Nothing to measure yet; skipped. The Inspector will offer it once
   100 lines are corrected.
6. **Ready.** "400 printed pages will be lined and read by Tesseract: about 20 minutes on this
   Mac, $0. 900 letters will be lined; reading them needs a model: transcribe by hand, and Fichero
   will offer to train one after about 1,000 corrected lines." **Start.**

Then: the newspaper is read in minutes and the researcher corrects a few columns; once 100 lines
are corrected the bake-off is offered there and measures Tesseract on them. The letters are lined
automatically; the researcher checks the lines and transcribes in the Source view with the
syllabary's font and keyboard. At the threshold the train step is offered: a Kraken reader trains on this 16 GB Mac,
throttled (`compute/jobs-and-fine-tuning.md`, `compute.tune.on-this-mac`), or on Hugging Face Jobs
or a cluster if the project allows pages to leave the Mac; a Kraken reader fine-tuned from the corrected letters (with the
corrected newspaper lines as extra data, marked as print) comes back as a card, is measured on
held-out letters, and is pinned into the letters folder's next recipe version only where it
clears the bar. The researcher can publish the recipe and, if the community agrees, the model, so
the next Cherokee project starts from both.

### 15. Finding a better model

From a project's Inspector, or from the AI settings, a researcher can **look for models that
suit**: by job, script, language, period and whether it must run locally. Fichero searches the
places the field keeps them and shows results **as cards**, with licence class, size and whether
this Mac can run them: Kraken's repository on Zenodo through the `htrmopo` library; Hugging Face
by task, language and licence (`image-to-text` for readers; `library=peft` for fine-tuned
adapters, shown with their base model and training data); Tesseract's language data; Whisper's
and other speech models' language lists; HTR-United for training sets, on the train-your-own
path; and an open list that can grow. Specialist pipelines found outside these (a cuneiform sign
detector published as code and weights) are shown as cards marked "not runnable in Fichero yet"
until a registered job can run them.

- **Open** models (permissive, or copyleft compatible with Fichero's own AGPL) are downloaded when
  asked for; nothing copyleft is bundled (ruled). Others (non-commercial, gated, special terms, a
  revenue cap) say so plainly and need a deliberate choice; some cannot be redistributed and the
  card says why.
- A model's **citation is shown** wherever its work is shown, and goes into exports.
- A downloaded model becomes a row under its provider in the AI settings, like any other.
- A model can be **tried on a few pages** and measured against ground truth before it becomes a
  step's model (Try Another Option…, section 8a).

### 16. The Reader shows anything; language tools are honest

The Reader lays out any script in its direction, uses the font a reading needs, shows declared
signs as their pictures, and keeps glosses and notes in their places (`languages-scripts-signs.md`).
There is **one** Reader renderer; today there are two, and neither does this.

A word-tagger or name-finder runs only for a language it was made for. Where none exists, Fichero
says so, and offers what does work for any language (search, vectors, a language model if the
project allows one). It never quietly runs the English pipeline over another language.

### 17. The synced folder

Specified in its own file, `synced-folder.md`: watching a folder, matching files, bringing
outside edits in, keeping outputs current. It belongs half to the exporter and half to the
importer; in a recipe it is the destination of an output step.

## Behaviors (each with its state tag; each cites its issue on milestone `source-model`, 322)

Model cards
- `source.model.one-card` — **[GAP]** (#4948) every usable model (cloud, local, Apple Vision, Kraken,
  layout, spaCy, embedding, speech) is returned by one catalogue route in one card shape with the
  same fields.
- `source.model.card-is-the-catalogue` — **[GAP]** (#4948) cards are the contents of the single
  catalogue; the shared picker and role defaults read them; no second catalogue exists.
- `source.model.jobs-typed` — **[GAP]** (#4948) a card names its jobs from the registry, each with
  what it takes and gives in source-model terms.
- `source.model.suits` — **[GAP]** (#4948) a card states scripts (ISO 15924), languages (BCP 47),
  period, material, direction and line position; a fact proposed by a language model is marked
  unconfirmed until a person confirms it, and the recipe rules ignore unconfirmed facts.
- `source.model.licence-class` — **[GAP]** (#4948) a card carries a licence and a licence class;
  only open models (permissive, or compatible copyleft) download without a further deliberate step.

Moved from `ai/local-runtimes.md` on 2026-10-04 (the card has one home). Each refines a card behaviour above under the same issue: `card-id` is `one-card`'s identity, `jobs-replace-capabilities` is `jobs-typed`'s rule, `licence-filled` is `licence-class` for Fichero's own catalogue.

- `source.model.card-id` — **[GAP]** (#4948) every card has one id `<runtime>:<source>@<version>`
  as section 1 sets out; recipes, role defaults, runtime configurations, the making record and
  jobs store it; no surface stores a bare model name. Today there are five schemes (MLX repo+SHA,
  Whisper repo+revision, Kraken DOI, an embedding "space contract", bare cloud strings) and a
  sixth reference, `$profile:`.
- `source.model.cloud-pin-is-honest` — **[GAP]** (#4948) a cloud card pins the provider's dated id
  where one exists; an alias is `pinnable: false`, a recipe step naming it is marked as able to
  change, and each reading records the dated id the provider returned.
- `source.model.weights-verified` — **[GAP]** (#4948) a downloaded model is checked against its
  card's files and checksums before it is installed; a partial download is never installed. Today
  Kraken loads the newest `.mlmodel` in a folder with no checksum and Whisper's `is_installed`
  checks only that a folder exists (`llm/whisper_runtime.py:179`).
- `source.model.embedding-space-has-revision` — **[GAP]** (#4948) the embedding card id includes the
  weights' revision and the vector-space key includes the card id, so a weights update is a new
  space. Today bge-m3 has no revision pinned (`db/embeddings.py`).
- `source.model.runs-here` — **[GAP]** (#4948, #5367) a card states its runtime, whether that
  runtime is bundled, OS or unavailable in this build, its measured resident memory (or a labelled
  estimate), its processor, and whether this Mac can run it now; "supported" is never derived from
  an environment default (today `FICHERO_SUBPROCESS_CAPABLE` defaults to `"1"`,
  `llm/local_inference.py:287`). The activity spec's co-run rule reads these numbers.
- `source.model.licence-filled` — **[GAP]** (#4948) every card in Fichero's own catalogue has a real
  licence and licence class; "user-managed" is only for a model the person added by hand. Today
  every managed model but blla and bge-m3 says "user-managed" *(review)*.
- `source.model.jobs-replace-capabilities` — **[GAP]** (#4948) a card's jobs replace the capability
  words and name-sniffing; "recognition-only" (reads a page, takes no prompt) is a job fact, not a
  hard-coded list.
- `source.model.citation-shown` — **[GAP]** (#4948) a model's citation appears wherever its work is
  shown and in exports.
- `source.model.measured-here` — **[GAP]** (#4948) a card shows this project's own measurements of
  the model (error per hand and page kind, lines, date), or "not measured on this project".
- `source.model.reaches-cli-by-generation` — **[GAP]** (#4948) a card route reaches the command line
  through the generated client; no model command is hand-written.
- `source.model.ranking-facts` — **[GAP]** (#4948) a card carries speed (measured on this Mac or
  published, marked as an estimate), price per page for a cloud model, an energy estimate per page
  labelled as an estimate or "unknown", and whether and how it can be trained.
- `source.model.coverage-two-ways` — **[GAP]** (#4948) a card states its coverage of a script: the
  LOOVE tokenizer tiers for a language or vision-language model, the share of the script's
  exemplar characters in its character set for Kraken or Tesseract, or "unknown".
- `source.recipe.text-material-is-not-read` — **[GAP]** (#5553) material that is already text (Markdown,
  plain text, Word, a PDF with a text layer, notes from Tinderbox, DEVONthink or Bookends) gets no reading
  step: the plan goes straight to search and whatever else was ticked, and Ready says the notes are already
  text. A project whose purpose is finding related material asks for no transcription. Scans of printed or
  typed pages are read by Tesseract first; Kraken or a vision model is offered only when the check on a few
  pages shows Tesseract misses.
- `source.model.tesseract-provider` — **[GAP]** (#4948) Tesseract is a provider row in the AI
  settings: its binary is built into the app, each language's data is downloaded on demand as
  data with a card of its own, and it can read whole pages or cut lines.
- `source.model.period-confirmed-not-guessed` — **[GAP]** (#4948, #4951) a card's period comes from
  the HTR-United record of its named training set, or from a language model's reading of its prose
  confirmed by a person; until then it is unknown, and an unknown period neither raises nor lowers
  a candidate.
- `source.model.line-or-page-from-architecture` — **[GAP]** (#4948) where a card does not say
  whether a reader reads lines or pages, it is worked out from the architecture (CTC readers read
  lines; vision-language models read pages), shown as worked out, and correctable.
- `source.find.zenodo-through-htrmopo` — **[GAP]** (#4948) Kraken's Zenodo repository is searched
  through the `htrmopo` library, which reads each record's card (model type, script, language,
  CER, licence), never through Zenodo's plain search alone.
- `source.find.adapters-as-a-tier` — **[GAP]** (#4948) the search finds fine-tuned adapters (Hugging
  Face `library=peft`) as their own tier, each shown with its base model and training data.

Jobs and chains
- `source.recipe.jobs-are-a-registry` — **[PARTIAL]** (#4949, #5364) **Built 2026-10-03 (engine):** the registry with typed takes and gives, layers, A/B comparison and descriptions (`recipes/jobs.py`); not yet read by setup or the activity queue; pinned by `fichero-server/tests/unit/recipes/test_job_registry.py`. jobs and export formats are
  registered by name with what they take, give, accept as settings, their layer and the Fichero
  version that added them; a newly registered one is available to recipes, setup, the activity
  queue and the recipe check with no other change; a recipe naming a job this copy lacks is
  refused before anything runs, naming the job and the version that has it.
- `source.recipe.jobs-carry-descriptions` — **[GAP]** (#4949) every registered job carries a plain
  description, an example and the trade-offs between its usual options, and declares how its
  outputs are compared; setup, the Inspector and an exported recipe's README show that same text.
- `source.job.find-and-identify-signs` — **[GAP]** (#4949) finding signs and identifying them
  against a sign list are jobs a recipe can name, used in place of finding lines and reading a
  line for scripts read sign by sign.
- `source.job.refine-shapes` — **[GAP]** (#4949) refining a pass's shapes with another model (a
  detector tightening a vision model's boxes) is a job that makes a new pass and keeps the first.
- `source.job.prepare-the-image` — **[GAP]** (#4949) preparing an image (crop, deskew, rotate,
  dewarp, adjust) is a job that makes a new rendition and never changes the original; later steps
  and segments name the rendition they used.
- `source.job.split-pages` — **[PARTIAL]** (#4949, #5382) *Built: the `split_pages` tool (51dbbfa93) cuts an open notebook at its gutter inside Apple Vision's outline and never a closed cover, pinned by `fichero-server/tests/unit/workflows/test_split_pages.py`; a recipe runs it as the `Split Pages` workflow (#5390), its pages then read by the steps after it, pinned by `fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py`.* splitting a spread or a strip of frames into ordered
  pages is a job a recipe can name.
- `source.job.tie-text-to-lines` — **[PARTIAL]** (#5444, #5487) *Built (2026-10-05, reworked 2026-10-06 to
  the one-line-pass ruling, #5467): `POST /api/check/runs` with `check: tie-text-to-lines` (provider
  `kraken`, a Kraken reader; `pass_model` keeps only that model's lines) queues a `tie-text-to-lines` job on
  the local model lane; `checking/tie_text.py` takes the page's best reading (`page_reading`: a person's,
  then one marked reviewed or confirmed by a person's verdict, then the newest model transcription; never a
  flagged read, never a reading that is the lines' own text, i.e. a reader's words already written onto
  the lines or Kraken's own read), takes the page's own lines (`llm/working_lines.py`, the working pass;
  a page with none has them found by Kraken first, regions kept as the lines' parents, counted
  `lines_found`), reads each line roughly through `kraken_runtime.read_given_lines`, aligns the page
  reading to those rough reads in one monotonic character alignment (accent-, case- and space-blind; a
  cut inside a word moves to the nearest space), and writes each line's stretch as a reading ON THAT LINE
  (`representation.create`, derived from the page reading's artifact, whose provider and model name the
  reader), all through audited, undoable actions under the job's run, so every row is `workflow`, never
  `human`; no second pass is made. A line given no stretch stays untied and is counted (`untied`). A line
  whose stretch agrees with its own rough read (1 − accent-blind CER) below the threshold keeps the
  stretch and is rejected (`check.verdict`, trust `model`, "doubtful: page text and line disagree" with its
  score), so the training set leaves it out until a person confirms it; the training set finds the
  teacher's readings on the page's lines (`training/kraken_set.teacher_pass`). A page whose lines already
  carry that page reading is not tied again; `GET /api/check/runs/{id}` gives the counts and each doubtful
  line. Which reading of a line counts is the counting rule's (`resolve_counting`, ranking machine readings
  by `source.reading.machine-ranked-by-measure`, #5558): a checked reading, then the better reader measured
  on this project, then the newest; so a rough Kraken re-read made after the tie does not displace a tied
  stretch whose page reading a person checked, or whose reader measured better here, and the training set
  carries the teacher's reading because it counts. A recipe card runs it (`recipes/start.py`: a `check`
  card with `check: tie-text-to-lines` and the step's Kraken reader, which the three Kraken reader cards
  offer), and since 2026-10-06 (#5558) it runs without one: a page reading saved through the one artifact
  save (`llm_base._save_artifact_sync`: a transcription with no lines of its own, not flagged, not the
  lines' own text) on a page that has lines queues one waiting tie job for that page
  (`tie_text.after_page_reading`, started by `automatic`, on the local model lane, never run inline),
  read with the project recipe's Kraken reader, else the first catalogue reader on this Mac; a page
  without lines, or a Mac with no Kraken reader, queues none. Default taken 2026-10-05 (design lead),
  awaiting the maintainer's ruling: the match threshold is 0.30, the line check's own-score floor. Tested
  in `fichero-server/tests/unit/check/test_tie_text_to_lines.py`,
  `fichero-server/tests/unit/check/test_which_reading_counts_after_the_tie.py` and
  `fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py`. Not built: the cluster reader
  (`remote_read/runner.py`) still drops Kraken's regions, and a whole-PDF Kraken read without per-page
  fan-out still makes its own pass; older projects' "Page reading tied to Kraken's lines" passes stay as
  they are (no migration; folding them into the page's lines waits on #5222's conversion rules); a cloud
  reader is never measured, so a cloud tie that nobody checked still gives way to a newer re-read (the
  evaluation has no remote target, #5533).* a page's reading is tied to its lines for free, on
  this Mac: Kraken finds the lines, a Kraken reader reads each roughly, and the page's best reading is
  aligned to them in order by the characters they share (a monotonic alignment; no line takes text
  from beyond its neighbours'). Each line gets the stretch of the page reading it matches, automatically,
  wherever the alignment scores above the match threshold (ruled 2026-10-04); a line whose alignment
  is doubtful is flagged for review and counted, and stays out of the training set until a person
  checks it. The
  lines keep Kraken's shapes (the page's own pass) and each reading names the page reading's model for the
  text; no second pass is made. The page's best
  reading is, in order: a person's checked reading, a checked model reading, then the newest model page
  reading. After alignment the line's counting reading is its aligned stretch; an earlier machine
  reading of the same line (Apple Vision's OCR, a stock Kraken read) stays as history and never counts
  while a better reading of the line exists. On Mosquera this is 319 of 374 pages, whose only shaped
  lines are Apple Vision's (C01_030: `WtrtNI-`, `¥eTIQ`) or stock Kraken's.
- `source.lines.read-the-marked-line` — **[BROKEN]** (#5445) a vision model reading Kraken's lines is shown
  the target line alone: the crop is cut to the line's own polygon with the outside masked (or the
  target is marked), never a crop in which a neighbouring line is more complete than the target. Today
  `llm/line_reader.crop_line` shows about two and a half lines with the target unmarked, and on
  SM_NPQ_C01_005 lines 4–19 hold the text of the line above; a check of the exported training set
  flags a quarter of a two-photo trial as shifted.
- `source.lines.reading-checked-against-the-page` — **[PARTIAL]** (#5446) *Built (2026-10-05): `POST /api/check/runs` with `check: line-against-page` (provider `kraken`, a Kraken reader) queues a `check-lines` job on the local model lane; `checking/line_check.py` reads each line of the pass again through `kraken_runtime.read_given_lines`, scores the reading (1 − accent-blind CER) against its own rough read and up to two same-column lines either side, and rejects (`check.verdict`, trust `model`, the scores in its reasons) a reading closer to a neighbour (beaten by 0.15 and itself at least 0.40) or below 0.30; passing lines get no verdict, and a line a person has checked is not checked again; `GET /api/check/runs/{id}` gives the counts and each flagged line with its scores. Empty and `null` readings are left out by the training set's own rule. Tested in `fichero-server/tests/unit/check/test_line_against_page.py`. Shown in the app (2026-10-05): `FlaggedLineStore` reads the reading verdicts and each run that rejected a line on the page; a line whose reading's newest verdict is still the run's reject carries a flag mark in the Order list (the Segments pane's list), the strip and the grid, with its flag and scores in words on hover ("Teacher text matches the next line better (0.52 vs 0.21)"), the Segments pane's head counts the page's flagged lines, and the Inspector says the flag, the run's counts and offers Confirm Reading (a person's `check.verdict` confirm on the rejected reading, which clears the mark in place); tested in `fichero/Tests/Unit/general/Models/FlaggedLineStoreTests.swift`. Not built: a null or empty line shown as flagged (the training set leaves it out by its own rule, unmarked).* each model reading of a Kraken line
  is scored against that line's own rough Kraken read and its neighbours' (the characters they share);
  a reading that matches a neighbour clearly better than its own line, a null or empty reading, and one
  below a set score are flagged, with the scores, so a person can look. A flagged line keeps its
  reading as a proposal, is shown as flagged, and is kept out of a training set
  (`compute.tune.set-excludes-flagged-lines`).
- `source.lines.null-is-no-text` — **[BROKEN]** (#5447) a model's null answer for a line, or the word
  `null` alone, stores no text: the line has no reading from that model. Today the word is kept as the
  line's text (SM_NPQ_C01_005, lines 42–43) and reaches the Order tab, exports and training sets.
- `source.split.carries-readings-over` — **[GAP]** (#5452; ruled 2026-10-04 as the rule for whenever a
  split runs, not a build priority) splitting a spread moves each of its line segments, with every
  pass's readings, to the half its polygon falls in, re-normalised to that half's region; a line that
  crosses the gutter is flagged, never cut. The spread keeps its passes as history, nothing is read
  again or paid for, and the halves count as the pages with their carried passes, so "already done"
  sees the work. Today the split only makes the halves (`persist_workflow_child_regions`): a spread
  split after its lines were read leaves them on the spread, which stops counting, and a recipe run
  would read every half again with a paid model.
- `source.recipe.apple-finds-lines-on-handwriting` — **[GAP]** (#5451; ruled 2026-10-04) when a page's
  hand is not print (decided from the derived script and hand, `source.onboard.*`), a recipe runs Apple
  Vision for its line finding only: its text is not kept as a reading. Apple's OCR of handwriting is
  noise (Mosquera SM_NPQ_C01_030: `WtrtNI-`, `¥eTIQ`), and every Mosquera page carries such a pass
  today.
- `source.job.check` — **[PARTIAL]** (#5404) *Built: `check` is in the job registry (`recipes/jobs.py`), its layer a setting, so a recipe can name it after any layer; pinned by `fichero-server/tests/unit/recipes/test_job_registry.py`. Not built: a tool that runs it and stores each verdict at the checker's trust level.* checking a layer's proposals (readings, names, statements, links) is a job a recipe can name, run by a person or a checker model; each verdict (confirm, correct, reject) keeps its reasons and the checker's trust level, a model's check is never recorded as a person's, and a corrected proposal names the one it replaces.
- `source.job.find-statements` — **[GAP]** (#4949) finding statements (subject, relation, object),
  each naming the stretch of text it came from, is a job a recipe can name.
- `source.job.describe-for-catalogue` — **[GAP]** (#5365) a step can propose values for the
  project's metadata fields from a page or document, for a person to confirm.
- `source.chain.is-a-workflow` — **[GAP]** (#4949) a chain is a workflow; the second chaining
  mechanism that ships today (`execution/chaining.py`) is folded into the workflow graph and retired.
- `source.chain.checked-before-run` — **[PARTIAL]** (#4949) a chain whose steps do not fit (what one
  gives is not what the next takes) is refused before it runs, naming the step and the missing input.
  A job may take one of several kinds: finding names, finding statements, checking and exporting take
  readings of the lines **or** a reading of the whole page, so a recipe that reads whole pages passes;
  one that gives neither is refused, naming both. **Built 2026-10-04 (recipes):** `unmet_inputs`
  (`recipes/jobs.py`), a `takes` entry `line_readings|page_reading` met by either; pinned by
  `fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py`. Chains (workflows) are not yet
  checked this way.
- `source.chain.segments-to-any-reader` — **[GAP]** (#4949) one general step cuts each segment's
  picture and hands it to any model that can do the next job, writing readings back on the same
  segments; `economy_htr`, `align_transcript`, `merge_geometry` and Kraken's segment-and-read are
  retired into it; any finder can feed any reader through it (Kraken lines read by Tesseract,
  Apple Vision or a vision-language model).
- `source.chain.jobs-without-models` — **[GAP]** (#4949) a chain can name jobs only, resolved
  against the project's recipe when run.
- `source.chain.bar-offers-project-default` — **[GAP]** (#4949) the workflow bar offers the
  project's recipe first, on the current selection, down to chosen segments.
- `source.chain.bar-offers-what-fits` — **[GAP]** (#4949) beside the project's recipe, the workflow
  bar offers the workflows the current selection can feed; there is no list of tools to hide.
- `source.chain.output-never-overwrites` — **[GAP]** (#4949) a chain's output is a new pass or new
  readings; no reading or pass a person made is changed.
- `source.resolve.one-cascade` — **[GAP]** (#4949) which model does a job, which language applies
  and which guideline holds are all answered by one engine resolver walking the one cascade;
  today's app-wide role defaults are its top level, not a separate system.
- `source.egress.one-gate` — **[GAP]** (#4949) whether content may leave this machine is decided in
  one place, where a model is called, reading the cascade (a project's rule, a segment's rights
  record); today's privacy check on model profiles becomes that gate.

The one egress home (ruled 2026-10-04). Moved here from `ai/local-runtimes.md`; `compute.leave.one-gate` (`compute/transfer-and-results.md`) is the remote-work sheet over this gate.

- `source.egress.every-call-site` — **[BROKEN]** (#5368) every model call goes through the gate;
  today `chat_with_tools` (`llm/__init__.py:2971`) and `structured_output` call
  `get_langchain_model` without it. A guardrail test lists every caller of the model factory.
- `source.egress.no-silent-cloud-fallback` — **[PARTIAL]** (#5368) no resolver falls back to a cloud
  model; it refuses, naming what to configure. Fixed for the chat route in 7feee5872 and pinned by
  `test_chat_never_falls_back_to_the_cloud.py`; the retrieval query compiler's library-database
  lookup is not yet re-checked *(review: `retrieval/query_compiler.py:148`)*.
- `source.egress.setting-is-reachable` — **[GAP]** (#5368, #4951) the project's egress rule is set
  in setup and the Inspector and is what `is_local_only()` reads; today it reads `local_only_ai`,
  which nothing writes.
- `source.egress.fichero-own-fetches-listed` — **[GAP]** (#5368) Fichero's own fetches (the weekly
  price list, Hub and Zenodo searches, tokenizers for language fit, model downloads) are listed in
  Settings, carry no library content, run as jobs, and stop when the person chooses to work
  offline.

How a result was made
- `source.making.recorded` — **[GAP]** (#4949) every pass and reading records run, step, model card
  and version, settings and prompt, inputs, and person-or-machine (set by the engine).
- `source.recipe.recorded-on-what-it-made` — **[GAP]** (#4949, #5364) every pass, segment, reading
  and claim a recipe step makes records the recipe id and version that ran it, beside its maker,
  model and run.
- `source.making.walkable` — **[GAP]** (#4949) the chain behind any reading can be walked back step
  by step to the image rendition it started from.
- `source.making.in-inspector` — **[GAP]** (#4949) the Inspector shows the selected segment's making
  as a readable chain.
- `source.making.same-everywhere` — **[GAP]** (#4949) the same making is returned over MCP and the
  command line, and shown for a run in the workflow bar and its Activity row.
- `source.making.compare-chains` — **[GAP]** (#4949) two chains' results on one page can be compared
  reading against reading and scored against ground truth.

Projects
- `source.project.has-settings` — **[GAP]** (#4951) a project (today's library) has settings of its
  own (purpose, recipe, defaults, rules, synced folders); one never set up behaves exactly as before.
- `source.project.in-the-cascade` — **[GAP]** (#4951) project settings sit between the app and a
  folder in the one cascade; a folder can override them; a shown value says which level it came from.
- `source.project.own-models` — **[GAP]** (#4951) two projects can use different models for the
  same job, and each run uses its own project's.
- `source.project.one-settings-window` — **[GAP]** (#4951) making a new project runs setup;
  afterwards its settings live in one place, the library's Inspector (ruled 2026-10-01); Project
  Settings… in the File menu and the context menu selects the library and opens that Inspector
  section; no separate settings window exists.
- `source.project.stays-local` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** Start refuses a cloud step, naming it, when setup's answers keep pages on this Mac; workflow runs started by hand do not check it yet; pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/api/test_start_is_the_first_yes.py`. a project whose pages may not leave this machine
  refuses every cloud step in it, naming the step and the rule.
- `source.project.record-rule` — **[GAP]** (#4951) a project is strict or relaxed about what counts
  as the record; a new project is strict; a recipe's profile can set either.
- `source.project.relaxed-never-changes-the-maker` — **[GAP]** (#4951) a relaxed project changes
  what counts as the record, never who made it: a machine's reading, pass or claim is stored and
  shown as a machine's in every project (the engine sets this; see → #4868, → #4869).
- `source.project.automatic-after-first-yes` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** `GET /api/recipes/project/start` shows what Start would run and on how many pages; `POST` records the first yes (`recipe/started.yaml`: when, recipe id and version), audited and undoable, refused while the plan has refusals (a recipe that fails the check, or nothing to run; a step it cannot run is skipped, #5390); and it runs the recipe (#5390, `source.recipe.start-runs-the-steps`); on-add after it is `source.onboard.just-do-it`; pinned by `fichero-server/tests/unit/api/test_start_is_the_first_yes.py` and `fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py`. nothing in a project runs by itself
  until the person presses Start at the end of setup (the first yes), which shows what will run,
  on how many pages, with an estimate; what it makes counts as the record only as the project's
  rule allows.
- `source.recipe.start-runs-the-steps` — **[OK]** (#5390, #5497, #5498; built: `recipes/runner.py`, the `run-a-recipe` job; tested in `fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py`, `fichero-server/tests/unit/recipes/test_recipe_runs_to_spec.py`) pressing Start runs the recipe over the
  project's material: its steps in order, each as the job its card names (a shipped workflow run for
  splitting pages (`Split Pages`), finding lines, reading a line (with a Kraken reader, or Kraken's lines
  read by a vision model: `Read Lines (Kraken lines, vision model)`) or a page, correcting, finding names
  (`Extract Entities`) and finding statements; a check
  run for `check`; the project's synced folder for `export`), together as one `run-a-recipe` job in
  Activity whose children are those runs; a step starts only when the one before it has finished.
  Each step declares what it takes and gives (its job's kinds); a step that fails stops only the steps
  that need what it would have given and no other earlier step gave, which say "not run" and why (names
  read the uncorrected lines when correcting fails; statements wait when names failed). A recipe finds
  each shipped workflow by the preset's stable key, never by a display name, and no ordering prefix
  ("2 · ") is part of a shipped workflow's name. Start's answer is the run it started: its `runs` and
  `workflows` are that run's, as `started.workflows` is.
- `source.recipe.failed-step-offered-again` — **[OK]** (#5498; built: `runner.unfinished_steps`, the plan's
  `last_run`/`last_why`; tested in `fichero-server/tests/unit/recipes/test_recipe_runs_to_spec.py`) a step the
  project's last finished run did not do (failed, or not run) stays in the Start plan, even beside a layer's
  proposed steps, marked with how it ended and why ("failed last time …; runs again"), and Start runs it
  again without naming it to redo.
- `source.recipe.run-status-is-activity` — **[OK]** (#5498; built: `runner.status`; tested as above) a recipe
  run's step states are its steps' own jobs, the rows Activity shows, so the run's status and Activity are one
  account; a run still waiting says what it waits for (recipe runs go one at a time).
- `source.recipe.step-skipped-says-why` — **[OK]** (#5390; built: `recipes/start.py` `skipped`; tested as above) a step Start cannot run (no model, a
  condition Start cannot honour yet, a cloud step in a project that keeps its pages on this Mac, a
  job no card runs yet) is skipped, and the plan and the recipe run name the step and why; the other
  steps still run. A recipe with nothing runnable, or one that fails the recipe check, never starts.

Profiles (the defaults section of a recipe)
- `source.recipe.missing-model-offered` — **[OK]** (#5367; built: `missing_models` in `recipes/start.py`, the plan's `downloads`; tested in `fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py`) a step pinned to a model that is not on this
  Mac and can be downloaded (today: a spaCy pipeline) is named in the Start plan with the model and its size,
  and the plan offers the download (`downloads`, each a `download-model` job on the network lane); Start is
  refused until it is there, so the step never fails at run time for want of it.
- `source.recipe.done-is-not-redone` — **[OK]** (#5390; built: `recipes/done.py`, the plan's `done`/`of`/`note` and Start's `redo`; tested in `fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py`) a started recipe does not run a step again on a
  page that already has its output: splitting, on a photograph already cut into pages; finding lines, on a page
  with a pass that has lines; reading lines, on a page with a pass read by the step's own model; reading a page, on
  a page with a transcription saved by the step's own model. The Start plan says,
  for each such step, "already done on N of M pages", and the run does only the rest, unless the person names
  the steps to redo when pressing Start. A step that cannot tell (names, statements, checks, export, publish)
  runs on every page, and the plan says so. The pages a step runs on are worked out when it starts, so pages a
  split made earlier in the same run are read like any others.
- `source.job.publish` — **[OK]** (#5390, #2535; built: the `publish` card in `recipes/start.py` and `recipes/runner.py`; tested in `fichero-server/tests/unit/recipes/test_publish_to_spec.py`) a recipe's `publish` step writes the project as a static
  website (an 11ty project that builds with `npx @11ty/eleventy` and deploys to Netlify) through the one
  site export (`export_service.export_eleventy_site`), into the folder its `where` setting names on the
  engine's disk, as a card of a started recipe; publishing again rewrites that site in place. A step that
  names no folder is skipped and says so. What the site shows of the checks is `source.check.on-the-site`.
- `source.profile.is-a-prototype` — **[GAP]** (#4951) a recipe's profile is stored as a prototype
  the project inherits from; the followed recipe is the parent, the project's overrides its own
  values; any value can be overridden and shows where it came from.
- `source.profile.shareable-file` — **[GAP]** (#4951) a profile travels as the `defaults` section of
  `recipe.yaml` (languages, scripts, period, direction, guideline, normalisation, record rule,
  fonts, metadata fields, views), never in a file of its own, and holds no sources or secrets.
- `source.profile.sets-up-the-project` — **[GAP]** (#4951) taking a recipe sets the project's
  defaults from its profile and offers to download the models its steps name, with sizes and
  licences.

Purposes and layers
- `source.onboard.purpose-first` — **[PARTIAL]** (#4951, #5478) **Built 2026-10-05 (engine):** the saved answers hold `purposes` as a list (a project saved with one `purpose` reads as a list of one, nothing lost; none ticked is `not-sure`), and `GET /api/recipes/purposes` offers the five new purposes; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** What it is for lists the engine's purposes as checkboxes (`RecipePurposeFields`), none ticked says Not sure yet, and the answers are saved and sent as `purposes` (a saved `purpose` reads as a list of one); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift` and `RecipeSetupStoreTests.swift`. *Not built: shown in the project's Inspector.* *Built 2026-10-03 (app + engine), as a single choice (replaced 2026-10-05): first run's Purpose step lists the engine's purposes (GET /api/recipes/purposes) before material; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`, `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`. Ruled 2026-10-05 (#5478): checkboxes, not a single choice.* setup's first question after where the project lives asks
  what it is for, as **checkboxes** over the purposes of section 7b (screen 2), any combination;
  none ticked is "Not sure yet"; the purposes are saved on the project as a list
  (`answers.purposes`; a saved single `purpose` reads as a list of one) and shown in its Inspector.
- `source.onboard.purpose-sets-layers` — **[OK]** (#4951, #5478) **Built 2026-10-05 (engine):** `assemble()` and `POST /api/recipes/assemble` take `purposes` (and jobs ticked on their own, `jobs`); the recipe is the union of their jobs, each once, in `STEP_ORDER` (every registered job), whatever order they were ticked in; each step carries its topic (`topic`, `title`, `sentence`). Catalogue also finds names (dates need them) and Tables also finds lines (cells are read line by line), so both recipes pass the check. Pinned by `fichero-server/tests/unit/api/test_setup_round_two.py` and `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the
  recipe's steps are the **union** of the ticked purposes' jobs, each once, in the registry's step
  order; `assemble()` and `POST /api/recipes/assemble` take a list of purposes, and the same list
  in any order gives the same recipe. The NLP layer is proposed only where a ticked purpose uses
  entities, and lines only where one includes them (refines the NLP and Kraken rulings,
  2026-10-01). *Test:* purposes [transcribe, map-places, search] assemble find-lines, read-a-line,
  correct, find-names-tag-words, place-in-a-gazetteer, make-a-vector, each once.
- `source.onboard.purposes-show-their-jobs` — **[PARTIAL]** (#5478) **Built 2026-10-05 (engine):** each purpose in `GET /api/recipes/purposes` carries its `jobs` (id and topic title, in step order); Map places gives Find lines, Read each line, Correct, Find names, Place in a gazetteer; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** under each ticked purpose its jobs in one line by their titles, and below every registry job as a checkbox (a job a ticked purpose brings stays ticked while it is; another can be ticked on its own and is sent as `jobs`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. under each ticked purpose, setup
  lists the jobs it proposes, one line, by their topic titles from the registry; the purposes
  offered are those of section 7b, screen 2 (the original eight, with Statements, Translate or
  normalise, Gather quotations, Catalogue my sources and Tables and forms proposed); a job not in the
  registry (hands, today) is never offered. *Test:* ticking Map places shows Find lines, Read each
  line, Correct, Find names, Place in a gazetteer.
- `source.onboard.job-detail-screens` — **[PARTIAL]** (#5478) **Built 2026-10-05 (app), not yet seen, as ruled that day (every ticked job its own screen):** each ticked job adds one screen after What it is, in step order (`SetupPage.pages`), with its topic's paragraph and example; Entities asks its kinds (default people and places), Translate or normalise how far, Map places which gazetteer, saved as `answers.job_answers`; an unticked job adds none; pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Not built: the steps reading `job_answers`; translate's target language, the gazetteer's region and period, catalogue fields, table columns.* a ticked job that needs an answer the
  engine cannot work out gets one short screen of its own after What it is, and only then: entity
  kinds (checkboxes; default people and places), translate or normalise (into which language, how
  far), gazetteer (which one, region and period), catalogue fields, table columns; an unticked job
  never shows its screen; image clean-up, reading order, dates and statements have no screen (their
  defaults live in the Inspector). *Test:* purposes [transcribe] show no detail screen; adding
  People, places and things shows the entity-kinds screen once.
- `source.onboard.what-runs-by-itself` — **[PARTIAL]** (#5478) **Built 2026-10-05 (app), not yet seen:** its own screen before Start (`RecipeAutomaticFields`): the choice, each recipe step with a checkbox pre-ticked from the purposes that run by themselves (training never), the sentences about Start and import; saved as `answers.automatic` (`runs`, `steps`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Not built: the import hand-off reading it (engine).* "What runs by itself" is its own screen
  before Start: **Nothing runs automatically** or **New material runs through the ticked steps**,
  then each recipe step with a checkbox pre-ticked by its purposes' kind (none ticked for Edit a
  corpus, Decipher, or no purpose); it says that Start runs the recipe once over the material
  already there, that after Start each import runs only the ticked steps over the pages it brought
  (none with Nothing runs automatically), and that an unticked step runs only by hand; the choice is saved with the project (`answers.automatic`) and
  read by the import hand-off (`source.onboard.just-do-it`). *Test:* with Nothing runs
  automatically, an import after Start queues no recipe run.
- `source.onboard.offers-never-hides` — **[PARTIAL]** (#4951) **Built 2026-10-04 (app):** setup's
  How It Will Be Done screen offers every job the registry knows (`RecipeSetupStore.offeredJobs`):
  the purpose's recipe steps first, in the recipe's order, then the rest, in the registry's order,
  under "Also on hand"; a purpose reorders the list and never shortens it (`fichero/Tests/Unit/general/Models/RecipeSetupFlowTests.swift`). 2026-10-05: "Also on hand" is a plain list (no disclosure), each job with Add. *Default taken
  2026-10-04 (design lead), awaiting the maintainer's ruling:* "offered first" in setup means the
  recipe's own steps lead and every other registered job follows in one list. Not built: views
  and menus elsewhere do not yet reorder by purpose (none hide by purpose today). a purpose
  changes what is offered first and what runs by itself; every view and tool stays reachable in
  every project.
- `source.onboard.just-do-it` — **[OK]** (#4951, #5390; built: an import after Start queues one recipe run over its pages (`importers/derivatives.queue_derivatives`)) on a "just do it" purpose, after Start, new
  material runs through the recipe's automatic steps with no further question: each import is one
  `run-a-recipe` job over the pages it brought, and nothing runs for material already there.
- `source.onboard.tools-not-automation` — **[PARTIAL]** (#4951; built: nothing runs at import on a tools purpose; offering its tools first is the app's) on a "tools" purpose (edit, decipher,
  train, not sure), nothing runs at import that the person did not ask for, and that purpose's
  tools are offered first.
- `source.onboard.add-layer` — **[PARTIAL]** (#4951, #5470) **Built 2026-10-04 (app):** the language half:
  the Inspector's Recipe section has a Languages field (search as in setup); adding or removing a
  language re-proposes the recipe from the new answers and saves both on the project, starting
  nothing (`RecipeSetupStore.updateLanguages`, `InspectorProjectLanguages`; `fichero/Tests/Unit/general/Models/RecipeSetupFlowTests.swift`). *Default taken
  2026-10-04 (design lead), awaiting the maintainer's ruling:* a language added later changes the
  recipe for material from then on; re-reading what is already there stays Start's or a run's.
  **Built 2026-10-05 (engine, #5470):** `POST /api/recipes/project/layers` (action
  `project.add_layer`, audited and undoable; `recipes/layers.py`) adds a layer or a language: the
  layer joins `answers.layers` and its steps join the recipe beside the ones it has (a model the
  person chose stays; `POST /api/recipes/assemble` takes the same `layers`); its steps are proposed
  for the material already there (`recipe/proposed.yaml`), and the Start plan shows them
  (`proposed`, each step explained by its topic) with the plan's estimate (pages, where it runs,
  cost); nothing runs until Start, which runs them as one `run-a-recipe` job over all the material
  and clears the proposal; undo, or `remove` before Start, takes the layer and its proposed jobs
  away; pinned by `fichero-server/tests/unit/api/test_add_a_layer_later.py`. *Default taken
  2026-10-05 (design lead), awaiting the maintainer's ruling:* the layers a project can add are the
  ones the rules assemble a step for (lines, reading, entities, graph, places, vectors); a layer the
  purpose already has, or one removed that the purpose brings, is refused in words; before the first
  yes the added layer simply runs with the whole recipe at Start; a language added through this
  route proposes the recipe again and proposes nothing for what is already there (as the 2026-10-04
  default). **Built 2026-10-05 (app, #5470):** the Inspector's Recipe section (and the project's
  own Inspector) has Add a Layer… offering the layers the Start plan names as `addable` (the app
  works out none); adding one shows the jobs proposed for the pages already there, each with its
  topic's words, and the estimate (pages, cost); Start is setup's Start; Remove withdraws them; a
  refusal shows the engine's sentence. Every save from setup or the Inspector keeps
  `answers.layers` (and any other answer the engine wrote), and a recipe proposed again asks for the
  added layers too (`RecipeSetupStore.changeLayer`, `InspectorProjectLayers`;
  `fichero/Tests/Unit/general/Models/RecipeAddLayerTests.swift`, over responses recorded from the
  engine's routes in `fichero/Tests/Fixtures/recipes/`). Not built: the plan's time and carbon (as
  `estimate-before-start`).
  a layer or a language can be added later from the
  library's Inspector; an added layer turns on the recipe's steps of that layer and runs them over
  everything already in the project, as one job.
- `source.recipe.steps-name-layers` — **[GAP]** (#4950) every step names a layer; the resolved
  recipe's `automatic` section lists the steps whose layer the purpose (or an added layer) turns
  on, with whether each may use the cloud, and is never written by hand.

Setup
- `source.onboard.widget-and-search` — **[PARTIAL]** (#4951, #5479) **Built 2026-10-05 (app), not yet seen:** What it is has a search field for languages and for scripts that autocompletes from the engine, and the chosen ones as blue tokens (name shown, tag on hover, × removes); Return on a typed word takes the engine's answer ("spanish" is the `es` token) and refuses a word it does not know in words (`CodeTokenField`, `RecipeSetupStore.addTyped`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. **Built 2026-10-05 (round 3, app):** the Browse… list is gone; matches show in the field's own dropdown (`textInputSuggestions` on the Mac, a List under the field on iPhone and iPad). **Built 2026-10-03:** the Your Material step searches languages and scripts through the engine (2026-10-04: `RecipeSetupStore.searchLanguages`/`searchScripts`; a dialect shows whose dialect it is, a Glottolog-only language is kept as a private-use tag). The engine searches ISO 639-3 joined with Glottolog 5.3 (CC BY 4.0, vendored; languages ISO lacks and about 13,000 dialects, each answer with its BCP 47 tag and glottocode kept apart) and every ISO 15924 script: `GET /api/recipes/languages`, `/scripts`, `fichero-server/tests/unit/api/test_setup_searches_languages_and_scripts.py` and `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. *Not built (ruled 2026-10-05, #5479): the field is free text; no browse menu; one value, not tokens.* setup is a form with search beside each
  field, not a conversation: languages and scripts each autocomplete from the engine's registries
  as the person types (ISO 639-3 with Glottolog; ISO 15924), in a dropdown under the field; no
  Browse… menu (ruled 2026-10-05, #5479); several can be chosen at once, each shown as a token with its name (its tag or code on
  hover) and removed with its ×. *Test:* typing "spanish" offers Spanish (es); choosing it and
  Latin shows two tokens.
- `source.onboard.language-stored-as-tag` — **[OK]** (#5479) **Built 2026-10-05 (engine):** `PUT /api/recipes/project` and `POST /api/recipes/assemble` resolve each language to its tag (`recipes/names.resolve_language`: a tag or ISO 639 code stays a tag, a name resolves when exactly one language has it, a Glottolog-only one to `und-x-<glottocode>`) and each script to its code, and refuse anything else with 422 in words; a project already holding a word reads it as its tag where it resolves and keeps it otherwise. Saving "spanish" stores `es`, and the names step then takes the card that lists `es`; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. what setup saves for a language is
  its tag (`es`, `la`, a private-use tag for a Glottolog-only language) and for a script its ISO
  15924 code, never the typed word; the engine, given a word that is not a tag (a project saved
  before this, or a call from MCP or the command line), resolves it to the tag when exactly one
  language has that name and otherwise refuses in words ("Fichero doesn't know the language
  'spanish'. Choose it from the list."), never passing the word to the rules. *Test:* saving
  languages ["spanish"] stores ["es"], and the recipe proposes a reader whose card lists `es`.
- `source.onboard.direction-chosen` — **[PARTIAL]** (#5479) **Built 2026-10-05 (engine):** the saved answers hold `directions` (script code to `ltr`, `rtl`, `ttb` or `ttb-lr`), each pre-filled from the script's derived direction and kept when changed; any other value is refused in words; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** What it is has one direction picker per chosen script, pre-filled from the engine's derived direction, saved and sent as `directions`. *Not built: the steps reading it.* direction is chosen in setup, pre-filled from
  each chosen script (the engine's derived fact, with where it came from) and changeable: left to
  right, right to left, top to bottom with columns right to left, or with columns left to right;
  one per script; saved on the project (`answers.directions`) and read by the steps that need it.
  *Test:* choosing Arab pre-fills right to left; changing it to left to right is saved.
- `source.onboard.material-any-mix` — **[PARTIAL]** (#5478) **Built 2026-10-05 (engine):** the answers hold `materials` (a saved single `material` reads as a list of one); with more than one kind, the reading step carries `readers`, one choice per kind, and its own model is the default kind's (handwriting first), so Start still reads each page once; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** Material is three checkboxes, at least one kept ticked, saved and sent as `materials`; pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Not built: "roughly when"; the folder or page override choosing a reader.* material is checkboxes, Handwriting, Print and
  Typescript, any mix (at least one; default Handwriting), saved as a list (`answers.materials`);
  the rules propose a reader for each kind ticked, and a card's `material` must cover the kind its
  step reads. *Test:* materials [handwriting, print] assemble two reading choices, one per kind.
- `source.onboard.screens-in-order` — **[PARTIAL]** (#4951, #5477, #5478, #5481, #5482, #5492) **Built 2026-10-06 (app), not yet seen:** setup is four steps (section 7b, ruled 2026-10-06): first run (after Welcome, Permissions and AI) and File › Set Up New Project… run Your project → Your material → What you want to do → Ready; Set Up… starts at Your material (`FirstRunStep.newProjectSteps`, `setUpSteps`); a ticked purpose opens its questions in place and an unticked one shows nothing (`RecipeSetupStore.questions(under:)`); Ready carries the plan, What runs by itself, and the optional rows Check on your pages and Keep an export, then Start (`RecipeReadyFields`); Continue on Your material and What you want to do saves a draft and stays put if the engine refuses it; Start saves, then starts; pinned by `fichero/Tests/Unit/general/Models/SetupFourStepsTests.swift`, `FirstRunStepSelectionTests.swift`, `RecipeSetupFlowTests.swift`, `SetupRoundTwoTests.swift`. *Not yet seen by the maintainer.* *Superseded 2026-10-06 by the four steps:* **Built 2026-10-05 (app):** first run (after Welcome, Permissions and AI) and File › Set Up New Project… run Where it lives → What it is for → Your material → What it is → one screen per ticked job → How it will be done → What runs by itself → Start; Set Up… starts at What it is for (`FirstRunStep.newProjectSteps`, `setUpSteps`, `SetupPage.pages`); every screen after Where it lives saves a draft on Continue and stays put if the engine refuses it; pinned by `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`, `RecipeSetupFlowTests.swift`, `SetupRoundTwoTests.swift`. *Not built: screen 5 of section 7 (check on your pages).* *Superseded 2026-10-05 by section 7b's order (below).* **Built 2026-10-04 (app):** first run
  and Set Up… run one list (`FirstRunStep.setUpSteps`): What are you doing? → Your material (how
  sources come in, Add a Folder…, roughly how many pages) → What it is (languages, scripts, the
  facts worked out for them, the kind of material) → How it will be done (the proposed recipe, the
  cloud question, everything else on hand) → Start. Leaving each screen before Start saves the
  answers as a draft (`PUT /api/recipes/project`) and posts nothing else; Skip still saves nothing
  (`fichero/Tests/Unit/general/Models/RecipeSetupFlowTests.swift`, `FirstRunStepSelectionTests`). *Default taken 2026-10-04 (design lead), awaiting the
  maintainer's ruling:* section 7's order, with screen 5 (Check on your pages) left out until the
  evaluation job exists (#5441; engine), and the draft saved on Continue rather than on every
  keystroke. Not built: screen 5; the order is still to be aligned with the maintainer's step
  document. setup runs in four steps, in one fixed order (ruled 2026-10-06, section 7b, #5492):
  Your project → Your material → What you want to do (a ticked purpose's questions open in place
  under it; an unticked one shows nothing) → Ready (the plan, what runs by itself, the optional
  rows Check on your pages and Keep an export, Start); Set Up… on an existing project starts at
  Your material; it can be closed at any step with the answers kept as a draft in the project,
  and nothing runs before Start. *Test:* setup is exactly those four steps; ticking People,
  places and things shows which kinds of names and nothing for an unticked purpose.
- `source.onboard.teaches-the-method` — **[GAP]** (#4951, #5471, #5481) **Engine built 2026-10-04:** each
  topic of section 7a has a title, one sentence, a paragraph and the example to show, served by
  `GET /api/topics` and `GET /api/topics/{id}` from `fichero-server/src/fichero_server/recipes/seed/topics.yaml`;
  pinned by `fichero-server/tests/unit/recipes/test_topic_registry.py`. **App built 2026-10-05:**
  setup explains each recipe step, languages and scripts with the topic's sentence and its paragraph
  and example on disclosure (`TopicStore`, `TopicExplanation`); pinned by
  `fichero/Tests/Unit/general/Models/TopicStoreTests.swift`. **2026-10-05 (#5481):** the disclosure
  is gone; How it will be done shows each step's one sentence, the paragraph and example are shown
  plainly on each ticked job's own screen and in the Inspector. *Owed: the other topics of section 7a
  are not yet placed on a setup screen, and the example is described, not yet drawn from the
  person's own pages.* across its steps setup explains each topic
  of section 7a (languages, scripts, fonts, glyphs and Unicode, a faithful way to write the script,
  finding sources, models and memory, Kraken, layout, tables, workflows and recipes, entities,
  statements, maps, calendars, normalisation, output formats, fine-tuning, remote compute) with an
  example from the person's own pages where there are some. **Ruled 2026-10-05 (#5481):** in setup,
  each step and field shows its topic's **one sentence** only; the paragraph and example are shown
  in the Inspector and the manual, not behind a disclosure in setup (the 2026-10-05 build's
  disclosure is removed).
- `source.onboard.no-disclosure` — **[PARTIAL]** (#5481) **Built 2026-10-05 (app), not yet seen:** the More and Advanced disclosures and the Also on hand disclosure are deleted; no setup view holds a `DisclosureGroup` (a scan of `Views/Onboarding`, not a walk of the screens); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. setup has no More, Advanced or other disclosure
  chevron on any screen; what is worth showing is shown, and the rest lives in the Inspector and the
  manual. *Test:* a view test walks every setup screen and finds no `DisclosureGroup` and no
  disclosure button.
- `source.onboard.topics-written-once` — **[PARTIAL]** (#4951, #5471) **Engine built 2026-10-04:** one
  registry (`fichero-server/src/fichero_server/recipes/seed/topics.yaml`) holds every topic's and every recipe
  job's words; a job's name and description are read from its entry (the text moved out of
  `recipes/jobs.py`), `GET /api/recipes/jobs` names each job's `topic`, and a test fails if a
  sentence is written in a second engine file (`fichero-server/tests/unit/recipes/test_topic_registry.py`).
  **App built 2026-10-05:** setup and the Inspector's Recipe section read each step's words from
  one per-library `TopicStore` (`GET /api/topics`, `GET /api/topics/{topic_id}`); the job's
  `description` is no longer shown, and a job whose topic is missing shows its name alone;
  pinned by `fichero/Tests/Unit/general/Models/TopicStoreTests.swift`. *Owed: Activity, an
  exported recipe's README and the user manual do not read the registry yet.* each topic's and each job's explanation
  is stored once, with its job or topic in the registry, and the same text is shown in setup, the
  Inspector, an exported recipe's README and the user manual.
- `source.onboard.new-project-offers-setup` — **[PARTIAL]** (#5430, #5482) **Changed 2026-10-05 (ruled that day):** a new project is made BY setup: File › Set Up New Project… (the menu item that was New Library…) opens setup at Where it lives in the key window, or, with no window, opens one that presents it (`NewProjectSetUpSheet`); `createProject` no longer asks for a second setup; pinned by `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`, `fichero/Tests/Unit/general/App/NewLibraryPanelTests.swift`. **Built 2026-10-04 (replaced):** creating a
  project asks for its setup (`LibraryManager.setUpRequestedLibraryId`) and the window showing it
  presents `FirstRunWindow(setUp: true)` through `projectSetUpIsDue`, which never reads
  `firstRunCompleted` (it waits only while the app's own first run is showing);
  `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`. Not pinned: the
  sheet's presentation itself (view code). a project created in the app opens
  setup for itself straight away (`FirstRunWindow(setUp: true)`), whether or not the app's own first
  run was ever completed. `firstRunCompleted` governs only the app's first launch, never a new
  project. Found 2026-10-04: the sheet is gated on `!featureManager.firstRunCompleted`
  (`LibraryWindow.swift:235`), so after the first launch a new project never offers setup. *Test:*
  creating a project through the app's create path with `firstRunCompleted = true` presents setup
  for that project.
- `source.onboard.reachable` — **[PARTIAL]** (#5421) **Built 2026-10-04:** File › Set Up Project…
  (the key window's project) and Set Up… on an empty project's main view (`projectOffersSetUp`)
  both call `LibraryManager.requestSetUp(for:)`, the one request the window presents as
  `FirstRunWindow(setUp: true)`; `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`.
  Not pinned: the menu item and button wiring (view code). 2026-10-05: the document Inspector's
  Set Up… asks through `requestSetUp(for:)` too (its own sheet is gone). setup is reachable without hunting: **File › Set Up
  Project…** for the selected project, and a **Set Up…** button on an empty project's main view, both
  opening the same flow as Inspector › Info › Recipe › Set Up…. *Test:* the menu command and the empty
  state's button each present setup for the selected project.
- `source.onboard.where-it-lives` — **[PARTIAL]** (#5482) **Built 2026-10-05 (app), not yet seen, as ruled that day:** the name (default My Project) and two places, **Inside Fichero** (the default: `Projects/` beside the app's Local project in its data folder) or **Choose a location…** (a folder picker; a synced folder is warned about); Continue makes `<folder>/<name>.fichero` through `LibraryManager.createProject(at:)` and has the engine open it (`POST /api/library`), and a folder that cannot be written is refused on the screen ("Fichero can't write to that folder. Choose another."), nothing made (`NewProjectStore`); pinned by `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`. *Superseded by that ruling: the save panel and the `~/Fichero/<project name>` proposal below.* first-run setup's first screen asks where the
  project lives: its name and folder, a default proposed (`~/Documents/Fichero/`; Open questions),
  and Choose…, which opens a save panel; Continue makes the `.fichero` package there through the one
  create path (`LibraryManager.createProject(at:)`: grant, save, `POST /api/library`), and a folder
  that cannot be written is refused on the screen in words; Set Up… on an existing project skips
  this screen. *Test:* through the real first-run path, Continue with a chosen folder leaves a
  package there that the engine opens.
- `source.onboard.saves-into-the-project` — **[PARTIAL]** (#5477) **Built 2026-10-05 (engine):** a project made by `POST /api/library` (under `~/Fichero/`, an allowed root, among others) takes `PUT`/`GET /api/recipes/project` and `GET /api/recipes/project/start` at once through its own path, and the same calls with no path answer 400 (the first-run bug's shape); pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. Proposing `~/Fichero/<project name>` is the app's. **Built 2026-10-05 (app), not yet seen:** `AppState`'s app-wide setup store is deleted; each project has its own (`LibraryReference.recipeSetupStore`, over its client), and first run, Set Up New Project… and Set Up… read and save through the project Where it lives made or the window shows; the made project's store names its path, and its save is kept where the app-wide client's is refused (a stub answering as the engine does); pinned by `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`. *Not pinned: against the real engine.* every setup read and save after Where it
  lives goes through **that project's** client (its library path sent), the one path Set Up… from
  a project uses; the app-wide client is never used for setup, so `GET`/`PUT /api/recipes/project`
  never answer 400 in first run. *Test:* first run through the real app environment saves the
  Your material answers and `GET /api/recipes/project` on the new project returns them.
- `source.onboard.start-works-in-first-run` — **[PARTIAL]** (#5477) **Built 2026-10-05 (app), not yet seen:** first run's Start plans and starts through the project made on Where it lives (its store), as Set Up… does. *Not pinned: first run to Start on a fixture folder against the real engine.* the Start screen in first run plans
  and starts exactly as Set Up… from a project does (`GET`/`POST /api/recipes/project/start` on the
  project made on screen 1); Start enables once the plan has no refusals. *Test:* first run to Start
  on a fixture folder enables Start and records the first yes in the new project.
- `source.onboard.five-ways-in` — **[PARTIAL]** (#5480) **Built 2026-10-05 (app), not yet seen:** Link, Copy, Move, Index and Keep arranged as radio buttons, each with its sentence; Keep arranged imports as Index and is saved as `ingest_mode: keep-arranged`, read back as Keep arranged (`SetupWayIn`; `fichero/Tests/Unit/general/Models/KeepArrangedTests.swift`). *Not built: the import menus and drops starting from the saved choice.* Your material offers five ways material comes in,
  each with one sentence of what it does to the originals: Link (default), Copy, Move, Index and
  Keep arranged; the choice is saved with the project and used by Add a Folder… and by the
  project's later imports. Supersedes the four of `source.sync.four-ways-in` for setup.
- `source.onboard.index-ties-the-folder` — **[PARTIAL]** (#5480, #4952) **Built 2026-10-05 (app), not yet seen:** Add a Folder… with Index imports the folder as `index`, then ties it through `/api/sync-folders` (the folder the import adopted is used as it is; one not listed is tied with `POST`), reads its intake and shows the tied folder on the screen: its place, formats and intake with Take In and Leave (`RecipeSetupStore.addFolder`, `SyncFolderStore.tie`; `fichero/Tests/Unit/general/Models/SyncFolderStoreTests.swift`). Keep arranged ties the folder the same way (built 2026-10-05, below). *Not built: the file count.* choosing Index or Keep arranged
  with a folder ties it through `/api/sync-folders` (the engine half built for #4952; the app calls
  none of those routes today) and setup shows the tied folder: its path, its file count, and intake
  (files added later) with the preview's count and a switch to turn it on. *Test:* setup with Index
  and a fixture folder lists the folder in `GET /api/sync-folders` and shows its intake preview.
- `source.onboard.keep-arranged` — **[PARTIAL]** (#5480) **Built 2026-10-05 (engine half):** a synced folder has a mode, `index` or `keep-arranged` (`POST /api/sync-folders` takes `mode`, `GET` shows it, `PUT /api/sync-folders/{id}/mode` switches it, refused in words (422) for a folder that cannot be written to or that no project folder came from); `GET /api/sync-folders/{id}/arrangement` is the dry run (the moves, from and to, and any refusal; nothing moves); kept arranged, the folder follows the project's own folders (rule (a) of open question 10): a document moved or renamed, or a folder renamed, in the project moves or renames its file inside the folder, never out of it, never over a file (a clash takes `name 2.jpg`), never deleting one; a file moved by hand stays, and the project follows it (its record, its project folder, its name; marked placed by hand) (`sync_folder.plan`, `arrange`, `follow_hand_moves`; `fichero-server/tests/unit/jobs/test_synced_folder_keep_arranged.py`). **Built 2026-10-05 (app), not yet seen:** Add a Folder… with Keep arranged imports as Index, ties the folder as Index (so nothing moves yet: the engine arranges a folder the moment it is kept arranged), reads the dry run and shows it on the screen in the folder's own section: how many files would move, three of the new paths (from → to), or the engine's refusal in its words with no Arrange; Arrange is the yes (`PUT …/mode`, `keep-arranged`) and Cancel drops it; the folder's Inspector switches Index ↔ Keep arranged through the same dry run (`SyncFolderStore.proposeKeepArranged`, `confirmKeepArranged`, `choose`; `KeepArrangedProposal`; `fichero/Tests/Unit/general/Models/KeepArrangedTests.swift`). *Not built: date and written-rule arrangements.* Keep arranged is Index plus arrangement (section
  7b): Fichero moves and renames files only inside the tied folder, by the project's chosen rule
  (Open questions), never out of it and never deleting one; before the first arrangement it shows
  how many files would move and a sample of the new paths, and nothing moves until the person says
  yes. *Test:* a fixture folder of five misplaced files shows five moves, and after yes each file
  is at its rule's path and none is gone.
- `source.onboard.keep-arranged-undoable` — **[PARTIAL]** (#5480) **Built 2026-10-05 (engine half):** each arrangement is one audited `sync.arrange` action listing every move (from, to); undo (`POST /api/actions/audit/{id}/undo`) puts every file back and its record with it (`fichero-server/tests/unit/jobs/test_synced_folder_keep_arranged.py`). *Not built: a file added from outside moved into place by the rule (it is taken in where it lands).* each arrangement is one audited,
  undoable action listing every move (old path, new path); undo puts every file back; a file added
  from outside is taken in by intake after its preview and then moved into place by the same rule;
  a file the person moves by hand stays where they put it and is recorded as placed by hand.
  *Test:* arrange then undo restores every original path.
- `source.onboard.kept-exported` — **[PARTIAL]** (#5485) **Built 2026-10-05 (engine half):** a project keeps any number of exports, each a folder, a format (`word`, `markdown`, `plain-text`, `alto`, `pagexml`, `tei`, `hocr`) and one file per `page` or `document` (a page's document is the node it sits in; the page formats are per page only, refused per document in words), kept in the library database (`kept_exports`, `kept_export_files`); `GET`/`POST /api/export/kept`, `DELETE /api/export/kept/{id}` (files stay), `POST /api/export/kept/{id}/write` (write now); keeping and removing are the audited `export.keep`/`export.unkeep`. Each write is one `write-kept-export` job on the background `database` lane; page formats through `page_export.export_page`, Word through `export_service.export_word_docx` (the record's derived text), Markdown through the new `export_service.render_markdown_text` (headings from the document and page names, reading-order text), plain text as the derived text. One-way: it overwrites only files it wrote (a hand edit included), never touches or deletes another file (one in its way is listed, `in_the_way`); a folder that is not there, a system folder (the owner folder pick's own check) or one inside the project is refused in one sentence. Rewritten after a quiet period when an audited action touches a page (the synced folder's hook) and when a recipe's workflow step finishes, for its pages; no watcher (`kept_export.py`; `fichero-server/tests/unit/jobs/test_kept_exports.py`). **Built 2026-10-05 (app), not yet seen:** setup's screen 3, Kept exported, between Your material and What it is for (`FirstRunStep.keptExported`; Continue with no rows skips it): one sentence says it is one-way and that a file changed there by hand is replaced at the next write; Add Export adds a row: Choose… (a folder panel; the folder is granted to the engine by the import path's own call), the format (Word, Markdown, plain text, ALTO XML, PAGE XML, TEI, hOCR), per page or per document (per document cannot be chosen for a page format) and ×; Continue keeps each row with a folder (`POST /api/export/kept`) and stays on the screen with the engine's sentence for a refused one; kept exports are listed with × (`DELETE`). The project's Inspector has a Kept Exported section listing each with its state (writing, waiting, last written) and Write Now (`POST …/write`) and × (`KeptExportStore`, `KeptExportFields`, `KeptExportsInspectorSection`; `fichero/Tests/Unit/general/Models/KeptExportStoreTests.swift`). setup's
  third screen keeps up-to-date exports in folders outside the project (section 7b, screen 3).
  *Test:* a kept ALTO-per-page export holds one file per page, and a second write leaves a file it did
  not write alone.
- `source.onboard.set-up-later` — **[PARTIAL]** (#4951) **Built 2026-10-03:** Skip leaves the project unset and saves nothing; `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`. "Set up later" makes a project with no settings
  that behaves as today, and Set Up… in its Inspector runs setup at any time.
- `source.onboard.samples-first` — **[GAP]** (#4951) given material, setup picks up to ten sample
  pages spread across it (first, last, evenly spaced, largest and smallest), which the person can
  swap; from them, where a local model is available, it suggests scripts, languages, material,
  period and layout, each labelled "suggested from your pages" until accepted.
- `source.onboard.five-questions` — **[GAP]** (#4951, #5478, #5479) beyond the location, the purposes
  and the material, setup's What it is screen asks four things (languages, scripts, direction,
  material as checkboxes with roughly when), each pre-filled where it can be; layout and whether
  pages may leave are asked later (the latter on How it will be done, only when a step would use
  the cloud).
- `source.onboard.volume-counted-or-asked` — **[PARTIAL]** (#4951) *Built (engine): an imported project's volume is counted (every live page, and every file without pages; not folders, deleted documents or workflows) and used by the Start plan and `GET /api/recipes/routes`; pinned by `fichero-server/tests/unit/recipes/test_routes_for_the_volume.py`. Not built: counting material before import (a folder, a manifest's canvases), asking when it cannot count, storing the volume.* setup counts the pages of the
  material given (images, PDF pages, manifest canvases) and asks how much (tens, thousands,
  hundreds of thousands) only when it cannot count; the volume is stored and used by the rules.
- `source.onboard.self-documenting` — **[PARTIAL]** (#4951) **Built 2026-10-03:** each proposed step explains itself with the job registry's own text (GET /api/recipes/jobs); `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. each setup screen and each proposed step
  explains in plain words what it does, why it is in the recipe, and its options' trade-offs
  (accuracy, cost, speed, carbon, trainability), with an example from the person's own sample
  pages where there are some, using the job registry's descriptions.
- `source.onboard.recordings-orthography` — **[GAP]** (#4951) for recordings, setup asks how the
  speech is to be written (a practical orthography, IPA, or the project's own system) instead of
  which script, and the recipe's reading step is "transcribe speech"; a language with no script is
  recorded as such.
- `source.onboard.folders-differ` — **[GAP]** (#4951) where folders of the material differ in
  material or language, the answers can be given per folder and the rules assemble a folder
  override for each step that differs, not a second recipe.
- `source.onboard.script-cases-covered` — **[GAP]** (#4951) for a fixture of each material in the
  coverage table (Latin hands, print in another script, vertical CJK, kuzushiji, palm-leaf,
  right-to-left, sign-by-sign scripts, an Indigenous syllabary, unwritten speech), setup produces
  the steps the table names or "needs a model", never an error and never a silent substitute.
- `source.onboard.estimate-before-start` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** the Start plan carries the page count and the cost per run (free on this Mac, unpriced cloud models null); the count is the pages a run runs over, and `estimate.counted` says what it counts ("4 photographs + 1 PDF page = 5 pages"), what the project holds that is not a page, and photographs that share a file name (copies taken in twice), #5498, pinned by `fichero-server/tests/unit/recipes/test_recipe_runs_to_spec.py`; time, carbon and the main alternative's estimate are not built; pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/api/test_start_is_the_first_yes.py`. screens 4 and 6 show the whole
  volume's estimate (time where it runs, cost, carbon labelled as an estimate) for the proposed
  recipe and for its main alternative, before anything runs.
- `source.onboard.routes-for-the-volume` — **[PARTIAL]** (#4951, #5404) *Built (engine): `GET /api/recipes/routes` (`recipes/routes.py`) returns the cloud, this-Mac and distil routes for a volume; this Mac's time is the median of its finished job rows for that model (measured), cloud cost the price list times the Start plan's per-page tokens (estimate), and a cloud model's time, a training run's cost and hours, accuracy and carbon are `unknown` until measured; pinned by `fichero-server/tests/unit/recipes/test_routes_for_the_volume.py`. Not built: training time from past runs, accuracy from stored bake-off scores, carbon, a cluster as the read target, and setup's screen.* for the volume the person has, setup
  answers "what can we do with this?" with routes side by side, not one plan: read it all with the
  cloud teacher; read it on this Mac; and distil (the teacher labels a sample, a small model is
  trained on this Mac or a compute target, then the small model reads the whole volume here or on
  a cluster). Each route shows the whole volume's cost, wall-clock time where it runs, expected
  accuracy (measured on this project's checked pages; else published; else "unknown until the
  bake-off") and carbon, each figure marked measured or estimate. The distil route also shows the
  teacher's labelling cost and the training run's cost and time. Ruled 2026-10-03.
- `source.onboard.derives-not-asks` — **[PARTIAL]** (#4951) *Built (engine): `GET /api/recipes/derived?scripts=` (`recipes/derived.py`) answers, each fact with where it came from: per script its direction (the language policy's own rule) and whether it may be vertical (then setup asks, since only the pages settle it), the bundled font for a script macOS lacks (Syriac, Mongolian, Coptic, Cherokee), this Mac's chip and memory, the providers with a key (names only) and the places work can run (this Mac, Hugging Face when its key is present, configured clusters); pinned by `fichero-server/tests/unit/recipes/test_setup_derives_not_asks.py`. The app's Your Material step shows each chosen script's direction, bundled font and "may be vertical" (`RecipeSetupStoreTests`, 2026-10-04). Not built: line position, correcting a derived fact on screen.* line position, fonts, this Mac's
  chip and memory, keys present and compute targets are worked out, shown, and correctable, never
  asked; direction is worked out and pre-filled, then chosen (ruled 2026-10-05,
  `source.onboard.direction-chosen`).
- `source.onboard.ground-truth-from-files` — **[PARTIAL]** (#4951, #5513) *Built (engine, 2026-10-06):
  a pass can be **marked ground truth** (`SegmentPass.ground_truth`; who made it stays the file,
  `external_import`), at import (`ground_truth` on `format.import`, `POST /api/documents/{id}/import` and
  the folder import; off by default) or afterwards (`PUT /api/segments/passes/{id}/ground-truth`, the
  audited, undoable `segment.pass_ground_truth`). One question, `made_by_a_person`, makes a marked pass a
  person's for the bake-off's ground truth, the evaluation's reference (trust `person`) and the working
  pass; its file readings count as a person's (not `labelled_machine`). The readiness sentence names
  pages of imported transcriptions not marked and how to mark them (`unmarked_import_pages`). Pinned by
  `fichero-server/tests/unit/recipes/test_import_ground_truth.py`. Not built: setup's screen taking the
  files, the app's Mark as Ground Truth, plain text named after its image as page-level ground truth.*
  Corrected transcriptions given at setup (PAGE, ALTO, TEI, or plain text named after its image) come
  in through the one import path as person-made passes marked ground truth, and the bake-off uses them.
- `source.onboard.existing-library` — **[GAP]** (#4951) setup on an existing library takes samples
  and ground truth from its pages, rewrites nothing, and offers running the recipe over its
  existing pages as a separate job with its page count and estimate.
- `source.onboard.search-triggered` — **[GAP]** (#4948, #4951) once scripts, languages and period
  are set, Fichero finds candidates for each step itself, without a manual search.
- `source.onboard.proposes-chain` — **[PARTIAL]** (#4951) **Built 2026-10-03:** the proposed recipe shows each step's model card (note, licence, size, error rate), reasons and gaps; estimates and samples are a gap; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. screen 4 shows the proposed recipe: a
  published one that fits (the flagship first where it fits) or a generated one, with each step's
  model, where it runs, download size, licence class and measurements.
- `source.onboard.deterministic-recipe` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-03 (engine):** `assemble()` from answers and cards (`recipes/assemble.py`); cards are not yet read from the real catalogue; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the recipe is assembled by rules
  from the answers and the cards' confirmed facts; the same answers and catalogue always give the
  same recipe, and each choice names the card facts and measurements it rests on.
- `source.recipe.candidates-filtered-then-ranked` — **[GAP]** (#4950) candidates are kept only if
  they pass the hard constraints (job, script coverage, language where it matters, runs here or on
  a bound target, licence, egress); material and period only lower a candidate's rank. The rest
  are ranked in a fixed order: accuracy in one-point bands (measured here, else published, else
  coverage), then local before remote, cheaper, faster, lower carbon, trainable, smaller, then
  card id.
- `source.recipe.cheapest-local-first` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-03 (engine):** local candidates first in `assemble()`; the A/B that moves up is not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. a step's starting choice is the cheapest
  local candidate that passes the hard constraints (Tesseract, Kraken, or a local open OCR model);
  a costlier option replaces it only after an A/B on the person's pages shows the cheap one misses
  the bar and the person confirms; the comparison shows accuracy, cost and environmental cost side
  by side; distilling and fine-tuning are offered as options, never defaults.
- `source.recipe.volume-rule` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-03 (engine):** training offered from 5,000 pages in `assemble()`; cost and time limits not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the volume band changes the
  recommendation: under 100 pages accuracy alone decides; from 5,000 the train step is offered
  from the start; above 100,000 a candidate whose whole-volume cost or time is beyond the limits
  (by default 500 dollars in the cloud or 30 days on this Mac) is shown but not chosen, and the
  teacher-and-student path is proposed.
- `source.recipe.reader-tiers` — **[GAP]** (#4948) with no measurement, readers are ordered by tier:
  specialist line readers, then small historical vision-language models, then general ones;
  Tesseract only for print and typescript; within a tier, by coverage.
- `source.recipe.no-other-style-substitute` — **[GAP]** (#4951) a reader made for another style of
  the project's script (naskh for nastaliq) is never proposed in its place; the step is "needs a
  model" and the gap is named.
- `source.onboard.sign-scripts-specialist-path` — **[GAP]** (#4951) for scripts read sign by sign
  (cuneiform, hieroglyphs, Linear B, Maya), setup names the gap, shows any specialist pipeline
  found as a card marked "not runnable in Fichero yet", offers the decipher or train paths, and
  never proposes a general vision model in their place.
- `source.onboard.speech-candidates` — **[GAP]** (#4951) for recordings, speech models (Whisper,
  MMS) are candidates by the language lists on their cards, LOOVE coverage is not used, and where
  none lists the language setup says so and offers hand transcription in the chosen orthography or
  IPA, then training.
- `source.recipe.loove-tokenizer-only` — **[GAP]** (#4948) LOOVE tokenizer coverage filters and
  ranks only language and vision-language models; Kraken and Tesseract are judged on their
  character-set coverage; a measurement on the project's pages outranks both.
- `source.recipe.no-llm-correction-in-unknown-language` — **[GAP]** (#4950) a correction or
  normalising step by a language model is included only when the model's card lists the project's
  language; otherwise it is left out and the recipe says why.
- `source.onboard.assistant-proposal` — **[GAP]** (#4951) a language model may help: filling in a
  prose-only card (facts unconfirmed until a person confirms), explaining a choice, or suggesting
  answers from samples; it runs locally unless the project allows the cloud, and never decides the
  recipe.
The bake-off's behaviours (`source.onboard.bakeoff`, `-combinations`, `-records-combination`, `-tesseract-baseline`, `-minimum`, `-is-a-job`, `-skippable`, `-random-sample`) moved on 2026-10-04 to the one home for evaluation, `compute/distillation.md` ("Evaluation against out-of-the-box models").
- `source.onboard.says-no-model` — **[PARTIAL]** (#4951, #5481) **Built 2026-10-05 (engine):** a step with no fitting model carries one `problem`: `kind` (no-model-for-job, -script, -language, no-reader-for-material, licence-not-accepted, cloud-not-allowed, not-enough-memory; the refusal of the card that got furthest through the rules), one `sentence` naming languages and scripts by name ("No correcting model here knows Spanish yet."), `fix` and `fixes` (download, choose-cloud, choose-model, allow-cloud, accept-licence), and the rules' raw reason in `detail` (the field is `kind`, not `code`: a recipe refuses any key named code); pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** How it will be done shows a step's problem once, its `sentence`, with its `fix` as a button (Download a model…, Use a cloud model…, Choose a model… open Settings › AI Models; Let pages leave this Mac answers the cloud question and proposes the recipe again); the recipe's `gaps` list is no longer shown; `detail` appears only in the Inspector (`RecipeStepsView.lines`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Not built: a download named for the language ("Download a Spanish reader…").* *Built 2026-10-03: a step with no fitting model shows its gap, but as the rules' raw reason, model ids included, and twice (under the step and again below; seen 2026-10-05); `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`.* where no candidate passes the hard constraints
  for a step, setup says so **once**, on that step's row, in words a historian reads, built from the
  rule that refused ("No reading model here knows Spanish yet."), with each fix as a button
  (download a fitting model, use a cloud model, choose a model; hand-transcribe, draft-and-correct
  and train where they apply); the rules' own reason goes to the log and the Inspector; it never
  substitutes silently. *Test:* a recipe whose correct step is refused for language shows one
  sentence naming the language, and no card id.
- `source.onboard.never-raw-model-ids` — **[PARTIAL]** (#5481) **Built 2026-10-05 (engine):** a step problem's `sentence` holds no `mlx:`, `hf/`, `@`, `kraken:` or repository; the raw ids stay in `detail` and `gap`; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** setup names a step's model by its card's name (`note`) beside where it runs, never its id, and shows nothing in its place when the card has no name; the Advanced disclosure that listed card ids is deleted; pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. nothing in setup shows a model's id, pin,
  repository path or revision; a model is named by its card's display name. *Test:* every string
  setup renders for a recipe whose cards are `mlx:hf/...@unpinned` contains no `mlx:`, `hf/` or
  `@`.
- `source.onboard.no-model-step-kept` — **[GAP]** (#4951) a step with no model stays in the recipe
  marked "needs a model"; steps that do not depend on it run, and those that do wait with that
  reason.
- `source.onboard.train-path` — **[GAP]** (#4951, #5336) where no candidate fits a reading step,
  setup offers the train-your-own path (`compute/distillation.md`) and shows the corrected-line
  count at which training will be offered.
- `source.onboard.egress-asked-twice` — **[GAP]** (#4951) superseded 2026-10-01 by
  `source.onboard.cloud-asked-once`: asked once per project, showing what is sent, to whom, how many
  pages and the estimated cost; the default is that nothing leaves.
- `source.onboard.flagship-recipe` — **[GAP]** (#4950, #4951) historical Spanish hands have a
  flagship recipe, shipped with Fichero and in the catalogue, measured end to end on real pages of
  that material, whose defaults need no adjusting; its `measurements.yaml` is published with it.
- `source.onboard.generates-for-any-language` — **[GAP]** (#4951) for a language and script no
  published recipe fits (Cherokee in the syllabary, for example), setup generates one through the
  same flow: model search, rules, bake-off where possible, and "needs a model" with the train path
  where nothing fits.
- `source.onboard.outputs-recipe-and-defaults` — **[GAP]** (#4950, #4951) setup produces the
  project's recipe and its defaults at the project rung of the cascade; both are shown on the
  Ready screen before Start.
- `source.onboard.edited-in-the-inspector` — **[GAP]** (#4951) everything setup set (purpose,
  defaults, recipe, steps, models, layers) is shown and edited in the Inspector when the library
  is selected.
- `source.onboard.regen-shows-diff` — **[GAP]** (#4951) changing an answer re-assembles the recipe
  and defaults and shows what would change, step by step; values the person set by hand are kept
  unless they choose otherwise.
- `source.onboard.rerun-rewrites-nothing` — **[GAP]** (#4951) changing a project's answers or recipe
  changes defaults for new work only; nothing already made is rewritten.

The recipe and its format
- `source.recipe.is-a-file` — **[GAP]** (#4950) a recipe can be exported as, and taken from, a
  shareable folder that names its steps, their models, and the scripts, languages, period and
  purposes it suits.
- `source.recipe.makes-a-workflow` — **[PARTIAL]** (#4950) **Built 2026-10-03 (engine):** `plan_start` maps each step to a shipped workflow by name with the step's model (`recipes/start.py`, four jobs so far), refusing by name a step it cannot map; a pinned Kraken reader reaches Transcribe (Kraken) as the run's `kraken` override (`workflows/validation.py`), and a reader outside the catalogue this Mac can fetch is refused; Start validates with `check_recipe`, and the assemble answer is a whole recipe (schema, version, suits); the runs are not started yet; pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/workflows/test_kraken_reader_is_a_run_override.py`, `fichero-server/tests/unit/api/test_start_is_the_first_yes.py`. applying a recipe's steps makes and runs
  workflows; nothing runs except workflows.
- `source.recipe.holds-no-second-copy` — **[GAP]** (#4950) a recipe refers to workflows in the
  store by name and may carry its own, but never a copy of one the store holds; the locked default
  workflows stay in the store and shipped recipes refer to them (ruled 2026-10-01).
- `source.recipe.stored-in-project` — **[GAP]** (#4950) a project's recipe (followed version,
  overrides, purpose, added layers, target bindings) is stored in the project database, and the
  Inspector, MCP and the command line return the same resolved recipe from the engine.
- `source.recipe.steps-are-jobs` — **[PARTIAL]** (#4949, #5364) **Built 2026-10-03 (engine):** `unmet_inputs` checks steps in order (`recipes/jobs.py`); pinned by `fichero-server/tests/unit/recipes/test_job_registry.py`. a recipe step names a job, where it
  applies (which segment kinds), a model, settings and a prompt; the recipe is checked before it
  runs, so a step uses only what an earlier step or the source gives.
- `source.recipe.per-region-kind` — **[GAP]** (#4949) a step can send each kind of region to a
  different model (main text, marginal gloss, table, drawing).
- `source.recipe.names-models-and-where` — **[GAP]** (#4950) a recipe names the model for each step,
  pinned (Hugging Face repository and revision, Zenodo DOI, package and version, Kraken built-in
  and version, or a cloud provider's model id with the date measured) or a role default, and where
  it runs: `this-mac`, `cloud`, `cluster` or `gpu-service`.
- `source.recipe.runs-on-binds-to-a-target` — **[GAP]** (#4950) a shared recipe never names a
  person's compute target; the project binds each `cluster` or `gpu-service` step to one of its own,
  and an unbound step waits with "No cluster is set up".
- `source.recipe.alternatives-in-order` — **[GAP]** (#4950) when this Mac cannot run a step's pin,
  the first listed alternative that can is used, and the choice is recorded and shown.
- `source.recipe.conditions-fixed-list` — **[GAP]** (#4950) a step's `when` and `offered_when` use
  only a fixed list of conditions (spreads detected, a confidence threshold, a corrected-line
  count); anything else is refused when the recipe is checked.
- `source.recipe.train-never-automatic` — **[GAP]** (#4950, #5336) a train step runs by itself only if the
  person chose automatic training in setup (offered with a default such as distilling from a large
  teacher, then fine-tuning a small model); otherwise it is offered when its condition is met and
  runs only when the person starts it.
- `source.recipe.update-is-clicked-not-applied` — **[GAP]** (#5364) a new version of a followed recipe shows
  as an update symbol in the Inspector; nothing changes until the person clicks it; then the recipe
  updates and a re-run of existing pages is offered as one job with its estimate.
- `source.onboard.cloud-asked-once` — **[PARTIAL]** (#4951) **Built 2026-10-03:** asked only when the recipe names cloud_options, saved with the project's answers (PUT /api/recipes/project); `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`, `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. whether pages may leave the Mac is asked once per
  project (at setup or first cloud use, whichever is first) and shown in the recipe editor, where
  every cloud step is marked; it is not asked again per provider or per step.
- `source.recipe.prompt-files` — **[GAP]** (#5364) each prompt is one file with a header naming its
  job, the model it was written for, its version and its variables; a variable the step does not
  supply is refused when the recipe is checked.
- `source.recipe.schema-versioned` — **[GAP]** (#5364) `recipe.yaml` carries its schema version; a
  version newer than this Fichero understands is refused with the version named, and an older one
  keeps working.
- `source.recipe.folder-format` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** `recipe.yaml` load and check (`recipes/recipe.py`); prompts, measurements and the RO-Crate wrapper not yet written by Export Recipe; pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe exports as a folder: `recipe.yaml`
  (published JSON Schema), one file per prompt, its workflows, its measurements, a licence, a README
  and a Workflow RO-Crate wrapper.
- `source.recipe.data-not-code` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** code-shaped keys refused anywhere in a recipe (`recipes/recipe.py`); pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe can name only registered jobs, models,
  prompts, settings and workflows built from Fichero's tools; it cannot carry scripts or grant a
  model tools or network access, and an imported recipe that tries is refused, naming the entry.
- `source.recipe.never-holds-keys` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** credential-shaped keys refused (`recipes/recipe.py`); pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe names providers and models but never
  a key; exporting one that would include a key is impossible by construction, and taking one that
  needs a missing key says which.
- `source.recipe.checked-at-every-door` — **[GAP]** (#4950, #5364) a recipe is checked at setup,
  when taken, when an update is offered and before each run, and the check lists by step: unknown
  jobs, newer schema, unmet inputs, missing pins, models this Mac cannot run, refused cloud steps,
  missing keys, unbound targets, missing prompts or variables.
- `source.job.find-documents` — **[GAP]** (#4949) a step can propose which consecutive pages of a folder form
  one document, for a person to confirm (the existing Group action makes it so).
- `source.job.split-into-entries` — **[GAP]** (#4949) a step can split a diary, register or ledger into
  dated entries.
- `source.job.extract-to-table` — **[GAP]** (#4949, #5365) a step can fill one row per document or entry
  with the project's metadata fields, each value tied to the text it came from, exportable as a
  spreadsheet.
- `source.job.pull-out-passages` — **[GAP]** (#4949) a step can gather excerpts on a question or theme,
  each with its source and place, into a note or collection.
- `source.recipe.embedder-by-language` — **[PARTIAL]** (#4948, #4951) **Built 2026-10-03 (engine):** the smallest local embedder covering the languages, in `assemble()`; the search A/B is not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the embedder is the smallest local
  model whose card covers all the project's languages and scripts and that this Mac holds; its A/B
  is a side-by-side search on the person's own questions; changing it re-embeds as one job.
- `source.recipe.advanced-per-step` — **[GAP]** (#4951) every step shown in setup and the Inspector has an
  Advanced disclosure for its model, settings and prompt, with A/B one click away.
- `source.recipe.by-material-kind` — **[GAP]** (#4951, #5364) a project can follow one recipe per kind of
  material; a sorting step tags each page's kind (handwritten, printed, typescript, map, drawing,
  photograph) from the image, each kind runs its own recipe, and a person's correction of a page's
  kind is kept and re-routes the page.
- `source.recipe.per-folder` — **[GAP]** (#4951, #5364) a folder can follow a recipe other than its
  library's, and a step's model can be overridden on a folder, resolved by the cascade; work in
  that folder runs that recipe.
- `source.recipe.reaches-the-whole-model` — **[GAP]** (#4949, #5364) a recipe can name the knowledge
  and output jobs too: link to authorities, place in a gazetteer, enrich from linked data over
  SPARQL, work out dates, attribute hands, export and publish; each is owned by its own spec and
  only named by the recipe; facts fetched from an endpoint are kept apart from what the pages say.
- `source.recipe.export-folder-in-sync` — **[GAP]** (#4640, #4952) an export step can write a synced
  folder that is kept current as the work changes, re-exporting only what a change touched.
- `source.recipe.travels-with-export` — **[GAP]** (#5364) an export package can include the recipe
  that made its data, in the same RO-Crate.

Trying another option
- `source.try.any-time` — **[GAP]** (#4950) Try Another Option… is offered on any selection (pages,
  a region, lines, a document) in the Inspector and the context menu, for a step or a run of
  steps, with one or two alternatives (a model, a combination or a prompt), at any time after setup.
- `source.try.every-job` — **[GAP]** (#4950) it works for every registered job, reading and beyond:
  layout, entities, statements, authority links, dates and search vectors.
- `source.try.never-over-existing` — **[GAP]** (#4950) each alternative shows its cost and time,
  runs as a job in Activity, and lands as new passes, readings, mentions or claims (a vector
  alternative as an index beside the current one); nothing existing changes.
- `source.try.compared-as-declared` — **[GAP]** (#4950) results open side by side in panes and are
  compared the way the job declares: shapes overlaid with overlap scores against confirmed shapes;
  readings by text diff with error rates against corrected text; entities, statements, links and
  dates by precision and recall against confirmed ones, else side-by-side lists; vectors by the
  top results for the person's queries; each with cost, speed and carbon estimate.
- `source.try.use-this-scope` — **[GAP]** (#4950) Use This makes the winner the step's (or the
  combination's) choice for the project or for one folder, stored as an override on the recipe.
- `source.try.kept-and-rerunnable` — **[GAP]** (#4950) a comparison is kept with its selection and
  options and can be run again later.
- `source.try.bakeoff-is-the-same-tool` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-05 (engine, readers
  only):** `recipes/bakeoff.py` runs the evaluation job (`training/evaluation.py`, `evaluation.run`) on the
  corrected sample pages (each page's newest pass a person made), so there is one comparison code path:
  the top three `read-a-line` readers by the rules' own rank, plus Tesseract for print or typescript when
  its card has the language (never handwriting; named, not scored, while it is not bundled), all scored by
  the one CER on the same pages, speed measured in the run; below 100 corrected lines on two pages it
  says how many more and runs nothing; the table is ranked by the fixed order and kept in
  `recipe/bakeoffs/<id>.yaml`, its scores read from the model cards; Use This writes an override on the
  recipe for the project or a folder through `project.save_setup` (audited, undoable). Routes
  `/api/recipes/project/bakeoffs` (start, list, result, `/use`), CLI and MCP generated. Pinned by
  `fichero-server/tests/unit/recipes/test_bakeoff_readers.py` and
  `fichero-server/tests/unit/training/test_evaluation_job.py`. **Built 2026-10-05 (app, not yet seen):**
  Check on your pages, under the reading step on setup's How it will be done screen and in the project
  Inspector's Recipe section (`BakeoffSection` in `RecipeStepsView`, `BakeoffStore` per project): one
  button; the engine's refusal sentence once, with no button, below the threshold; progress from the
  Activity store while the job runs (setup can be left); the table in the engine's order (reader, error
  rate, this Mac or cloud, speed, cost for all pages, why not scored); Use This for this project or a
  folder, updating the reading step in place and keeping the override through later saves. Pinned by
  `fichero/Tests/Unit/general/Models/BakeoffStoreTests.swift`. **Fixed 2026-10-05 (engine and app, app not
  yet seen):** each bake-off row carries its reader's `name`, the card's own name (its `note`, the name a
  recipe step shows for its model), and the table shows it; a refusal or a Use This refusal names readers
  by that name, never a card id; assembling for an open project with a saved recipe returns its
  `overrides` and applies each project-scope one to its step (`bakeoff.apply_project_overrides`, the path
  Use This takes; a folder override stays an override), so setup proposing the recipe again keeps a Use
  This; `GET /api/recipes/project/bakeoffs` reports `readiness` (corrected lines and pages, how many more,
  the sentence; `bakeoff.readiness`, the one count a start refuses by), and the app says the sentence
  before anything is pressed and shows Compare Readers only when ready. Pinned by
  `test_bakeoff_readers.py` (the row's name, assemble keeps Use This, readiness matches the start
  refusal, no card id in a refusal) and `BakeoffStoreTests.swift`. **Built 2026-10-06 (#5513, part of
  #5499):** ground truth counts passes marked ground truth and, on a page with no person-made pass, the
  lines a person corrected inside a model's pass (those lines only; `evaluation.person_read_lines`, by
  the one counting rule); the sentence reads "Needs 100 corrected lines on at least 2 pages; this project
  has 44 on 1 page. Correct 56 more lines, on at least 1 more page." (`test_import_ground_truth.py`).
  *Not built: combinations across steps (find lines then read; at most nine); other steps than reading;
  WER (the one function gives CER only); per hand and page kind (per page only); a
  cloud candidate scored (the evaluation job has no remote target yet: it is priced, not scored); Start
  honouring a folder override.* setup's bake-off is Try Another
  Option… run on the sample ground-truth pages over the rule-proposed combinations; there is one
  comparison code path.

Running and failure
- `source.recipe.download-failure-waits` — **[GAP]** (#4950, #5352) a failed model download is shown
  in Activity with its reason, retried three times, then the steps that need the model wait with
  "Model download failed" and offer Retry or the next candidate; other steps run.
- `source.recipe.missing-key-never-substitutes` — **[GAP]** (#5364) a cloud step whose provider has
  no key waits with "Needs a key for <provider>" and Add Key…; no other model is used in its place
  unless the person chooses one, which is kept as an override.
- `source.recipe.take-without-missing-step` — **[GAP]** (#4949) a recipe naming a job this Fichero
  lacks can be taken without that step; the removal is recorded as an override "job not available"
  and offered back after Fichero is updated.
- `source.recipe.pinned-model-gone` — **[GAP]** (#5364) a pinned model that can no longer be fetched
  is reported by the check, naming the step, and the rule's next candidate is offered.

Sharing
- `source.recipe.publish` — **[GAP]** (#5364) a recipe can be published to the community catalogue
  on GitHub, which checks the schema, the pinned models, the referenced files and the licence on
  submission, or to Zenodo for a DOI; publishing is asked every time and sends no pages unless
  added, each listed first.
- `source.recipe.catalogue-search` — **[GAP]** (#5364) setup and the Inspector search the catalogue
  by script, language, period and purpose, and show each recipe's measurements.
- `source.recipe.update-check` — **[GAP]** (#5364) Fichero checks for new versions of followed
  recipes at most once a day, sending only recipe ids; offline, nothing is offered and nothing
  fails.
- `source.recipe.follow-and-update` — **[GAP]** (#5364) a project follows a published recipe at a
  version; a new version is offered with a step-by-step diff (steps, pins, prompt text, settings)
  and its measurements beside the old; taking it is the person's choice.
- `source.recipe.update-measured-here` — **[GAP]** (#5364) when an update changes steps that run on
  this Mac and the project has ground truth, the new version is measured on the project's pages in
  the background and shown beside the old.
- `source.recipe.update-new-work-only` — **[GAP]** (#5364) a taken update changes new work;
  re-running changed steps on existing pages is offered as one job, whose output arrives as new
  passes and readings.
- `source.recipe.overrides-kept` — **[GAP]** (#5364) a project's own changes (a prompt, a model, a
  setting, an extra or removed step) are kept as overrides on top of the followed version; an
  update replaces only what was not overridden and lists conflicting steps, keeping the project's
  own unless the person takes the author's.
- `source.recipe.fork` — **[GAP]** (#5364) a recipe can be forked into the project's own and
  published, naming the recipe and version it came from and crediting its authors.

Finding models
- `source.find.by-need` — **[GAP]** (#4948) the existing model recommender and language-fit score
  are extended (not replaced) to search by job, script, language, period and local-only, across an
  open list of sources including Kraken's repository and Hugging Face (→ #2116).
- `source.find.download-is-a-provider-row` — **[GAP]** (#4948) a downloaded model becomes a row under
  its provider, through the one catalogue's download path.
- `source.find.results-are-cards` — **[GAP]** (#4948) results are shown as cards, with licence
  class, size and whether this Mac can run them.
- `source.find.try-before-default` — **[GAP]** (#4948) a found model can be tried on chosen pages and
  measured before becoming a step's model.

Reader and language tools
- `source.reader.one-renderer` — **[GAP]** (#4948) one Reader renderer shows any script, direction
  and declared sign.
- `source.nlp.no-silent-fallback` — **[GAP]** (#4948) see `histnorm.language.no-silent-english-entity-model`
  (→ #4914), which owns this; not restated here.

### Models are nodes in the sidebar (ruled 2026-10-04, #5439)

A model is a thing the project has, like an entity or a workflow, so it is a node in the sidebar.
The node shows its card (`source.model.one-card`); nothing is kept only for display. Where the node
kind sits in the sidebar is the sidebar's (`ui/modes-to-panes.md`, `ui/sidebar-crud.md`; #4335).

Corrected by the maintainer, 2026-10-04: models do NOT generally live in the sidebar. They live in
Settings, downloaded or imported (`settings.models.import`, #5460). **Training** is the sidebar
node; a model appears in the sidebar only inside a training node, as its base or what it produced.

- `source.model.node-in-sidebar` — **[PARTIAL]** (#5439, #4335) *Built (engine): `GET /api/training/models`
  lists every model Fichero trained or fine-tuned on this engine, newest first, read from its card; a
  downloaded or imported model (no training card) is not listed. Tested in
  `fichero-server/tests/unit/training/test_trained_model_nodes.py`. Built (app): each project's sidebar
  shows a Training node listing those models (`SidebarTrainingNode`, `TrainedModelsStore`), drawn only
  when there is one; tested in `fichero/Tests/Unit/general/Models/TrainedModelsStoreTests.swift`. Not
  built: the base model as its own node inside Training (the Inspector names it), and a per-project
  list: the list is the engine's, since no card records the project it was trained in.* training is a node in the sidebar; the
  base model and every model a run produced show inside it. A model with no training stays in
  Settings only.
- `source.model.node-inspector` — **[OK]** (#5439) *Built (engine): `GET /api/training/model` gives
  one trained model's facts from its card: base, teacher, training set, job, when and where it trained,
  the newest held-out CER per normalisation policy (null before any evaluation) and every evaluation,
  size on disk, its builds and whether each is here, the base's licence (null for a Kraken reader, whose
  card names none) and `may_publish`, true only when the card says `not_for_release: false`. Tested in
  `fichero-server/tests/unit/training/test_trained_model_nodes.py`. Built (app): `ModelNodeInspector`
  shows provenance, the held-out CER per policy ("Not evaluated yet" before any evaluation), size,
  where it runs, the licence ("Unknown" when the card names none) and whether it may be published,
  with the reason when it may not; tested in
  `fichero/Tests/Unit/general/Models/TrainedModelsStoreTests.swift`. Read-only: the actions are
  `source.model.node-actions`.* selecting a model inside a training node shows its
  Inspector, read from its card: what it is; where it came from (a base and its training set); its
  scores on held-out pages (`distill.eval.stored-on-the-model-node`); its size; where it can run
  (`source.model.runs-here`); its licence and its release flag.
- `source.model.node-actions` — **[GAP]** (#5439) from the training node a person can train, fine-tune
  or distil again (the start sheet, `compute.tune.start-sheet`), test (an evaluation job,
  `distill.eval.job`) and publish, through the one audited action layer. The node keeps the history:
  every run, its data set, its scores and the model it produced.

### The vision base a fine-tune starts from (ruled 2026-10-04, #5442)

A smaller base trains and runs faster, so the default base for a vision fine-tune is a model of
about 3B, not 8B. The recipe picks it.

- `source.model.vision-base-catalogue` — **[GAP]** (#5442) the bases a vision fine-tune can start
  from are a catalogue. Each entry's size, licence and Hub availability are verified and dated, and
  an unverified fact says so. Today `training/vision_bases.py` lists only 7-9B models and
  Nanonets-OCR-s, and `DEFAULT_BASE` is `Qwen/Qwen3-VL-8B-Instruct`.
- `source.recipe.picks-the-tuning-base` — **[GAP]** (#5442, #4950) the recipe picks the base from
  the project's language, script and hand among the catalogue's candidates, preferring about 3B.
  Where several fit, the evaluation job (`distill.eval.job`) decides on the project's held-out
  pages. A base with a restricted licence can train but not be released (Sergio's data: train yes,
  release no). Ruled 2026-10-04: the default is Qwen3-VL-4B, with 2B as the fast choice; the recipe
  can pick others, and the evaluation decides.

Checked on the Hugging Face API on 2026-10-04: parameters from safetensors, licence from the card.

| Base | Size | Licence | Use |
|---|---|---|---|
| `Qwen/Qwen3-VL-2B-Instruct` | 2.13B | Apache-2.0 | the fast choice |
| `Qwen/Qwen3-VL-4B-Instruct` | 4.44B | Apache-2.0 | the default (ruled 2026-10-04) |
| `dots-studio/dots.ocr` (was `rednote-hilab/dots.ocr`) | 3.04B | MIT | candidate; needs trainer support for its custom code, unverified |
| `PaddlePaddle/PaddleOCR-VL` | 0.96B | Apache-2.0 | candidate; needs trainer support for its custom code, unverified |
| `nanonets/Nanonets-OCR2-3B`, `nanonets/Nanonets-OCR-s` | 3.75B | none declared; its base `Qwen/Qwen2.5-VL-3B-Instruct` is `qwen-research` | train yes, release no |
| `datalab-to/chandra-ocr-2` | 5.30B | modified OpenRAIL-M (research, personal, small companies) | over the ~3B target; not a default |
| `datalab-to/chandra` | 8.77B | modified OpenRAIL-M | too big for the default |

Unverified for every entry: whether an MLX build exists to read with the untrained base on this Mac.

## Requests to other specs (for the manager to route; nothing edited here)

- `ai/ai-settings.md`: the single catalogue's entries should take the card shape above, including
  embedding models (today chosen by an environment variable) and licence class. Its local-runtime
  "profile" (`llm/model_profiles.py`) should take another name (a runtime configuration), because
  **profile** here means a recipe's defaults. And a **Tesseract** provider row (binary built in,
  language data downloaded as data), as section 1 describes.
- `ui/` (the compare design, still a proposal): Try Another Option… needs panes that show two
  passes or readings side by side with a diff lens, and list views for entities and statements.
- `source/source-model.md`: its glossary rows for **profile** and **recipe** should point here (a
  profile is a recipe's defaults section; a recipe is more than a chain), and its ruling 10's
  "project settings window" is settled as the Inspector (ruled 2026-10-01).
- `ui/activity-and-automatic-work.md`: its request for an `automatic` section is met by the
  resolved recipe (`source.recipe.steps-name-layers`), worked out from the purpose, not written in
  the shared file.
- `ai/ai-settings.md` (section M): a picker row could show what a card knows (suits, local or
  cloud, licence class).
- `ui/workflows.md` / `ui/workflow-node-config.md`: steps declare a job; a chain is checked before
  it runs; the general "segments to any reader" step replaces `economy_htr` and its kin; the drift
  between `kraken_model` and `kraken_recognition_model` disappears when the model is a card.
- `compute/remote-compute.md` asked that a card can say "also present on these targets" and
  "trained by this job": accepted in principle, to be added to the card shape with #4948.
- The Reader specs: two renderers exist, one declaring itself English.

## Test matrix

To be filled at approval. The legs this slice will need, so the gap is visible:

| Leg | Pins |
|---|---|
| Backend (pytest) | the recipe schema (valid, newer version, unknown job, code refused, missing prompt variable); the assembly rules (same answers and catalogue, same recipe; filter and rank order; volume rule; no-LLM-correction rule; "needs a model"); combination pruning (never more than nine); the resolved recipe and its `automatic` section per purpose; overrides through an update; the check's report for each failure row; each coverage-table fixture; each job family's comparison |
| MCP / CLI | the resolved recipe, the check, the catalogue search and Try Another Option return the same as the app |
| Click-around (Mac) | setup's six screens on a fixture folder, each explaining itself; Start enqueues the automatic steps in Activity; the Inspector shows and edits the recipe; Try Another Option on two pages, then Use This for a folder |
| Named-machine | the flagship measured on real Spanish pages; the Cherokee journey on real syllabary scans |

## Rulings

- **2026-10-04 (#5444, refines #5217):** in a recipe, a page's text is tied to its lines
  automatically wherever the alignment scores above a match threshold. A line whose alignment is
  doubtful is still given its best stretch, but it is flagged for review and stays out of the
  training set until a person checks it. This refines #5217's rule (run by itself only where the
  match is known to be perfect) for the recipe step; the hand-run Align Text to Lines tool keeps its
  confirm-the-pass flow.
- **2026-10-05 (#5477 to #5482), setup round 2:** first run asks where the project lives and saves
  into it; purposes and material are checkboxes, any combination; "nothing runs automatically" is
  its own screen; a fifth way in, Keep arranged; languages, scripts and direction are chosen, with
  search and a browse menu, several as tokens, a language stored as its tag; no disclosure
  chevrons; one sentence per step; a step's problem once, in words, with the fix as a button; never
  a raw model id. The screens: section 7b.

## Open questions (with recommendations)

Ruled 2026-10-01 (former questions 1-4):
- **Answered** (this spec, ruled 2026-10-01): Training runs automatically only if chosen in setup; otherwise offered, never started. **Training can be automatic when the person chose it in setup.** Onboarding offers training as
  part of the recipe, with a good default (for example: distil from a large model such as a
  frontier LLM as the teacher, then fine-tune a small one); if chosen, the train step runs when its
  condition is met. If not chosen, it is offered when the condition is met, never started.
  (`source.recipe.train-never-automatic` is refined accordingly.)
- **Answered** (this spec, ruled 2026-10-01): A new recipe version shows an update symbol; re-runs are offered only after the person updates. **A recipe change never changes the person's data by itself.** When the recipe a project follows
  has a new version, the Inspector shows an update symbol; clicking it shows the diff and updates
  the recipe; only then is a re-run of existing pages offered, as one job with its estimate. Nothing
  runs out of the blue.
- **Answered** (this spec, ruled 2026-10-01): Asked once per project and visible in the recipe editor. **Ask once about the cloud, and don't ask too much.** Whether pages may leave the Mac is asked
  once for the project, at setup or at the first cloud use, whichever comes first, and is always
  visible and changeable in the recipe editor (every cloud step is marked there). It is not asked
  again per provider or per step.
- **Answered** (this spec, ruled 2026-10-01): Random stratified sample of at least 20 pages and 100 corrected lines, with confidence ranges. **The bake-off must be useful; Fichero decides the sample.** It asks for a good number of
  pages, or uses them all, and draws a **random, stratified sample** (across folders, hands and
  page kinds) of at least 20 pages where the project has them, with at least 100 corrected lines;
  each rank shows its line count and a confidence range, and candidates within one point of CER
  are marked "too close to call". Below the minimum it still runs and says its result is only
  indicative.

5. **Where does the flagship's measurement come from?** It needs real pages of historical Spanish letters,
   notarial and administrative records with ground truth that can be published. *Recommend:* the app's two
   heaviest users' corrected pages, measured privately, with the published `measurements.yaml`
   pointing at public IIIF pages of comparable material (or stating "private: N pages"), so no
   unpublished archive page leaves.
6. **The catalogue's home.** *Recommend:* a `fichero-recipes` repository under the project's own
   GitHub organisation, mirrored to Zenodo by release, as HTR-United does for training sets.
7. **Where the carbon figures come from.** There is no agreed per-page figure for cloud models.
   *Recommend:* a small vendored table, like the price list, of chip power draws, GPU ratings and
   grid figures, with its sources cited; cloud "unknown" unless a provider publishes a figure;
   always labelled an estimate, and last but one in the ranking order, so a guess never outranks
   a measurement or a price.
8. **The volume limits** (500 dollars, 30 days) at which a candidate is shown but not chosen.
   *Recommend:* keep them as engine constants for now, shown in the explanation ("not chosen:
   about 7,500 dollars for 500,000 pages"), rather than a budget setting; revisit if people ask
   for a budget.
9. **Two-page spreads: split into page documents, or mark page regions?** (#5452, #5427) Ruled so
   far (2026-10-04): **Mosquera is not split**; its whole photographs stay the pages, and its
   recipe has no split step (Preview's one-page view, #5427, covers seeing one side). Open, with two
   options:
   - (a) **Split at import**, as the first step of preparing images: setup sees two-page spreads (or
     the person says so), and the spread becomes two page documents before any line is found or
     any text is read, so every later step works on the halves and nothing has to be carried over.
   - (b) **Page regions**: the photograph stays one document; setup marks each page on it as a
     page-kind region; Preview can show one region (#5427); each line belongs to its page region;
     the lines mode, export and the site work per page region.
   *Recommend (b):* nothing is destroyed or carried over, the photograph stays the evidence, and it
   is IIIF's own model (pages as regions of one canvas). It needs: the engine half of #5427 (page
   regions stored as regions of kind page, a line's page region worked out from its polygon); export
   and the site per page region (#5427); reading orders and "already done" counted per page region.
   Whichever is chosen, a split run on a spread that already has lines carries them over
   (`source.split.carries-readings-over`).

10. **Keep arranged: arranged by what?** (#5480) Options: (a) the **project's structure**, the
    folder mirrors the project's own folders in the sidebar (a document moved in the project moves
    its files); (b) **date**, year then month, from the document's date or, lacking one, the file's;
    (c) **a written rule**, a path pattern over metadata fields (`{collection}/{year}/{box}/{item}`).
    *Recommend (a)* for the first build: it needs no new setting, the person already arranges the
    project, and the folder then reads like the sidebar; (c) later as the Inspector's way to change
    it, with (b) as one shipped pattern.
11. **Keep arranged: files moved by hand, and file names.** *Recommend:* a file the person moves by
    hand stays where they put it and is recorded as placed by hand (Fichero never fights the
    person; Arrange Again offers to bring it back); files are renamed only to resolve a clash
    (`name 2.jpg`), never to a scheme, until a rule asks for one.
12. **The five new purposes** (Statements, Translate or normalise, Gather quotations, Catalogue my
    sources, Tables and forms; section 7b screen 2). *Recommend:* add all five as purposes (each is
    a reason someone starts a project, and checkboxes make extra purposes cheap); keep image
    clean-up, reading order, check, export and train as jobs on How it will be done, not purposes.
13. **Hands.** No job tells hands apart today. *Recommend:* register a `tell-hands-apart` job (a
    region or line property, with the topic's sentence) before setup offers it; until then setup
    does not mention hands.
14. **Which jobs get a details screen** (section 7b screen 5). *Recommend* the five named (entity
    kinds, translate or normalise, gazetteer, catalogue fields, table columns), each only when its
    job is ticked; everything else defaults and is changed in the Inspector.
15. **The default location** (#5482). *Recommend:* `~/Documents/Fichero/<name>.fichero`, the folder
    made if missing, so projects sit together and inside the folder the sandbox already asks for;
    Choose… for anywhere else.

**Not asked** (already decided by rulings): purpose first; purpose decides layers; offer, never
hide; the recipe's contents; deterministic rules; the flagship and generated paths; the bake-off;
the Inspector as the one surface; egress asked once and shown in the recipe editor; recipes as shared folders, data not code,
no keys; per-folder recipes; jobs as a registry.

Older questions were ruled on 2026-09-19 and 2026-10-01: see `source-model.md`.

## Sources

- HTRMoPo: https://github.com/mittagessen/HTRMoPo · Kraken repository: https://kraken.re/6.0.0/advanced/repo.html · https://zenodo.org/communities/ocr_models/records
- HTR-United: https://htr-united.github.io/catalog.html · CATMuS: https://huggingface.co/datasets/CATMuS/medieval · Teklia PyLaia: https://huggingface.co/collections/Teklia/pylaia
- Hugging Face model cards: https://huggingface.co/docs/hub/model-cards · API: https://huggingface.co/docs/hub/api
- RO-Crate and Workflow RO-Crate: https://www.researchobject.org/ro-crate/ · https://about.workflowhub.eu/Workflow-RO-Crate/ · WorkflowHub: https://workflowhub.eu
- CWL: https://www.commonwl.org/
- Transkribus public models: https://help.transkribus.org/public-models
- OCR-D tool description: https://ocr-d.de/en/spec/ocrd_tool · Arkindex runs and models: https://doc.teklia.com/arkindex/processes/worker_runs/ · https://doc.teklia.com/arkindex/models/
- eScriptorium quick start: https://escriptorium.readthedocs.io/en/latest/quick-start/
- YALTAi: https://github.com/PonteIneptique/YALTAi · Ultralytics licence: https://www.ultralytics.com/license · Surya model licence: https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE
- Apple document reading: https://developer.apple.com/videos/play/wwdc2025/272/
- LatinCy: https://spacy.io/universe/project/latincy · Stanza: https://stanza.stanford.edu
- Embedders: https://huggingface.co/intfloat/multilingual-e5-large · https://huggingface.co/BAAI/bge-m3
- CHURRO: https://arxiv.org/pdf/2509.19768 · Benchmarking LLMs for HTR: https://arxiv.org/pdf/2503.15195

The 2026-10-01 model search (section 8c) cites its own sources, among them PP-OCRv6
(https://zenodo.org/records/21788410), TRIDIS v2 (https://zenodo.org/records/13862096), McCATMuS
(https://zenodo.org/records/13788177), Muharaf (https://zenodo.org/records/14295489), the medieval
TrOCR family (https://huggingface.co/medieval-data), CHURRO (https://github.com/stanford-oval/Churro),
Tesseract's data list (https://tesseract-ocr.github.io/tessdoc/Data-Files.html) and HTR-United's
schema (https://htr-united.github.io/document-your-data.html).

Not verified in this pass: what Apple Vision does with handwriting,
right-to-left, vertical text and single-line pictures (to be probed at run time); a fair
comparison of line-by-line against whole-page reading by vision-language models; whether the
Hugging Face revisions in the example exist (they are illustrative).

## Triaged from the backlog (2026-10-04)
- `source.segments.align-page-text-to-lines` **[GAP]** (#5217): when a page's text belongs to the page and not to its lines, the Segments list says so ('text on the page, not aligned to lines') and offers one Align Text to Lines tool, as a dialog or a tool option, whose result is a pass the person confirms. Run by hand, it runs by itself only where the match is known to be perfect, such as a reliable import (ruled 2026-10-01). In a recipe the tie is automatic above a match threshold, with doubtful lines flagged for review and kept out of the training set until checked (ruled 2026-10-04, #5444; see `source.job.tie-text-to-lines` and Rulings).
