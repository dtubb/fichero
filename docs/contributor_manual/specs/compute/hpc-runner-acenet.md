# Remote Compute — Running on ACENET (Alliance clusters) — Design Spec (#5642)

> Milestone: remote-compute
> Manual: TBD — the user manual needs "Running on a university cluster": adding ACENET, the one-time
> key, what Fichero asks before pages leave the Mac, watching a run, results coming back.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-10-09 from a design session with
> the maintainer; critiqued 2026-10-10 (the Critique section below, folded into the design and behaviours).** A slice of the compute
> set: read `remote-compute.md` and `linux-server-image.md` first. Every behaviour is **[GAP]** (#5642).
> Claims about our code are **VERIFIED** (with a path) or **INFERRED**; claims about the Alliance are
> **CITED** (Sources below) or **TO CONFIRM** with ACENET.
> Shareable summary and the questions for ACENET: https://claude.ai/artifact/KYaVjiLFk4r3WKUAtiUrne

## Intent

A researcher whose project is too big for the Mac (a 32B–70B model, or a million IIIF pages) sends the
heavy work to ACENET's GPUs and gets the results back into the project, without learning Slurm. Two
kinds of work: **reading** (inference: a large model reads pages) and **fine-tuning by distillation**
(a large teacher answers corrected pages; a small 3–8B student is trained on them and comes back to run
on the Mac with MLX). The project, corrections and review stay on the Mac; the cluster sees only what a
run needs.

**Ruled 2026-10-09: don't write our own where an established tool does it.** Slurm's own features,
Globus Transfer and (if supported) Globus Compute, vLLM for serving, FSDP for training. Fichero's runner
stays thin: it decides what runs, shows the plan and GPU hours, and folds results back exactly once
with provenance.

## What exists today

- Cluster profiles: `/api/hpc/clusters` (host alias, user, project folder; the person's own key)
  — VERIFIED `api/routes/ai/hpc.py`, `workflows/remote_jobs.py`.
- A reading run described as a Slurm array under Apptainer (`--nv`), one task per shard, resubmitting only
  failed shards — VERIFIED `remote_read/slurm.py`. It prefetches IIIF pages on the login node, which the
  cluster's rules below forbid at any size: that prefetch moves off the login node (Critique, 2).
- Dry run ("show me what will run") — VERIFIED `hpc/dry-run-submit`.
- Live submission is disabled (`SshCliSubmitter`, `compute.job.live-submit`) — VERIFIED. As designed it
  shells out to `ssh`/`rsync` and reads `~/.ssh`, which the sandboxed app cannot do (#4555) — INFERRED
  from the sandbox rules in `sandbox-refuses-downloaded-code`.

## The cluster's rules (CITED)

- Login nodes: light work only (about 10 CPU-minutes and 4 GB; 400% CPU, 4G memory, 4 sessions per
  user); no servers or model runs. [S1][S2]
- Compute nodes have no internet (Rorqual "designed for scientific calculations that do not require
  access to the internet"). [S3]
- SSH requires multifactor authentication; unattended workflows use **automation nodes**: CCDB-uploaded
  constrained keys only, no PTY or forwarding, access granted by support after describing the commands.
  [S4] Hostnames and the allowed-command options are TO CONFIRM.

## The design

### Flow (what the researcher sees)

1. **Set up once.** Add the cluster (host, user, project folder, allocation account). Fichero makes its
   own key; the public half goes into CCDB; the private half stays in the Keychain. Test Connection checks
   the folder, Apptainer, the GPU driver version, and that the image is there. The image is never built
   on the cluster: CI builds the Apptainer image and publishes it to a registry (an OCI/ORAS artifact); the
   cluster pulls it once, on a data-transfer node or inside a job, never on a login node.
2. **Plan.** On a step or a recipe, Where: ACENET. Before anything leaves, the plan in words: pages, model,
   GPUs, GPU hours, time estimate, that pages leave the Mac (asked once per project, as egress already is).
3. **Stage.** Pages as tar shards and the model weights go to `/project` by Globus Transfer through the
   Alliance's endpoints (SFTP only for small sets); 140 GB of 70B weights never pass through a login node.
   Shards, not one file per page: `/project` has file-count quotas that a million pages would break. The
   image is pulled once and shared.
4. **Submit.** One Slurm job per recipe step (the chain `remote-compute.md` describes), each an array of
   batches, throttled (`--array=0-N%K`), the allocation named, a warning signal before walltime
   (`--signal=B:USR1@300`). A batch is sized to finish inside the site's shorter walltime class (jobs of
   about 3 h or 12 h are scheduled sooner; the classes are in the site profile, TO CONFIRM). Large models
   read with vLLM's offline batch inference inside each task's own process, tensor-parallel across the
   job's GPUs: no server to start and wait for. The GPU request (`--gpus=h100:1`, MIG slice names) is the
   site profile's, TO CONFIRM.
5. **Watch.** `sacct -j <id> --parsable2` at the interval `compute.job.poll-is-gentle` sets, while the app is open;
   each batch writes `done/<n>.json` or `failed/<n>.json`. One Activity row: queued, running N of M, done.
6. **Bring back.** Finished batches' results (Parquet shards: text, lines, names, dates, page references,
   optionally embeddings) are downloaded as they land and folded in exactly once, with provenance (job,
   node, model, image digest). Failed batches can be resent alone. The run folder is cleaned up.

### Who talks to the cluster

- **A. The Mac app** over SSH in the engine (`asyncssh`, bundled; not the `ssh` program). Before
  automation-node access: one MFA push at submit, the connection kept for the session; when the session
  lapses, watching stops until the person signs in again, so without automation access a run is an
  attended run. After: the automation node with a constrained key, nothing asked.
- **B. Globus Compute** (if ACENET supports endpoints): an endpoint submits Slurm jobs for us, sign-in
  through the institution; preferred over our own SSH if available. TO CONFIRM.
- **C. An always-on coordinator** (the full Linux image on a lab server) that the app pairs with: watches
  with the laptop closed, shared by a lab. Built on A or B. **Not in the first version** (Critique, 8): an
  Alliance Cloud VM needs its own cloud allocation and still needs automation access.

### Two images (`linux-server-image.md`)

- **Worker** (cluster jobs): readers (Kraken, YOLO, spaCy), vLLM, training (FSDP), the page loader, the
  runner. No API server, DuckDB, LanceDB, MCP or CLI. amd64 only (the clusters' GPU nodes); Apptainer from
  the Docker image, built in CI. CUDA build no newer than the cluster's driver.
- **Coordinator**: the full engine (#5640 for its LLM runtime).

### Model sizes (planning estimates, H100 80 GB; to be measured on Rorqual)

| Model | Reading | Fine-tuning | Weights |
|---|---|---|---|
| 3–8B | MIG slice or 1 GPU | 1 GPU | 6–16 GB |
| 32B | 1 GPU 16-bit, or 4-bit on a slice | QLoRA 1 GPU; LoRA 2–4 | ~64 GB |
| 70B | 2 GPUs 16-bit (tensor parallel), or 1 GPU 4-bit | QLoRA 1–2; LoRA a 4-GPU node (FSDP) | ~140 GB |

### At scale: 1,000,000 IIIF pages

Fetch off the cluster's login nodes (on the Mac, a lab server, or a data-transfer node ACENET recommends), politely (a few requests
a second, honour the server's limits: about 3 days at 4/s), at the reader's size (e.g. 2000 px long side:
0.5–1 TB, not several TB). The project keeps IIIF references, not copies. Roughly 300–800 GPU-hours for a
32B model (twice for 70B): a RAC-sized request; a 1,000-page pilot measures the real rate first.

### Rehearsal before ACENET (maintainer 2026-10-09: know it works before the cluster)

Three layers, cheapest first; each is a test environment for the same runner:

1. **Scheduler logic, no GPU:** Slurm in Docker in CI (submit, arrays, `sacct` states, timeout,
   requeue, failed batches). Free. Not on the M4, which is usable only when idle and on power.
2. **The GPU work itself:** the worker image on a paid GPU: Hugging Face Jobs (already used for vision
   LoRA training, #5398) or a rented GPU machine. Proves the image, vLLM serving, 32B/70B memory, LoRA
   training, and measures pages per second. Not Slurm, so it does not test the runner.
3. **A full rehearsal:** a rented GPU machine (one or a few H100s by the hour) set up like a cluster:
   Slurm and Apptainer installed, outbound internet blocked on the "compute" side, a login side with
   internet. The whole flow runs against it exactly as it would on ACENET. A few dollars an hour.

Only after layer 3 passes does the request go to a real cluster.

### Other sites (not only Canadians)

Nothing here is ACENET-only. Most university and national clusters use Slurm and Apptainer (Singularity),
Globus for data and an allocation account; they differ in MFA, automation access, internet on compute
nodes, GPU types and limits. So a cluster profile records the site's choices: scheduler (Slurm only for
now), container runtime, how unattended access works (automation node, MFA per
session, Globus Compute), transfer (Globus or SFTP), allocation, GPU types, walltime limit, and whether
compute nodes are online. ACENET (Rorqual) is the first profile; others (for example Princeton's
Research Computing clusters, Penn's, the US ACCESS resources) are added by filling a profile and running
Test Connection, each site's details CONFIRMED with that site rather than assumed.

## Critique (2026-10-10)

What holds: a thin runner over Slurm's own features; throttled arrays; the walltime warning signal;
checkpoint then a dependent job; `sacct --parsable2` with done/failed markers and failed shards resent
alone; unpacking to `$SLURM_TMPDIR`; tar shards; the rehearsal ladder; a 1,000-page pilot before a RAC
request; site profiles as data. What changed, each folded in above:

1. **No image building on a login node.** Converting a multi-GB CUDA image to a `.sif` exceeds the login
   node's limits. CI builds and publishes it; the cluster pulls.
2. **No IIIF fetching on a login node**, at any size (today's `remote_read/slurm.py` does): the Mac, a lab
   server or a data-transfer node fetches.
3. **Weights staged by Globus or a data-transfer node**, never through a login node.
4. **File-count quotas** on `/project`: shards and Parquet results, never one file per page.
5. **Batches sized to the walltime classes** that are scheduled soonest; the classes live in the profile.
6. **vLLM offline batch inference**, not a server (as `jobs-and-fine-tuning.md` already says).
7. **MFA without automation access means attended runs.**
8. **Cut for the first version:** the coordinator on an Alliance Cloud VM, LSF and PBS, the arm64 worker
   image, and the vLLM server mode.

Adopted rather than written: Globus Transfer (Alliance endpoints), Globus Compute if ACENET runs endpoints,
vLLM offline inference, `resume_from_checkpoint` with `--requeue` for training, `sacct` as it is.

## Behaviors

- `compute.hpc.key-once` — **[GAP]** (#5642) Fichero makes the key; the person pastes the public half into CCDB once; the private half is in the Keychain; no `~/.ssh` access.
- `compute.hpc.test-connection` — **[GAP]** (#5642) checks the folder, Apptainer, the allocation and the GPU driver against the image's CUDA, and stages the image.
- `compute.hpc.plan-before-send` — **[GAP]** (#5642) pages, model, GPUs, GPU hours and that pages leave the Mac, shown and agreed before anything is sent.
- `compute.hpc.stage-as-shards` — **[GAP]** (#5642) pages travel as tar shards; tasks unpack to `$SLURM_TMPDIR`; nothing stays in `/scratch`.
- `compute.hpc.submit-array` — **[GAP]** (#5642) one Slurm job per recipe step, each a throttled array with the allocation and the walltime signal; large models read by vLLM offline batch inference inside the task, no server.
- `compute.hpc.nothing-heavy-on-a-login-node` — **[GAP]** (#5642) no image build, page fetch or weight copy runs on a login node; the image comes from CI by pull, pages and weights by Globus or a data-transfer node.
- `compute.hpc.batches-fit-the-walltime` — **[GAP]** (#5642) a batch is sized from measured pages per second to finish inside the site profile's shorter walltime class.
- `compute.hpc.shards-not-files` — **[GAP]** (#5642) pages travel and results return as shards (tar in, Parquet out), never one file per page on `/project`.
- `compute.hpc.status-from-sacct` — **[GAP]** (#5642) status from `sacct` and batch markers, every few minutes; one Activity row; picked up again on reopen.
- `compute.hpc.failure-states-in-words` — **[GAP]** (#5642) TIMEOUT resumes; OUT_OF_MEMORY resizes; NODE_FAIL and PREEMPTED requeue; FAILED shows the log; a batch failing twice is set aside.
- `compute.hpc.resume-long-training` — **[GAP]** (#5642) a fine-tune checkpoints at the warning signal and continues in a dependent job.
- `compute.hpc.results-exactly-once` — **[GAP]** (#5642) results fold in once, with job, node, model and image digest, even if downloaded twice or resubmitted.
- `compute.hpc.mfa-modes` — **[GAP]** (#5642) one MFA push per session before automation-node access, and the run is attended (watching stops when the session lapses, said in words); none after.
- `compute.hpc.slim-worker-image` — **[GAP]** (#5642) the worker image carries only what jobs need, amd64, built and published by CI, Apptainer-ready.
- `compute.hpc.rehearsed-before-a-cluster` — **[GAP]** (#5642) the runner passes Slurm-in-Docker in CI (logic), a paid GPU (the work) and a rented Slurm+Apptainer machine (the whole flow) before a real cluster.
- `compute.hpc.site-profiles` — **[GAP]** (#5642) a cluster profile holds the site's scheduler, container runtime, unattended-access mode, transfer, allocation, GPU types, walltime and compute-node internet; nothing is ACENET-only.
- `compute.hpc.iiif-at-scale` — **[GAP]** (#5642) a million-page IIIF run fetches politely at reader size off the login nodes, keeps references, and starts with a measured pilot.

## Test matrix

| Leg | This surface? | Pins | File |
|---|---|---|---|
| Backend (pytest) | y | plan, sbatch script, sacct parsing, failure states, exactly-once folding | `fichero-server/tests/unit/remote_read/` |
| Integration (Slurm in Docker, in CI) | y | submit, array, sacct, timeout and requeue against a real Slurm | TBD |
| Image | y | worker image builds for amd64 in CI, passes the import check, published for `apptainer pull` | TBD |
| MCP / CLI | y | plan and submit through the generated tools | `fichero-mcp/tests/` |

## Open questions (for the critique and for ACENET)

The questions sent to ACENET are on the shared page (automation nodes, Globus Compute, large-model GPU
jobs and walltimes, MIG, shared weights, image pulls, array limits, a cloud coordinator, checkpointing,
the CUDA driver, rights-restricted images, where a million downloads should happen). For the critique:
whether A, B or C comes first; whether Globus Compute replaces our SSH entirely; the exact contents of
the worker image; how results shards map onto the project's archive model.

## Sources

- [S1] https://docs.alliancecan.ca/wiki/Translations:Running_jobs/112/en — login-node exceptions.
- [S2] https://docs.alliancecan.ca/wiki/Special:MobileDiff/137397 — login-node per-user limits.
- [S3] https://alliancecan.ca/en/services/compute/rorqual — Rorqual overview.
- [S4] https://docs.alliancecan.ca/wiki/Automation_in_the_context_of_multifactor_authentication — automation nodes.
