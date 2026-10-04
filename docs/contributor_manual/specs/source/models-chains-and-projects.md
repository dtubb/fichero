# Source Model — Models, recipes, projects and setup — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Setting up a project" section: the purpose question and what each purpose
> runs by itself; what setup asks and what it works out; the recipe it makes, and how to see
> and change it in the Inspector; checking models on your own corrected pages; taking,
> following, updating and publishing a recipe; finding a better model; how to see how any
> reading was made.
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
| 6 ✱ | Check, by Fable or a person | `check` | no start or results screen | `POST /api/check/runs` | `fichero_check_run`, `_status`, `_verdicts`; the teacher-line check is missing (#5446) | a `check` job | PARTIAL (#5404, #5446; `source.check.run-is-a-job`) |
| 7 ✱ | A clean set | training set | none | `POST /api/export/training` (no app caller) | missing (#5455) | none | GAP (#4947, #5446; `source.train.human-checked-by-default`, `recipe.distil.damaged-text-stays-out-of-training`) |
| 8 ✱ | Train small models, choosing where | `train-a-model`, base from the catalogue | the start sheet (`compute.tune.start-sheet`), not built | `POST /api/training/kraken`, `/vision-lora`, `/reasons` (Hugging Face); Rorqual not yet | `fichero_train_kraken`, `fichero_train_vision_lora`, `fichero_training_status`, `_cancel`, `fichero_gather_reasons` | `train-a-model`, `convert-a-model`, `gather-reasons` | engine PARTIAL, app GAP (#5440, #5119, #5240); base Qwen3-VL-4B (#5442); nothing trains on this Mac by default |
| 9 ✱ | Evaluate against out-of-the-box small OCR models, per script and hand | the evaluation job | none | none yet; pieces: CER scoring, `/reasons-ab`, model comparison | missing (#5441); `fichero_reasons_ab`, `fichero_compare_readings` are pieces | (to be) one job, a row per model and page | GAP (#5441; `distill.eval.job`) |
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
never what can be reached** (ruled 2026-10-01: offer first, never hide).

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

**The step order below is provisional: to be aligned with the maintainer's step document
(2026-10-02),** which will be the source for the order and wording of the steps. What is fixed
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
- `source.job.tie-text-to-lines` — **[GAP]** (#5444) a page's reading is tied to its lines for free, on
  this Mac: Kraken finds the lines, a Kraken reader reads each roughly, and the page's best reading is
  aligned to them in order by the characters they share (a monotonic alignment; no line takes text
  from beyond its neighbours'). Each line gets the stretch of the page reading it matches; a line, or a
  stretch of text, that does not align above a set score is left untied and counted, never forced. The
  new pass names Kraken for the shapes and the page reading's model for the text. The page's best
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
- `source.lines.reading-checked-against-the-page` — **[GAP]** (#5446) each model reading of a Kraken line
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
- `source.recipe.start-runs-the-steps` — **[OK]** (#5390; built: `recipes/runner.py`, the `run-a-recipe` job; tested in `fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py`) pressing Start runs the recipe over the
  project's material: its steps in order, each as the job its card names (a shipped workflow run for
  splitting pages (`Split Pages`), finding lines, reading a line (with a Kraken reader, or Kraken's lines
  read by a vision model: `Read Lines (Kraken lines, vision model)`) or a page, correcting, finding names and
  finding statements; a check
  run for `check`; the project's synced folder for `export`), together as one `run-a-recipe` job in
  Activity whose children are those runs; a step starts only when the one before it has finished,
  and a step that fails stops the steps after it, saying which.
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
- `source.onboard.purpose-first` — **[PARTIAL]** (#4951) **Built 2026-10-03 (app + engine):** first run's Purpose step lists the engine's purposes (GET /api/recipes/purposes) before material; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`, `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`. setup's first screen asks the purpose, from the
  table's purposes in plain words, "Not sure yet" included; the purpose is stored on the project
  and shown in its Inspector.
- `source.onboard.purpose-sets-layers` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** purpose to steps in `assemble()` (`PURPOSE_STEPS`); running layers automatically at import is not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the purpose decides which layers run at
  import, as the table says: the NLP layer runs by itself only where the purpose uses entities, and
  lines only where it includes them (refines the NLP and Kraken rulings, 2026-10-01).
- `source.onboard.offers-never-hides` — **[GAP]** (#4951) a purpose changes what is offered first
  and what runs by itself; every view and tool stays reachable in every project.
- `source.onboard.just-do-it` — **[OK]** (#4951, #5390; built: an import after Start queues one recipe run over its pages (`importers/derivatives.queue_derivatives`)) on a "just do it" purpose, after Start, new
  material runs through the recipe's automatic steps with no further question: each import is one
  `run-a-recipe` job over the pages it brought, and nothing runs for material already there.
- `source.onboard.tools-not-automation` — **[PARTIAL]** (#4951; built: nothing runs at import on a tools purpose; offering its tools first is the app's) on a "tools" purpose (edit, decipher,
  train, not sure), nothing runs at import that the person did not ask for, and that purpose's
  tools are offered first.
- `source.onboard.add-layer` — **[GAP]** (#4951) a layer or a language can be added later from the
  library's Inspector; an added layer turns on the recipe's steps of that layer and runs them over
  everything already in the project, as one job.
- `source.recipe.steps-name-layers` — **[GAP]** (#4950) every step names a layer; the resolved
  recipe's `automatic` section lists the steps whose layer the purpose (or an added layer) turns
  on, with whether each may use the cloud, and is never written by hand.

Setup
- `source.onboard.widget-and-search` — **[PARTIAL]** (#4951) **Built 2026-10-03:** the Your Material step searches languages and scripts through the engine (2026-10-04: `RecipeSetupStore.searchLanguages`/`searchScripts`; a dialect shows whose dialect it is, a Glottolog-only language is kept as a private-use tag). The engine searches ISO 639-3 joined with Glottolog 5.3 (CC BY 4.0, vendored; languages ISO lacks and about 13,000 dialects, each answer with its BCP 47 tag and glottocode kept apart) and every ISO 15924 script: `GET /api/recipes/languages`, `/scripts`, `fichero-server/tests/unit/api/test_setup_searches_languages_and_scripts.py` and `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. setup is a form with search beside each
  field, not a conversation.
- `source.onboard.screens-in-order` — **[GAP]** (#4951) setup asks the purpose first and shows
  Start last, with its screens in one fixed order (provisionally the six of section 7; to be
  aligned with the maintainer's step document of 2026-10-02); it can be closed at any screen with
  the answers kept as a draft, and nothing runs before Start.
- `source.onboard.teaches-the-method` — **[GAP]** (#4951) across its steps setup explains each topic
  of section 7a (languages, scripts, fonts, glyphs and Unicode, a faithful way to write the script,
  finding sources, models and memory, Kraken, layout, tables, workflows and recipes, entities,
  statements, maps, calendars, normalisation, output formats, fine-tuning, remote compute) with an
  example from the person's own pages where there are some.
- `source.onboard.topics-written-once` — **[GAP]** (#4951) each topic's and each job's explanation
  is stored once, with its job or topic in the registry, and the same text is shown in setup, the
  Inspector, an exported recipe's README and the user manual.
- `source.onboard.set-up-later` — **[PARTIAL]** (#4951) **Built 2026-10-03:** Skip leaves the project unset and saves nothing; `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`. "Set up later" makes a project with no settings
  that behaves as today, and Set Up… in its Inspector runs setup at any time.
- `source.onboard.samples-first` — **[GAP]** (#4951) given material, setup picks up to ten sample
  pages spread across it (first, last, evenly spaced, largest and smallest), which the person can
  swap; from them, where a local model is available, it suggests scripts, languages, material,
  period and layout, each labelled "suggested from your pages" until accepted.
- `source.onboard.five-questions` — **[GAP]** (#4951) beyond the purpose and the material, setup
  asks at most five things (scripts, languages, material and period, layout, whether pages may
  leave), and the last only when a step would use the cloud.
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
- `source.onboard.estimate-before-start` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** the Start plan carries the page count and the cost per run (free on this Mac, unpriced cloud models null); time, carbon and the main alternative's estimate are not built; pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/api/test_start_is_the_first_yes.py`. screens 4 and 6 show the whole
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
- `source.onboard.derives-not-asks` — **[PARTIAL]** (#4951) *Built (engine): `GET /api/recipes/derived?scripts=` (`recipes/derived.py`) answers, each fact with where it came from: per script its direction (the language policy's own rule) and whether it may be vertical (then setup asks, since only the pages settle it), the bundled font for a script macOS lacks (Syriac, Mongolian, Coptic, Cherokee), this Mac's chip and memory, the providers with a key (names only) and the places work can run (this Mac, Hugging Face when its key is present, configured clusters); pinned by `fichero-server/tests/unit/recipes/test_setup_derives_not_asks.py`. The app's Your Material step shows each chosen script's direction, bundled font and "may be vertical" (`RecipeSetupStoreTests`, 2026-10-04). Not built: line position, correcting a derived fact on screen.* direction, line position, fonts, this Mac's
  chip and memory, keys present and compute targets are worked out, shown, and correctable, never
  asked.
- `source.onboard.ground-truth-from-files` — **[GAP]** (#4951) corrected transcriptions given at
  setup (PAGE, ALTO, TEI, or plain text named after its image) come in through the one import path
  as person-made passes marked ground truth, and the bake-off uses them.
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
- `source.onboard.says-no-model` — **[PARTIAL]** (#4951) **Built 2026-10-03:** a step with no fitting model shows its gap in words; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. where no candidate passes the hard constraints
  for a step, setup says so in words and proposes the hand-transcribe, draft-and-correct and
  train routes; it never substitutes silently.
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
- `source.try.bakeoff-is-the-same-tool` — **[GAP]** (#4950, #4951) setup's bake-off is Try Another
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

- `source.model.node-in-sidebar` — **[GAP]** (#5439, #4335) training is a node in the sidebar; the
  base model and every model a run produced show inside it. A model with no training stays in
  Settings only.
- `source.model.node-inspector` — **[GAP]** (#5439) selecting a model inside a training node shows its
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

## Open questions (with recommendations)

Ruled 2026-10-01 (former questions 1-4):
- **Training can be automatic when the person chose it in setup.** Onboarding offers training as
  part of the recipe, with a good default (for example: distil from a large model such as a
  frontier LLM as the teacher, then fine-tune a small one); if chosen, the train step runs when its
  condition is met. If not chosen, it is offered when the condition is met, never started.
  (`source.recipe.train-never-automatic` is refined accordingly.)
- **A recipe change never changes the person's data by itself.** When the recipe a project follows
  has a new version, the Inspector shows an update symbol; clicking it shows the diff and updates
  the recipe; only then is a re-run of existing pages offered, as one job with its estimate. Nothing
  runs out of the blue.
- **Ask once about the cloud, and don't ask too much.** Whether pages may leave the Mac is asked
  once for the project, at setup or at the first cloud use, whichever comes first, and is always
  visible and changeable in the recipe editor (every cloud step is marked there). It is not asked
  again per provider or per step.
- **The bake-off must be useful; Fichero decides the sample.** It asks for a good number of
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
