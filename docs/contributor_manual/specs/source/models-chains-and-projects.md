# Source Model — Models, chains, projects and the synced folder — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Setting up a project" section: the few questions Fichero asks, what it sets
> up from the answers, how to see and change the chain of models a project uses, how to find a
> better model, how to see how any reading was made, and how a project's folder is kept in
> step.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Behaviour ids below have **no tags yet**; everything under "The design" is unbuilt
> design.
>
> **See also, and do not duplicate.** Four specs own neighbouring ground and change daily on
> the release branch. This slice builds on them and restates none of them:
> `ai/ai-settings.md` (ratified: provider rows as peers, downloads inside each row, ONE
> catalogue; its `settings.one-catalog-unification` is the catalogue this slice describes the
> *contents* of); `ui/model-selector-consistency.md` (ruled: pickers list the configured
> models and the role defaults such as `$small`, `$large` and the vision tiers, from one
> shared list builder); `ui/workflows.md` (a workflow is a saved graph of tool nodes; the
> workflow bar; the locked default workflows); `ui/workflow-node-config.md` (what a node's
> popover shows). Where this slice needs one of them to change, that is listed under
> "Requests to other specs", not done here.

## Intent

The source model makes a page rich. This slice is about how that richness gets *made* with the
least effort and the most honesty: which model does which job, how jobs chain, how a project
says what it is so Fichero can set itself up, and how the results stay in step with a folder
on disk.

Four rulings from the maintainer drive it (recorded in the foundation): every model described
one way, the same in the app, over MCP and on the command line; steps chain, and how a result
was made is always visible, through workflows and the workflow bar; a project sets itself up
through a short onboarding, because language and models are no longer one setting for a whole
project; and a project can be tied to a synced folder.

## What exists today (read on disk 2026-09-19 by a code worker; to be re-read before tagging)

- **Models are described in five or more different shapes**: providers (`llm/providers.py`);
  cloud model prices and abilities from a vendored list (`llm/model_types.py`); the local
  catalogue entry (`llm/local_inference.py`) which spaCy, Kraken and Whisper are folded into
  (`llm/local_model_catalog.py`); a separate list of embedding models (`llm/local_models.py`);
  and named model profiles in the app database (`llm/model_profiles.py`). None says what a
  model **takes in and gives out**; the nearest thing is a free list of words such as
  "segmentation" or "recognition". The AI settings spec already records the unification as a
  gap with open issues.
- **Two families of engine routes** (one for MLX, one for spaCy, Kraken and Whisper) carry
  through into two families of MCP tools. **The command line has no model commands at all**:
  it can run workflows and manage providers, nothing else.
- **Role defaults** (`$small`, `$large`, vision tiers) are app-wide. A workflow node can store
  an alias, resolved when it runs. There is no default at the level of a project, a folder or
  a document.
- **Kraken's reading models are a hard-coded shortlist of two**, fetched from Zenodo by DOI and
  marked in the code as provisional. There is no browsing of Kraken's repository or of
  Hugging Face.
- **Chains.** Workflow tools declare typed ports, and about fifty default workflows ship. But
  the paleography ones are a single transcribe step with a tuned prompt, not real chains.
  "Find the lines with one engine, read them with another" exists **four separate ways** with
  no shared part. VERIFIED on disk by the spec writer (file and function), 2026-09-19:
  (1) `llm/kraken_runtime.py` `recognize_lines` / `recognize_to_geometry`: Kraken segments
  (`blla.segment`) and reads (`rpred.rpred`) in one script; (2)
  `workflows/tools/economy_htr.py`, tool `economy_htr`: `crop_line_strips` cuts line pictures,
  then `trocr_transcribe_lines` or `kraken_transcribe_page` reads them, all inside one
  function `economy_htr_file`; (3) `workflows/tools/align_transcript.py`, tool
  `align_transcript`; (4) `workflows/tools/merge_geometry.py`, tool `merge_geometry`. What (3)
  and (4) do inside (joining by counting lines; laying a reviewed transcript over word boxes)
  is from the code worker's reading, INFERRED here. **Kraken's
  baselines cropped and handed to Apple Vision or a local vision model does not exist**,
  though every piece it needs does (Apple Vision accepts any image; the cropping exists).
- **How a result was made** is partly recorded: an artifact names its provider, model, run,
  step and the artifact it came from. It is not shown as a chain anywhere.
- **A prototype system exists** (VERIFIED on disk: `models/node_prototypes.py`,
  `models/prototype_schema.py`): a node can name a prototype; prototypes inherit from a parent
  and carry attributes that a node of that prototype takes on, in the manner of Tinderbox. It
  is used for kinds of document today. It is the natural base for project profiles.
- **Fichero's own licence is the GNU Affero GPL, version 3** (VERIFIED: `LICENSE` at the root).
- **No project.** Nothing between a project and a document carries settings. The one
  project-level setting mechanism has a single use. First-run onboarding asks about the
  project, permissions and AI providers; it asks nothing about languages, scripts or period.
- **Apple Vision** runs in the engine, takes a language from a supported list, and returns line
  and word boxes.
- **Two Readers exist**: a native one, and an engine-made HTML page that declares itself
  English. Neither handles direction, script or vertical writing.
- **Embeddings** use one multilingual model for everything; the alternative is chosen by an
  environment variable, not in Settings. Vectors live in DuckDB and refuse to mix spaces.
- **spaCy** knows five languages. For any other language it **falls back to English without
  telling the user** (VERIFIED on disk; recorded as broken in
  `historical-text-normalization.md`, #4914), or to a language model if nothing is installed.

## What the field does (survey, 2026-09-19; sources at the end)

- **Kraken's model repository** (the `ocr_models` community on Zenodo, read through the
  HTRMoPo project that `kraken list` uses) now publishes a machine-readable model card: task,
  script, language, characters covered, accuracy, licence, authors, a DOI for the version and
  one for the family. It covers segmentation, reading, reading order and correction, and is
  not tied to Kraken alone.
- **HTR-United** catalogues *training sets*, not models. (When the maintainer spoke of two
  places, these two are the likely pair: HTR-United for ground truth; Zenodo/HTRMoPo for
  models.)
- **Hugging Face** is where most other models live and can be searched by language, task,
  project and licence. Period and script are only in free text, so Fichero must read the
  model pages to find "seventeenth-century Spanish". Teklia publishes permissively licensed
  PyLaia readers there; the CATMuS sets are there.
- **Transkribus** has hundreds of public models, usable only inside Transkribus.
- **OCR-D** describes every tool in one machine-readable file with typed inputs, outputs and
  parameters: the closest prior art to describing models one way.
- **Arkindex** signs every result with the run that made it, from which the tool version, its
  settings and the **model version** can be recovered: the closest prior art to "how was this
  made".
- **Onboarding elsewhere is tiny.** eScriptorium insists on two things only: reading direction
  and where the line sits (on the baseline, or hanging from a top line as in Hebrew).
  Transkribus asks nothing until a job is run.
- **Evidence on vision-language models**: they now beat older recognisers on modern hands and
  do well on historical print; a small open model trained on historical text (CHURRO) beats
  much larger ones. But they invent plausible readings and quietly modernise spelling, which
  a faithful transcription must not do. No study was found that compares, fairly, reading
  each cut-out line against reading the whole page: Fichero should measure that on its own
  sources.
- **Licences.** The YOLO family (Ultralytics, DocLayout-YOLO, and YALTAi which puts YOLO
  inside Kraken) is under the AGPL, and its publisher holds that this covers the trained
  weights too. **Fichero is itself AGPL, so these are compatible with it**, with one caution
  not yet checked with anyone qualified: the Mac App Store build, where Apple's terms and
  copyleft code from *other* authors do not sit easily together. So such models are better
  **downloaded on request than bundled**. Models whose terms are not open at all are a
  separate matter (below). Surya's weights
  carry a revenue cap. One well-known embedding model (jina-embeddings-v3) is non-commercial;
  the two Fichero uses or offers (multilingual-e5, BGE-M3) are permissive. Apple's own document
  reader (macOS 26), Detectron2 / LayoutParser and the RT-DETR family have no such problem.
- **Apple's frameworks cover none of the hard cases** (early-modern hands, Syriac, woodblock
  Chinese, Indigenous orthographies). Their language lists must be asked for at run time, not
  assumed.

## The design (proposed)

### One card for every model

Every model Fichero can use has one **model card**, in one shape, whatever it is: a cloud
vision-language model, a local one, Apple Vision, a Kraken segmenter, a Kraken reader, a
layout detector, a spaCy or Stanza pipeline, an embedding model, a speech recogniser.

The cards are the **contents of the one catalogue** the AI settings spec already calls for.
They are what the shared picker lists and what a role default resolves to. They are not a new
catalogue beside it.

A card says:

- **What it is**: name, version, who made it, where it came from (a DOI, a Hugging Face
  address), how to cite it.
- **What it does**: one or more **jobs** from the list below.
- **What it suits**: scripts, languages, a period (from year, to year), print or hand or
  typescript, reading direction, where the line sits, the characters it knows.
- **How it runs**: on this machine or in the cloud; the engine it needs; its size; the memory
  it needs; whether this Mac can run it.
- **How far to trust it**: its licence and **licence class**; its published accuracy, on what
  data; what it was trained on; its known limits; whether Fichero's maintainers have tried it;
  and **this project's own measurements** of it against ground-truth pages (see
  `formats-and-training.md`).

The same card is what the app shows, what MCP returns and what the command line prints.

### Jobs: what goes in and what comes out

A short, fixed list of jobs, each defined in the source model's own terms. This is what makes
chaining safe: a step can only follow a step that gives what it needs.

| Job | Takes | Gives |
|---|---|---|
| find regions | a page image | a pass of regions, with kinds |
| find lines | a page image (and regions, if any) | a pass of lines with baselines and polygons |
| put in order | a pass | a named reading order |
| read a line | a line's picture | a reading of that line |
| read a page | a page image | a reading of the page, with or without shapes |
| tie text to lines | a reading of the page + a pass of lines | readings on those lines |
| correct | a reading + the picture it was read from | a new reading that names the first |
| propose a shape | a page image + a click | one shape |
| find a table's cells | a table segment's picture (and its lines, if any) | cell segments with rows, columns, spans and headers |
| trace a drawing | a segment's picture | a drawing (SVG) as a reading of that segment |
| describe / classify a picture | a segment's picture | a description, or classes |
| translate / transliterate / normalise | a reading | a reading |
| find names; tag words | a reading | mentions on stretches of it; word-level analysis |
| make a vector | a reading, or a picture | a vector |
| transcribe speech | a stretch of a recording | a reading, with timings |

"Read a page" is kept apart from "read a line" on purpose. Vision-language models mostly do
the first, and cannot be trusted to keep shapes; Kraken and its kin do the second.

### One way to say "find here, read there"

A single general step replaces today's three or four special ones: **take the segments of a
pass, cut each one's picture (to its polygon, straightened on its baseline), hand each to any
model that can do the next job, and write what comes back as readings on those same
segments.** With it:

- Kraken finds the baselines; Apple Vision reads each line.
- Kraken finds the baselines; a local vision-language model reads each line; a second model
  corrects against the picture.
- A person draws the lines by hand for a script no segmenter knows; any reader reads them.
- A layout detector finds the regions; each kind of region goes to a different reader (a
  table to one, a marginal gloss in another language to another).

`economy_htr`, `align_transcript` and Kraken's own segment-and-read become cases of it, not
separate code.

### Chains are workflows

A **chain** is a workflow: a saved graph of steps, as the workflows spec already defines.
There is no second kind of thing. What this slice adds:

- steps declare their job, so a chain can be checked before it runs (what each step gives is
  what the next one takes);
- a step's model is a **model card or a role default**, chosen with the one shared picker;
- a chain can be made of **jobs with no model named** ("find lines, read each line, correct,
  find names"), which resolves against the project's settings when it runs. That is what lets
  one best-practice chain serve many projects;
- the **workflow bar** offers the project's default chain first, on whatever is selected:
  sources, pages, or these three lines;
- machine output arrives as a **new pass or new readings**, never over a person's work.

### How was this made

Every pass and every reading carries its **making**: the run; the step; the model card and its
exact version; the settings used; what it was given (which pass, which reading, which image);
and whether a person or a machine made it, set by the engine. Because each reading names what
it was made from, the whole chain can be walked back.

- The **Inspector** shows it for the selected segment, as a short readable chain: "Lines found
  by Kraken (blla, version…) → read by Apple Vision (Spanish) → corrected by Qwen (local) →
  corrected by you, 3 May."
- The **workflow bar** and the run log show the same for a run.
- The same answer comes back over MCP and the command line.
- Two chains run on the same page can be **compared**, reading against reading, and scored
  against ground truth where there is some.

### A project

**A project is what Fichero has called a library** (the maintainer has decided on the new
name; the rename is not yet carried through the app, and is not this spec's to carry). One
project is one research undertaking with its own file: a palaeographic project here, a
project of twenty-first-century notes there. So a project is not a new kind of container, and
nothing new sits between it and its folders.

What is new is that **a project has settings of its own**, and an onboarding that fills them
in. Until now almost every such setting (language, the models for each job) has been one
value for the whole app.

### Project profiles: "Spanish palaeography", and it sets itself up

A **profile** is a named, shareable description of a kind of project: "Spanish palaeography,
16th to 18th century"; "Medieval Latin with glosses"; "Modern typed notes"; "Syriac
manuscripts". Choosing one is often the *whole* of onboarding: say "Spanish palaeography" and
Fichero brings the right languages and scripts, the right chain, the right models (offering
to download them), the right transcription guideline, and only the tools that matter.

- A profile is built on the **prototype system that already exists**: a profile is a prototype
  for a project. Profiles inherit ("Spanish palaeography, notarial hands" from "Spanish
  palaeography" from "Handwritten, Latin script"), and a project can override anything.
- A profile is **a plain file that can be shared** (one JSON document, or lines of JSON for a
  set of them): languages and scripts; period; material; **which recipe is its chain** and
  which model does each job; the project's rule for what counts as the record (strict or
  relaxed); the guideline and level of normalisation; model suggestions with their citations; rights
  defaults; what the synced folder should hold. It holds no sources and no secrets.
- Profiles can be **exported, imported, and published** by a community of practice, so best
  practice for a language or a script travels as a file, not as folklore. Fichero ships a
  starter set, kept as data.
- **It can be automatic, after a first yes.** Automatic work is switched on once for each
  project, and the first time Fichero shows what it is about to do and waits. After that new
  sources go through the project's chain by themselves. Whether what it makes counts as the
  record follows **the project's rule**: in a strict project (every new project) it is a pass
  and readings to look at until a person says so; in a relaxed project the newest counts.
  Cloud models are used only if the project allows it.

Project settings sit **inside the cascade already ruled** for language and other attributes:

```
app  >  project  >  folder  >  source  >  page  >  region  >  line  >  word  >  character
```

Each level inherits from the one above unless it says otherwise, and every shown value says
where it came from. So a project of mostly Spanish papers can hold one folder of Nahuatl
ones, set on that folder, without becoming two projects. A project whose settings were never
filled in behaves exactly as today. (The cascade was recorded earlier as a future direction;
per-project settings bring its upper levels forward.)

A project's settings:

- **What it is**: languages, scripts, period, print or hand, how complex the pages are. These
  become the defaults that cascade down to its pages and segments.
- **Its chain**: the default workflow for new sources, and which model does each job here (a
  card, or a role default). Two projects can use quite different models: a
  palaeographic one, and one of twenty-first-century notes.
- **Its rules**: whether pages may leave this machine (which shuts out cloud models for
  everything in it); the transcription guideline and level of normalisation; the rights
  defaults (see `rights-and-access.md`).
- **Its folder**, if it has one (below).

### Onboarding: a profile, or five questions

Onboarding is a window (the app's first-run window, which already has a step for making a
library, is the thing to grow), shown when a **new project** is made. The same settings are
reached afterwards from **Project Settings…**, in the File menu and on the project's context
menu. One window, reached two ways; no second settings surface. An existing project can run
the onboarding at any time.

**It starts with sample pages** (ruled 2026-09-19). Drop in a few pages and Fichero proposes
what the project is: scripts, languages, print or hand, period, how complex the pages are,
and the profile that fits best. Then a profile, or the questions, or both, to correct what it
proposed. With no sample pages, it offers the profiles; and if none fits, making a project
asks **at most five things**, each of which changes what Fichero does.
Anything that can be worked out is worked out and shown for correction, not asked.

1. **Which scripts?**
2. **Which languages?**
3. **Print, handwriting or typescript, and roughly when?**
4. **How complex are the pages?** (one column; columns or tables; margins and glosses)
5. **May pages leave this machine?**

(How faithful the transcription must be is set by the guideline a profile carries, not asked
as a sixth question.)

Reading direction and where the line sits follow from the script, and can be corrected. The
Mac's abilities are detected. Better still: **give Fichero a few sample pages first** and it
proposes answers to 1 to 4, which the researcher corrects.

From the answers Fichero proposes a **default chain**. A best-practice chain is a **recipe: a
shareable file of its own** (ruled 2026-09-19) that names the jobs, the models that suit, and
for which languages, scripts and periods it is meant. Applying a recipe **makes a workflow**.
What runs is always a workflow, so there is still one way of running things; a recipe is a
second way of arriving at one, built to be shared between people and projects. Profiles and
onboarding point at recipes. Fichero ships a starter set. Fichero says plainly:

- which models it will use, and why;
- which it needs to download, how big they are, and their licences;
- **where no good model exists**, and what to do about it: "No reader is known for this
  script. Transcribe twenty pages by hand, or with a vision model and correct them; Fichero
  will then help you train one." Honest absence, never a quiet wrong substitute.

Examples of recipes the survey suggests: modern typed English (Apple's document reader, spaCy,
the multilingual embedder; all local); early-modern Spanish hands (Kraken lines, the nearest
reader, a local vision model correcting each line, expect to fine-tune); medieval Latin with
glosses (regions by kind, a CATMuS reader, LatinCy); an Arabic manuscript (right-to-left
lines, a reader searched for by script, no dependable historical word-tagger, so stop at text
and vectors); an Indigenous language in Latin letters (a letter-faithful reader, **never** a
language-model correction that would turn it into Spanish or English; no fake lemmas); a
script nothing can read (lines, hand transcription, train).

Onboarding can be run again; changing an answer changes defaults for new work and rewrites
nothing already made.

### Finding a better model

From a project, or from the AI settings, a researcher can **look for models that suit**: by
job, script, language, period and whether it must run locally. Fichero searches the places the
field keeps them (Kraken's repository on Zenodo; Hugging Face; an open list that can grow) and
shows results **as cards**, with licence class, size and whether this Mac can run them.

- **Open** models (permissive, or copyleft compatible with Fichero's own AGPL) download
  without a further step. Others (non-commercial; gated; special terms; a revenue cap) say so
  plainly and need a deliberate choice; some cannot be redistributed at all and the card says
  why.
- A model's **citation is shown** wherever its work is shown, and goes into exports.
- A downloaded model becomes a row under its provider in the AI settings, like any other.
- A model can be **tried on a few pages** and measured against ground truth before it is made
  a project's default.

### The Reader shows anything

The Reader lays out any script in its direction (right-to-left, vertical, mixed), uses the font
a reading needs, shows declared signs as their pictures, and keeps glosses and notes in their
places (detail in `languages-scripts-signs.md`). There is **one** Reader renderer that does
this; today there are two, and neither does.

### Language tools are honest

A word-tagger or name-finder runs only for a language it was made for. Where none exists,
Fichero says so, and offers what does work for any language (search, vectors, a language
model if the project allows one). It never quietly runs the English pipeline over another
language.

### A synced folder (which is also a new way to import)

A project can be tied to a folder on the machine where the engine runs. This is more than
export: the folder is a **new way to start an import**, and it needs real engine and app work
(watching the folder; matching files to sources; bringing outside edits in as passes; showing
conflicts). It is a new *trigger* for the one import path that `importer/importer.md` owns,
not a second importer. Taking files **in** from the folder is switched on for each project,
and the first time it shows what it is about to bring in and waits for a yes (a folder of
fifty thousand images must not start work by surprise).

- **Out, as you go.** For each source, Fichero keeps chosen outputs up to date in the folder.
  It writes the **working pass and the chosen readings**. Where a reading nobody has chosen
  is written, the file and its loss report say it is machine-made. Outputs:
  the page's PageXML or ALTO, a TEI file for the source, plain text, the training set, and the
  rest of `formats-and-training.md`. When a segment or reading changes, the affected files are
  rewritten soon after, not at some later export. Each file says which pass, reading order and
  kind of reading it holds, and carries its loss report beside it.
- **In, as they arrive.** New images dropped into the folder become sources in the project and
  go through its default chain. An XML file that appears or changes there (edited in another
  tool) comes in as **a new pass with its own provenance**, the same as any import. It never
  overwrites work in the project.
- **Conflicts are shown, not settled silently.** If the project and the file both changed,
  Fichero keeps both, as two passes, and says so.
- **Restricted material stays out** of the folder unless deliberately included.
- The folder is a **projection**: it can be deleted and made again from the project. The
  project remains the record.
- The engine may be on another machine, so the folder is named on the engine's side; the app
  never assumes it can see the same disk.
- Writing is throttled like all background work, so a large project never pegs the machine.

## Behaviors (ids proposed; untagged until approval)

Model cards and jobs
- `source.model.one-card` — every usable model has one card in one shape, whatever kind it is.
- `source.model.card-is-the-catalogue` — cards are the contents of the single catalogue; the
  shared picker and role defaults read them; no second catalogue exists.
- `source.model.jobs-typed` — a card names its jobs from a fixed list, each with what it takes
  and gives in source-model terms.
- `source.model.suits` — a card states scripts, languages, period, material, direction and line
  position.
- `source.model.licence-class` — a card carries a licence and a licence class; only open
  models (permissive, or compatible copyleft) download without a further deliberate step.
- `source.model.citation-shown` — a model's citation appears wherever its work is shown and in
  exports.
- `source.model.measured-here` — a card shows this project's own measurements of the model.
- `source.model.cli-parity` — the command line can list, show, search, download and remove
  models.

Chains and making
- `source.chain.is-a-workflow` — a chain is a workflow; no second chaining mechanism exists.
- `source.chain.checked-before-run` — a chain whose steps do not fit (what one gives is not
  what the next takes) is refused before it runs, with the reason.
- `source.chain.segments-to-any-reader` — one general step cuts each segment's picture and
  hands it to any model that can do the next job, writing readings back on the same segments.
- `source.chain.jobs-without-models` — a chain can name jobs only, resolved against the
  project's settings when run.
- `source.chain.bar-offers-project-default` — the workflow bar offers the project's default
  chain first, on the current selection, down to chosen segments.
- `source.chain.output-never-overwrites` — a chain's output is a new pass or new readings.
- `source.making.recorded` — every pass and reading records run, step, model card and version,
  settings, inputs, and person-or-machine (set by the engine).
- `source.making.walkable` — the chain behind any reading can be walked back step by step.
- `source.making.in-inspector` — the Inspector shows the selected segment's making as a
  readable chain.
- `source.making.same-everywhere` — the same making is returned over MCP and the command line,
  and shown for a run in the workflow bar and run log.
- `source.making.compare-chains` — two chains' results on one page can be compared and scored.

Projects and onboarding
- `source.project.has-settings` — a project (today's library) has settings of its own for
  languages, scripts, period, chain, models, rules and folder; one never filled in behaves as
  before.
- `source.profile.is-a-prototype` — a project profile is a prototype for a project;
  profiles inherit from one another, and a project can override any value.
- `source.profile.shareable-file` — a profile can be exported to and imported from a plain file
  that holds settings, chain, tools to show, guideline and model suggestions, and no sources
  or secrets.
- `source.profile.sets-up-the-project` — choosing a profile sets languages, scripts, chain,
  guideline and the tools shown, and offers to download the models it names.
- `source.chain.bar-offers-what-fits` — beside the project's chain, the workflow bar offers the
  workflows the current selection can feed; there is no list of tools to hide.
- `source.recipe.is-a-file` — a best-practice chain is a shareable recipe file that names jobs,
  suitable models, and the languages, scripts and periods it is for.
- `source.recipe.makes-a-workflow` — applying a recipe makes a workflow; nothing runs except
  workflows.
- `source.profile.automatic-after-first-yes` — automatic chaining is switched on for each
  project and confirms before its first run; what it makes counts as the record only as the
  project's rule allows.
- `source.project.record-rule` — a project is strict or relaxed about what counts as the
  record; a new project is strict; a profile can set either.
- `source.project.one-settings-window` — making a new project and Project Settings… (File menu
  and the project's context menu) open the same window; there is no second surface.
- `source.project.in-the-cascade` — project settings sit between the app and a folder in the
  one cascade; a folder can override them; a shown value says which level it came from.
- `source.project.own-models` — two projects can use different models for the same job.
- `source.project.stays-local` — a project marked "pages may not leave this machine" refuses
  cloud models for everything in it, and says why.
- `source.onboard.five-questions` — making a project asks at most five questions.
- `source.onboard.samples-first` — onboarding starts by asking for sample pages, and from them
  proposes scripts, languages, material, period, layout and the best-fitting profile, for
  correction.
- `source.onboard.derives-not-asks` — direction, line position and hardware are worked out,
  shown, and correctable.
- `source.onboard.proposes-chain` — the answers yield a proposed default chain from recipes
  kept as data, with models, downloads and licences stated.
- `source.onboard.says-no-model` — where no suitable model exists, Fichero says so and proposes
  the hand-transcribe-then-train route; it never substitutes silently.
- `source.onboard.rerun-rewrites-nothing` — changing a project's answers changes defaults for
  new work only.

Finding models
- `source.find.by-need` — models can be searched by job, script, language, period and
  local-only, across an open list of sources including Kraken's repository and Hugging Face.
- `source.find.results-are-cards` — results are shown as cards, with licence class, size and
  whether this Mac can run them.
- `source.find.try-before-default` — a found model can be tried on chosen pages and measured
  before becoming a default.

Reader and language tools
- `source.reader.one-renderer` — one Reader renderer shows any script, direction and declared
  sign.
- `source.nlp.no-silent-fallback` — a language tool runs only for a language it supports;
  otherwise Fichero says none exists and offers what does work.

The synced folder
- `source.sync.writes-the-record-or-says-so` — the folder holds the working pass and chosen
  readings; an unchosen machine reading written there is marked machine-made in the file and
  its loss report.
- `source.sync.intake-is-opt-in` — taking files in from the folder is switched on for each
  project and shows what it will bring in before its first run.
- `source.sync.outputs-follow-edits` — chosen outputs in the project's folder are rewritten
  soon after the segments or readings they hold change.
- `source.sync.files-say-what-they-hold` — each file names its pass, reading order and reading
  kind, with its loss report beside it.
- `source.sync.new-images-come-in` — images added to the folder become sources and run the
  project's default chain.
- `source.sync.outside-edits-are-passes` — a changed or new XML file comes in as a new pass
  with provenance and overwrites nothing.
- `source.sync.conflicts-kept-both` — when project and file both changed, both are kept and
  the conflict is shown.
- `source.sync.restricted-stays-out` — restricted material is left out of the folder unless
  deliberately included.
- `source.sync.folder-is-a-projection` — the folder can be deleted and remade from the project.
- `source.sync.one-import-path` — files arriving through the synced folder go through the same
  import path as any other import.
- `source.sync.engine-side-and-throttled` — the folder is named where the engine runs, and
  syncing is throttled background work.

## Requests to other specs (for the manager to route; nothing edited here)

- `ai/ai-settings.md`: the single catalogue's entries should take the card shape above,
  including embedding models (today chosen by an environment variable) and licence class.
  Also: its local-runtime "profile" (`llm/model_profiles.py`) should take another name (a
  runtime configuration), because **profile** now means a project's set-up.
- `ui/model-selector-consistency.md`: a picker row could show what a card knows (suits,
  local or cloud, licence class); that spec's open question on what a row shows.
- `ui/workflows.md` / `ui/workflow-node-config.md`: a recipe file makes a workflow (the
  maintainer ruled recipes are files of their own; the locked default workflows and recipes
  must not become two stores of the same chains); steps declare a job; a chain is checked
  before it runs; the general "segments to any reader" step replaces `economy_htr` and its
  kin; the known drift between `kraken_model` and `kraken_recognition_model` disappears when
  the model is a card.
- `historical-text-normalization.md`: done. The silent fall-back to the English spaCy pipeline
  is recorded there as `histnorm.language.no-silent-english-entity-model`, broken, #4914.
- The Reader specs: two renderers exist, one declaring itself English.

## Test matrix

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.

## Sources

- HTRMoPo: https://github.com/mittagessen/HTRMoPo · Kraken repository: https://kraken.re/6.0.0/advanced/repo.html · https://zenodo.org/communities/ocr_models/records
- HTR-United: https://htr-united.github.io/catalog.html · CATMuS: https://huggingface.co/datasets/CATMuS/medieval · Teklia PyLaia: https://huggingface.co/collections/Teklia/pylaia
- Hugging Face API: https://huggingface.co/docs/hub/api
- Transkribus public models: https://help.transkribus.org/public-models
- OCR-D tool description: https://ocr-d.de/en/spec/ocrd_tool · Arkindex runs and models: https://doc.teklia.com/arkindex/processes/worker_runs/ · https://doc.teklia.com/arkindex/models/
- eScriptorium quick start: https://escriptorium.readthedocs.io/en/latest/quick-start/
- YALTAi: https://github.com/PonteIneptique/YALTAi · Ultralytics licence: https://www.ultralytics.com/license · Surya model licence: https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE
- Apple document reading: https://developer.apple.com/videos/play/wwdc2025/272/
- LatinCy: https://spacy.io/universe/project/latincy · Stanza: https://stanza.stanford.edu
- Embedders: https://huggingface.co/intfloat/multilingual-e5-large · https://huggingface.co/BAAI/bge-m3
- CHURRO: https://arxiv.org/pdf/2509.19768 · Benchmarking LLMs for HTR: https://arxiv.org/pdf/2503.15195

Not verified in this pass: HTRMoPo's exact field names; what Apple Vision does with
handwriting, right-to-left, vertical text and single-line pictures (to be probed at run time);
a fair comparison of line-by-line against whole-page reading by vision-language models.
