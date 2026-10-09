# Remote Compute — Running on ACENET (Alliance clusters) — Design Spec (#5642)

> Milestone: remote-compute
> Manual: TBD — the user manual needs "Running on a university cluster": adding ACENET, the one-time
> key, what Fichero asks before pages leave the Mac, watching a run, results coming back.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-10-09 from a design session with
> the maintainer; critique due 2026-10-10 before the request goes to ACENET.** A slice of the compute
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
- A reading run described as a Slurm array under Apptainer (`--nv`), one task per shard, a login-node
  prefetch for IIIF pages, resubmitting only failed shards — VERIFIED `remote_read/slurm.py`.
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
   the folder, Apptainer, the GPU driver version, and stages the image.
2. **Plan.** On a step or a recipe, Where: ACENET. Before anything leaves, the plan in words: pages, model,
   GPUs, GPU hours, time estimate, that pages leave the Mac (asked once per project, as egress already is).
3. **Stage.** Pages as tar shards and the model weights go to `/project` (Globus Transfer for large sets,
   SFTP otherwise). The image is pulled once and shared.
4. **Submit.** One Slurm job: an array of batches, throttled (`--array=0-N%K`), the allocation named,
   a warning signal before walltime (`--signal=B:USR1@300`). Large models: the model server (vLLM) starts
   across the job's GPUs and must answer before any batch reads.
5. **Watch.** `sacct -j <id> --parsable2` every few minutes while the app (or the coordinator) is open;
   each batch writes `done/<n>.json` or `failed/<n>.json`. One Activity row: queued, running N of M, done.
6. **Bring back.** Finished batches' results (Parquet shards: text, lines, names, dates, page references,
   optionally embeddings) are downloaded as they land and folded in exactly once, with provenance (job,
   node, model, image digest). Failed batches can be resent alone. The run folder is cleaned up.

### Who talks to the cluster

- **A. The Mac app** over SSH in the engine (`asyncssh`, bundled; not the `ssh` program). Before
  automation-node access: one MFA push at submit, the connection kept for the session. After: the
  automation node with a constrained key, nothing asked.
- **B. Globus Compute** (if ACENET supports endpoints): an endpoint submits Slurm jobs for us, sign-in
  through the institution; preferred over our own SSH if available. TO CONFIRM.
- **C. An always-on coordinator** (the full Linux image on an Alliance Cloud VM or a lab server) that the
  app pairs with: watches with the laptop closed, shared by a lab, moves data on the fast network.
  Built on A or B. Target for labs.

### Two images (`linux-server-image.md`)

- **Worker** (cluster jobs): readers (Kraken, YOLO, spaCy), vLLM, training (FSDP), the page loader, the
  runner. No API server, DuckDB, LanceDB, MCP or CLI. Multi-arch (amd64, arm64); Apptainer from the
  Docker image. CUDA build no newer than the cluster's driver.
- **Coordinator**: the full engine (#5640 for its LLM runtime).

### Model sizes (planning estimates, H100 80 GB; to be measured on Rorqual)

| Model | Reading | Fine-tuning | Weights |
|---|---|---|---|
| 3–8B | MIG slice or 1 GPU | 1 GPU | 6–16 GB |
| 32B | 1 GPU 16-bit, or 4-bit on a slice | QLoRA 1 GPU; LoRA 2–4 | ~64 GB |
| 70B | 2 GPUs 16-bit (tensor parallel), or 1 GPU 4-bit | QLoRA 1–2; LoRA a 4-GPU node (FSDP) | ~140 GB |

### At scale: 1,000,000 IIIF pages

Fetch outside the cluster's limits (coordinator VM or a route ACENET recommends), politely (a few requests
a second, honour the server's limits: about 3 days at 4/s), at the reader's size (e.g. 2000 px long side:
0.5–1 TB, not several TB). The project keeps IIIF references, not copies. Roughly 300–800 GPU-hours for a
32B model (twice for 70B): a RAC-sized request; a 1,000-page pilot measures the real rate first.

### Rehearsal before ACENET (maintainer 2026-10-09: know it works before the cluster)

Three layers, cheapest first; each is a test environment for the same runner:

1. **Scheduler logic, no GPU:** Slurm in Docker on the M4 (submit, arrays, `sacct` states, timeout,
   requeue, failed batches). Free; runs in the test suite.
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
nodes, GPU types and limits. So a cluster profile records the site's choices: scheduler (Slurm first;
LSF and PBS later if needed), container runtime, how unattended access works (automation node, MFA per
session, Globus Compute), transfer (Globus or SFTP), allocation, GPU types, walltime limit, and whether
compute nodes are online. ACENET (Rorqual) is the first profile; others (for example Princeton's
Research Computing clusters, Penn's, the US ACCESS resources) are added by filling a profile and running
Test Connection, each site's details CONFIRMED with that site rather than assumed.

## Behaviors

- `compute.hpc.key-once` — **[GAP]** (#5642) Fichero makes the key; the person pastes the public half into CCDB once; the private half is in the Keychain; no `~/.ssh` access.
- `compute.hpc.test-connection` — **[GAP]** (#5642) checks the folder, Apptainer, the allocation and the GPU driver against the image's CUDA, and stages the image.
- `compute.hpc.plan-before-send` — **[GAP]** (#5642) pages, model, GPUs, GPU hours and that pages leave the Mac, shown and agreed before anything is sent.
- `compute.hpc.stage-as-shards` — **[GAP]** (#5642) pages travel as tar shards; tasks unpack to `$SLURM_TMPDIR`; nothing stays in `/scratch`.
- `compute.hpc.submit-array` — **[GAP]** (#5642) one throttled array per run with the allocation, the walltime signal and the model server for large models.
- `compute.hpc.status-from-sacct` — **[GAP]** (#5642) status from `sacct` and batch markers, every few minutes; one Activity row; picked up again on reopen.
- `compute.hpc.failure-states-in-words` — **[GAP]** (#5642) TIMEOUT resumes; OUT_OF_MEMORY resizes; NODE_FAIL and PREEMPTED requeue; FAILED shows the log; a batch failing twice is set aside.
- `compute.hpc.resume-long-training` — **[GAP]** (#5642) a fine-tune checkpoints at the warning signal and continues in a dependent job.
- `compute.hpc.results-exactly-once` — **[GAP]** (#5642) results fold in once, with job, node, model and image digest, even if downloaded twice or resubmitted.
- `compute.hpc.mfa-modes` — **[GAP]** (#5642) one MFA push per session before automation-node access; none after.
- `compute.hpc.slim-worker-image` — **[GAP]** (#5642) the worker image carries only what jobs need, multi-arch, Apptainer-ready.
- `compute.hpc.rehearsed-before-a-cluster` — **[GAP]** (#5642) the runner passes Slurm-in-Docker (logic), a paid GPU (the work) and a rented Slurm+Apptainer machine (the whole flow) before a real cluster.
- `compute.hpc.site-profiles` — **[GAP]** (#5642) a cluster profile holds the site's scheduler, container runtime, unattended-access mode, transfer, allocation, GPU types, walltime and compute-node internet; nothing is ACENET-only.
- `compute.hpc.iiif-at-scale` — **[GAP]** (#5642) a million-page IIIF run fetches politely at reader size outside the login node, keeps references, and starts with a measured pilot.

## Test matrix

| Leg | This surface? | Pins | File |
|---|---|---|---|
| Backend (pytest) | y | plan, sbatch script, sacct parsing, failure states, exactly-once folding | `fichero-server/tests/unit/remote_read/` |
| Integration (Slurm in Docker on the M4) | y | submit, array, sacct, timeout and requeue against a real Slurm | TBD |
| Image | y | worker image builds for amd64 and arm64, passes the import check | TBD |
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
