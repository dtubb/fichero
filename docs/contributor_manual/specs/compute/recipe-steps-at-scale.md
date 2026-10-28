# A recipe's steps at scale: cloud batch, Hugging Face, ACEnet — batched, resumable — APPROVED (#5642, #5940, #6233)

> Milestone: remote-compute
> Manual: docs/contributor_manual/guide/08-workflows-activity-and-curation.md (the user manual's "Running on a
> university cluster" page grows a "Sending a big run to a cloud provider's batch" section as this is built)
>
> **Status: APPROVED 2026-10-28** (proposed 2026-10-27, revised 2026-10-28 on the owner's direction; the owner took
> the recommended answer to each open question, written in below as rulings). It extends `compute/hpc-runner-acenet.md` (the cluster, its rules, `SlurmTarget`),
> `ui/activity-and-automatic-work.md` `activity.lane.scale-out-batches-and-result-files` (K tasks of S pages, the
> retry ladder, result files, the one sheet) and `activity.run.cloud-batch` (a place per step; a step nobody is
> waiting for goes to the provider's Batch API), and `ai/where-models-run.md` `ai.where.provider-batch-is-an-offer`
> (#5940), `ai.where.batch-results-land-once` (#5945), `ai.where.batch-stop-reaches-the-provider` (#5946). Those
> lines keep their ids and their rules; this doc adds what they leave open: a RECIPE of several steps, run at a
> remote place in a logical order, in batches, stopped and started without redoing anything, toward 100,000 pages.

## Intent

The owner's north star (2026-10-27, ordered 2026-10-28): the engine grinds through 100,000 images over time, alone
or with cloud models and HPC; batches; stop and start cleanly (resume, nothing redone); a logical order; and the app
shows which steps are done on each folder, kept current while it runs. Each step solid before the next, with real
runs and slow-path logs. The order is: **cloud batch first** (the providers' own batch APIs: cheaper, made for big
jobs, and no machine of ours to keep up), **Hugging Face Jobs second** (it exists for one step today), **ACEnet
third** (a rehearsal on a local Slurm container first).

Today `remote_read/job.py` ships ONE step (read at scale) to Hugging Face Jobs or a Slurm cluster, shard by shard. A
cloud model is called one page at a time (`llm/__init__.py:1636-1646`, the network lane). A recipe is several steps
(find the lines, read them, find the names, embed), and the steps that are not reading still run on this Mac.

## What exists (read 2026-10-28)

- `remote_read/job.py`: `start` (the consent gate `pages_may_leave`, `job.py:162`), `run` (package once; submit up
  to `max_in_flight`; one `statuses` a round; `land_shard`), `resend_failed`, `request_cancel`, `catch_up` (after a
  restart), shard states in the job's detail (`pending`, `submitted`, `landed`, `failed`).
- `remote_read/package.py` (`pack_shards`, `build_read_package`), `remote_read/runner.py` (`run_shard` on the remote
  side, PAGE XML + `_outcome.json`; a rerun skips sources already written), `land_shard` skips pages already imported
  by checksum.
- `remote_read/slurm_target.py` `SlurmReadTarget` (one single-task `sbatch --array=<n>` per shard; tested on a fake
  shell only) and `remote_read/slurm.py` `describe_slurm_read` (a true array, not yet used);
  `training/hf_jobs.py` `HfJobsTarget` (send, submit, statuses, fetch_part, cancel).
- `remote_read/sizing.size_run`; `api/routes/ai/hpc.py` (clusters, keys, second factor, dry run).
- A recipe run's checkpoint: `recipes/runner.py` `detail["batches_done"]`, `detail["batch_states"]` (a step ended on
  a batch is not run again; `BATCH_PAGE_LIMIT = 500`, `runner.py:965`); per-page step state in `recipes/done.py`
  (`pages_with_readings`, `lines_states`).
- Cloud calls today: one request per page through `llm/__init__.py` (the OpenAI SDK imported lazily, `:1527`;
  `aiohttp` for the rest, `:2130`; one shared `httpx.AsyncClient`, `:4641`), held in `model_call_slot` (`:1461`) under
  the spend cap (`llm/spend.py`, `holding`) and the egress gate (`llm/egress.py` `require_project_yes`,
  `ai.where.batch-sends-ask-the-project` #5368). The result cache `_LLM_RESULT_CACHE` (`:200-230`) is keyed by
  provider, model, prompt and image hashes.
- **No batch client.** `workflows/validation.py:337` refuses a batch-only model before a run because "Fichero has no
  batch client"; `llm/model_types.py:431` `is_batch_only_model`; `resources/model_prices.json` already lists
  `/v1/batch` among a model's `supported_endpoints`. Hugging Face Inference Endpoints: no code.

## The design

### Units: a batch × a run of steps at one place

A recipe run is already cut into batches (a folder, or up to about 500 pages; `source.recipe.batch-checkpoint`).
Each step has a place (`activity.run.cloud-batch`: local, a cloud model, Hugging Face Jobs, a cluster). Consecutive
steps of a batch that share a remote place are FUSED into one remote stage: the images go once, the task runs those
steps one after another on each of its pages, and returns every step's result files together. A step whose place is
this Mac runs here as today. So a recipe "lines (Kraken) → read (VLM) → names (spaCy) → embed" with lines and read
on ACEnet and the rest local is, per batch: one remote stage (lines + read), then two local steps on the landed text.
A step on a cloud model is its own kind of remote stage: one provider batch per recipe batch (next section).

### Order: step-major inside a batch, batches pipelined

Inside a batch the order is the recipe's (a step never starts on a page before the step it needs has landed for that
page), and each model loads once per task (`activity.run.stage-by-stage-no-model-juggling`). Across batches the
stages pipeline: while batch b's remote stage is queued or running, batch b-1's local steps run here, so neither the
cluster nor the Mac waits on the other. At most two batches are in flight per cluster or Hugging Face place (one
running, one queued), so a stop leaves little half-done; a cloud batch place is wider (open question 2).

### State: what is done is what has landed

The plan (batches, stages, places, K and S per stage) is stored on the run's row when it starts. A page's step is done
when its result has LANDED in the library (`recipes/done.py`'s state, the same rule the local steps use), never when a
task said so. A task's result is landed in one batched pass per task, as it returns (`compute.land.idempotent`), so a
partial return counts. On Start again, Resume, an engine restart (`catch_up`), or a new run over the same folder, the
plan is made again from the done state: a page whose step has landed is not sent, and a task still running remotely
is adopted by its id, not submitted twice. Same input and same model reuse the result (`never rerun a model pass`, #6127).

### Stop and start

Stop cancels the queued and running tasks (`scancel` on the array, HF's cancel, the provider's cancel) and keeps
everything landed; a task's files that arrive after a Stop are still landed (they are paid for). Pause leaves running
tasks to finish and submits nothing new. Both say so on the run's row in words ("Stopped: 3,400 of 6,000 pages read
on ACEnet; nothing read is lost").

### Cloud batch: a recipe step on a provider's batch API

This is the first place to build. The three providers Fichero already calls page by page each have a batch API with
the same shape: send many requests at once, get them answered within a day at half the price, fetch the answers by a
key you chose. Facts checked on the providers' own pages, 2026-10-28:

- **Anthropic Message Batches** (`platform.claude.com/docs/en/build-with-claude/batch-processing`): submitted INLINE,
  one `POST /v1/messages/batches` whose body is a list of requests, each a `custom_id` plus the usual Messages
  params (images allowed). Up to 100,000 requests or 256 MB per batch. Polled by id (`processing_status`:
  `in_progress` → `ended`); fetched as one `.jsonl` from `results_url`, one line per request typed `succeeded`,
  `errored`, `canceled` or `expired` (only `succeeded` is billed). Answered within 24 hours, most within an hour;
  results kept 29 days; `POST .../cancel`. Half the standard price.
- **OpenAI Batch** (`developers.openai.com/api/docs/guides/batch`): submitted as a FILE: upload a `.jsonl`
  (`purpose=batch`; one line per request with `custom_id`, `method`, `url`, `body`; one model per file), then
  `POST /v1/batches` with the file id, the endpoint (`/v1/chat/completions`, `/v1/responses`, `/v1/embeddings`, and
  more) and `completion_window=24h` (the only window). Up to 50,000 requests or 200 MB per file; image inputs as
  `image_url` in a chat body. Statuses `validating`, `in_progress`, `finalizing`, `completed`, `expired`,
  `cancelling`, `cancelled`, `failed`; answers in `output_file_id`, failures in `error_file_id`, matched by
  `custom_id` (order differs). Cancel takes up to ten minutes to settle. Half the standard price.
- **Gemini Batch Mode** (`ai.google.dev/gemini-api/docs/batch-mode`): INLINE (a list of `GenerateContentRequest`,
  suited under about 20 MB) or a FILE (a `.jsonl` through the Files API, up to 2 GB, one key per line). States
  `JOB_STATE_PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `EXPIRED` (48 hours waiting or running).
  Inline batches answer inline; file batches answer as a result file; results kept six weeks. Target 24 hours. Cancel
  and delete. Half the standard price. Its per-account open-job and enqueued-token limits are on the rate-limits
  page, not the batch page: read them before fixing the width (open question 2).

How a recipe step uses it:

- **Above a threshold, a batch; below it, plain calls.** A step on a cloud model whose pages in this run number at
  least the threshold (open question 4; proposed 100) goes as ONE provider batch per recipe batch; below it, or when
  a person is waiting (a Read Now press, a bake-off sample), the pages are called one by one as today. Images are
  sized for the place first (`ai.where.image-sized-for-the-place`), and a recipe batch whose bytes would pass the
  provider's cap (256 MB, 200 MB, 20 MB inline) is cut into as many provider batches as fit; Gemini goes by file for
  any batch with images. A text step (names, embed) on a cloud model batches the same way where the provider's batch
  endpoint takes it (OpenAI `/v1/embeddings` does).
- **One request per page per step, keyed to land once.** The `custom_id` is the result-cache key (provider, model,
  prompt, image hashes; `_vision_cache_key`), so a returned line lands as the same pass a plain call would have
  (`ai.where.batch-results-land-once`), and the same input and model are never sent twice (#6127): a page whose
  cache key already has an answer is left out of the batch.
- **Done is landed; resume adopts by id.** The provider's batch id (and OpenAI's file ids) are written on the run's
  row beside the recipe batch's state the moment the provider acknowledges them. A Resume, restart or new run over
  the same folder finds an open provider batch, adopts it by its id, polls and lands it; it never resubmits those
  pages. A batch id the provider no longer knows (past retention) is dropped and its unlanded pages replanned.
- **Polling, not waiting.** The run polls each open batch on the network lane at a slow cadence (a minute, then
  backing off to five), lands what has arrived, and shows the row in words ("Sent as a batch to Anthropic: 480 pages,
  answered within a day; 0 back so far"). The run's other batches and local steps carry on meanwhile.
- **Errors per request: retry only those.** A line typed `errored`/`expired` (Anthropic), a line in `error_file_id`
  or an `expired` batch (OpenAI), a failed response or `JOB_STATE_EXPIRED` (Gemini) marks that page's step failed
  with the provider's words; the pages that succeeded land regardless. Failed pages are re-sent on the retry ladder
  (`activity.lane.scale-out-batches-and-result-files`): as one smaller provider batch when there are enough of them,
  else as plain calls; a page that fails twice waits for a person's press (`ai.where.batch-results-land-once`).
- **Stop cancels the provider batch and lands what is back.** Stop calls the provider's cancel, keeps polling until
  the batch's state is terminal, lands every succeeded line (they were billed), books what was billed, and only then
  reads "Stopped" (`ai.where.batch-stop-reaches-the-provider`). Pause submits no new batch and leaves open ones to
  finish.
- **Costs on the one sheet.** The sheet before the run shows the batch price (half the listed price per token) per
  step beside the plain-call price and the local estimate; the spend cap reserves the batch's worst case at
  submission and books each line's real usage as it lands (`ai.where.cloud-spend-cap`); a provider's batch price is
  read from `model_prices.json`, and a model with no listed batch price falls back to half the listed price, said on
  the sheet.
- **Consent.** A provider batch is a package that is SENT: it needs the person's `pages_may_leave` for this request
  AND the project's own yes (`egress.require_project_yes`), the same two gates as a read at scale and a training job,
  through the one egress gate (`ai.where.one-egress-gate`). A project that keeps its pages on this Mac never sees a
  batch offered.
- **Batch-only models.** With a batch client, `validation.py:337`'s refusal relaxes for a step whose place is a
  cloud batch; a batch-only model stays refused for a plain call.

### Shown

Activity's run row draws one strip per remote stage (`activity.lane.scale-out-batches-and-result-files`), and each
folder shows which steps are done on it (the counts from the done state, kept current as tasks land). The one sheet
before anything is sent covers the whole recipe: per stage its place, pages, tasks, time and cost, and the local
estimate beside it.

### Slow-path logs at scale

Each task's compute record (per page: time per step, the model load count and time, peak RSS) is landed with its
results; the run logs one line when a stage's per-page time climbs across tasks, or a task loads a model more than
once, the same thresholds as a local run. A provider batch's record is its wait (submitted to answered), its answered
and failed counts, and its billed cost against the sheet's estimate; the run logs one line when a batch waits past
twelve hours or costs more than its estimate.

## Behaviors

- `compute.recipe.fuse-same-place-steps` — **[OK]** (#5642) consecutive steps of a batch at the same
  remote place run as one remote stage: the images are sent once and each step's result files return together.
  Built for the one pair that runs remotely today, Kraken's lines then the read: the plan's read card that carries
  its lines step says `stage: [lines, read]`, `_run_at_scale` sends that stage, `run_shard` finds each page's lines
  once (`<id>.lines.xml`) and the read reads THOSE lines, each step's end and seconds in `_outcome.json`, a rerun
  reading back the lines it found; landing lands the read, or a page's lines alone when its read failed
  (`lines_only`). A text step riding along joins this list when one runs remotely (ruling 1).
  *Test:* `fichero-server/tests/unit/remote_read/test_recipe_steps_at_scale.py`.
- `compute.recipe.step-major-batches-pipelined` — **[GAP]** (#5642) inside a batch the steps run in the
  recipe's order, a model loading once per task; batch b's remote stage overlaps batch b-1's local steps; at most two
  batches in flight per cluster or Hugging Face place. *Test (to write):* the same file.
- `compute.recipe.done-is-landed` — **[PARTIAL]** (#5642, #6127) a page's step is done when its result has
  landed; a rerun, resume or restart plans from the done state, sends no landed page, and adopts a task still running
  by its id. Built: a step's pages are worked out from the done state as it runs (`split_done`); a page's lines landed
  alone count its lines step done; a resumed recipe adopts the read still out under it (`job.out_under`, a paused one
  brought back first) and never sends it again. Not yet: the plan (batches, stages, places) stored on the row at start.
  *Test:* the same file.
- `compute.recipe.stop-keeps-what-landed` — **[GAP]** (#5642) Stop cancels queued and running tasks and keeps
  everything landed, landing results that arrive after it; Pause submits nothing new. *Test (to write):* the same file.
- `compute.recipe.folder-shows-steps-done` — **[GAP]** (#5642) each folder shows which steps are done on it,
  current while tasks land. *Test (to write):* the same file.
- `compute.recipe.task-compute-record-landed` — **[GAP]** (#5642) each task's per-page compute record lands with
  its results and feeds the run's slow-path lines. *Test (to write):* the same file.
- `compute.recipe.cloud-batch-above-threshold` — **[PARTIAL]** (#5940; built: `llm/provider_batch.py` `goes_as_batch`, `cut_to_cap`, one client per API shape over the provider's own SDK, each against a fake of that SDK: Anthropic inline, OpenAI by file, Gemini by file (its inline answers come back by position, not key), `tests/unit/llm/test_provider_batches.py`; the plan places a cloud read of 100 pages or more as `batch` (`start.place_runs`), `cloud_batch.run_step` queues one row, waits and replays the step from the answers, the capture runs below the run machinery (`remote_read/capture.py`, `tests/unit/remote_read/test_capture_run.py`), and a batch-only model passes the preflight inside a batch; the recipe runner's `_run_card` sends a `batch` step there, pinned end to end through the scheduler and the replay (`test_capture_run.py`); not yet: a real run on a provider) a step on a cloud model with at least the
  threshold of pages in a run nobody is waiting for goes as one provider batch per recipe batch (cut to the provider's
  byte cap; Gemini by file when images are in it); below the threshold, or for a press a person waits on, plain calls
  as today; a page whose cache key is already answered is left out. *Test (to write):* the same file, with a fake
  provider per API shape (inline, file, inline-or-file); the builder may split the provider fakes into their own file.
- `compute.recipe.cloud-batch-adopted-by-id` — **[PARTIAL]** (built: `remote_read/cloud_batch.run` saves each batch's ids on the row as the provider acknowledges them, adopts them on a resume, drops a forgotten one (`gone`); the answers file leaves answered keys out of a rerun; a resumed step adopts its row (`cloud_batch.run_step`, reached from the recipe runner); not yet: a real run on a provider; test: `fichero-server/tests/unit/remote_read/test_cloud_batch_job.py`; #5940, #6127) the provider's batch id is on the
  run's row the moment it is acknowledged; a resume, restart or new run adopts an open batch by its id and never
  resubmits its pages; an id the provider has forgotten is dropped and its unlanded pages replanned. *Test (to
  write):* the same file.
- `compute.recipe.cloud-batch-retries-failed-requests-only` — **[PARTIAL]** (built: answered lines are kept whatever the others did; a failed line is not kept, so a rerun sends it alone and the replay asks it as a plain call; not yet: wired into the recipe runner; test: `fichero-server/tests/unit/remote_read/test_cloud_batch_job.py`; #5940) a batch's succeeded lines
  land whatever the others did; its errored or expired lines mark those pages failed in the provider's words and are
  re-sent alone, as a smaller batch or plain calls, never the whole batch again. *Test (to write):* the same file.
- `compute.recipe.cloud-batch-stop-cancels` — **[PARTIAL]** (built: `request_cancel` marks the row; the run cancels at the provider, polls each batch to its end, keeps the answered lines, then reads Stopped; not yet: wired into the recipe runner; test: `fichero-server/tests/unit/remote_read/test_cloud_batch_job.py`; #5940, #5946) Stop cancels the provider batch, polls
  it to a terminal state, lands and books every succeeded line, and only then reads Stopped; Pause submits no new
  batch. *Test (to write):* the same file.
- `compute.recipe.cloud-batch-consent-and-cost` — **[PARTIAL]** (built: `cloud_batch.start` refuses without the request's yes, the app's cloud place or the project's own yes, nothing queued; the key comes from the Keychain per send and is never stored; the cap holds each batch's worst case at the batch price from submission (`spend.reserve_batch`, the hold on the row and held again on adoption) and books its lines' cost at the price list's batch rates, else half the listed ones; a batch that would pass the cap is never sent; the sheet prices a step the plan sends as a batch at the batch price, said in words (`start.estimate`); not yet: a real batch billed and checked against the estimate (#6251); test: `fichero-server/tests/unit/remote_read/test_cloud_batch_job.py`; #5940) a provider batch needs `pages_may_leave`
  and the project's yes through the one egress gate; the one sheet shows its half price beside the plain-call and
  local estimates, the cap reserves its worst case at submission and books real usage as lines land. *Test (to
  write):* the same file.
- `compute.recipe.cloud-batch-slow-path-record` — **[OK]** (#5940, #6251; each batch's `sent_at`, `ended_at`,
  `waited_hours`, counts and billed tokens on the row, one log line past twelve hours; the row keeps the sheet's
  estimate (`estimate_usd`, by `start.estimate`'s rule) and the billed total (`cost_usd`), one log line when over; test:
  `fichero-server/tests/unit/remote_read/test_cloud_batch_job.py`) a provider batch's wait, counts and billed cost land
  with its results; a batch past twelve hours or over its estimate logs one line.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | Activity's own spec draws the run's strips and counts | — |
| Availability (Swift) | n | — | — |
| Backend (pytest) | y | a stage runs its steps in order, the read reading the lines found; each step's file and seconds return; a rerun does nothing again; fusing, adopt by id, Stop, the batch clients against fakes per API shape | `fichero-server/tests/unit/remote_read/test_recipe_steps_at_scale.py` |
| MCP | n | the run is read through the existing `fichero_recipes_run_status` | — |
| CLI | n | — | — |
| Click-around (XCUITest, Mac) | n | Activity's spec owns the window's UI test | — |
| iPhone (iOS) | n | — | — |
| iPad | n | — | — |
| Load (#4634) | y | the real runs of the order of work (500 pages, then 5,000 to 10,000) with their slow-path records read afterwards | booked on the M4 through the manager, not a suite |

## Order of work (reordered 2026-10-28)

1. **The shared multi-step stage.** `run_shard` runs a list of steps per page (lines, then read), not only read, with
   result files per step; the recipe runner hands a batch's same-place steps to `remote_read/job.py` as one stage
   and waits on its landing; `done-is-landed` replans on resume; the folder's steps-done counts. Tested on this Mac
   with the local place standing in for a remote one.
2. **Cloud batch.** One batch client per provider shape (Anthropic inline, OpenAI file, Gemini inline or file) behind
   one interface (submit, status, fetch, cancel), keyed by the cache key; the threshold; adopt by id; retry failed
   lines only; Stop; the sheet and the cap; the consent gates. Real run: one 500-page batch per provider on a project
   that allows cloud, then a weekend's 10,000 pages, with the slow-path record read afterwards.
3. **Hugging Face Jobs.** The stage of step 1 on `HfJobsTarget` (send, submit, statuses, fetch_part, cancel exist);
   the pipelining of batches, two in flight. Real run: one 500-page batch, then 5,000.
4. **Slurm and ACEnet.** `SlurmReadTarget` submits one array per stage (`describe_slurm_read`), the login-node
   prefetch goes (`compute.hpc.submit-array`, `compute.hpc.nothing-heavy-on-a-login-node`); a rehearsal on a local
   Slurm container (`compute.hpc.rehearsed-before-a-cluster`), then one 500-page batch on ACEnet.

## Rulings (2026-10-28; were the open questions, each answered with its recommendation)

1. **Text steps (names, embed) on the remote too, or always here?** *Ruled:* yes when they ride along: a text
   step whose input is already at a remote place (it follows a remote read in the same stage) runs there in the same
   task, since the model loads once and nothing more leaves the Mac; a text step on its own (a local read, then
   names) stays here on the background lane; embedding runs where the project's embedder lives, and a cloud embedder
   batches like any cloud step. Nothing is shipped remotely for a text step alone.
2. **Batches in flight per place.** *Ruled:* two per cluster or Hugging Face place (one running, one queued), as
   written; the cluster's queue limit (`%M`) stays the site's rule, read from the profile, and overrides two when it
   is lower. A cloud batch place is different: a batch may take a day, so two in flight would make 100,000 pages a
   hundred days; submit every packaged recipe batch up to ten open per provider, and lower it to what the provider's
   rate-limits page allows once read.
3. **Hugging Face: Jobs only, or Inference Endpoints too?** *Ruled:* Jobs only. A model with no Job image is
   either a cloud model (it goes by the provider's batch) or stays local; an Endpoint is a server to keep up, which
   the batch APIs spare us. Endpoints are out of this doc.
4. **The cloud-batch threshold (new).** *Ruled:* 100 pages of one step on one cloud model in one run that nobody
   is waiting on; below it the plain calls finish sooner than a batch is likely to and the saving is cents. Changed
   with a measurement from step 2's real runs, not a guess.
