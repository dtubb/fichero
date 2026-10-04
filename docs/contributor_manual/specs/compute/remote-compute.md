# Remote Compute — where and how work runs — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — the user manual needs a "Running work somewhere else" section, written for a
> researcher: what a compute target is; adding a Linux machine, a cluster or Hugging Face;
> what Fichero asks before anything leaves the Mac; sending a job and watching it; what comes
> back and where it shows; training a model on your own corrected pages; and what cannot be
> done away from the Mac.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — first pass 2026-09-20; revised 2026-10-03 against the
> maintainer's rulings of that day (see "Ruled 2026-10-03" and `REVIEW-2026-10-03.md`). This is
> the FOUNDATION of the compute set. Nothing is approved.** Milestone `remote-compute` exists;
> its issues are #5238 (targets), #5239 (transfer and results), #5240 (jobs and fine-tuning),
> #5241 (the image), #5336-#5338 (distillation), #5119 (the training loop), #5397 (training on
> this Mac) and #5398 (Hugging Face Jobs first).
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven · **[GAP]** intended,
> never built · **[BROKEN]** code contradicts the rule. Each behaviour in this set carries its
> own tag and issue. Built since 2026-10-03 (corrected 2026-10-04): training a Kraken reader on this
> Mac and on Hugging Face Jobs, a vision LoRA on Hugging Face Jobs, reading at scale on Hugging Face
> Jobs (`training/`, `remote_read/`), each a row in the one jobs table; no YOLO detector code and no
> live Slurm submission.
>
> Every claim about Fichero's own code is marked **VERIFIED** (read in the file, line given)
> or **INFERRED**. Every claim about an outside service carries a source in "Sources" and is
> marked **CITED** (read in that service's documentation on 2026-09-20, not tried by us) or
> **UNVERIFIED**. Nothing in this set has been tried against a real cluster, a real container
> or a real Hugging Face account.

## The question, and the honest answer

The maintainer asked for this, and asked whether it is doable:

- Machine-learning inference and fine-tuning, **on the Mac and on remote compute**.
- On the Mac: Apple's on-device models, Kraken (finding lines, and reading handwriting), and
  YOLO-family layout models.
- Away from the Mac: fine-tuning a model of three or eight billion parameters, inference, and
  batch work over a whole project.
- How: a Docker build of `fichero-server` for Linux, beside the Mac build, with everything in
  it except the Apple parts. Fichero on the Mac is pointed at a remote place (a cluster such as
  ACENET's, or Hugging Face) with an API key or an SSH login. It installs the server there,
  starts it, connects to it, and efficiently sends it a unit of work. Then fine-tuning,
  inference and batch work run there.

**The answer: yes in substance. Not exactly as described. Three parts of the description
have to change, and one part is better than it sounds.**

### The two ways it could work, and which comes first

The maintainer described two possibilities for a cluster such as ACENET's, where a person logs
in to a login computer and launches a Slurm job from there, and was not sure which is right:

- **A. The engine manages Slurm.** Fichero's engine, on the Mac, logs in to the cluster, sends
  it a properly made piece of work, asks Slurm to run it, waits, and fetches the result.
- **B. The engine runs on the cluster.** Start `fichero-server` there and work through it.

**A is the first thing built, and it is the only way of working on a cluster.** This set calls
it *send a job*. **B is later, and only on machines we control** (a lab machine, a rented GPU),
because a cluster will not let a server stay up: it would be a job with a time limit, behind a
queue. His reasoning is right and the spec follows it: a workflow already runs the same way
every time through LangGraph, so the same run can happen under Slurm, and the Mac fetches what
it made.

**What is sent is "a Python project done properly", and the proper form of it is the image.**
A Python project done properly means the engine's own code, its exact dependencies, and one
command to run it. That is what the Linux image is: the same engine code as the Mac, the same
workflow runner, the same records out, with nothing written a second time for the cluster.
A cluster does not run Docker, so the image is converted once into a single Apptainer file.
Compute nodes are cut off from the internet, so **nothing is fetched by the job itself**: the
login node, which has the internet, fetches the Apptainer file and any models beforehand, and
the Mac sends the pages. If a cluster's login node will not fetch the image, the Mac uploads
the file instead.

*A plain Python environment on the cluster, without the image, is possible but is not
proposed.* Alliance clusters have their own way of installing Python packages (their own
builds, no downloads from the usual index on compute nodes; CITED, S5). The engine needs about
a hundred packages, some of which those clusters may not carry, and Kraken pins its own
versions. It would be a second way of installing the engine, different on every cluster, that
the project's automation cannot test. It stays a last resort for a cluster with no Apptainer,
and none is known.

**What comes back, traced against the code.** A local run today does **not** write one result
file. It writes in two places: straight into the project's database, as it goes (VERIFIED:
the runner is handed the open database, `execution/runner.py:842-850`; documents and artifacts
are saved at the run's boundary, `workflows/completion.py:230-243`, `:305`); and one line for
each model call into the **episode ledger**, which *is* JSONL, append-only, inside the
project's own folder (VERIFIED `observability/episodes.py:10-14`, `:65-78`). So the one code
path is kept like this: on the cluster the package is unpacked into a **small scratch
project** holding only the chosen sources; the **unchanged** runner runs against it exactly
as it does on the Mac, writing the same database rows and the same ledger lines; then the
engine's existing export stream (`export_service.py:124`, `iter_export_records`, the one the
JSONL and Parquet exports already use) writes what is new as JSONL. The Mac fetches those
files. Ledger lines are appended to the Mac's ledger (each has its own id, so a second fetch
adds nothing). The exported records are landed through audited actions. **The run side is one
code path (INFERRED: nothing in the runner needs the Mac; not yet tried). The landing side is
new code: nothing in the engine reads those JSONL records back in today (VERIFIED by search).**
That is the honest size of the work.

**Who manages Slurm, and what survives.** The **Mac's engine** holds the one SSH connection to
the login node and asks Slurm for the state of the person's jobs about once a minute. It must
be the Mac, because the second factor stays with the person. Once a job is submitted it belongs
to the cluster: it waits, runs and finishes **whether or not the Mac is awake or Fichero is
open**. Its results sit in the job's folder on the cluster. When Fichero next runs and the
person has signed in again, one check catches up, and fetching and landing carry on from the
checkpoint. What does not happen while the Mac sleeps: new pieces are not sent, results are not
fetched, and nothing lands. With a cluster's unattended "automation" path (by request), sending
and fetching need no person, but still need the Mac awake.

**Fichero controls Slurm; it does not only describe it** (ruled 2026-10-03). Over that one SSH
connection, with the person's own cluster account, the Mac's engine submits (`sbatch`), watches
(`squeue`, `sacct`), cancels (`scancel`) and fetches the results, and every one of those is a step
of a job in the one job table, shown in Activity like any other. The account's key lives in the
Keychain; a recipe says only that a step runs on a cluster and never names a host, an account or a
key. The command builders in `workflows/remote_jobs.py` stay as the description of what is run;
the in-process SSH connection is the one way it is run. See `jobs-and-fine-tuning.md`,
"Controlling Slurm", and `targets-and-connection.md`.

### What is straightforward

1. **One Linux image.** A Docker image of `fichero-server` for Linux is ordinary work. A seed of
   it is already in the repository (`fichero-server/docker/Dockerfile`), never built. The same
   image runs under Docker on a machine we control and, converted by one command, under
   Apptainer on a cluster. Clusters of the Digital Research Alliance of Canada do not offer
   Docker at all; Apptainer is what they offer, and it builds directly from a Docker image
   (CITED, S1). So "a Docker build" really means **one image, two ways to run it**.
2. **A Linux machine we control.** A lab machine, or a GPU machine rented by the hour, can run
   the image all day. The Mac reaches it over Tailscale, which the transport rules already
   allow (loopback plus `tailscale serve`). This is the one place where "install it, start it,
   connect to it, leave it running" is true as said.
3. **Batch work and fine-tuning as jobs.** Both are work that is sent, runs unattended, and
   comes back. That is what a cluster is for. The pure half of Fichero's Slurm support is
   already written and tested (`workflows/remote_jobs.py`).
4. **Fine-tuning a 3-billion or 8-billion parameter model.** With LoRA it fits on one GPU of
   40 GB: about 8 GB for a 3B model and 22 GB for an 8B, less with QLoRA (CITED, S9). No
   multi-GPU set-up is needed. The libraries are standard (`transformers`, `peft`, `trl`).
5. **Fine-tuning Kraken.** `ketos train` runs on a CUDA GPU. The model that comes back is a
   file Kraken on the Mac already knows how to use. No conversion. This is the cheapest real
   win in the whole set.
6. **Efficient transfer.** The right core exists and is tested: a list of objects named by
   their content (sha256 and size), a difference, a checkpoint, and resume
   (`workflows/library_sync.py`). It moves only what the other side lacks.

### What is hard

1. **Logging in to a cluster from an app.** Alliance clusters require a second factor on every
   SSH login, and a person cannot turn it off (CITED, S3). So the first connection always
   needs the person at the keyboard. The sanctioned unattended path ("automation nodes") must
   be requested in writing, accepts a restricted key only, and **forbids port forwarding**
   (CITED, S4). It can submit jobs and move files. It cannot reach a running server.
2. **SSH from a sandboxed Mac app.** The release build of Fichero is sandboxed. The existing
   design assumes the server shells out to the person's own `ssh` with their own keys and
   `~/.ssh/config` (VERIFIED `remote_jobs.py:147-168`). A sandboxed app very likely cannot read
   those (INFERRED; needs a trial). The way through is a key pair that Fichero makes and keeps
   itself. See `targets-and-connection.md`.
3. **Compute nodes are cut off.** They accept no connection from outside and, on most Alliance
   clusters, cannot reach the internet (CITED, S2, S5). Everything a job needs (the image, the
   models, the data) must be put in place beforehand from a login node.
4. **The app side.** The Mac app today has no way to hold a second server's address and token,
   or to say that a project lives on another machine (issue #2573, open). Everything where
   the Mac "connects to a server somewhere else" waits on that.
5. **A large image.** A GPU image with PyTorch, an inference engine and the training libraries
   is several gigabytes. It has to be built and tested by the project's own automation, not by
   hand, and free build machines have about 14 GB of disk (CITED, S17).

### What is not possible as described, and the nearest possible thing

| As described | Why not | The nearest possible thing |
|---|---|---|
| Install the server on a cluster, start it, and stay connected to it | A login node allows only a few minutes of work. A server must be a **Slurm job**: it waits in a queue, starts when the scheduler says, runs on a node nothing outside can reach, and is killed at its time limit, seven days at most (CITED, S2). | **On a cluster, send jobs.** For work a person watches (trying a model on a page), open a **session**: a job that serves a model for a few hours, reached through an SSH tunnel, and shown in the app with its time left. It is honest to call it a session and dishonest to call it a server. |
| "With everything except Apple Vision" | More than Vision stays behind. **MLX runs only on Apple silicon**, and today every local language model in Fichero runs through MLX. Apple's on-device model and Apple's translation also stay on the Mac. | The Linux image carries a **different engine for the same job**: vLLM for language and vision models. It sits behind the one provider list the AI settings already have. Kraken, spaCy and the rest are the same on both. |
| Install `fichero-server` on Hugging Face | Hugging Face is mainly a place to **keep** models and datasets. Its "Spaces" lose their disk on restart and are shaped as public web pages. | **Hugging Face Jobs** runs a container on a rented GPU, by the minute, from an API token, and can expose one port behind that token (CITED, S12). That fits "send a job" well. And the Hub is a good **registry**: the place to keep and publish datasets, adapters and model cards. Both send research material to a company in the United States, which the person must agree to first. |
| Reach the cluster over Tailscale | Tailscale on a compute node needs the node to reach the internet. On at least three Alliance clusters it cannot (CITED, S5). No Alliance policy on it was found either way (UNVERIFIED). | **An SSH tunnel** is the documented way in on a cluster (CITED, S2). Tailscale is right for machines we control. |
| Fine-tune "on the Mac and on remote compute" alike | A Linux container on a Mac gets no GPU that PyTorch can use (CITED, S16). Kraken training on Apple's GPU was blocked upstream and is unconfirmed today (UNVERIFIED, S10). Apple's on-device model takes an adapter, but one adapter fits one system-model version and shipping it needs an entitlement (CITED, S11). | On the Mac, Kraken and YOLO train **natively, inside the engine** (no container), on Apple's GPU if Kraken allows it and on the CPU if not, measured on a 16 GB Mac (ruled 2026-10-03; #5397). A vision-language LoRA trains on a GPU elsewhere, Hugging Face Jobs first, and comes back to *run* on the Mac. The Apple adapter is left out of this set. |

### What is better than it sounds

Nearly all of this was **already thought through** in three design plans of 2026-09-02 and
2026-09-06, and the safe halves are **already built and tested**. See "What exists today". The
work is to turn three plans into one ruled design, and to build the halves that touch a
network. It is not a fresh start.

## Intent (the design)

A researcher has more pages than their Mac can read in a night, or wants a model that knows
their scribe's hand. They add a **compute target** once: a Linux machine, a cluster account, or
a Hugging Face account. From then on, any work Fichero can do on the Mac it can offer to do
there instead. Fichero says plainly what will leave the Mac, where it will go and who runs
that place, and asks. It sends only what the work needs, picks up where it left off if the
network drops, shows the work queued, running and finished, and brings the results back
through the same audited actions as everything else, marked with where and how they were
made. Nothing that comes back overwrites a person's work. A model trained there comes back as
a card in the one catalogue, measured against the researcher's own ground truth.

Underneath, there is **one of each thing**: one server (the same code on the Mac and in the
Linux image), one job describer, one transfer core, one list of machines, one provider list,
one catalogue, one gate that decides whether content may leave.

## The files

| File | What it holds |
|---|---|
| `remote-compute.md` | this file: the answer, the words, the design on one page, what exists, the rulings proposed against duplicate paths, testing from the maintainer's side, build order, questions, sources |
| `linux-server-image.md` | the Linux image: what is in it and what is left out, CPU and GPU images, running offline, what it reports about itself, how it is built and smoke-tested with no person involved, the local stand-in on the Mac; release questions routed to `harness/release-and-versioning.md` |
| `targets-and-connection.md` | compute targets as one list of machines; adding one; installing; connecting on each kind of target (Tailscale, SSH tunnel, token); the second factor; secrets; sessions and their time limits; what existing cluster settings become |
| `transfer-and-results.md` | what is asked before anything leaves; the work package; the one transfer core and its two carriers; resume; cleaning up the far side; results landing as audited actions; what happens when the project changed meanwhile |
| `jobs-and-fine-tuning.md` | job kinds; which engine for which work (the answer to "Blackfish, or load the models directly"); batch work over a project; fine-tuning as a job; surviving a time limit; the model coming back; publishing to Hugging Face and Zenodo, routed to the exporter and model-card specs |

## The design

### Ruled (maintainer, 2026-09-20)

- **The goal.** Inference, fine-tuning and batch work on the Mac and on remote compute, as
  described under "The question".
- **A Linux build beside the Mac build, shipped as a Docker release.** (The maintainer's stated
  leaning; the release mechanics are routed, see `linux-server-image.md`.)
- **The existing Slurm and ACENET work is to be found and built on**, not replaced.
- **The most efficient inference engine for each kind of work**, all behind the one provider
  list. (Answered in `jobs-and-fine-tuning.md`.)
- **Hugging Face, with Parquet, as a place to keep track of and publish** datasets, adapters,
  models and model cards. (Built on the existing exporter; see below.)
- **A new word: collection.** Superseded: the unit is the **project** (a library becomes a
  project; confirmed 2026-10-03). This set says "project" throughout; what a job is sent is a
  selection of sources inside a project.

### Ruled 2026-10-03 (maintainer; paraphrased)

- **Where training is proven, in order.** Hugging Face Jobs first, because it is known to run
  training reliably; then ACENET (Slurm); then Docker on a machine we control, and others.
- **As much as possible runs on the Mac.** Fine-tuning Kraken (lines and readers) and YOLO
  (page and region detectors) runs inside Fichero on a 16 GB Mac. Every small model Fichero
  adopts must run on a 16 GB Mac.
- **Cheapest and local first.** A costlier place or model is used only when an A/B on the
  project's own checked pages shows it is needed: by error rate, cost, speed, carbon and
  trainability.
- **Distillation is an option, never the default.** When a person chooses training in setup,
  the default offered is to distil from a large teacher, then fine-tune a small model. Training
  runs by itself only if it was chosen in setup (`source.recipe.train-never-automatic`).
- **The models.** Kraken (`ketos train`, `ketos segtrain`); YOLO detectors; a small
  vision-language model (for example Qwen2.5-VL 3B) with LoRA; spaCy. Good models are released
  on Hugging Face as part of Fichero, with their licences respected.
- **One job model.** A remote, cluster or training run is a job in the one job table of
  `ui/activity-and-automatic-work.md` (its question 9, ruled 2026-10-01), never a second runner
  or a second job table.
- **Load a model once, group work by model, never co-run heavy models unless both fit**, and
  measure what each job uses (CPU, GPU, Neural Engine, memory).
- **One audited action layer; logic in the engine; recipes are data and name providers, never
  keys.** Pages leaving the Mac are asked about **once per project**.
- **The Mac stays usable**: background work, training included, throttles itself.
- **One error rate.** CER is Fichero's one definition (`workflows/transcription_accuracy.py`,
  reached through `POST /api/documents/{id}/readings/compare`). A score is called *CER* only when
  a person checked the reference; otherwise it is *agreement*.

Everything else in this set is **PROPOSED** until ruled.

### The design on one page (proposed)

**Three kinds of place, two ways of working.**

| | A machine we control (lab machine, rented GPU) | A Slurm cluster (Alliance, ACENET) | Hugging Face |
|---|---|---|---|
| How the image gets there | the target pulls the published image with Docker | a login node pulls it once as an Apptainer file into project space | nothing to install; a job names the image |
| What runs | a **server** that stays up, and jobs | **jobs**; and **sessions** (a model served for a few hours) | **jobs**; sessions possible (CITED, not proposed for the first build) |
| How the Mac reaches it | Tailscale `serve`, or an SSH tunnel | SSH, with the person's second factor on first connection; a tunnel for a session | HTTPS with the person's token |
| Credential | a paired-device token (the existing pairing) and, for install, an SSH key | an SSH key Fichero keeps; the second factor stays with the person | a fine-grained token |
| Who else can read the data there | whoever runs that machine | the cluster's administrators; not certified for sensitive data (CITED, S6) | a company in the United States |
| Can hold a project and be opened from the Mac | yes (needs #2573) | not proposed | no |

**Send a job** is the way of working that exists everywhere, so it is built first. The Mac's
own server stays in charge. It makes a **work package**: a job description, and a list of the
objects the job needs, each named by its content. It sends what the target lacks. The target
runs the package with the same image, with no web server and no open port, and writes a
**result package**. The Mac fetches it and **lands** it through audited actions. A job is
finished only when its results have landed, which the existing code already says (VERIFIED
`remote_jobs.py:281-293`).

**Open a session** is for work a person watches. The target serves one model through the
OpenAI-style protocol that Fichero's provider list already speaks to (Ollama, LM Studio, oMLX
are rows of that kind today; VERIFIED `llm/providers.py:48-51`). To Fichero it is one more
provider row, which exists while the session does. Page images go to it one request at a
time, through the same gate as any cloud model.

**A remote server that holds a project**, opened from the Mac as if it were local, is the
third thing. It is true on a machine we control. It is the existing "remote engine" model
plus the push half of the existing sync. It waits on #2573, so it comes last.

**One transfer core, two carriers.** The content-addressed manifest, difference, checkpoint and
resume in `workflows/library_sync.py` become the only transfer logic. It gains a second
subject (a work package, not only a whole library) and a second carrier (files over SSH to a
cluster, beside HTTPS to a running Fichero server). The older `BundleManifest`, which lists
bare paths with no hashes (VERIFIED `remote_jobs.py:39-81`), is folded into it.

**One gate.** Whether content may leave the Mac is decided in the one place the source-model
set already names (`source.egress.one-gate`, #4949), reading the project's own rule
(`source.project.stays-local`, #4951). Sending a work package is one more caller of that gate,
not a second check.

**Blackfish: learn from it, do not depend on it.** It is real, MIT-licensed, made at Princeton,
and does for inference most of what the cluster half of this set needs: a profile for each
cluster, a cache of images and models on the cluster, submit a job, wait, open an SSH forward
(CITED, S13). But it is a beta with about a hundred open issues; it does no fine-tuning; services
started from its interface have no authentication; and its templates need the engine to listen
on every network interface, which Fichero's transport rules forbid. Its design confirms ours.
The reasoning is in `jobs-and-fine-tuning.md`; the choice is question 6.

### The words (one meaning each)

| Word | Meaning here | Not to be confused with |
|---|---|---|
| **project** | the whole thing a person works on, with its own settings and recipe (a library becomes a project; confirmed 2026-10-03). A job is sent a **selection** of a project's sources. The earlier word "collection" (2026-09-20) is retired in this set. | a selection (the sources one job is sent) |
| **compute target** | a place work can run, added once: *this Mac*, *a Linux machine*, *a Slurm cluster*, *Hugging Face*. One list holds them all. | a provider (a thing that offers models); a paired device (a phone or iPad that reads a project) |
| **server image** | the published Linux image of `fichero-server`. One image, run by Docker or by Apptainer. | the Mac's embedded engine (same code, packaged by Briefcase) |
| **job** | work that is sent, runs unattended and comes back. It has a kind, a work package, a state and a result package. | a workflow run (a job *carries* a workflow run, or a training run) |
| **session** | a model served on a target for a limited time, reached through a tunnel, shown with its time left. | a server (which stays up) |
| **work package** | what a job needs and nothing more: a job description plus a content-addressed list of objects. A **projection** in the source-model sense: made when wanted, never the record. | a whole project; an export |
| **result package** | what a job made: the engine's own export records for what is new (JSONL), the episode-ledger lines the run appended (JSONL), and new objects. | a database; a changed copy of the project |
| **landing** | replaying a result package into the project through the audited action layer, so history stays whole. | copying files back |
| **carrier** | the way bytes travel: HTTPS to a running Fichero server, or files over SSH. The transfer core is the same over both. | transport (the app-to-engine connection in `transport/`) |
| **adapter** | the small file a LoRA fine-tune produces; useless without its base model. | a merged model (base plus adapter, a full-size file) |
| **publish** | to put a dataset, adapter, model or card where other people can get it (Hugging Face, Zenodo). Always a separate, deliberate act. | sending a work package to a target (which is private) |

### What this set owns, and what it routes

This set owns **where and how compute runs**: the Linux image, targets, installation,
connection, what is sent, jobs, sessions, fine-tuning runs *as jobs*, and results coming back.

It routes, and does not restate:

| Matter | Owner |
|---|---|
| what a training set is, the split, ground truth, measuring a model | `source/formats-and-training.md` (`source.train.*`, #4947) |
| what a model card is, licence classes, the one catalogue, finding models | `source/models-chains-and-projects.md` (`source.model.*`, `source.find.*`, #4948) |
| the one gate for content leaving; "pages may not leave this machine" | same file (`source.egress.one-gate` #4949, `source.project.stays-local` #4951) |
| rights, consent, community protocols, restricting and removing | `source/rights-and-access.md` (**blocked on the maintainer**) |
| the Parquet stream and the Hugging Face dataset bundle | `export/exporter.md` (`export.huggingface-dataset-ready-bundle`, #4069 #2181 #1806) |
| provider rows, one catalogue, downloads inside each row | `ai/ai-settings.md` |
| where keys live | `ai/provider-keys.md` |
| the app-to-engine transports | `transport/transport-http-uds.md` |
| where the image is published, its version, staying compatible with the Mac app | `harness/release-and-versioning.md` (a request is listed below) |
| that a formal Kraken training spec "is not written" | `source/formats-and-training.md:133-135` says so; **this set is that spec**, for the running of it |

Note on Parquet. The maintainer spoke of PyArrow. The exporter's ratified rule is that Parquet
is written by DuckDB and PyArrow is not required (`export.duckdb-parquet-not-pyarrow`, [OK]).
The goal (a bundle Hugging Face's `datasets` loads directly) is unchanged and unbuilt. This set
builds on that exporter. It plans no second one.

## What exists today (read on disk 2026-09-20)

The full table, with a line reference for every claim, is in the working note
*what-exists* (kept in the working folder for this set, outside the repository). In short:

- **Slurm job describer.** `fichero-server/src/fichero_server/workflows/remote_jobs.py`. Pure
  functions: a cluster is a reference and never a secret (VERIFIED `:147-168`); an `sbatch`
  script (`:92-118`); one run over N files is one array job, and a re-submit can name only the
  missing pieces (`:310-344`); Slurm's states map to Fichero's, and "completed" waits for
  landing (`:246-293`); a submitter seam with a scripted fake (`:361-374`, `:458-491`). **The
  SSH submitter builds commands and never runs them** (`:504-553`). Its default command names
  `runner/run_task.py`, **which does not exist** (VERIFIED by search).
- **Cluster settings routes.** `api/routes/ai/hpc.py`. Save, list, delete; stored as one JSON
  value under the key `hpc.clusters` (VERIFIED `:50-53`). **"Test" does not connect**: it
  returns the command it would run, with `ok: true` (VERIFIED `:253-285`). "Dry-run submit"
  returns the script (`:288-333`). Five MCP tools exist. **No app screen exists.** Guardrail
  issue #4907 is open against these routes.
- **Library sync.** `workflows/library_sync.py`, `library_sync_io.py`, `library_sync_db.py`,
  `api/routes/library/sync.py`. Content-addressed manifest, difference, checkpoint, resume,
  hash-checked landing, a library identity that survives a move. **Two read-only routes; no
  push, no commit, no clone command, no app screen** (VERIFIED `sync.py:14`).
- **A Dockerfile.** `fichero-server/docker/Dockerfile`, 66 lines, with a README. CPU only; no
  Kraken, no inference engine; listens on every interface by way of the engine's "I understand
  the risk" setting (VERIFIED `:61-63`), which the remote-backend document calls "not the
  supported remote-backend model" (VERIFIED `remote-backend-acenet.md:145-150`). **Nothing in
  the repository builds it, and Docker is not installed on the development Mac.**
- **A manual recipe.** `docs/contributor_manual/remote-backend-acenet.md`, marked "AI
  generated. Not reviewed." Start the server on the far machine bound to its own loopback, open
  an SSH forward, copy the token by hand. The server's remote mode refuses any bind but
  loopback (VERIFIED `security/remote_backend.py:92-133`). The recipe never mentions a queue or
  a time limit, contradicts itself on `http` and `https` (`:60-61`, `:124`), and overwrites the
  Mac's own token file because **the app has no setting for a second server's token** (`:82-96`).
- **The provider list** already holds local servers that speak the OpenAI-style protocol
  (VERIFIED `llm/providers.py:48-51`).
- **No training code and no YOLO detector exist** in the engine (VERIFIED by search,
  2026-10-03). The job registry already names the step: `train-a-model`, taking line readings
  and lines, giving a model card (VERIFIED `recipes/jobs.py:143-146`); the seed cards mark the
  Kraken and small vision-language models trainable (`recipes/seed/cards.yaml`). YOLO is read and
  written only as label files (`formats/yolo.py`).
- **Kraken now runs inside the engine's own process**, loaded once, one operation at a time
  (VERIFIED `llm/kraken_runtime.py:512-519`), with PyTorch in the engine. So a Kraken trainer
  can run in the same process on the Mac.
- **The one CER is reachable**: `POST /api/documents/{id}/readings/compare` scores a reading
  against a reference with the CER of `workflows/transcription_accuracy.py`, and labels it
  `agreement` unless a person checked the reference (VERIFIED
  `api/routes/document/compare_readings.py:88`; #5389 and #5394 closed). `mlx_lm`'s
  convert step, which a model trained elsewhere would need, **is not called anywhere**
  (VERIFIED by search of `llm/mlx_model_store.py` and `llm/mlx_runtime.py`).
- **PyTorch is now inside the Mac engine.** On the integration branch, commit `b844f9d85`
  (2026-09-20) put `pykeen`, and with it PyTorch, into the embedded engine and into the core
  dependency list, about half a gigabyte more (VERIFIED `fichero-server/pyproject.toml:163-165`,
  `:317-319` on that branch). So the existing Dockerfile's `pip install .` now pulls PyTorch too
  (INFERRED; never built).
- **Tests.** 74 tests across these modules pass (run 2026-09-20). They prove the pure rules.
  They prove nothing about a network.
- **Issues.** #657 and #1239 were closed on the pure halves. Open and relevant: #2573
  (a host for each library), #4621 (Kraken capability, including fine-tuning), #31 (look into
  Blackfish), #4642 (distil a small palaeography vision model), #4907 (undo guardrail on the
  cluster routes), #1806 #2178 #2181 #4069 (Parquet and Hugging Face export), #4947 #4948
  (training sets, model cards). A legacy milestone named "Settings - Models & Providers - HPC"
  holds #31 and #4621.
- **Three design plans**, in the gitignored working folder `agent-work/design/`: the live
  Slurm connection (2026-09-02), resumable library sync and the server in a container
  (2026-09-06), and fine-tuning on a cluster (2026-09-06). They are plans: no behaviour ids, no
  tests, not in this manual. This set supersedes them and keeps their conclusions where the
  evidence still holds.

## One of each thing: the duplicate paths, and the ruling proposed for each

The maintainer's standing worry is two code paths for one job. Five are already forming.

| # | Two paths forming | Proposed: the one path |
|---|---|---|
| 1 | Files to a remote by **rsync** (two of the plans) or by **our own manifest over HTTPS** (the third plan, and the only one with code) | Our manifest, difference and checkpoint are the one transfer logic. SSH is a second **carrier** under it, not a second logic. See `transfer-and-results.md`. |
| 2 | `BundleManifest` (paths, no hashes) and `SyncManifest` (hashes, resume) | One manifest. A work package is a `SyncManifest` with a job description beside it. `BundleManifest` is removed. No stored data uses it (VERIFIED: it is only ever built in memory, `hpc.py:308-315`). |
| 3 | **Clusters** saved under `hpc.clusters`, and **remote servers** in the app's connection settings and, one day, on each library (#2573) | One list of **compute targets**, which is also the list of machines a project can live on. See `targets-and-connection.md` for what happens to saved clusters. |
| 4 | The container **listens on every interface**; the documents and the remote mode say **loopback only** | The image listens on loopback by default, like the Mac. It listens more widely only inside a container's private network, and the far machine never offers the port to a public network. See `linux-server-image.md`. |
| 5 | A cluster-served model as a **new kind of provider** (the fine-tuning plan) or as **an existing local-server row at another address** | An existing kind of row. A session adds a row and removes it. No second provider system. See `jobs-and-fine-tuning.md`. |
| 6 | Two **job runners**: the workflow runner on the Mac, and a separate small `runner/run_task.py` for clusters (named, never written) | One runner. The image runs the same workflow code in a "run this package" mode. See `jobs-and-fine-tuning.md`. |
| 7 | Two **model catalogues**: models on the Mac, and models cached on a target | One catalogue of cards (`source.model.card-is-the-catalogue`). A card gains "also present on these targets". A target has no catalogue of its own. |
| 8 | Two **job models**: a `compute_jobs` table proposed here, and the one `jobs` table of `ui/activity-and-automatic-work.md` | The one `jobs` table (ruled 2026-10-01). A remote job is a row with lane `remote` and its target named; its far-side states are its `state` and `waiting_reason`; array pieces are child jobs. See `compute.job.one-state-machine`. |
| 9 | Two **trainers**: one in the Mac engine, one in the image | One trainer in the engine's code. It runs in process on the Mac and in "run a package" mode in the image, on Hugging Face Jobs or a cluster. See `compute.tune.one-trainer-three-places`. |

## How this is tested from the maintainer's side

The maintainer does not build Docker images and should never have to. Two paths, and a stand-in.

**The automated path needs nothing from a person.** On every change to the server or the image,
the project's own continuous integration: builds both images on machines of the right
architecture; starts the image; waits for its health route; sends one tiny job with the
network switched off inside the container; checks the result; stops it; converts the image to
an Apptainer file and runs the same tiny job under Apptainer; and runs submit, poll and fetch
against **a real Slurm scheduler inside containers**, reached through a real SSH server
(CITED, S18). "It works" is that run being green. Behaviours: `compute.image.ci-*` in
`linux-server-image.md`.

**The no-Docker stand-in runs in the ordinary test gate.** One kind of compute target is *this
Mac*: the same job loop (package, send, run, fetch, land) with the far side being a folder and
a process on the same machine. It needs no Docker and no network, so it runs in `pytest` on the
development Mac and in the release gate. It is also a real feature: it is how a job runs when
no target is chosen. Behaviour: `compute.target.this-mac-is-a-target`.

**The walkthrough is what the maintainer does by hand**, once, to see it end to end without a
cluster:

1. Install Docker Desktop from its website (a normal Mac installer; free for personal and
   educational use; CITED, S16). Open it once. Nothing else is installed.
2. In Fichero: Settings, AI, **Where work runs**, **Add…**, **This Mac, in a container (for
   testing)**. One button.
3. Fichero fetches the published image, starts it, pairs with it, and the row turns green:
   *Connected. Linux server 2026.09.x. No GPU. Can run: Kraken, spaCy, workflows. Cannot run:
   Apple models, MLX.*
4. Select three pages. Run a workflow, choosing that target. Fichero shows what will leave
   (three page images, their sizes) and asks.
5. The job shows *sending*, *running*, *fetching*, *done*. The pages gain a new pass, marked
   with the target's name and the models used. Nothing else on the pages has changed.
6. Remove the target. Fichero stops the container and says so.

What he sees if it fails is part of the behaviour: the row is red and names the step that
failed (*Docker is not running*; *could not fetch the image*; *the server started but its
version does not match this app*).

One unknown sits under step 2: whether the **sandboxed** release build may talk to Docker
Desktop's control socket at all (UNVERIFIED, S16). If it may not, step 2 becomes: Fichero shows
one command with a Copy button, the maintainer pastes it into Terminal once, and adds the
target as "a Linux machine at this address". This needs a half-day trial before the slice is
cut. It is question 9.

A container on a Mac gets no GPU that PyTorch can use (CITED, S16), so the stand-in proves the
loop and proves nothing about speed.

## Build order (revised 2026-10-03; engine before app; each slice builds, tests and commits alone)

The first goal is narrow: **fine-tune a Kraken reader and a YOLO page detector on the Sergio
notebooks' checked pages, first on Hugging Face Jobs, then on this Mac, then on ACENET; measure
each by CER on held-out pages; adopt the winner in the project's recipe as a new card.** The
order serves that goal first. `REVIEW-2026-10-03.md` gives the reasons.

0. **Before any training (other specs).** Checked pages on the Sergio notebooks (a person);
   a training set from them, split by notebook (`source.train.*`, #4947), with line pictures for
   Kraken and YOLO labels for the detector (`formats/yolo.py` already writes them); the one CER
   (built); the one job table (#5353).
1. **One trainer, proven on this Mac's CPU in `pytest`.** The `train-a-model` job's engine code:
   training set in; model file, log and held-out CER out. Tiny set, two epochs, no network. It is
   the code every later place runs.
2. **The image that trains.** One `linux/amd64` image with the CUDA runtime, the engine, Kraken
   and the YOLO trainer, with "run a package" mode. Built and smoke-tested by automation on CPU.
   No vLLM, no LoRA libraries, no `arm64` stand-in yet.
3. **Hugging Face Jobs as the first target** (#5398). Token, the hub carrier, run the image,
   fetch, land the model as a card, egress asked once per project. Run twice: the same CER within
   noise is the proof.
4. **Training on this Mac** (#5397). The same trainer in the local ML lane on a 16 GB Mac,
   throttled, with memory and processor use measured. Compared with the Hugging Face run.
5. **Adoption.** The trained card enters the A/B against the current step (Kraken's general
   models, the frontier draft) on held-out checked pages; the winner is offered as the
   project's next recipe version (`compute.tune.adopted-by-the-recipe`).
6. **ACENET.** The Slurm target: the Fichero-kept key, the second factor, Apptainer from the same
   image, staging, the SSH carrier, live submit, poll and fetch. The trials in
   `targets-and-connection.md` (its questions 1 to 3) come first.
7. **Release on Hugging Face** as part of Fichero, once the project's rights allow it.
8. **Later, each its own slice:** the small vision-language model with LoRA (on Hugging Face
   Jobs, then ACENET; it must then *run* on a 16 GB Mac); batch inference jobs and landing passes
   (`compute.land.*` for readings); vLLM and sessions; a Linux machine we control; the `arm64`
   stand-in; MLX conversion; Zenodo; a remote server that holds a project (#2573).

Slices 1 and 2 need no outside account; slice 3 needs a Hugging Face token with credit.

## Requests to other specs (for the manager to route; nothing edited there from here)

1. **`harness/release-and-versioning.md`**: a Linux image becomes a fourth thing a release
   ships. Wanted there: where it is published (proposed: GitHub's container registry, because
   Docker Hub's anonymous pull limit is per network address and a whole cluster shares one;
   CITED, S15); that its version is the engine's version stamp; that an app refuses a server
   whose API contract it does not match, with the OpenAPI contract as the seam; that the image
   is signed with build provenance; that the image is built and smoke-tested before a release
   is called done.
2. **`source/models-chains-and-projects.md`**: a card should be able to say "also present on
   these targets" and "trained by this job". Nothing else about cards is wanted from here.
3. **`source/rights-and-access.md`**: this set needs one answer from it before slice 3 is
   final: what makes a source "restricted" in a way a work package must honour. Until it is
   unblocked, this set excludes nothing automatically and says so on the sheet.
4. **`ai/ai-settings.md`**: a home for compute targets (proposed: a section of the same list,
   titled "Where work runs", each row carrying its own controls, as provider rows do). A new
   kind of provider row for vLLM, as a peer of oMLX.
5. **`export/exporter.md`**: publishing to Hugging Face is that spec's bundle plus an upload
   step. This set asks that the upload step, and the questions asked before it, live there, and
   offers the text in `jobs-and-fine-tuning.md` as a draft to move.
6. **`ai/provider-keys.md`**: SSH private keys and Hugging Face tokens are new kinds of secret
   under its rule ("exactly one place a local engine's keys live").
7. **The legacy milestone "Settings - Models & Providers - HPC"** (#31, #4621) should fold into
   this set's milestone once it is named.

## Behaviors

The behaviours are in the four slice files, grouped as below. This file holds none of its own.

| Group | File | Ids |
|---|---|---|
| the image | `linux-server-image.md` | `compute.image.*` |
| targets, installing, connecting, secrets, sessions | `targets-and-connection.md` | `compute.target.*`, `compute.connect.*`, `compute.secret.*`, `compute.session.*` |
| consent, packages, transfer, landing | `transfer-and-results.md` | `compute.leave.*`, `compute.package.*`, `compute.transfer.*`, `compute.land.*` |
| jobs, engines, fine-tuning, publishing | `jobs-and-fine-tuning.md` | `compute.job.*`, `compute.engine.*`, `compute.tune.*`, `compute.publish.*` |

Each behaviour is written so that an issue and a test can be cut from it directly: it names
the data it touches, says what a person or a caller observes, and says what happens to data
that already exists.

## Test matrix

| Leg | This set? | Pins | File |
|-----|-----------|------|------|
| Pure rule (Swift) | y | the target row's state and wording; the "what will leave" sheet's contents from a package | a new `compute` group under the Swift unit tests |
| Availability (Swift) | y | "Where work runs" is reachable in Settings; a target can be chosen where a workflow is run | same |
| Backend (pytest) | y | packages, transfer, resume, state machine, landing, refusal at the gate; marker `remote_compute` to be added to `fichero-server/pyproject.toml` | `fichero-server/tests/unit/workflows/`, `tests/unit/api/` |
| MCP | y | targets and jobs reachable as tools; the five existing `fichero_hpc_*` tools are renamed with them | `fichero-mcp/tests/test_mcp_server.py` |
| CLI | y | the same through the generated surface | `fichero-cli/tests/` |
| Click-around (XCUITest, Mac) | y | add the test target, run a job on three pages, see the new pass | `fichero/Tests/UI/…` |
| iPhone / iPad | n | targets are added on the Mac; a phone sees results like any other change | |
| Load (#4634) | y | sending a large package never pegs the Mac (background priority, bounded) | `fichero-server/tests/perf/…` |
| **Image (continuous integration)** | y | build, start, health, offline tiny job, Apptainer, Slurm-in-containers | `.github/workflows/` (new leg; not in the template) |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y (the maintainer's own; facts only from here) | the user manual |
| Contributor | developer docs | y | this set; and `remote-backend-acenet.md` is to be replaced by a page written from the built behaviour, not before |
| AI / agent | MCP tool description | y | `fichero-mcp/**` |
| Scripter | CLI `--help` | y | generated |
| Reference | capability/endpoint reference | y | generated |

## Open questions for the creative director

Each has a proposal, so "agreed" is a complete answer. The same list, with more room for notes,
is in the working note *questions for the maintainer*, outside the repository.

*Questions 1, 2, 3, 8, 11 and 17 are answered by the rulings of 2026-10-03 (above): the project
is the unit; the milestone is `remote-compute`; jobs first, sessions later; Kraken and YOLO are the
first fine-tunes; Hugging Face Jobs is the first target for training; ACENET is second. They are
kept below, marked, so the record stays whole.*

1. **What is a collection?** *Answered 2026-10-03: the project is the unit; a job is sent a
   selection of a project's sources. This set no longer uses "collection".*
2. **The name of this set and its milestone.** *Proposal: `remote-compute`, files in
   `specs/compute/`, behaviour ids `compute.*`.*
3. **Build "send a job" first, everywhere; sessions second; a remote server that holds a
   project last.** *Proposal: yes, in the build order above. It gives fine-tuning and batch
   work on every kind of target soonest, and needs the least new app work.*
4. **On a cluster, no long-lived server: jobs and time-limited sessions only.** *Proposal:
   agreed as the honest limit. A whole `fichero-server` holding a project is for machines we
   control.*
5. **A key Fichero makes and keeps**, rather than the person's own SSH set-up. The person pastes
   the public half into the cluster's account page once. *Proposal: yes, because a sandboxed
   app very likely cannot use the person's own keys, and because a cluster's automation path
   demands a dedicated restricted key anyway. Needs a short trial first.*
6. **Blackfish.** *Proposal: learn from its design, do not depend on it or wrap it. Close #31
   with that finding. Reasons in `jobs-and-fine-tuning.md`.*
7. **One inference engine for each kind of work.** *Proposal: on the Mac, MLX as today. On Linux
   with a GPU, vLLM: inside the job for batch work, as a session for watched work. Kraken and
   layout models load directly in the job's own process. Fine-tuning is always a job.*
8. **The first fine-tune to build is Kraken's**, then a language or vision model with LoRA.
   *Proposal: yes. Kraken's result needs no conversion and the maintainer's own corrected pages
   are the training set.*
9. **The walkthrough needs Docker Desktop on the maintainer's Mac.** *Proposal: agreed, with a
   half-day trial of whether the sandboxed build can drive it; if not, one pasted command.*
10. **What is asked before a project leaves.** *Proposal: a sheet that names what, how much,
    where, who runs that place and how long it stays; a yes that is remembered for that
    project and that target; nothing sent from a project marked "may not leave"; and
    until the rights slice is unblocked, nothing is excluded automatically and the sheet says
    so.*
11. **Hugging Face.** *Proposal: the Hub as a registry first (private by default, gated where
    access must be approved, takedown described honestly as slow), built on the exporter.
    Hugging Face Jobs as a compute target later. Spaces and Inference Endpoints not used.*
12. **Zenodo for Kraken models and ground truth.** The field's convention is Zenodo and the
    HTR-United catalogue, which give a citable DOI; Kraken has a publish command for it
    (CITED, S14). *Proposal: offer both, Zenodo for Kraken models and ground truth, Hugging Face
    for adapters and merged models; routed to the exporter and model-card specs.*
13. **Layout models and their licence.** Ultralytics YOLO and DocLayout-YOLO are AGPL-3.0, and
    Ultralytics says that reaches the trained weights (CITED, S8). Fichero is AGPL-3.0, so this
    is compatible today, but it would bind any future change of licence. RT-DETR, YOLOX and
    D-FINE are Apache-2.0. *Proposal: nothing is baked into the image; every model is fetched
    on request by its card, under `source.model.licence-class`; and the default layout model
    recommended by Fichero is a permissively licensed one.*
14. **Saved cluster settings and the five `fichero_hpc_*` tools are renamed, not kept beside
    the new ones.** No app screen uses them. *Proposal: convert the saved value once, rename the
    routes and tools, keep no alias.*
15. **PyTorch is now in the Mac engine.** That makes it possible to run Kraken, and later a
    layout model, inside the engine's own process instead of a separate environment installed
    on demand. It buys sameness between Mac and Linux, not speed. *Proposal: not now. Note it
    in `ai/ai-settings.md` as a simplification to weigh after this set's first three slices.*
16. **Apple's on-device model adapters** are left out of this set. *Proposal: agreed; one
    adapter fits one system-model version and shipping one needs an entitlement.*
17. **Which cluster first?** ACENET's own cluster, Siku, has about eleven GPUs (CITED, S7). The
    national clusters have hundreds. *Proposal: whichever the maintainer has an account and an
    allocation on; the spec names none. Please say which.*

## Sources

Read on 2026-09-20 by research workers; the full notes with every link are in the working
notes *outside-facts*, parts 1 to 3, outside the repository. The Alliance's own wiki refuses automated readers; its pages were read
through a text proxy, and a person should re-read S1 to S5 before this spec is approved.

- **S1** Apptainer on Alliance clusters; Docker not offered; building from a Docker image; `--nv`. <https://docs.alliancecan.ca/wiki/Apptainer>
- **S2** Running jobs (login-node limits, 168-hour limit); SSH tunnelling to a compute node. <https://docs.alliancecan.ca/wiki/Running_jobs>, <https://docs.alliancecan.ca/wiki/SSH_tunnelling>
- **S3** Multifactor authentication is mandatory. <https://docs.alliancecan.ca/wiki/Multifactor_authentication>
- **S4** Automation nodes; restricted keys; no port forwarding. <https://docs.alliancecan.ca/wiki/Automation_in_the_context_of_multifactor_authentication>
- **S5** Compute nodes and the internet. <https://docs.alliancecan.ca/wiki/Python>; per-cluster detail (secondary): <https://docs.mila.quebec/technical_reference/clusters/drac/>
- **S6** Not designated for sensitive data. <https://docs.alliancecan.ca/wiki/Data_protection,_privacy,_and_confidentiality>
- **S7** GPUs by cluster; ACENET's Siku. <https://docs.alliancecan.ca/wiki/Using_GPUs_with_Slurm>, <https://www.ace-net.ca/compute-resources/>
- **S8** Licences: Ultralytics <https://www.ultralytics.com/license>; DocLayout-YOLO, RT-DETR, YOLOX, D-FINE, Kraken, vLLM, llama.cpp, Qwen3 (links in the working notes).
- **S9** Memory for LoRA and QLoRA. <https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements.md>
- **S10** Kraken: training, devices, no server, the repository of models. <https://kraken.re/main/index.html>, <https://github.com/mittagessen/kraken/issues/358>
- **S11** Apple's adapter training toolkit. <https://developer.apple.com/apple-intelligence/foundation-models-adapter/>
- **S12** Hugging Face Jobs, Spaces, Inference Endpoints, storage. <https://huggingface.co/docs/huggingface_hub/en/guides/jobs>, <https://huggingface.co/docs/hub/spaces-sdks-docker>, <https://huggingface.co/docs/hub/storage-limits>
- **S13** Blackfish. <https://github.com/princeton-ddss/blackfish>, its issues #534 and #537.
- **S14** Publishing: Hugging Face upload, gating, deletion; Zenodo and HTR-United; CARE and Local Contexts. <https://huggingface.co/docs/huggingface_hub/en/guides/upload>, <https://huggingface.co/docs/hub/en/models-gated>, <https://kraken.re/6.0.0/advanced/repo.html>, <https://localcontexts.org/>
- **S15** Tailscale in containers and in userspace; registries and pull limits. <https://tailscale.com/docs/features/containers/docker/docker-params>, <https://tailscale.com/docs/concepts/userspace-networking>
- **S16** Containers on a Mac: licences, no GPU for PyTorch, Apple's `container`. <https://docs.docker.com/subscription/desktop-license/>, <https://github.com/apple/container>
- **S17** Inference engines; vLLM's start-up cost and LoRA loading; TGI archived; PyTorch 2.14 on Apple silicon; build-machine disk. <https://docs.vllm.ai/en/latest/features/lora/>, <https://github.com/huggingface/text-generation-inference>, <https://pytorch.org/blog/pytorch-2-14-release-blog/>
- **S18** A Slurm scheduler in containers for tests; Apptainer in continuous integration; Slurm signals and requeue. <https://github.com/giovtorres/slurm-docker-cluster>, <https://github.com/eWaterCycle/setup-apptainer>, <https://docs.mila.quebec/examples/good_practices/checkpointing/index.html>
- **S19** MLX: converting and quantising a Hugging Face model, fusing adapters, fine-tuning on a Mac; vision models. <https://github.com/ml-explore/mlx-lm>, <https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md>, <https://github.com/Blaizzy/mlx-vlm>
