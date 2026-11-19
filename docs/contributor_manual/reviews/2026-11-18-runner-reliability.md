# Review: how a run fails today, everywhere work runs (2026-11-18)

> The reviewer, for the owner. Read against `origin/integration` d01807cd12 (2026-11-17 night), file and line, nothing
> run. Two surveys fed it (the engine's failure paths; the app's run and failure surfaces); every claim below cites a
> path and a line in that tree, or says "to verify". The companion plan is `2026-11-18-runner-reliability-plan.md`; the
> contract the plan builds is `../specs/compute/runner-reliability.md`; the window that shows models and places is
> `../specs/ui/models-and-compute-window.md`.

## The ten things that matter most

1. **Out of credit, or a refused key, still FAILS the run.** A 402 with no in-flight reason or a 401 is `fatal`
   (`workflows/circuit_breaker.py:313-314`); `llm/retry.py:82-84` marks the provider dead for 30 s, every later page
   raises, `builder.py:2392` wraps it in `SystemicErrorDetected`, and `execution/runner.py:2781-2784` ends the run
   `failed`. The owner asked for a pause that asks (#6675, open, no milestone). Only a rate limit (`retry.py:101-103`)
   and Fichero's own cap (`llm/spend.py:452-455`) pause today.
2. **A later step can still run on nothing.** The step gate `_blocked` (`recipes/runner.py:2057-2080`) looks at the
   giver step's STATE, never its output; a page Kraken found zero lines on is not done for `read-a-line`
   (`recipes/done.py:705-737`, `found > 0`), so the read runs on it, and `failed_reads` (`done.py:446-466`) counts the page
   lost only when it has reasons, which a zero-line page has none of: the step ends `done` with no text. #6271 saw 545
   pages like this counted done. Section 13's per-page `waiting_on` (`runner.py:1730-1772`, built for #6673) covers the
   "earlier step failed" case, not the "earlier step produced nothing" case.
3. **Kraken's own "reader not on this Mac" reads as a bug in Fichero.** `kraken_runtime.py:432-456` raises a plain
   `RuntimeError`, which `llm/failure.kind_of` (`failure.py:159-198`) cannot type, so the row says "Something went wrong in
   Fichero" (`execution/jobs.py:324-345`, `failed_reason`). The fetch-before-the-step of #6673 makes it rarer, not typed.
4. **The vision tool bypasses the one retry layer.** `workflows/tools/vision_base.py:4383` builds its own breaker and
   calls `call_with_breaker` directly, so a plain 429 storm there ends in "Vision processing skipped" and a FAILED page
   (`vision_base.py:6141-6148`); the rate-limit pause lives in `llm/retry.resilient` (`retry.py:69-106`), which that path
   never enters. Only the in-flight budget pauses from inside `call_with_breaker` (`circuit_breaker.py:541-546`).
5. **The app never shows the engine's words or fix.** `ActivityJob.Failure` carries `words`, `fix` and `actions`
   (`Services/ActivityJob+Facts.swift:12-22`); no view renders `failure.words` or `failure.fix` (grep of Views and
   Models). The table shows `rowWords`, else a reason of 8 words or fewer, else NOTHING (`Views/Activity/Pane/ActivityPane+Row.swift:156-175`,
   `wordBudget = 8`). The one alert, `RunFailurePrompt` (`Models/RunFailurePrompt.swift:8-40`), is called only from tests.
6. **Pane actions swallow their errors.** Each verb returns a `Bool`; the engine's text is dropped and the status line
   says "Retried 0 · 1 skipped" (`Views/Activity/Pane/ActivityPaneView+Actions.swift:118-148`, `ActivityPaneVerbs.swift:78-91`).
   Pause All / Continue All / Stop All failures are a tooltip (`ActivityRunControlsBar.swift:67`, `.help(notice ?? "")`).
   The table says "Continue"; the Inspector's button says "Resume" (`ActivityPaneVerbs.swift:17-27` vs
   `ActivityMonitorModel.swift` `Control.label`).
7. **Three failure vocabularies, two in specs, one in code.** `llm/failure.py:226-242` serves sixteen kinds;
   `ai/run-failure-alerts.md` tables twelve of them and says `no-credit` ENDS the run (decision 2);
   `ui/activity-and-automatic-work.md` §J tables thirteen DIFFERENT names (`out-of-credit`, `provider-down`, `disk-full`,
   `engine-crashed`, `unknown`, …) and says eight of them PAUSE. Issues cite both (#6569 cites §J; #6597 cites the pane
   spec). The code also mis-types: a 5xx is `network` ("Could not reach …", `failure.py:197`), `EmbedderUnavailable` is
   `model-broken` ("could not be loaded", `failure.py:177-178`) when the model is merely being fetched.
8. **spaCy missing is "done".** `knowledge/spacy_ner.py:326-363` returns `None` with a warning, `extract_entities`
   returns `[]` (`:466-476`), and the names step ends done with no names; the import draft swallows a parser error
   outright (`importers/nlp_draft.py:275`). A PINNED pipeline is typed (`PipelineMissing`, `:292-301`); the default path is not.
9. **Remote places fail loud in the wrong way or quiet in the wrong way.** A Slurm login that drops is `SlurmError`
   (`remote_read/slurm_target.py:182-190`), not in `cannot_reach` (`training/hf_jobs.py:109-116`), so a status poll with
   shards out FAILS the run (`remote_read/job.py:408-428` re-raises) and "Catch up" is the only way back; `send_ahead`
   discards a refusal's reason (`remote_read/pipeline.py:31-54`); the Inspector's Cancel / Retry failed shards / Catch Up
   drop their results (`Views/Activity/Detail/RemoteRunInspector.swift:55-61`). Hugging Face without a token WAITS out of
   reach, which is right (`hf_jobs.py:126-135`, `job.py:408-428`).
10. **Automatic work and the person's work still collide.** `release_idle_models` frees every idle embedder at once
    under pressure (`execution/jobs.py:4641-4690`, `idle_seconds=0`); the throttle's first paging reading never holds
    (`execution/throttle.py:206-220`) and warn-level pressure alone never holds (`:99-137`); an MLX load that waits for
    memory ends as a FAILED page after its deadline (`llm/local_inference.py:371-372`), never a pause; a run the person
    started waited for Run now (#6263); half the cores while in use is ruled, not built (#6230). What IS built and
    pinned: one heavy model at a time, the embed lane waiting while Kraken has pages, Kraken never released under its own
    stage (`jobs.py:4644-4646`, `recipes-run.memory.one-heavy-model-in-sequence`).

## How a run can fail today: place × failure

Verdicts: **SILENT** (a log line or nothing) · **PAGE** (fails the page, the run goes on) · **STEP** · **RUN** ·
**PAUSES** (needs Continue) · **WAITS** (held, runs later by itself) · **RETRIES** · **NOTHING** (carries on with no
result) · **NO FALLBACK** (no other model or place; by ruling, right; but nothing asks either).

### On this Mac

| Place | Failure | What happens, where | What the person sees | Spec id / issue |
|---|---|---|---|---|
| Kraken | reader not downloaded | plain `RuntimeError` (`llm/kraken_runtime.py:432-456`) → `unexpected` | "Something went wrong in Fichero" (`execution/jobs.py:324-345`) | `recipes-run.steps.models-fetched-before-the-step` [OK] makes it rare; the kind is wrong: **none**, to file |
| Kraken | segmentation raises | `KrakenSegmentationError` (`kraken_runtime.py:1519`) → PAGE | "Failed: Kraken segmentation failed: …" (reason text) | `recipes-run.engine.failure-in-words` [PARTIAL] #6212 |
| Kraken | a line's polygon `None` or < 3 points | dropped at `kraken_runtime.py:1764, 1851, 1942` (`continue`) and `_usable` `:1544-1545`; **to verify** whether the boxing of 31f94d0dda runs before these | nothing | `recipes-run.kraken.no-silent-line-loss` [OK] claims the box; the three drop sites stay unlogged: **to verify**, #6673 |
| Kraken | every line empty | WARNING `kraken_runtime.py:2007`, the page counted lost, step `partial` | "most lines came back empty: the reader may not suit this hand" | `recipes-run.engine.empty-kraken-lines-are-named` [OK] #6219 |
| Kraken | finds no lines | `PRODUCED_NOTHING` geometry, page not done, later read runs and ends done with no text (finding 2) | the step reads done | #6271, **no behaviour covers the zero-line page** |
| Kraken | memory | `KrakenMemoryUnavailableError` (`:731-745`), a `MemoryShortError` → WAITS | "Waiting: memory is tight" | `recipes-run.memory.hold-when-paging` [PARTIAL] #6075 |
| Kraken | released under a run | guarded: pages in flight keep it (`jobs.py:4644-4646`) | — | `recipes-run.memory.one-heavy-model-in-sequence` [OK] #6673 |
| spaCy | pipeline absent (default path) | `None` + warning, `[]` returned, step done (`knowledge/spacy_ner.py:326-363, 466-476`) → NOTHING | a names step "done" with no names | `runtime.spacy.pin-is-honoured` [OK] covers the pinned path only: **none** for the default, to file |
| spaCy | pinned pipeline absent | `PipelineMissing` (`:292-301`) → STEP | the words of the error | `runtime.spacy.pin-is-honoured` [OK] |
| spaCy | a page spins | 300 s limit, page left out with its reason (`recipes-run.reliability.a-page-never-spins-silently`) | the words | [PARTIAL] #6236 |
| spaCy | import draft parser error | swallowed (`importers/nlp_draft.py:275`) → SILENT | nothing | `engine.silent.ledger-counts-a-swallowed-exception` [GAP] #4420 |
| Search embedder | model not downloaded | `EmbedderUnavailable` (`db/embed_process.py:489-492`) → WAITS; callers wait (`importers/derivatives.py:701-712`) | "The search model is not downloaded yet …"; the job blocked under the download | `activity.pane.blocked-under-its-blocker` [OK] #6593 |
| Search embedder | model will not load (bge-m3 blob folders) | one WARNING per write before the ledger (389k lines, `engine-silent-failures.md` rows 1-3); now a `failure_ledger` entry and health `degraded` | the app shows `degraded` nowhere | `engine.silent.app-says-degraded` [GAP] #4420; #6591 |
| Search embedder | typed wrong | `EmbedderUnavailable` → `model-broken` "could not be loaded" (`llm/failure.py:177-178`) even while fetching | wrong words if it reaches a row | **none**, to file |
| Search embedder | freed under pressure | every idle embedder released at once (`jobs.py:4641-4690`) | reload on the next write | `activity.lane.idle-unload` [OK]; the cost is #4999's |
| MLX / oMLX (local server) | model not downloaded | `LocalModelNotInstalledError` (`llm/local_inference.py:1086`) → `model-missing` | "<Model> is not downloaded" | `run.fail.kinds-table` [PARTIAL] #6354 |
| MLX / oMLX | runtime not installable (sandbox) | `LocalInferenceRuntimeMissingError` (`:913, 1047`) → `runtime-unavailable` | "No runtime for this step" | `runtime.unavailable-says-so` [BROKEN] #5367, #4973 |
| MLX / oMLX | will not fit now | `LocalModelMemoryShortError`, waits to a deadline, then `LocalModelMemoryUnavailableError` (`:301-308, 371-372`) → PAGE | "Waited N minutes for memory; close other apps, then run the page again" | `ai.where.app-keeps-memory` [PARTIAL] #5537; a pause, not a failed page: **none** |
| MLX / oMLX | server dies mid-read | "The local model server stopped while reading this page" (`llm/__init__.py:1593-1630`) → PAGE; no progress 120 s → "the model stopped answering" (`local_inference.py:572`) | those words, kept by `failed_reason` | `recipes-run.engine.local-call-judged-by-progress` [OK] #5537 |
| MLX runtime set-up | not set up / could not set up | plain `RuntimeError` (`llm/mlx_runtime.py:253, 277`) → `unexpected` | "Something went wrong in Fichero" | **none**, to file; #5267 |
| Apple Vision / Intelligence / Foundation Models | worker stops on a page | "Apple Vision's worker stopped while reading this page" ×13 on one folder, the systemic rule fails the run | the run failed | #6288 open; `runner.local.apple` in the contract |
| Apple | language `auto`, print pages refused | #5859 | the words | #5859 open (Next release) |
| Apple translation | missing language pack | typed refusal, NO FALLBACK (`llm/apple_translation.py:13, 134-136`) | the words | by design |
| Whisper | model missing / transcription fails | `WhisperModelNotInstalledError`, `WhisperTranscriptionError` (`llm/whisper_runtime.py:347, 362-387`) → STEP; download state recorded failed `:256-263` | the words; the download says nothing until it ends (#6592) | `runtime.one-download-path` [GAP] #5359; #4628 |
| YOLO | model missing | `LocalModelNotInstalledError` (`llm/yolo_runtime.py:103-106`) → `model-missing` | "<Model> is not downloaded" | #5525 |
| OpenCV | `cv2` import inside the function (`recipes/prepare_suggest.py:29-98`) | **to verify** whether an `ImportError` is caught above | — | **none** |
| Any download | the job row is gone | `_await_downloads` counts a `None` row as landed (`recipes/runner.py:1040-1078`) → SILENT success | the step runs without the model, then fails on it | **none**, to file |
| Any job | exception in a lane job | `failed` with `failed_reason` (`jobs.py:5916-5938`); `library-closed` and `export-folder-gone` PAUSE (`_PAUSED_NOT_FAILED`, `jobs.py:6026`) | row words; the fix button for those two | `activity.failure.no-raw-text-ever` [PARTIAL] #6597 |
| Any job | the engine quits | every unfinished row `paused` "Stopped when Fichero quit" (`jobs.resume`, `jobs.py:2761`); a thumbnail orphan requeued after 60 s (`requeue_orphaned_first`, `:2736`) | the quit alert "Leave Paused / Continue All" (`Models/StoppedAtQuitAlert.swift:41-60`) | `activity.relaunch.only-running-work-resumes` [OK] #6584 |
| Any model-lane job | silent for 60 s | the slot is let go, the thread lives on (`_Lane`, `jobs.py:4882-4897`) → SILENT | the row stays running | `recipes-run.isolation.one-project-never-blocks-another` [PARTIAL] #6213; #5874 |

### At a cloud provider (OpenRouter, OpenAI, Anthropic, Google, HF router)

| Failure | What happens, where | What the person sees | Spec id / issue |
|---|---|---|---|
| 402 no credit, a key limit, 401 | `fatal` (`circuit_breaker.py:313-314`), dead 30 s (`retry.py:82-84`), pages fail, `SystemicErrorDetected` → RUN (`runner.py:2781`) | "Out of credit at <Provider>" on a failed run; no alert; no Continue | `activity.failure.credit-exhausted-pauses` [GAP] #6354; **#6675 open, no milestone** |
| 402 `in_flight_budget_exhausted` | slow-down, cap halved, retried; retries spent → `ProviderInFlightBudgetError`, the run PAUSES (`circuit_breaker.py:541-546`, `vision_base.py:6136-6137`, `builder.py:2374-2378`) | "… is limiting how many requests can be in flight …, so this step paused" with Continue | `activity.limits.rate-limit-backs-off-then-pauses` [PARTIAL] #6671 (closed) |
| 429 through `resilient` | back-off with Retry-After (cap 120 s), `RATE_LIMIT_PAUSE_AFTER` 3 → PAUSES (`retry.py:101-103`) | "… is limiting how fast Fichero can send", wait ≥ 60 s, Continue | same |
| 429 through the vision tool | own breaker per call (`vision_base.py:4383`), retries spent → PAGE (`:6141-6148`) | "Vision processing skipped …" | **gap**: finding 4, to file |
| 5xx, dropped connection | `transient`, retried 4× (`circuit_breaker.py:486-590`), then the call fails → PAGE; typed `network` "Could not reach <Provider>" (`failure.py:197`) | wrong words for a 500 | `run.fail.kinds-table` [PARTIAL] #6354; the words: **to file** |
| our own call timeout | `terminal`, no retry (`:321-322`) → PAGE | the page's reason | #5944 (one retry layer) |
| 404 / bad request | `terminal` → PAGE, typed `model-error` | "<Model> could not do this step" | `run.fail.kinds-table` |
| Fichero's cap | `holding` waits for in-flight calls then `CloudSpendRefusedError` after `_ask_run_to_pause` (`spend.py:425-470`) → PAUSES with the typed refusal | "Paused at the spend cap", Change Caps…; the refusal alert only BEFORE Start (`ai.cloud.alert-on-hand-run-paths`) | [PARTIAL] #6349, #6295 |
| the images rule | `EgressRefusedError`, nothing sent (`llm/__init__.py:779-798`) | the typed refusal | `ai.cloud.never-sent-while-off` [OK] #6028 |
| a provider batch's errored/expired lines | kept answers, failed lines asked again as plain calls (`llm/provider_batch.py:338-360`, `remote_read/cloud_batch.py:236`) → RETRIES | the row's counts | `compute.recipe.cloud-batch-retries-failed-requests-only` [PARTIAL] #5940 |
| an unpriced call | booked at an assumed price (`spend.py` `_book`) → SILENT | "Not priced" in the cost column at best | #6598 |
| any of the above | no other model or place is tried (`chat_with_fallback` docstring `llm/__init__.py:2128-2147`; `_record_model_fallback` has no caller) | NO FALLBACK, and nothing asks | `ai.where.fallback-free-and-asked` [OK]; `ai.where.fallback-across-places` [GAP] #5592 |

### At a remote place (another Mac, a cluster, Hugging Face Jobs)

| Place | Failure | What happens, where | Spec id / issue |
|---|---|---|---|
| Hugging Face Jobs | no token | `NoHuggingFaceToken` (`training/hf_jobs.py:126-135`); with shards out the row stays running, `JobOutOfReach`, taken up at the next open (`remote_read/job.py:408-428`) → WAITS, said | right; `runner.remote.hf-jobs` |
| Hugging Face Jobs | token rejected | `HuggingFaceTokenRejected` (`hf_jobs.py:55-57`) → RUN, or WAITS when adopted | `compute.hpc.failure-states-in-words` sibling; #5740 |
| Hugging Face Jobs | a shard fails far-side | the shard `failed` with the far words, others go on, "N shards failed (re-send them)" (`job.py:380-394`) | right; the Inspector's buttons drop their results (`RemoteRunInspector.swift:55-61`): **to file** |
| Hugging Face training | the Job fails | `phase="failed"`, `RuntimeError(why)` (`training/job.py:331-338`) → RUN | `compute.tune.*`; #5412 (cancel before submit still submits) |
| Slurm / ACENET | login or sign-in drops | `SlurmError` (`slurm_target.py:182-190`) not in `cannot_reach` → status poll re-raises → RUN with shards still out; Catch up is the way back (`job.py:491-501`) | `compute.hpc.mfa-modes` [GAP] #5642: **to file** the mapping |
| Slurm / ACENET | `sbatch` fails / no job id | `SlurmError` (`:83, 103, 264`) → STEP | `compute.hpc.submit-array` [PARTIAL] #5642 |
| Slurm / ACENET | TIMEOUT, OOM, NODE_FAIL, PREEMPTED | said in words from `sacct`; no resume, resize or requeue yet | `compute.hpc.failure-states-in-words` [PARTIAL] #5457 |
| the pipeline | a send-ahead refused | `_why` discarded (`remote_read/pipeline.py:31-54`) → SILENT until the batch's turn | `compute.recipe.step-major-batches-pipelined` [PARTIAL] #5642 |
| another Mac | stops answering mid-run | no place-level handling; the call's error is the page's | `runner.remote.mac` [GAP] #5951 |
| transfer | a copy differs | `TransferFailed`, rolled back in words (`transfer/copy.py:117-128, 225-232`) → RUN | `transfer-and-results.md` |

### The recipe runner itself

| Failure | What happens, where | Spec id / issue |
|---|---|---|
| a step fails on 3 batches in a row with nothing done | `OUTRIGHT_IN_A_ROW` (`recipes/runner.py:1470, 2047-2048`), `_halted` (`:1508-1514`) → RUN "Stopped: …" | `source.recipe.batch-at-archive-scale` |
| a step fails working out its pages / fails to start | STEP, the rest go on (`:1836-1850`, `:1916-1918`, `could_not_start` `:1010`) | `recipes-run.steps.*` |
| a step has no pages | `done` "nothing to run / already done" (`:1859-1870`) → NOTHING, honest | `source.recipe.done-is-not-redone` |
| a download failed | `_DownloadFailed`: the pages WAIT under the download (`:1847`) | `recipes-run.steps.models-fetched-before-the-step` [OK] |
| an unexpected error in the plan | RUN, work kept, Start carries on (`:1334-1346`) | `recipes-run.engine.failure-in-words` [PARTIAL] |
| Pause | `_park`, `JobDeferred("Paused with its run")` (`:432-502`) → PAUSES | `recipes-run.control.pause-and-resume` [PARTIAL] #5933 |
| Retry inside a run | redoes the failed pages of the earliest failed step and flows on | `recipes-run.steps.retry-flows-through` [OK]; #6331, #6332 open say otherwise: **to verify on a build** |

## Which failures are silent

Nothing said where the person looks: Kraken's three geometry drop sites (to verify); a zero-line page counted done by
the read (#6271); spaCy absent on the default path; the import draft's swallowed parser error; a download row that
vanished counted as landed; a model-lane job silent for 60 s keeping its row "running"; `send_ahead`'s discarded
refusal; the throttle's first paging reading and warn-level pressure never holding; an unpriced call booked at a guess;
in the app, a reason over eight words with no row words (blank cell), every pane verb's error ("Retried 0 · 1 skipped"),
Pause All's tooltip, `failure.fix` never rendered, Add Provider's failure (`AddProviderSheet+Helpers.swift:84-86`, log
only), Test Connection's error as a tooltip glyph (`ProvidersView+ProviderDetailView.swift:~183-185`), delete-model
failures (log only), Translate's progress (`isTranslating` never read), the chain's poll errors and its 4-hour deadline
(`ContentView+WorkflowChainEngine.swift:389-425`, `try?`), auto-save failures (`ContentView+WorkflowActions.swift:~155`),
Duplicate / Make Alias (`LibraryView+ContextMenu.swift:183, 206`), a batch run with an empty scope
(`LibraryView+BatchWorkflow.swift:76-80, 200-214`), the Start button's refusal (`FocusedCommandButtons+Recipe.swift:145`,
`guard await store.start() else { return }`), and the workflow bar's dropped model pin (`ContentView+WorkflowActions.swift:~27-97`).

## Which failures compound

- A model not fetched → every page of its step fails at once → the systemic rule → the run fails → later steps that
  needed it either wait (built, #6673) or, for the zero-output case, run on nothing (finding 2).
- A 402 on one page → the provider dead for 30 s → every page in that window fails → `SystemicErrorDetected` → the run
  fails, with Fichero's own words blaming "quota or rate limit" (`runner.py:634-648`).
- Pressure → `release_idle_models` frees the embedder → the next write reloads it → more pressure; and before #6673,
  Kraken itself was freed under its own stage (31 reloads in one run, `recipes-run.memory.recorded-per-step`).
- A wedged job holds a lane → `STUCK_*` lets the slot go but the thread lives → the row reads running for ever (#5874).
- A refused grant → every original reads as "moved" (`engine-silent-failures.md`, the originals class) → thumbnails
  stand in → a run reads the thumbnails or fails as `files-unavailable` with no Reconnect (#6306).

## Pause, fail or carry on: the honest table

| Cause | Today | Ruled / wanted |
|---|---|---|
| rate limit (429), in-flight budget | backs off, then PAUSES, Continue | the same (owner 2026-11-13) |
| Fichero's spend cap | PAUSES with the typed refusal | the same; the alert mid-run is owed |
| no credit, key limit, refused key | FAILS the run | PAUSES and asks, one dialogue per provider (#6675) |
| 5xx, network | retried, then FAILS the page | backs off, then PAUSES as `network` (§J) |
| memory (Kraken) | WAITS (the hold) | the same, then a pause if the hold gives up |
| memory (MLX) | waits, then FAILS the page | a pause, never a failed page |
| model missing | blocked under the download (built) | the same |
| model broken | blocked, "Download again" (built for the embedder) | the same for every runtime |
| runtime unavailable | FAILS the step | the same, said before Start |
| a page's own error | FAILS the page, one retry | the same |
| the engine stopped | paused "Stopped when Fichero quit", or resumed gently for a kill | the same |
| library closed, export folder gone | PAUSES (built, `jobs.py:6026`) | the same |
| a bug | FAILS the item, "Something went wrong in Fichero" | the same, a bug report offered (route built, app owed) |

## Where there is no fallback

Everywhere, by ruling (`ai.where.fallback-free-and-asked`): no silent model or place substitution exists in the code
(`llm/__init__.py:2128-2147`, `recipes/assemble.py:765-766`, `recipes/start.py:468`). What is missing is not a fallback
but the ASK: the only fallback offered is at Start (`use-instead`, a free place for the same card); mid-run, a place that
fails has no "run these pages at <other place>?" and no pause that asks (`ai.where.fallback-across-places` [GAP] #5592,
needing the owner's ruling, which `ai.where.fallback-free-and-asked` already gave: free, same card, asked).

## Where automatic work and the person's work collide

- **Memory.** One heavy model at a time is built and pinned (`recipes-run.memory.one-heavy-model` [OK]); the embed
  lane waits while Kraken has pages (#6673, built); the hold while paging is built (#6075) but the first reading never
  holds and warn-level pressure never holds (`throttle.py:99-137, 206-220`); the DuckDB cap applies (#6177); the
  ceilings per model kind are not measured (#6076, #6212). The engine records memory per step now (#6673).
- **The Mac staying usable.** One in-use rule exists (`activity.throttle.use-means-slower` [OK]); half the cores while
  in use is ruled, not built (#6230); a started run waited for Run now (#6263); background QoS is PARTIAL (#5358).
- **Downloads.** A download resumes only when its project is reopened (#5649, needs the owner's ruling); only Kraken's
  download reports bytes (#6592); `installed` is said before a load check (#6591).
- **What the person sees of it.** The popover says "Memory pressure", "Paging" and "Heavy work is held back"
  (`ActivityPopoverSummary.swift:309-361`); the opened run says pages at once and threads (`ProjectRunStrip.swift:221-232`);
  nothing shows RAM or GPU per model or what unloading would give back (#4987 §4-5; the window spec).

## The specs: where they disagree

1. `activity-and-automatic-work.md` §J names 13 kinds and says 8 pause; `run-failure-alerts.md` names 12 and says
   `no-credit` ends the run; `llm/failure.py` has 16. Resolved in the integration: the code's sixteen are the table;
   pause-or-fail is a column (`runner-reliability.md` §1); §J's table is superseded.
2. `run-failure-alerts.md` says `Milestone: run-failure-alerts`; no such milestone exists on GitHub (#6354 sits in
   `activity`). Resolved: the spec's Milestone line now reads `activity`.
3. `recipes-run.md` §13 says "a provider's in-flight or rate limit pauses the run"; #6675 widens it to credit. Resolved
   by pointer.
4. `where-models-run.md` §F `ai.where.fallback-across-places` [GAP] waits for a ruling the line above it already gives.
   Resolved by pointer: the mid-run answer is a pause that asks, never a different model.
5. `ai-settings.md` holds providers, local models, clusters and "Where work runs" in Settings; the owner's rulings of
   2026-11-15/16 put models and places in Activity's sidebar. The window spec says what leaves Settings.
6. Issues cite ids that exist on a branch, not on integration: #6569 cites §J ids (now on integration); #6597, #6593,
   #6592 cite `activity-pane.md` (on integration since 2026-11-13). Fine now; the harness worktree this review started in
   (45bf39bc37) lacked them, which is why the review moved to `origin/integration`.
