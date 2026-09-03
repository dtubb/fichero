# Fichero ⇄ HPC (Slurm) — Live Connection Plan

**Date:** 2026-09-02
**Status:** DESIGN — no code modified. For review by Andy first, then the HPC provider
(§9 is the provider-facing section). Directed by Daniel; this document paraphrases his
intent into spec prose.
**Verified against:** the `integration` worktree — `workflows/remote_jobs.py`,
`workflows/run_status.py`, `workflows/run_steps.py`, `execution/runner.py`,
`api/change_stream.py`, `docs/contributor/remote-backend-acenet.md`,
`docs/contributor/remote-backend-tailscale.md`.

## 0. What this is

Fichero should be able to run a workflow — the same workflow a user picks today over a
selection of documents — on an academic HPC cluster running Slurm, from inside the app,
with results landing in the library **as they complete**. Not "export a batch, run it by
hand, import the results": the user presses run, the cluster does the work, and pages
light up in the library one by one.

Two prior-art documents already exist and stay valid; this plan is their complement,
not their replacement:

- `docs/contributor/remote-backend-acenet.md` — run the **whole engine** on the cluster,
  SSH-forward loopback to the Mac. Good for "my library lives on the cluster".
- `docs/contributor/remote-backend-tailscale.md` — loopback engine + `tailscale serve`
  for a lab machine. Good for a persistent second machine you own.

This plan covers the third and most common case: **the library and the engine stay on
the Mac; the cluster is a compute provider.** The cluster never holds the library, never
holds an API token, and never runs a Fichero engine.

And there is a head start in the tree: `fichero_server/workflows/remote_jobs.py` already
contains pure, tested building blocks for exactly this — `RemoteConnectionConfig`,
`SlurmJobConfig`, `BundleManifest`, `build_slurm_script()` (sbatch rendering), and
`parse_squeue_output()`. It is built-but-unwired (only `test_remote_jobs.py` imports
it). The plan below is largely "wire this module up", per the iterate-never-replace
rule.

## 1. Topology — three options, one recommendation

### Option A — engine-orchestrated SSH + Slurm CLI (recommended)

The Mac engine opens **outbound SSH** to the cluster login node and drives everything
through the ordinary Slurm CLI: `rsync` the input bundle up, `sbatch` an array job,
poll `squeue`/`sacct`, `rsync` results down as they appear. The compute job itself is a
self-contained batch runner staged with the bundle; it writes result files to scratch
and exits. Nothing on the cluster talks back to the Mac — the Mac *pulls*.

- **No inbound connections anywhere.** All sockets are outbound SSH from the Mac. The
  engine stays loopback-bound; no new listener is added on either side, so the
  fail-closed transport invariants (wildcard binds refused, app pins loopback TLS) are
  untouched rather than extended.
- **Provider footprint is indistinguishable from a normal user.** SSH in, `sbatch`,
  `squeue`, `rsync`. No daemon on the login node, no persistent allocation, nothing an
  acceptable-use policy has to make an exception for.
- **Restartable by construction.** The durable state is (job id, remote workdir,
  manifest) recorded on the run row. If the Mac sleeps or the SSH drops, the Slurm job
  keeps running; on wake the engine reconnects and re-polls `sacct` — no state was
  lost because no state lived in the connection.
- **The engine remains the only library writer.** Results come back as files; the
  engine lands them through its existing artifact write path with full provenance.
  Cluster code never sees the DuckDB, the API, or a bearer token.

### Option B — a Fichero agent/runner on the cluster that pulls work and pushes results

A long-lived runner process (on the login node, or as a persistent job) polls for work
and POSTs results back through a reverse SSH tunnel to the Mac engine. Rejected for v0–v2:

- A persistent process on a login node is exactly what academic providers prohibit; as
  a persistent *job* it burns allocation while idle.
- Pushing results means the cluster holds a Fichero API token and the engine's write
  surface is reachable from a shared multi-user machine — a new trust boundary the
  fail-closed model would have to be widened to admit, for no capability Option A lacks.
- Two schedulers (Slurm plus our runner's queue) where one suffices.

The one thing Option B buys — sub-second result latency instead of poll-interval
latency — does not matter for jobs whose unit of work is an LLM call over a page image.

### Option C — REST via `slurmrestd`

Where the provider enables `slurmrestd`, submission and status become HTTPS calls
instead of `ssh sbatch` / `ssh squeue`. This is strictly a nicer *submission channel*:
it does not move data, so rsync-over-SSH remains regardless. Most academic sites do not
expose it. **Design decision: isolate submission/status behind a small
`SlurmSubmitter` seam** (two implementations: `SshCliSubmitter` now, `RestdSubmitter`
if the provider offers it) so Option C is an upgrade, not a fork. It is question #1 for
the provider (§9), not a dependency.

**Recommendation: Option A**, with the submitter seam so C can slot in later. B is not
planned at any phase.

## 2. Data flow

### Up: staging a run

1. The user picks a workflow and a selection in the app, exactly as today. The client
   sends what the user pointed at; the **engine** resolves the document set (the
   #4396/#4419 rule — the cluster path changes nothing about scope resolution).
2. The engine builds a **bundle** under a run-scoped remote workdir
   (`$SCRATCH/fichero/runs/<run_id>/`):
   - `manifest.json` — `BundleManifest` (already implemented): workflow id/name, run
     id, the input file list, metadata (model name, prompt/config per step).
   - `inputs/` — the page images / PDFs for the selected documents. Images are
     rendered/normalized engine-side first (same renditions the local vision tools
     use), so the cluster job needs no PDF stack.
   - `job.sh` — rendered by `build_slurm_script()` (already implemented).
   - `runner/` — the worker environment reference (§6).
3. Transfer is `rsync -a --partial` over SSH with a ControlMaster-multiplexed
   connection. rsync gives resumability (a dropped transfer restarts where it left
   off) and idempotency (re-staging an already-staged run is a fast no-op) for free —
   no custom transfer protocol.
4. Batching: inputs are laid out one directory per array index
   (`inputs/000/`, `inputs/001/`, …), one document (or one page-chunk for large
   documents) per index. The layout **is** the array mapping — no separate index file
   to drift.

### Down: results, live

Each array task writes, atomically (`tmp` + rename), into `results/<index>/`:

- `result.json` — the artifact payloads for that document: transcription text, region
  geometry, structured extraction — the same shapes the local tools emit, so the
  landing code is shared, not parallel.
- `done` / `failed` — completion marker; `failed` carries the typed failure kind
  (mirroring the per-page failure-kind vocabulary `vision_base` uses locally, so a
  cluster failure renders in the compare/summary UI the same way a local one does).

The engine's poll loop (§3) lists new markers, rsyncs **only those** result directories
down, and lands each one through the existing artifact write path — the same audited
layer every local tool uses. Nothing else writes the library. Each landed artifact is a
normal `RunStepArtifact` with the provenance fields that already exist (`run_id`,
`workflow_id`, `step_name`, `provider`, `model`) **plus** the Slurm coordinates:

- `provider` = the actual model provider that ran (`vllm`, `tesseract`, …) so the
  existing "provider · model" provenance line stays truthful about what produced the
  text;
- execution-site provenance (`hpc/slurm`, cluster name, Slurm job id, array index)
  goes on the run/step record and into artifact metadata — recorded once at the write,
  queryable forever. Job id on the artifact's provenance trail is a hard requirement:
  it is the researcher's receipt and the support ticket's key.

Because landing goes through the engine's write path, the change stream
(`api/change_stream.py`) emits at the write — every open client (app, CLI, MCP) sees
the page complete without a refresh. That is the "live" in live updates; no new
mechanism is needed, only the discipline of landing through the front door.

Embeddings: **not** computed on the cluster in v0–v1. The engine embeds landed text
locally, as it does for local runs — one embedding path, one LanceDB writer. Cluster
embedding is a v2 option if volumes demand it (and then it returns vectors as result
files, landed the same way).

## 3. Job model — Slurm ⇄ Fichero run lifecycle

**One Fichero workflow run over N documents = one Slurm array job**
(`--array=0-{N-1}%<throttle>`), one task per document/chunk. One job id to record,
cancel, and account; per-document states come from array-task states; the `%throttle`
respects provider fairness policy.

The run's canonical lifecycle is the closed `RunStatus` enum (`accepted → running →
paused → completed | failed | cancelled`). **No new client-visible states.** Slurm
states map in, they do not leak out:

| Slurm (job/task)                  | Fichero run/step |
|-----------------------------------|------------------|
| `PENDING`, `CONFIGURING`          | `running`, step detail "queued on cluster (position via `squeue`)" |
| `RUNNING`                         | `running` |
| `COMPLETED` (task)                | that document's step `completed` (on successful **landing**, not on Slurm exit) |
| `FAILED`, `TIMEOUT`, `OUT_OF_MEM…`| that document's step `failed`, with the Slurm state string preserved in the step's failure detail |
| `CANCELLED`                       | `cancelled` |

A task is complete when its results are **landed in the library**, not when Slurm says
it exited — Slurm exit is a signal to go fetch, never the source of truth. The run
completes when every array task is terminal and every completed task's results are
landed; it fails/partially-completes with per-document detail exactly as a local run
does today.

**Polling.** A single engine-side poll loop per active remote run: every ~30–60s (a
provider-friendly cadence — question #7 in §9), one `sacct -j <jobid> --parsable2`
call plus one marker listing, over the multiplexed SSH connection. `sacct` rather than
`squeue` alone, because `squeue` forgets finished jobs — `parse_squeue_output()` is
kept for queue-position detail while the job is pending.

**Reconnect / resume.** The run row persists `{cluster, job_id, remote_workdir,
manifest_hash}` at submission time. Engine restart, Mac sleep, or SSH drop → on the
next poll tick the engine reconnects and continues; landed-artifact records tell it
which result indices are already down. The existing run-recovery sweep treats a remote
run with a live job id as legitimately `running`, not stuck.

**Idempotent re-submission.** The remote workdir is keyed by `run_id`. Re-running:
staging is an rsync no-op for unchanged inputs; array indices with a `done` marker are
excluded from the new `--array` list (Slurm takes sparse index lists), so a re-submit
after a partial failure runs only the missing documents. Submitting while the recorded
job id is still alive in `sacct` is refused with the job id in the error — fail
loudly, never a silent duplicate job.

**Cancel** in the workflow-execution UI issues `scancel <jobid>`, then marks the run
`cancelled`; results already landed stay (they are real artifacts with real provenance).

## 4. Security and auth

- **Per-user SSH keys, standard OpenSSH.** The engine shells out to `ssh`/`rsync`
  using the user's own `~/.ssh` configuration (a named `Host` alias). Keys live in
  `ssh-agent` / the macOS keychain as the user already manages them; **Fichero stores
  no key material** — the library/app DB records only the host alias, username, remote
  base directory, and default partition. This follows the existing rule that
  credentials in the DB are at most a keychain/agent *reference*, never a secret.
- **ControlMaster multiplexing** (`ControlPersist`) so one authenticated session
  carries staging, polling, and fetching — one MFA touch per session if the provider
  enforces interactive MFA (question #6, §9).
- **Login node vs compute node.** On the login node: `sbatch`, `sacct`, `rsync`,
  marker listing — seconds of CPU per minute, within any acceptable-use policy. All
  model inference runs inside Slurm-allocated compute jobs. Nothing persistent runs
  anywhere on the cluster.
- **No tokens on the cluster.** The cluster job reads its inputs from its workdir and
  writes files. It has no Fichero credential, no callback URL, no network dependency
  on the Mac. Compromise of the cluster account exposes the staged documents (a real
  consideration for sensitive archives — flagged as provider question #8) but cannot
  touch the library.
- **Transport invariants unchanged.** The engine's bind rules, the app's pinned
  loopback TLS, and the refusal of wildcard binds are not modified by this feature.
  This plan adds outbound SSH client behavior only.
- **Cleanup.** `results/` and `inputs/` under the run workdir are removed after a run
  is fully landed (retention window configurable), both as scratch-quota hygiene and
  as data-minimization for the documents themselves.

## 5. Software on the cluster

- **Worker environment: Apptainer (Singularity) container, preferred; uv-managed venv
  as fallback.** Academic clusters near-universally support Apptainer and
  near-universally frustrate bespoke Python environments (old glibc, no root, license
  walls). We publish one image per release —
  `fichero-hpc-runner:<version>` — containing the runner and its inference stack. The
  venv fallback (`uv sync` against a committed lockfile in the runner bundle) covers
  clusters without container support. Provider question #4 decides which is primary.
- **The runner is deliberately small.** It is not the engine: no FastAPI, no DuckDB,
  no LanceDB. v0 is a standalone script (`runner/run_task.py`) that reads
  `manifest.json` + one input directory, calls the model, writes `result.json`.
  Later phases may factor the relevant `workflows/tools/` model-calling code into an
  importable "worker mode" so prompt/parsing logic is shared with the engine rather
  than duplicated — but the boundary stays: workflow orchestration, scope resolution,
  and all persistence are engine-side; the cluster executes one task.
- **Models: MLX does not travel.** MLX is Apple-silicon-only; on HPC the local-model
  tier becomes CUDA — **vLLM serving an open vision/HTR model** (e.g. Qwen2.5-VL
  class) inside the job allocation, or CPU OCR (Tesseract/Kraken) on CPU partitions
  for the cheap tier. Weights are pre-staged into project space (not scratch, which
  purges; not home, which is small) by a one-time setup step, because compute nodes
  frequently have no internet egress (question #5). Hosted-API providers (Anthropic
  etc.) stay engine-side — there is no reason to proxy an API call through a cluster,
  and egress rules would likely forbid it anyway.
- **What stays engine-side:** workflow definitions, scope resolution, prompt/config
  assembly into the manifest, PDF rendering/renditions, embedding, all DB writes, the
  change stream, cost/usage accounting (fed by per-task usage counts in
  `result.json` plus `sacct` elapsed/TRES data).

## 6. UI surface

- **v0: none** (CLI-driven, §7).
- **v1: an "HPC cluster" provider row in AI settings**, alongside the existing
  provider rows (and consistent with the standing MLX-as-first-class-provider-row
  direction): host alias, username, remote base dir, default partition/account, a
  *Test connection* button (SSH reachability + `sinfo` + scratch writability), and a
  clear "uses your SSH key from the keychain/agent" affordance. Per the two-toggles /
  no-needless-toggles rule: configuring the row makes the capability available;
  routing decides use.
- **Routing like model tiers.** A workflow step that today picks a provider/model
  gains "HPC" as a routable execution site, surfaced the same way model tiers are in
  the workflow bar — not a global mode switch. A run mixing engine-side steps and
  cluster steps is a v2 concern; v1 routes whole runs.
- **The existing workflow-execution UI is the status surface.** Because §3 maps
  everything into the existing run/step model and artifacts stream in through the
  change stream, the activity/run views work unchanged; the only additions are detail
  strings (queue position, Slurm job id, cluster name) on the run and steps.

## 7. Phasing and rough effort

**v0 — Andy can demo it.** Wire `remote_jobs.py` end to end for **one** workflow
(transcription), driven by the CLI (`fichero hpc run …` or a dev-tier route), manual
SSH/host setup, venv or container by hand on the cluster. Array job, poll loop,
results landing as real artifacts with full provenance, visible live in the app via
the change stream. No settings UI, no routing UI. *Effort: ~1–2 focused agent-weeks;
the Slurm-facing third already exists as tested code.*

**v1 — a user can do it.** HPC provider row in AI settings (§6), keychain/agent-backed
key selection, per-run routing in the workflow launch surface, run detail showing
queue position and job id, cancel via `scancel`, cleanup + retention setting,
hardened resume paths (sleep/drop/restart tests), containerized runner published per
release. *Effort: ~3–4 agent-weeks across backend + SwiftUI + release scripting.*

**v2 — it scales politely.** Sparse-array resubmission polish, chunked multi-page
documents, throttle/quota awareness (`sshare`/`diskusage` checks before staging),
per-task usage → cost accounting via `sacct`, streamed job logs into run detail,
mixed-site runs (some steps local, some cluster), optional `RestdSubmitter` if the
provider enables `slurmrestd`, optional cluster-side embedding. *Effort: incremental;
each item ~days, scheduled by demand.*

Sequencing note: v0 deliberately precedes any schema/UI work so the provider
conversation (§9) is informed by a working prototype, not projections.

## 8. Testing

The existing pattern extends naturally: `remote_jobs.py` stays pure and unit-tested;
the submitter seam gets a fake (`FakeSubmitter` scripted with state sequences) so the
poll loop, state mapping, resume, and idempotent-resubmit logic are all testable
without a cluster — including the ugly cases (job vanished from `sacct`, marker
present but `result.json` unparsable → that task `failed` loudly, never a silent
skip). One opt-in integration test (env-gated, like the write-suites) runs against a
real or containerized Slurm.

## 9. What we need from the provider

Framed as questions; none block v0 on a standard allocation.

1. **`slurmrestd`** — is it enabled or enableable for us? (Nice-to-have; we work over
   SSH CLI regardless.)
2. **Partitions and hardware** — which partitions may we use; GPU types and memory;
   typical queue waits; max walltime and max array size per job.
3. **Storage** — home/project/scratch quotas; scratch purge policy; is project space
   suitable for ~10–100 GB of model weights.
4. **Containers** — Apptainer/Singularity available on compute nodes? Any registry
   restrictions on pulling images?
5. **Network egress from compute nodes** — any internet access (for one-time weight
   downloads), or must everything be pre-staged via the login node?
6. **Authentication** — SSH key policy; is interactive MFA enforced per connection,
   and is `ControlMaster` persistence acceptable? Any session-length limits?
7. **Automation policy** — is an application polling `sacct` + rsyncing results every
   ~30–60s from a user's machine acceptable login-node usage? Preferred cadence?
8. **Data governance** — the inputs are digitized archival documents, occasionally
   under access restrictions; where may they be stored, and is scratch acceptable for
   transient processing?
9. **Account model** — per-user submission is our design (each researcher uses their
   own allocation); is a service/instrument account available or preferable from your
   side?
10. **Support channel** — a named contact for the pilot, and whether a short
    technical call to review this section is possible.

## 10. Decisions, restated

1. **Topology A**: engine-orchestrated outbound SSH + Slurm CLI; a submitter seam
   keeps `slurmrestd` as a drop-in upgrade; no cluster-resident agent, ever, at any
   phase.
2. **The engine remains the only library writer**; cluster results are files, landed
   through the existing artifact path with provider/model **and** Slurm job-id
   provenance, emitting change-stream events at the write — that is what makes the
   library update live.
3. **One workflow run = one Slurm array job**; Slurm states map into the closed
   `RunStatus` vocabulary; completion means *landed*, not *exited*; resume and
   re-submission are idempotent via run-keyed workdirs and done-markers.
4. **No secrets move**: SSH via the user's own keys/agent, config references only in
   the DB, no Fichero token on the cluster, transport invariants untouched.
5. **Apptainer-first runner, vLLM/CUDA (or CPU OCR) instead of MLX**, weights
   pre-staged in project space; the runner is a task executor, not an engine.
6. **Build on `remote_jobs.py`** — the module was written for this and is waiting to
   be wired.
