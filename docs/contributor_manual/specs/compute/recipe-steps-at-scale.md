# A recipe's steps on Hugging Face or ACEnet, batched and resumable — PROPOSED (#5642, #6233)

> **Status: PROPOSED 2026-10-27, for the owner to approve.** Nothing here is built by this doc. It extends
> `compute/hpc-runner-acenet.md` (the cluster, its rules, `SlurmTarget`) and
> `ui/activity-and-automatic-work.md` `activity.lane.scale-out-batches-and-result-files` (K tasks of S pages, the retry
> ladder, result files, the one sheet) and `activity.run.cloud-batch` (a place per step). Those lines keep their ids
> and their rules; this doc adds what they leave open: a RECIPE of several steps, run at a remote place in a logical
> order, in batches, stopped and started without redoing anything, toward 100,000 pages.

## Intent

The owner's north star (2026-10-27): the engine grinds through 100,000 images over time, alone or with cloud models
and HPC; batches; stop and start cleanly (resume, nothing redone); a logical order; and the app shows which steps are
done on each folder, kept current while it runs. Today `remote_read/job.py` ships ONE step (read at scale) to
Hugging Face Jobs or a Slurm cluster, shard by shard. A recipe is several steps (find the lines, read them, find the
names, embed), and the steps that are not reading still run on this Mac.

## What exists (read 2026-10-27)

- `remote_read/job.py`: `start` (the consent gate `pages_may_leave`), `run` (package once; submit up to
  `max_in_flight`; one `statuses` a round; `land_shard`), `resend_failed`, `request_cancel`, `catch_up` (after a
  restart), shard states in the job's detail (`pending`, `submitted`, `landed`, `failed`).
- `remote_read/package.py` (`pack_shards`, `build_read_package`), `remote_read/runner.py` (`run_shard` on the remote
  side, PAGE XML + `_outcome.json`; a rerun skips sources already written), `land_shard` skips pages already imported
  by checksum.
- `remote_read/slurm_target.py` `SlurmReadTarget` (one single-task `sbatch --array=<n>` per shard; tested on a fake
  shell only) and `remote_read/slurm.py` `describe_slurm_read` (a true array, not yet used);
  `training/hf_jobs.py` `HfJobsTarget` (send, submit, statuses, fetch_part, cancel).
- `remote_read/sizing.size_run`; `api/routes/ai/hpc.py` (clusters, keys, second factor, dry run).
- A recipe run's checkpoint: `recipes/runner.py` `detail["batches_done"]`, `detail["batch_states"]` (a step ended on
  a batch is not run again); per-page step state in `recipes/done.py` (`pages_with_readings`, `lines_states`).
- No code: Hugging Face Inference Endpoints; provider Batch APIs (`ai.where.provider-batch-is-an-offer`, #5940).

## The design

### Units: a batch × a run of steps at one place

A recipe run is already cut into batches (a folder, or up to about 500 pages; `source.recipe.batch-checkpoint`).
Each step has a place (`activity.run.cloud-batch`: local, a cloud model, Hugging Face Jobs, a cluster). Consecutive
steps of a batch that share a remote place are FUSED into one remote stage: the images go once, the task runs those
steps one after another on each of its pages, and returns every step's result files together. A step whose place is
this Mac runs here as today. So a recipe "lines (Kraken) → read (VLM) → names (spaCy) → embed" with lines and read
on ACEnet and the rest local is, per batch: one remote stage (lines + read), then two local steps on the landed text.

### Order: step-major inside a batch, batches pipelined

Inside a batch the order is the recipe's (a step never starts on a page before the step it needs has landed for that
page), and each model loads once per task (`activity.run.stage-by-stage-no-model-juggling`). Across batches the
stages pipeline: while batch b's remote stage is queued or running, batch b-1's local steps run here, so neither the
cluster nor the Mac waits on the other. At most two batches are in flight per remote place (one running, one queued),
so a stop leaves little half-done.

### State: what is done is what has landed

The plan (batches, stages, places, K and S per stage) is stored on the run's row when it starts. A page's step is done
when its result has LANDED in the library (`recipes/done.py`'s state, the same rule the local steps use), never when a
task said so. A task's result is landed in one batched pass per task, as it returns (`compute.land.idempotent`), so a
partial return counts. On Start again, Resume, an engine restart (`catch_up`), or a new run over the same folder, the
plan is made again from the done state: a page whose step has landed is not sent, and a task still running remotely
is adopted by its id, not submitted twice. Same input and same model reuse the result (`never rerun a model pass`, #6127).

### Stop and start

Stop cancels the queued and running tasks (`scancel` on the array, HF's cancel) and keeps everything landed; a task's
files that arrive after a Stop are still landed (they are paid for). Pause leaves running tasks to finish and submits
nothing new. Both say so on the run's row in words ("Stopped: 3,400 of 6,000 pages read on ACEnet; nothing read is
lost").

### Shown

Activity's run row draws one strip per remote stage (`activity.lane.scale-out-batches-and-result-files`), and each
folder shows which steps are done on it (the counts from the done state, kept current as tasks land). The one sheet
before anything is sent covers the whole recipe: per stage its place, pages, tasks, time and cost, and the local
estimate beside it.

### Slow-path logs at scale

Each task's compute record (per page: time per step, the model load count and time, peak RSS) is landed with its
results; the run logs one line when a stage's per-page time climbs across tasks, or a task loads a model more than
once, the same thresholds as a local run.

## Behaviors

- `compute.recipe.fuse-same-place-steps` — **[GAP]** (#5642, PROPOSED) consecutive steps of a batch at the same
  remote place run as one remote stage: the images are sent once and each step's result files return together.
  *Test (to write):* `fichero-server/tests/unit/remote_read/test_recipe_steps_at_scale.py`.
- `compute.recipe.step-major-batches-pipelined` — **[GAP]** (#5642, PROPOSED) inside a batch the steps run in the
  recipe's order, a model loading once per task; batch b's remote stage overlaps batch b-1's local steps; at most two
  batches in flight per remote place. *Test (to write):* the same file.
- `compute.recipe.done-is-landed` — **[GAP]** (#5642, #6127, PROPOSED) a page's step is done when its result has
  landed; a rerun, resume or restart plans from the done state, sends no landed page, and adopts a task still running
  by its id. *Test (to write):* the same file.
- `compute.recipe.stop-keeps-what-landed` — **[GAP]** (#5642, PROPOSED) Stop cancels queued and running tasks and keeps
  everything landed, landing results that arrive after it; Pause submits nothing new. *Test (to write):* the same file.
- `compute.recipe.folder-shows-steps-done` — **[PARTIAL]** (#5642, PROPOSED) each folder shows which steps are done on it,
  current while tasks land. Built for local steps as `activity.run.folder-steps-done` (ui/activity-and-automatic-work.md,
  its own test); owed here: a remote stage's landed tasks counted as they land.
- `compute.recipe.task-compute-record-landed` — **[GAP]** (#5642, PROPOSED) each task's per-page compute record lands with
  its results and feeds the run's slow-path lines. *Test (to write):* the same file.

## Order of work (proposed)

1. `SlurmReadTarget` submits one array per stage (`describe_slurm_read`), and the login-node prefetch goes
   (`compute.hpc.submit-array`, `compute.hpc.nothing-heavy-on-a-login-node`).
2. `run_shard` runs a list of steps per page (lines, then read), not only read; its result files per step.
3. The recipe runner hands a batch's same-place steps to `remote_read/job.py` as one stage and waits on its landing;
   `done-is-landed` replans on resume.
4. The pipelining of batches; the folder's steps-done counts.
5. A rehearsal on a local Slurm container (`compute.hpc.rehearsed-before-a-cluster`), then one 500-page batch on
   ACEnet, then Hugging Face Jobs with the same stage.

## Open questions for the owner

1. Text steps (names, embed) on the remote too, or always here? They are light per page but 100,000 pages of
   embedding is hours on one Mac.
2. Two batches in flight per place: enough to keep a cluster queue fed, or should the queue limit (`%M`) decide?
3. Hugging Face: Jobs only (as built), or Inference Endpoints too for a model with no Job image?
</content>
</invoke>
