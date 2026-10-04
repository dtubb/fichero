# Remote Compute — The Linux server image — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — nothing here is shown to a researcher except one line on a target's row: what
> the server there is, its version, and what it can and cannot run. The contributor manual
> needs "Building and testing the Linux image", written from the built behaviour.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-09-20; revised
> 2026-10-03 against the maintainer's rulings (`remote-compute.md`, "Ruled 2026-10-03";
> the review appendix in `remote-compute.md`).** A slice of the compute set: read `remote-compute.md` first. Every
> behaviour is **[GAP]** with its issue (#5241); none is built. Claims about our code are **VERIFIED** with a line or **INFERRED**; claims about
> outside services are **CITED** (S-numbers refer to "Sources" in `remote-compute.md`) or
> **UNVERIFIED**.

## Intent

There is one `fichero-server`. On the Mac it is packaged by Briefcase inside the app. For
Linux it is published as a container image. It is the same code, answering the same API, so
everything the Mac app, the command line and the MCP tools can ask of one they can ask of the
other. The image leaves out what only Apple hardware can do, and says so when asked, instead
of failing when tried. It runs with the network switched off, because that is what a cluster's
compute node is. Nobody builds it by hand: the project's automation builds it, starts it, runs
a job through it, and only then publishes it.

## What exists today

- A Dockerfile and a README: `fichero-server/docker/Dockerfile` (66 lines),
  `fichero-server/docker/README.md`. `python:3.12-slim`; `pip install .`; a non-root user; port
  8765; the library mounted at `/data` (VERIFIED `Dockerfile:31-66`).
- It already records the right idea: the same image by `docker run` on a rented GPU, or turned
  into an Apptainer file for a cluster (VERIFIED `Dockerfile:8-11`).
- It has no GPU base, no Kraken, no inference engine and no training libraries. Kraken on the
  Mac installs itself later into its own environment with `pip`, which needs the internet
  (VERIFIED `llm/kraken_runtime.py:352-381`); a compute node has none.
- It sets the engine to listen on every interface, using the engine's deliberate escape hatch
  (VERIFIED `Dockerfile:61-63`; `security/bind_host.py:49-56`). The remote-backend document calls
  that hatch "not the supported remote-backend model"
  (VERIFIED `docs/contributor_manual/remote-backend-acenet.md:145-150`).
- A request that does not come from loopback is refused unless it carries a paired device's
  token (VERIFIED `api/auth.py:732-735` for the refusal; the device-token branch INFERRED from
  `:727-731`). So a server in a container, reached through Docker's port mapping, can only be
  used by a **paired** client. That is the right rule, and it means installing must end with a
  pairing.
- **Nothing builds this image.** No workflow, no script, no test (VERIFIED: `.github/workflows/`
  holds `ci.yml` and two review workflows, none mentions Docker; INFERRED that it has never been
  built).
- MLX is not among the server's core dependencies, so a Linux install does not trip on it
  (VERIFIED: no `mlx` dependency line in `fichero-server/pyproject.toml`). PyTorch now is, on the
  integration branch (VERIFIED there, `pyproject.toml:317-319`).

## The design (proposed)

### Two images from one recipe

| Image | For | Architectures | Carries |
|---|---|---|---|
| **cpu** | the stand-in on a Mac; a small Linux machine; every automated test | `linux/arm64` and `linux/amd64` | the server, Kraken, spaCy, the workflow runner |
| **gpu** | a GPU machine; a cluster; Hugging Face Jobs | `linux/amd64` | everything in **cpu**, plus the CUDA runtime, vLLM, and the fine-tuning libraries (`transformers`, `peft`, `trl`, `accelerate`, `bitsandbytes`) |

**Built first** (2026-10-03): only what Hugging Face Jobs needs to train: the **gpu** image on
`linux/amd64`, carrying the server, Kraken and the YOLO trainer, with "run a package" mode, and
smoke-tested by automation on CPU (PyTorch's CUDA wheels also run on a CPU; INFERRED, confirmed at the first build). vLLM and the LoRA libraries are
added with their slices; the `arm64` **cpu** image comes with the local stand-in.

Two, because a GPU image is several gigabytes and only runs on one architecture, while the
stand-in on an Apple-silicon Mac must be `arm64` to run at a usable speed: an emulated `amd64`
PyTorch image is slow and can fail outright (CITED, S16). They are built from **one** recipe
with a build argument, so there are not two lists of dependencies to keep in step. Whether the
fine-tuning libraries deserve a third image is a question of measured size, left open until
the first build shows the numbers.

### What is in it, and what is not

- **In:** the server; the one workflow runner; the one trainer (`compute.tune.one-trainer-three-places`);
  Kraken, **installed at build time**, not at first use; the YOLO trainer (Ultralytics, AGPL-3.0,
  the same licence as Fichero; its card says so); spaCy and its small models, as on the Mac; DuckDB; LanceDB; the exporter.
- **Left out, and reported as unavailable:** Apple's on-device model, Apple Vision, Apple
  translation, MLX, and Whisper through MLX.
- **Never in:** any model's weights. Every model is fetched on request, by its card, into a
  model cache on the target, under the licence rule that already exists
  (`source.model.licence-class`, #4948). This keeps the image small, keeps copyleft and
  restricted-licence models out of what Fichero distributes, and means an AGPL-licensed layout
  model is a person's choice, not a default.
- **Never in:** any secret, any project, any person's data.

### Listening

The image listens on **loopback** by default, exactly like the Mac. Two cases widen it, and
only inside a private network:

1. **Under Docker**, a port mapping reaches the container from outside its own network
   namespace, so inside the container the server must listen on the container's interface.
   The image does this only when told to by the one who starts it, and the start command
   Fichero issues always maps the port to the far machine's **loopback** (`127.0.0.1:8765`),
   never to all of its interfaces. From there the Mac reaches it through `tailscale serve` or
   an SSH forward, as the transport rules say.
2. **Under Apptainer on a cluster**, a container shares the node's network with every other
   user's jobs. There the server listens on loopback only, with no exception. A tunnel reaches
   it by jumping through the login node to the compute node (`ssh -J`), which the existing
   recipe already uses (VERIFIED `remote-backend-acenet.md:53-58`). Whether Alliance clusters
   let a person SSH to a node where their job is running is **UNVERIFIED** and is part of the
   cluster slice's first trial.

The baked-in "listen everywhere" setting is removed from the Dockerfile. In every case a
request that is not from loopback needs a paired device's token, as today.

### Offline

A compute node usually has no internet (CITED, S5). So the image must start, report its
health, and run a job with the network switched off, given a model cache and a work package
that were put in place beforehand. Nothing in a job may reach for the network and wait: not
`pip`, not a model hub, not a licence check, not telemetry. For Hugging Face's libraries that
means running with `HF_HUB_OFFLINE=1` and resolving every model from the cache (CITED, S17).

### Two ways to start

- **Serve:** the ordinary server. Used on a machine we control, and by a session.
- **Run a package:** no web server, no port. Read a work package from a folder, run it with the
  one runner, write a result package beside it, exit with a status. Used by every job. This is
  the piece the old plan called `runner/run_task.py` and never wrote (VERIFIED
  `remote_jobs.py:435-442`); it is a mode of the one server, not a second program.

### Release, routed

Where the image is published, how it is numbered, how the Mac app and a server of another
version are kept from talking past each other, and signing: these belong to
`harness/release-and-versioning.md`. The request is item 1 under "Requests to other specs" in
`remote-compute.md`. What this slice fixes is only what the *server* must do so that spec can
hold: report its version and its API contract, and refuse nothing silently.

## Behaviors

All [GAP]: designed, not built. "Data" names what the behaviour reads or writes.

### The image

- `compute.image.one-recipe-two-images` — **[GAP]** (#5241) one Dockerfile builds a **cpu** image (`linux/arm64`
  and `linux/amd64`) and a **gpu** image (`linux/amd64`). The dependency list is the server's
  own `pyproject.toml`; the GPU additions are one named extra in that same file. *Data:*
  `fichero-server/docker/Dockerfile`, `fichero-server/pyproject.toml`. *Existing data:* the
  present Dockerfile is edited in place, not replaced. *Test:* a guardrail fails if the
  Dockerfile installs a package that `pyproject.toml` does not name.
- `compute.image.same-api` — **[GAP]** (#5241) the image serves the same OpenAPI contract as the Mac engine of
  the same version. *Data:* `fichero-server/tests/contracts/openapi.json`. *Test:* in
  automation, the contract fetched from the running container equals the committed one.
- `compute.image.kraken-built-in` — **[GAP]** (#5241) Kraken is present when the container starts; no step at
  run time installs it. *Data:* the image's Python environment; `llm/kraken_runtime.py`'s
  "is it installed" answer. *Existing data:* on the Mac nothing changes; Kraken there is still
  installed on request. *Test:* with the network off, the container segments one page.
- `compute.image.no-weights-no-secrets-no-data` — **[GAP]** (#5241) the published image contains no model
  weights, no credential and no research data. *Test:* automation scans the image's layers for
  files over a size limit with model extensions (`.mlmodel`, `.safetensors`, `.gguf`, `.pt`)
  and for the token file name, and fails on any.
- `compute.image.reports-what-it-can-run` — **[GAP]** (#5241) the health route gains a `capabilities` object:
  platform, architecture, GPU present and its memory, and for each provider kind *available*
  or *unavailable, and why* ("MLX needs Apple silicon"). The app shows it on the target's row.
  *Data:* `GET /api/health` (the existing `remote_backend` block is where this joins; VERIFIED
  `remote-backend-acenet.md:127-139`). *Existing data:* the Mac engine reports the same object,
  so one Swift type reads both. *Test:* on the cpu image, `apple` and `omlx` read unavailable
  with a reason, `kraken` and `spacy` read available, `gpu` is false.
- `compute.image.unavailable-is-refused-not-crashed` — **[GAP]** (#5241) asking the Linux server for an Apple or
  MLX provider returns a typed refusal naming the reason; it never raises an import error and
  never silently uses another model (the project's rule: prefer raise over silent fallback).
  *Data:* the provider resolution in `llm/providers.py`. *Test:* a workflow that names an MLX
  model, sent to the cpu image, fails at the step with that refusal, and the job's state says
  so.
- `compute.image.loopback-by-default` — **[GAP]** (#5241) started with no settings, the server in the image
  listens on `127.0.0.1` only. The Dockerfile bakes in no "listen everywhere" setting.
  *Existing data:* the three `ENV` lines at `Dockerfile:61-63` are removed. *Test:* the
  container's listening sockets, read from inside it, show loopback only.
- `compute.image.never-a-public-port` — **[GAP]** (#5241) the start command Fichero issues on a Linux machine
  maps the port to that machine's loopback, never to all interfaces. *Data:* the command text
  produced by the install step (`targets-and-connection.md`). *Test:* a pure test on the
  command builder: the published-port argument always begins `127.0.0.1:`.
- `compute.image.non-loopback-needs-a-paired-token` — **[GAP]** (#5241) a request arriving through a port
  mapping carries a paired device's token or is refused `403`; the bootstrap token is not
  accepted from there. Built today (VERIFIED `api/auth.py:732-735`); this id exists so a test
  pins it *for the container case*. *Test:* in automation, a request to the mapped port with
  the bootstrap token is refused; with a paired token it succeeds.
- `compute.image.runs-offline` — **[GAP]** (#5241) with the network switched off inside the container, the
  server starts, reports healthy, and runs a job whose models are in the mounted cache.
  *Test:* automation runs the container with no network (`--network none` for the job mode)
  and `HF_HUB_OFFLINE=1`.
- `compute.image.run-a-package-mode` — **[GAP]** (#5241) started in "run a package" mode with a folder, the
  image opens no port, runs the package with the one workflow runner, writes a result package
  into the same folder, and exits `0` on success, non-zero with a written reason on failure.
  *Data:* the work package and result package of `transfer-and-results.md`. *Test:* a tiny
  package (one page, Kraken line-finding) in, a result package out, no listening socket at any
  point.
- `compute.image.runs-as-an-ordinary-user` — **[GAP]** (#5241) the image runs as a non-root user and writes only
  under the folders it is given. Built in the present Dockerfile (VERIFIED `:52-55`); Apptainer
  runs a container as the calling user, so the same must hold there. *Test:* under Apptainer in
  automation, with a read-only image and one writable folder, the tiny job succeeds.
- `compute.image.converts-to-apptainer` — **[GAP]** (#5241) `apptainer build` from the published image yields a
  single file that runs the same tiny job, with `--nv` adding the GPU where there is one.
  *Test:* automation builds the file from the just-built cpu image and runs the tiny job under
  Apptainer (CITED, S18).

### Built and tested with no person involved

- `compute.image.ci-builds-both` — **[GAP]** (#5241) on every change under `fichero-server/` or the Dockerfile,
  automation builds the cpu image on a native `arm64` machine and a native `amd64` machine, and
  the gpu image on `amd64`, with no emulation (CITED, S17). *Data:* a new workflow file under
  `.github/workflows/`. *Test:* the workflow itself; a guardrail checks it exists and names
  both architectures.
- `compute.image.ci-smoke` — **[GAP]** (#5241) for each built image, automation: starts it; polls `/api/health`
  until healthy or a stated time limit; checks `capabilities`; pairs a client; sends the tiny
  job; checks the result package; stops the container; and fails the build on any step, naming
  the step. *Test:* as stated.
- `compute.image.ci-fits-the-build-machine` — **[GAP]** (#5241) the gpu image builds within the disk a free build
  machine offers (about 14 GB; CITED, S17), using the CUDA *runtime* base, not the development
  one. If it cannot, that is reported as a finding with the measured sizes, and the choice of a
  larger build machine or a third image goes to the maintainer. *Test:* the build records the
  final image size as an artefact; a guardrail fails if it grows past a stated budget.
- `compute.image.gpu-path-is-tested-somewhere-named` — **[GAP]** (#5241) free build machines have no GPU, so the
  gpu image's GPU paths (vLLM loading a model, one LoRA step) are **not** proven by the
  automation above. The spec for a release names where they were proven (a named machine, a
  date, the image's digest) or says "not proven on a GPU". *Data:* a line in the release
  record. *Test:* a release guardrail refuses a release record with neither.
- `compute.image.published-only-after-smoke` — **[GAP]** (#5241) an image is published only by the workflow that
  smoke-tested it, from the same build, and carries build provenance. *Routed:* the where and
  the version number are `harness/release-and-versioning.md`'s.

### The stand-in on the maintainer's Mac

- `compute.image.local-stand-in` — **[GAP]** (#5241) the cpu image, run under Docker Desktop on an Apple-silicon
  Mac, is a complete compute target for the purpose of trying the whole loop. It has no GPU
  that PyTorch can use, and its row says "No GPU" (CITED, S16). *Test:* the click-around leg in
  `targets-and-connection.md` (`compute.target.add-local-container`).

### No second way to install the engine

- `compute.image.the-image-is-the-only-install` — **[GAP]** (#5241) on a target, the engine is only ever the
  published image (run by Docker, or as an Apptainer file). Fichero never builds a Python
  environment on a target from a list of packages. *Why:* a cluster's own package builds differ
  from cluster to cluster (CITED, S5) and cannot be tested by the project's automation.
  *Test:* a guardrail: no `pip install` or `virtualenv` appears in any command Fichero sends to
  a target.

## Test matrix

| Leg | This slice? | Pins | File |
|-----|-------------|------|------|
| Pure rule (Swift) | y | reading `capabilities` into the row's wording | a new `compute` group under the Swift unit tests |
| Backend (pytest) | y | `capabilities` on health; typed refusal of an unavailable provider; "run a package" mode against a temp folder | `fichero-server/tests/unit/` |
| Image (continuous integration) | y | every `compute.image.ci-*` behaviour, offline run, Apptainer | `.github/workflows/` |
| Guardrail | y | Dockerfile installs only what `pyproject.toml` names; no weights, secrets or data in layers; size budget | `scripts/check_*.py` |
| MCP / CLI | n | nothing new here | |
| Click-around | n | covered in `targets-and-connection.md` | |

## Open questions

1. **A third image for fine-tuning?** *Proposal: decide from the first build's measured sizes.
   One gpu image if it fits the build machine; otherwise split the training libraries out.*
2. **The base.** *Proposal: NVIDIA's CUDA runtime image of the version PyTorch's current wheels
   are built against, because Alliance H100 nodes are reported to need a recent PyTorch
   (UNVERIFIED, S17). The exact versions are pinned at build time and recorded, not chosen here.*
3. **Should the Mac engine also stop installing Kraken on demand**, now that PyTorch is in the
   bundle? *Proposal: not in this set; it is question 15 of the foundation.*
