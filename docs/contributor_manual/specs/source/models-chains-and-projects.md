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
  Built: the tools named in the table, and (R0 2026-10-17, read in `fichero-mcp/src/fichero_mcp/openapi_tools_generated.py`) the
  recipe setup tools (`fichero_recipes_get_project_setup`, `_save_project_setup`), `routes_for_volume`, `start_project`,
  `get_start_plan`, `choose_samples` and `use_candidate_for_step`, so the table's MCP column for steps 1, 2, 5 and 10 is
  stale where it says missing. The true residue: a Hugging Face Hub publish (step 14), a clean-set export as a step (step 7),
  and evaluate and choose as steps of their own (steps 9 and 10).

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

**Superseded in part by section 7c (ruled 2026-10-11, #5668):** What you want to do becomes Choose the
Stages, with one page per chosen stage, and Train gets its own page; the rest of this section stands.

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
list tags ("es") (#5479). Direction is worked out from the script, never chosen (ruled 2026-10-18). Each
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

1. **Where it lives** (#5482). The project's name (default "Untitled Project", the Finder/Pages convention, ruled 2026-10-10) and where it lives: **Inside
   Fichero** (the default, the app's own container) or **Choose a location…**, which opens a save
   panel (ruled 2026-10-05, revised the same day). Continue makes the `.fichero` package there through the one create path
   (`LibraryManager.createProject(at:)`, which grants the folder and has the engine open it with
   `POST /api/library`), and from then on setup reads and writes through **that project's**
   client, the same path as Set Up… from a project. A location that cannot be written is refused
   on this screen in words ("Fichero can't write to that folder. Choose another."), and the
   person stays on it. This is what fixes the first-run 400 (#5477): there is always a project to
   save to.
2. **Your material** (#5480). How material comes in, five ways, each with one sentence of what it
   does to the originals: **Link** (read where they are, never changed), **Copy** (the default; the
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
   - **Direction**: not asked (ruled 2026-10-18, #5788). It follows from the script (the engine's derived fact, `recipes/answers.default_direction`) and is saved with the answers; setup shows it only as a fact under the script ("Left to right"), and a project that must differ changes it afterwards on the source (`SourceDirectionMenu`). *Test:* a script with no chosen direction reads as the derived one (`SetupThreeWaysInTests`); the engine fills `answers.directions` from the script when none is sent (`recipes/answers.py`).
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

#### Everything automatic after Start (review 2026-10-07)

**The goal (the maintainer's, paraphrased).** A person brings material (a folder, a box of loose
pages, PDFs, notes), answers the four steps, and presses Start. From then on everything happens by
itself: the right reader for the language, script and hand is chosen and checked, the pages are
read, names, places and dates are found, and the material is **organised** (Find the Documents:
boundaries, kinds as prototypes, groups or cases, their order, the canvas). The person never drives
a step by hand, always sees progress and results, and nothing fails without saying so.

**How this was reviewed.** Read on disk in the `lead` worktree on 2026-10-07, nothing run: the four
steps (`FirstRunWindow`, `RecipeSetupPlanFields`, `RecipeStepsView`, `RecipeSetupStore`), the engine's
`recipes/assemble.py`, `start.py`, `runner.py`, `done.py`, `jobs.py`, `answers.py`, `seed/cards.yaml`,
`api/routes/system/recipes.py` and `importers/derivatives.py`, against `source/finding-documents.md`,
`compute/jobs-and-fine-tuning.md` (memory, runs, read again) and `ui/activity-and-automatic-work.md`.
Three cases were traced end to end.

**The order after Start, by kind of material (the target).** Each stage is a job with its rows in
Activity; a stage that cannot run says why and the stages that do not need it carry on.

| Material | After Start, in order |
|---|---|
| **Images of loose pages** (a box: Istmina) | 1 look at the pages: blank pages, recto/verso pairs, duplicate shots; a sample of about ten suggests script, language, material and hand → 2 prepare damaged images where the sample shows damage → 3 find lines → 4 read: a strong reader reads the sample, the check removes its misreads, the candidate readers are compared on it, the winner reads the rest, each page by the reader for its material and hand → 5 correct where unsure → 6 names → 7 dates → 8 statements, if ticked → 9 **organise**: Find the Documents proposes boundaries, kinds as prototypes, groups and order, drawn on the canvas for review → 10 search (vectors follow every reading) → kept exports → a summary of what was found |
| **Bound volumes** (a diary across volumes: Marshall) | as above, run **volume by volume** (one batch per folder, so the first volume is finished and readable early, #5540), with step 9 splitting each volume into **dated entries** rather than finding boundaries between documents; once enough lines are corrected, the offer to train the project's own reader comes by itself |
| **Text already** (a slip box of md/txt notes, Word, a PDF with a text layer) | 1 count, and detect the language from the text → names → dates → statements, if ticked → organise (groups by shared names, links and likeness; canvas) → search. No lines and no reading (#5553) |

**What happens today, case by case.**

*(a) Istmina: 203 page images of 1940s Spanish court papers, handwritten and typed.*
- **Setup asks:** the project's name and place; the way in and Add a Folder…; material (Handwriting is
  ticked by default; the person must tick Typescript); languages and scripts typed by hand (`es`, `Latn`;
  nothing is suggested from the pages, and the plan is not proposed until both are given); the purposes
  (say, The full knowledge graph) and which kinds of names. Ready shows the plan, the cloud question
  only when a cloud model would fit, and "203 pages · free, runs on this Mac". No time, and not the
  peak-memory sentence the engine already writes for a step on this Mac's model server.
- **The plan:** lines and reading as one Kraken run, the reader chosen by rule. PP-OCRv6 ranks first
  because its card carries a published aggregate CER of 3.9% over 44 languages, and no other reader
  has a figure; the same reader measured 24.6% on Mosquera pages on 2026-10-05/06. Then correcting
  with the 3B local vision model (the 7B is refused on 8 GB), names with spaCy's Spanish pipeline, and
  dates by the Gregorian rules. Statements and authority links have no model card, so setup shows them
  with a problem and a fix. Search **has** a card in setup, but Start has no runner card for
  `make-a-vector`, so the plan skips it with "no card runs the job yet". Vectors do still come from the
  import's embed job and the re-embed after changes, but the plan never says so. The typescript reader
  that the recipe assembles under `readers` is never used, because the runner reads every page with
  the default (handwriting) reader. No purpose brings image preparation, page splitting or Find the
  Documents, and Start has no card for them.
- **What runs:** one `run-a-recipe` row. Kraken lines and reads all 203 images, about a hundred of them
  blank versos; then correcting, names and dates, each step across every page before the next starts
  (one model load per step, as `compute/jobs-and-fine-tuning.md` rule 8 asks).
- **What the person sees:** Start closes setup, and the project opens with nothing pointing to the
  run. The skipped steps are in the plan's `skipped` list and the run's detail, but the app never reads
  either, and it has no caller of `/api/recipes/project/runs`. When the run ends, its row says "Done: N
  steps run, K skipped (see why)", with no account of what was found. Pages that failed inside a step
  are shown on that step's workflow row and are not counted on the recipe's row.
- **Where it stops:** transcriptions, names and dates on 203 flat pages in one folder. There are no
  documents, kinds, cases, order or canvas: none of the organising happens.

*(b) Marshall: an English diary in cursive, across several volumes.*
- **Setup asks** the same questions (`en`, `Latn`, handwriting typed and ticked by hand). The volumes
  come in through Add a Folder…, either one folder per volume or their shared parent.
- **The plan:** the same reader by the same published aggregate, the 3B corrector (`en`), names with
  spaCy's English pipeline, and dates. `split-into-entries` is in the job registry, but no purpose
  brings it and Start has no card for it.
- **What runs:** each step across every page of every volume before the next step starts. At thousands
  of pages no volume is finished early (`compute/jobs-and-fine-tuning.md` rule 9, #5540, not built).
- **What the person sees:** as in (a). The train step is assembled as `offered_when: 2,000 corrected
  lines`, but nothing in the engine watches that count and the app never reads the plan's `offered`. So
  the offer to fine-tune Kraken on Marshall's own hand never arrives, though this is the clearest case
  for it (section 14).
- **Where it stops:** read and corrected pages, names, and dates attached to pages rather than entries.
  There are no dated entries and no reader trained on this hand.

*(c) A slip box: a folder of born-digital md/txt notes (#5553).*
- **Setup asks** for a material, with no "already text" choice (Handwriting by default), and for a
  language and a script before it proposes anything.
- **The plan:** every purpose except Decipher and Not sure brings `find-lines` and `read-a-line`. A
  recipe's inputs start from page images (`jobs.STARTS_WITH`), so a recipe made only of names, dates and
  search fails the recipe check. Not sure runs nothing.
- **What runs:** Kraken is pointed at files that have no image, because files without pages count as
  units of work. At best it does nothing. At worst the step fails, and names and statements say "not
  run: needs line readings". This must be confirmed on a fixture.
- **What helps today:** the import embeds the notes' text, so search works, and the NLP draft runs if
  its setting is on.
- **Where it stops:** searchable notes with no names, dates, links or arrangement, unless each step is
  run by hand.

**The memory and the 8 GB Mac.** The runner already loads each model once per step. What is not built
(#5537): the budget across runtimes, letting MLX, spaCy and the embedder go between steps, and the
plan's peak memory across steps. Ready shows none of it.

**Gaps, as behaviours.**
- `source.onboard.auto.no-hand-driving` — **[PARTIAL]** (#5492) after the four steps and Start, the
  person is asked nothing more except where money is spent or pages would leave the Mac: one question,
  in one place, with the run waiting on it and saying so. Built: the four steps and Start. Not built:
  the stages below.
- `source.onboard.auto.plan-shows-what-will-not-run` — **[PARTIAL]** (#5573) Ready lists every step
  the Start plan skips (`skipped`) with its reason and fix button, and every model that must be fetched
  (`downloads`) with its size and a Download button. Start is never pressed without the person seeing
  what will not run. **Built 2026-10-07 (engine + app), not yet seen:** each skipped step carries its
  `fix` (`choose-model`, `allow-cloud`, or none when setup cannot fix it: a job no card runs, a condition,
  a site with no folder, a calendar), set in `recipes/start.py`'s `skip`; Ready shows Will not run (title,
  why, the fix button through setup's one fix handler) and To download first (model, size, the steps it
  serves, Download through `POST /api/local-models/download/{runtime}/{model}`, then Downloading…)
  (`RecipeSkippedRows`, `RecipeDownloadRows`, `ModelDownloads.start` since #5620). Pinned by
  `fichero-server/tests/unit/recipes/test_run_visible_to_spec.py` and
  `fichero/Tests/Unit/general/Models/RecipeRunVisibleTests.swift`. *Not built:* the plan reading again by
  itself when a download finishes (Ready re-reads it when the plan changes). A fix setup has no button for
  (a job done by hand, a reader to choose) is said in the `why`, and `fix` is then none (#5574).
- `source.onboard.auto.every-proposed-step-runs` — **[OK]** (#5574; built 2026-10-07: `start.START_JOBS`,
  `assemble()` puts a job Start has no card for under the recipe's `by_hand` and never among its steps, the plan
  lists each in `skipped` with why and the workflow or tool that does it by hand; search runs as an `embed` card,
  the `make-a-vector` job for each page, and the rules name the engine's own search embedder; tested in
  `fichero-server/tests/unit/recipes/test_every_step_runs_to_spec.py`. Wired: `make-a-vector`. No longer proposed as a step, because Start has no card and no shipped
  workflow can take the step's model or read its inputs: the other twelve below; a layer whose jobs Start cannot
  run is not addable) setup never proposes a step
  that Start has no card for. Each registered job either has a card in `start.py` or is not offered as
  a step that runs by itself. Jobs with no card today: `make-a-vector`, `link-to-authorities`,
  `place-in-a-gazetteer`, `prepare-the-image`, `find-documents-in-a-folder`, `put-in-order`,
  `split-into-entries`, `translate-transliterate-normalise`, `pull-out-passages`,
  `describe-for-the-catalogue`, `extract-to-a-table`, `find-regions` and `find-a-tables-cells`. Search is
  the first fix: its step is the embed job that already follows every reading, and the plan says so
  rather than "skipped". *Test:* for every purpose, the assembled recipe's steps that have a model all
  appear in the Start plan's `runs`.
- `source.onboard.auto.runs-by-itself-honoured` — **[OK]** (#5478; built 2026-10-07: the import hand-off's plan
  reads `answers.automatic` (`plan_start(automatic=…)`), so with Nothing runs automatically nothing is queued and
  an unticked step is in the run's `skipped` saying it runs only by hand; Start, pressed by hand, runs the recipe
  once as screen 8 says; tested in `fichero-server/tests/unit/recipes/test_every_step_runs_to_spec.py`) the import hand-off reads
  `answers.automatic`. With Nothing runs automatically, an import after Start queues no recipe run;
  otherwise it runs only the ticked steps. Today `runner.material_arrived` reads only the purposes, so a
  person's "nothing" or an unticked step is ignored without a word.
- `source.onboard.auto.on-add-refusal-said` — **[OK]** (#5575; built: `runner.refused`,
  `jobs.record_not_run`; tested in `fichero-server/tests/unit/recipes/test_run_visible_to_spec.py`) an
  import after Start whose recipe cannot run (the plan has refusals, or nothing runs) leaves a row in
  Activity saying why and what fixes it: a `run-a-recipe` row, failed, started by `import`, whose reason
  names the pages, the plan's refusals in its words (each with its fix) and that Set Up… › Ready shows
  the plan; the new pages are not read.
- `source.onboard.auto.lands-on-the-run` — **[PARTIAL]** (#5576, see #5555) after Start, the project
  window shows the run: each stage, pages done and left, time left, and what is waiting and why (memory,
  a download, another run). **Built 2026-10-07 (engine + app), not yet seen:** Start closes setup onto
  the recipe run's Activity details (the one details view, #5561), which list its stages in order, by
  name, each with its state and why and, for a workflow stage, its run's account: pages done, failed and
  left, the time left at its pace and what its pages wait for. The run's node in
  `GET /api/activity/jobs/{id}` carries `stages`, its reason says what it waits for (another recipe run,
  memory), and `/api/recipes/project/runs[/{id}]` carry the same accounts with `waiting_for`; a stage's
  run changing re-reads the recipe run's tree, so the details follow live. Pinned as above.
  **Built 2026-10-08 (app), not yet seen:** the project window shows the run itself, in a strip along the
  bottom of the content column (beneath the library's bottom bar; `ProjectRunStripView`, the detail
  column's bottom inset). The project's `ActivityStore` follows the first recipe run its jobs poll
  (`GET /api/activity/jobs`, the one poll Activity already makes) lists running, waiting or paused
  (`projectRunId`; never the `waiting:run-a-recipe` row that stands for several), reads its tree once
  (`GET /api/activity/jobs/{id}`), and re-reads it as its row, a stage run's row or the change stream
  moves. The strip says, in the details' own words (`ActivityDetails.stages`): the running stage by name
  and its place ("Transcribe (Kraken) · stage 1 of 3"), its run account's pages done, failed and left
  (`pages_done`/`pages_failed`/`pages_left`), the time left (`estimate_seconds_left`) and what its pages
  wait for (`waiting_reason`, else the run's reason); before a stage runs, what the run waits for (its
  reason). Show Details opens the recipe run's Activity details. Nothing is counted in the app.
  **Built 2026-10-08 (app), not yet seen:** after a relaunch the strip comes back. When the project
  opens, before its first jobs poll, `ActivityStore.restoreProjectRun` reads the project's recipe runs
  once (`GET /api/recipes/project/runs`, newest first) and follows the newest one still running,
  waiting or paused; if none, the newest run that ended, with its summary, unless the person closed
  that run's summary (Close is remembered per run in the app's defaults,
  `project.runStrip.closed.<project id>`). An older ended run never replaces a closed one. From then on
  the jobs poll follows it as above (one path: `adoptProjectRun`). Pinned by
  `fichero/Tests/Unit/general/Models/ProjectRunStripTests.swift`. *Not built:* waiting on a download
  (a run never waits for one; Start is refused until it is here).
- `source.read.line-with-no-writing-is-read` — **[PARTIAL]** (#5758) a line a reader looked at and found no writing
  on (a ruled or blank line, the margin's edge) is recorded as that: it counts as read, has no reading, is left out
  of the page's text, and is never read again by a later Start unless the person asks. A line the reader did not
  answer for (a failed call, a refused or flagged reading) stays unread and is read again. The run summary counts
  the unread lines and never counts a page with one as read (`N lines have no reading`). *Built:* the line reader
  and the Kraken reader name the lines they looked at without finding writing; they are marked on the segment
  (`read_no_writing`, naming the reader that looked), written through `segment.update` so it is versioned and audited; the page is done when none of its lines is unread (`recipes.done.lines_state`), and a different reader than the one that looked reads the line again. The reader's batch is bounded by the memory the Mac has now (`kraken_runtime.reader_batch_size`: one line when the memory is unknown, at most 16), and every line left without a reading is logged with why (`line left without a reading`). *Left:* a
  "no writing" line is not yet drawn as such in the Reader. *Test:* `tests/unit/recipes/test_unread_lines_not_read_5758.py`. Also (live M4 run, 2026-10-17): a line a recognising reader (Kraken, segmenting and reading in one pass) gave no text for is saved carrying the mark and its reason (`models.segments.segment_from_box`); the run summary's `lines_unread_why` counts the unread lines by reason (`done.unread_reasons`), so no log is needed to say why a line is unread; pinned by `test_unread_lines_not_read_5758.py`. A page whose lines Kraken found but read every one as empty text is a FAILED read, not a page of blank lines: it keeps its lines, unmarked and unread, with the reason \"every line came back empty: the reader may not suit this hand\" (summary `pages_read_nothing`, a second Start reads it again); only a blank line on a page that also has lines with text is marked 'no writing'. It is not saved with no geometry (`recognize_to_geometry`; M4 run 2026-10-17, page 1: 30 lines found, none stored; `test_kraken_batch_bounded_5758.py`). The local pages read at once also follow the memory, read each time a page starts (`kraken_runtime.page_fan_out`, `builder._wait_for_memory`; a hosted reader keeps its own pool): 1.5 GB a page beyond the model, never above the cap of 4, one when memory is unknown (`test_kraken_batch_bounded_5758.py`); a run's `engine_peak_memory_bytes` is the physical footprint, which counts compressed and swapped pages and so can exceed the Mac's RAM.
- `source.onboard.auto.results-summary` — **[PARTIAL]** (#5577) when a run ends, the project says what
  it made: pages read, lines, names by kind, dates, statements, documents and groups proposed, pages
  failed (with Read Again) and steps skipped (with their fixes). Each figure opens what it counts.
  **Built 2026-10-07 (engine + app), not yet seen:** `GET /api/recipes/project/runs/{id}/summary`
  (`recipes/run_view.summary`), also on the ended run's node of the job tree: pages and pages with a
  reading, names by kind and dates (the document knowledge graph's own grouping), statements, each
  stage's failed pages with its offer and Read Again (the run account's, the existing read-again route),
  the skipped steps with their fixes (Open Set Up…), and the stages that did not run. The recipe run's
  Activity details show it as What this run made. Pinned as above. **Built 2026-10-08 (app), not yet
  seen:** when the run ends (it leaves the jobs poll and its tree, read once more, carries `summary`),
  the project window's strip (see `source.onboard.auto.lands-on-the-run`) stays with "Recipe run
  finished", "failed" or "stopped" and the summary in one line, the details' own lines joined ("Read 2
  of 2 pages · Names: 1 People · 1 Places · 1 date · 1 statement"); each stage whose pages failed offers
  its run's Read Again (`ActivityStore.readPagesAgain`, the read-again route); Show Details opens the
  Activity details with the rest (skipped steps and their fixes); Close puts the strip away for that
  run. Pinned by `fichero/Tests/Unit/general/Models/ProjectRunStripTests.swift`. **Built 2026-10-08
  (engine):** the summary says itself in the engine's words, `lines`, one per figure, and the app shows them as
  given: "Read 2 of 2 pages", "Names: 1 People · 1 Places" (or "No names found"), "1 date · 1 statement", and,
  when the run had those stages, "3 documents proposed, 2 accepted" and "1 group proposed" (Find the
  Documents' proposals as they stand now, with `documents_proposed`, `documents_accepted`, `groups_proposed`)
  and "4 entries from 2 pages" (the entries stage's account, #5581, with `entries`); a figure for a stage the
  run did not have is null and has no line (`fichero-server/tests/unit/recipes/test_run_visible_to_spec.py`).
  **Built 2026-10-08 (app), not yet seen:** the Activity details' What this run made and the project window's
  strip show `lines` as given (`ActivityDetails.summary`; none when the engine sends none, never a line the app
  builds), pinned by `RecipeRunVisibleTests` and `ProjectRunStripTests` against the recorded summary.
  **Built 2026-10-11 (engine, #5668, found by the end-to-end onboarding run):** a run with Find Lines or Find
  Regions says how many pages have them, "Lines on 92 of 92 pages · regions on 90 of 92 pages"
  (`pages_with_lines`, `pages_with_regions`, null for a stage the run did not have); and the dates and
  statements line names only the figures of stages the run had (Work out dates: pages dated; Names: dates
  named; Find statements: statements) or that are not zero, so a run without them no longer says "0 pages dated · 0 dates named ·
  0 statements". Pinned by `fichero-server/tests/unit/recipes/test_run_visible_to_spec.py`.
  **Built 2026-10-18 (engine):** a run with a review step counts what the review did, "Reviewed 12 lines on 2
  pages: 3 corrected, 1 it could not read and left as read" (`run_view.reviewed`, three queries over all the run's pages: each page's newest review, the
  lines it answered by id, those given a new reading, those flagged unreadable; `pages_reviewed`, `lines_reviewed`,
  `lines_corrected`, `lines_review_unreadable`, null for a run without one), pinned by
  `fichero-server/tests/unit/recipes/test_run_summary_counts_the_reviewed_lines.py` (R3 live exit step 6).
  *Not built:* lines (of text); each figure opening what it counts.
- `source.onboard.auto.failed-pages-roll-up` — **[PARTIAL]** (#5555) the recipe run's own row counts
  the pages that failed inside its steps and offers Read Again for them. Built: per workflow run
  (`compute.run.read-failed-again`). Not built: on the recipe's row, which today says "Done" when every
  step's workflow completed.
- `source.onboard.auto.estimate-time-and-memory` — **[PARTIAL]** (#4951, #5537) Ready states the
  whole run's time on this Mac, labelled measured or estimate, and its peak memory across steps. Built:
  pages and cost, and a per-step memory sentence in the engine's estimate. Not built: time, the
  across-steps peak, and the app showing either.
- `source.onboard.auto.suggested-from-samples` — **[GAP]** (#4951, as `source.onboard.samples-first`)
  from a sample of the material, setup fills in its suggestions for language, script, material, period
  and hand, labelled "suggested from your pages", along with the pages that are blank or duplicates. The
  person confirms them; they do not type them.
- `source.onboard.auto.reader-measured-before-bulk` — **[PARTIAL]** (#5533, #5519, #4951, #5660; built: the Start
  plan carries `bakeoff_offer`, the comparison on the sample with its cost first and whether the project has the
  corrected lines for it, pinned by `fichero-server/tests/unit/recipes/test_bakeoff_offered_on_start_plan.py`;
  not built: the strong-reader sample read and the teacher-line check as jobs of the run) no reader reads the
  whole material on the strength of a published figure alone. The Start plan OFFERS a comparison on the sample,
  cost first, and never runs it by itself (ruled 2026-10-17, #5660 item 7); once run, its winner is the step's
  model and the bulk read waits for the person's Use This (the ruling of section 12, "Use the winner").
- `source.onboard.auto.reader-per-material` — **[PARTIAL]** (#5478, #5578; tested in
  `fichero-server/tests/unit/recipes/test_reader_per_material_to_spec.py`)
  each page is read by the reader for its kind. A cheap first job sorts the pages (handwriting, print,
  typescript, blank) from the image, and a person's correction of a page's kind is kept. **Built
  (#5578, engine):** the Start plan carries a reading step's `readers` as the card's `readers` (kind →
  the workflow and model that reads it, worked out as the step's own model is; a reader that would send
  pages off a Mac that keeps them, or that no workflow can run, is left out and its kind read by the
  step's own reader; the readers' models are checked and offered for download as the step's are).
  Before a card lines or reads pages, the run sorts them (`recipes/sorting.py`): a page's kind is the
  document attribute `material`, with `material_set_by` saying who set it (`sorting`, or `person` when
  a person changes it through the document update route); a kind already set is not worked out again,
  and a person's is never overwritten. Blank is the blank-verso rule of Find the Documents (one code
  path); the rest are told apart from the image by a heuristic (machine text has clean gaps between its
  lines, handwriting does not), only when the card has `readers`. Blank pages are left out; the rest
  are read in one workflow run per reader, each page by `readers[kind]` when the recipe has one for its
  kind, else by the step's own reader; the step's account in the run status lists `kinds` (pages by
  kind) and `readers` (each run, its kind, pages, model and state). *Not built:* telling print from
  typescript (a machine-made page is the first of print, typescript the project ticked); a trained
  classifier (the heuristic is marked `ponytail:` with that upgrade path); the sorting as its own row in
  Activity; the app showing or correcting a page's kind.
- `source.onboard.auto.hand-and-script-per-page` — **[GAP]** (#5456) script and hand are found per
  page and region, and each region goes to the reader that suits it (as
  `recipe.distil.script-and-hand-routed-per-region`).
- `source.onboard.auto.blank-pages-not-read` — **[PARTIAL]** (#5579, #5578, #5676; #5550 for pairing leaves;
  tested in `fichero-server/tests/unit/recipes/test_find_documents_step.py`
  (`test_blank_versos_are_not_read`), `fichero-server/tests/unit/recipes/test_reader_per_material_to_spec.py`
  and `fichero-server/tests/unit/finddocs/test_blank_pages_anywhere_5676.py`,
  `fichero-server/tests/unit/recipes/test_one_blank_rule_5705.py`)
  blank pages are found before reading and are not read, lined or sent to a model. Each is reported in
  the run's account. About half of Istmina's 203 images are blank versos. **Built:** before a recipe
  card lines or reads pages, every page blank as its image shows, wherever it falls in its folder (its
  first page, a blank after a blank, the back of a leaf: `finddocs.job.blank_versos`), and any page a
  person marked blank, are sorted as `blank` and left out; the step's account counts them
  (`blank_versos`). Blank is a proposal: a person who changes the page's kind has it read, and their kind
  is never overwritten (`material_set_by`). Ink is what is much darker than the paper around it (the
  page with its thin strokes closed over, at 384 px), so a broad ground around the sheet, black or grey,
  is not ink and does not hide the writing on it. WHY (#5676, measured on CACIQUES_INDIOS,17,D.5): the
  archive's "Hoja_en_blanco" sheets are one placeholder photograph of a white sheet on grey, which read
  as 6% ink against the paper's median; a written page shot on black read as 0% and was taken for a
  blank verso; and only a blank right after a written page was caught. The threshold holds on those
  sheets (the placeholder 0.007, the folder's faintest written page 0.0175, the line at 0.011), and faded ink
  (`source.onboard.auto.prepare-damaged-images`) is still ink.
  **One blank rule (#5705):** the pages a run leaves out are the pages Find the Documents calls blank: one rule
  (`finddocs.propose._is_blank`: a short reading and ink below one line, 0.011), on the page's reading if it has one,
  so the two never disagree on a page. A page whose image cannot be looked at is read. A `blank` sorting set is
  looked at again on every run (a person's kind is not), and dropped when the page is not blank. WHY: on
  CACIQUES_INDIOS,17,D.5 a written recto (51_Hoja_555_Recto, ink 0.039) was sorted blank under the measure #5676
  replaced and left out of every later run, while Find the Documents called it written; the two rules also drew
  their lines at 0.011 and 0.014.
  **Named, not only counted (#5691):** a page a stage left out is named with why, on the step
  (`left_out`: each page's id, its name and why, "a blank page: its image holds almost no ink", or "a person called
  it blank") and in the run's summary ("Left out: 2_Hoja_en_blanco.jpg, a blank page: ..."), so "Read 91 of 92 pages"
  never leaves a page unaccounted for. A page left out as blank is not counted as read, though an earlier run gave
  it a reading, so the figures add up (#5705: "Read 92 of 92 pages" with 5 left out). The CLI says each reason
  once. A workflow node that ran over many pages reports what it did over all of them
  (`processed_count`, `reused_count`), never 0 after reading 91; and the shipped Kraken reading node is named as
  a person says it ("Read the lines with Kraken"). *Test:*
  `fichero-server/tests/unit/recipes/test_left_out_named_5691.py`. **Not on unreadable text (#5694):** Find Names is not run on a page whose reading is too uncertain:
  the mean, over its lines, of each line's newest machine certainty (`machine_confidence`, which a reader such as
  Kraken now keeps on each reading; a line a person read counts as sure; where no reading carries one, the
  certainty the reader gave its working lines when its result became the page's pass, #5704) below 70%. A
  Kraken reader reading lines a page already has (Find Regions' or Find Lines', #5487) keeps each line's
  certainty on its reading (`kraken_runtime.ReadLine`, #5707), and a reading the same result already wrote on a
  line is not written a second time. A page's line list (`GET /api/segments/document/{id}`) serves each line's
  counting reading where that reading is another result's than the pass's own (a later reader's, a person's),
  never the words the pass's own result carried once a newer reading counts. (A line lists its pass's own words
  twice by design: the result's provisional reading and the stored reading made of it.) The page is left out, named
  with why ("its reading is too uncertain to find names in (the reader was 42% sure, below 70%); read it with a
  better reader first"), and the summary warns ("Names not looked for on 3 pages: their reading is too
  uncertain"); a Names try on the samples says the same. A page whose reader gave no certainty (a vision model)
  is not held back. One bar for every reader for now. *Test:*
  `fichero-server/tests/unit/recipes/test_names_on_unreadable_text_5694.py`.
- `source.onboard.auto.prepare-damaged-images` — **[PARTIAL]** (#5580; tested in
  `fichero-server/tests/unit/recipes/test_prepare_images_step.py`) where the sample shows faded
  or damaged pages, image preparation (contrast, deskew) is proposed as a step with a card. It runs before
  lines, and the original image is kept. **Built:** setup measures a sample of the open project's pages (up to
  ten, spread from first to last; `recipes/prepare.py`): a page whose grey spread (darkest 1% to lightest 1%) is
  under 100 of 255 is faded, a near-empty one is blank, not faded. Where one is faded (or the answers say
  `faded_pages`, or `prepare-the-image` is ticked), a recipe that lines or reads gets the step, after any split and
  before lines, with Fichero's own measure (no model to choose, on this Mac). Start runs it as its own card
  (`prepare`): each faded page gets a new rendition (`prepared`, the page's own frame, never primary) with its
  contrast raised; the clear and blank pages are left alone; the original file is never written to. Lines and
  reading (Kraken, Apple Vision, a vision model reading a page) read the prepared rendition in place of the
  original; a page already prepared is not prepared again; the run's account (`prepared`) counts what it prepared
  and left alone. *Not built:* deskew (a straightened picture is not the page's frame, so the lines found on it
  would not map back until a rendition can carry its transform to the lines); stains, holes and uneven light are
  not measured; the measure is not yet judged by reading (`prep.judged-by-reading`).
- `source.onboard.photographed-pages-asked` — **[PARTIAL]** (#5390; ruled 2026-10-17; engine half tested in
  `fichero-server/tests/unit/recipes/test_photographed_pages_step.py`) setup **asks** whether the pages are photographs
  (a book open on a table, two pages to a picture), and the default is off. Answered yes, a recipe that lines or reads
  gets `split-pages` and `prepare-the-image` before lines, so the table, ruler and spiral are not read as text; answered
  no or left unset, the recipe is unchanged. The answer is `photographs` on assemble; nothing guesses it. *Not built:*
  the question in the app's setup, and the other three faults of #5390 (cloud options listed when allowed, running an
  assembled recipe from the CLI, plain list values).
- `source.onboard.auto.organise-is-a-stage` — **[PARTIAL]** (#5550; built 2026-10-07, engine, as `finddocs.recipe-step`: setup's `loose_pages` adds the step after reading, names and dates, on by default for a project holding a folder of loose page images; Start runs it as its own `find-documents` card under the recipe's row; it proposes only, so nothing moves until the person accepts; pinned by `fichero-server/tests/unit/recipes/test_find_documents_step.py` and `fichero-server/tests/unit/finddocs/test_find_documents_to_spec.py::test_finddocs_proposes_only_by_default`; not seen: the proposals drawn on the canvas for review) Find the Documents is a recipe stage
  that runs after names and dates, on any material, images or text. Its proposals (boundaries, kinds as
  prototypes, groups, order) are drawn on the canvas for review. Nothing in the source moves until the
  person accepts, and a project of loose material brings this stage by default.
- `source.onboard.auto.diary-entries` — **[PARTIAL]** (#5581; tested in
  `fichero-server/tests/unit/recipes/test_diary_entries_step.py`. *Not built:* an entry that runs across a
  page break is still two entries, one on each page (the splitter reads one page at a time); the entries are
  ordered within their page, not across the volume by date; setup proposes the step only when it is ticked, never
  from the material being a diary or register; the card has no row of its own in Activity and no cost in the
  estimate; the entries are child nodes, not yet units over their lines, `source.extract.entries-are-units`,
  #5601) a diary or register is split into dated
  entries as a recipe stage (`split-into-entries`). Each entry carries its date, the entries are ordered
  by it, and an entry that runs across a page break is one entry. **At Start:** the step is a card of
  its own (`entries`), after reading: it takes the pages' reading (`READING`, a page's or its lines'),
  so a failed read stops it. It needs a model, the step's own (a cloud or local text model as the
  run's provider and model, never another); a step with none is skipped with "choose-model". It runs
  only on the pages that have text; the rest are left alone and counted. Each page is split by the
  Diary Entries workflow's own splitter (`workflows/tools/diary_entries.split_pages_into_entries`, one
  code path): one `entry` child per dated entry, its date as the `date` attribute, in the page's order;
  run again, it matches the entries it made rather than making them twice. The step's account in the
  run status (`entries`) says how many pages it split, how many had no text, and how many entries it
  made, kept, changed and removed. The entries are not pages: they are not counted as the project's
  material, and no later card reads them.
- `source.onboard.auto.volumes-in-batches` — **[OK]** (#5540; built as `source.recipe.batch-at-archive-scale` below, one batch per folder with every step finished on it before the next, progress per folder; tested in `fichero-server/tests/unit/recipes/test_recipe_batches_to_spec.py`) a run over several volumes goes one
  volume at a time, with every stage finished on that volume before the next volume starts. Progress is
  shown per volume.
- `source.onboard.auto.train-offer-comes` — **[PARTIAL]** (#5440; reworded 2026-10-17, ruled; *built (engine): `train_offers.training_setting` and the setting on every Start-plan offer (`setting`, `does`); pinned by `fichero-server/tests/unit/recipes/test_training_setting_5440.py`. Not built: the onboarding screen that sets `answers.training`, and training actually starting by itself once the threshold is reached*) training runs by itself per an
  onboarding setting, not a prompt: in the project's setup the person chooses how training happens (`answers.training`:
  `here`, `huggingface` or `offered`). With no choice the default depends on the machine: a Mac with enough memory to train
  a Kraken reader trains **here**, automatically; otherwise **huggingface** when a Hugging Face token is set up; else the
  offer stays on the Start plan (`offered`). A choice that cannot be met (`huggingface` with no token) falls back to
  `offered` and says why. No alert and no notification. The Start plan shows what it did and will do: each train offer
  carries its `setting` (mode and the sentence that says why) and what the setting does once the corrected lines reach the
  step's threshold. *Test:* the default by machine, an explicit choice winning, an unmeetable choice falling back with its
  reason, and the setting on the Start plan's offers.
- `source.onboard.auto.text-needs-no-reading` — **[PARTIAL]** (#5553, as
  `source.recipe.text-material-is-not-read`) material that is already text is a kind of its own. Its
  recipe starts from text (`STARTS_WITH` includes the page's text), its language is detected from the
  text, no script or material is asked, and the plan goes straight to names, dates, organising and
  search. Built: the material `text`, read off the sample when unset, and its recipe starting from the page's
  text (see `source.recipe.text-material-is-not-read`). Not built: the language detected from the text; setup
  still asks a language and a script.
- `source.onboard.auto.job-answers-read` — **[PARTIAL]** (#5478, #5574) the answers given under a purpose
  (which kinds of names, which gazetteer, how far to normalise) are read by the steps they configure.
  Built: saved as `answers.job_answers`; each becomes its step's setting (`start.JOB_ANSWER_SETTINGS`), at
  assembly when sent and in the Start plan from the saved answers; the kinds of names reach the names step as
  the sections its entity extraction finds (tested in `fichero-server/tests/unit/recipes/test_every_step_runs_to_spec.py`).
  Built 2026-10-11 (#5660 item 1): "Into what" is a list of reading levels (as written, abbreviations
  expanded, normalised spelling, modernised, and `translation:<tag>`), a single saved value read as a list of
  one (`answers.normalise_levels`); the normalise step runs once per level asked, each run writing a
  transcription at that level (or a translation) with the step's model (`start.LEVEL_PROMPTS`, the
  Modernización workflow's analyze node); pinned by `fichero-server/tests/unit/recipes/test_set_up_steps_5660.py`.
  Not built: the gazetteer reaches no step, because placing in a gazetteer is not a step Start runs yet
  (`by_hand`); setup's gazetteers (GeoNames, Wikidata, the project's list) are not the engine's (a small
  offline list, then Nominatim).
- `source.onboard.auto.models-fetched-first` — **[PARTIAL]** (#5367, #5537) every model the plan needs
  is fetched before its step, as a visible download job, never during a page read. This covers the
  Kraken readers and the MLX vision models as well as spaCy pipelines. Built: spaCy pipelines
  (`missing_models`); MLX models offered as downloads (`local_models_to_download`, #5583).
- `source.onboard.auto.installed-model-first` — **[PARTIAL]** (#5583; built 2026-10-07 (engine + app), not yet
  seen: `Card.installed` (`discovery.mark_installed`) ranked in `assemble._rank_key`;
  `start.local_models_to_download`, `start.use_instead`, `POST /api/recipes/project/start/use-instead`, the
  `mlx` runtime on `POST /api/local-models/download/{runtime}/{model}` and `model.download`; Ready's
  `RecipeDownloadRows` and `RecipeSetupStore.useInstead`; tested in
  `fichero-server/tests/unit/recipes/test_installed_model_first_to_spec.py`. **Built 2026-10-08 (engine):** the
  plan is worked out afresh on every read from what is on this Mac now, so once a download it waits for finishes
  its `downloads` drops it and a refusal that was only that download clears; and the finished download says so
  on every window's change stream (`model.installed`, with its `runtime` and `model`; an MLX model from this
  Mac's model store, a spaCy pipeline from its `download-model` job), the app's cue to read the plan again.
  **Built 2026-10-08 (app), not yet seen:** `RecipeSetupStore` is registered on the project's change stream
  (domain `model`) and reads a shown plan again on `model.installed` (and on a reconnect), pinned by
  `RecipeSetupStoreTests.modelInstalledReadsThePlanAgain`) a step's local model that is not on
  this Mac never refuses Start in words the person must answer by editing the recipe. (1) When the rules
  propose a recipe, a model already on this Mac wins over one that must be downloaded, among the cards the
  rules accept for the step, after accuracy (each card's `installed`; the reason says "already on this
  Mac"). (2) When the plan's step is pinned to a catalogue MLX model that is not installed, the plan offers
  it in `downloads` (runtime `mlx`, its name, its size, the steps it serves, Download through the one
  download route) and, beside it, `instead`: every installed model this Mac can serve for that step, each a
  card the person can choose in one press (`POST /api/recipes/project/start/use-instead`, kept as a
  project-scope override on the recipe, as Use This keeps a bake-off's choice; the press is the deliberate
  choice a licence that is not open needs). Ready shows the two as one choice: "Download Qwen2.5-VL 7B
  (OCR) · 5653 MB" and "Use the installed Qwen2.5-VL 3B (OCR)". Start waits, saying so, until one is
  taken: the refusal names the download and the installed models, never "edit the recipe".

**The five fixes that would most make onboarding just work, ranked.**
1. **Make the run visible and honest** (#5573, #5575, #5576, #5577; #5555). Ready shows skipped steps and downloads.
   Start lands on the run, live. An import that cannot run says why. The run ends with a summary of what
   it found, and failed pages roll up to the run's row. Without this, every other gap is silent.
2. **Run every step that setup proposes, and keep the What runs by itself promise** (#5574, #5478).
   Either add a card for each proposed job or stop proposing it, starting with search, and have the
   import hand-off read `answers.automatic`.
3. **Organising as a stage** (#5550, #5579 blank pages). Find the Documents runs after names and
   dates, with leaves and blank pages first, its proposals on the canvas. This is the half of the goal
   that does not run at all today.
4. **Measure before the bulk read** (#4951, #5533, #5519, #5456, #5578 sorting). Samples suggest the
   answers. A teacher reads and is checked, the readers are compared, and the winner reads, each page by
   its material's reader. Today a published aggregate decides, and one reader reads everything.
5. **Text needs no reading** (#5553). A slip box gets a recipe that starts from its text and goes
   straight to names, dates, organising and search. Today it cannot get a recipe that passes the check.

### 7c. Set Up, one page per stage (ruled 2026-10-11, #5668)

**Ruled by the maintainer 2026-10-11 (morning).** Set Up becomes one page per stage of the work. The
person chooses the stages first; each chosen stage then has its own page that says what it does, who
runs it, asks its own questions, and shows its result on 3 to 5 of the person's own pages, so they
know it works before Start. This supersedes the third of section 7b's four steps (What you want to do)
and moves the plan's per-step rows, the model finder and Check on your pages from Ready onto the stage
pages. Your project, Your material, Train and Ready stay; what each holds is below. As before, nothing
runs on the project before Start: the sample results are the stage's, never the project's work.

**The left list, in recipe order.** The window's list (`FirstRunWindow`'s sidebar) reads:
1. **Your Project**: its name and where it lives (unchanged from 7b).
2. **Your Material**: how it comes in, what it is (handwriting, print, typescript), languages, scripts
   and direction (unchanged), and two new questions, each with examples:
   - **When were they written**: a century or a range of years ("16th century", "1650–1700"),
     proposed from the sample pages where a local model can look, labelled "suggested from your pages".
   - **Which hand**: the script's style, chosen from a curated list of hands for the script and the
     century (Latin: Caroline minuscule, Gothic textualis, Gothic cursiva, Secretary, Humanistic,
     Italic, Kurrent, Copperplate…), each shown with a picture example and mapped to the Hugging Face
     tags readers carry; anything else can be typed (kept as typed), and "Not sure" is an answer
     (ruled 2026-10-11, open question 18).
   Both feed the search for readers (the Hugging Face tags people use, such as `htr`, `catmus`,
   `kurrent`, with the language tags) and the comparison of readers on the person's pages.
3. **Choose the Stages**: the first decision about the work, replacing What You Want to Do. Every
   stage is on or off. The goals (Transcribe, Search, Knowledge graph…) stay as shortcuts that tick
   the stages they need; a stage another chosen stage needs is ticked and says why ("Dates & Times
   needs Names").
4. **One page per chosen stage**, in this order, each only when chosen: **Clean Up Images · Find
   Lines · Read · Translate · Organise (Find the Documents) · Names · Statements (who did what) ·
   Dates & Times · Passages · Structured Data · Search**. Translate, Passages and Search were added on
   2026-10-11 (open question 16), so every job a person can choose has a page.
5. **Train**: offered later (`source.recipe.train-offered-per-step`, #5660 item 9), its own page.
6. **Ready**: the plan in one list, what runs by itself, what Start will fetch (#5664), Keep an
   export, and Start.

**The stages and the jobs they carry** (the job registry's ids, section 2; one stage can carry several
jobs, and the recipe keeps the registry's step order whatever order stages are chosen in):

| Stage | Jobs | Its own questions (examples) |
|---|---|---|
| Clean Up Images | `split-pages`, `prepare-the-image` | Two pages per image? Straighten, crop, brighten? |
| Find Lines | `find-regions`, `find-lines`, `put-in-order`, `refine-shapes` | Columns, margins and glosses? Tables on the pages? |
| Read | `read-a-line`, `read-a-page`, `correct`, `tie-text-to-lines` | Have a second model check the reading? (Lines are read one by one; the page-at-once question was dropped 2026-10-18, #5788.) |
| Organise | `find-documents-in-a-folder`, `split-into-entries` | Are several documents in one folder, or one document per folder? |
| Names | `find-names-tag-words`, `place-in-a-gazetteer`, `link-to-authorities` | Which kinds of names (people, places, things, organisations)? Which place list? |
| Statements | `find-statements` | Which kinds (sales, gifts, marriages, letters sent…)? |
| Dates & Times | `work-out-dates` | Which calendars (Gregorian, Julian, regnal years, the French Republican…)? |
| Structured Data | `find-a-tables-cells`, `extract-to-a-table`, `describe-for-the-catalogue` | Which fields to fill, and from what? |
| Translate | `translate-transliterate-normalise` | Into what: as written, abbreviations expanded, normalised, modernised, a translation into which language? |
| Passages | `pull-out-passages` | Which kinds of passages (quotations, formulae, a party's own words…)? |
| Search | `make-a-vector` | Nothing to ask; its sample result is a search over the sample pages with an example query. |

The table lists the stages by their jobs; the pages follow the order in item 4.

**Each stage page holds, in order:**
- **What it does**, in one sentence with an example, from the job registry's words (section 7a), so
  the page, the Inspector and the manual say the same.
- **Who runs it**: the model each of its jobs would use, with where it runs, its size and licence, the
  model finder (Choose a model…) and the candidates, and for Read and Find Lines the comparison of
  candidates on the person's pages (the bake-off, section 8a).
- **Its own questions** (the table above), each with its default filled in.
- **A result on 3 to 5 sample pages.** Fichero proposes the samples, spread across the material (first,
  last, evenly spaced, the largest and smallest images); the person can pick others in the window. The
  stage runs on them locally and free where it can; a stage that would use the cloud shows its cost
  first and runs only on a press. The result is shown in place: the lines found drawn on the page, the
  text read, the names found marked, the dates normalised, the table filled. The Read stage shows the
  readers compared, line by line, with the disagreement heat map (#5665).

**The engine.** One new run: **try this stage on these pages**. For Read and Find Lines it reuses the
bake-off and its evaluation job (section 8a); for the other stages it runs the stage's workflow on the
samples. Its results are kept as the stage's sample results, beside `recipe/setup.yaml` (one record per
stage: the samples, the models used, the result; ruled 2026-10-11, open question 17), never written as
the project's passes, readings, names or statements; they are replaced when the stage is tried again
and cleared when the stage is unticked. The sample run's cost and time are said before it runs.

**What carries over from 7b.** Your project, Your material's ways in and fields, the cloud question,
What runs by itself, Keep an export, the Start plan and its refusals, Start, and "nothing runs before
Start" are unchanged. The purposes keep their place in the engine (`PURPOSE_STEPS`) as the goals that
tick stages; the questions under a ticked purpose (`RecipeSetupStore.questions(under:)`) move onto the
stage pages that own them.

**Translate, Passages and Search** (ruled 2026-10-11, open question 16) are stages like the others,
each with its page, its questions and a sample result.

#### The Swift as it is, mapped onto the stages (read on disk 2026-10-11, `lead/2026-10-09b`)

**Stays as it is:**
- `FirstRunWindow` (the window, its left list, `stepPage`, the recipe card) and `SetupWhereItLivesFields`
  (Your Project).
- `RecipeMaterialSourceFields` and `RecipeAboutFields` (Your Material), which gain the two new fields.
- `ModelFinderSheet` / `ModelFinderView`, `LicenceReviewSheet` and `BakeoffSection`: moved from Ready
  onto the stage pages (Who runs it; the comparison on Read and Find Lines).
- `RecipeTrainOffersFields`: the Train page's content, moved off Ready.
- `KeptExportFields`, `RecipeAutomaticFields`, `RecipeDownloadRows`, `RecipeElsewhereRows`,
  `RecipeSkippedRows`, `RecipeTakenOutRows`, `RecipeStartFields`: stay on Ready.
- `RecipeSetupStore` (answers, save, the Start plan, the training offers and Start), `ModelFinderStore`
  and `BakeoffStore`, as they are.

**Splits:**
- `FirstRunStep`: today a fixed enum (`project`, `material`, `purpose`, `ready`). It becomes the fixed
  steps plus one step per chosen stage (`.stages`, `.stage(id)`, `.train`, `.ready`), and
  `setUpSteps` / `newProjectSteps` are computed from the chosen stages.
- `RecipePurposeFields` becomes **the stage chooser**: the stages as checkboxes, the goals as
  shortcuts above them, and a stage another needs ticked with its reason.
- `JobQuestionFields`: its questions move to the stage that owns their job (Names' kinds and gazetteer
  to Names; Into what to Translate).
- `RecipeProposalFields` and `RecipeStepsView` / `RecipeStepRow`: the plan's rows are split by stage.
  Each stage page shows its own steps' rows (who runs it, with the finder); Ready keeps the whole plan
  as one compact list.
- `RecipeReadyFields.Row`: `checkOnYourPages` leaves Ready (it is the Read and Find Lines pages'
  comparison) and `trainLater` becomes the Train page.

**New:**
- **The stages' list from the engine**: each stage's id, title, sentence and example, its jobs, its
  questions and what it needs (`GET /api/recipes/stages`). The app shows what the engine lists and
  works nothing out.
- **`SetupStagePage`**: one view for every stage page (what it does, who runs it, its questions,
  its samples), driven by the stage's entry.
- **`SetupStageSamples`**: the 3 to 5 sample pages (proposed, changeable in the window), the Try on
  These Pages button with its cost and time, and the result drawn per page by kind (lines on the page,
  text, names marked, dates, a table).
- **Your Material's two fields**: When were they written (a century or a range, with suggestions)
  and Which hand (the curated hands for the script and century, each with its picture, as tokens;
  free text kept as typed).
- **The engine's sample run**: try this stage on these pages, its result kept as the stage's
  (`POST /api/recipes/stages/{stage}/try`, `GET` its result), the proposed samples
  (`GET /api/recipes/samples`), and the reader search taking the period and hand.
- **Read's comparison** with the disagreement heat map (#5665), on the Read page.

### 7d. Two set-ups: the app, then a project (ruled 2026-10-11 afternoon, #5668)

**From the maintainer's walkthrough of a first launch on a Dev Local build, 2026-10-11** (the comment
on #5668). It restructures sections 7b and 7c where they differ, and supersedes the first-run flow of
`FirstRunWindow` (Welcome, Permissions, AI, then the project's steps in one window). Where 7c and this
section disagree, this section holds; 7c's stage pages, samples and engine run stand as written.

**Two flows, one code path each.**
- **Setting up the app** (a first launch, and Fichero › Set Up Fichero…): Welcome, then What Fichero
  runs, then a hand-off to Set Up a Project or to the app.
- **Set Up a Project**: one view, the same from every way in: the welcome's Set Up a New Project…, File ›
  Set Up New Project… and Project › Set Up…. There is never a second copy of it.

**Setting up the app.**
1. **Welcome**: its sentence and its two choices, nothing else (no card, no pills; done on the lead).
2. **What Fichero runs** (it was "AI is optional"): what Fichero can do, and with what:
   - reading pages: Kraken, Apple Vision, MLX vision models;
   - finding regions and lines: YOLO, Kraken;
   - names and statements: spaCy;
   - speech: Whisper;
   - remote models: OpenRouter, Anthropic, OpenAI, Google.
   It suggests two accounts and takes them right in the step: **Hugging Face** (to find and download
   models) and **OpenRouter** (remote readers). Choose a Provider opens its sheet in the step, while
   the step is showing; it opened only after onboarding ended.
3. **The hand-off**: Set Up a Project, or straight into the app.
- **Permissions is no longer a step.** Access to a folder is asked when a folder is added.
- **One Continue per step**, in the footer. A step's body has no Continue of its own.

**Set Up a Project: small pages, one step at a time, any of them skippable.**
1. **Your project**: its name and where it lives.
2. **Add material**: Add Files or Folders… (it was Add a Folder…), then how it comes in: Copy (the
   default), Link, Move, Index, Keep arranged. How it comes in is separate from what it is. The line
   about adding material later goes.
3. **About the material**:
   - the pages, counted from what was added;
   - languages and scripts. The language field offers matches as the person types, by ISO 639-3 and
     Glottolog (about 8,000 languages and 13,000 dialects), and by a language's own name, with or
     without its accents ("español", "espanol"); the engine half is on the lead. A language it does
     not know is said once, on the language row, never repeated on the scripts row;
   - kinds: handwriting, print, typescript, and more (tables and forms, maps and drawings);
   - when it was written; where it was written (a place);
   - which hand: the curated hands for the script and century (section 7c).
   The line saying a reader is proposed for each goes.
4. **The stages, in pipeline order**: Prepare Images · Find Regions · Find Lines · Read · Normalise ·
   Translate · Organise · Names · Statements · Dates & Times · Passages · Structured Data · Search.
   Each stage's explanation shows whether or not it is ticked. The goals stay as shortcuts that tick
   stages (section 7c).
5. **One page per chosen stage**: what it does, its questions, its model (with the comparison on 3 to 5
   sample pages, section 7c) and training or fine-tuning for that step (Kraken, spaCy, Core ML, MLX
   LoRA).
   - **Normalise and Translate are two stages.** Normalise offers as written (diplomatic),
     abbreviations expanded, normalised spelling, and modernised (for instance into modern Spanish).
     Translate goes into any language, found by the same search as the material's languages, not a
     fixed five.
6. **Ready**: the plan in words. No raw engine message reaches the page: a step whose model is not in
   a form the engine knows says so in words, with what to do. A step that will not run (Find a table's
   cells, for one) is listed only when its stage was chosen.

**The model chooser, per step.** A step's candidates and its online search are that step's own: Find
statements lists models that find statements, never page readers, and never says it searched for
readers. Find Regions has a default with an open licence; a model under a licence that needs accepting
(YOLO11 DocLayNet, AGPL-3.0) is accepted once, clearly, and Accept and Use for This Step then works.

**What the engine needs for this** (the stages list is the engine's, section 7c): Prepare Images and
Find Regions become stages of their own (they were Clean Up Images, and part of Find Lines), and
Normalise its own stage beside Translate, whose target is any language tag. Thirteen stages, in the
order above.

**Each stage shows what it does, and compares who does it** (ruled 2026-10-11 evening). A stage page opens
with a short picture of its work: the stage's job played once on a page, about 3 to 5 seconds, with
Replay; with Reduce Motion on, its last frame stands still. The page is the person's own where there is
one: a sample page the stage was tried on, with what the try made (its reading, its names, its
statements). Before any try, it is one example page shipped with the app, with its regions, lines,
reading, names and dates worked out once: page 18 of the sixteenth-century manuscript of Juan de Valdés's
*Diálogo de la Lengua* (Biblioteca Nacional de España, public domain; "Imagen procedente de los fondos de
la Biblioteca Nacional de España"), its lines read after the DILE transcription (CC BY-SA 4.0, M. T.
Carrasco Benitez, dir.; Alba Agraz Ortiz and Sara Sánchez Hernández), the same page and licence as the
engine's paleography fixture. Never a project's own material, and never the Marshall or Sergio papers.

What each stage's picture does:

| Stage | Its picture |
|---|---|
| Prepare Images | a tilted, dim scan straightens, crops and brightens, a light sweeping down it |
| Find Regions | the blocks outline one after another (text, margin, folio, catchword) |
| Find Lines | each baseline draws left to right |
| Read | the reading types in, line by line, beside the page, a light sweeping the line being read |
| Normalise | an abbreviated word becomes its expanded form ("q́" into "que", "tþo" into "tiempo") |
| Translate | a line crossfades into its translation |
| Organise | page thumbnails slide together into dashed document groups |
| Names | the names light up, coloured by kind |
| Statements | arrows join the names a statement links |
| Dates & Times | the date words become date chips |
| Passages | a passage lifts out of the page |
| Structured Data | values fly into a table's cells |
| Search | a query lights its matches |

**A / B / C: the same page by two or three candidates** (ruled 2026-10-11 evening). Comparing is how setup
teaches: a stage page shows the same sample page done by 2 or 3 of the step's candidates side by side
(Read: Kraken, Apple Vision, an MLX reader; Find Regions: Kraken blla, YOLO DocLayNet; Names: spaCy, a
cloud model). Each column plays the stage's picture on its own result, says under it how it measured
(agreement or character error rate, how long, and the cost: "free, on this Mac" or the cloud price), and
offers Use This, which sets that candidate for the step (the use-candidate route, section 8a). Try on These
Pages becomes Compare on These Pages; the defaults are the step's top 2 or 3 candidates, and the person can
change which. With one candidate there is one column. The engine's result is the bake-off's row for each
candidate (card, its name, where it runs, its measures and cost) with that candidate's own result on the
samples, in the shape the stage's try already answers (per page: readings, segments, statements; names).

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
  readers. It stays small: at most **two of each kind** per step (Kraken, Apple Vision, an MLX vision
  model, a cloud reader), drawn from everything the finder found, then at most **nine combinations**.
  All run on the same pages. **Ruled 2026-10-11: no fixed ranking decides; the bake-off does.** The rules'
  order only chooses which two of a kind take part; the default is whichever is measured best.
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
   object-detection for layout), and by name for the HTR words (htr, manuscript, trocr, medieval,
   palaeograph…) and the project's languages, which find the models made for manuscripts that the tag
   listings miss (#5660); a GGUF chat model is not a reader.
4. **spaCy's published pipelines** and the named community ones (LatinCy, greCy), by language.
Each candidate becomes a card that says where it came from, its licence, size, what it claims to
cover and what was measured; the same rules rank it; it is offered for download through the one
model path; and it can enter the bake-off like any other. Rules stay data: no candidate is named
in code. Offline, discovery offers only what is installed. A "no model fits" problem names what
was searched and the nearest candidates, and offers Train a Model where none exists.
Known gaps that discovery must close (corpus run 2026-10-06, #5519): Fraktur (UB Mannheim, Tesseract
`frk`), Japanese (NDLOCR), traditional Chinese (PaddleOCR `chinese_cht`), Hebrew (BiblIA Kraken),
Syriac (eScriptorium, Calamari), Latin and Ancient Greek spaCy (LatinCy, greCy).
Built 2026-10-07 for readers (#5519, `source.find.installed-count`, `source.find.kraken-repository`,
`source.find.hub-runs-here`, `source.find.rules-see-candidates`): sources 1 (MLX vision models), 2 and 3,
through `GET /api/recipes/candidates`. Built 2026-10-08 (#5593): a found Hub reader is kept, chosen by the
rules and offered as a download (`source.find.found-reader-downloads`), and "no model fits" names the nearest
candidates (`source.onboard.nothing-fits-names-nearest`). Built 2026-10-08 (#5594): only readers are taken from the
Hub (chat builds counted as left out), an unstated size says so, and the online search is an Activity job
(`source.find.online-search-is-a-job`). Still owed: installed Kraken readers outside the
repository, spaCy pipelines, YOLO weights.

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

### The best model, and the best place to run it (2026-10-07, #5582)

Choosing a reader (or any step's model) chooses a pair: the model, and where it runs. This Mac first
when the model fits its memory and has a local runtime. When it doesn't — too big for the Mac, or a kind
Fichero can't run locally (PyLaia, TrOCR, a 32B vision model) — the plan says so plainly and offers where
it can run instead: any provider in Fichero's provider catalogue that serves it or an equivalent (a Hugging
Face Inference Endpoint or inference provider, OpenRouter, Gemini, Anthropic, OpenAI, Mistral, Ollama or LM
Studio on another machine), and ACENET/Alliance for batch reading at scale (#5566), ranked by cost and fit. Each offer states
the cost for the project's pages, the speed, that pages leave the Mac (the project's egress rule decides),
and the account it needs, configured or not. The recipe picks the pair, Ready shows it, and a bake-off can
score a candidate wherever it runs (#5533).

- `source.find.model-and-where-it-runs` — **[GAP]** (#5582) every chosen or offered model carries where it
  runs (this Mac, Hugging Face endpoint, OpenRouter, ACENET) with cost, speed, egress and account status;
  a model that can't run here is never chosen silently and never dropped silently — the plan names the
  places it can run.

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

- `source.model.card-id` — **[PARTIAL]** (built in part, pinned by `fichero-server/tests/unit/recipes/test_seed_cards.py`; what is still unbuilt is not yet written down here, R0 2026-10-17; #4948) every card has one id `<runtime>:<source>@<version>`
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
- `source.recipe.text-material-is-not-read` — **[PARTIAL]** (#5553) material that is already text (Markdown,
  plain text, Word, a PDF with a text layer, notes from Tinderbox, DEVONthink or Bookends) gets no reading
  step: the plan goes straight to search and whatever else was ticked, and Ready says the notes are already
  text. A project whose purpose is finding related material asks for no transcription. Scans of printed or
  typed pages are read by Tesseract first; Kraken or a vision model is offered only when the check on a few
  pages shows Tesseract misses.
  Built: `text` is a material (`assemble.MATERIALS`); a project of text alone gets none of the jobs that make
  text from a picture (lines, readers, corrections, training), its recipe starts from the page's text
  (`jobs.starts_with`, so search, names and statements pass the check) and `/assemble` returns `already_text`,
  the sentence Ready shows. Unset, the material is `text` when every page of the open project's sample is a
  text file or a PDF page whose text layer the import kept (`prepare.sample_is_text`); a scanned PDF page is
  read. Beside other materials, text gets no reader. Tested in
  `fichero-server/tests/unit/recipes/test_text_material_not_read.py`. Not built: Tesseract first for printed
  scans (#4948); a mixed project's read step still reads every page, including those already text; the app
  offers no "already text" checkbox yet.
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
- `source.find.zenodo-through-htrmopo` — **[OK]** (#4948, #5519) Kraken's Zenodo repository is searched
  through the `htrmopo` library, which reads each record's card (model type, script, language,
  CER, licence), never through Zenodo's plain search alone. *Built 2026-10-07: `recipes/discovery.py`
  reads `htrmopo.get_listing` (the call `kraken list` makes), keeps Kraken recognition models only, the
  newest version of each; pinned by `fichero-server/tests/unit/recipes/test_model_discovery.py` with
  recorded records.*
- `source.find.adapters-as-a-tier` — **[GAP]** (#4948) the search finds fine-tuned adapters (Hugging
  Face `library=peft`) as their own tier, each shown with its base model and training data.

Jobs and chains
- `source.recipe.jobs-are-a-registry` — **[PARTIAL]** (#4949, #5364) **Built 2026-10-03 (engine):** the registry with typed takes and gives, layers, A/B comparison and descriptions (`recipes/jobs.py`); not yet read by setup or the activity queue; pinned by `fichero-server/tests/unit/recipes/test_job_registry.py`. jobs and export formats are
  registered by name with what they take, give, accept as settings, their layer and the Fichero
  version that added them; a newly registered one is available to recipes, setup, the activity
  queue and the recipe check with no other change; a recipe naming a job this copy lacks is
  refused before anything runs, naming the job and the version that has it.
- `source.recipe.jobs-carry-descriptions` — **[PARTIAL]** (#4949) every registered job carries a plain
  description, an example and the trade-offs between its usual options, and declares how its
  outputs are compared; setup, the Inspector and an exported recipe's README show that same text.
  *Built: every registered job (33) has its topic's sentence and paragraph and declares how its outputs are
  compared (`Job.compare`), served at `GET /api/topics/{id}`
  (`fichero-server/tests/unit/recipes/test_jobs_carry_descriptions_4949.py`). Not built: an example per job (Set Up's
  stages carry theirs, `recipes/stages.py`), the trade-offs between a job's usual options, and an exported recipe's
  README (#5364).*
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
- `source.read.once-lines-exist-every-reading-ties-to-a-line` — **[PARTIAL]** (#5721) done in the Transcribe tool: on a page that already has lines, Apple Vision (on each line's own picture, one line a call) and a vision model (the line reader, a few pictures a call) read each line onto the page's working pass, as Kraken does, with no second pass and the page's text left alone (`tests/unit/workflows/test_every_reader_ties_to_lines_5721.py`: `test_apple_vision_on_a_page_with_lines_reads_each_line_and_makes_no_second_pass_5721`, `test_a_vision_model_on_a_page_with_lines_is_shown_each_line_and_its_words_land_on_them_5721`, `test_an_auto_reader_on_a_page_with_lines_ties_to_them_whichever_it_resolves_to_5721`, `test_a_reader_never_replaces_the_text_of_a_page_that_has_lines_5721`); a page with text and no instruction to read again is still passed through as before (`test_a_page_that_has_text_and_no_instruction_to_read_again_is_not_read_5721`); a page with no lines read by a model says its text is tied to no line (`test_a_page_with_no_lines_read_by_a_model_says_its_text_is_tied_to_no_line_5721`); a run where only some pages have lines reads every page whole and names the one with no lines (`test_a_run_where_only_some_pages_have_lines_reads_every_page_whole_and_says_which_has_no_lines_5721`); a page whose lines came back with no reading is read whole, only that page, with a note (`test_a_page_whose_lines_came_back_empty_keeps_its_page_text_in_a_run_of_several_pages_5721`). Owed: a real run on a page like 39_Hoja_549_Recto.JPG; Apple Vision is given the line's padded polygon bounds, not its exact rectangle. On a page that already has lines
  (segments), every reader's output is a reading of those lines, whatever the reader is: Kraken, Apple Vision (run on
  the line's rectangle), an MLX or cloud vision model (shown each line's crop), or the one the recipe chose. Page-level
  text with no line under it is a draft a person may promote, never the step's result, and the step says so when it
  could only produce that. WHY (2026-10-16, page 39_Hoja_549_Recto.JPG, project 17402): Kraken's pass held 44 lines;
  the Apple Vision pass and the Qwen pass each held the whole page as text with 0 segments. Built in part by #5719
  (the review's answer is asked by id) and #5720 (the per-line re-ask); the read step for non-Kraken readers on a page
  with lines is built in the Transcribe tool (see the tests named above). *Test:* run Apple Vision, then a stub vision model, on a page with three lines: each pass
  has three readings tied to the three segments.
- `source.job.review-is-built-from-the-project-and-a-profile` — **[PARTIAL]** (#5723) done: the review nodes carry a `lens` (abbreviations, orthography, names-and-dates) and no prompt, and the step builds its prompt at run time from the project's saved setup (language, script, direction, period, material; place and hand where setup records them) and a profile chosen by the reader-card rules (`recipes/review_profiles.py`, data files in `recipes/seed/review-profiles/`: es-colonial and generic, with de-kurrent, aramaic and zh as stubs; no language is named in code). A project no profile fits is told so and gets the generic review (`test_an_english_secretary_hand_project_is_never_sent_the_spanish_review`, `test_a_spanish_colonial_project_is_sent_the_spanish_colonial_review`, `test_spanish_outside_the_profiles_period_gets_the_generic_review_and_is_told_so`, `test_each_script_gets_its_profile_and_its_direction_is_said`, `test_the_shipped_review_is_built_from_the_projects_answers_5723` through the shipped preset). No shipped preset's review carries its own Spanish colonial prompt: Transcribe (Auto-Detect)'s two review nodes run once through all three lenses (`lens` takes a comma list) (`test_no_shipped_review_carries_the_spanish_colonial_prompt_5723`, `test_one_pass_through_several_lenses_is_given_each_lens_5723`). Built 2026-10-18 (engine): the review step turns its lenses on or off (setup's `job_answers.review_lenses`, the step's `lenses`, in the profiles' order; a lens Fichero does not have is refused in words; every lens off skips the step and says so); the runner runs the review preset without a pass whose lens is off, the passes either side chained and a search that fed only it dropped, and a pass through several lenses keeps those on (`review_profiles.keep_lenses`, `fichero-server/tests/unit/recipes/test_review_lenses_turn_on_and_off_5723.py`). Built 2026-10-19 (engine): the Start estimate prices the review by the passes it runs (`calls_per_page`, `review_profiles.review_passes` over the run's own workflow; three calls a page with every lens on, it was priced as one; a review whose passes cannot be counted is unpriced, never $0) and gives each lens, on or off, its cost per page (`estimate.runs[].lenses`), `fichero-server/tests/unit/recipes/test_review_priced_by_its_passes_5723.py`. Owed: each lens's effect on the error rate shown by the A/B, Set Up's question and the cost beside it (Swift); the stubs' genres. The Correct offer at Ready prices the same way, its `calls_per_page` the passes of the lenses on (`assemble._correct_left_off`, `fichero-server/tests/unit/recipes/test_correct_offered_with_a_key_5677.py`). The review (the `correct` job,
  `transcribe_paleography_review`) is not written for one language. Its prompts are built from the recipe's answers
  (language, script, period, place, hand, material) and a shipped profile chosen by the same rules as a reader card;
  Spanish colonial notarial (genres carta de poder, probanza; ç/c/z, f-/h-; dela, quel, desta; the `mer[ce]d`
  convention) is one profile, with others beside it as the read presets already are (es_moderna, en_secretary, latin).
  The three passes become lenses (abbreviations and formulary; orthography and consistency; names and dates) the recipe
  turns on, each with the cost per page shown first and its effect on the error rate shown by the A/B; a project with
  no profile for its language and period says so and offers the generic review, never the Spanish one. WHY
  (2026-10-16): the preset's wording is Spanish colonial whatever the project says, and the node's language is
  "auto". *Test:* an English secretary-hand project is never sent "carta de poder" or "ç/c/z"; a Spanish colonial one
  is.
- `source.job.review-is-segment-native` — **[OK]** (#5724) done: the review asks for `<segment id> | <flag> | <text>` and a line flagged unreadable is left as read and counted (`test_a_line_the_review_flags_unreadable_is_left_as_read_and_says_so_5724`); a person's line is untouched (`test_a_line_a_person_read_keeps_the_persons_reading`). the review is shown each line's machine confidence (`test_the_review_is_shown_each_lines_confidence_5724`); an uncertain line that is changed keeps the machine's confidence, never made surer (`test_an_uncertain_line_keeps_the_machines_confidence_5724`); a corrected line's reading names the review artifact, which records the lens the step ran through, the `lens` config (`test_a_corrected_line_records_the_lens_that_changed_it_5724`); a short note after a line (`<id> | <flag> | <text> | note: <note>`) is kept on the review artifact under the line's id (`line_notes`) and never read as the line's text, even with the flag dropped; only the id and flag are split off, so a `|` in diplomatic text stays in it (`working_lines.answer_line`; a bare `<id> | unreadable` is a line the model could not read, listed on the review as `unreadable_lines` and never its text, `test_a_bare_unreadable_answer_is_a_line_the_model_could_not_read_never_its_text_5724`; `test_a_lines_short_note_is_kept_with_the_review_and_never_read_as_its_text_5724`, `test_a_bar_inside_a_lines_text_stays_in_its_text_5724`, `test_a_note_without_a_flag_is_never_the_lines_text_5724`). The lens names come from #5723. The review is given the page's lines as `<segment id> |
  box | maker | confidence | text` and answers `<segment id> | <text>` with a flag per line (certain, uncertain,
  unreadable) and a short note; it never changes a line a person read; it leaves an uncertain line uncertain, keeping the
  machine's confidence (#5694), rather than inventing text; and a corrected line records which lens changed it. Builds
  on `source.job.review-asks-one-answer-line-per-segment-id`, which asks for the ids; today the preset's prompts say
  only "same line breaks" and think in text, not segments. *Test:* a stub that marks one line unreadable leaves it
  unchanged and flagged; a person's line is returned unchanged by the stub and untouched in the project.
- `source.job.review-context-fits-the-model` — **[PARTIAL]** (#5648, ruled 2026-10-17) done: a pass of words never takes a page from a pass of read lines as the working pass; it ranks after the sound passes of lines and still leads where it is all there is (`PassCandidate.words_beside_read_lines`; `test_a_newer_pass_of_words_does_not_take_the_page_from_read_lines_5648`, `test_a_pass_of_words_is_still_the_working_pass_beside_lines_nobody_read_5648`); a model whose card states `prefill_tokens` is sent the page's lines in reading order up to what the prompt and the page image leave of it, and the prompt, the log and the step's notes say how many were left out (`test_a_page_over_the_models_budget_is_sent_the_lines_that_fit_and_told_what_was_left_out_5648`, `test_the_3b_mlx_reader_states_its_prefill_budget_5648`). Ruled 2026-10-17 (manager, on #5648; consistent with the 2026-09-28 ruling that word readings retire): a word pass whose words sit in lines is listed by line, each line's words joined, and a correction to such a line is written as a reading of the parent line, the words keeping their own readings; a word pass with no lines stays listed by word, capped by the budget. Built: `tool_context._grouped_into_lines` and `working_lines._as_lines` (`test_a_word_pass_is_listed_by_its_lines_5648`, `test_a_correction_to_a_grouped_line_is_a_reading_of_the_line_and_the_words_keep_theirs_5648`). Owed: the first-token wait scaling with the prompt (manager's call).
- `source.job.review-uses-the-projects-names-and-places` — **[PARTIAL]** (#5725) done: every review step is given the project's verified names, places and organisations (`recipes/known_names.py`; rejected, merged, unreviewed entities and concepts are left out, the most corroborated 300 are listed and the rest counted) with every other name each carries, whatever prompt the node has (`test_a_reading_of_a_confirmed_names_variant_comes_back_in_the_confirmed_spelling_5725`, `test_only_what_a_person_confirmed_is_listed_with_every_other_name_it_carries_5725`, `test_a_graph_larger_than_the_limit_says_how_many_are_left_out_5725`). Owed: the gazetteer's places beyond graph entities; the reference search over the graph and the corrected pages; names the review confirms going back to the graph; the disagreement view. The review is given the project's
  confirmed names and places (its knowledge-graph entities and gazetteer, the Find Names result) as a word list, so a
  name is spelled one way throughout; its reference search covers that graph and the project's corrected pages, not
  only other completed documents (hybrid search, limit 5, today); names it confirms go back to the graph; and a place
  where passes or readers disagree is shown by `find-where-readers-disagree`. A place or person carries its variants
  across scripts and spellings (Popayán, Popaian; 北京, Beijing), and the review is given every variant of an entity it
  may meet. *Test:* a stub reviewer given "Popayán"
  in the list and a reading "Popaian" returns the list's spelling for that line.
- `source.job.names-step-fails-on-nothing-read` — **[OK]** (#5521; ruled 2026-10-17: fail visibly, and a batch carries on and reports the count of pages left out, `summary.documents_left_out`) a names run that processes no page does not complete:
  the step fails, saying why: with no page selected the files source refuses ("would process nothing"), and when none of the N
  selected pages has a reading the step's error says so, naming the first few with the reason each is left out. A run that reads at least one page and leaves others out still completes and names
  them (`left_out`, #5691). WHY: a spaCy names workflow and the "NER per-page (local)" workflow both ended "completed"
  over 0 pages with no error, which read as success. Tests: `tests/unit/workflows/test_names_step_fails_on_nothing_5521.py`
  (`test_a_names_run_over_pages_with_no_reading_fails_and_says_why_5521`,
  `test_a_names_run_over_no_page_fails_and_says_so_5521`, `test_a_page_left_out_beside_a_page_read_still_completes_5521`).
  Owed from #5521: a spaCy pipeline for a language none ships (Latin, Greek), and the installed pipelines counted by the
  recipe's finder (#5519, #5688 compares the ones installed here).
- `source.recipe.workflow-gaps` — **[PARTIAL]** (#5726) done: `classify_script` is a shipped workflow of its own, Classify Script (a files source and the classify step, nothing else), so a person or a recipe can classify a page's script without running Transcribe (Auto-Detect) (`tests/unit/workflows/test_classify_script_workflow_5726.py`, `test_classify_script_is_a_workflow_of_its_own_5726`). Owed, re-read 2026-10-17 (R1): of the four gaps, the recipe job for the classify step is `source.job.find-the-script` (built); a page read by a model that answers by segment id is `source.read.once-lines-exist-every-reading-ties-to-a-line` (on a page with lines the model is shown each line, `test_every_reader_ties_to_lines_5721.py`); a review for each language the read presets cover is `source.job.review-is-built-from-the-project-and-a-profile` (a profile chosen by the project's answers). Left: a workflow that exports tied lines as PAGE XML training pairs; the code is `training/kraken_set.export_training_set`, reached today through the audited `training.*` actions and the Start plan's train offers, not through a workflow (a question for the manager: is a workflow wanted too?). Surveyed 2026-10-16 against 60 default workflows: a page read by
  a model that answers by segment id (`transcribe_htr` and `transcribe_cloud` are page text; `read_lines_kraken_vision`
  is per line); a review for each language the read presets cover; `classify_script`, which exists only inside
  `transcribe_auto_detect`, as a step the recipe can use; and a workflow that exports tied lines as PAGE XML training
  pairs (the code is in `training/`; no workflow seen, to be confirmed). Workflows with no recipe job today (not gaps
  by themselves): `paleo_regesto`, `paleo_translate_english`, the translate set, `extract_geo`, `extract_table`,
  `extract_events_timeline`, `describe_visual`, `clean_up_text`, `ner_per_page_local`, the `convert_to_*` set.
- `source.job.find-the-script` — **[OK]** (#5726; R1 2026-10-17; tested in `fichero-server/tests/unit/recipes/test_find_the_script_job_5726.py`, 3 pass, run alone 2026-10-17 after the gate3 pause) a recipe can name a step that finds a page's script and hand
  (the classify step on its own, the shipped workflow Classify Script), so a project whose script is not known classifies it
  without running Transcribe (Auto-Detect). It takes the page image and gives the script; it is a vision-model step, run with
  the step's own model like Correct (a cloud, MLX or Apple model); it is in no purpose's default steps, so no recipe changes
  until a person ticks it. *Test:* the job is registered with a place in the step order and a topic; a step naming it plans the
  Classify Script workflow with the step's model as the run's override.
- `source.recipe.nothing-assumes-spaces-direction-or-an-alphabet` — **[PARTIAL]** (#5728) done: the four-script matrix (`tests/unit/workflows/test_nothing_assumes_script_5728.py`): each is sent its own profile and none of another's wording (`test_each_script_is_never_sent_another_scripts_wording_5728`), the words every review shares assume no alphabet, spaces or direction (`test_what_every_profile_shares_assumes_no_alphabet_no_spaces_and_no_direction_5728`; the generic profile was reworded), a reviewer's answer in each script lands on its segments in their own order and leaves their script and direction as set (`test_each_scripts_review_lands_on_its_segments_in_their_reading_order_5728`, with the vertical page's columns in the segments' order, not the boxes'), and the table's WER is counted only where the script divides its words (`recipes/seed/scripts-without-word-spaces.txt`, `training.evaluation.word_errors`; `test_where_the_script_does_not_separate_words_the_page_is_scored_by_character_5728`, `test_where_the_script_separates_words_a_wrong_word_is_counted_5728`). A page whose lines state different scripts or directions is told each line's own, from its segment, never the project's one script (`review_profiles.line_scripts`; `test_a_page_that_mixes_scripts_is_read_line_by_line_in_each_lines_own_script_5728`). Owed: the stub profiles' genres and audits; a real run on a right-to-left and a vertical page; granularity (#5722) over a vertical page. The review, the profiles, the
  granularity and the A/B's scoring hold for ANY language and script, with none named in code; the test matrix is Spanish
  colonial, German Kurrent, Aramaic (Hebrew square script and Syriac, right to left) and Chinese (vertical columns, no
  spaces, variant and abbreviated characters), chosen to differ from one another in spaces, direction and alphabet, so
  that passing all four is evidence for the rest and a fifth script is a data file, never a code change. A profile carries its
  own letter or character audit (Latin: u/v, i/j, long-s; Kurrent: minim runs, ſ/s; Hebrew and Aramaic: ד/ר, ב/כ,
  final forms; Chinese: variant forms, popular abbreviations, absent punctuation); no lens assumes word spaces, a left to
  right order or an alphabet. A region is a region whatever its direction, and a line is a segment: its direction,
  script and language come from the segment, never from the language's name, and the review keeps them. The table's
  WER appears only where the script separates words; Chinese is scored by character. *Test:* the matrix of the four,
  each with a stub reviewer, never sent another's wording, and a right-to-left and a vertical page both returned in
  their segments' reading order.
- `source.job.review-asks-one-answer-line-per-segment-id` — **[OK]** (#5719; the review prompts ask for the ids and the answer is tied by id, pinned by `fichero-server/tests/unit/workflows/test_review_corrects_the_lines_5654.py`) the paleographer review, shown the
  page's lines as `<segment id> | box | maker | text`, is told to answer one line per shown line as `<segment id> |
  <corrected text>`, in the same order, never merging, splitting, dropping or adding a line; the prompt it is sent
  says so. WHY (2026-10-16, page 39_Hoja_549_Recto.JPG, project 17402): the default prompt said only "output only the
  corrected transcription"; Qwen2.5-VL answered 16 lines for 44, `correct_lines` matched nothing, and the review
  stayed a page text tied to no line (its pass has no segments, its geometry "not supported"). *Test:* a model that
  answers by id only when the prompt asks for it ties its corrections to the lines; one asked nothing answers a
  paragraph and the step says "not tied to lines".
- `source.job.correct-re-asks-per-line-when-it-does-not-tie` — **[OK]** (#5722, #5720; tested in `fichero-server/tests/unit/workflows/test_review_re_asks_lines_5720.py`, including the card's `lines_per_request` as the batch limit, `transcribe_review.py`, eight when a card states none) hybrid, decided 2026-10-16: a
  correction is first asked of the whole page (one call, the image and every line with its id and box, the answer
  `id | text` per line, #5719); the lines it leaves out or cannot match are then re-asked in batches of up to eight,
  each line cut from the page and sent with its current text, the page's own text beside it for context, the model
  answering a JSON array, a batch that does not match re-asked line by line (as `llm/line_reader.py` does), never
  guessed into place. Where a line still cannot be tied, THAT PAGE'S STEP FAILS, naming the model, the lines and why;
  it does not end as "not tied to lines". Kraken's reading stays the line's counting reading, so a failed correction
  loses nothing. For a model that does not localise text as for one that does, a cloud model as a local one. *Test:*
  with a stub that answers a paragraph to the page and arrays to the batches, every line is tied; with one that
  answers nothing usable, the step fails for that page and the Kraken readings are unchanged.
- `source.try.asking-granularity-is-measured` — **[PARTIAL]** (#5722) *Built 2026-10-16: the card's `lines_per_request` (Card field, `recipes/cards.lines_per_request_for`, set on the Qwen2.5-VL 3B card) caps every re-ask request (`test_review_re_asks_lines_5720.py::test_a_request_never_exceeds_the_model_cards_lines_per_request_5722`); **Built 2026-10-17 (engine):** the bake-off asks its two best vision candidates and any named at lines / region / page (`evaluation.requests_for`, `granularities_for`, `evaluate`'s trial pass; `granularities_for_best`, `named`), one table row per way asked (`granularity` on the row, `winner_granularity`), Use This records it on the override and the step (`use_this(granularity=)`), and `next_run` shows the extra cost first (`granularity_run_cost_usd`); pinned by `test_bakeoff_granularity_5722.py`. **Built 2026-10-18:** the read step reads with the recipe's granularity at Start (`start.plan_start` gives the run's read node `read_granularity`; the transcribe tool passes it to `line_reader.read_lines(granularity=)`, `request_groups`; pinned by `fichero-server/tests/unit/recipes/test_granularity_reaches_the_read_5722.py`). STILL OWED: answers tied by segment id rather than by position in an array; the app naming readers to compare (`named`) and showing the granularity column; a real run.* how a model is asked is an option the A/B measures,
  not a constant: the whole page, a region (a paragraph, the unit Kraken's regions give) at a time, or a few lines at a
  time, always with segment ids and always answered by id. A card states `lines_per_request`, the most lines the model is asked to read at once (decided 2026-10-16: a field
  on the card, never found by trying: a large cloud model, the whole page; a 2B local model, a few lines), and a request
  never exceeds it; a region longer than it is split on line boundaries. The bake-off tries the two best candidates
  (by their score at their default granularity) and any the person named, at each granularity,
  within the cost shown beforehand; the others run once at their default, and the table names the granularity beside each row, so a smaller
  model can win at paragraph. The recipe takes the winner's model AND granularity; if none beats the Kraken reading on
  the person's corrected pages, the recipe keeps Kraken's reading and says so. *Test:* a stub whose answers are right
  only per paragraph wins at paragraph and loses at page; the recipe records both.
  *Sizes (2026-10-16):* **lines** is one line a request; **region** is one region (`TextRegion`, or the whole page
  where the page has none) a request, split on line boundaries at the card's `lines_per_request`; **page** is the
  whole page in one request, tried only for a card that states no `lines_per_request` (a card that states one says
  the model cannot take a page, so `page` would only be `region` again). A model that reads one line at a time
  by nature (Kraken, Apple Vision) is measured once and has no granularity. The cost of the extra runs is shown with
  the cost of the first (`next_run`), as an upper bound, before anything runs. Test:
  `fichero-server/tests/unit/recipes/test_bakeoff_granularity_5722.py`.
- `source.job.correct-onto-lines` — **[OK]** (#5654) *Built 2026-10-10: the paleographer's review
  (`workflows/tools/transcribe_review.py`, the `correct` job's workflow) is shown the page's lines
  (`tool_context`), and each review it saves is put back onto them (`llm/working_lines.correct_lines`):
  matched by segment id when every line of the answer names one, else line for line when the answer has as
  many lines as it was shown; each changed line gets a reading through `write_readings`
  (`representation.create`, under the run, so `workflow`, never `human`). Pinned by
  `fichero-server/tests/unit/workflows/test_review_corrects_the_lines_5654.py`.* a correcting step's
  corrections land as readings on the lines of the page's working pass, one per line it changed: a
  transcription, as written unless the step says otherwise, made by the step's model and naming the line's
  counting reading it corrects. A line it left unchanged gets no new reading, and a line a person read keeps
  the person's reading. The page's text then reads the corrections, so the steps after it (names,
  statements, search) read the corrected lines. A correction that cannot be matched to the lines is never
  guessed onto them: it stays the page's review, and the step's result for that page says "not tied to
  lines".
- `source.lines.read-the-marked-line` — **[PARTIAL]** (#5445) a vision model reading Kraken's lines is shown
  the target line alone: the crop is cut to the line's own polygon with the outside masked (or the
  target is marked), never a crop in which a neighbouring line is more complete than the target. Before
  (2026-10-04) `llm/line_reader.crop_line` showed about two and a half lines with the target unmarked, and
  on SM_NPQ_C01_005 lines 4–19 held the text of the line above; a check of the exported training set
  flagged a quarter of a two-photo trial as shifted. Built (2026-10-17): `crop_line` paints everything
  outside the polygon (widened by a sixth of the line's height, for ascenders) the crop's median paper
  colour; the runner's copy (`remote_read/runner.crop_line`) does the same, pixel for pixel; the training
  pairs, the checker's cards and the evaluation all cut through `crop_line`. Tested in
  `fichero-server/tests/unit/llm/test_read_the_marked_line_5445.py`. Not built: a real run on
  SM_NPQ_C01_005 to count the lines that still read a neighbour; training sets exported before this
  hold the old pictures and are built again.
- `source.lines.reading-checked-against-the-page` — **[PARTIAL]** (#5446) *Built (2026-10-05): `POST /api/check/runs` with `check: line-against-page` (provider `kraken`, a Kraken reader) queues a `check-lines` job on the local model lane; `checking/line_check.py` reads each line of the pass again through `kraken_runtime.read_given_lines`, scores the reading (1 − accent-blind CER) against its own rough read and up to two same-column lines either side, and rejects (`check.verdict`, trust `model`, the scores in its reasons) a reading closer to a neighbour (beaten by 0.15 and itself at least 0.40) or below 0.30; passing lines get no verdict, and a line a person has checked is not checked again; `GET /api/check/runs/{id}` gives the counts and each flagged line with its scores. Built (2026-10-08, #5524): while the check runs or waits for memory, those counts and flags are the pages it has finished so far, and its job's reason says the counts; a stop for memory waits and carries on after its last finished page (never `failed`, no line given a second verdict); a passing line is counted, not given a verdict; the memory reason shows the two amounts it compared so they never read as the same number (`fichero-server/tests/unit/check/test_line_check_memory.py`). Empty and `null` readings are left out by the training set's own rule. Tested in `fichero-server/tests/unit/check/test_line_against_page.py`. Shown in the app (2026-10-05): `FlaggedLineStore` reads the reading verdicts and each run that rejected a line on the page; a line whose reading's newest verdict is still the run's reject carries a flag mark in the Order list (the Segments pane's list), the strip and the grid, with its flag and scores in words on hover ("Teacher text matches the next line better (0.52 vs 0.21)"), the Segments pane's head counts the page's flagged lines, and the Inspector says the flag, the run's counts and offers Confirm Reading (a person's `check.verdict` confirm on the rejected reading, which clears the mark in place); tested in `fichero/Tests/Unit/general/Models/FlaggedLineStoreTests.swift`. Not built: a null or empty line shown as flagged (the training set leaves it out by its own rule, unmarked).* each model reading of a Kraken line
  is scored against that line's own rough Kraken read and its neighbours' (the characters they share);
  a reading that matches a neighbour clearly better than its own line, a null or empty reading, and one
  below a set score are flagged, with the scores, so a person can look. A flagged line keeps its
  reading as a proposal, is shown as flagged, and is kept out of a training set
  (`compute.tune.set-excludes-flagged-lines`).
- `source.lines.null-is-no-text` — **[OK]** (#5447) a model's null answer for a line, or the word
  `null` alone (quoted or not, any case), stores no text: the line has no reading from that model. Built
  (2026-10-17): `llm/line_reader.parse_answer` and `cut_short_reading` read the word as no text (so does
  `remote_read`, which shares the parse); the word inside a longer line is kept. Tested in
  `fichero-server/tests/unit/llm/test_null_is_no_text_5447.py`. Rows already stored as `null` are not
  rewritten; re-reading the page replaces them.
- `source.split.carries-readings-over` — **[PARTIAL]** (#5452; ruled 2026-10-04 as the rule for whenever a
  split runs, not a build priority) splitting a spread moves each of its line segments, with every
  pass's readings, to the half its polygon falls in, re-normalised to that half's region; a line that
  crosses the gutter is flagged, never cut. The spread keeps its passes as history, nothing is read
  again or paid for, and the halves count as the pages with their carried passes, so "already done"
  sees the work. Today the split only makes the halves (`persist_workflow_child_regions`): a spread
  split after its lines were read leaves them on the spread, which stops counting, and a recipe run
  would read every half again with a paid model. *Built (2026-10-17):* `split_carry.carry_readings_over`,
  called by both splits (the route's `split_image_impl` and the workflow's `persist_workflow_child_regions`):
  a result's boxes not yet rows are converted first; each live pass of the spread gets a copy on each half
  that holds one of its lines; each line (kind `line`, by the centre of its outline) is copied to its half,
  box, outline and baseline re-normalised and clamped to the half, with every reading, the readings'
  revisions, the person's reading and pass choices and the pass's reading orders; a line reaching past its
  half is flagged `metadata.crosses_gutter`, never cut; the spread keeps all of it. Tested in
  `fichero-server/tests/unit/api/test_split_carries_readings_5452.py` (`is_done` sees the halves).
  Regions and words go too (2026-10-17): every kind of segment is carried with its readings, a segment inside
  another (a word or character in its line) with the line it sits in, still inside it, while a region and a line go by their own centre (`test_a_line_goes_by_its_own_centre_even_inside_a_region_that_crosses_the_gutter`)
  (`test_regions_and_words_go_with_their_lines_and_keep_their_parents`).
  *Not built:* a real run on a read spread; the spread's page-level transcriptions and `page_content` stay on
  the spread only (so "read a page" still reads a half);
  a line measured on a rendition's frame refuses the split loudly rather than being placed by a guess; the
  app showing the flag.
- `source.recipe.apple-finds-lines-on-print` — **[OK]** (#5451; ruled 2026-10-17, replacing the 2026-10-04
  wording; tested in `fichero-server/tests/unit/recipes/test_apple_finds_lines_on_print_5451.py`: the card `apple:vision/find-lines@os`, the rule in `assemble._choose`, the planner's `detect_regions_apple_lines` workflow, `ocr_geometry.lines_only`; when a Kraken reader follows, it still finds its own lines) for print and typescript a recipe's Find lines step runs Apple Vision for its line finding only:
  Apple finds the lines and keeps no text (the Detect Segments tool's `keep_text` off: the page's line boxes
  carry no reading, no word boxes), so the text of a print page comes from the reader the recipe names. A
  handwriting page goes to Kraken (the card states print and typescript only). Apple's OCR of handwriting is
  noise (Mosquera SM_NPQ_C01_030: `WtrtNI-`, `¥eTIQ`) and would otherwise reach the Order tab as a reading.
- `source.recipe.line-finders-are-a-candidate-list` — **[PARTIAL]** (#5451; ruled 2026-10-17; *built: `bakeoff.line_finders()` lists a finder for every card naming `find-lines`, one with no workflow is listed not scored, and the planner skips a pin it cannot run by name; pinned by `fichero-server/tests/unit/recipes/test_line_finders_candidate_list_5451.py`. Not built: a cloud or MLX line finder that runs, and the online search for line finders*) the Find lines route for
  a kind of page (print, typescript, a hand) is a LIST of candidate line finders, never a constant: for print the
  list starts with Apple lines-only (`source.recipe.apple-finds-lines-on-print`); for a hand it holds Kraken's
  line finder, a cloud model and an MLX model, and the bake-off compares them on the person's pages
  (`source.try.bakeoff-is-the-same-tool`, the line finders' comparison) so the person decides with the result in
  front of them. The recipe also looks online (Hugging Face, Zenodo) for line finders it does not yet know, as it
  does for readers (`source.find.wide-every-time`). The candidates come from the cards that name the Find lines
  job, so adding a card adds a candidate; the planner maps a chosen candidate's pin to its shipped workflow
  from a table, and a pin with no workflow is skipped saying so ("cannot run here"), never run as Kraken.
  *Test:* every card naming `find-lines` is a bake-off candidate; a pin with no workflow is skipped by name.
- `source.job.find-statements.candidates` — **[PARTIAL]** (#5637; ruled 2026-10-17; *built: the free-parser default and the installed-model preference in `assemble._choose`, the parser cards in `discovery.known_cards`; pinned by `fichero-server/tests/unit/recipes/test_find_statements_candidates_5637.py`; Apple Intelligence and the cloud text models of the provider rows are listed candidates, a cloud one flagged needs-permission, pinned by `fichero-server/tests/unit/recipes/test_find_statements_cloud_candidates.py`. Not built: Apple Intelligence running as a statements model where this build has it, and the bake-off comparing the candidates, cost first*) Find statements is not parser-or-nothing:
  its candidates are the spaCy parser's triples, Apple Intelligence, and text models such as Claude or Qwen, compared
  by the same bake-off pattern as reading, with the cost shown first. The default: where no text model is installed
  on this Mac, the free local candidates (the parser, Apple Intelligence) run at Start, and a text model is offered
  beside them (the person chooses it; nothing is downloaded or sent off the Mac by itself); where a text model is
  installed here, the rules take it over the parser. *Test:* with no text model the recipe's statements step is the
  parser's and the step offers a model; with one installed it is that model.
- `source.model.page-text-is-constructed-from-the-segments` — **[PARTIAL]** (#5486, #5467; ruled 2026-10-17; *built for the correcting step: `transcribe_review` no longer writes the page text (`update_page_content` off), so an untied review leaves the chosen reading's text; pinned by `fichero-server/tests/unit/workflows/test_page_text_is_constructed_from_segments_5486.py`. Not built: the other producers that still write a page-level text (LLM Transcribe, DOCX, Markdown, legacy transcriptions) tying onto lines, `source-model.md`'s table*) a page's text is
  the CHOSEN reading, constructed from its segments (the lines of the working pass, in reading order) by the engine
  (`actions/page_text_cache.py`), never a separate blob a step writes and a later round overwrites. A step that
  reads or corrects a page writes readings onto the page's lines; it does not write the page's text. Where a
  correction cannot be tied to the lines the step fails for that page (`source.job.correct-re-asks-per-line-when-it-does-not-tie`)
  and the page's text stays what the chosen reading was. *Test:* the correcting step does not write the page text
  by default; with the corrected readings on the lines, the page's text is the lines' text.
- `source.job.check` — **[PARTIAL]** (#5404) *Built: `check` is in the job registry (`recipes/jobs.py`), its layer a setting, so a recipe can name it after any layer; pinned by `fichero-server/tests/unit/recipes/test_job_registry.py`. Not built: a tool that runs it and stores each verdict at the checker's trust level.* checking a layer's proposals (readings, names, statements, links) is a job a recipe can name, run by a person or a checker model; each verdict (confirm, correct, reject) keeps its reasons and the checker's trust level, a model's check is never recorded as a person's, and a corrected proposal names the one it replaces.
- `source.job.find-statements` — **[PARTIAL]** (#4949, #5637; built: spaCy triples and an installed text model as candidates, `assemble.py`, pinned by `test_find_statements_candidates_5637.py`; not built: Apple Intelligence and cloud text models as bake-off candidates) finding statements (subject, relation, object),
  each naming the stretch of text it came from, is a job a recipe can name.
- `source.job.find-statements.parser-tier` — **[PARTIAL]** (#5637) a free tier for Find statements: the bundled
  spaCy pipelines (`es_core_news_sm`, `en_core_web_sm`) are offered for the step (`spacy:svo/<pipeline>`, the
  person's to choose; never ranked by the rules over a text model they have; where none is installed the rules
  take the parser, #5637 ruled 2026-10-17, `source.job.find-statements.candidates`), and with one chosen the step reads
  the dependency parse's subject-verb-object triples (`knowledge/spacy_svo.py`) on this Mac, at no cost, instead of
  asking a language model. Each triple is a **proposal, never a fact**: it passes the same gates a model's
  statement does (the shared `svo_quality` rules, a subject that is one of the page's names, the grammar check),
  is written through `_write_kg_rows` unreviewed and marked as the parser's (`provider` spacy, `model` the
  pipeline), carries its sentence as its words, and rests on its line as every statement does
  (`source.extract.statements-on-segments`). A page whose reading is below the certainty bar Find Names uses
  (#5694, `runner.reading_too_uncertain`) gives no parser statements, in the step (its summary's `left_out`
  names it, "its reading is too uncertain to find statements in") and in the import's NLP draft. The parser
  finds no dates of its own: the dates pass is a model's only. **Built 2026-10-12 (engine):**
  `workflows/tools/extract_svo_only.py` with provider `spacy`; the cards in `discovery._parser_statement_cards`.
  *Test:*
  `fichero-server/tests/unit/workflows/test_statements_parser_tier_5637.py`. *Not built: precision and recall
  against the model step on corrected pages in the bake-off; a relation-extraction component trained on
  corrected statements; a model pass refining what the parser kept.*
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
- `source.project.has-settings` — **[PARTIAL]** (built in part, pinned by `fichero-server/tests/unit/api/test_project_setup_is_saved.py`; what is still unbuilt is not yet written down here, R0 2026-10-17; #4951) a project (today's library) has settings of its
  own (purpose, recipe, defaults, rules, synced folders); one never set up behaves exactly as before.
- `source.project.setup-saves-what-is-sent` — **[OK]** (#5584; built: the `project.save_setup` action keeps a
  part its params leave unset; tested in `fichero-server/tests/unit/recipes/test_setup_through_mcp_edges.py`) saving a project's setup
  (`PUT /api/recipes/project`, MCP `fichero_recipes_save_project_setup`) changes only the parts sent:
  a part left out (the answers, or the recipe) is kept as it was, and a part sent as null is removed.
  The route's description says so. An agent onboarding a project saved its recipe alone and lost
  the answers it had saved a step before. Through MCP a part is sent only when given (the generated tool
  drops an argument left None), so the tool keeps what it is not given and cannot remove a part.
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
- `source.project.automatic-after-first-yes` — **[PARTIAL]** (#4951) **Built 2026-10-03 (engine):** `GET /api/recipes/project/start` shows what Start would run and on how many pages; `POST` records the first yes (`recipe/started.yaml`: when, recipe id and version), audited and undoable, refused while the plan has refusals (a recipe that fails the check, or nothing to run; a step it cannot run is skipped, #5390; **2026-10-11:** a project with no pages yet, said in words, "the project has no pages yet: add a folder or files to it, then press Start", and no run is queued, `fichero-server/tests/unit/recipes/test_start_with_nothing_says_so.py`; seen when the folder chosen in Set Up never reached the project and Start ran every step on nothing); and it runs the recipe (#5390, `source.recipe.start-runs-the-steps`); on-add after it is `source.onboard.just-do-it`; pinned by `fichero-server/tests/unit/api/test_start_is_the_first_yes.py` and `fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py`. nothing in a project runs by itself
  until the person presses Start at the end of setup (the first yes), which shows what will run,
  on how many pages, with an estimate; what it makes counts as the record only as the project's
  rule allows.
- `source.recipe.start-runs-the-steps` — **[OK]** (#5390, #5497, #5498, #5684; built: `recipes/runner.py`, the `run-a-recipe` job; tested in `fichero-server/tests/unit/recipes/test_recipe_execution_to_spec.py`, `fichero-server/tests/unit/recipes/test_recipe_runs_to_spec.py`, `fichero-server/tests/unit/recipes/test_step_that_cannot_start_5684.py`; **built 2026-10-11 (#5684):** a step whose work raises before it can end (its runtime would not start, a native library would not load) fails that step alone, saying in one line what the person can do ("Find regions could not start: a library it needs would not load on this Mac. Restart Fichero, or reinstall."), the technical text in the log only; steps that do not need it still run; and Kraken's status reads not available, with that reason, when its native libraries do not load (`kraken_runtime.runtime_status` `loads`). WHY: in the MCP walk one dlopen failure ended the run and its raw text was repeated on every later step, ~12 KB) pressing Start runs the recipe over the
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
  account; a run still waiting says what it waits for (recipe runs go one at a time). **(#5615)** A run that has
  ended has no stage waiting or running: each says "not run" with why (see `activity.ended-run-reads-ended`).
- `source.recipe.folder-scoped-start` — **[OK]** (#5540; built 2026-10-10: `folder_id` on `GET|POST
  /api/recipes/project/start` and `runner.enqueue`, `runner.folder_scope`, `done.material`/`annotate` `within`;
  tested in `fichero-server/tests/unit/recipes/test_recipe_batches_to_spec.py`) Start, and the Start plan before
  it, can be given one folder node (`folder_id`): the plan, its estimate and each step's "already done on N of M
  pages" then cover only that folder's live pages, those of its folders inside it included, and the run started
  from it touches no page outside it. With no folder it is the whole project, as before. The engine works out the
  folder's pages; a folder that is not in the project is refused (422), and one with no pages refuses Start.
  App **[PARTIAL]** (built 2026-10-10, not yet seen in a build: `RunRecipeOnFolderMenuItem`, `RecipeFolderScope`,
  `RecipeSetupStore.loadStartPlan(folderId:)`/`start(folderId:)`; tested in
  `MenuTerminologyBoundaryTests.testRunTheRecipeOnThisFolderIsOneComponent`, `testRecipeFolderScope`,
  `testProjectMenuDeclaresTheStageSectionsInRecipeOrder`, and
  `RecipeSetupStoreTests.folderPlanAndStartSendTheFolder`): one item, "Run the Recipe on This Folder…", in the
  Project menu's Read section and in the library's and the sidebar's folder context menus (one component, one
  label, one action). It acts on one folder: the clicked folder in a context menu (not a folder among several
  selected); in the menu bar the one selected folder, or with nothing selected the folder the window shows; with
  anything else the menu bar's item is disabled and says "Select one folder to run the recipe on", and a context
  menu does not offer it. It reads the folder's Start plan (`folder_id`) and, when the plan can start, starts it
  on that folder and opens the run in Activity, as Start does; when it cannot, Set Up… opens so the steps say why,
  as Start does. Not seen: Set Up… then shows the whole project's plan, so a refusal only the folder has (a folder
  with no pages) is not on its screen.
- `source.recipe.batch-at-archive-scale` — **[OK]** (#5540; rule 9 of `compute/jobs-and-fine-tuning.md`; built
  2026-10-10: `runner._batches`, `runner._run_batch`, `runner.BATCH_PAGE_LIMIT`; tested as above) a
  run goes a batch at a time: a batch is one folder (a page's nearest folder; pages in no folder are one
  folder of their own), or at most 500 pages of it, whichever is smaller (a photograph cut into pages
  counts once, and its pages go with it). Every step finishes on a batch before the next batch starts, so
  the first volume is read, named and searchable while the rest waits; no step is ever handed more than one
  batch's pages at once. Folders go in the order of the project's material. The whole-project Start, a
  folder's Start and an import's run are the same loop (an import is usually one batch). **[OK, provisional]**
  (#5540: a default chosen while the maintainer was away, awaiting his ruling; built 2026-10-10:
  `runner._note_batch`, `runner._did_no_page`, `runner._halted`, `runner.OUTRIGHT_IN_A_ROW`, `run_view.summary`; tested in
  `test_recipe_batches_to_spec.py::test_a_page_failing_in_one_batch_does_not_stop_the_next`,
  `::test_a_step_failing_outright_three_batches_in_a_row_stops_the_run`) a step that fails or is not run on a
  batch does not end the run: the step's failed batches are kept on it (`failed_batches`: the folder, the step's
  job on it, why), and the run carries on to the next batch, so one bad page no longer holds an 800-folder run at
  the same folder on every Start. A run with failures ends failed, its row saying "Done with failures: step
  lines, read failed on 1 of 4 folders (B: why)" and how many folders it finished. **(2026-10-11)** Each cause
  is said once, with every step it stopped ("2 steps (correct; translate-transliterate-normalise) did not run:
  why"), never once a step, and with no folders counted the row names no count (it said "1 of 0 folders"; seen on a
  first-run onboarding, one download failure said eight times; `runner._failures_words`,
  `fichero-server/tests/unit/recipes/test_one_failure_one_line.py`). Its summary lists each failed
  batch's pages with Read Again for just those (`source.onboard.auto.results-summary`), and the next Start offers
  the step again (`source.recipe.done-is-not-redone` skips the pages it did). A step that fails **outright** on a
  batch (it did none of the batch's pages: a missing model, the step itself crashing) on 3 batches in a row stops
  the run there, saying "Stopped: step lines, read failed on 3 folders in a row without doing a page (why)", so a
  broken model does not burn through 800 folders; a batch it did any page of resets the count. A step that is not
  a workflow (a check, an embed) cannot say which pages it did, so its every failure counts as outright. A step
  that covers the whole project at once (publish) runs once, on the last batch. A step's
  state over the run is its worst on any batch; its counts (already done, blank versos, by kind, what it made)
  add up over the batches.
- `source.recipe.batch-checkpoint` — **[OK]** (#5540; built 2026-10-10: the run's `batches_done`,
  `batch_states`, `folders_done`, `folders_total` in its row's detail; tested as above) every finished batch is a
  checkpoint on the run's row: its `folders_done` of `folders_total`, the batches done, and, inside the batch
  being run, which steps finished on it. A quit or crash (the run is carried on when the project opens again)
  resumes at the next unfinished step of the unfinished batch, and within that step at its next unfinished page
  (`source.recipe.done-is-not-redone`): a finished batch, or a step finished on the interrupted batch, is never
  run again, even a step that cannot tell what it has done (tested also with a failed step carried past, in
  `::test_a_resumed_run_after_a_failed_batch_redoes_nothing`). A person's Stop ends the run after the current
  batch (#5609; tested in `::test_stop_still_ends_the_run_after_the_current_batch`), failures or not; Start then
  begins a new run, which skips only what `source.recipe.done-is-not-redone` can tell is done.
- `activity.run.progress-per-folder` — **[OK]** (#5540; built 2026-10-10: `runner._folders_words`, `folders_done`
  and `folders_total` on `GET /api/recipes/project/runs/{id}`; tested as above) a recipe run's row says how far
  it is in folders, not one figure for every page: "Running step lines, read: 3 of 800 folders done" while it
  runs, and a run that fails or is stopped says how many folders it finished; its status carries
  `folders_done` and `folders_total` (and `folder_id` for a folder's run). App **[OK]** (built 2026-10-10, not yet
  seen in a build: `RecipeRunFolders`, `ActivityStore.recipeRunFolders`, `ProjectRunStrip`; tested in
  `ProjectRunStripTests.testFolderWords_sayHowFarInFolders_onlyForARunOverSeveral`,
  `testStrip_aRunOverManyFolders_saysHowManyAreDone_fromItsStatus`,
  `testStrip_aRunOverOneFolder_saysNothingMoreThanItsStage`): the project window's run strip says how far the run
  is in folders after its stage ("Transcribe (Kraken) · stage 1 of 3 · 3 of 800 folders"), from the run's
  `folders_done` and `folders_total` (`GET /api/recipes/project/runs/{id}`), only when the run goes over more than
  one folder (a run over one folder, as an import's one batch, says nothing extra); the figure is read again each
  time the run's tree is, one run's entry replaced in place.
- `source.recipe.step-skipped-says-why` — **[OK]** (#5390; built: `recipes/start.py` `skipped`; tested as above) a step Start cannot run (no model, a
  condition Start cannot honour yet, a cloud step in a project that keeps its pages on this Mac, a
  job no card runs yet) is skipped, and the plan and the recipe run name the step and why; the other
  steps still run. A recipe with nothing runnable, or one that fails the recipe check, never starts.

Profiles (the defaults section of a recipe)
- `source.recipe.no-text-found-is-not-a-failure` — **[OK]** (#5668, found by the end-to-end onboarding run)
  *Built: `vision_base`'s empty-result branch, for Apple's text recognition; pinned by
  `fichero-server/tests/unit/importers/test_onboarding_e2e_5668.py`.* When Apple's text recognition finds no
  text on a page, that is what it found, said as such ("Apple's text recognition found no text on this
  page"), not a failed read: it is not counted in the run's failures and not offered to read again (it would
  find the same nothing). A vision model that answers with nothing is still a failure, as before, in
  its wording.
- `source.pages.image-found-wherever-kept` — **[OK]** (#5668, found by the end-to-end onboarding run) *Built:
  `recipes/regions.py`, `recipes/prepare.py`, `finddocs/job.py` (the blank-verso rule and the image cues),
  `training/evaluation.reference_page`, `training/yolo_set.export_region_set`, all through
  `workflows/tools/sources._resolve_abs_path`; pinned by
  `fichero-server/tests/unit/importers/test_onboarding_e2e_5668.py`.* Every step that looks at a page's image
  finds it the one way the reading steps do: a page copied into the project (its stored path inside the
  package, `files/…`) and a linked page alike. None opens the stored path as it stands. Found when a copied
  folder's Find Regions said every page had no image, the blank versos were sent to Apple Vision (the
  blank-verso rule saw no image), and Find the Documents worked from the text alone.
- `source.onboard.icloud-pages-warned` — **[PARTIAL]** (#5669) *Built: `importers/keep_a_copy.summary`, the
  Start plan's and an import's `in_icloud`, `document.copy_into_project`. Not built: Ready's and the import
  sheet's Swift (B).* Before Start, and in an import's answer, Fichero says how many of the project's pages are
  linked to originals that are in iCloud and not on this Mac ("34 of 92 pages are in iCloud and not on this
  Mac") and offers, first, to copy them into the project. Only a page's own file is counted: a folder is never
  "a page in iCloud" (a directory reports a size with no blocks of its own, which is not a placeholder), and
  pages copied into the project are never counted. *Test:*
  `fichero-server/tests/unit/importers/test_dataless_sources.py` (a directory is not dataless) and
  `fichero-server/tests/unit/importers/test_onboarding_e2e_5668.py` (a Copy import of a folder warns of nothing).
- `source.onboard.correct-off-unless-a-corrector-is-here` — **[PARTIAL]** (#5677; ruled Q3 2026-10-17: with a cloud key set, Correct is OFFERED at Ready with its cost, never on by itself. *Built: the off line names a cloud and its price only when that provider has a key set here (`Answers.cloud_keys`), and carries it as `offered` (card, provider, pages, cost), `fichero-server/tests/unit/recipes/test_correct_offered_with_a_key_5677.py`. The corrector offered is the person's own: a cloud vision reader from their Settings › AI rows whose provider has a key, priced per page from the price list (`recipes._cloud_correctors`, passed to `assemble` as `offered`, never among the rules' cards); one that lists no language of the project's is offered saying so ("try it on a few pages first"), and one with no known price is not offered. Taken through `POST /api/recipes/project/steps/use-candidate` (step `correct`, the offered `card`) once the answers turn Correct on. Not built: Ready's button that turns it on from the offer (app)*) Correct (a second model checking the
  reading) is in a purpose's recipe only when a corrector is already available: a model for it already on this Mac
  (or one that ships with Fichero), or a cloud model the project allows; or when the person asks for it (ticks
  Correct, or answers yes to "Correct with a second model?"). Otherwise it is off, and the recipe (`left_off`) and the
  Start plan (`left_off`) say so in one line with what turning it on would cost: the download ("Turning it on
  downloads Qwen2.5-VL 7B (OCR), 5.7 GB") or the cloud's price for the project's pages; where no corrector fits at
  all, the line says why in the rules' words (the Mac's memory, a language no corrector knows). Saying no to the
  question turns it off, saying so. Seen 2026-10-11: choosing
  Read brought a Correct step pinned to a 5.7 GB model no Mac had. Built: `assemble.correct_available`, the
  recipe's `left_off`, the plan's `left_off`; tested in
  `fichero-server/tests/unit/recipes/test_correct_off_unless_available_5677.py`. **App:** Set Up's Read page lists
  Read's left-off steps and the Start section all of them, one line each with **Turn On**, which ticks the step,
  answers its question yes and has the engine propose the plan again (`RecipeLeftOffRows`,
  `RecipeSetupStore.turnOn(job:)`). Set Up now sends the stage questions' answers with every proposal
  (`job_answers`), so a yes on the Read page reaches the rule. Tested in `RecipeLeftOffTests`.
- `source.recipe.missing-model-offered` — **[OK]** (#5367; built: `missing_models` in `recipes/start.py`, the plan's `downloads`; tested in `fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py` and, for a Kraken reader, `fichero-server/tests/unit/recipes/test_kraken_reader_offered_before_start.py`) a step pinned to a model that is not on this
  Mac and can be downloaded (a spaCy pipeline, or a catalogue or Zenodo Kraken reader; MLX models are `local_models_to_download`) is named in the Start plan with the model and its size,
  and the plan offers the download (`downloads`, each a `download-model` job on the network lane). **Changed
  2026-10-11 (#5664, ruled: Set Up never downloads):** Start is no longer refused for it. Pressing Start queues
  each such download itself through the one download path (`start.queue_downloads`, `model.download`'s
  `enqueue_download`), as an import after Start does too, and the run's steps on it wait for it to land
  (`awaited`), so the step still never fails at run time for want of it. The plan says what Start will fetch in
  one line for Ready (`start_downloads`: each model by the name a person reads, its size, the total, e.g. "Start
  downloads Qwen2.5-VL 7B (OCR) (5.7 GB) and the Kraken reader PP-OCRv6 (medium) (60 MB): 5.8 GB in all."). Only a
  model that cannot be downloaded at all still refuses Start, in words. Pinned by
  `fichero-server/tests/unit/recipes/test_start_while_models_download.py`. **(2026-10-11)** What Start fetches
  includes setting up this Mac's local model runtime when a step runs on the local model server and the runtime is
  not set up (outside the app, where MLX does not ship inside it): one more download, "the local model runtime",
  a `download-model` job (`mlx-runtime:mlx`) in Activity, and the steps on it wait for it; a model download that
  finds the runtime missing sets it up first instead of failing. No sentence names an API route or a file path
  (it said "Call POST /api/local-inference/runtime/provision" and the interpreter's path; where it looked goes to
  the engine's log). `start.runtime_to_set_up`, `MLXRuntime.provision_now`/`ensure_provisioned`;
  `fichero-server/tests/unit/recipes/test_start_sets_up_local_models.py`. *Not built: Ready's Swift (B); a
  licence acceptance asked before Start (no acceptance is recorded: the rules never pin a model whose licence is
  not open, and a person's own choice of one is its acceptance).*
- `source.recipe.done-is-not-redone` — **[OK]** (#5390; built: `recipes/done.py`, the plan's `done`/`of`/`note` and Start's `redo`; tested in `fichero-server/tests/unit/recipes/test_recipe_cards_to_spec.py`) a started recipe does not run a step again on a
  page that already has its output: splitting, on a photograph already cut into pages; finding lines, on a page
  with a pass that has lines; reading lines, on a page with a pass read by the step's own model; reading a page, on
  a page with a transcription saved by the step's own model. The Start plan says,
  for each such step, "already done on N of M pages", and the run does only the rest, unless the person names
  the steps to redo when pressing Start. A step that cannot tell (names, statements, checks, export, publish)
  runs on every page, and the plan says so.
  **[OK] (#5584; built: `recipes/done.py`; tested in `fichero-server/tests/unit/recipes/test_setup_through_mcp_edges.py`):** correcting and finding names
  can tell too: correcting, on a page with a reviewed transcription saved by the step's own model (#5616: its
  effective model, the step's choice else its workflow's; with neither, a review its own workflow saved, never
  any model's review from a run outside the recipe; `done.effective_model`, pinned by
  `fichero-server/tests/unit/recipes/test_start_plan_counts_what_ran_5616.py`, which also pins `last_run` and
  `last_why` on a step a failed run left unfinished);
  finding names, on a page some entity names as a page it was found on, or one a finished run's names step
  ran on (#5706: a page whose text names no one is done once looked at). The pages a step runs on are worked out when it starts, so pages a
  split made earlier in the same run are read like any others. **Find Regions and redo (#5689):** a page whose regions the step's own model found is done for
  Find Regions (for Kraken's segmenter, which keeps the page's lines with its regions, a page that has lines
  too; regions found before it did are found once more, with their lines, so Read never segments the page
  itself). The plan as started says what it redoes: a step named in `redo` "runs again on all N pages, as
  asked (redo)", never "already done on 87 of 92". *Test:*
  `fichero-server/tests/unit/recipes/test_regions_one_pass_5689.py`. **What a step ran on counts (#5706):** a step whose output may leave no trace on a page (Find Names on a page
  naming no one, Prepare on a clear page) keeps on the run the pages it ran on and ended well (`ran_on`,
  `runner.RAN_ON_JOBS`), and the plan counts them done (`done.pages_a_run_did`), so a page is not "to do" after
  every run. A stage's account counts every page done when it read them all in one call and ended well (Names,
  Dates: never "0 of 92" after 1,193 names), and its offer says the stage's own verb ("Find names on the 3 pages
  that failed", `run_view.offer_words`). *Test:* `fichero-server/tests/unit/recipes/test_steps_count_what_they_did_5706.py`.
- `source.job.publish` — **[PARTIAL]** (#5390, #2535; *not built: no purpose turns `publish` on (`assemble.PURPOSE_STEPS` lists none, found live 2026-10-17), so a recipe has the step only when a person adds it (by hand, or as a layer through `POST /api/recipes/project/layers`) and names its `where` folder; which purpose should bring it, and where its folder comes from, is the maintainer's to say*; built: the `publish` card in `recipes/start.py` and `recipes/runner.py`; tested in `fichero-server/tests/unit/recipes/test_publish_to_spec.py`) a recipe's `publish` step writes the project as a static
  website (an 11ty project that builds with `npx @11ty/eleventy` and deploys to Netlify) through the one
  site export (`export_service.export_eleventy_site`), into the folder its `where` setting names on the
  engine's disk, as a card of a started recipe; publishing again rewrites that site in place. A step that
  names no folder is skipped and says so. No purpose turns publishing on; a project adds the `publish` layer later (`POST /api/recipes/project/layers`, `source.onboard.add-layer`), which puts the step last in the recipe, tested in `fichero-server/tests/unit/recipes/test_publish_purpose_turns_it_on.py`. What the site shows of the checks is `source.check.on-the-site`.
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
- `source.onboard.job-detail-screens` — **[PARTIAL]** (#5478) **Built 2026-10-05 (app), not yet seen, as ruled that day (every ticked job its own screen):** each ticked job adds one screen after What it is, in step order (`SetupPage.pages`), with its topic's paragraph and example; Entities asks its kinds (default people and places), Translate or normalise how far, Map places which gazetteer, saved as `answers.job_answers`; an unticked job adds none; pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Built 2026-10-07 (engine): the names step reads its kinds (`source.onboard.auto.job-answers-read`). Not built: the gazetteer and translate steps reading theirs; translate's target language, the gazetteer's region and period, catalogue fields, table columns.* a ticked job that needs an answer the
  engine cannot work out gets one short screen of its own after What it is, and only then: entity
  kinds (checkboxes; default people and places), translate or normalise (into which language, how
  far), gazetteer (which one, region and period), catalogue fields, table columns; an unticked job
  never shows its screen; image clean-up, reading order, dates and statements have no screen (their
  defaults live in the Inspector). *Test:* purposes [transcribe] show no detail screen; adding
  People, places and things shows the entity-kinds screen once.
- `source.onboard.what-runs-by-itself` — **[PARTIAL]** (#5478) **Built 2026-10-05 (app), not yet seen:** its own screen before Start (`RecipeAutomaticFields`): the choice, each recipe step with a checkbox pre-ticked from the purposes that run by themselves (training never), the sentences about Start and import; saved as `answers.automatic` (`runs`, `steps`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Built 2026-10-07 (engine, #5574): the import hand-off reads it (`source.onboard.auto.runs-by-itself-honoured`).* "What runs by itself" is its own screen
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
- `source.recipe.steps-name-layers` — **[OK]** (#4950) every step names a layer; the resolved
  recipe's `automatic` section lists the steps whose layer the purpose (or an added layer) turns
  on, with whether each may use the cloud, and is never written by hand. *Built 2026-10-18 (engine):* `assemble` sets each
  step's `layer` from its job and returns `automatic` (`id`, `layer`, `uses_cloud`, in step order; a step ticked by hand on top
  of the purpose is a step but not automatic) on `POST /api/recipes/assemble`; pinned by
  `fichero-server/tests/unit/recipes/test_steps_name_layers_4950.py`. `layer` and `automatic` are saved with the recipe as a snapshot of the assembly (checked 2026-10-18, review 136: nothing in the engine or the app compares a saved recipe with a fresh assembly, so the new keys read as no change; the app's own `answers.automatic` is a different thing, what runs by itself after Start). Not built: the app does not show the section yet.

Setup
- `source.onboard.widget-and-search` — **[PARTIAL]** (#4951, #5479) **Built 2026-10-05 (app), not yet seen:** What it is has a search field for languages and for scripts that autocompletes from the engine, and the chosen ones as blue tokens (name shown, tag on hover, × removes); Return on a typed word takes the engine's answer ("spanish" is the `es` token) and refuses a word it does not know in words (`CodeTokenField`, `RecipeSetupStore.addTyped`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. **Built 2026-10-05 (round 3, app):** the Browse… list is gone; matches show in the field's own dropdown (`textInputSuggestions` on the Mac, a List under the field on iPhone and iPad). **Built 2026-10-03:** the Your Material step searches languages and scripts through the engine (2026-10-04: `RecipeSetupStore.searchLanguages`/`searchScripts`; a dialect shows whose dialect it is, a Glottolog-only language is kept as a private-use tag). The engine searches ISO 639-3 joined with Glottolog 5.3 (CC BY 4.0, vendored; languages ISO lacks and about 13,000 dialects, each answer with its BCP 47 tag and glottocode kept apart) and every ISO 15924 script: `GET /api/recipes/languages`, `/scripts`, `fichero-server/tests/unit/api/test_setup_searches_languages_and_scripts.py` and `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. *Not built (ruled 2026-10-05, #5479): the field is free text; no browse menu; one value, not tokens.* setup is a form with search beside each
  field, not a conversation: languages and scripts each autocomplete from the engine's registries
  as the person types (ISO 639-3 with Glottolog; ISO 15924), in a dropdown under the field; no
  Browse… menu (ruled 2026-10-05, #5479); several can be chosen at once, each shown as a token with its name (its tag or code on
  hover) and removed with its ×. *Test:* typing "spanish" offers Spanish (es); choosing it and
  Latin shows two tokens. **Built 2026-10-11 (#5679 walk, #5680):** both searches rank an exact code or an exact
  name first, then names starting with the query, then names containing it: "Latin" gives Latn before Latf
  (Fraktur) and Latg (Gaelic); pinned in `fichero-server/tests/unit/api/test_setup_searches_languages_and_scripts.py`.
- `source.onboard.language-stored-as-tag` — **[OK]** (#5479) **Built 2026-10-05 (engine):** `PUT /api/recipes/project` and `POST /api/recipes/assemble` resolve each language to its tag (`recipes/names.resolve_language`: a tag or ISO 639 code stays a tag, a name resolves when exactly one language has it, a Glottolog-only one to `und-x-<glottocode>`) and each script to its code, and refuse anything else with 422 in words; a project already holding a word reads it as its tag where it resolves and keeps it otherwise. Saving "spanish" stores `es`, and the names step then takes the card that lists `es`; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-08 (#5595):** a name resolves without its dates ("Old Irish" is "Old Irish (to 900)", `sga`) and by names scholars use that ISO lacks (`names.ALSO_CALLED`: "Old Church Slavonic" `cu`, "Ge'ez" `gez`, "Classical Chinese" `lzh`); a script's name typed as a language says it is a script, and an unknown name offers the nearest languages; a card listing Syriac (`syr`) covers Classical Syriac (`syc`, `names.ALSO_COVERS`); pinned by `fichero-server/tests/unit/recipes/test_language_script_data_5595.py`. what setup saves for a language is
  its tag (`es`, `la`, a private-use tag for a Glottolog-only language) and for a script its ISO
  15924 code, never the typed word; the engine, given a word that is not a tag (a project saved
  before this, or a call from MCP or the command line), resolves it to the tag when exactly one
  language has that name and otherwise refuses in words ("Fichero doesn't know the language
  'spanish'. Choose it from the list."), never passing the word to the rules. *Test:* saving
  languages ["spanish"] stores ["es"], and the recipe proposes a reader whose card lists `es`.
- `source.onboard.direction-chosen` — **[PARTIAL]** (#5479) *Superseded in the app 2026-10-18 by the owner's ruling: setup no longer asks a direction. There is no picker; a script reads in the engine's derived direction (`RecipeSetupStore.direction(of:)`, `SetupThreeWaysInTests`), and a page that may be vertical is flagged ("check a page"). The engine still accepts and keeps `directions` for a project that has them.* **Built 2026-10-05 (engine):** the saved answers hold `directions` (script code to `ltr`, `rtl`, `ttb` or `ttb-lr`), each pre-filled from the script's derived direction and kept when changed (2026-10-08, #5595: a script whose historical material runs in columns pre-fills vertical, Mongolian `ttb-lr`, Han and Japanese `ttb`, as ruled 2026-09-28; Simplified Han and Korean stay `ltr`; `answers.VERTICAL_BY_DEFAULT`); any other value is refused in words; pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** What it is has one direction picker per chosen script, pre-filled from the engine's derived direction, saved and sent as `directions`. *Built 2026-10-18 (engine): the steps read it: the review says it (`review_profiles.facts`, `fichero-server/tests/unit/recipes/test_review_profiles_5723.py`), and Find Lines tells Kraken's segmenter the page's direction (`kraken_runtime.text_direction`, `vision_base.page_direction` through the one direction cascade: right to left `horizontal-rl`, columns `vertical-rl` or `vertical-lr`), so a right-to-left page's lines are ordered from the right and a page in columns is found in columns (`fichero-server/tests/unit/recipes/test_lines_found_in_the_projects_direction_5728.py`). Not built: a real run on a right-to-left and a vertical page.* direction is chosen in setup, pre-filled from
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
**Set Up, one page per stage (section 7c, ruled 2026-10-11, #5668).**

- `source.onboard.stages.left-list` — **[GAP]** (#5668) *Superseded in part by section 7d: the steps are
  `source.onboard.project.steps`, the stages' order `source.onboard.stages.pipeline-order`.* the setup window's left list reads, in recipe
  order: Your Project, Your Material, Choose the Stages, one page per chosen stage (Clean Up Images,
  Find Lines, Read, Translate, Organise, Names, Statements, Dates & Times, Passages, Structured Data,
  Search, each only when chosen), Train, Ready. Set Up… on an existing project starts at Your Material.
  *Test:* pure Swift, the step list for no stage, one stage and all eleven, in that order whatever order
  they were ticked in.
- `source.onboard.stages.choose-first` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStageChooser` over `GET /api/recipes/stages`; pinned by `SetupStagesTests`. Choose the Stages replaces What You Want
  to Do and is the first decision about the work: every stage is a checkbox, on or off, with its one
  sentence. *Test:* pure Swift over the engine's stages list.
- `source.onboard.stages.goals-are-shortcuts` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStageChoice.applyGoal`; pinned by `SetupStagesTests`. the goals (Transcribe, Search,
  Knowledge graph and the rest of `PURPOSES`) stay, as shortcuts above the stages: choosing one ticks
  the stages it needs (`PURPOSE_STEPS`); unticking a stage by hand is kept. *Test:* pure Swift, a
  goal ticks its stages and a stage unticked afterwards stays unticked.
- `source.onboard.stages.needs-are-ticked` — **[PARTIAL]** (#5668) Built 2026-10-11 (engine half): each stage's `needs` with its words, checked against the job registry; pinned by `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`. a stage another chosen stage needs is
  ticked with its reason in words ("Dates & Times needs Names") and cannot be unticked while it is
  needed, as the plan's own steps are today (`needed_by`). *Test:* engine, the stages list carries
  each stage's needs; pure Swift, the chooser locks a needed stage.
- `source.onboard.stages.stages-list-from-the-engine` — **[PARTIAL]** (#5668) Built 2026-10-11 (engine): `recipes/stages.py`, `GET /api/recipes/stages`; pinned by `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`. *Not built: the app (B).* the stages, their titles,
  sentences, examples, jobs, questions and needs come from one engine list (`GET /api/recipes/stages`),
  read by setup, the Inspector and the manual; the app works none of it out. *Test:* pytest, every
  registered job that a stage carries exists and every stage's needs are stages; the eleven in order.
- `source.onboard.stages.page-says-what-it-does` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStagePage` (the sentence as the page's subtitle, then its example). each stage page opens with what
  the stage does in one sentence, with an example, in the job registry's words (section 7a).
  *Test:* pure Swift, the page's first line is the engine's sentence for that stage.
- `source.onboard.stages.page-who-runs-it` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStagePage` shows the plan's rows for its own jobs (`RecipeStepsView(onlyJobs:)`) with the finder and, for Read and Find Lines, the comparison; the finder still searches readers only (`source.onboard.models.chooser-per-step`). each stage page shows who runs each of
  its jobs (the model, where it runs, its size and licence), with Choose a model… (the finder, for
  that job) and its candidates; Read and Find Lines add the comparison of candidates on the person's
  pages (the bake-off). *Test:* pure Swift, the page lists its own steps' rows and no other stage's.
- `source.onboard.stages.page-asks-its-questions` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStagePage` and `SetupStageQuestionField`, answers kept by key in `job_answers`; pinned by `SetupStagesTests`. each stage page asks its own
  questions with defaults filled in (Names: which kinds of names, which gazetteer; Dates & Times:
  which calendars; Statements: which kinds; Organise: one document per folder or several), saved with
  the answers; a question belongs to one stage and is asked once. *Test:* pure Swift, each question's
  stage; pytest, the answers round-trip.
- `source.onboard.stages.shows-what-it-does` — **[PARTIAL]** (#5668) each stage page opens with a picture of
  its work (section 7d, the table there), about 360 by 220 points, played once as the page appears and
  again on Replay, 3 to 5 seconds; with Reduce Motion it shows its last frame still. It plays on the
  person's own sample page when the stage was tried (the sample's picture and what the try made), else on
  the example page shipped with the app (Diálogo de la Lengua, p. 18: regions, lines, reading, names and
  dates worked out once and kept with its licence and credit). Drawn in SwiftUI alone (no Metal shader, so no build needs the Metal toolchain); a light
  sweeping the page, for Prepare Images and Read. *Test:* pure Swift, the try's page is chosen over the
  example; every stage has a picture; Reduce Motion gives the last frame; the example's data decodes and
  every box lies on its image. **Built 2026-10-11 (app), not yet seen:** `StageShowcaseSection` at the top of
  `SetupStagePage`; `StageShowcaseView` plays it (a TimelineView, Replay, Reduce Motion's last frame); the thirteen
  pictures in `StagePictures+Page.swift` and `StagePictures+Knowledge.swift` over `StagePageLayer`; the light's sweep a SwiftUI gradient band (`scanSweep`);
  the example in `Resources/StageShowcase` with its credit shown under it (`ShowcaseCredit`). Pinned by
  `fichero/Tests/Unit/general/Models/StageShowcaseTests.swift` and
  `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift`.
- `source.onboard.stages.compares-candidates` — **[PARTIAL]** (#5668, #5806; engine built: a stage try runs on its own lane, so a Find Lines compare never queues behind the Read try waiting on a reader download; a try waiting on a download says what for with its progress; a stage's try is refused only for its own steps, not another step's problem (`fichero-server/tests/unit/recipes/test_stage_try_does_not_wait_or_hide_5806.py`). the stage result follows its job (a finished comparison or a lost job stops the spinner, a failed one says why) and exists before the job is queued (`test_stage_try_result_follows_its_job_5806.py`); the app shows the engine's 422 sentence, a failed try's reason, a missing result as not tried yet, and why Compare is off with no sample pages (`SetupStagesTests.swift`). Not built: confirmed on the owner's screen) a stage page shows the same sample page
  done by 2 or 3 of the step's candidates side by side, each column playing the stage's picture on its own
  result with its measures under it (agreement or character error rate, time, cost: "free, on this Mac" or
  the cloud price) and Use This (the use-candidate route); Compare on These Pages runs them, the step's top
  2 or 3 by default, the person free to change which; one candidate is one column. The engine's answer is
  the try's, with `candidates: [...]`, each the bake-off row's fields (`card`, `name`, `runs_on`, `local`,
  `cer` or `agreement`, `seconds`, `cost_usd`, `why`) and its own `per_page` and `names`. *Test:* pure Swift,
  one column per candidate, its measures in words, Use This sends its card for the step. **Built 2026-10-11 (app),
  against that shape:** `StageCandidate` (read from the try's `candidates`), `StageComparisonView`, Use This through
  `RecipeSetupStore.useCard(_:named:forStep:)`; the button reads Compare on These Pages. Pinned by
  `StageShowcasePicturesTests`. **The engine (worker A, 2026-10-11):** `POST /api/recipes/stages/{stage}/try`
  takes `candidates` (card ids); without them the stage's main step (the recipe's first step of the stage's jobs
  that names a model) is compared with its own model first and the per-step finder's next one or two runnable on
  this Mac (`source.find.candidates-fit-the-step`), up to three. Each candidate runs the stage's own steps, with
  that step's model swapped for it, on its own copy of the sample pages (one scratch project each, removed
  after), through the Start plan's cards and the recipe runner (one code path); its column is the bake-off row's
  fields (`card`, `name`, `runs_on`, `local`, `cost_usd` as `{value, basis}`, `seconds`, `why` when it could not
  run, `cer`, `agreement`) with its own `per_page` and `names`, and `measures` saying how it was compared:
  for Read, Normalise and Translate the text's agreement with the other candidates (1 less their character
  distance) and its character error rate on lines a person corrected on these pages; for Find Regions and Find
  Lines the overlap of its shapes with the others' (mean best IoU); for Names, Statements and Dates the count of
  what it found and the items no other candidate found (`only_this_found`). The try's own result fields stay the
  step's own candidate's, so a try with one candidate reads as before. A cloud candidate is said with its cost
  and the try refused (402) without `cost_ok`; a candidate Start could not run is a column that says why. Read
  and Find Lines keep the bake-off (its evaluation job over the corrected lines) when no candidates are named and
  the samples hold its ground truth; otherwise they are compared the same way. *Test:*
  `fichero-server/tests/unit/recipes/test_stage_compares_candidates_5668.py`. **From the overnight walk
  (#5687):** a candidate whose model is not on this Mac is fetched before it runs, as Start fetches it (a
  `download-model` job in Activity), and its run waits for it; one that cannot be fetched says why, in words.
  Every `why` is a sentence, never an exception's class name. Find Regions' and Find Lines' measures carry
  what was found (`found`, and `kinds`: each label and how many) with one candidate as with three. A stage
  that needs Read (Names, Statements, Organise …), tried on pages that have no reading yet, is refused (422):
  "These pages have no reading yet: Names needs Read." *Test:*
  `fichero-server/tests/unit/recipes/test_stage_try_words_5687.py`. **Built 2026-10-11 (app, the choice
  and the measures):** the stage page lists its main step's candidates from the per-step finder
  (`StageCandidateChooser`, up to three ticked, `StageCandidateChoice`); Compare on These Pages sends them as
  `candidates`, none when none are ticked; each column says how it compared by kind ("4.1% character errors" or
  "80% agreement" for text, "80% overlap" for shapes, "found 12, 3 only here" for items,
  `StageCandidate.quality`). Pinned by `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift`. **Names finds what is here (#5688):** every spaCy
  pipeline installed on this Mac for the project's language is a card for Find names (beside the shipped small
  one, and the text models already here), so a Names try compares them by default; one not installed is not a
  candidate. *Test:* `fichero-server/tests/unit/recipes/test_set_up_follows_the_project_5688.py`.
- `source.onboard.stages.samples-proposed` — **[PARTIAL]** (#5668) **App built 2026-10-11, not yet seen:** `SetupStageSamples` and `SetupStageTryStore` (the samples with why, Try on These Pages, the cost asked first, the result per page and the names); pinned by `SetupStagesTests`. Built 2026-10-11 (engine): `recipes/samples.py`, `GET`/`PUT /api/recipes/samples` (the choice kept beside the setup); pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. Fichero proposes 3 to 5 sample pages,
  spread across the material (first, last, evenly spaced, the largest and smallest images), shown on
  every stage page; the person can pick others in the window, and the choice holds for every stage. **Order
  (#5686):** "first" and "last" are as Items shows the pages, each folder in its own order (its sort order,
  then the name read naturally: `2_Hoja` before `10_Hoja`), never the order an import happened to make them.
  **One order everywhere (#5693):** Items, Find the Documents, the samples, the Inspector's pages, a training
  set and a remote read all sort a folder's children by one shared key (`core.naturalsort.in_folder_order`:
  the order a person set, then a page's place in its file, then the name read naturally), so no surface shows
  a folder's pages in another order. Nothing is stored at import: `sequence` on an image means its page
  within a multi-page file, and a stored number would put pages added later at the end. *Test:*
  `fichero-server/tests/unit/recipes/test_one_page_order_5693.py`.
  *Test:* pytest, the proposal on a folder of 1, 4 and 200 pages; pure Swift, a page picked by hand
  replaces a proposed one.
- `source.onboard.stages.sample-result` — **[PARTIAL]** (#5668) **App built 2026-10-11, not yet seen:** `SetupStageSamples` and `SetupStageTryStore` (the samples with why, Try on These Pages, the cost asked first, the result per page and the names); pinned by `SetupStagesTests`. Built 2026-10-11 (engine half): a try whose steps use the cloud is refused (402) with its cost until `cost_ok`; pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. *Not built: the result drawn in place (B).* Try on These Pages runs the stage on the
  samples and shows its result in place: lines drawn on the page, the text read, names marked, dates
  normalised, the table filled. It runs locally and free where it can; a stage that would use the
  cloud says its cost and time first and runs only on that press. *Test:* click-around per stage;
  pytest, a cloud stage's try refuses without the press's yes.
- `source.onboard.stages.read-compares-readers` — **[GAP]** (#5668, #5665) the Read stage's result
  is the readers compared on the samples, line by line, with the disagreement heat map (#5665).
  *Test:* pure Swift over a recorded comparison.
- `source.onboard.stages.sample-run-reuses` — **[PARTIAL]** (#5668) Built 2026-10-11 (engine): `POST`/`GET /api/recipes/stages/{stage}/try`; Read and Find Lines start the bake-off on the samples, the others run their own steps' Start cards through the recipe runner's `_run_workflow` on a copy of the samples (`transfer` copy into a scratch project beside the setup, removed after), one `try-a-stage` job on the recipes lane; pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py` (the bake-off seam is faked; Names' run is faked at `_run_workflow`). the engine's one sample run (try this
  stage on these pages) reuses the bake-off and its evaluation job for Read and Find Lines, and runs
  the stage's workflow on the samples for the others; one route, `POST /api/recipes/stages/{stage}/try`,
  with its result read back by `GET`. *Test:* pytest, Read's try writes one evaluation job; Names'
  try runs its workflow on the samples only.
- `source.onboard.stages.organise-tried-on-a-run` — **[PARTIAL]** (#5668, B's Organise review) *Built (engine): `samples.propose_run`, `GET /api/recipes/samples?stage=organise`, the try running `finddocs.find_documents` and the entries splitter on the copy (`samples._organise`); pinned by `fichero-server/tests/unit/recipes/test_organise_try_5668.py`. Not built: the documents and entries drawn in the window (B).* Organise can
  be tried on sample pages. Finding where one document ends and the next begins needs neighbouring pages
  of one folder, which 3 to 5 pages spread across the material are not. So for Organise, Fichero proposes
  one run of consecutive pages instead: up to 12 in the folder's own order, from the folder with the
  most pages, starting at its first page, each saying why (`GET /api/recipes/samples?stage=organise`).
  The run is Organise's alone; every other stage, Find Regions included, gets the spread samples (#5686). The
  folder's own order is Items' (natural), the order Find the Documents reads a folder in too, so the run is
  `1_` to `12_`, never `10_`, `11_` … `1_`.
  The person may try it on pages of their own choosing instead (`page_ids`). The try copies the run into
  a scratch project, as every try does, and runs Find the Documents there with nothing accepted by
  itself (`accept_above` none), and Split into entries with the step's model where the recipe has it.
  The result, `recipe/samples/organise.json`, holds the documents proposed (`documents`: each with its
  page ids, name, kind, confidence and reasons, in the project's own page ids) and the entries split from
  pages with text (`entries`: each with its page id, name and opening words). *Test:* pytest, the run
  proposed for a folder of 30 pages and of 5; a try writes the documents proposed in the project's ids
  and changes nothing in the project.
- `source.onboard.stages.samples-are-not-the-work` — **[PARTIAL]** (#5668) Built 2026-10-11 (engine): what the copy's run made is kept as `recipe/samples/<stage>.json` (per page: readings, segments by kind, statements; the names), the project's passes, readings and names unchanged, and a stage no longer chosen loses it; pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. a sample result is kept as the
  stage's, beside `recipe/setup.yaml` (with the samples and the models used), replaced when the stage is
  tried again and cleared when it is unticked; it is
  never written as the project's passes, readings, names, dates or statements, and Start does not
  count it as done. *Test:* pytest, after a try the project's passes, readings and claims are
  unchanged and Start's plan runs on every page.
- `source.onboard.material.when-written` — **[PARTIAL]** (#5668) **App built 2026-10-11, not yet seen:** `RecipeWhenWhereHandFields`, saved as `answers.period` and `answers.hands`; pinned by `SetupStagesTests`. Built 2026-10-11 (engine): `answers.period`, kept as typed, read by `recipes/hands.period_years`; pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. *Not built: the suggestion from the sample pages.* Your Material asks when the material was
  written, as a century or a range of years ("16th century", "1650–1700"), proposed from the sample
  pages where a local model can look and labelled "suggested from your pages"; saved with the answers.
  *Test:* pure Swift, a century and a range round-trip; pytest, the answers carry it.
- `source.onboard.material.which-hand` — **[PARTIAL]** (#5668) **App built 2026-10-11, not yet seen:** `RecipeWhenWhereHandFields`, saved as `answers.period` and `answers.hands`; pinned by `SetupStagesTests`. Built 2026-10-11 (engine): `recipes/hands.py` and `GET /api/recipes/hands` (Latin, Arabic and Hebrew hands, each with its centuries, its tags and what it looks like), `answers.hands` kept as typed; pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. *Not built: the pictures (each hand says what it looks like in words until then).* Your Material asks which hand, from a
  curated list of hands per script and century kept by the engine (Latin: Caroline minuscule, Gothic
  textualis, Gothic cursiva, Secretary, Humanistic, Italic, Kurrent, Copperplate…), each shown with a
  picture example and mapped to the Hugging Face tags readers carry; anything else is typed and kept as
  typed, and "Not sure" is an answer. *Test:* pytest, the hands offered for Latin script in the 15th
  century and in the 18th, each with its picture and tags; pure Swift, a listed hand and a typed one
  round-trip as tokens. **From the overnight walk (#5688):** the hands
  offered follow the project as saved: with no period or language asked, `GET /api/recipes/hands` reads the open
  project's period and languages; a hand written in particular languages (Kurrent in German; Procesal and the
  Spanish humanistic cursive in Spanish; Secretary in English) is offered only to a project in one of them, the
  others to any. A hand typed is kept as typed, so a curated id cannot be told from a typed word and is not
  refused. *Test:* `fichero-server/tests/unit/recipes/test_set_up_follows_the_project_5688.py`.
- `source.onboard.material.feeds-the-reader-search` — **[PARTIAL]** (#5668) Built 2026-10-11 (engine): the hand's tags join the Hugging Face tag search (`discovery.search_hugging_face(hand_tags)`, from the open project's answers in the search job); pinned by `fichero-server/tests/unit/recipes/test_setup_samples_5668.py`. *Not built: the period in the search.* the period and the hand feed the
  search for readers (the Hugging Face tags people use, such as `htr`, `catmus`, `kurrent`, with the
  language tags) and the comparison of readers. *Test:* pytest, the finder's query for a Kurrent hand
  carries `kurrent`.
- `source.onboard.stages.train-and-ready-last` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStep.projectSteps`; Train left Ready's rows. Train (the offers of
  `source.recipe.train-offered-per-step`) is its own page after the stages, and Ready is last: the plan
  as one list, what runs by itself, what Start will fetch, Keep an export, and Start. *Test:* pure
  Swift, the last two steps are Train and Ready.

**The two set-ups (section 7d, ruled 2026-10-11 afternoon, #5668).**
- `source.onboard.app.steps` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStep.appSteps`, `FirstRunWindow.flow(for:)`; pinned by `FirstRunStepSelectionTests`. setting up the app (a first launch, and Fichero › Set
  Up Fichero…) is Welcome → What Fichero runs → the hand-off, and no Permissions step: folder access is
  asked when a folder is added. *Test:* pure Swift, the app's steps are exactly those three.
- `source.onboard.app.what-fichero-runs` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `WhatFicheroRunsFields` (one sentence on what comes with Fichero, and the two accounts added as providers); pinned by `SetupStagesTests`. The step is titled "Where the work runs". It says in one line what Fichero comes with: "Fichero comes with readers for handwriting and print, a line finder and a name finder; it downloads others for your language when you need them." (no table of engine names), and
  takes a Hugging Face and an OpenRouter account in the step; the OpenRouter row says pages leave the Mac. *Test:* pure Swift, the step's line and its
  two account fields.
- `source.onboard.app.provider-sheet-in-step` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** the sheet is the window's own (`FirstRunWindow.showsProviderSheet`), no longer deferred to finish. Choose a Provider opens its sheet
  while the step shows; it opened only after onboarding ended. *Test:* pure Swift, the sheet's presented
  state is set by the press, in the step.
- `source.onboard.app.one-continue` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** the footer's Continue only; the welcome's two choices hide it. each step has one Continue, the footer's; a
  step's body carries none. *Test:* pure Swift, no step body offers Continue.
- `source.onboard.project.one-view` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `FirstRunWindow.flow(for:)` for each way in; pinned by `FirstRunStepSelectionTests`. Set Up a Project is one view, reached from the
  welcome's Set Up a New Project…, File › Set Up New Project… and Project › Set Up…. *Test:* pure Swift,
  each way in opens the same steps.
- `source.onboard.project.steps` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStep.projectSteps`, the stage pages from the chosen stages; pinned by `FirstRunStepSelectionTests`, `SetupStagesTests`. Set Up a Project runs Your project → Add material →
  About the material → the stages → one page per chosen stage → Train → Ready, one small page each, any
  of them skippable; Project › Set Up… starts at Add material. *Test:* pure Swift, the step list for no
  stage and for every stage.
- `source.onboard.project.add-material` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** its own page, Add Files or Folders…, the line about adding later gone. The chooser takes files and folders (`RecipeMaterialSourceFields`, `allowedContentTypes: [.folder, .item]`; `importFiles`/`importFolder`, `SetUpAddsMaterialToTheProjectTests`). Add material offers Add Files or Folders…
  and then how it comes in (Copy, the default; Leave in place, Move; Index and Keep arranged are set on a synced folder, `source.onboard.five-ways-in`), separate from what the
  material is. *Test:* pure Swift, the ways in and the default (`SetupThreeWaysInTests`).
- `source.onboard.project.about-material` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** when written, where written (`answers.place`) and which hand (`RecipeWhenWhereHandFields`); pinned by `SetupStagesTests`. Pages counted from what was added (`RecipeSetupStore.countPages`, the Start plan's count). *Not built: the kinds beyond handwriting, print and typescript, which the engine's `MATERIALS` refuses today.* About the material holds the pages
  counted from what was added, languages, scripts, kinds (handwriting, print, typescript, tables and
  forms, maps and drawings), when written, where written, and which hand. *Test:* pure Swift, the
  page's fields in that order.
- `source.onboard.project.language-as-you-type` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** the matches listed under the field as the person types, on every platform (`CodeTokenField`); an unknown word said on its own row (`RecipeSetupStore.typedRefusal`), pinned by `SetupRoundTwoTests`. the language field offers
  matches as the person types, by the language's own name with or without accents; a language it does
  not know is said on the language row only, never repeated on the scripts row. *Test:* pure Swift, a
  typed "espanol" lists Spanish; an unknown language's message appears once.
- `source.onboard.stages.pipeline-order` — **[GAP]** (#5668) the stages are, in pipeline order: Prepare
  Images, Find Regions, Find Lines, Read, Normalise, Translate, Organise, Names, Statements, Dates &
  Times, Passages, Structured Data, Search, from the engine's list. *Test:* pytest, the thirteen in that
  order; pure Swift, the chooser shows the engine's order.
- `source.onboard.stages.explanation-always-shown` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `SetupStageRow`. every stage in the chooser shows
  its explanation whether or not it is ticked. *Test:* pure Swift, an unticked stage's row carries its
  sentence.
- `source.onboard.stages.normalise-and-translate` — **[PARTIAL]** (built in part, pinned by `fichero/Tests/Unit/general/Models/SetupStagesTests.swift`; what is still unbuilt is not yet written down here, R0 2026-10-17; #5668) Normalise and Translate are two
  stages: Normalise offers as written, abbreviations expanded, normalised spelling and modernised;
  Translate's target is any language, found by the language search. *Test:* pytest, the two stages and
  their questions; pure Swift, Translate's target field is the language search.
- `source.onboard.stages.page-trains` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** the stage page shows the engine's train offers for its own jobs (`RecipeTrainOffersFields(onlyJobs:)`, `RecipeSetupStore.trainOffers(forJobs:)`); pinned by `SetupStagesTests`. each stage page offers training or fine-tuning
  for its step (Kraken, spaCy, Core ML, MLX LoRA) where the step can be trained. *Test:* pure Swift, a
  trainable stage's page offers it and another's does not.
- `source.onboard.ready.words-not-engine-errors` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `RecipeStartFields.words(for:title:)` names the step by its title and says a model the engine cannot run as what to do; pinned by `SetupStagesTests`. The engine's own words are the fuller fix. Ready says the plan in words and
  never shows a raw engine message (a model "not pinned in a known form" is said in words with what to
  do). *Test:* pure Swift, a refusal's engine text is not on the page.
- `source.onboard.ready.will-not-run-when-chosen` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** `RecipeSetupStore.skippedStepsOfChosenStages`; and an unchosen stage's jobs are taken out of the answers. a step that will not run is
  listed on Ready only when its stage was chosen. *Test:* pure Swift, an unchosen stage's refusal is not
  listed.
- `source.onboard.models.chooser-per-step` — **[PARTIAL]** (#5668; the engine is pinned by `test_model_chooser_per_step_5668.py`; the Swift search label naming the step is unseen) a step's model candidates and online
  search are that step's own: Find statements never lists page readers or says it searched for readers.
  *Test:* engine, the candidates for `find-statements` carry that job; pure Swift, the search label
  names the step.
- `source.onboard.normalise-runs-named-by-the-engine` — **[PARTIAL]** (#5795, review 99) the Normalise step's runs are named by the engine, one title for each reading level asked and one for a translation, in the order Start makes them, so the Set Up row reads them and never works them out. *Built (engine): `POST /api/recipes/assemble`'s Normalise step carries `run_titles` (`answers.normalise_run_titles`, pinned to the runs `plan_start` makes by `fichero-server/tests/unit/recipes/test_normalise_run_titles_5795.py`). Not built: the row reading them in place of `RecipeSetupAnswers.runTitles` (Swift, m-ios).*
- `source.recipe.into-what-is-a-multi-select` — **[PARTIAL]** (#5789, split from #5660 item 1) **Built 2026-10-18 (app), not yet seen:** the page offers the levels as checkboxes with a translation picker (`JobQuestionFields`, `RecipeSetupStoreTests.intoWhatIsAMultiSelect`) and the step's row names one run per ticked level ("2 runs: As written · Modernised", `IntoWhatRunsTests`). Set Up shows "Into what" as a multi-select of reading levels (as written, abbreviations expanded, normalised spelling, translations); each ticked level turns on its step and the plan names one run per level. The engine takes the list (`test_set_up_steps_5660.py`); the page does not yet offer it.
- `source.onboard.every-setup-button-acts-or-says-why` — **[PARTIAL]** (#5790, split from #5660 item 2) **Built 2026-10-18 (engine):** a `licence-not-accepted` problem carries `licence` {card, name, words} for the button to open, and `assemble.FIX_ACTIONS` names the route each fix calls or why it cannot, one or the other; pinned by `test_setup_buttons_act_or_say_why_5790.py`. **Built (app, unbuilt):** every fix code the engine names routes to an action (`RecipeStepsView.fixRoute`: the finder, the licence sheet, or setup's handler; `SetUpButtonsActTests`, `ModelsUXTests`), and Start is disabled with its reason (`RecipeSetupStore.startDisabledReason`, `SetUpAddsMaterialToTheProjectTests`). "Review the licence…" opens the licence to accept; every button in Set Up either acts or is disabled with its reason, and a test fails on a button with no effect.
- `source.onboard.setup-says-what-is-happening` — **[PARTIAL]** (#5791, split from #5660 items 3, 5, 6; Built (app, unbuilt): the Find a Reader sheet words each card's place ("Ships with Fichero", "Download (2.3 GB)", `ModelFinderView.facts`, `ModelFinderStoreTests`); Ready says a step waits for a download that is running and Start stays pressable (`RecipeSetupStore.waitingForDownloads`, `RecipeSetupStoreTests`); *engine built 2026-10-18: each Start-plan run carries `how`, a sentence on how its step works (Work out dates: rules, not a model, its calendars and tables, on this Mac), and each download carries `sentence` ("Downloading X: 1.2 GB of 5.6 GB; its steps wait for it", or "X is not on this Mac yet (60 MB): Start downloads it"), so the app shows the engine's words; `start.how_it_works` (the job topic's "How it works:" text in `recipes/seed/topics.yaml`, written once), `start.download_sentence`, pinned by `fichero-server/tests/unit/recipes/test_setup_says_what_is_happening_5791.py`; the candidate's `availability` (ships, here, download) is #5660 item 3, `test_reader_finder_5660.py`. The Find a Reader sheet's engine half (#5791 item 3): a candidate whose download is under way carries `download.downloading`, `download.job_id` (its Activity job) and `download.progress`, and its `availability_words` say "Downloading" (`GET /api/recipes/candidates` with a project open; same test file). Search Online finds the palaeography readers (#5791, the Hub stubbed: the HTR words and the project's language are searched by name beside the tag listings; `fichero-server/tests/unit/recipes/test_reader_finder_5660.py`). Not built: the Swift sheet reading these fields*) the Find a Reader sheet says briefly what is happening and which cards ship with Fichero and which download; the Work out dates card says what it uses and which engine; while a model downloads its warning says downloading and Start is pressable, each step waiting for its model.
- `source.onboard.models.licence-accepted-once` — **[PARTIAL]** (#5668) **Built 2026-10-11 (app), not yet seen:** one tick accepts the licence, then Accept and Use works (`LicenceReviewSheet.canAccept`), and the sheet no longer inherits a disabled presenter; pinned by `SetUpButtonsActTests`. *Not built: an open-licence default for Find Regions (engine).* Find Regions has a default under an
  open licence, and a model under a licence that needs accepting is accepted once, after which Accept and
  Use for This Step works. *Test:* pure Swift, accepting enables the button.
 **Copyleft is open (#5687):** a licence that needs accepting is said by name and what it
  is: AGPL-3.0 and the other copyleft licences are open and copyleft ("its licence, AGPL-3.0, is copyleft: accept
  it to use it"), never "not open"; another unlisted licence says it needs accepting.
- `source.onboard.sheet-fits-its-window` — **[PARTIAL]** (#5624) **Built 2026-10-09 (app), not yet seen:**
  rows of checkboxes and tokens wrap (`FlowLayout`: the kinds of names, the kinds of material, the language and
  script tokens), the step column takes `minWidth: 0` and the page body never widens the button row; pinned by
  `fichero/Tests/Unit/general/Views/Onboarding/SetupSheetFitsTests.swift`. the Set Up sheet always fits its
  window: whatever a step shows wraps to the step's column, and the step list and the Back and Continue (or
  Start) row are always whole. *Test:* the kinds of names and eight language tokens fit a column narrower than
  their one-line width.
- `source.onboard.purposes-grouped` — **[PARTIAL]** (#5625) **Built 2026-10-09 (engine + app), not yet seen:**
  `GET /api/recipes/purposes` lists Transcribe, Search, Translate or normalise, Knowledge graph, Entities,
  Statements, then the rest, each with `parent` (`PURPOSE_PARENT`); What you want to do indents an option under
  its parent and shows one the ticked parent holds as ticked and fixed, "Included in Knowledge graph"
  (`RecipeSetupStore.includingPurpose(of:)`); pinned by
  `fichero-server/tests/unit/api/test_setup_rulings_2026_10_09.py` and
  `fichero/Tests/Unit/general/Models/SetupRulingsOctNineTests.swift`. *Open question:* the ruling also names
  Search as an option of the Knowledge graph; one purpose is listed once, so Search sits under Transcribe and the
  graph's sentence says it is searchable. the goals are listed in the order ruled 2026-10-09: **Transcribe**,
  with **Search** under it; **Translate or normalise** after it; **Knowledge graph**, with **Entities** and
  **Statements** as its options below it; then the rest. An option is still a goal of its own (Entities without
  the graph); ticking a goal that holds an option's jobs includes it. Each asks only what it needs. *Test:* the
  engine's list is in that order with those parents; the ticked graph includes Entities; Entities alone
  assembles transcription and names only.
- `source.onboard.script-from-language` — **[PARTIAL]** (#5626) **Built 2026-10-09 (engine + app), not yet
  seen:** every match of `GET /api/recipes/languages` carries `script` and `script_name`, the language's usual
  script from Unicode CLDR 48 likely subtags (`recipes/seed/language-scripts.txt`, Unicode License v3;
  `names.usual_script`); choosing a language in setup adds that script as a token unless it is there, and says
  so under the scripts; taking the language out takes out a script only it proposed
  (`RecipeSetupStore.proposedScripts`); pinned by `test_setup_rulings_2026_10_09.py` and
  `SetupRulingsOctNineTests.swift`. a language chosen proposes the script it is usually written in (ISO 15924:
  English → Latin, Russian → Cyrillic, Classical Syriac → Syriac), instead of asking; the person removes it or
  adds another like any token; a language with no usual script on record proposes nothing (never a guess); a
  script the person chose is never taken out with a language. *Test:* English gives `Latn`, Russian `Cyrl`,
  `syc` `Syrc`, `grc` `Grek`; an unknown languoid gives none.
- `source.onboard.plan-editable` — **[PARTIAL]** (#5627) **Built 2026-10-09 (engine + app), not yet seen:**
  `answers.removed_jobs` (and `POST /api/recipes/assemble`'s `removed_jobs`) leaves those steps out of the
  assembled plan; a step a step left in needs stays and carries `needed_by` (`assemble.needed_by`, the recipe
  check's own input rule); the recipe lists what was taken out under `removed`. Ready shows Remove from Plan
  under each step nothing needs (else "Read each line needs it, so it stays."), and Taken out of the plan with
  Put Back (`RecipePlanEditing.swift`); ticking a goal asks for its taken-out steps again; pinned by
  `test_setup_rulings_2026_10_09.py` and `SetupRulingsOctNineTests.swift`. *Not built:* reordering steps where
  the order is free; changing a step's model from this row is the model finder's (Find a Reader…,
  `RecipeSetupStore.useCandidate(_:forStep:)`). the plan on Ready can be edited: a step can be taken out and put
  back, the edit is saved with the project's setup (so Set Up… reopens with it), and Start runs the plan as
  shown; a step that a later step needs cannot be taken out, and Ready says which step needs it. *Test:*
  transcribe + search with `make-a-vector` taken out assembles transcription only and lists it as removed;
  taking out Find lines keeps it with `needed_by` Read each line; Start's plan has no vector step.
- `source.onboard.teaches-the-method` — **[PARTIAL]** (built in part, pinned by `fichero-server/tests/unit/recipes/test_topic_registry.py` and `fichero/Tests/Unit/general/Models/TopicStoreTests.swift`; what is still unbuilt is not yet written down here, R0 2026-10-17; #4951, #5471, #5481) **Engine built 2026-10-04:** each
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
- `source.onboard.first-launch-offers-setup` — **[PARTIAL]** (#5655) **Built 2026-10-10 (app), not yet seen,
  as ruled after the maintainer's cold-launch test that day:** a first launch (first run not done, and
  every project the app knows of is the always-there one, which has no name: none open, saved or
  recent) opens setup by itself. It starts with a welcome ("Welcome to Fichero", what Fichero does,
  and that the first step is setting up a project), then **Set Up a New Project…** as the main action
  and **Start Without a Project** as the other (replacing "Use My Project for Now", ruled final
  2026-10-10); either way the window opens with **Sources**, in the sidebar's top section, selected
  (`sidebar.project.opens-on-sources`, `sidebar.top-section-is-the-always-there-project`). The decision is made once
  when the window arms its sheets, so the project setup makes does not close setup. Later launches do
  not show it. Pinned by `fichero/Tests/Unit/general/App/ProjectNamingTests.swift`
  (`firstLaunchOffersSetUp`, `FirstLaunchChoices`). *Not pinned: the sheet presenting in the real
  window.*
- `source.onboard.reachable` — **[PARTIAL]** (#5421) **Built 2026-10-04:** File › Set Up Project…
  (the key window's project) and Set Up… on an empty project's main view (`projectOffersSetUp`)
  both call `LibraryManager.requestSetUp(for:)`, the one request the window presents as
  `FirstRunWindow(setUp: true)`; `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`.
  Not pinned: the menu item and button wiring (view code). 2026-10-05: the document Inspector's
  Set Up… asks through `requestSetUp(for:)` too (its own sheet is gone). setup is reachable without hunting: **File › Set Up
  Project…** for the selected project, and a **Set Up…** button on an empty project's main view, both
  opening the same flow as Inspector › Info › Recipe › Set Up…. *Test:* the menu command and the empty
  state's button each present setup for the selected project.
- `source.onboard.where-it-lives` — **[PARTIAL]** (#5482) **Built 2026-10-05 (app), not yet seen, as ruled that day:** the name (default **Untitled Project**, the Finder/Pages convention, ruled 2026-10-10 with the always-there project losing its name, #5655) and two places, **Inside Fichero** (the default: `Projects/` beside the app's Local project in its data folder) or **Choose a location…** (a folder picker; a synced folder is warned about); Continue makes `<folder>/<name>.fichero` through `LibraryManager.createProject(at:)` and has the engine open it (`POST /api/library`), and a folder that cannot be written is refused on the screen ("Fichero can't write to that folder. Choose another."), nothing made (`NewProjectStore`); pinned by `fichero/Tests/Unit/general/Models/LibraryManagerCreateProjectTests.swift`. *Superseded by that ruling: the save panel and the `~/Fichero/<project name>` proposal below.* first-run setup's first screen asks where the
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
- `source.onboard.start-works-in-first-run` — **[PARTIAL]** (#5477) **Built 2026-10-05 (app), not yet seen:** first run's Start plans and starts through the project made on Where it lives (its store), as Set Up… does. *Engine half pinned (2026-10-18): the saved setup's plan has no refusals and Start records the first yes, with no setup refused in words (`fichero-server/tests/unit/recipes/test_first_run_start_5477.py`). Not pinned: the app's first run against the real engine.* the Start screen in first run plans
  and starts exactly as Set Up… from a project does (`GET`/`POST /api/recipes/project/start` on the
  project made on screen 1); Start enables once the plan has no refusals. *Test:* first run to Start
  on a fixture folder enables Start and records the first yes in the new project.
- `source.onboard.five-ways-in` — **[OK]** (#5788; built 2026-10-18 (app, unbuilt): `ProjectIntakeChoice`, `SetupWayIn.setupChoices`) *Superseded 2026-10-18 by the owner's ruling: setup offers three ways in, not five.* **Copy** (default; Fichero makes its own copy in the project, the originals are never touched), **Leave in place** (the engine's Link mode; Fichero reads the files where they are and never changes them) and **Move** (the files move into the project; the originals are removed, said plainly). **Index** and **Keep arranged** are not asked in setup: they are set on a synced folder in the Inspector (`source.onboard.index-ties-the-folder`, `source.onboard.keep-arranged`). The choice is saved with the project (`answers.ingest_mode`: `copy`, `link`, `move`) and used by Add a Folder… and later imports; a project saved earlier as `index` or `keep-arranged` still reads back (its folder keeps its mode in the Inspector) and setup shows it as Leave in place. With Copy, the line after an add says what the copy takes and the room left (`CopySpaceTests`). *Test:* `SetupWayIn.setupChoices` is Copy, Leave in place, Move in that order and Copy is the default (`SetupThreeWaysInTests`).
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
- `source.onboard.kept-exported.markdown-keeps-lines` — **[OK]** (#5502) a kept Markdown export keeps each
  line of a page as a line: a reader of the file (CommonMark, pandoc) shows the page's lines one under
  another, not run together as one paragraph. Built (2026-10-17): `export_service.render_markdown_text`
  ends every line but the last of a page with two spaces (CommonMark's hard break, invisible in the
  file). Tested in `fichero-server/tests/unit/jobs/test_kept_markdown_lines_5502.py`.
- `source.onboard.kept-exported.loose-pages-are-documents` — **[GAP]** (#5502) the operator's run wrote
  one `Sources.md` for a project whose pages sit loose under one folder, and expected one file per
  document. By the rule above a page's document is the node it sits in, and a folder of loose pages is
  one document; whether each loose page (a file of its own) should be its own document is the
  maintainer's to rule (recorded on the issue). Not built.
- `source.onboard.set-up-later` — **[PARTIAL]** (#4951) **Built 2026-10-03:** Skip leaves the project unset and saves nothing; `fichero/Tests/Unit/general/Views/Onboarding/FirstRunStepSelectionTests.swift`. "Set up later" makes a project with no settings
  that behaves as today, and Set Up… in its Inspector runs setup at any time.
- `source.onboard.samples-first` — **[PARTIAL]** (#4951; built (#5668, section 7c): `recipes/samples.propose` picks 3 to 5 pages spread across the material (first, last, largest, smallest, then evenly spaced; every page of a small project), each saying why, and the person's own choice holds and can go back (`fichero-server/tests/unit/recipes/test_setup_samples_5668.py`); from the sample, setup proposes text material when every page is already text (`prepare.sample_is_text`) and preparing faded images (`prepare.sample_shows_faded`). Not built: up to ten (section 7c ruled 3 to 5); suggesting scripts, languages, period and layout from the pages, labelled "suggested from your pages") given material, setup picks up to ten sample
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
- `source.onboard.existing-library` — **[PARTIAL]** (#4951; built: setup on a library with pages takes its samples from them (`fichero-server/tests/unit/recipes/test_setup_samples_5668.py`) and the bake-off its ground truth from their corrected lines; saving the setup runs nothing, and Start, its own job, shows the plan with the page count and estimate before anything runs (`fichero-server/tests/unit/api/test_start_is_the_first_yes.py::test_the_plan_is_shown_before_anything_runs_with_the_page_count`) and never redoes what is done (`source.recipe.done-is-not-redone`); saving the setup again on a library already read leaves every page, segment and reading as it was (`fichero-server/tests/unit/recipes/test_setup_rewrites_nothing_on_a_read_library_4951.py`). Not built: an offer, worded as such, to run the recipe over the existing pages) setup on an existing library takes samples
  and ground truth from its pages, rewrites nothing, and offers running the recipe over its
  existing pages as a separate job with its page count and estimate.
- `source.onboard.search-triggered` — **[GAP]** (#4948, #4951) once scripts, languages and period
  are set, Fichero finds candidates for each step itself, without a manual search.
- `source.onboard.proposes-chain` — **[PARTIAL]** (#4951) **Built 2026-10-03:** the proposed recipe shows each step's model card (note, licence, size, error rate), reasons and gaps; estimates and samples are a gap; `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`. screen 4 shows the proposed recipe: a
  published one that fits (the flagship first where it fits) or a generated one, with each step's
  model, where it runs, download size, licence class and measurements.
- `source.onboard.deterministic-recipe` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-03 (engine):** `assemble()` from answers and cards (`recipes/assemble.py`); cards are not yet read from the real catalogue; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. **Built 2026-10-11 (#5682):** each step's reasons are its own kind's: only a reading step says what material it is made for, its CER and that a bake-off measures it; a line finder, name finder or search model says what covers the project (script, languages), where it comes from and whether it is here (seen in the MCP walk: the embedder, spaCy and blla each said "made for handwriting" and "unmeasured on your pages until a bake-off measures it"); pinned by `fichero-server/tests/unit/recipes/test_step_reasons_by_kind_5682.py`. the recipe is assembled by rules
  from the answers and the cards' confirmed facts; the same answers and catalogue always give the
  same recipe, and each choice names the card facts and measurements it rests on.
- `source.recipe.candidates-filtered-then-ranked` — **[OK]** (#4950) candidates are kept only if they pass the
  hard constraints: the job, script coverage (a Latin reader covers Fraktur and Gaelic type), the language where it
  matters, the material where a reader is made for print or typescript only and the pages are handwriting, the cloud
  only where pages may leave this Mac, this Mac's memory, and the licence. The rest are ranked in a fixed order: a
  measurement on the project's pages in one-point bands; then a reader made for the project's script; then one that
  lists the project's languages, one made for its period, one made for its material; then the published CER in
  one-point bands; then a model already on this Mac, local before remote, cheaper, faster, lower carbon, trainable,
  smaller, and the card id, so a tie is always broken the same way. *Built: `assemble._choose`, `_refusal`,
  `_rank_key` (`source.recipe.script-reader-first`, #5516). Pinned by
  `fichero-server/tests/unit/recipes/test_candidates_filtered_then_ranked_4950.py`.*
- `source.recipe.cheapest-local-first` — **[PARTIAL]** (#4950, #4951; RETIRED 2026-10-17, the code changed in 4ffd86b01 and `assemble._choose` now ranks every passing candidate best first; replaced by `source.recipe.candidates-fallback-chain` and
  `source.recipe.placement-by-scale` below, ruled by the maintainer) the bulk reader is the BEST MEASURED candidate, not the cheapest local one.
  What stood here (pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`, `assemble._choose` choosing the best LOCAL candidate and a remote
  one only when none passes) is the behaviour the next code change replaces; cost and carbon still show beside accuracy, and distilling and
  fine-tuning are still offered as options, never defaults.
- `source.recipe.candidates-fallback-chain` — **[PARTIAL]** (#4950, #5582; ruled 2026-10-17) *Built 2026-10-17 (engine): `assemble._choose` ranks all candidates that pass the hard constraints, best accuracy band first (a cloud one only when pages may leave), and the step carries the rest as `chain`; `start.plan_start` runs the next chain entry that can run when the step's key is missing and records it in `fallbacks`; pinned by `fichero-server/tests/unit/recipes/test_candidates_fallback_chain.py`. Built 2026-10-18: readers measured on the person's pages are ranked in buckets of the project's noise band once an evaluation measured it, a bucket tie (floor of CER over the band, so two readers less than a band apart can still fall in neighbouring buckets) going to the cheaper, then local, one (`Answers.noise_band`, read from `project.read_noise_band` when the project's recipe is assembled; one point until then), `test_a_project_that_measured_its_noise_band_ties_measured_readers_inside_it`, `test_the_recipe_the_project_assembles_reads_its_measured_band`. Built 2026-10-18 (#5758): when the reader left a hand empty or more than half its lines blank, the run summary's `next_reader` names the next entry of the read step's `chain` (a local one first, free; a cloud one with `needs_permission` until pages may leave), offered and never run on its own (`run_view.next_reader`; `fichero-server/tests/unit/recipes/test_next_reader_for_a_hand_5758.py`). Not built: measured-on-the-person's-pages candidates in the chain beyond `cer_measured_here`, 'not enough memory' / 'repository gone' fallbacks, and the app showing `fallbacks`.* the candidates for a step are ranked best-measured first
  (accuracy in one-point bands, measured on the person's pages, else published, else coverage); cheaper, then local, only break ties inside the
  noise band (`source.train.noise-band-per-project`). Cloud candidates stay shown greyed with "needs permission" until the person has said in setup
  that pages may leave this Mac (`source.onboard.pages-may-leave`). When the best candidate cannot run (no key, not enough memory, the repository
  gone), the next one in the chain runs if it is another local model or the same cloud provider, and the plan says which and why; one that sends pages somewhere new (another provider, or off the Mac for a local step) is offered and never used without the person's press; a missing key never substitutes silently
  (`source.recipe.missing-key-never-substitutes`). *Test:* the best measured candidate is chosen over a cheaper one outside the noise band and the
  cheaper inside it; a candidate that cannot run is replaced by the next, named in the plan.
- `source.recipe.placement-by-scale` — **[PARTIAL]** (#4950, #5589; ruled 2026-10-17; the rule is `recipes/placement.py` `place_step`, tested in `fichero-server/tests/unit/recipes/test_placement.py`; built 2026-10-17: the Start plan (`start.place_runs`) puts `place`, `target`, `why` and `sizing` (`remote_read.sizing.size_run`, or \"measured by a 1,000-page pilot\" with no rate) on each read run; built 2026-10-18: with the project's cluster bound (`source.recipe.runs-on-binds-to-a-target`), a read placed `cluster` is sent there by Start as a read-at-scale run under its step and waited on (`runner._run_at_scale`; a cluster that refuses fails the step by name), `fichero-server/tests/unit/recipes/test_project_binds_its_cluster_4950.py`; not built: a vision reader or one reader per material on a cluster (they stay on this Mac and say so), and a live run, which waits on #5238) where the chosen reader runs depends on the project's scale: about 100 or
  about 1,000 pages run on this Mac; about 100,000 pages belong on ACENet or Hugging Face. Below a page threshold set in the plan the reader runs
  locally, above it remotely, where the person has allowed pages to leave. *Test:* the same candidate is placed here for 1,000 pages and remote for
  100,000, and stays here when pages may not leave.
  Also (#5589): each step declares where it can run (Mac / GPU cluster / CPU cluster / cloud); the plan places a step by scale and by GPU saturation. A step reaches a `cluster` target only through its bound target (`source.recipe.runs-on-binds-to-a-target`). Supersedes `source.recipe.cheapest-local-first` (cheapest only within the noise band). *Test:* a 1,000-page step places local; a 100,000-page step places on the bound `cluster` target; a recipe with no bound cluster never places there.
- `source.onboard.spend-cap` — **[PARTIAL]** (#5769, ruled 2026-10-17 Q5) *Built 2026-10-18 (app, unbuilt): `RecipeMoneyAndPlaceFields` asks the cap under the cloud question, shown once pages may go to a cloud service; saved as `answers.hf_spend_cap_usd`, `MoneyAndPlaceAnswersTests`.* Setup records how much the project may spend on Hugging Face a month (`answers.hf_spend_cap_usd`, default $0, refused below $0): at $0 Hugging Face is never the training setting and every Hugging Face place of a train offer is `held`, offered, never started by itself (`answers.spend_cap`, `fichero-server/tests/unit/recipes/test_spend_cap_cluster_copies_5769.py::test_spend_cap_holds_paid_offers`). The Start plan shows this month's spend against the cap (`hf_spend`, `train_offers.spend_this_month`: each Job sent this month, training or reading at scale, at its most, its hardware's price an hour times its time limit; one with no listed price counted as unknown, never $0; `test_spend_this_month_is_shown_against_the_cap`, `test_the_start_plan_carries_the_spend`); a reading run counts a Job for each shard it sent, and a read on a cluster is outside it (`test_a_reading_run_counts_each_shard_it_sent_and_a_cluster_read_costs_nothing_here`; the month turns at midnight UTC, `test_the_month_turns_at_midnight_utc`). A Hugging Face reading run's Inspector shows the same spend (`GET /api/reading-at-scale/jobs/{id}` `hf_spend`, null on a cluster; `test_a_reading_runs_inspector_shows_the_spend_against_the_cap`). Set Up reads the cap from the engine (`GET /api/recipes/stages` `money_and_place`, `test_setup_reads_the_money_and_place_settings_from_the_engine`). Not built: the setup screen's field and the Inspector's line (#5769, Swift).
- `source.onboard.cluster-offer` — **[PARTIAL]** (#5769, ruled 2026-10-17 Q5) where a cluster is set up here, every way offered on Hugging Face also offers the cluster as the free alternative (`place: cluster`, its name, no start action yet, `first_run`: test the connection, dry-run the submission, watch the first job) (`test_cluster_offered_beside_hf`). A Kraken reader trains on a cluster through the same training job (`TrainKrakenRequest.target` the cluster's id; `SlurmTrainTarget`: the set to the run's `data/`, one GPU sbatch running Fichero's trainer in the server image, `out/` home as one tar, the run's folder removed unless copies may stay; `fichero-server/tests/unit/training/test_train_on_a_cluster_5769.py`). Not built: the app's key and sign-in for a cluster (#5238), so a live start is refused by name and the offer's `starts` stays null until the attended first run; the vision LoRA on a cluster (the Hub's base weights staged first).
- `source.onboard.copies-may-stay-on-cluster` — **[PARTIAL]** (#5769, ruled 2026-10-17) *Built 2026-10-18 (app, unbuilt): the same fields ask it where `GET /api/recipes/stages` `money_and_place.clusters` names a cluster, showing the engine's value until answered.* Setup records whether downscaled working copies may stay on the cluster for re-runs (`answers.copies_may_stay_on_cluster`, yes or no); with no answer it follows whether pages may leave this Mac (`answers.copies_may_stay`, `test_copies_stay_default_follows_pages_may_leave`). A read-at-scale run on a cluster reads it when every shard has landed: no takes the run's folder off the cluster (downscaled pages, package, results), yes leaves it for re-runs, and the run's line says which; with failed shards the folder waits for the re-send (`test_working_copies_leave_the_cluster_when_the_project_said_no_5769`). Set Up reads its value as it stands and whether it still follows pages-may-leave, and the clusters set up here, from the engine (`GET /api/recipes/stages` `money_and_place`, `test_setup_reads_the_money_and_place_settings_from_the_engine`). The setup screen's question is built (app, unbuilt: `RecipeMoneyAndPlaceFields`, shown only where `clusters` is non-empty).
- `source.onboard.pages-may-leave` — **[PARTIAL]** (#4951, #5768; built: the engine flags a cloud candidate `needs_permission` until `cloud_allowed`, pinned by `fichero-server/tests/unit/recipes/test_cloud_candidates_need_permission_5768.py`; built in the app, not yet built or looked at: the finder card is greyed with "Needs permission: pages would leave this Mac." and, beside a Set Up step, an Allow Cloud Models press, pinned by `fichero/Tests/Unit/general/Models/CloudNeedsPermissionCardTests.swift`) (ruled 2026-10-17) project setup asks "May pages leave this Mac?"; nothing leaves until the
  answer is yes (`answers.cloud_allowed`), and cloud candidates show greyed with "needs permission" until then.
- `source.recipe.volume-rule` — **[PARTIAL]** (#4950, #4951) **Built 2026-10-03 (engine):** training offered from 5,000 pages in `assemble()`; cost and time limits not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. the volume band changes the
  recommendation: under 100 pages accuracy alone decides; from 5,000 the train step is offered
  from the start; above 100,000 a candidate whose whole-volume cost or time is beyond the limits
  (by default 500 dollars in the cloud or 30 days on this Mac) is shown but not chosen, and the
  teacher-and-student path is proposed.
- `source.recipe.reader-tiers` — **[GAP]** (#4948) with no measurement, readers are ordered by tier:
  specialist line readers, then small historical vision-language models, then general ones;
  Tesseract only for print and typescript; within a tier, by coverage.
- `source.recipe.no-other-style-substitute` — **[OK]** (#4951) a reader made for another style of
  the project's script (naskh for nastaliq) is never proposed in its place; the step is "needs a
  model" and the gap is named. *Built: `assemble._refusal` refuses a reader whose card does not state the
  project's script (`no-model-for-script`), and the step's problem names it only among the nearest, as "a
  related script" (`_nearest`). The ruled exception is Latin: a Latin reader reads Fraktur and Gaelic type,
  the exact one ranking first (#5516). Pinned by
  `fichero-server/tests/unit/recipes/test_no_other_style_substitute_4951.py`.*
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
- `source.recipe.no-llm-correction-in-unknown-language` — **[OK]** (#4950) a correction or
  normalising step by a language model is included only when the model's card lists the project's
  language; otherwise it is left out and the recipe says why. *Built: `assemble._refusal` refuses a
  Correct or Normalise card that does not list the language, or lists none (`no-model-for-language`,
  "No … here knows Arabic yet."); a frontier cloud model is the one exception, counted as multilingual and
  only ever offered (#5718). Pinned by
  `fichero-server/tests/unit/recipes/test_no_llm_correction_in_unknown_language_4950.py`.*
- `source.onboard.assistant-proposal` — **[GAP]** (#4951) a language model may help: filling in a
  prose-only card (facts unconfirmed until a person confirms), explaining a choice, or suggesting
  answers from samples; it runs locally unless the project allows the cloud, and never decides the
  recipe.
The bake-off's behaviours (`source.onboard.bakeoff`, `-combinations`, `-records-combination`, `-tesseract-baseline`, `-minimum`, `-is-a-job`, `-skippable`, `-random-sample`) moved on 2026-10-04 to the one home for evaluation, `compute/distillation.md` ("Evaluation against out-of-the-box models").
- `source.onboard.says-no-model` — **[PARTIAL]** (#4951, #5481) **Built 2026-10-05 (engine):** a step with no fitting model carries one `problem`: `kind` (no-model-for-job, -script, -language, no-reader-for-material, licence-not-accepted, cloud-not-allowed, not-enough-memory; the refusal of the card that got furthest through the rules), one `sentence` naming languages and scripts by name ("No correcting model here knows Spanish yet."), `fix` and `fixes` (download, choose-cloud, choose-model, allow-cloud, accept-licence), and the rules' raw reason in `detail` (the field is `kind`, not `code`: a recipe refuses any key named code); pinned by `fichero-server/tests/unit/api/test_setup_round_two.py`. **Built 2026-10-05 (app), not yet seen:** How it will be done shows a step's problem once, its `sentence`, with its `fix` as a button (Download a model…, Use a cloud model…, Choose a model… open the model finder for that step's job, `source.find.choose-a-model-opens-the-finder`, #5619; they opened Settings › AI Models before, which did nothing visible from setup; Let pages leave this Mac answers the cloud question and proposes the recipe again); the recipe's `gaps` list is no longer shown; `detail` appears only in the Inspector (`RecipeStepsView.lines`); pinned by `fichero/Tests/Unit/general/Models/SetupRoundTwoTests.swift`. *Not built: a download named for the language ("Download a Spanish reader…").* *Built 2026-10-03: a step with no fitting model shows its gap, but as the rules' raw reason, model ids included, and twice (under the step and again below; seen 2026-10-05); `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`.* where no candidate passes the hard constraints
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
- `source.onboard.no-model-step-kept` — **[OK]** (#4951, #5668) *Built 2026-10-11: `start.plan_start` skips it with its fix (choose-model) and drops its refusal; `start._without_what_waits` skips a run that needs what it would make ("waits for <step>"); pinned by `fichero-server/tests/unit/recipes/test_no_model_step_kept_5668.py`.* a step with no model stays in the recipe
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
- `source.onboard.regen-shows-diff` — **[PARTIAL]** (#4951; *engine built 2026-10-18: `POST /api/recipes/assemble` for an open project with a saved recipe returns `changes`, each step added, taken out or run with another model or settings, in a sentence, writing nothing (`recipes/diff.py`; `fichero-server/tests/unit/recipes/test_regen_shows_diff_4951.py`); a step the person set by hand is the saved model, which the assembly keeps. Not built: the defaults' changes (answers other than steps), the app showing the diff, and the person's choice to take a hand-set step back*) changing an answer re-assembles the recipe
  and defaults and shows what would change, step by step; values the person set by hand are kept
  unless they choose otherwise.
- `source.onboard.rerun-rewrites-nothing` — **[PARTIAL]** (#4951; built: saving the setup again with new answers, or with a step's model swapped in the recipe, leaves every page, segment and reading as it was, and the saved recipe says the swap (`fichero-server/tests/unit/recipes/test_setup_rewrites_nothing_on_a_read_library_4951.py`); Start never redoes what is done (`source.recipe.done-is-not-redone`). a Start after a swap may queue a run, but one that asks for no redo, so the pages already done are split off at run time and nothing made changes (`fichero-server/tests/unit/api/test_add_a_layer_later.py::test_swapping_the_reader_after_start_rewrites_nothing_and_a_new_page_gets_the_new_reader`).; the same test queues a page imported after the swap, as an import run over that page alone, with the new reader). a saved reader pin no workflow can run is refused by the plan in words, and Start refuses, never kept as the old reader (#5800; `fichero-server/tests/unit/recipes/test_unrunnable_reader_refused_5800.py`). Not built: the swapped reader proven to run in the page's steps, not only to be in the queued plan) changing a project's answers or recipe
  changes defaults for new work only; nothing already made is rewritten.

The recipe and its format
- `source.recipe.is-a-file` — **[GAP]** (#4950) a recipe can be exported as, and taken from, a
  shareable folder that names its steps, their models, and the scripts, languages, period and
  purposes it suits.
- `source.recipe.makes-a-workflow` — **[PARTIAL]** (#4950) **Built 2026-10-03 (engine):** `plan_start` maps each step to a shipped workflow by name with the step's model (`recipes/start.py`, four jobs so far), refusing by name a step it cannot map; a pinned Kraken reader reaches Transcribe (Kraken) as the run's `kraken` override (`workflows/validation.py`), and a reader outside the catalogue this Mac can fetch is refused; Start validates with `check_recipe`, and the assemble answer is a whole recipe (schema, version, suits); the runs are not started yet; pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/workflows/test_kraken_reader_is_a_run_override.py`, `fichero-server/tests/unit/api/test_start_is_the_first_yes.py`. applying a recipe's steps makes and runs
  workflows; nothing runs except workflows.
- `source.recipe.holds-no-second-copy` — **[PARTIAL]** (built in part, pinned by `fichero-server/tests/unit/recipes/test_start_plan.py`; what is still unbuilt is not yet written down here, R0 2026-10-17; #4950) a recipe refers to workflows in the
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
- `source.recipe.names-models-and-where` — **[PARTIAL]** (built in part, pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py` and `test_yolo_pin_is_a_known_form.py`; what is still unbuilt is not yet written down here, R0 2026-10-17; #4950) a recipe names the model for each step,
  pinned (Hugging Face repository and revision, Zenodo DOI, package and version, Kraken built-in
  and version, or a cloud provider's model id with the date measured) or a role default, and where
  it runs: `this-mac`, `cloud`, `cluster` or `gpu-service`.
  **(2026-10-11)** A YOLO layout model is pinned by its catalogue name (`{yolo: yolo-doclaynet-11n}`), the form
  the shipped card writes, and the recipe check knows it; a pin the check does not know is said in words, never
  as a list of its keys (`recipes/recipe.PIN_FORMS`; `fichero-server/tests/unit/recipes/test_yolo_pin_is_a_known_form.py`).
- `source.recipe.runs-on-binds-to-a-target` — **[PARTIAL]** (#4950) a shared recipe never names a
  person's compute target; the project binds each `cluster` or `gpu-service` step to one of its own,
  and an unbound step waits with "No cluster is set up". *Built: the placement rule takes the step's bound
  cluster and, with none, keeps a step a cluster would suit on this Mac, saying "No cluster is set up for
  this project" (`placement.place_step`; `fichero-server/tests/unit/recipes/test_placement.py`). Built
  2026-10-18: the project binds its cluster (`answers.cluster`, a cluster set up here by the name Set Up shows;
  owner-only, as every cluster is; one not set up here binds nothing), and the Start plan places its reads on it
  (`fichero-server/tests/unit/recipes/test_project_binds_its_cluster_4950.py`). Not built: a binding per step (one
  cluster serves the project's cluster steps), a `gpu-service` target, the Set Up question (Swift), and a live run,
  which waits on the app's key and sign-in (#5238).*
- `source.recipe.alternatives-in-order` — **[OK]** (#4950; ruled 2026-10-18 by default, manager may veto: free and asked) when this Mac cannot run a step's pin,
  the first listed alternative that can is used where it sends nothing anywhere new (a missing key: the step's `chain`, first entry that can run, recorded in `plan.fallbacks`, pinned by `fichero-server/tests/unit/recipes/test_candidates_fallback_chain.py`); a model this Mac cannot serve (memory) is never replaced unasked: a free place is offered and used only on the person's press (`ai.where.fallback-free-and-asked`, pinned by `fichero-server/tests/unit/recipes/test_fallback_free_and_asked.py`). The choice is recorded and shown.
- `source.recipe.conditions-fixed-list` — **[OK]** (#4950) a step's `when` and `offered_when` use
  only a fixed list of conditions (spreads detected, a confidence threshold, a corrected-line
  count); anything else is refused when the recipe is checked. *Built: `recipe.CONDITIONS`
  (`spreads_detected`, `confidence_below`, `corrected_lines_at_least`); `check_recipe` names any other, by its key.
  Pinned by `fichero-server/tests/unit/recipes/test_conditions_fixed_list_4950.py`.*
- `source.recipe.train-never-automatic` — **[PARTIAL]** (#4950, #5336, #5440; reworded 2026-10-17; *built: a train step is never among what Start runs and
  the plan offers it, pinned by `fichero-server/tests/unit/recipes/test_start_plan.py` and `test_train_offers_5660.py`; under `here`, a ready offer starts by itself on this Mac when a recipe step finishes, once
  (a training job waiting, running, paused or done stops another), never on Hugging Face, and a refusal never fails the
  step; after a training here failed or was stopped it starts again only on more corrected lines than it began on (or the
  person's press), and the Start plan's setting says why it waits (`held_after_failure`): `train_offers.start_when_ready`, `fichero-server/tests/unit/recipes/test_training_starts_by_setting_5440.py`.
  Not built: `huggingface` starting by itself (its pages leave only on the person's yes); training again on later
  corrections (#5441)*) training runs by itself only per
  the onboarding setting (`answers.training`: here, huggingface or offered, defaulting by machine; see `source.onboard.auto.train-offer-comes`); with
  `offered` it is offered when its condition is met and runs only when the person starts it. Never an alert.
- `source.recipe.train-offered-per-step` — **[PARTIAL]** (#5660 item 9) for each step a model can be trained
  for, the Start plan offers "Train a model of your own for this step" (`train_offers`), offered later and never
  run at Start: the line reader (fine-tune a Kraken reader, on this Mac or Hugging Face Jobs; distil into an MLX
  vision model by LoRA, on Hugging Face Jobs), regions (fine-tune YOLO, on this Mac), and names (a spaCy
  fine-tune, listed as not available yet: Fichero has no spaCy trainer). Each way names the places the engine
  trains on today and the action that starts it there (`training.start_here`, `training.start`,
  `training.start_vision_lora`, `training.start_regions_here`); a project that keeps its pages on this Mac is
  offered this Mac only. Each offer says how many more corrected lines and pages it needs, counted as the
  bake-off counts them (`bakeoff.readiness`) at the train step's `offered_when` threshold (2,000 corrected lines
  on at least 2 pages by default); regions count the pages holding a person's regions. Built in
  `recipes/train_offers.py`; pinned by `fichero-server/tests/unit/recipes/test_train_offers_5660.py` (4 tests).
  *Not built: Core ML (the engine has no Core ML training path); a cluster (ACENET) or another Mac as a
  training place; the app showing the offers.*
- `source.distil.each-step-has-a-method` — **[PARTIAL]** (#5770; ruled: any recipe step with a model distils into a local model, each by its own method; order read-a-line, review, regions, names) every job in the registry whose step takes a model declares its distil method in `recipes/jobs.DISTIL`: its teacher (what makes the lessons), student, trainer and measure, or none with why (`train_offers.method_for`); a job with a method has an available way to train in the train offers and one with none has none (`fichero-server/tests/unit/recipes/test_source_distil_each_step_has_a_method_5770.py`). Today two jobs have a method, read-a-line (Kraken or MLX LoRA, from the person's corrections or the project's reader) and find-regions (YOLO); review (#4642) and names (#5536) say they are not built yet. Not built: the offers built from the declaration alone (`WAYS` still holds where each runs and the action that starts it).
- `source.recipe.update-is-clicked-not-applied` — **[GAP]** (#5364) a new version of a followed recipe shows
  as an update symbol in the Inspector; nothing changes until the person clicks it; then the recipe
  updates and a re-run of existing pages is offered as one job with its estimate.
- `source.onboard.cloud-asked-once` — **[PARTIAL]** (#4951) **Built 2026-10-03:** asked only when the recipe names cloud_options, saved with the project's answers (PUT /api/recipes/project); `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`, `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. whether pages may leave the Mac is asked once per
  project (at setup or first cloud use, whichever is first) and shown in the recipe editor, where
  every cloud step is marked; it is not asked again per provider or per step.
- `source.recipe.prompt-files` — **[GAP]** (#5364) each prompt is one file with a header naming its
  job, the model it was written for, its version and its variables; a variable the step does not
  supply is refused when the recipe is checked.
- `source.recipe.schema-versioned` — **[OK]** (#5364) `recipe.yaml` carries its schema version; a
  version newer than this Fichero understands is refused with the version named, and an older one
  keeps working. *Built: `recipe.SCHEMA_VERSION` (1); `check_recipe` refuses a newer one by number and one that names
  none (`fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`). Schema 1 is the only one so far, so
  "older" has nothing to read yet.*
- `source.recipe.folder-format` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** `recipe.yaml` load and check (`recipes/recipe.py`); prompts, measurements and the RO-Crate wrapper not yet written by Export Recipe; pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe exports as a folder: `recipe.yaml`
  (published JSON Schema), one file per prompt, its workflows, its measurements, a licence, a README
  and a Workflow RO-Crate wrapper.
- `source.recipe.check-names-every-fault` — **[OK]** (#5364, R6 exit) the check of a hand-edited recipe (`POST /api/recipes/check`,
  `fichero_recipes_check`) names each fault in it, one sentence each, and one fault never hides another or stops the check with
  an error: a schema it cannot read, a missing id, title or steps, code or a key anywhere, steps that are not a list, a step
  that is not a step, a step with no id or another's id, a job this Fichero lacks, a layer not the job's, an unknown condition,
  an unpinned model, an unknown place, a missing prompt file, a step whose inputs no earlier step gives, and a kept choice
  (override) that names a step the recipe does not have or no scope. *`recipes/recipe.check_recipe`;
  `fichero-server/tests/unit/recipes/test_check_names_every_fault_5364.py`.* Publishing, following and forking a recipe stay
  open under #5364.
- `source.recipe.data-not-code` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** code-shaped keys refused anywhere in a recipe (`recipes/recipe.py`); pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe can name only registered jobs, models,
  prompts, settings and workflows built from Fichero's tools; it cannot carry scripts or grant a
  model tools or network access, and an imported recipe that tries is refused, naming the entry.
- `source.recipe.never-holds-keys` — **[PARTIAL]** (#5364) **Built 2026-10-03 (engine):** credential-shaped keys refused (`recipes/recipe.py`); pinned by `fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`. a recipe names providers and models but never
  a key; exporting one that would include a key is impossible by construction, and taking one that
  needs a missing key says which.
- `source.recipe.checked-at-every-door` — **[PARTIAL]** (#4950, #5364; built: `recipe.check_recipe` at setup (`POST /api/recipes/assemble` answers its `problems`), on its own (`POST /api/recipes/check`, `fichero-server/tests/unit/api/test_recipe_routes.py::test_checking_a_recipe_with_code_in_it_names_the_problem`) and before each run (Start refuses a recipe that fails it, `fichero-server/tests/unit/recipes/test_start_plan.py::test_a_recipe_that_fails_the_check_never_starts`); it names unknown jobs, a newer schema, unmet inputs, unpinned models, unknown conditions and missing prompt files by step (`fichero-server/tests/unit/recipes/test_recipe_format_and_check.py`); the Start plan names models this Mac cannot run, refused cloud steps, missing keys and an unbound cluster by step. Not built: the doors that do not exist yet, a recipe taken from a file and an update offered (`source.recipe.is-a-file`, `source.recipe.update-check`); prompt variables) a recipe is checked at setup,
  when taken, when an update is offered and before each run, and the check lists by step: unknown
  jobs, newer schema, unmet inputs, missing pins, models this Mac cannot run, refused cloud steps,
  missing keys, unbound targets, missing prompts or variables.
- `source.job.find-documents` — **[PARTIAL]** (#4949) a step can propose which consecutive pages of a folder form
  one document, for a person to confirm (the existing Group action makes it so). *Built: owned by
  `finding-documents.md` -- the recipe step (`finddocs.recipe-step`, [OK]) and the proposals; accepting them as
  groups is `finddocs.accept-makes-groups` [PARTIAL]. Tested in
  `fichero-server/tests/unit/recipes/test_find_documents_step.py`.*
- `source.job.split-into-entries` — **[PARTIAL]** (#4949) a step can split a diary, register or ledger into
  dated entries. *Built: the recipe's entries stage (`recipes/runner.py`, the `entries` card), tested in
  `fichero-server/tests/unit/recipes/test_diary_entries_step.py`; the entries as units are
  `source.extract.entries-are-units` [PARTIAL].*
- `source.job.extract-to-table` — **[PARTIAL]** (#4949, #5365, #5636) a step can fill one row per document or entry
  with the project's metadata fields, each value tied to the text it came from, exportable as a
  spreadsheet. *Built 2026-10-10: the recipe's `table` card (`recipes/runner.py`, `recipes/table.py`) fills
  the attributes of each document and entry of the step's prototype, each value citing its words; designed
  and tagged in `source/structured-data.md` (`structured.extract.*`, `structured.cite.*`), tested in
  `fichero-server/tests/unit/recipes/test_structured_data_to_spec.py`. Not built: the spreadsheet export
  with a source per cell (`structured.export.csv-source-per-field`).*
- `source.job.pull-out-passages` — **[GAP]** (#4949) a step can gather excerpts on a question or theme,
  each with its source and place, into a note or collection.
- `source.recipe.embedder-by-language` — **[PARTIAL]** (#4948, #4951, #5574) **Built 2026-10-03 (engine):** the smallest local embedder covering the languages, in `assemble()`; since 2026-10-07 the engine's own search embedder first where its card covers them (a library searches one embedding space, so a step naming another is skipped with its fix); the search A/B is not built; pinned by `fichero-server/tests/unit/recipes/test_assemble_by_rule.py`. **Built 2026-10-11 (#5681):** the finder ranks the search step's candidates the same way (`assemble.rank_key`: the engine's space first, so another embedder is never rank 1 without the explicit migration), and an embedder already in this Mac's FastEmbed store reads "On this Mac", not "Downloads when first used" (`local_models.embedding_model_installed`); pinned by `fichero-server/tests/unit/recipes/test_embedder_keeps_the_search_space_5681.py`. the embedder is the smallest local
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
- `source.try.never-over-existing` — **[PARTIAL]** (#4950; *built for the readers' and the line finders' bake-off: it runs as a job and changes nothing that exists, the pages, segments, readings, passes and text are the same after it, pinned by `fichero-server/tests/unit/recipes/test_bakeoff_never_over_existing_4950.py`. Not built: the alternatives of the other jobs, and landing a try as new passes or readings beside the current ones*) each alternative shows its cost and time,
  runs as a job in Activity, and lands as new passes, readings, mentions or claims (a vector
  alternative as an index beside the current one); nothing existing changes.
- `source.try.compared-as-declared` — **[GAP]** (#4950) results open side by side in panes and are
  compared the way the job declares: shapes overlaid with overlap scores against confirmed shapes;
  readings by text diff with error rates against corrected text; entities, statements, links and
  dates by precision and recall against confirmed ones, else side-by-side lists; vectors by the
  top results for the person's queries; each with cost, speed and carbon estimate.
- `source.try.use-this-scope` — **[PARTIAL]** (#4950; tested in `fichero-server/tests/unit/recipes/test_bakeoff_readers.py`, `bakeoff.use_this`; the winner of a combination of steps is not built) Use This makes the winner the step's (or the
  combination's) choice for the project or for one folder, stored as an override on the recipe.
- `source.try.kept-and-rerunnable` — **[PARTIAL]** (#4950; *built for the bake-off: the record is kept in `recipe/bakeoffs/<id>.yaml`, readable after Activity clears the job, listed, and run again on the same pages; pinned by `fichero-server/tests/unit/recipes/test_bakeoff_readers.py::test_the_comparison_is_kept_and_readable_later`. Not built: the other jobs' comparisons, and re-running with the saved selection and options in one action*) a comparison is kept with its selection and
  options and can be run again later.
- `source.try.bakeoff-is-the-same-tool` — **[PARTIAL]** (#4950, #4951, #5660) **Changed 2026-10-11 (ruled: search
  wide, the bake-off decides):** the readers taking part are at most two of each kind (`bakeoff.PER_KIND`) from
  what the finder found (shipped cards, the models here, Kraken's repository, Hugging Face, and the person's
  remote endpoints), those that can be scored here first; there is no rules' top three, and a language with no
  Kraken reader still has its Hugging Face and remote contenders. `GET /api/recipes/project/bakeoffs` says who
  would take part and what reading the sample would cost before it starts (`next_run`: each candidate's
  `run_cost_usd`, the total, a sentence). Pinned by `fichero-server/tests/unit/recipes/test_reader_search_wide_5660.py`. **Built 2026-10-11 (engine,
  #5660 item 7):** one of each kind of reader beside the rules' top three (Kraken, Apple Vision read on this Mac,
  an MLX vision model, a cloud reader only where pages may leave; a kind that cannot read here listed with why,
  never faked), each row with WER beside CER; the line finders compared with `step: find-lines` (Kraken's
  segmenter, Apple Vision's text lines; YOLO named as finding regions, not lines), scored by the checked lines
  each finds; pinned by `fichero-server/tests/unit/recipes/test_bakeoff_contenders_5660.py`. *Not built: the
  app's table for them (B), and Use This for a line finder other than Kraken's (the line step runs Kraken's
  only).* **Built 2026-10-05 (engine, readers
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
- `source.recipe.download-failure-waits` — **[PARTIAL]** (#4950, #5352) a failed model download is shown
  in Activity with its reason, retried three times, then the steps that need the model wait with
  "Model download failed" and offer Retry or the next candidate; other steps run. *Built: a download retries a
  broken connection on its own (`model_downloads.BACKOFF_SECONDS`, four tries, then `COME_BACK_ROUNDS`, five, five
  minutes apart: more than three), its row in Activity carries the reason, and the run's steps on it are not run
  with "Model download failed: <model> did not download (<reason>). Retry it in Activity, or choose the step's next
  candidate in Set Up" while the other steps run (`runner._await_downloads`,
  `fichero-server/tests/unit/recipes/test_start_while_models_download.py`). Built (engine, #5352): the run summary's `download_failed` lists each step waiting on a download that failed, with the
  download's `job_id` to retry (`POST /api/activity/jobs/{job_id}/retry`), and `next_candidate`, the first other entry of the step's
  `chain` (local first; a cloud one carries `needs_permission` until pages may leave), chosen with
  `POST /api/recipes/project/steps/use-candidate` (`run_view.download_failures`;
  `fichero-server/tests/unit/recipes/test_download_failed_actions_5352.py`). Not built: the buttons in the app.*
- `source.recipe.missing-key-never-substitutes` — **[PARTIAL]** (#5364) *Built 2026-10-17 (engine): `start.provider_without_key`; Start skips the step with "Needs a key for <provider>" and runs no model that sends pages somewhere new for it: a LOCAL model, or one of the same provider, from the step's `chain` runs on its own and is named in `plan.fallbacks` (`used` true, `source.recipe.candidates-fallback-chain`); another cloud provider is offered there (`used` false) and never used without the person's press; pinned by `fichero-server/tests/unit/recipes/test_missing_key_never_substitutes_5364.py`. Not built: the app's Add Key… button, and the person's chosen replacement kept as an override.* a cloud step whose provider has
  no key waits with "Needs a key for <provider>" and Add Key…; no other model is used in its place
  unless the person chooses one, which is kept as an override.
- `source.recipe.take-without-missing-step` — **[PARTIAL]** (#4949; record shape ruled 2026-10-17; *built: `recipe.take_without_missing_steps`, `offered_back`, `override_kind`; pinned by `fichero-server/tests/unit/recipes/test_take_without_missing_step_4949.py`. Not built: the route and the app screen that take a shared recipe through it and show the offer*) a recipe naming a job this
  Fichero lacks can be taken without that step. The removal is recorded in the recipe's `overrides` as
  `{step, kind: "removed-step", reason: "job not available", job, scope: "project"}`; an override that states no `kind`
  is a `card` override (a chosen reader, as before), so every record kept so far reads unchanged. After Fichero is
  updated, a removed step whose job now exists is offered back, never put back by itself. *Test:* the taken recipe
  passes the check and holds the record; the original is unchanged; the step is offered back once its job exists, and
  not before.
- `source.recipe.pinned-model-gone` — **[PARTIAL]** (#5364; how it is known, ruled 2026-10-17; *built: `llm/failed_fetches.py`, the store's hook in `_run_download_in_process`, `recipe._check_not_gone`; pinned by `fichero-server/tests/unit/recipes/test_pinned_model_gone_5364.py`. Not built: offering the rule's next candidate, and the Kraken and Zenodo readers' fetches recording a failure*) a pinned model that can no longer be
  fetched is reported by the check, naming the step, and the rule's next candidate is offered. It is known from the
  model store's record of the last failed fetch: when a fetch fails for a reason that is not a dropped connection (the
  repository is gone or refuses the request), the store writes the repository and the reason to `failed_fetches.json` in its
  root, and removes the entry when the model lands. `check_recipe` reads that record and makes no network call. *Test:* a
  failed fetch is recorded and a later one that lands clears it; the check names the step of a pin with a record, and not
  one without.

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
- `source.find.by-need` — **[PARTIAL]** (#4948, #5519) the existing model recommender and language-fit score
  are extended (not replaced) to search by job, script, language, period and local-only, across an
  open list of sources including Kraken's repository and Hugging Face (→ #2116). *Built 2026-10-07 for
  readers: `GET /api/recipes/candidates` gathers the shipped, installed, Kraken-repository and Hugging
  Face candidates by job, script and language, ranked by the rules (below). Period, spaCy pipelines,
  YOLO weights and installed Kraken readers outside the repository are not searched yet.*
- `source.find.installed-readers-listed` — **[OK]** (#5584; built: `installed_readers` in
  `api/routes/ai/local_models.py`, and the Kraken readers downloaded from the repository joined to the
  catalogue in `llm/local_model_catalog.py`; tested in `fichero-server/tests/unit/recipes/test_setup_through_mcp_edges.py`) the local-models list
  (`GET /api/local-models`, MCP `fichero_local_models_list`) lists the readers installed on this
  Mac beside Whisper, embeddings and spaCy: every complete MLX vision model in the model store
  (`model_type` `mlx`) and every Kraken reader downloaded or trained (`model_type` `kraken`), read
  from the one local catalogue Settings lists (`local_inference.installed_local_model_entries`), not
  a second list. `model_type=mlx` or `kraken` narrows it to those.
- `source.find.repository-reader-named` — **[OK]** (#5617; built 2026-10-08: `discovery.repository_record`,
  `discovery.record_words`, `kraken_runtime.recognition_model_bytes`, the repository readers in
  `llm/local_model_catalog.py`; pinned by `fichero-server/tests/unit/recipes/test_reader_cards_5617.py`) a
  Kraken reader downloaded from the repository is named by its record's title, never only by its DOI, and its
  note says what the record states: its languages and scripts by name, the material (print, handwriting,
  typescript) and the period its words name, then where it came from (the DOI). Its size is the record's,
  else its downloaded file's, never 0. Read from the repository listing discovery kept (no network); with no
  listing kept, it is named by its DOI and its note says the record has not been read. A repository candidate's
  reason (`GET /api/recipes/candidates`) carries the same words.
- `source.find.reader-size-real` — **[OK]** (#5617; built 2026-10-08: the shortlist readers in
  `llm/local_model_catalog.py`; pinned by `fichero-server/tests/unit/recipes/test_reader_cards_5617.py`) an
  installed Kraken reader of the catalogue's shortlist (McCATMuS, CATMuS Medieval) lists its size on disk as its
  downloaded file's (`size_bytes`; its record's when the file cannot be read) and its download size as its
  record's (`expected_size_mb`), never 0.
- `source.find.broken-reader-unusable` — **[OK]** (#5617; built 2026-10-08: `kraken_runtime.recognition_model_problem`,
  the Kraken readers in `llm/local_model_catalog.py`, the on-device models `GET /api/chat/providers` offers; pinned by
  `fichero-server/tests/unit/recipes/test_reader_cards_5617.py`) listing an installed Kraken reader (downloaded or
  trained) checks its model file: a file missing, empty or cut short (under 1 KB; a reader's weights run to
  megabytes) is listed as installed but unusable (`available: false`) with the reason in words ("the model file
  is empty"), its size is the file's, and it is never offered to a step (the on-device models a workflow step
  picks from leave it out).
- `source.find.note-counts-agree` — **[OK]** (#5617; built 2026-10-08: `training.job.counted`, the trained
  readers' notes in `llm/local_model_catalog.py`; pinned by `fichero-server/tests/unit/recipes/test_reader_cards_5617.py`)
  a reader's note counts in words that agree with the number: "on 1 page (3 lines)", "1 page held out", never
  "on 1 pages". A trained reader's card is written so, and a card written before (its summary kept on disk) is
  said so when listed.
- `source.find.note-describes-model` — **[OK]** (#5617; built 2026-10-08: the notes in `llm/local_models.py`
  `SPACY_MODELS` and `llm/kraken_runtime.py` `KRAKEN_RECOGNITION_MODELS`; pinned by
  `fichero-server/tests/unit/recipes/test_reader_cards_5617.py`) a model's note in the local-models list describes
  the model (its language, what it reads, what is unmeasured about it), never a period or kind of record it was not
  chosen for: a note shown in every project names no century and no project's material (no "16th-century
  orthography" for a spaCy pipeline, no "court record" for CATMuS).
- `source.find.installed-count` — **[OK]** (#5519) every complete MLX vision model in this engine's
  model store that no shipped card pins (a catalogue model, one Fichero trained, one found in the
  store) is a reader candidate with a card made from its own metadata: its config says it reads
  images, its weights give its size and memory floor, its README's front matter its licence and
  languages; its scripts are unstated, so the rules never miss it for a script no shipped card covers.
  A model with no stated licence needs the person's acceptance like any other. *Pinned by
  `test_model_discovery.py`.*
- `source.find.kraken-repository` — **[OK]** (#5519) the repository's Kraken readers join the
  rules by script (a Latin record whose card says Fraktur covers `Latf`; Han, kana and Hangul cover
  `Jpan` and `Kore`); a record's published CER is ranked on only when it names the project's languages,
  and otherwise is named in its reason. Fetched only when asked and the engine is not offline, kept in
  the model store's `discovery/` folder, fetched again at most daily; offline, the last fetch is used.
  *Pinned by `test_model_discovery.py`.*
- `source.find.hub-runs-here` — **[PARTIAL]** (#5519) the Hugging Face search asks by task
  (image-to-text, image-text-to-text) and language tag, and by name for the HTR words and the
  project's languages (#5660 item 3: TrOCR fine-tunes and VLMs trained on old hands are found by name
  only; one this build cannot run is listed `availability: not_here`, refused in words, never chosen,
  pinned by `test_reader_finder_5660.py`), and offers the rules only MLX builds
  (the `mlx` tag; the Hub ignores a `library` parameter, which is how the old search returned GGUF chat
  models) or a safetensors model's MLX conversion found by its `base_model:` tag, each saying why it is
  offered; never a GGUF repository. *Built, pinned by `test_model_discovery.py` with recorded Hub
  answers. Since #5593 (2026-10-08) what a search finds is kept and the rules choose from it
  (`in_recipe_rules: true`; `source.find.found-reader-downloads`). Residue: the Hub's listing states
  no size or memory for a found build.*
- `source.find.wide-every-time` — **[PARTIAL]** (#5660, ruled 2026-10-11; #5665) the finder searches every time, not as a
  fallback: Kraken's repository, Hugging Face, and the person's remote endpoints (their provider rows' vision
  models, a source of its own, `discovery.remote_reader_cards`, offered and never the rules'). On Hugging Face it
  asks by the tags HTR models are published under (`discovery.HTR_TAGS`: htr, handwritten-text-recognition, catmus,
  palaeography, paleography, manuscripts; and ocr with a language), alone and with each project language, as well
  as by name; it ranks a language match first, then downloads; each listing says how it can run here (an MLX build,
  Fichero's MLX catalogue, or "transformers only" / "a GGUF build": cannot run yet). The COMMA reader
  (`wjbmattingly/comma-qwen-3.5-0.8b-full-33k`, medieval Latin, CATMuS, Apache-2.0) is a shipped card fetched by
  Fichero's MLX catalogue as its Hugging Face checkpoint (mlx-vlm 0.6.17 reads `qwen3_5`), untested inside Fichero
  yet. Pinned by `fichero-server/tests/unit/recipes/test_reader_search_wide_5660.py` (a Latin project finds the COMMA reader by its tags; a German one finds trocr-kurrent and says
  it cannot run yet). *Not built: running a transformers-only reader; converting one with `mlx_vlm.convert` on
  download.*
- `source.find.hub-readers-only` — **[OK]** (#5594; built 2026-10-08: `discovery.reads_text`, `left_out` in `keep_hub` and the source; pinned by `fichero-server/tests/unit/recipes/test_hub_discovery_quality_5594.py`) a Hugging Face result is a reader candidate only
  when its listing says it reads text from images: published as image-to-text, or a vision-language
  model (image-text-to-text) whose tags or name say OCR, HTR, text recognition or document reading. A
  chat build (tagged or named uncensored, abliterated, decensored or heretic, or a vision chat model with
  no OCR use) is never listed, whatever its task; how many were left out is counted (`left_out` on the
  Hugging Face source) and said in its detail. *Test:* a listing mixing an OCR model, a VLM tagged OCR and
  an abliterated chat model offers the first two and says one was left out.
- `source.find.unknown-size-said` — **[OK]** (#5594; built 2026-10-08: `ModelCandidate.size`, null `size_gb`/`memory_gb` in `api/routes/system/recipes.py`; pinned by `fichero-server/tests/unit/recipes/test_hub_discovery_quality_5594.py`) a candidate whose size or memory its listing does
  not state says "size not stated" (`size`), and its `size_gb`/`memory_gb` are null, never 0.0 GB.
- `source.find.reason-names-fit` — **[OK]** (#5594; built 2026-10-08: `discovery._hf_card`; pinned by `fichero-server/tests/unit/recipes/test_hub_discovery_quality_5594.py`. Built 2026-10-18: any script ISO 15924 names in one word of four or more letters is read from the listing's tags or name (`discovery.script_words`; "latin" is the language and "gothic" the blackletter hand, so neither Latn nor Goth is read; a two-word script name is not, nor are the three-letter ones: Han, Lao, Vai, Mro, Yi; `test_a_script_named_in_a_listing_is_stated_whatever_the_script`, `test_latin_in_a_listing_is_the_language_not_the_script`).) a found reader's reason says why it fits the
  project in words: what it reads (OCR, handwriting, a script such as Fraktur where its tags or name say
  so), the project's languages it lists by name, and that it is an MLX build this Mac runs; never only
  "tagged de".
- `source.find.online-search-is-a-job` — **[PARTIAL]** (#5594; built 2026-10-08 (engine): the `find-models` kind, `discovery.search`/`search_online`, `search_job` on `ModelCandidateList`; pinned by `fichero-server/tests/unit/recipes/test_hub_discovery_quality_5594.py`, `test_model_discovery.py` and `test_reader_choice_for_scripts_to_spec.py`. *Residue: its progress is said in words (the query it is on), not as a count Activity can draw; the app's setup screen and the CLI are not yet seen polling the job.*) the online search (Kraken's repository and
  Hugging Face) runs as an Activity job (`find-models`, on the network lane, a person waiting on it) of the
  open project, never inside the request: `GET /api/recipes/candidates?online=true` answers at once with what
  is cached and the job (`search_job`: id, state, reason), the job says what it is searching as it goes and
  keeps what it found (its detail, and the model store's `discovery/` files), and a later call returns the
  fresh list with the job done. A search for the same languages done within a day is not run again; one
  waiting or running is reused. With no project open the online search is not run and the source says why.
  *Test:* the cold call returns before the Hub answers, with the job id; Activity lists the job; once it is
  done the next call lists what it found.
- `source.find.app-finder-three-hosts` — **[PARTIAL]** (built in part, pinned by `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift`; what is still unbuilt is not yet written down here, R0 2026-10-17; #5611) the app's model finder is one view
  (`ModelFinderView`) over one store per project (`ModelFinderStore`, on the project's own client, so every
  call names the project), shown in three places (ruled 2026-10-08): the project's Inspector (a Find a
  Reader disclosure under its readers), Set Up… › Ready (a Find a Reader… button beside a reading step's
  model, opening the finder for that step's job, the project's scripts and languages and its first
  material), and Settings › AI (a section for the open project; with no project open it says to open one,
  since the scripts and languages are the project's answers). The finder never works out a candidate,
  a rank or a fit: it shows `GET /api/recipes/candidates` in the engine's order, and a change to the
  list replaces it as the engine answered it.
- `source.find.app-card-says` — **[PARTIAL]** (built in part, pinned by `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift`; what is still unbuilt is not yet written down here, R0 2026-10-17; #5611) each candidate is a card: its name, the engine's
  reason it is offered (`offered_because`), its size in the engine's words (`size`: "1.2 GB" or "size
  not stated", never 0), where it came from in words (ships with Fichero, installed on this Mac, Kraken's
  repository, Hugging Face), what is measured on the project (`measured`), its licence when not open, and,
  when the rules refuse it, the rules' reason (`refused`) in place of an action. Each source's line
  (`sources[].detail`) is said once above the cards.
- `source.find.app-card-actions` — **[PARTIAL]** (built in part, pinned by `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift` and `fichero-server/tests/unit/recipes/test_model_finder_card_actions_5612.py`; what is still unbuilt is not yet written down here, R0 2026-10-17; #5611, #5612) a card's actions are only those an existing
  route serves: **Download** for any candidate that names a `download`, through the one download route
  (`POST /api/local-models/download/{runtime}/{model}`, the runtime and model its `download` names; the
  card then says Downloading… and Activity shows the job); **Use for This Step** in Set Up… on any
  candidate, through `POST /api/recipes/project/steps/use-candidate` (setup's own `useCandidate`, which
  replaces the step in place); and **Search Online** for the whole list (`online=true`). The card says
  whether the model is on this Mac (`installed`) and where it runs (`runs_where`) in words, and Find a
  Reader… is offered on the steps whose job reads the material (`JobInfo.reads_material`), never a list
  the app keeps. **Built 2026-10-08 (app, #5612), not yet seen:** `ModelFinderStore.download`,
  `RecipeSetupStore.useCandidate`, `ModelFinderCard.facts`; pinned by
  `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift`. **Built 2026-10-08 (engine, #5612):** each candidate
  carries `download` (the action that downloads it, `model.download` with its runtime and id, as the
  Start plan's `downloads` name it; null when it is here, the run fetches it, or it runs elsewhere),
  `installed` (an MLX model in this Mac's store, a spaCy pipeline, a bundled Kraken model; null where
  nothing is downloaded first) and `runs_where` (`this_mac`, `own_machine` or `provider`, `llm.places`);
  `POST /api/recipes/project/steps/use-candidate` (`{step, card}`) sets any listed candidate as a step's
  reader, kept as a project-scope override by the path use-instead takes, through `project.save_setup`
  (audited, undoable); `GET /api/recipes/jobs` says which jobs read the material (`reads_material`).
  Pinned by `fichero-server/tests/unit/recipes/test_model_finder_card_actions_5612.py`. *Residue:* a
  Kraken reader has no download action (the run fetches it); the tag stays [GAP] until the app half is
  seen working.
- `source.find.app-searching-line` — **[PARTIAL]** (built in part, pinned by `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift`; what is still unbuilt is not yet written down here, R0 2026-10-17; #5611) after Search Online the finder says
  "Searching online…" with the job's reason, observed through the project's `ActivityStore` (the one
  poller of `GET /api/activity/jobs`) by the job's id (`search_job.id`, or the `find-models` kind's
  waiting row), never by a poller of its own; when the job leaves the list (done), the finder reads the
  candidates once more with `online` (a search done within a day is not run again, so this returns the
  finished job's findings) and the line goes; when Activity shows it failed, its reason is said in the
  line's place and the finder reads once more without `online`, so a failing search is never queued
  again by itself. *Test:* `ModelFinderStoreTests`.
- `source.find.choose-a-model-opens-the-finder` — **[PARTIAL]** (#5619) a step's Choose a model…,
  Download a model… and Use a cloud model… in Set Up… › Ready (on the step's row, and on the same step
  under Will not run) open the model finder for THAT step's job, never Settings and never nothing: the
  finder lists the engine's candidates for the job (installed and downloadable, with Download and Use for
  This Step), and choosing one replaces the step in place, so the step can run. The finder answers for
  any job a card can name, not only a reader's (`GET /api/recipes/candidates?job=find-statements`); the
  online search is the step's own (`source.find.online-search-per-step`, #5668; it was readers only).
  *Test:* `fichero-server/tests/unit/recipes/test_models_ux_5619.py` (candidates for find-statements);
  `fichero/Tests/Unit/general/Models/ModelsUXTests.swift` (the fix opens the finder for the step).
  Built 2026-10-11 (#5660 item 4): for Find names and the other text jobs the finder also offers Apple
  Intelligence (said "Fichero cannot run it yet" where this build or this Mac lacks it), the catalogue's MLX
  text models to download, and the cloud models of the person's provider rows (with none, a Claude card
  that says to add it in Settings › AI first); spaCy stays the default, these are the person's to choose
  (`discovery.other_text_cards`), and use-candidate keeps the choice, which the Start plan runs with
  (`fichero-server/tests/unit/recipes/test_set_up_steps_5660.py`). **`chosen` without `step` (#5688):** a finder asked
  for a job with no step named marks the open project's step for that job (its first) as `chosen`, so the
  step's own model is never shown as not chosen. *Test:*
  `fichero-server/tests/unit/recipes/test_set_up_follows_the_project_5688.py`.
- `source.find.candidates-fit-the-step` — **[PARTIAL]** (#5668 walkthrough section 4) *Built: a model in this Mac's MLX store or catalogue with a vision path is a reader only, never a card for a text job (`discovery.local_text_cards`, `other_text_cards`); Find regions lists Kraken's segmenter and the YOLO model; pinned by `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py`. Not built: cloud and Ollama models are general chat models and stay offered for text jobs whatever they can see.* a step's candidates are only
  models whose kind does that step's job: readers (OCR and HTR, vision models) for reading; text models for
  Find names, Find statements, Split into entries and Extract to a table; layout models for Find regions;
  line finders for Find lines. A vision model made to read pages (every catalogue model with a vision
  path, and any model in the store whose config has one) is never a card for a text job, so Find
  statements never lists Qwen-VL OCR.
- `source.find.online-search-per-step` — **[PARTIAL]** (#5668 walkthrough section 4) *Built: `discovery.STEP_SEARCHES` (Find names, Find statements, Split into entries, Extract to a table, Find regions), run as the `find-models` job by job and languages, kept in `hugging-face-steps.json`; a found MLX text build downloads through `hub_spec` as a text model; pinned by `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py`. Not built: Find lines and the other steps have no search of their own and say so.* Search Online searches
  Hugging Face for THAT step's job, by the step's own pipeline tags and Hub tags, never "readers only":
  text generation (MLX builds) for the text jobs; token classification (NER) beside it for Find names;
  object detection tagged for document layout for Find regions; the reader search, as before, for
  reading. What it finds is kept for that job and those languages and listed only for that job. An MLX
  text build found for a text job downloads into the model store and runs like a catalogue text model;
  anything else found is listed as one Fichero cannot run yet, saying why. A step with no search of its
  own (Prepare images, Put in order, Export and the like) says so in the sources row in place of
  "Searched for readers only".
- `source.find.used-candidate-runs` — **[OK]** (#5668, found by the end-to-end onboarding run) *Built: Start's
  `_override` reads Apple Vision's pin (`builtin: apple-vision`) as the bake-off does (`bakeoff._reader_of`):
  the `apple` provider; pinned by `fichero-server/tests/unit/importers/test_onboarding_e2e_5668.py`.* A candidate
  the finder lists as runnable on this Mac, once used for the step, is what Start runs: never a step skipped
  for a model the finder offered. Apple Vision, offered for Read a page as the reader that needs no download,
  runs as Apple's own text recognition through the step's workflow.
- `source.recipe.local-text-models-are-cards` — **[PARTIAL]** (#5619) a text model already on this Mac
  is a card for the jobs that send a model text alone and that the shipped cards do not cover
  (`find-statements`, `split-into-entries`): every MLX model complete in this Mac's model store that
  reads text (its card made from the store's own facts, licence included), and every enabled model of
  the person's Ollama or LM Studio rows (not an embedder). Where it runs is by its address
  (`ai.where.place-is-by-address`): a server on this Mac runs on this Mac, free, and never counts as
  sending pages off it; a server on another machine of the person's own is free but its pages leave this
  Mac, so it is chosen only where the project lets pages leave. So a Mac with Ollama or an MLX model is
  offered it for Find statements, by name, rather than "Fichero has no model". *Test:*
  `fichero-server/tests/unit/recipes/test_models_ux_5619.py`.
- `source.recipe.fichero-does-it-steps` — **[PARTIAL]** (#5619) a step Fichero carries out itself
  needs no model and never says it has none: Split pages runs the built-in page splitter (Apple Vision's
  outline and the gutter, on this Mac, free: `model: {builtin: page-splitter}`), Work out dates runs
  Fichero's date rules (`model: {builtin: date-rules}`), as Find the documents and Prepare the image
  already do. *Test:* `fichero-server/tests/unit/recipes/test_models_ux_5619.py`.
- `source.find.one-download-path` — **[PARTIAL]** (#5620) downloading a model has one path: the app's
  one method (`ModelDownloads.start`), used by Set Up… › Ready (To download first), the model finder
  (Inspector, setup, Settings) and Settings' model rows, calls the one route
  (`POST /api/local-models/download/{runtime}/{model}`, the `model.download` action), which queues a
  `download-model` job on the network lane for every runtime, MLX included, so Activity lists it. While it
  runs the job's reason says how far it has got ("Downloading Qwen2.5-VL 7B: 1.2 of 5.6 GB"); the row
  that asked says the same line; a failure says why on the row, in the job's words (and a refusal before
  queueing, such as a model this Mac cannot run, is said at once); when it finishes the engine says
  `model.installed`, the Start plan is read again and the step it waited for can run. The route reads the
  project from the library header as every other route does (#5620: a project whose path had a space was
  refused with a bare 404, so Download did nothing). *Test:*
  `fichero-server/tests/unit/llm/test_one_download_path_5620.py`;
  `fichero/Tests/Unit/general/Models/ModelsUXTests.swift`.
- `source.find.rules-see-candidates` — **[OK]** (#5519) setup's assembly, the bake-off and Use This
  choose from the shipped, installed and cached repository cards (never the network), ranked by the
  same fixed order, so a Japanese, Chinese or Fraktur project gets a reader where one is installed or
  was found; every chosen step whose model is not measured on the project says it is unmeasured until
  a bake-off measures it, and its card names where it came from (`card.source`). An installed vision
  model runs at Start and is scored in the bake-off like a catalogue one. *Pinned by
  `test_model_discovery.py`.*
- `source.recipe.period-weighs-in-the-reader-rank` — **[OK]** (#5683, on #5516's fit tier in
  `source.recipe.script-reader-first`) among the readers whose period covers the project's, the one centred nearest
  the project's period comes first, in whole centuries (for a 16th-century project McCATMuS, 1500–2100, before
  CATMuS Medieval and COMMA, 800–1550, whose periods reach it only at their end); the chosen reader's reasons say
  "made for pages of 1500–2100, the project's period". The finder takes the period too
  (`GET /api/recipes/candidates?period=`), and lists the page readers for `read-a-line` (Apple Vision, a vision
  model; a line step reads the lines Kraken found with them) as the person's to choose, with no rule rank, as the
  bake-off counts them. The bake-off's contenders are at most two of each kind
  (`source.try.bakeoff-is-the-same-tool`), and one whose licence is not yet accepted is named, not scored. WHY
  (2026-10-11, the MCP onboarding walk): a project saved as 16th century, Popayán, ranked McCATMuS (installed)
  4th, behind two medieval readers. Tested in `fichero-server/tests/unit/recipes/test_period_ranks_readers_5683.py`.
- `source.recipe.unstated-period-is-offered-not-chosen` — **[OK]** (test in `fichero-server/tests/unit/recipes/test_unstated_period_5714_5715.py`, filed as #5714) for a project that states a period and
  whose material is handwriting, a reader whose card states no period is offered to the person and measured by
  the bake-off, and ranks below one whose stated period covers the project's (McCATMuS, 1500-2100, for a 16th-century
  hand); **changed 2026-10-17 (ruled, #4950): rank only, never a refusal; with nothing better it is still the choice, and the
  measured pages replace the guess**. The rule names no date and no script, so it
  holds for a Chinese or an Arabic project as for a Spanish one. WHY (2026-10-13, the maintainer's onboarding
  walk): the rules took Apple Vision for reading pages because it states handwriting, costs nothing and needs no
  download, though nothing states it reads a 16th-century hand; its failure would have shown only as a poor score.
  Alone this does not stop the next unmeasured generic reader (a Qwen vision card) taking its place; the same rule
  covers it. *Test:* a 16th-century Spanish handwriting project, with an installed Apple Vision and an uninstalled
  vision model that state no period, is given the period-matched reader, or a named gap, never either of them.
- `source.recipe.apple-vision-is-for-modern-writing` — **[OK]** (test in `fichero-server/tests/unit/recipes/test_unstated_period_5714_5715.py`, filed as #5715; the on/off language-correction measurement is still owed) Apple Vision's card states `period: [1900, 2100]`
  (Apple publishes no handwriting or period claim for `VNRecognizeTextRequest`: the Vision documentation, read on
  2026-10-13, is silent; the maintainer's own use reads 20th- and 21st-century hands, so the 1900-2100 period is stated
  from use, not measured, and is replaced by a measurement on the person's pages as soon as the bake-off has one).
  A card whose stated period does
  not overlap the project's ranks last for that project (`_period_rank` 2; ruled 2026-10-17, no longer refused), and the bake-off names it once with that reason, as it names a reader that
  cannot run here, never silently dropped and never scored for a project it was not made for. `_period_rank` ranks
  and `_refusal` does not today, so the card alone would still enter the bake-off. *Test:* the same project's
  bake-off lists Apple Vision as not taking part, with that reason; a 20th-century project still lists and scores it.
  The card states handwriting for Latin script only (the one use observed); for the other scripts it lists (Cyrillic,
  Han, Hangul, Arabic, Thai) it states print only, since nothing says it reads their hands (one account says cursive Chinese
  is near zero, unverified).
  The engine keeps its language handling (the project's language is passed and a locale Vision does not honour
  raises) and turns language correction off for the bake-off's reading (decided 2026-10-16), so old spelling is not
  pulled toward modern words; one measurement on a corrected page, on and off, confirms it and is kept in the issue.
- `source.try.on-device-model-is-a-reader` — **[GAP]** (#5716) the macOS 27 on-device model (Foundation Models with
  image input, and the OCR tool of `compute/distillation.md`) is a reader the bake-off offers and scores like any
  other, beside Kraken, Apple Vision, an MLX vision model and a cloud reader (at most two of each kind; the
  person may name the readers they want compared, so a cloud model such as Gemini or Claude, an MLX Qwen model or
  a Hugging Face model takes part when named, and the cap only chooses among those not named). It is never the
  rules' choice. Where Apple Intelligence is off or the OS is older it is named once with why. A refusal ("may contain
  unsafe content"), an empty answer or a paraphrase is not read, with why, and never scores as a perfect reading; its
  text is read against the corrected lines like any other. The call is made once per page, not per line, and its
  cold start is shown in the table's speed. *Test:* with a stub that refuses, the table says "not read: refused" and
  gives no CER; with a stub that answers, the row scores. Needs a spec of `fm-bridge`'s image call before code.
- `source.find.models-that-run-remotely` — **[PARTIAL]** (#5717) *Built 2026-10-17 (engine): the Hugging Face search offers a vision-language model with no MLX build or conversion as a card that runs on Hugging Face Jobs (`discovery.remote_compute`, `_remote_card`, `REMOTE_RUNS_ON`), saying where it runs, the hardware's listed price an hour and its size, offered only and never the rules' (`hub_cards`); with no account it is listed as unavailable with why; the finder's sources name Hugging Face Jobs, and Transkribus models and HTR-United as not searched (`remote-compute`, `transkribus`, `htr-united`); pinned by `test_find_remote_models_5717.py`. NOT built: measuring a remote model in the bake-off (it is offered, not scored: no family of the bake-off carries it yet); other remote compute (a cluster, Slurm) is not offered models; Transkribus and HTR-United are named, not searched; the app shows the card as its generic card, with no cost line of its own.* the search for models offers those that need a bigger
  machine than this Mac, not only builds it can run: today `discovery.search_hugging_face` keeps an MLX build or a
  model the Hub names an MLX conversion for, and never offers the rest. A model found for remote compute
  (`remote_read/`) is a card that says where it would run and what it costs, offered and measured like any other,
  never the rules' choice. The sources searched are named in the finder (Kraken's repository on Zenodo, Hugging Face,
  the person's remote endpoints) and so are the ones not searched (Transkribus models, HTR-United), never left
  implied. *Test:* a safetensors vision model with no MLX conversion is listed as "runs on remote compute", with its
  size and cost; with no remote compute set up it is listed as unavailable, with why.
- `source.try.cloud-models-are-compared-for-reading-and-cleanup` — **[PARTIAL]** (#5718) *Built 2026-10-17 (reading half): every cloud reader of the person's provider rows (`discovery.remote_reader_cards`: Claude, Gemini, OpenAI, OpenRouter, any vision model of a row) takes part; two of a kind by the rules' order, and any the person names in addition (`named` on `candidates`, `next_run`, `start`, the start request and `GET /project/bakeoffs?named=`), each priced before anything runs, none scored where pages stay here, none the rules' choice; pinned by `test_bakeoff_cloud_models_5718.py`. **Ruled 2026-10-18 (owner confirmed), built:** a frontier cloud text model (Claude, Gemini, OpenAI, OpenRouter) counts as multilingual (`Card.multilingual`), so `REWRITING_JOBS` never refuses it for a language; the cloud text cards of those providers carry `correct`, are offered only (never the rules' choice), name that pages leave this Mac, and wait for permission while pages stay here. The frontier list is a default the owner can change (`recipes/seed/frontier-cloud-providers.txt`, one provider type a line; `discovery.frontier_providers`); pinned by `fichero-server/tests/unit/recipes/test_cloud_cleanup_candidates_5718.py`. NOT built: the Correct comparison itself (a bake-off family that feeds each candidate the uncleaned reading and scores it against the person's corrected lines), which still waits on where the uncleaned reading comes from.* the person's cloud models
  (Claude, Gemini, OpenAI, OpenRouter, whatever their provider rows enable; the spec names none, the rows do) are
  compared by the A/B, for reading (a reader kind of the bake-off today: `remote_reader_cards`) AND for clean-up,
  the Correct step, which has no comparison and no cloud text card today (`TEXT_MODEL_JOBS` lacks it). A clean-up
  candidate takes each page's reading and returns it cleaned; it is scored against the person's corrected lines and
  against the uncleaned reading, so the table says whether it helped or made the text worse (a model that rewrites
  old spelling into modern words scores worse, and says so). The cost for the sample is shown before anything runs;
  a cloud candidate takes part only where the project lets pages leave; a model that does not list the project's
  language is refused for a rewriting job (`REWRITING_JOBS`). Never the rules' choice. *Test:* with a stub cloud
  model that modernises spelling, its row has a higher error rate than the uncleaned reading and the table says
  "made it worse"; with one that fixes a slip it says "better".
- `source.recipe.script-reader-first` — **[OK]** (#5593; built 2026-10-08: `made_for_script` and `_rank_key` in `recipes/assemble.py`, a record's material in `discovery._row_material`; pinned by `fichero-server/tests/unit/recipes/test_reader_choice_for_scripts_to_spec.py`) among the readers that pass the hard
  constraints, one **made for the asked script** comes before a generic one: every script its card
  states is the asked one, its parent (Latin for Fraktur) or one of its parts (kana for Japanese), its
  card lists the project's languages, and it states a published CER. A generic multilingual card (a
  base model trained on many scripts) never outranks it, however low its own CER. Next, a reader whose
  card states the asked material (print, handwriting) comes before one that does not state it, so the
  same generic card is not chosen for print and handwriting alike; a repository record's material is
  read from its own words ("printed", "manuscript"). Only then does a published CER rank, so it only
  ranks cards of the same script tier and material. A measurement on the project's pages outranks all
  of these. *Test:* a Fraktur print project gets a Fraktur card, not the multilingual base model; a
  Spanish project keeps PP-OCRv6 (no Latin-only card states a CER). **Fit before an average (#5516,
  2026-10-11):** before material and before any published CER, a card that lists the project's languages
  (or any) comes before one that lists others, and a card whose period
  covers the project's period (`answers.period`, read as years) comes before one that states no period,
  which comes before one whose period is another (cards state `period: [from, to]`: CATMuS Medieval
  800–1550, McCATMuS 1500–2100). So a 13th-century Latin project gets CATMuS Medieval over PP-OCRv6's
  3.9% averaged over 44 languages (the bake-off agreed: 11.2% against 16.4%), and a 19th-century German
  print set to Latin gets McCATMuS. A project that answers no period ranks as before. Fraktur itself: a
  repository record filed as Latin whose own words say Fraktur covers `Latf` (`discovery._row_scripts`,
  #5593); no shipped card claims it, so before a search a Fraktur project names its nearest readers. *Test:*
  `fichero-server/tests/unit/recipes/test_reader_fit_5516.py`.
- `source.recipe.no-cross-script-reader` — **[OK]** (#5593; Fraktur and Gaelic type (`Latf`, `Latg`) are Latin: a reader that states Latin and lists the language fits them, one that states the exact variant ranking first, `assemble._refusal`, #5516, pinned by `test_fraktur_gets_a_reader_5516.py`; built 2026-10-08: `discovery.covered_scripts` widens a card one step from what it states, never chained; pinned by `fichero-server/tests/unit/recipes/test_reader_choice_for_scripts_to_spec.py`) a reader is never chosen for a script its
  card does not cover: a Japanese card covers Han, kana and Japanese, never Traditional or Simplified
  Chinese, so Classical Chinese (`Hant`) never gets the Kuzushiji reader silently. Where no reader
  covers the script, the step says so (`source.onboard.nothing-fits-names-nearest`).
- `source.find.found-reader-downloads` — **[PARTIAL]** (#5593; built 2026-10-08: `discovery.keep_hub`/`hub_cards`/`hub_spec`, the model store's `hub_spec`; pinned by `fichero-server/tests/unit/recipes/test_reader_choice_for_scripts_to_spec.py`. *Residue: the Hub's listing states no size or memory, so a found reader's are unknown until downloaded; the download itself is not exercised without the network.*) a Hugging Face reader found by the online
  search is kept beside the repository listing in the model store's `discovery/` folder, joins the rules
  for the languages it was found for (never the network at assembly), and where the rules choose it the
  Start plan offers it as a download (`downloads`, with `instead`), through the same model download as a
  catalogue model (`local_models_to_download`, `model.download`); a size the Hub did not state is said to
  be unknown, never zero. *Test:* a Tamil project after an online search has its reader in `downloads`.
- `source.onboard.nothing-fits-names-nearest` — **[PARTIAL]** (#5593; built 2026-10-08 (engine): `_nearest` and `_problem` in `recipes/assemble.py`, the plan's skip in `recipes/start.py`, `StepProblem.nearest`/`refused`; pinned by `fichero-server/tests/unit/recipes/test_reader_choice_for_scripts_to_spec.py`. *Residue: "the same language family" is not built (the engine holds no language families; a card listing the project's language stands in); the app's step row is not yet seen showing the nearest.*) where no reader fits, the step's
  problem sentence stays short and names up to three nearest readers by name (one for the same script
  but another material, then a related script, then one listing the project's language), never an id;
  `detail` is one short line (how many cards each rule refused, naming two of each); every refused card
  and why stays in the structured `refused` list and
  `nearest` lists the three. The Start plan's skipped step says the same sentence.
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
  shows a node named **Models** (was Training; ruled 2026-10-10, #5655) listing those models
  (`SidebarModelsNode`, `SidebarModelsNode.name`, `TrainedModelsStore`), drawn only when there is one; tested in `fichero/Tests/Unit/general/Models/TrainedModelsStoreTests.swift`. Not
  built: the base model as its own node inside Models (the Inspector names it). Since #5539 (ruled
  2026-10-06) a model trained for a project lives inside its package (`models/`) and the project's list
  holds those, with the models in the engine's global store whose card names the project; each says
  where it lives (`lives`: `project`, `global`, `both`; `compute.model.lives-in-project`).* training is a node in the sidebar; the
  base model and every model a run produced show inside it. A model with no training stays in
  Settings only.
- `source.model.trained-card-keeps-its-release` — **[OK]** (#5683) the card a recipe sees for a model Fichero
  trained says what its own card says: its licence "trained by you; not for release" unless its card says
  `not_for_release: false` (the one test, `training.project_models._may_publish`), and the languages its card
  names, never its base model's README's (a reader taught on Spanish notebooks is not an English one). It stays
  usable in the person's own projects (`open_licence`: no licence to accept); releasing is what it never does. WHY (2026-10-11, the MCP onboarding walk): the trained Mosquera reader, taught on Sergio's
  notebooks, showed `open_licence: true` and `languages: ["en"]` while its own card said not for release; Sergio's
  pages may train a model but never be released. Built: `recipes.discovery.installed_cards` and
  `local_text_cards`; tested in `fichero-server/tests/unit/recipes/test_trained_card_keeps_its_release_5683.py`.
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
  `distill.eval.job`), make global (built in the engine as `training.make_model_global`,
  `compute.model.make-global`, #5539) and publish, through the one audited action layer. The node keeps the history:
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

16. **Translate or normalise, Search and Pull out passages under the stages** (#5668). **Ruled
    2026-10-11: all three are stages** (Translate, Passages, Search; section 7c). The ruling lists
    eight stages; these three jobs have none. *Recommend:* three more stages after Dates & Times, each
    with its page (Translate & Normalise: into what; Search: nothing to ask; Passages: which kinds), so
    every job a person can choose has a page and a sample result.
17. **Where a stage's sample results are kept** (#5668). **Ruled 2026-10-11 as recommended.** *Recommend:* on the project's setup, beside
    `recipe/setup.yaml`, one record per stage (the samples, the models, the result), replaced on each
    try and cleared when the stage is unticked; never in the tables that hold the project's work.
18. **The hands offered** (#5668). **Ruled 2026-10-11: a curated list of hands per script and century,
    mapped to Hugging Face tags, each with a picture example, plus free text.** *Recommend:* a short list per script and century kept by the engine
    (Latin: Caroline minuscule, Gothic textualis, Gothic cursiva, Secretary, Humanistic, Italic,
    Kurrent, Copperplate; others as their own lists grow), each with the Hugging Face tags it maps to;
    anything typed is kept as typed, and Not sure is an answer.

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

Not verified in this pass: what Apple Vision does with handwriting
(Apple's Vision documentation, read 2026-10-13, makes no handwriting or period claim; see
`source.recipe.apple-vision-is-for-modern-writing`), right-to-left, vertical text and single-line pictures (to be probed at run time); a fair
comparison of line-by-line against whole-page reading by vision-language models; whether the
Hugging Face revisions in the example exist (they are illustrative).

## Triaged from the backlog (2026-10-04)
- `source.segments.align-page-text-to-lines` **[GAP]** (#5217; split into the `source.align.*` entries below, to the "properly" bar): when a page's text belongs to the page and not to its lines, the Segments list says so ('text on the page, not aligned to lines') and offers one Align Text to Lines tool, as a dialog or a tool option, whose result is a pass the person confirms. Run by hand, it runs by itself only where the match is known to be perfect, such as a reliable import (ruled 2026-10-01). In a recipe the tie is automatic above a match threshold, with doubtful lines flagged for review and kept out of the training set until checked (ruled 2026-10-04, #5444; see `source.job.tie-text-to-lines` and Rulings).

### Align Text to Lines, to the "properly" bar (#5217, #5486; ruled 2026-10-17)
The tool is `tie-text-to-lines` (`checking/tie_text.py`, `source.job.tie-text-to-lines`); these entries are the bar it is built to. If one cannot be met,
drafts stay drafts and #5217 records why.
- `source.align.new-reading-never-overwrites` — **[OK]** (#5217; tested in `fichero-server/tests/unit/check/test_tie_text_to_lines.py`
  (`test_the_readings_are_the_machines_never_a_persons`, `test_the_tie_writes_onto_the_pages_lines_and_never_makes_a_second_pass`) and
  `test_which_reading_counts_after_the_tie.py`) the alignment lands as a NEW reading on each line (`representation.create`, derived from the
  page reading), never overwrites a reading, and never replaces a person's or a confirmed one as the counting reading.
- `source.align.confidence-per-line` — **[OK]** (#5217; the score is the reading's `machine_confidence`, set by the job; tested in `fichero-server/tests/unit/check/test_tie_text_to_lines.py` (`test_each_aligned_line_carries_how_well_the_text_matched_it`, 12 pass) and `test_which_reading_counts_after_the_tie.py` (12 pass); the app showing it beside the line is the Swift half) each aligned line carries how well the page text matched it (the score against the
  rough read of the line, 0 to 1), kept on the reading it made and served with the line, so the person sees which lines to check; today the score
  is only in the job's result and in the reason of a rejected line.
- `source.align.known-misalignments-fixture` — **[OK]** (#5217; tested in `fichero-server/tests/unit/check/test_align_text_to_lines_5217.py`: a clean control, a dropped line, two lines merged, two reordered; 5 pass) the aligner is pinned over a real two-page fixture with known misalignments: a
  line the reader dropped, two lines it merged, two it reordered; each case says what lands on which line and which lines are doubtful.
- `source.align.below-threshold-stays-a-draft` — **[OK]** (#5217; `tie_text.page_is_draft`, `DRAFT_ABOVE` 0.5 stated not measured, the job counts `drafts` and flags the page; pinned by `test_align_text_to_lines_5217.py` and the unchanged `test_tie_text_to_lines.py`, 11 pass) a page whose alignment is too poor (the share of doubtful lines above a limit)
  gets no readings at all: it stays a draft, flagged as "text on the page, not aligned to lines", never half-aligned; its lines keep their own reads.
- `source.align.person-moves-text-between-lines` — **[GAP]** (#5217) for a line whose text landed on the wrong line a person can move the line's
  first or last words to the neighbouring line, split a line or merge two (the segment split and merge actions exist and undo), each a new reading by
  the person, every step undoable. *Test:* moving words from line 2 to line 3 gives each a new person reading and one undo restores both.

## Behaviour ids for issues this spec described without one (R0, 2026-10-17)
Each is described in the paragraph named; the id lets a test cite it.
- `source.read.kraken-confidence-kept` — **[OK]** (#5707; tested in `fichero-server/tests/unit/recipes/test_kraken_readings_5707.py`) a
  Kraken reader reading lines a page already has keeps each line's certainty on its reading, and a reading the same result already
  wrote on a line is not written a second time (described under `source.onboard.auto.blank-pages-not-read`'s neighbours: "Not on
  unreadable text").
- `source.recipe.step-counts-its-pages` — **[OK]** (#5706; tested in `fichero-server/tests/unit/recipes/test_steps_count_what_they_did_5706.py`)
  a step whose output may leave no trace on a page (Find Names on a page naming no one, Prepare on a clear page) keeps on the run the pages
  it ran on, and the plan counts them done, so a page is not "to do" after every run.
- `source.sort.written-recto-is-read` — **[OK]** (#5705; tested in `fichero-server/tests/unit/recipes/test_one_blank_rule_5705.py`) the pages a
  run leaves out are the pages Find the Documents calls blank, by one rule; a written page is never sorted blank and left out of every later run.
- `source.job.names-warn-on-unreadable` — **[OK]** (#5694; tested in `fichero-server/tests/unit/recipes/test_names_on_unreadable_text_5694.py`)
  Find Names is not run on a page whose reading is too uncertain, and the step says which pages and why.
- `source.extract.entry-text-from-its-lines` — **[PARTIAL]** (#5601; *built in part, pinned by `fichero-server/tests/unit/workflows/test_entries_over_lines_5601.py`;
  the entries are child nodes, not yet units over their lines*) a diary entry is the set of lines it covers; its text is read from them, not copied.
- `source.train.spacy-names-fine-tune` — **[GAP]** (#5536) a spaCy names model is fine-tuned on a project's confirmed names, on this Mac or on
  Hugging Face; today the train offer for Find Names says "not available yet: Fichero has no spaCy trainer".
- `source.train.regions-yolo` — **[PARTIAL]** (#5525; *built in part, pinned by `fichero-server/tests/unit/training/test_yolo_regions_training.py`;
  the table detectors are not built*) a YOLO layout model is trained on the person's corrected regions, on this Mac.
- `source.lines.teacher-check-honest-end` — **[OK]** (#5524; built 2026-10-08: a stop for memory waits and carries on after its last finished page, then finishes with the whole run's counts in its words, no memory message, and no line given a second verdict (the queue marks a job whose work returns done), pinned by `fichero-server/tests/unit/check/test_line_check_memory.py`; a passing line is counted and gets no verdict, pinned by `fichero-server/tests/unit/check/test_line_against_page.py::test_a_good_line_passes_and_gets_no_verdict`; the built rule, as `source.lines.reading-checked-against-the-page` says, ruled 2026-10-18 by default, manager may veto) a teacher-line check that lands its verdicts ends "completed" with correct status counts,
  and never "failed" with a memory message that contradicts the verdicts that landed; a passing line is counted, with no verdict.
- `source.lines.correct-this-line-verb` — **[PARTIAL]** (#5499; *built in part, pinned by `fichero-server/tests/unit/api/test_correct_a_line.py`
  and `test_import_ground_truth.py`*) correcting a line is one verb, not three ids and six flags, and a person's corrections count as the
  bake-off's ground truth.
- `source.try.compare-in-setup-works` — **[PARTIAL]** (#5727; built: the engine path Set Up calls, offer to table to Use This, pinned by `fichero-server/tests/unit/recipes/test_compare_in_setup_works_5727.py`; not reproduced: the live failure on the scratch project, which needs a GUI Set Up run) the Compare step in Set Up (the bake-off) works on a scratch project with enough
  corrected lines; the symptom is first reproduced and pinned by a test (`source.try.bakeoff-is-the-same-tool`).
- `source.find.htr-united-and-tessdata` — **[PARTIAL]** (#5571; built 2026-10-18, HTR-United half: `recipes/htr_united.py` reads the catalogue (`catalog.json`), keeps it in `discovery/`, and `matching` finds datasets by language, script and hand, most lines first, with licence, format and size; `search_online` fetches it when a day old and the finder counts the kept datasets for the project's languages; pinned by `fichero-server/tests/unit/recipes/test_htr_united_datasets_5571.py`. `htr_united.offered` says what each may be used as (test set, training) and the licence to accept first, an unaccepted or unstated licence used as nothing, served by `GET /api/recipes/htr-united`. NOT built: the app's offer and the import of a dataset's PAGE/ALTO, Tesseract's tessdata) discovery reads HTR-United's catalogue (ground-truth datasets by language, script,
  period and hand, offered as a bake-off test set and fine-tuning data, ground truth only, licence respected) and Tesseract's tessdata.
- `source.train.on-the-persons-corrections` — **[OK]** (#5700) a reader is fine-tuned on the person's corrected lines, not only distilled from a
  model's lines, and the readiness count matches what it trains on. *Offer built (#5700, m-recipes-r3): the line reader's
  first way is "Fine-tune a Kraken reader on the lines you corrected" (teacher `person`, this Mac or Hugging Face Jobs),
  the material its corrected-lines readiness counts, and the way that starts by itself under `here`; distilling a model's
  lines stays a second way (`fichero-server/tests/unit/recipes/test_train_on_corrections_5700.py`). The set's teacher `person` is built and pinned by
  `fichero-server/tests/unit/training/test_train_on_the_persons_corrections_5700.py`. The readiness count is the set's line count (`test_the_readiness_count_is_the_set_it_trains_on_5700`), and the trained reader's card says it was trained on the lines you corrected, never "none checked by a person" (`test_a_reader_taught_by_the_persons_corrections_says_so_on_its_card_5700`).*
- `source.train.noise-band-per-project` — **[OK]** (#5692, ruled Q6 2026-10-17) a project's noise band is measured (CER spread over three held-out splits, 0.5 until
  measured), stored and served, so a comparison says when a difference is noise. *Built: an evaluation measures it from
  the best reader's pages, from 15 read pages up (`training.evaluation.noise_band`, `NOISE_MIN_PAGES`), the project keeps it (`recipe/noise-band.yaml`,
  `recipes.project.read_noise_band`, the ruled 0.5 CER points until then, said so), and every train offer carries it
  (`noise_band`); `fichero-server/tests/unit/training/test_noise_band_per_project_5692.py`. The reasons A/B judges by it when its
  request names no band (`reasons_job.band_for`, `test_the_reasons_ab_uses_the_projects_band_unless_one_is_given`). A
  trained reader is adopted only past it (`source.train.adopt-only-past-the-noise-band`).*
- `source.train.adopt-only-past-the-noise-band` — **[PARTIAL]** (#5700, #5441, R4 exit) after an evaluation, the best trained Kraken
  reader measured becomes the project's read-a-line reader only when its CER on the held-out pages beats the best downloadable
  reader's by more than the project's noise band; it is kept as the step's project-scope override (`model: {trained: <reader id>}`,
  its CER, and why, naming both CERs and the band) through `project.save_setup`, audited and undoable. The reader to beat is the
  step's current one when the evaluation measured it, else the best downloadable one. A reader the person chose (Use This, a
  bake-off, a cloud reader) is never replaced: past the band the trained reader is `offered`, and only a reader the rules or an
  earlier adoption chose is swapped (review 77). Measured on fewer than 15 held-out pages (`NOISE_MIN_PAGES`), nothing is
  adopted. Within the band, or worse, the current reader is kept and the evaluation's reason says why. *Built: `training.evaluation.adopt_trained`, called by
  the evaluation job (`result.adoption`); `recipes.cards.kraken_reader_for` reads a `trained` pin;
  `fichero-server/tests/unit/training/test_adopt_past_the_noise_band_5700.py`. Not built: a trained vision model set on the
  step (it is measured and carded only).*
