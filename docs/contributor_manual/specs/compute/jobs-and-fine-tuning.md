# Remote Compute — Jobs, engines, fine-tuning and publishing — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — "Sending work away, and training your own model": choosing where a run
> happens; what queued, running and finished mean on a cluster; cancelling; training Kraken on
> pages you corrected, and seeing whether it helped; training a language or vision model; what
> comes back to your Mac; publishing a model or a dataset, and what cannot be taken back.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass, 2026-09-20.** A slice of the
> compute set: read `remote-compute.md` first. Behaviours carry **no tag and no issue yet**, by
> the rule stated there. **VERIFIED / INFERRED** for our code; **CITED / UNVERIFIED** for
> outside services, with S-numbers from "Sources" in `remote-compute.md`.

## Intent

Wherever a researcher can run a workflow, they can choose where it runs. A job is shown the
same way whatever the target: waiting to send, sending, queued there, running, fetching, done;
or failed, with the reason in words. On a cluster, large work is cut into pieces that run side
by side and can be re-sent piece by piece when some fail. Fine-tuning is a kind of job: a
training set goes out, a model and its scores come back, and the model appears as a card in
the one catalogue, already measured against the researcher's own ground truth, so the first
thing they learn is whether it helped. Publishing is separate, deliberate and honest about
what cannot be undone.

## What exists today

- **The Slurm job describer** and its tests: script, array jobs, sparse re-submit, throttle,
  state mapping, submitter seam, scripted fake (VERIFIED
  `workflows/remote_jobs.py:92-118`, `:310-344`, `:246-302`, `:361-374`, `:458-491`).
- **The submitter that does nothing**: `SshCliSubmitter` builds commands; `enabled` is False;
  with it True every method raises `NotImplementedError` (VERIFIED `:504-553`).
- **A runner that was never written**: the default command is
  `python runner/run_task.py --manifest … --index …` (VERIFIED `:435-442`; absent by search).
- **Run states**: the canonical `RunStatus` that Slurm states map onto (VERIFIED `:17`,
  `:246-263`).
- **The provider list** with local-server rows that speak the OpenAI-style protocol: Ollama,
  LM Studio, oMLX (VERIFIED `llm/providers.py:48-51`); and rows for Kraken, spaCy, Whisper and
  Apple as peers (`:35-47`), as `ai/ai-settings.md` ratified.
- **Kraken on the Mac** runs in its own environment by subprocess, and fetches recognition
  models by DOI from Zenodo (VERIFIED `llm/kraken_runtime.py:23`, `:94-104`, `:213-269`). It
  only reads; it is never trained (`source/formats-and-training.md:15`).
- **No training code, no YOLO code, no vLLM, and no call to MLX's convert step** anywhere in
  the engine (VERIFIED by search).
- **Training sets, scores and cards are designed elsewhere and unbuilt**: `source.train.*`
  (#4947), `source.model.*` and `source.find.*` (#4948). That spec says a Kraken training spec
  "is not written" (`formats-and-training.md:133-135`). For the *running* of training, this is
  it.
- **The Hugging Face dataset bundle is designed and unbuilt** in the exporter
  (`export.huggingface-dataset-ready-bundle`; #4069, #2181, #1806), on the DuckDB Parquet writer
  that is built (`export.duckdb-parquet-not-pyarrow`, [OK]).
- **Open issues this slice answers or serves:** #31 (look into Blackfish), #4621 (Kraken
  capability, including fine-tuning), #4642 (distil a small palaeography vision model).

## Which engine for which work

The maintainer asked for whatever is most efficient on Linux under Slurm, and whether that is
Blackfish or loading the models directly. The honest answer differs by kind of work.

### The evidence

- **A serving engine beats a plain loop by about ten times or more** for language-model
  throughput. vLLM's own measurement was up to 24 times Hugging Face `transformers` (CITED,
  S17; a 2023 figure: trust the order of magnitude, not the number). vLLM and SGLang are within
  the same order of each other; published comparisons are vendors' and are treated as noise.
- **vLLM is slow to start**: about three minutes for an 8B model, most of it compiling and
  warming up, not loading weights (CITED, S17). So it must be started **once for a whole batch
  or a whole session**, never once for a page.
- **vLLM runs with no web server at all**: its offline mode takes a list of prompts and returns
  a list of answers inside one Python process, and its documentation calls that its simplest
  use (CITED, S17). When the work and the model are in the same job, a web server between them
  adds a port, a client and a failure for no gain.
- **vLLM serves one base model with many small adapters**, loaded while it runs (CITED, S17).
  That is exactly the shape of "one 8B model, and an adapter for each researcher's hand". Its
  documentation warns that loading adapters at run time is for trusted settings only, which a
  person's own session is.
- **vLLM under Apptainer on Slurm is an established pattern** with public reference scripts
  (CITED, S17).
- **Hugging Face's TGI is finished**: in maintenance, its repository archived in March 2026,
  its makers pointing to vLLM and SGLang (CITED, S17).
- **llama.cpp** runs the same model file on a Mac, a CPU and a GPU. It is the fallback for a
  Linux machine with no NVIDIA GPU. It is slower than vLLM on a GPU.
- **Kraken has no server.** It is a command and a Python library over PyTorch. The unit of
  parallel work is the process. No figure for pages a second on a GPU has been published
  (UNVERIFIED; to be measured on the maintainer's own pages before any is quoted).
- **Layout detection needs no server.** It is one pass over each image with nothing shared
  between images, which is the only thing a serving engine exists to share.
- **Fine-tuning is never served.** No serving engine trains. It is a batch job.
- **Blackfish** (CITED, S13) is a launcher around the above: it keeps a profile for each
  cluster, caches Apptainer images and models there, submits a job that runs vLLM, waits, and
  opens an SSH forward. It is MIT-licensed, from Princeton, a beta (v1.0.0b2), about a hundred
  open issues. It does inference and batch jobs; no fine-tuning was found. Services started
  from its interface have no authentication (its #534), and its templates rely on vLLM
  listening on every interface (its #537). It needs Python 3.12 and its own server process
  beside ours.
- **PyTorch on Apple silicon** is real and improving (PyTorch 2.14, September 2026, added native
  linear algebra there), but for generating text it is reported several times slower than MLX,
  and the whole model must fit in memory (CITED, S17). PyTorch in the Mac bundle buys *the same
  code on Mac and Linux*, not speed.

### One default for each kind of work

| Kind of work | On the Mac | On Linux with a GPU | Why |
|---|---|---|---|
| **Watched work**: trying a language or vision model on a page, chat | MLX, as today | **vLLM, as a session**, reached as a provider row | the one case with a person waiting; a server is right; adapters load while it runs |
| **Batch reading with a vision model** over a collection | MLX, as today (slow for thousands of pages; that is why it is sent away) | **vLLM inside the job's own process**, no web server; large work cut into array pieces | highest throughput, fewest parts; one start-up for each piece |
| **Batch Kraken** (finding lines, reading) | Kraken as today | **Kraken in the job's own process**, array pieces | the only shape Kraken has |
| **Layout detection** | in process (a later slice on the Mac) | **in the job's own process** | nothing for a server to share |
| **Fine-tuning Kraken** | not proposed (upstream support on Apple silicon UNVERIFIED) | **`ketos train` / `ketos segtrain` as a job** | batch by nature |
| **Fine-tuning a language or vision model** | small runs natively through MLX (a later slice) | **`trl` + `peft` as a job**; LoRA by default, QLoRA when memory is short | batch by nature; one 40 GB GPU is enough for 8B |
| A Linux machine with **no GPU** | | llama.cpp for language models; Kraken on CPU | the honest fallback; the row says "No GPU" |

**Blackfish: learn, do not use, do not wrap.** What it solves, we need: a cache of images and
models on the cluster, submit-then-forward, batch work that resumes. We take those ideas; they
are in `targets-and-connection.md` and below. We do not depend on it because: it would be a
second server, a second job runner and a second list of clusters beside ours, which is the
maintainer's standing worry made real; it covers inference only, and we need fine-tuning and
our own workflows; it is a beta; and two of its open issues run against Fichero's transport
rules. Its licence would allow any of the three choices. Issue #31 can close with this finding.

**All of it behind the one provider list.** A workflow step names a job ("read this line") and
the cascade resolves it to a card (`source.resolve.one-cascade`, #4949). A card says which
engines can run it. On the Mac that resolves to MLX; in the Linux image, to vLLM; for Kraken,
to Kraken on both. The workflow does not change when it is sent away. One new kind of provider
row, `vllm`, is added as a peer of `omlx`. Nothing else about providers is new.

## The design (proposed)

### One runner

The image's "run a package" mode (`compute.image.run-a-package-mode`) runs the **same workflow
code** the Mac runs, over the package's inputs, with providers resolved as above. There is no
`runner/run_task.py`. A training job runs a training recipe through the same entry point.

### Job kinds

| Kind | Input | Output | Array? |
|---|---|---|---|
| `workflow` | a workflow and the selected sources' objects | new passes and readings | yes: one piece for each shard of sources |
| `train-kraken-recognition` · `train-kraken-segmentation` | a training set (#4947) and a base model card, or none | a `.mlmodel`, its training log, scores on the held-out part | no |
| `train-lora` | a training set, a base model card, a recipe | an adapter, its log, scores; optionally a merged model | no |
| `session` | a base model card, adapter cards | a provider row while it lasts | no |

A **shard** is a fixed number of sources, not one source: one process start (and, with vLLM,
one three-minute warm-up) for each page would waste the allocation.

### One state machine

`preparing` → `waiting-for-yes` → `sending` → `staging-models` → `submitted` → `queued` →
`running` → `finished-there` → `fetching` → `landing` → `done`.

Side states: `waiting-for-sign-in` (the cluster connection dropped; the job there is
unaffected), `failed` (with a reason from a fixed list and the far side's last lines of
output), `cancelled`, `done-with-problems` (landed, with lines set aside or pieces failed).

This is `RunStatus` with the steps before and after the far side made visible. Slurm's states
fill `queued` and `running` through the existing mapping. A job is `done` only when landed.

### Surviving a time limit

A cluster ends a job at its time limit. Training that takes longer than one limit must carry
on from where it stopped. The pattern is standard (CITED, S18): the job asks Slurm for a signal
some minutes before the limit and for a re-queue; on the signal the trainer saves a checkpoint;
the re-queued job, which keeps its job id, finds the checkpoint and carries on. Workflow pieces
do not need this: a piece that was cut short is simply re-sent, which the sparse re-submit
already supports.

### A model coming back

- **Kraken**: the `.mlmodel` lands as a model file and a card. Kraken on the Mac uses it
  directly. `_SEGMENT_SCRIPT` today always uses Kraken's built-in line finder
  (INFERRED from the fine-tuning plan's reading of `kraken_runtime.py`; to be VERIFIED when the
  slice is cut), so using a trained *segmentation* model needs that one small change.
- **An adapter** (tens to hundreds of megabytes) always comes back. On Linux it is used as it
  is, by vLLM, beside its base model.
- **For MLX on the Mac**, the documented route is: merge the adapter into the base model where
  it was trained; bring the merged model home (about 16 GB for an 8B model at 16 bits, by the
  resumable transfer); convert and quantise it on the Mac with `mlx_lm.convert`, which only
  runs on Apple silicon (CITED, S19). Whether MLX can load a PyTorch adapter without merging is
  UNVERIFIED, so this set assumes it cannot. **This route is called nowhere in Fichero today,
  so it is its own slice, with its own test, and is not promised until that test is green.**
- Every model that comes back is **scored at once** against the collection's ground truth
  (`source.train.measured`, #4947) and its card names the training set it came from
  (`source.train.model-lineage`). A model whose scores are worse than its base is shown as
  worse, not hidden.

### Publishing

Publishing is the exporter's work and the model-card spec's; this set asks for it and states
what a compute job adds. The field has two homes, and they serve different things (CITED, S14):

- **Zenodo and the HTR-United catalogue** are where palaeographers publish Kraken models and
  transcription ground truth. A deposit gets a citable DOI. Kraken has its own publish command
  and metadata scheme for it.
- **The Hugging Face Hub** suits adapters, merged models and datasets. It offers private
  repositories (100 GB free), **gated** repositories where each request is approved by a named
  person and can be asked custom questions, fine-grained tokens limited to chosen repositories,
  resumable uploads, and Parquet datasets that its viewer reads directly.

What publishing must ask first, every time, whatever was agreed for sending:

1. Who may get this: *only me* (private), *people I approve* (gated), *anyone* (public).
   **Private is the default.**
2. For a dataset or a model trained on the collection: the community question of
   `transfer-and-results.md`, asked **again**, in its publishing form, because a model can
   carry what it was trained on.
3. The licence, from the card or the training set's own description.
4. One sentence, before the first upload to a given place: **taking something down afterwards
   is slow and may be incomplete.** On the Hub it takes several steps, storage is freed over
   about a day and a half, and anyone who already fetched it keeps it (CITED, S14).

The default for anything that may be community-held is *restricted until agreed*, not *open
until someone objects*.

## Behaviors

All untagged and unbuilt unless stated.

### Jobs

- `compute.job.choose-where` — wherever a workflow can be run, the person can choose a target
  from those that are green and able to run it; the default is this Mac. The choice can be
  saved as a collection's default only after a yes for that collection and target
  (`compute.leave.yes-is-recorded-and-scoped`). *Data:* `capabilities` of each target against
  the workflow's model cards. *Test:* a workflow needing an MLX-only model offers only this Mac,
  and says why the others are absent.
- `compute.job.one-runner` — a `workflow` job runs the same workflow code, with the same step
  semantics, as a run on the Mac. No separate runner exists. *Existing data:* the default
  `runner_command` in `build_remote_run_spec` (`remote_jobs.py:435-442`) is replaced by the
  image's "run a package" command. *Test:* the same three-page workflow on this Mac and in the
  cpu image yields identical readings.
- `compute.job.one-state-machine` — every job, on every target, moves through the states above
  and no others; each change is stored and broadcast. *Data:* a `compute_jobs` table: job id,
  kind, collection id, target id, person, package manifest hash, state, state history, far-side
  ids, counts, reason. *Existing data:* none. *Test:* pure transitions; illegal ones raise.
- `compute.job.done-means-landed` — see `compute.land.completed-means-landed`.
- `compute.job.array-by-shard` — a `workflow` job over many sources is one Slurm array job, one
  piece for each shard of a fixed number of sources; the number is a setting on the job with a
  default that amortises start-up. Built as a pure rule for one piece for each *file*
  (VERIFIED `api/routes/ai/hpc.py:298-301`); this changes the unit to a shard. *Test:* 1,000
  sources at 50 to a shard yields `--array=0-19`.
- `compute.job.sparse-resubmit` — when some pieces fail, "Send the failed pieces again" submits
  only those indices. Built as a pure rule (VERIFIED `remote_jobs.py:310-344`). *Test:* fixture:
  pieces 3 and 7 of 10 fail; the re-submit names `3,7`; the other eight are not re-run and
  their results are landed once.
- `compute.job.live-submit` — `SshCliSubmitter`'s `submit`, `poll` and `cancel` are
  implemented over the in-process SSH connection, and the `enabled` flag goes away: the guard
  against accidental submission is now the consent sheet and the owner role, not a constant.
  *Existing data:* `DryRunSubmitter` stays as the test fake; the dry-run route stays as "show
  me what will run". *Test:* fixture: submit returns the scheduler's job id; poll follows it to
  COMPLETED; cancel ends it.
- `compute.job.poll-is-gentle` — polling a cluster is one `sacct` call for all of a person's
  open jobs on that cluster, no more often than a stated interval (default 60 seconds), and
  stops when none are open. *Test:* three open jobs produce one call for each interval on the
  fixture's log.
- `compute.job.queued-says-so` — a job waiting in a cluster's queue reads "Queued on *name*",
  with the scheduler's estimated start if it gives one; it never reads "running". *Data:* the
  existing `QUEUED_SLURM_STATES` (VERIFIED `remote_jobs.py:267`). *Test:* pure.
- `compute.job.fails-with-a-reason` — a failed job carries a reason from a fixed list (*out of
  time*, *out of memory*, *node failed*, *a model was missing*, *the step refused: …*,
  *cancelled by the cluster*) and the last lines of the far side's output, fetched before the
  job folder is cleaned. *Data:* Slurm's state (`TIMEOUT`, `OUT_OF_MEMORY`, `NODE_FAIL`…;
  VERIFIED mapping `:246-263`) and the package mode's exit record. *Test:* one for each reason.
- `compute.job.cancel-everywhere` — cancelling a job stops sending, cancels it on the target,
  fetches nothing more, cleans the far side, and lands nothing that was not already landed.
  *Test:* cancel in each state.
- `compute.job.survives-the-app-quitting` — a job on a target carries on while the Mac sleeps
  or Fichero is closed; on next launch the state is caught up by one poll, and fetching and
  landing resume. *Test:* stop the server in `running`; restart; the job reaches `done`.
- `compute.job.resources-from-the-card` — the GPU, memory and time a job asks for come from the
  model cards it uses and its size, shown and changeable before sending; they are never silent
  constants. On Alliance clusters the GPU is asked for by its model name (CITED, S7). *Data:*
  `SlurmJobConfig` (VERIFIED `remote_jobs.py:28-36`), filled from cards. *Test:* an 8B LoRA
  recipe proposes one GPU of at least 40 GB.
- `compute.job.costs-shown-where-known` — for Hugging Face Jobs, the price for each hour of the
  chosen hardware is shown before sending, read from its API, and a time limit is always set
  explicitly because the service's default is 30 minutes (CITED, S12). *Test:* recorded API.
- `compute.job.everywhere` — jobs can be listed, started, watched and cancelled from the app,
  MCP and the command line, with one exception: only a person in the app can say yes
  (`transfer-and-results.md`). *Test:* cross-surface invariant.

### Engines

- `compute.engine.vllm-is-a-provider-row` — `vllm` is a provider kind, a peer of `omlx`, in the
  one provider list; it is *available* only where a CUDA GPU is. *Routed:* its row's look is
  `ai/ai-settings.md`'s. *Test:* on the Mac and the cpu image it reads unavailable with the
  reason.
- `compute.engine.batch-runs-in-process` — inside a `workflow` job, a language or vision model
  step runs through vLLM's offline mode in the job's own process: no port is opened, and the
  engine is started once for the piece, not once for a page. *Test:* the job's process list and
  sockets, read during the fixture run on a GPU machine (a named-machine test, see
  `compute.image.gpu-path-is-tested-somewhere-named`).
- `compute.engine.kraken-and-layout-in-process` — Kraken and layout models are loaded directly
  in the job's process, on the GPU when there is one. *Test:* cpu image: Kraken reads one page.
- `compute.engine.same-card-resolves-by-platform` — a card names the engines that can run it;
  the same workflow resolves to MLX on the Mac and vLLM in the gpu image with no change to the
  workflow. A card no engine on the target can run refuses the job before sending.
  *Routed:* the card's fields are #4948's. *Test:* resolution table, pure.
- `compute.engine.session-adds-and-removes-a-row` — a `session` job that reaches *ready* adds
  one provider row of kind `vllm`, named for the target and the model, addressed at the local
  end of the forward; it is removed when the session ends. It is not saved as a setting.
  *Test:* fixture with a stub OpenAI-style server in place of vLLM.
- `compute.engine.session-serves-adapters` — a session can serve its base model with any of the
  person's adapters for that base, chosen as models of that row. *Test:* named-machine.
- `compute.engine.session-passes-the-gate` — every request to a session's row passes the one
  egress gate like any model that is not on this Mac, so a collection marked "may not leave"
  cannot use it. *Test:* such a collection is refused with the collection's rule.
- `compute.engine.no-gpu-fallback-is-named` — on a Linux machine with no GPU, language models
  run through llama.cpp and the row and every result say so; nothing silently runs on a CPU
  when a GPU was asked for. *Test:* a job asking for a GPU on the cpu image is refused.

### Fine-tuning

- `compute.tune.input-is-a-training-set` — a training job's only data input is a training set
  as `source.train.*` defines it, made by that spec's code; this slice adds no second way to
  cut line pictures. *Routed:* #4947. *Test:* a training package holds exactly the training
  set's objects and its description.
- `compute.tune.kraken-recognition` — a `train-kraken-recognition` job runs `ketos train` on the
  training set, from a base model card or from nothing, and returns the best model, its log,
  and character and word error rates on the held-out part. *Data:* the training set's split
  (`source.train.split-by-manuscript`). *Test:* a tiny set in the cpu image for two epochs
  yields a loadable `.mlmodel`.
- `compute.tune.kraken-segmentation` — the same with `ketos segtrain`, and Kraken's line finder
  on the Mac can then be told to use that model rather than its built-in one. *Existing data:*
  pages segmented before are untouched; the trained model makes new passes. *Test:* as above,
  plus one page segmented on the Mac with the returned model.
- `compute.tune.lora` — a `train-lora` job fine-tunes a base model named by card with LoRA
  (QLoRA when the card and the target's memory call for it), from a recipe file that names
  rank, learning rate, epochs and the prompt form, and returns the adapter, its log and scores.
  A recipe is a shareable file in the sense of `source.recipe.is-a-file` (#4950). *Test:* a
  tiny model and a tiny set, in automation on CPU for a few steps, yields an adapter that
  loads; the full path is a named-machine test.
- `compute.tune.survives-the-time-limit` — a training job longer than its time limit saves a
  checkpoint on the scheduler's warning signal, is re-queued under the same job id, and resumes
  from the checkpoint; the job's row reads "running (part 2)". *Test:* fixture with a
  two-minute limit and a trainer stub: the run completes across two parts with no repeated
  steps. Whether `ketos train` resumes by itself is UNVERIFIED (S18) and is checked when the
  slice is cut.
- `compute.tune.model-comes-back-as-a-card` — a returned model lands as a model file and a card
  in the one catalogue, naming its base, its training set, the job, the target, the recipe and
  its scores (`source.train.model-lineage`). It is a row under its provider like any downloaded
  model (`source.find.download-is-a-provider-row`). *Test:* after landing, the catalogue lists
  it with those fields.
- `compute.tune.scored-against-your-own-pages` — on landing, the model is scored against the
  collection's ground truth beside its base model, and the card shows both. A model that is
  worse is shown as worse. *Routed:* the scoring is `source.train.measured`. *Test:* a
  deliberately bad model lands with a worse score displayed.
- `compute.tune.not-default-until-chosen` — a returned model is never made a collection's
  default by landing; the person chooses it (`source.find.try-before-default`). *Test:* defaults
  unchanged after landing.
- `compute.tune.adapter-always-returns` — a `train-lora` job always returns the adapter. A
  merged model is returned only when asked for, because it is as large as the base. *Test:*
  result package contents for both choices.
- `compute.tune.convert-for-mlx` — a merged model fetched to the Mac can be converted and
  quantised for MLX, and then appears as a model of the MLX row. The convert step runs on the
  Mac only. **Its own slice; not promised until its test is green.** *Test:* a tiny merged
  model converts, loads in the MLX runtime, and answers one prompt.
- `compute.tune.licence-carries` — a fine-tuned model's card carries its base model's licence
  and licence class, and the training set's; publishing reads them. *Routed:*
  `source.model.licence-class`. *Test:* an adapter on a base with a bespoke licence is marked
  so.
- `compute.tune.bootstrapped-data-is-marked` — if a training set includes readings made by a
  model rather than checked by a person, which `source.train.human-checked-by-default`
  allows only by a deliberate choice, the job's record and the card say how many, so a model
  taught by another model is never mistaken for one taught by a person. *Test:* counts on the
  card.

### Publishing (offered to the exporter and model-card specs)

- `compute.publish.is-separate-and-asked-again` — publishing a dataset, adapter, model or card
  is always its own act with its own sheet (the four things above); a yes to *sending* never
  covers it. *Test:* a collection with a recorded send yes still gets the publish sheet.
- `compute.publish.private-by-default` — a new repository is private unless the person chooses
  gated or public. *Test:* the create call's visibility.
- `compute.publish.gated-is-offered` — "people I approve" makes a gated repository with manual
  approval, and requests can be seen and answered from Fichero. *Test:* recorded API.
- `compute.publish.builds-on-the-exporter` — a dataset is published by uploading the exporter's
  Hugging Face bundle (`export.huggingface-dataset-ready-bundle`); no second emitter exists.
  *Test:* a guardrail: nothing under `compute/` writes Parquet.
- `compute.publish.card-is-the-card` — the model card published is the catalogue's card
  rendered in the Hub's form, with base model, training set, licence and the adapter library
  named as the Hub expects (CITED, S14); no second card is written by hand. *Test:* round trip
  of the rendered fields.
- `compute.publish.zenodo-for-kraken` — a Kraken model or a ground-truth set can instead be
  deposited on Zenodo, with the metadata Kraken's own repository expects, and gets a DOI that
  the card then carries. *Test:* against Zenodo's sandbox.
- `compute.publish.is-audited-and-says-what-cannot-be-undone` — a publish is an audited action
  recording what, where, visibility and the answers given; "unpublish" is offered and described
  honestly as slow and possibly incomplete. *Test:* the audit record; the wording is present.
- `compute.publish.token-is-narrow` — the Hugging Face token Fichero asks for is fine-grained,
  limited to the person's own repositories, and lives in the one key store. *Test:* a broad
  token is accepted with a warning naming what is wider than needed.

## Accessibility identifiers

- `compute.run.where` — the target chooser where a workflow is run; `compute.run.where.<id>`
- `compute.jobs.list`, `compute.job.row.<id>`, `compute.job.<id>.state`
- `compute.job.<id>.cancel`, `.resend-failed`, `.show-output`, `.undo`
- `compute.tune.start`, `compute.tune.recipe`, `compute.tune.base-model`
- `compute.publish.start`, `compute.publish.visibility.<private|gated|public>`

## Test matrix

| Leg | This slice? | Pins | File |
|-----|-------------|------|------|
| Pure rule (Swift) | y | a job row's wording for each state; which targets are offered for a workflow | a new `compute` group under the Swift unit tests |
| Availability (Swift) | y | "where" is reachable wherever a workflow is run; jobs list reachable | same |
| Backend (pytest) | y | state machine; shards and array lines; sparse re-submit; reasons; resolution by platform; resources from cards; this-Mac job loop end to end | `fichero-server/tests/unit/workflows/`, marker `remote_compute` |
| Fixture (continuous integration) | y | live submit, poll, cancel; gentle polling; time-limit survival; session row with a stub server | `.github/workflows/` with the Slurm-and-SSH containers |
| Image (continuous integration) | y | Kraken training for two epochs on CPU; a few LoRA steps on a tiny model on CPU | same |
| Named machine (a person, recorded) | y | vLLM in process; a real 3B LoRA; adapters in a session; MLX convert | recorded in the release record, never claimed by automation |
| MCP / CLI | y | jobs everywhere; an agent cannot say yes | `fichero-mcp/tests/`, `fichero-cli/tests/` |
| Click-around (Mac) | y | run three pages on the local container; see the pass; undo the job | `fichero/Tests/UI/` |

## Open questions

1. **One default engine for each kind of work, as in the table.** *Proposal: agreed.*
2. **Blackfish: learn, not use.** *Proposal: agreed; close #31 with the finding.*
3. **Shard size.** *Proposal: 50 sources by default, a setting on the job; to be re-set from a
   measurement on the maintainer's own pages.*
4. **Base model for the first language or vision fine-tune.** Qwen's 3B-to-8B models are
   Apache-2.0 and are the cleanest licence; Llama's and older Gemma's are bespoke (CITED, S8).
   *Proposal: Qwen-class by default; the choice is a card, so nothing is hard-wired.*
5. **Does the merged model come home by default?** It is about 16 GB for an 8B model.
   *Proposal: no. The adapter always; the merged model only when the person wants it on the
   Mac.*
6. **Publishing lives in the exporter and model-card specs.** *Proposal: move the eight
   `compute.publish.*` behaviours there once their owners agree, keeping only
   `compute.publish.is-separate-and-asked-again` here.*
7. **Distilling a small palaeography vision model (#4642)** is a customer of this slice, not
   part of it. *Proposal: it stays its own design issue and names `train-lora` as its means.*
