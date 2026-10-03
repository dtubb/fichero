# Remote Compute — Jobs, engines, fine-tuning and publishing — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — "Sending work away, and training your own model": choosing where a run
> happens; what queued, running and finished mean on a cluster; cancelling; training Kraken on
> pages you corrected, and seeing whether it helped; training a language or vision model; what
> comes back to your Mac; publishing a model or a dataset, and what cannot be taken back.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-09-20; revised
> 2026-10-03 against the maintainer's rulings (`remote-compute.md`, "Ruled 2026-10-03";
> `REVIEW-2026-10-03.md`).** A slice of the compute set: read `remote-compute.md` first. Every
> behaviour is **[GAP]** with its issue; none is built. **VERIFIED / INFERRED** for our code; **CITED / UNVERIFIED** for
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
- **Kraken on the Mac** now runs inside the engine's own process, loaded once and used one
  operation at a time (VERIFIED `llm/kraken_runtime.py:512-519`; the subprocess of the first pass
  is gone), and fetches readers by DOI from its repository (#4951). It only reads; it is never
  trained (`source/formats-and-training.md:15`).
- **The step is registered, not built**: `train-a-model` (line readings and lines in, a model card
  out) is in the job registry (VERIFIED `recipes/jobs.py:143-146`). Its description still says it
  runs "on a cluster, a GPU service or a large Mac", which the 2026-10-03 ruling corrects: Kraken
  and YOLO train on a 16 GB Mac.
- **The one CER is reachable** through `POST /api/documents/{id}/readings/compare`
  (`workflows/transcription_accuracy.py`; VERIFIED `api/routes/document/compare_readings.py:88`),
  labelled `agreement` unless a person checked the reference.
- **No training code, no YOLO detector, no vLLM, no Hugging Face Jobs call, and no call to MLX's
  convert step** anywhere in the engine (VERIFIED by search, 2026-10-03).
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
| **Batch reading with a vision model** over a project | MLX, as today (slow for thousands of pages; that is why it is sent away) | **vLLM inside the job's own process**, no web server; large work cut into array pieces | highest throughput, fewest parts; one start-up for each piece |
| **Batch Kraken** (finding lines, reading) | Kraken as today | **Kraken in the job's own process**, array pieces | the only shape Kraken has |
| **Layout detection** | in process (`prep.yolo-detectors-run-and-train`) | **in the job's own process** | nothing for a server to share |
| **Fine-tuning Kraken** | **in the engine's process, in the local ML lane, on a 16 GB Mac** (ruled 2026-10-03; Apple's GPU if Kraken allows it, else the CPU; #5397) | **`ketos train` / `ketos segtrain` as a job**, Hugging Face Jobs first, then a cluster | batch by nature |
| **Fine-tuning a YOLO detector** | **in the engine's process, in the local ML lane, on a 16 GB Mac** (#5397) | the same trainer as a job | a few dozen to a few hundred boxed pages |
| **Fine-tuning a language or vision model** (for example Qwen2.5-VL 3B with LoRA) | runs, quantised, on a 16 GB Mac; small training runs through MLX are a later slice | **`trl` + `peft` as a job**, Hugging Face Jobs first; LoRA by default, QLoRA when memory is short | batch by nature; one 40 GB GPU is enough for 8B |
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
| `train-layout` | a training set of checked boxes (YOLO labels) and a base detector card | a detector, its log, precision and recall per region kind on the held-out part | no |
| `train-lora` | a training set, a base model card, a recipe | an adapter, its log, scores; optionally a merged model | no |
| `session` | a base model card, adapter cards | a provider row while it lasts | no |

A **shard** is a fixed number of sources, not one source: one process start (and, with vLLM,
one three-minute warm-up) for each page would waste the allocation.

### One state machine, inside the one job model

A compute job is **a row in the one `jobs` table** of `ui/activity-and-automatic-work.md`
(its question 9, ruled 2026-10-01): `kind` is what it does (`workflow`, `train-a-model`), its
target is named, a job sent away runs in lane `remote`, and a training job on this Mac runs in
the local ML lane. There is no `compute_jobs` table. The phases below are that row's `state`
(`waiting`, `running`, `done`, `failed`, `cancelled`) with its `waiting_reason` and `progress`
saying which phase, in words:

`preparing` → `waiting-for-yes` → `sending` → `staging-models` → `submitted` → `queued` →
`running` → `finished-there` → `fetching` → `landing` → `done`.

Side phases: `waiting-for-sign-in` (the cluster connection dropped; the job there is
unaffected), `failed` (with a reason from a fixed list and the far side's last lines of
output), `cancelled`, `done-with-problems` (landed, with lines set aside or pieces failed).

Slurm's states fill `queued` and `running` through the existing mapping. Array pieces are child
jobs. A job is `done` only when landed. Global pause stops new sends and polling and never
cancels a job already running on a cluster or on Hugging Face (that costs allocation or money).

### Controlling Slurm

Fichero runs the cluster's own commands for the person, over the one in-process SSH connection
to the login node (`compute.connect.ssh-in-process`), with the person's own account:

| Step of the job | Command | What Fichero records on the job row |
|---|---|---|
| submit | `sbatch --parsable` (an array for many shards) | the scheduler's job id; phase `submitted` |
| watch | `squeue` while queued (with `--start` for the estimate), `sacct` for every open job | phase `queued` or `running`; the estimated start; on the end, state and exit code |
| cancel | `scancel <id>` (or the listed pieces) | phase `cancelled`, once the scheduler confirms it |
| fetch | the SSH carrier (`compute.transfer.ssh-carrier`) from the job's folder | phases `fetching`, `landing`, `done` |

The commands are built by the existing pure builders (`remote_jobs.py`) and shown on request as
"what will run". There is no second way: no shelling out to the system's `ssh`, no script the
person runs by hand, no cluster-side daemon.

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
- Every model that comes back is **scored at once** against the project's ground truth
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
2. For a dataset or a model trained on the project: the community question of
   `transfer-and-results.md`, asked **again**, in its publishing form, because a model can
   carry what it was trained on.
3. The licence, from the card or the training set's own description.
4. One sentence, before the first upload to a given place: **taking something down afterwards
   is slow and may be incomplete.** On the Hub it takes several steps, storage is freed over
   about a day and a half, and anyone who already fetched it keeps it (CITED, S14).

The default for anything that may be community-held is *restricted until agreed*, not *open
until someone objects*.

## Behaviors

All [GAP]: designed, not built.

### Jobs

- `compute.job.choose-where` — **[GAP]** (#5240) wherever a workflow can be run, the person can choose a target
  from those that are green and able to run it; the default is this Mac. The choice can be
  saved as a project's default only after a yes for that project and target
  (`compute.leave.yes-is-recorded-and-scoped`). *Data:* `capabilities` of each target against
  the workflow's model cards. *Test:* a workflow needing an MLX-only model offers only this Mac,
  and says why the others are absent.
- `compute.job.one-runner` — **[GAP]** (#5240) a `workflow` job runs the same workflow code, with the same step
  semantics, as a run on the Mac. No separate runner exists. *Existing data:* the default
  `runner_command` in `build_remote_run_spec` (`remote_jobs.py:435-442`) is replaced by the
  image's "run a package" command. *Test:* the same three-page workflow on this Mac and in the
  cpu image yields identical readings.
- `compute.job.one-state-machine` — **[PARTIAL]** (#5240, #5353) *Built for training (#5398): a `train-a-model` job is a row in the one `jobs` table, lane `remote`, with `target` and `detail` (request, far-side id, phase history) columns; workflow jobs and `job.updated` broadcast on every phase are not built.* every compute job, on every target, is a row in
  the one `jobs` table (`activity.one-job-model`), moves through the phases above and no others,
  and each change is stored and broadcast as `job.updated`. *Data:* the `jobs` row, plus what a
  remote job adds to it: target id, package manifest hash, far-side ids, phase history. No
  `compute_jobs` table. *Existing data:* none. *Test:* pure transitions; illegal ones raise; a
  remote job appears in `/api/jobs` beside local ones.
- `compute.job.done-means-landed` — **[GAP]** (#5240) see `compute.land.completed-means-landed`.
- `compute.job.array-by-shard` — **[GAP]** (#5240) a `workflow` job over many sources is one Slurm array job, one
  piece for each shard of a fixed number of sources; the number is a setting on the job with a
  default that amortises start-up. Built as a pure rule for one piece for each *file*
  (VERIFIED `api/routes/ai/hpc.py:298-301`); this changes the unit to a shard. *Test:* 1,000
  sources at 50 to a shard yields `--array=0-19`.
- `compute.job.sparse-resubmit` — **[GAP]** (#5240) when some pieces fail, "Send the failed pieces again" submits
  only those indices. Built as a pure rule (VERIFIED `remote_jobs.py:310-344`). *Test:* fixture:
  pieces 3 and 7 of 10 fail; the re-submit names `3,7`; the other eight are not re-run and
  their results are landed once.
- `compute.job.live-submit` — **[GAP]** (#5240) Fichero controls Slurm itself: `SshCliSubmitter`'s `submit`
  (`sbatch`), `poll` (`squeue`, `sacct`), `cancel` (`scancel`) and the fetch of results are
  implemented over the in-process SSH connection with the person's own account, each a step of a
  row in the one job table (`compute.job.one-state-machine`), and the `enabled` flag goes away: the guard
  against accidental submission is now the consent sheet and the owner role, not a constant.
  *Existing data:* `DryRunSubmitter` stays as the test fake; the dry-run route stays as "show
  me what will run". *Test:* fixture: submit returns the scheduler's job id; poll follows it to
  COMPLETED; cancel ends it.
- `compute.job.poll-is-gentle` — **[GAP]** (#5240) polling a cluster is one `sacct` call for all of a person's
  open jobs on that cluster, no more often than a stated interval (default 60 seconds), and
  stops when none are open. *Test:* three open jobs produce one call for each interval on the
  fixture's log.
- `compute.job.queued-says-so` — **[GAP]** (#5240) a job waiting in a cluster's queue reads "Queued on *name*",
  with the scheduler's estimated start (`squeue --start`) if it gives one; it never reads "running". *Data:* the
  existing `QUEUED_SLURM_STATES` (VERIFIED `remote_jobs.py:267`). *Test:* pure.
- `compute.job.fails-with-a-reason` — **[GAP]** (#5240) a failed job carries a reason from a fixed list (*out of
  time*, *out of memory*, *node failed*, *a model was missing*, *the step refused: …*,
  *cancelled by the cluster*) and the last lines of the far side's output, fetched before the
  job folder is cleaned. *Data:* Slurm's state (`TIMEOUT`, `OUT_OF_MEMORY`, `NODE_FAIL`…;
  VERIFIED mapping `:246-263`) and the package mode's exit record. *Test:* one for each reason.
- `compute.job.cancel-everywhere` — **[GAP]** (#5240) cancelling a job stops sending, cancels it on the target,
  fetches nothing more, cleans the far side, and lands nothing that was not already landed.
  *Test:* cancel in each state.
- `compute.job.survives-the-app-quitting` — **[GAP]** (#5240) a job on a target carries on while the Mac sleeps
  or Fichero is closed; on next launch the state is caught up by one poll, and fetching and
  landing resume. *Test:* stop the server in `running`; restart; the job reaches `done`.
- `compute.job.resources-from-the-card` — **[GAP]** (#5240) the GPU, memory and time a job asks for come from the
  model cards it uses and its size, shown and changeable before sending; they are never silent
  constants. On Alliance clusters the GPU is asked for by its model name (CITED, S7). *Data:*
  `SlurmJobConfig` (VERIFIED `remote_jobs.py:28-36`), filled from cards. *Test:* an 8B LoRA
  recipe proposes one GPU of at least 40 GB.
- `compute.job.costs-shown-where-known` — **[PARTIAL]** (#5240) *Built for training (#5398): the price per hour is read from `list_jobs_hardware` and returned when the job starts, and the time limit is always sent; no app sheet shows it yet.* for Hugging Face Jobs, the price for each hour of the
  chosen hardware is shown before sending, read from its API, and a time limit is always set
  explicitly because the service's default is 30 minutes (CITED, S12). *Test:* recorded API.
- `compute.job.everywhere` — **[GAP]** (#5240) jobs can be listed, started, watched and cancelled from the app,
  MCP and the command line, with one exception: only a person in the app can say yes
  (`transfer-and-results.md`). *Test:* cross-surface invariant.

### Engines

*Deferred* (2026-10-03): vLLM, sessions and batch vision-model jobs come after the first
training path (Kraken and YOLO on Hugging Face Jobs, this Mac, then ACENET). Nothing in that path
needs them.

- `compute.engine.vllm-is-a-provider-row` — **[GAP]** (#5240) `vllm` is a provider kind, a peer of `omlx`, in the
  one provider list; it is *available* only where a CUDA GPU is. *Routed:* its row's look is
  `ai/ai-settings.md`'s. *Test:* on the Mac and the cpu image it reads unavailable with the
  reason.
- `compute.engine.batch-runs-in-process` — **[GAP]** (#5240) inside a `workflow` job, a language or vision model
  step runs through vLLM's offline mode in the job's own process: no port is opened, and the
  engine is started once for the piece, not once for a page. *Test:* the job's process list and
  sockets, read during the fixture run on a GPU machine (a named-machine test, see
  `compute.image.gpu-path-is-tested-somewhere-named`).
- `compute.engine.kraken-and-layout-in-process` — **[GAP]** (#5240) Kraken and layout models are loaded directly
  in the job's process, on the GPU when there is one. *Test:* cpu image: Kraken reads one page.
- `compute.engine.same-card-resolves-by-platform` — **[PARTIAL]** (#5240) *Built for trained vision models (#5398): a landed student's card names two builds, `mlx` (4-bit, this Mac) and `hf` (merged bf16 weights and adapter in the job's bucket, for transformers or vLLM on a Linux GPU); resolving a run to one by platform is not built.* a card names the engines that can run it;
  the same workflow resolves to MLX on the Mac and vLLM in the gpu image with no change to the
  workflow. A card no engine on the target can run refuses the job before sending.
  *Routed:* the card's fields are → #4948's. *Test:* resolution table, pure.
- `compute.engine.session-adds-and-removes-a-row` — **[GAP]** (#5240) a `session` job that reaches *ready* adds
  one provider row of kind `vllm`, named for the target and the model, addressed at the local
  end of the forward; it is removed when the session ends. It is not saved as a setting.
  *Test:* fixture with a stub OpenAI-style server in place of vLLM.
- `compute.engine.session-serves-adapters` — **[GAP]** (#5240) a session can serve its base model with any of the
  person's adapters for that base, chosen as models of that row. *Test:* named-machine.
- `compute.engine.session-passes-the-gate` — **[GAP]** (#5240) every request to a session's row passes the one
  egress gate like any model that is not on this Mac, so a project marked "may not leave"
  cannot use it. *Test:* such a project is refused with the project's rule.
- `compute.engine.no-gpu-fallback-is-named` — **[GAP]** (#5240) on a Linux machine with no GPU, language models
  run through llama.cpp and the row and every result say so; nothing silently runs on a CPU
  when a GPU was asked for. *Test:* a job asking for a GPU on the cpu image is refused.

### Fine-tuning

- `compute.tune.one-trainer-three-places` — **[GAP]** (#5119, #5397) a `train-a-model` job runs one engine
  code path wherever it runs: in the engine's process on this Mac, and in the image's "run a
  package" mode on Hugging Face Jobs or a cluster. The same training set gives a model, a log and
  a held-out score of the same form in all three. *Test:* a tiny Kraken set for two epochs on
  this Mac's CPU and in the cpu image yields loadable models and scores of the same shape.
- `compute.tune.where-cheapest-first` — **[GAP]** (#5119, #4950) a train step runs on this Mac when its card's
  measured memory fits this Mac beside the resident embedder; otherwise on the project's bound
  `gpu-service` target, then its `cluster` target (`source.recipe.runs-on-binds-to-a-target`). A
  costlier place is chosen only when the A/B evidence on the project's pages (error rate, cost,
  speed, carbon, trainability) is shown for it. *Test:* a Kraken recipe on a 16 GB Mac resolves to
  this Mac; a 3B LoRA recipe resolves to the bound Hugging Face target, with the reason.
- `compute.tune.proven-on-huggingface-first` — **[GAP]** (#5398) a training recipe is first run on Hugging Face
  Jobs and counts as proven when two runs reach the same held-out CER within a stated noise
  band; the proof (dates, image digest, hardware, CER) is recorded on the recipe before it is run
  on a cluster. *Test:* the recipe file carries the proof record; a cluster run of an unproven
  recipe is offered with "not yet proven on Hugging Face".
- `compute.tune.on-this-mac` — **[GAP]** (#5397) Kraken recognition, Kraken segmentation and a YOLO detector
  train on a 16 GB Mac in the local ML lane: the trainer holds the lane as one heavy model, no
  reader runs beside it unless both fit (`activity.lane.co-run-only-if-it-fits`), it runs at
  utility QoS with bounded threads, it waits on battery, heat, memory pressure and active use
  (`activity.throttle.power-heat-memory`), and pause resumes from its last checkpoint. *Test:* a
  tiny set trains under the lane with a fake memory-pressure signal: it waits, then resumes
  without repeating an epoch.
- `compute.tune.measured-on-16gb` — **[GAP]** (#5397) every training run records its peak memory and what it
  used (CPU, GPU, Neural Engine) on the job and on the resulting card, and every adopted model
  carries a measurement of reading on a 16 GB Mac (speed per page, peak memory). *Test:* the card
  of a trained model has those fields filled from the run, never typed by hand.
- `compute.tune.input-is-a-training-set` — **[PARTIAL]** (#5240) *Built for distillation (#5398): `training/kraken_set.py` writes the teacher's line passes as PAGE XML beside each photograph, held-out pages left out; the person-checked split of #4947 is not built.* a training job's only data input is a training set
  as `source.train.*` defines it, made by that spec's code; this slice adds no second way to
  cut line pictures. *Routed:* → #4947. *Test:* a training package holds exactly the training
  set's objects and its description.
- `compute.tune.kraken-recognition` — **[PARTIAL]** (#5240) *Built on Hugging Face Jobs (#5398): `ketos train -f page -q early` from a base reader card, best model returned; on this Mac and in the image, and held-out scores, not built.* a `train-kraken-recognition` job runs `ketos train` on the
  training set, from a base model card or from nothing, and returns the best model, its log,
  and character and word error rates on the held-out part. *Data:* the training set's split
  (`source.train.split-by-manuscript`). *Test:* a tiny set in the cpu image for two epochs
  yields a loadable `.mlmodel`.
- `compute.tune.kraken-segmentation` — **[GAP]** (#5240) the same with `ketos segtrain`, and Kraken's line finder
  on the Mac can then be told to use that model rather than its built-in one. *Existing data:*
  pages segmented before are untouched; the trained model makes new passes. *Test:* as above,
  plus one page segmented on the Mac with the returned model.
- `compute.tune.yolo-layout` — **[GAP]** (#5240, #5397) a `train-layout` job trains a YOLO-family detector
  for the page (`prep.yolo-detectors-run-and-train`), regions (by kind) or lines from a training
  set of the project's checked boxes or outlines (exported as YOLO, which Fichero already writes,
  `source.format.yolo-out`), on this Mac first (16 GB), on Hugging Face Jobs, or on a cluster; the trained detector comes back as a model card and is measured on held-out pages
  (precision and recall per region kind) before a recipe may use it. *Existing data:* earlier
  passes are untouched; the detector makes new passes. *Test:* a tiny set trains, returns, and
  finds boxes on one held-out page.
- `compute.tune.lora` — **[PARTIAL]** (#5240) *Built for a vision model on Hugging Face Jobs (#5398): `hf_vision_lora_train.py` (transformers + peft, bf16, loss on the answer alone) on line pairs cut by the line reader's own crop with its own instruction; rank and epochs on the request, not yet a recipe file; QLoRA and the CPU tiny-model test are not built.* a `train-lora` job fine-tunes a base model named by card with LoRA
  (QLoRA when the card and the target's memory call for it), from a recipe file that names
  rank, learning rate, epochs and the prompt form, and returns the adapter, its log and scores.
  A recipe is a shareable file in the sense of `source.recipe.is-a-file` (→ #4950). *Test:* a
  tiny model and a tiny set, in automation on CPU for a few steps, yields an adapter that
  loads; the full path is a named-machine test.
- `compute.tune.survives-the-time-limit` — **[GAP]** (#5240) a training job longer than its time limit saves a
  checkpoint on the scheduler's warning signal, is re-queued under the same job id, and resumes
  from the checkpoint; the job's row reads "running (part 2)". *Test:* fixture with a
  two-minute limit and a trainer stub: the run completes across two parts with no repeated
  steps. Whether `ketos train` resumes by itself is UNVERIFIED (S18) and is checked when the
  slice is cut.
- `compute.tune.model-comes-back-as-a-card` — **[PARTIAL]** (#5240) *Built for Kraken and for a vision model (#5398): `training/landing.py` lands `kraken-trained-<job>`, `training/mlx_landing.py` lands `fichero-trained/<name>`, each with a card (base, teacher, set, held-out pages, job, target, release) listed in its catalogue; scores on landing are not built.* a returned model lands as a model file and a card
  in the one catalogue, naming its base, its training set, the job, the target, the recipe and
  its scores (`source.train.model-lineage`). It is a row under its provider like any downloaded
  model (`source.find.download-is-a-provider-row`). *Test:* after landing, the catalogue lists
  it with those fields.
- `compute.tune.scored-against-your-own-pages` — **[GAP]** (#5240, #4947) on landing, the model is scored
  against the project's held-out ground truth beside its base model, and the card shows both. A
  reader's score is the one CER (`workflows/transcription_accuracy.py`, through
  `POST /api/documents/{id}/readings/compare`), named *CER* only where a person checked the
  reference and *agreement* otherwise; no second scorer is written. A detector's score is
  precision and recall per region kind, and the CER of reading the pages it prepared. A model
  that is worse is shown as worse. *Routed:* the scoring is `source.train.measured`. *Test:* a
  deliberately bad model lands with a worse score displayed; a reference that no person checked
  is labelled agreement.
- `compute.tune.not-default-until-chosen` — **[GAP]** (#5240) a returned model is never made a project's
  default by landing; the person chooses it (`source.find.try-before-default`). *Test:* defaults
  unchanged after landing.
- `compute.tune.adopted-by-the-recipe` — **[GAP]** (#5337, #4950) a trained model that beats the current step
  on the project's held-out checked pages enters the recipe as a **new card for that step**, in
  the project's next recipe version, offered to the person with the A/B table (error rate, cost,
  speed, carbon, trainability); a model that does not beat it is kept as a card and not offered.
  Training and adoption run by themselves only if the person chose automatic training in setup
  (`source.recipe.train-never-automatic`). *Test:* a better tiny model yields a proposed recipe
  version pinning its card; a worse one yields none.
- `compute.tune.adapter-always-returns` — **[PARTIAL]** (#5240) *Built (#5398): the adapter always returns and is kept beside the MLX model. The vision card also returns the merged model, because the MLX conversion needs it, and deletes it once converted; a choice to skip it is not built.* a `train-lora` job always returns the adapter. A
  merged model is returned only when asked for, because it is as large as the base. *Test:*
  result package contents for both choices.
- `compute.tune.convert-for-mlx` — **[PARTIAL]** (#5240) *Built, not yet run on a real model (#5398): `training/mlx_landing.py` runs `mlx_vlm.convert -q --q-bits 4` in the MLX runtime's Python on this Mac, on the local ML lane, and lands `fichero-trained/<name>` in the MLX store; the named-machine test (a merged model converts, loads and answers) is the maintainer's run.* a merged model fetched to the Mac can be converted and
  quantised for MLX, and then appears as a model of the MLX row. The convert step runs on the
  Mac only. **Its own slice; not promised until its test is green.** *Test:* a tiny merged
  model converts, loads in the MLX runtime, and answers one prompt.
- `compute.tune.licence-carries` — **[PARTIAL]** (#5240) *Built in part (#5398): the vision student's card carries its base's licence (`base_licence`, Apache-2.0 for Qwen2.5-VL 7B); the training set's licence and licence classes are not.* a fine-tuned model's card carries its base model's licence
  and licence class, and the training set's; publishing reads them. *Routed:*
  `source.model.licence-class`. *Test:* an adapter on a base with a bespoke licence is marked
  so.
- `compute.tune.bootstrapped-data-is-marked` — **[PARTIAL]** (#5240) *Built (#5398): the set's manifest and the reader's card count lines read by a model and lines checked by a person; no app view shows it yet.* if a training set includes readings made by a
  model rather than checked by a person, which `source.train.human-checked-by-default`
  allows only by a deliberate choice, the job's record and the card say how many, so a model
  taught by another model is never mistaken for one taught by a person. *Test:* counts on the
  card.

### Publishing (offered to the exporter and model-card specs)

- `compute.publish.good-models-released-by-fichero` — **[GAP]** (#5240) a model that cleared its project's bar,
  whose training data's rights and whose base model's licence allow it, can be released on
  Hugging Face as part of Fichero, with its card stating its data, hand, period, held-out CER and
  licence. Release is a person's act and is asked on its own (`compute.publish.is-separate-and-asked-again`).
  *Test:* a model whose project has no rights answer is refused release with that reason.

- `compute.publish.is-separate-and-asked-again` — **[GAP]** (#5240) publishing a dataset, adapter, model or card
  is always its own act with its own sheet (the four things above); a yes to *sending* never
  covers it. *Test:* a project with a recorded send yes still gets the publish sheet.
- `compute.publish.private-by-default` — **[GAP]** (#5240) a new repository is private unless the person chooses
  gated or public. *Test:* the create call's visibility.
- `compute.publish.gated-is-offered` — **[GAP]** (#5240) "people I approve" makes a gated repository with manual
  approval, and requests can be seen and answered from Fichero. *Test:* recorded API.
- `compute.publish.builds-on-the-exporter` — **[GAP]** (#5240) a dataset is published by uploading the exporter's
  Hugging Face bundle (`export.huggingface-dataset-ready-bundle`); no second emitter exists.
  *Test:* a guardrail: nothing under `compute/` writes Parquet.
- `compute.publish.card-is-the-card` — **[GAP]** (#5240) the model card published is the catalogue's card
  rendered in the Hub's form, with base model, training set, licence and the adapter library
  named as the Hub expects (CITED, S14); no second card is written by hand. *Test:* round trip
  of the rendered fields.
- `compute.publish.zenodo-for-kraken` — **[GAP]** (#5240) a Kraken model or a ground-truth set can instead be
  deposited on Zenodo, with the metadata Kraken's own repository expects, and gets a DOI that
  the card then carries. *Test:* against Zenodo's sandbox.
- `compute.publish.is-audited-and-says-what-cannot-be-undone` — **[GAP]** (#5240) a publish is an audited action
  recording what, where, visibility and the answers given; "unpublish" is offered and described
  honestly as slow and possibly incomplete. *Test:* the audit record; the wording is present.
- `compute.publish.token-is-narrow` — **[GAP]** (#5240) the Hugging Face token Fichero asks for is fine-grained,
  limited to the person's own repositories, and lives in the one key store. *Test:* a broad
  token is accepted with a warning naming what is wider than needed.

## Accessibility identifiers

- `compute.run.where` — **[GAP]** (#5240) the target chooser where a workflow is run; `compute.run.where.<id>`
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
4. **Base model for the first language or vision fine-tune.** *Answered 2026-10-03: a small
   Qwen-VL-class model (for example Qwen2.5-VL 3B) with LoRA; the choice is a card, so nothing is
   hard-wired. It comes after the Kraken and YOLO path.* *Revised 2026-10-03 (maintainer): the base is a
   choice on the request, Qwen3-VL 8B (Apache-2.0) by default, Qwen2.5-VL 7B or another family after a
   bake-off of the untrained readers; trained in bf16 and landed as MLX 4-bit and as Hugging Face
   weights; the 3B's licence is research-only.*
5. **Does the merged model come home by default?** It is about 16 GB for an 8B model.
   *Proposal: no. The adapter always; the merged model only when the person wants it on the
   Mac.*
6. **Publishing lives in the exporter and model-card specs.** *Proposal: move the eight
   `compute.publish.*` behaviours there once their owners agree, keeping only
   `compute.publish.is-separate-and-asked-again` here.*
7. **Distilling a small palaeography vision model (#4642)** is a customer of this slice, not
   part of it. *Proposal: it stays its own design issue and names `train-lora` as its means.*
