# Remote Compute — Running on ACENET (Alliance clusters) — Design Spec (#5642)

> Milestone: remote-compute
> Manual: TBD — the user manual needs "Running on a university cluster": adding ACENET, the one-time
> key, what Fichero asks before pages leave the Mac, watching a run, results coming back.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass 2026-10-09 from a design session with
> the maintainer; critiqued 2026-10-10 (the Critique section below, folded into the design and behaviours).** A slice of the compute
> set: read `remote-compute.md` and `linux-server-image.md` first. Behaviours are **[GAP]** (#5642) unless tagged otherwise; **[BROKEN]** where today's code contradicts the line.
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
   own key; the public half goes into CCDB; the private half stays in the engine's own key folder (mode 0700, readable only by the engine), not the Keychain. Test Connection checks
   the folder, Apptainer, the GPU driver version, and that the image is there. The image is never built
   on the cluster: CI builds the Apptainer image and publishes it to a registry (an OCI/ORAS artifact); it is pulled once onto `/project` from a data-transfer node (or uploaded from the Mac), never on a login node and never inside a job (compute nodes are offline).
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
6. **Bring back.** Finished batches' results (one PAGE XML per page in each batch's tar, plus `_outcome.json`; the format `format.import` lands today; see the result-format decision below) are downloaded as they land and folded in exactly once, with provenance (job,
   node, model, image digest). Failed batches can be resent alone. The run folder is cleaned up.

### The target: SlurmTarget behind the read-at-scale loop

The read-at-scale loop (`remote_read/job.py`: package, shards, submit, poll, fetch, land, resend, cancel) already talks to its target through one small interface (`send/submit/statuses/status/fetch_part/cancel/last_lines/price_per_hour`, `training/hf_jobs.py`). A `SlurmTarget` implements that interface. The cluster gets no second runner (`compute.job.one-runner`). Bulk moves by Globus; small sets by the SSH carrier.

**Result format (A0 default, 2026-10-17; for the manager to ratify):** one PAGE XML per page, one tar per batch, plus `_outcome.json`, landed by `format.import` as a new pass. `transfer-and-results.md` still describes `records.jsonl` for clusters; that is open until reconciled.

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
4. **File-count quotas** on `/project`: shards and per-batch tars, never one file per page.
5. **Batches sized to the walltime classes** that are scheduled soonest; the classes live in the profile.
6. **vLLM offline batch inference**, not a server (as `jobs-and-fine-tuning.md` already says).
7. **MFA without automation access means attended runs.**
8. **Cut for the first version:** the coordinator on an Alliance Cloud VM, LSF and PBS, the arm64 worker
   image, and the vLLM server mode.

Adopted rather than written: Globus Transfer (Alliance endpoints), Globus Compute if ACENET runs endpoints,
vLLM offline inference, `resume_from_checkpoint` with `--requeue` for training, `sacct` as it is.

## Behaviors

- `compute.hpc.key-once` — **[GAP]** (#5642) Fichero makes the key; the person pastes the public half into CCDB once; the private half is in the engine's own key folder (mode 0700), not the Keychain; no `~/.ssh` access.
- `compute.hpc.test-connection` — **[GAP]** (#5642) checks the folder, Apptainer, the allocation and the GPU driver against the image's CUDA, and stages the image.
- `compute.hpc.plan-before-send` — **[GAP]** (#5642) pages, model, GPUs, GPU hours and that pages leave the Mac, shown and agreed before anything is sent. (#5642) `dry-run-submit` (`api/routes/ai/hpc.py`) builds one array index per INPUT FILE, right for a workflow run and wrong for a page read: it must also take the pages and show K, the pages in each task, the `--array` line, GPU-hours and the queue wait (`sinfo`) before anything is sent. Dry-run only, tested on the fake login shell; no submission, no cluster spend.
- `compute.hpc.stage-as-shards` — **[PARTIAL]** (#5457) local pages travel downscaled (longer side `fetch.longest`) as one tar per shard (`pack_shards`); the runner unpacks its tar to `$SLURM_TMPDIR` and removes it after. Not yet: the upload itself (Globus/SFTP), per-batch result tars. Test: `fichero-server/tests/unit/remote_read/test_read_package.py`.
- `compute.hpc.sbatch-fits-the-site` — **[OK]** (#5457) the script names the allocation, a typed GPU (`--gres=gpu:h100:1`), `--signal=B:USR1@120` and `--requeue`, sets `HF_HUB_OFFLINE=1` (compute nodes are offline), and names a partition only when the person gave one. Test: `fichero-server/tests/unit/remote_read/test_read_on_slurm.py`.
- `compute.hpc.slurm-target` — **[PARTIAL]** (#5457) `SlurmTarget` (`remote_read/slurm_target.py`) has the surface `HfJobsTarget` has (send, submit, statuses, status, fetch_part, last_lines, cancel) over a `Shell` seam, tested against a fake login shell. `SshShell` drives the system `ssh` with one ControlMaster connection (no new dependency; asyncssh ruled out, 2026-10-17) and refuses without a key. Not yet: the second factor passed through the app (it is answered where ssh asks), the engine-held key, and a real cluster `target` (`read-at-scale` takes `target`; `SlurmReadTarget` runs the loop over a fake login shell, one single-task `sbatch --array=<n>` per shard, results home as one tar; a cluster is refused by name until the key and sign-in exist). Test: `fichero-server/tests/unit/remote_read/test_slurm_target.py`.
- `compute.hpc.submit-array` — **[GAP]** (#5642) one Slurm job per recipe step, each a throttled array with the allocation and the walltime signal; large models read by vLLM offline batch inference inside the task, no server. (#5642; owner, 2026-10-19; plan in `briefs/speed-many-pipelines-2026-10-19.md`) A run of P pages is ONE array of K tasks, each reading its own slice with its own model load. WHAT EXISTS: `remote_read/slurm.py` DESCRIBES such an array (a task per shard, sparse resubmit `--array=3,7`), but the run path does not use it: `SlurmReadTarget` sends one single-task `sbatch --array=<n>` PER SHARD, K separate submissions. The gap is to submit the run as one array. K = ceil(P / pages per task), pages per task from `size_run` (measured rate, shortest walltime class), then clamped by the queue limits (`MaxArraySize`, most jobs one person may queue; pages per task grows until K fits) and throttled (`--array=0-K-1%T`). Not built: the one-array submit and the clamp.
- `compute.hpc.nothing-heavy-on-a-login-node` — **[BROKEN]** (#5642; `remote_read/slurm.py:63-69` prefetches IIIF pages on the login node) no image build, page fetch or weight copy runs on a login node; the image comes from CI by pull, pages and weights by Globus or a data-transfer node.
- `compute.hpc.batches-fit-the-walltime` — **[PARTIAL]** (#5642, #5566; the sizing rule is `remote_read/sizing.py` `size_run`, tested in `fichero-server/tests/unit/remote_read/test_sizing.py`: shortest class, 20% margin, more shards for a slow reader, GPU-hours from the rate; not yet fed by a real pilot or the plan) a batch is sized from measured pages per second to finish inside the site profile's shorter walltime class.
- `compute.hpc.shards-not-files` — **[PARTIAL]** (#5457) the package no longer copies a full-size file per image: pages are downscaled and packed as a tar per shard (`remote_read/package.py`). Results still return as one PAGE XML per page, not a per-batch tar. Test: `fichero-server/tests/unit/remote_read/test_read_package.py`.
- `compute.hpc.status-from-sacct` — **[PARTIAL]** (#5457) one `sacct` call covers every task of the array and is read into the job row's words (`remote_read/slurm_target.py`). Not yet: the poll every few minutes, one Activity row, picked up on reopen. Test: `fichero-server/tests/unit/remote_read/test_slurm_target.py`. (#5642) Activity shows ONE row for the run, "Reading on <cluster>: 7 of 12 tasks done, 2 running, 1 waiting in the queue, 2 failed · 3,400 of 6,000 pages", from that one `sacct` call plus the pages landed so far; a task's own line says its state and its last log lines; results land as each task finishes, not only at the end.
- `compute.hpc.failure-states-in-words` — **[PARTIAL]** (#5457) TIMEOUT, OUT_OF_MEMORY, NODE_FAIL, PREEMPTED, FAILED and CANCELLED are said in words from `sacct`. Not yet: TIMEOUT resumes, OUT_OF_MEMORY resizes, NODE_FAIL/PREEMPTED requeue, a batch failing twice is set aside. Test: `fichero-server/tests/unit/remote_read/test_slurm_target.py`. (#5642) A failed task fails only ITS pages ("pages 1,501 to 2,000: out of memory, 2 tries"); the run's other pages land and stay. Retry is per task (the sparse array), once automatically for NODE_FAIL/PREEMPTED, with a smaller slice for OUT_OF_MEMORY and TIMEOUT; a task that fails twice is set aside and offered as "Read these pages again".
- `compute.hpc.resume-long-training` — **[PARTIAL]** (#5642, #5240; `training/resumable.py`, see `compute.tune.survives-the-time-limit`; test `fichero-server/tests/unit/training/test_resumable_training.py`; the continuation is the same job re-queued, not a dependent job) a fine-tune checkpoints at the warning signal and continues in a dependent job.
- `compute.hpc.results-exactly-once` — **[GAP]** (#5642) results fold in once, with job, node, model and image digest, even if downloaded twice or resubmitted.
- `compute.hpc.mfa-modes` — **[GAP]** (#5642) one MFA push per session before automation-node access, and the run is attended (watching stops when the session lapses, said in words); none after.
- `compute.hpc.slim-worker-image` — **[PARTIAL]** (#5642, #5241) the worker image carries only what jobs need, amd64, built and published by CI, Apptainer-ready. Built: `fichero-server/docker/worker.Dockerfile` (the runner's own PEP 723 dependencies, no MLX, an ordinary user) and `.github/workflows/worker-image.yml` (amd64 build, import check, publish to ghcr.io from main). Not yet: CI has not run it; vLLM/CUDA (A2); the Apptainer pull on a cluster. Test: `fichero-server/tests/unit/remote_read/test_worker_image.py`.
- `compute.hpc.rehearsed-before-a-cluster` — **[GAP]** (#5642) the runner passes Slurm-in-Docker in CI (logic), a paid GPU (the work) and a rented Slurm+Apptainer machine (the whole flow) before a real cluster.
- `compute.hpc.site-profiles` — **[GAP]** (#5642) a cluster profile holds the site's scheduler, container runtime, unattended-access mode, transfer, allocation, GPU types, walltime and compute-node internet; nothing is ACENET-only.
- `compute.hpc.iiif-at-scale` — **[GAP]** (#5642) a million-page IIIF run fetches politely at reader size off the login nodes, keeps references, and starts with a measured pilot.
- `compute.hpc.vllm-offline-reader` — **[PARTIAL]** (#5566; A2) a vision-model read step with `engine: vllm` loads the model once per task and answers every line of a page in ONE batched call (vLLM offline inference inside the task's own process, no server), tensor-parallel across the job's GPUs when the step names it; a line with no writing is dropped as in the Transformers reader. Built: `runner.py` `vllm_reader`, `ReadStep.engine`; tested with a fake `vllm` module in `fichero-server/tests/unit/remote_read/test_vllm_reader.py`. The GPU variant is `fichero-server/docker/worker-gpu.Dockerfile` (the slim worker plus a pinned vLLM, no MLX), built by `worker-image.yml` only on `workflow_dispatch`; guard-tested in `test_worker_image.py`. Not yet: CI has built it, a run on a real GPU.
- `compute.job.one-runner-line-cut` — **[PARTIAL]** (#5240, review debt) the line cut and the answer parser are ONE implementation (`llm/line_cut.py`): the line reader imports it, the package ships it beside the runner as `_fichero/line_cut.py`, and the runner uses it (it had drifted: the text "null" landed as a line's text on a cluster). Test: `fichero-server/tests/unit/remote_read/test_one_line_cut.py`. Not yet: the sbatch default `runner/run_task.py` of `build_remote_run_spec` is a second, workflow runner path that nothing runs.
- `compute.hpc.slurm-target-behind-read-at-scale` — **[PARTIAL]** (#5457, #5238) the loop runs unchanged against `SlurmReadTarget` over a fake login shell (`test_the_same_loop_reads_on_a_cluster`); not yet against a real cluster or Slurm-in-Docker. A `SlurmTarget` implements the read-at-scale target interface; the loop's package, shard, submit, poll, fetch, land and resend steps run unchanged against it. *Test:* the read-at-scale loop against Slurm-in-Docker lands its pages as a pass.


## Test matrix

| Leg | This surface? | Pins | File |
|---|---|---|---|
| Backend (pytest) | y | plan, sbatch script, sacct parsing, failure states, exactly-once folding | `fichero-server/tests/unit/remote_read/` |
| Integration (Slurm in Docker, in CI) | y | submit, array, sacct, timeout and requeue against a real Slurm | TBD |
| Image | y | worker image builds for amd64 in CI, passes the import check, published for `apptainer pull` | `fichero-server/tests/unit/remote_read/test_worker_image.py` |
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
