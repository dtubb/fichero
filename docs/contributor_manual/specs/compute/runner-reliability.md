# Runner reliability — one contract for every place work runs — Design Spec (#6354, #6675)

> Milestone: recipes-run (the open issues sit there, in `activity` and in `ai-settings` until the milestone hygiene in
> `reviews/2026-11-18-runner-reliability-plan.md` is done; this spec names no milestone of its own on purpose)
> Manual: TBD — a "When a run stops" section: what a paused run looks like, what Continue does, which problems Fichero
> fixes by itself and which it asks about, and why automatic work goes slower while you use the Mac.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-18** (the reviewer, from the owner's concern of 2026-11-18;
> the owner approves). Written from the review `docs/contributor_manual/reviews/2026-11-18-runner-reliability.md`, whose
> findings cite the code; nothing here was run.
> Tags: **[OK]** built and pinned by a test that ran · **[PARTIAL]** exists in part or not wired · **[GAP]** designed, not
> built · **[BROKEN]** built and contradicting the line. Every non-[OK] line cites an issue.
>
> **What this spec is.** The ONE contract the runners agree to, wherever work runs: on this Mac (Kraken, spaCy, the
> search embedder, OpenCV, YOLO, MLX and oMLX models, Apple Intelligence and Foundation Models, Whisper), at a cloud
> provider (OpenRouter, OpenAI, Anthropic, Google, Hugging Face's router), at another Mac, on a cluster (Slurm, ACENET), or
> as a Hugging Face Job. It does not replace the specs that own each runner; it names what each must do when work goes
> wrong, and points at the one table, the one pause path and the one place it is shown. Where an owning spec says
> otherwise, THIS file wins and the other's line is marked superseded in the same commit (the integration of 2026-11-18 did
> that for the lines listed under "Changes to existing behaviours").
>
> **What it builds on, by name.** The failure kinds table is `run.fail.kinds-table` (section F below; carried from
> the former failure-alerts spec, merged into this file on 2026-11-18), built as
> `fichero-server/src/fichero_server/llm/failure.py` (`RunFailure`, `classify`, `row_words`). The pause path is the one
> `execution/cancellation.request_pause` → `_finish_as_paused` path that a person's Pause, the spend cap
> (`llm/spend._ask_run_to_pause`) and a rate limit (`llm/retry._pause_the_run_for`) already take. The surface is the
> Activity pane (`ui/activity-pane.md`: the states table, `activity.pane.failure-with-its-fix-in-the-row`,
> `activity.pane.blocked-under-its-blocker`) and the alert of `run.fail.alert-on-a-failed-run`. The recipe's own rules are
> `source/recipes-run.md` section 13 (a page waits for its inputs; models fetched first; no empty done).
>
> **Owns / Does not own.** This spec OWNS how work fails, pauses and goes on, wherever it runs: the one table of failure
> kinds with their words, fixes and actions, which kinds pause and which fail, the one pause path and Continue, the one alert
> and the bug report, memory holds, and what every runner (local, cloud, remote) must do when work goes wrong. It does NOT
> own: the Activity window, pane and its rows, lanes and throttle (`ui/activity-pane.md`); a recipe run's journey from Start
> to the summary (`source/recipes-run.md`); designing a recipe and the Set Up screens (`source/recipe-designer.md`); the
> Models and Compute window, every model and place and its account (`ui/models-and-compute-window.md`); which model and
> place a step chooses, egress and the spend caps (`ai/where-models-run.md`, `ai/cloud-permission-and-spend.md`).

## Intent (the design)

A person starts work and can leave. Anything that goes wrong is one of a fixed set of kinds; each kind has words a
person can read, a fix they can do, and a rule: the engine fixes it by itself (retry, back off, wait for a download,
free a model), or it PAUSES the work and asks, or, for a thing that cannot mend (a bug, a bad request), it FAILS that
item and goes on with the others. Nothing is ever silent: no page is counted done that holds nothing, no step runs on a
page whose inputs are missing, no line found is dropped without a word, no model is swapped for another without asking.
A paused run keeps what it did, says why it waits in one place (its Activity row, and one alert per cause), and goes
on from the first item not done when the person presses Continue. The same words reach the app, the CLI and MCP from the
engine; no client classifies. And automatic work never makes the Mac unusable: one heavy model at a time, pages held
while the Mac pages, half the cores while the person works.

## Prior art / best practices (don't invent from scratch)

- **Job queues that survive their workers** (Sidekiq, Celery acks-late, Postgres `SKIP LOCKED`): a failure is a typed
  reason on the row, a retry is bounded, a dead lease returns the row to waiting. The former Activity spec
  adopts this; this spec adds the rule that a failure the person can mend pauses rather than fails.
- **Circuit breakers and retry budgets** (Hystrix, Google SRE's "retry budgets"): classify by status, honour
  `Retry-After`, bound the sends per item. Built in `workflows/circuit_breaker.py` and `llm/retry.py`; this spec makes the
  classification the one table's and the budget's end a pause, not a failed page.
- **Spotlight and Photos**: background work that holds back while the Mac is in use and never dies of memory
  (`activity.throttle.*`). We add no setting; the engine measures and says why in one grey line.
- **Slurm's own states** (`sacct`: TIMEOUT, OUT_OF_MEMORY, NODE_FAIL, PREEMPTED): the cluster's failure words map onto the
  one table (`compute.hpc.failure-states-in-words`), never a second vocabulary.
- **What we do differently.** No fallback ladder: a different model is never substituted mid-run (owner ruling
  2026-09-07, `ai.where.fallback-free-and-asked`); the only fallback is the same model at a place the person accepted at
  Start, and a failure otherwise pauses and asks.

## The contract

### 1. One table of failure kinds, with three more columns

The kinds are those `llm/failure.py` serves today (the sixteen below); the section "The words, fixes and actions of each
kind" below keeps the words and the fixes. This spec adds, per kind, **pause-or-fail**, **retryable by the engine**, and **which runners can raise it**. The
engine owns all three; the app shows only what the row says.

| kind | pause-or-fail | engine retries first | raised by |
|---|---|---|---|
| `no-credit` | **pauses the run**, asks (one dialogue per provider per run, #6675) | no (fatal at the provider) | cloud providers, HF router |
| `key-refused` | **pauses**, asks | no | cloud providers, HF Jobs (token), a cluster (key, second factor) |
| `rate-limited` (a 429, or OpenRouter's in-flight budget #6671) | backs off (Retry-After, jitter, capped) then **pauses**, Continue when the wait is up; no dialogue | yes, bounded | cloud providers, HF router |
| `cap-refused` | **pauses**, the refusal's fixes | no | any cloud step (Fichero's own cap) |
| `images-refused` | refused before Start, or **pauses** mid-run | no | any cloud or remote step (the egress gate) |
| `network` | backs off then **pauses** ("Could not reach …"), Continue | yes, bounded | cloud, another Mac, a cluster, HF Jobs, a model download |
| `model-missing` | the page is **blocked** under the download; the run goes on with other steps | the download is retried on Retry | Kraken, spaCy, embedder, MLX, Whisper, YOLO |
| `model-broken` | **blocked** under its blocker, fix "Download again" | no | embedder (bge-m3 #6591), Kraken, MLX |
| `runtime-unavailable` | **fails the step** before it runs, fix "Choose a model that runs another way" | no | MLX/Whisper in a sandboxed build, Apple on an unsupported Mac, Kraken without its runtime |
| `memory` | **holds** (the throttle), then **pauses** if the hold gives up; never kills the engine | yes (the hold) | Kraken, MLX, embedder, YOLO, a thumbnail |
| `model-error` | **fails the page**, the run goes on; the step's summary names it | one page retry (`page_retry`) | cloud, MLX, Apple (a refused page, an empty answer) |
| `files-unavailable` | **fails the page**, the run goes on; "Reconnect" when a volume or grant is the cause (#6306) | no | every runner that reads an original |
| `library-closed` | **pauses** ("the project closed") | no | every job of that project |
| `export-folder-gone` | **pauses** the export, "Choose a folder" | no | the exporter's kept export |
| `interrupted` | **resumes by itself**, gently (`recipes-run.restart.resumes-at-once-gently`); never counted as an attempt | yes | every job (the engine stopped) |
| `unexpected` | **fails the item**; the run goes on with the others; a bug report is offered | no | anything (a slip in Fichero) |

A remote runner's own states map onto these and never add a kind: Slurm `TIMEOUT`/`OUT_OF_MEMORY` → `memory` with a
smaller slice on Retry, `NODE_FAIL`/`PREEMPTED` → `interrupted`, `CANCELLED` → stopped; a Hugging Face Job that cannot
start for want of a token → `key-refused`; a Job the account cannot pay for → `no-credit`; a provider batch line
`errored`/`expired` → `model-error` for that page.

### 2. One pause path, one Continue

A pause for a cause is the same state as a person's Pause: the run settles `paused` at its next boundary with
`failure` set (`RunFailure`, the kind above), its done items kept and counted, its row reading "Paused: <row words>" with
the fix button, and nothing of it sent anywhere until Continue. Continue re-checks the cause (a dead provider mark, a cap,
a download) and takes up the first item not done; it never redoes a done item and never re-reads a done page. A pause
survives a relaunch as paused (`activity.relaunch.only-running-work-resumes`); the open never continues it. One pause
per cause per run: a second page meeting the same cause joins the pause, it does not fail.

### 3. One place it is shown

The Activity row (the states table of `ui/activity-pane.md`: paused with its cause as its line, blocked under its
blocker, failed with its ≤ 8 row words and the fix button) and, for a pause or failure of the whole run, ONE alert per
attempt (`run.fail.alert-on-a-failed-run`), coalesced by cause and provider. The CLI and MCP read the same `failure`
(`run.fail.cli-says-the-fix`, `run.fail.mcp-says-the-fix`). No client classifies; no raw exception text reaches a row.

## The words, fixes and actions of each kind (carried from the former failure-alerts spec, merged 2026-11-18)

The former failure-alerts spec (#6354, DRAFT 2026-11-05) was the spec of the failure kinds table, the bug report and the one
alert. On 2026-11-18 (owner: one owning spec per area) its decisions, its table and its eighteen `run.fail.*` behaviours
moved here unchanged (ids, tags, citations and issue numbers intact); the old path is a pointer. Its "What exists today"
survey of 2026-11-05 was not carried (a code survey, nothing normative; the review of 2026-11-18 supersedes it).

### Decisions (overrule any in one line)

1. **One mapping, in the engine, on the run.** `_classify_provider_error` moves to `llm/failure` and answers a
   served model, `RunFailure`; the runner stores it on the run row when the run ends failed (or pauses for a cause), and
   every client reads it. The per-page classification keeps using the same function, so a page's reason and the run's
   reason never disagree.
2. **A failed run is one that ends `failed`, or pauses for a cause the person must act on (a cap, the images rule, and,
   amended 2026-11-18 per the owner's rulings of 2026-11-13 and 2026-11-18, #6675: no credit, a refused key, the network
   and memory).** Which kinds pause and which fail is the contract's column (`compute/runner-reliability.md` §1,
   `runner.kinds.pause-or-fail-is-the-tables`); a pausing kind settles the run `paused` with its `failure` and raises the
   alert, and its words say "paused", never "stopped" (the `no-credit` and `key-refused` rows below were amended to match;
   the acceptance text of those two rows changed). A run that ends partial ("Done with failures: 3 of 203 pages")
   FINISHED: Activity's Partial line and Retry cover it, no alert (question 1). A run paused by a person or by the
   engine's own stop raises nothing. A page's failure is not the run's.
3. **Unknown falls to `unexpected`, never to silence.** There is no `unknown` kind. What the table does not name is a
   bug in Fichero, said so, with the exception's type and an offer to report it.
4. **One alert per failed run attempt.** The key is the run's id and its `failed_at` (the key `ActivityErrorLedger`
   already uses): a retry that fails again is a new attempt and alerts again; a relaunch never alerts again for a
   failure already seen; a failure older than an hour at launch is in Activity, not an alert.
5. **The cap and images kinds ARE the existing refusal alert.** `RunFailure.refusal` carries the typed `CloudRefusal`;
   the app hands those kinds to `CloudRefusalAlert`, whose buttons resume the paused run with the once flags (the half
   of `ai.cloud.alert-on-hand-run-paths` that is not built). Nothing is respecified.
6. **The bug report is built by the engine** (`POST /api/activity/jobs/{id}/bug-report`), so the app, the CLI and an
   agent send the same report and the redaction is tested once. Where it goes is question 2; until ruled, the route
   answers the report and the app offers to save it (the Send Logs path can attach it the day the address exists).
7. **Actions are typed, in one vocabulary with `CloudRefusalFix`** (`retry`, `resume`, `open-settings` with a control id,
   `choose-model`, `report-bug`, `reconnect`, plus the refusal's own), so the app's one switch grows by cases, not
   by alerts.
8. **A pause for a cause survives a relaunch, and a failed run is never re-run by itself** (owner 2026-11-13, night;
   #6584). Decision 2 pauses the run; the relaunch must not undo it: the recipe run's pause is stored on its row at the
   open (`activity.relaunch.only-running-work-resumes` in the former Activity spec), so the run still reads
   paused with its alert's cause, and only Resume (the alert's or Activity's) carries it on. A run that ended failed
   stays failed with its reason and its Retry.
9. **A rate limit backs off, then pauses; every failure carries its solution; no codes** (owner 2026-11-13, 22:25–23:15;
   #6584, #6354). The `rate-limited` kind is a pause kind like `no-credit` and `cap-refused`: after the bounded back-off
   (Retry-After honoured, jitter, capped) the run PAUSES with "<Provider> is limiting how fast you can send" and the fix
   "Wait N minutes, then Continue" (no automatic Continue: the back-off is the automatic retrying; the review 2026-11-13 night),
   never a tight loop, never a failed page per 429 (`ui/activity-pane.md` `activity.limits.rate-limit-backs-off-then-pauses`). Every kind in the table has a
   non-empty sentence AND a fix (a typed action with a label, or an exact instruction); a kind with neither is a spec gap listed
   under Open questions, never shown bare. The sentence names no HTTP status, error code, exception type, traceback or the
   provider's raw reason text; those are the bug report's and Copy Details' (`activity.pane.failure-with-its-fix-in-the-row`);
   `unexpected` says "Something went wrong in Fichero, not in your files." Every kind also has ROW WORDS of at most eight
   whitespace tokens for the table (the "row words" column below), never a sentence cut at a word boundary. Test:
   `fichero-server/tests/unit/llm/test_every_failure_kind_has_a_fix_6354.py` (built, with the row-words column: `RunFailure.row_words`,
   `failure.row_words(kind)`, ≤ 8 tokens per kind; the no-raw-text rule for the provider's reason is still to add).

### The table (`run.fail.kinds-table`)

The engine's one mapping. "Judged by" is the exception's type first, its status code or words only when it has no type
of its own (today's `_typed_failure` rule). `<Provider>` and `<Model>` are display names (`circuit_breaker.provider_display`),
never ids or internals; `N`/`M` are the run's pages done and total.

Row words (≤ 8 tokens, for the table; the review's column): `no-credit` "Out of credit at <Provider>" · `key-refused` "<Provider>
refused the key" · `rate-limited` "<Provider> is limiting how fast you send" (the run PAUSES) · `cap-refused` "Paused at the
spend cap" · `images-refused` "Pages stay on this Mac" · `model-error` "<Model> could not do this step" · `model-missing`
"<Model> is not downloaded" · `runtime-unavailable` "No runtime for this step" · `memory` "Not enough memory for <Model>" ·
`network` "Could not reach <Provider>" · `files-unavailable` "Some pages' files could not be opened" · `unexpected`
"Something went wrong in Fichero".

| kind | judged by | words (what happened) | fix (what to do) | actions |
|---|---|---|---|---|
| `no-credit` | `ProviderQuotaExhaustedError`; `fatal_cause == "quota"`; 402, `insufficient_quota`, a key limit | "<Provider> has no credit left, or this key's limit is reached, so the run is paused at page N of M. The N pages done are kept." (PAUSES, #6675; was "stopped") | "Add credit at <Provider>, or give Fichero a different key or provider, then continue the run." | `open-provider-page`, `open-settings` (`settings.ai.providers`), `choose-model`, `resume` |
| `key-refused` | `ProviderKeyRefusedError`; `fatal_cause == "key"`; 401, `KEY_REFUSED_WORDS`; today's `auth` | "<Provider> refused the key Fichero has for it, so the run is paused at page N of M." (PAUSES, #6675; was "stopped") | "Check the key in Settings › AI › Providers (paste it again, or make a new one), or switch this step to another provider, then continue the run." | `open-settings` (`settings.ai.providers`), `choose-model`, `resume` |
| `rate-limited` | `ProviderRateLimitedError` with the retries spent; 429 past the retry policy | "<Provider> asked Fichero to slow down more often than the run could wait, so it stopped at page N of M." | "Wait a few minutes and run it again. A higher plan at <Provider>, or another provider, avoids it." | `retry` (with `retry_after_seconds` when the provider gave one), `choose-model` |
| `cap-refused` | `CloudSpendRefusedError` (the run PAUSES at the cap; `refusal` carried) | the refusal's own `words` | the refusal's own `fixes` | the refusal's `fixes[]`, then `resume` |
| `images-refused` | `EgressRefusedError` (the run is refused or paused; `refusal` carried) | the refusal's own `words` | the refusal's own `fixes` | the refusal's `fixes[]`, then `resume` |
| `model-error` | 404 / `model_not_found`; a 400 the provider blames on the request; `StructuredDecodeError`, `StructuredCallEmptyError`, a capability miss | "<Model> at <Provider> could not do this step: <the provider's one-line reason>." | "Choose another model for this step, then run it again." | `choose-model`, `retry` |
| `model-missing` | `LocalModelNotInstalledError` | "<Model> is not downloaded to this Mac." | "Download it in Settings › AI › Local models, or choose another model." | `open-settings` (`settings.ai.localModels`), `choose-model` |
| `runtime-unavailable` | `LocalInferenceRuntimeMissingError`, `AppleUnavailableError`, `KrakenRuntimeMissingError` | "<the runtime> is not available in this build or on this Mac." | "Choose a model that runs another way." | `choose-model` |
| `memory` | `MemoryShortError`, `LocalModelMemoryUnavailableError` | "This Mac did not have the memory for <Model> while this ran, so it stopped at page N of M." | "Close other work, or choose a smaller model, then run it again." | `choose-model`, `retry` |
| `network` | `transient` after the retries; DNS, connection, timeout words; 5xx (today's `network` and `server`) | "Fichero could not reach <Provider> (<the one-line cause>), so the run stopped at page N of M." | "Check the connection and <Provider>'s status, then run it again." | `retry` |
| `files-unavailable` | today's `file_unavailable` (iCloud eviction, a missing original) | "N pages' files could not be opened (<the one-line cause>)." | "Reconnect the folder, or download the pages from iCloud, then run it again." | `reconnect`, `retry` |
| `unexpected` | everything else, including today's `unknown` | "Something went wrong inside Fichero while it ran <step> (<ExceptionType>), so the run stopped at page N of M." | "This is a bug in Fichero, not something you did. Send a bug report so it can be fixed; you can also try the run again." | `report-bug`, `retry` |

A run paused by a person, or by the engine's own stop, has no kind and no alert (`activity.durable.paused-stays-paused`).

## Behaviours

### A. The table and the path (shared by every runner)

- `runner.kinds.one-table` — **[PARTIAL]** (#6354, #6597) every runner's failure is classified by `llm/failure.classify`
  and nothing else: the recipe runner, the workflow runner, the lane (`execution/jobs.failed_reason`), the remote-read loop
  (`remote_read/job.py`), the cloud-batch loop, the training job and the download job. Built: `failure.py` with sixteen
  kinds; `jobs.failed_reason` writes the kind's row words; the workflow run row carries `failure`. Not built: the per-page
  `error_category` still comes from `execution/runner._classify_provider_error`'s own words; the remote-read, cloud-batch,
  training and download paths write their own strings. *Test:* `fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py`
  (extend: each runner's failure path through a stub yields a `RunFailure`, never a bare string).
- `runner.kinds.pause-or-fail-is-the-tables` — **[OK]** (#6675, #6569, #6354) each kind's pause-or-fail rule (section 1)
  is a column of the table (`pauses: bool`, `engine_retries: bool`) served on `RunFailure`, and the runner acts on it: a
  pausing kind settles the run `paused` with its `failure`; a failing kind fails the item and goes on. Today only a rate
  limit and the cap pause; `no-credit` and `key-refused` are `fatal` in `llm/retry.resilient` (the provider is marked dead for
  `DEAD_FOR_SECONDS`, every later call raises, the pages fail, `SystemicErrorDetected` fails the run). *Test (to write, a new file beside
  `fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py`):* a 402 with no in-flight reason on page 4 of 10
  leaves the run paused with `failure.kind == "no-credit"`, three pages kept, nothing sent to that provider; Continue after
  the stub recovers reads pages 4 to 10 only; a bare `RuntimeError` fails that page and the run ends partial.
- `runner.pause.one-path` — **[PARTIAL]** (#6675, #5933) every pause for a cause goes through
  `execution/cancellation.request_pause` and settles in `_finish_as_paused` with `failure` set; no runner keeps a second
  paused state. Built: a person's Pause, the cap (`spend._ask_run_to_pause`), a rate limit (`retry._pause_the_run_for`).
  Not built: `no-credit`, `key-refused`, `network`, `memory` after the hold gives up, `library-closed`; the recipe run parking on
  the paused step for those causes. *Test:* `fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py`
  (extend to each pausing kind).
- `runner.pause.continue-from-first-not-done` — **[PARTIAL]** (#6569, #6331, #6332) Continue on a paused run re-checks the
  cause, forgets the pause (`forget_provider_pause`: `forget_rate_limit_pause`, `forget_cap_stop`, `forget_credit_pause`), and takes up the first item not done; done pages
  are never re-read; Retry inside a run redoes only the failed pages and the step list updates. Built for the rate limit, the
  cap and no credit or a refused key (a plain run's Continue, `resume_workflow`, and the recipe row's both call the helper); owed for the other causes and the recipe parking. *Test:* `fichero-server/tests/unit/recipes/test_recipe_pause_5933.py`,
  `fichero-server/tests/unit/recipes/test_a_page_waits_for_its_inputs_6673.py` (extend: a continued run makes only the missing calls).
- `runner.pause.survives-relaunch` — **[OK]** (#6584) a run paused for a cause is still paused after a relaunch, with its
  cause; the open continues only work that was running when the app quit. *Test:*
  `fichero-server/tests/unit/jobs/test_durable_5357.py`, the tests cited by `activity.relaunch.only-running-work-resumes`.
- `runner.ask.one-dialogue-per-cause` — **[PARTIAL]** (#6675, #6354) a pausing kind that needs the person (`no-credit`,
  `key-refused`, `cap-refused`, `images-refused`, `export-folder-gone`) raises ONE dialogue per cause and provider, whatever number of runs it pauses (Continue and Stop run act on all of them), from
  the one alert (`run.fail.alert-on-a-failed-run`): the provider, the key or account, the kind, the provider's own words
  (redacted), what is paused (run, step, pages done of total), and the buttons the table names (Open provider page,
  Continue, Stop run). A `rate-limited`, `network`, `memory` or `interrupted` pause raises no dialogue: the row says it and
  Continue enables when the wait is up. *Test:* `fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift` (extend: a `no-credit`
  pause builds one prompt with those buttons; two pages meeting it build one prompt), `fichero/Tests/Unit/general/Models/CreditPausePromptTests.swift`
  (`oneDialoguePerCause`, `dialogueHoldsEveryRun`). Built for `no-credit`; the other pausing kinds raise no dialogue yet.
- `runner.surface.one-row-one-alert` — **[PARTIAL]** (#6354, #6597, #6599) the failure is shown in the Activity row (the
  kind's ≤ 8 row words and its fix button; `activity.pane.failure-with-its-fix-in-the-row`), in the opened run, and as the
  one alert; a job row never carries exception text (`activity.failure.no-raw-text-ever`). Built: `failed_reason` writes row
  words; the row's fix button has words; `failure` on every failed single job row, downloads and remote rows included
  (`GET /api/activity/jobs`). Not built: the generic prompt for a pausing kind other than `no-credit`.
  *Test:* `fichero-server/tests/unit/execution/test_failure_in_words_6212.py` (`test_the_jobs_list_serves_a_failed_row_with_its_failure`), `ActivityErrorRow` tests.
- `runner.no-fallback-without-asking` — **[OK]** (#5592, #6269) no runner substitutes a different model or reader for the
  one the step names: a step whose model cannot run says so and is skipped or blocked; the only fallback is the same card at
  a place the person accepted at Start (`ai.where.fallback-free-and-asked`). Built: the plan's `use-instead`; the read-a-page
  override honoured (#6269's model-choice half). *Test:* `fichero-server/tests/unit/recipes/test_fallback_free_and_asked.py`.
- `runner.cli-mcp.same-words` — **[PARTIAL]** (#6354, #6350) the CLI and MCP print the run's `failure` words, fix and
  actions; a refusal or a pause carries its typed shape intact. Built for a failed workflow run and a cloud refusal; not for a
  paused recipe run's cause or a remote job. *Test:* `fichero-cli/tests/test_cli_run_failure_words_6354`,
  `fichero-server/tests/unit/mcp/test_mcp_run_failure_6354`.

### B. Inputs, models and empty results (the recipe's half, owned by `recipes-run.md` §13)

- `runner.inputs.page-waits` — **[OK]** (#6673; `recipes-run.steps.a-page-waits-for-its-inputs` owns it) a step runs on a
  page only when every step it needs finished on that page; a later step never "completes" on nothing. *Test:*
  `fichero-server/tests/unit/recipes/test_a_page_waits_for_its_inputs_6673.py`.
- `runner.models.fetched-first` — **[OK]** (#6673; `recipes-run.steps.models-fetched-before-the-step` owns it) every model a
  run's steps name is on this Mac before its step starts; a failed fetch blocks that step's pages under the download, the
  other steps run. *Test:* `fichero-server/tests/unit/recipes/test_models_fetched_before_the_step_6673.py`.
- `runner.models.blocked-never-polled` — **[OK]** (#6593; `activity.pane.blocked-under-its-blocker` owns it) work that needs
  a missing or broken model is `blocked` under the blocker's row and never picked and re-deferred. *Test:*
  `fichero-server/tests/unit/jobs/test_blocked_work_waits_on_its_blocker_6593.py`.
- `runner.results.no-silent-loss` — **[PARTIAL]** (#6673, #6271) no runner drops an item it found without a word: Kraken's
  line without an outline is boxed and counted (`recipes-run.kraken.no-silent-line-loss`, built); a page a step skipped is
  counted and named with its reason on the step (#6271: 545 pages never segmented and counted done, owed); a names run
  counts its "left out: no text" pages on its row (`engine.silent.pages-left-out-of-a-names-run`, owed). *Test:*
  `fichero-server/tests/unit/llm/test_kraken_line_without_outline_is_boxed_6673.py`, `fichero-server/tests/unit/recipes/test_left_out_is_not_done_6271.py`.
  Built: #6271's skipped pages are counted and named on the step (`left_out`), never "already done".
- `runner.results.counted-done-only-with-a-result` — **[PARTIAL]** (#6271, #6673) a page is done for a step only when the
  step's result is there (lines on the working pass, a reading on each line, a judgement "blank"); a page with no result and
  no judgement is neither done nor silent. Built for the steps §13 covers; owed for `read-a-line`'s done check against pages
  Kraken never saw (#6271).
  Built: `read-a-line`'s done check for a page with no lines (`test_left_out_is_not_done_6271.py`).

### C. Each runner (what each must do; the owning spec is named)

- `runner.local.kraken` — **[PARTIAL]** (#6673, #6587, #6351; `ai/local-runtimes.md`, `recipes-run.md` §7 and §13 own the
  details) Kraken's segmenter and reader: a missing model is `model-missing` (blocked under the download), a model that
  will not load `model-broken`, a page that does not fit `memory` (shrunk and said, #6351), a line without an outline boxed
  and counted, an empty read named ("most lines came back empty"), an exception on a page `unexpected` for that page only;
  resident models are released only when idle or before another heavy model, never under a run's own stage. Built: the
  outline fix, the empty-lines words, the fetch before the step, one heavy model in sequence. Owed: Kraken's own
  reliability measured (`recipes-run.kraken.reliability-measured`); the unit tests that need a downloaded model (#6587).
- `runner.local.spacy` — **[PARTIAL]** (#5359, #6236; `runtime.spacy.*` in `ai/local-runtimes.md`) a pipeline not on this
  Mac is `model-missing` (blocked, downloaded as data), a pinned pipeline is never swapped, a page past its time limit is
  left out with its reason and the step goes on (`recipes-run.reliability.a-page-never-spins-silently`). Owed: the names
  step's spaCy call as a row of its own, so a waiting page says what for (#5359).
- `runner.local.embedder` — **[PARTIAL]** (#4395, #6591, #6593; `engine.silent.embedding-fails-every-write`,
  `recipes-run.engine.embedder-child-*` own it) the search model that cannot load is said ONCE (`model-broken`, health
  `degraded`, the embed job blocked with "Download again"), never a warning per write; a model not downloaded is fetched by
  the app's download job while the embed waits; the embed lane waits while a run's Kraken stage has pages. Built: the ledger
  entry, the blocked state, the lane wait. Owed: the Swift rows for `degraded`; `installed` only after a load check in
  Settings (#6591).
- `runner.local.mlx` — **[PARTIAL]** (#5267, #4973, #5221; `ai/local-runtimes.md` §C, `settings.local-model-refused-before-it-loads`)
  a served MLX or oMLX model is refused BEFORE it loads when this Mac cannot hold it (`memory`, with smaller models that fit
  named), is `runtime-unavailable` in a build that cannot install it, is loaded once per engine and released before Kraken;
  a page the model answers empty or malformed is `model-error` for that page. Owed: the end-to-end smoke that proves each
  runtime works (#5267); the honest runtime status the app reads (`runtime.status-from-the-endpoint`, BROKEN).
- `runner.local.apple` — **[PARTIAL]** (#6288, #5859, #4629; `ai/local-runtimes.md`, `source/models-chains-and-projects.md`)
  Apple Vision, Apple Intelligence and Foundation Models: an unsupported Mac or a model not ready is `runtime-unavailable`
  before the step; a worker that stops on a page is `model-error` for that page and is said ONCE per run, never 13 times;
  the plan never routes handwriting to a print reader (#5451). Owed: the root cause of the stopped worker (#6288).
  Built: a stopped worker's failure names the signal or exit code when the engine forked the worker itself; a seed-forked
  worker's end is not visible to the engine, so it names none.
- `runner.local.whisper-yolo-opencv` — **[GAP]** (#4628, #5525, #6592; `ai/local-runtimes.md`) Whisper, YOLO and the
  OpenCV steps (image preparation) raise the same kinds: a missing model `model-missing` with a download that reports its
  bytes (#6592), a build that cannot install it `runtime-unavailable`, a page that fails `model-error` for that page. Today
  their downloads say nothing until they end and their failures reach the row as text.
- `runner.cloud.provider` — **[PARTIAL]** (#6675, #6671, #5944, #6569; `ai/where-models-run.md` `ai.where.one-retry-policy`,
  `ui/activity-pane.md` `activity.limits.*` own the numbers) one retry layer (`llm/retry.resilient` over
  `circuit_breaker.call_with_breaker`): a 429 or in-flight budget backs off honouring Retry-After and pauses after
  `RATE_LIMIT_PAUSE_AFTER` spent calls; a 402 with no credit, a 401 and a key limit PAUSE and ask (owed, #6675); a 5xx or a
  dropped connection backs off then pauses as `network` (owed); a 404 or a refused request fails the page as `model-error`;
  one cap of calls in flight per provider across every run; LangChain's own retries off behind the breaker (owed, #5944).
  Built: LangChain's own retries off (`max_retries=0`) with a call sent at most 5 times by the breaker, the classification, the in-flight budget as a slow-down, the per-provider cap, the rate-limit pause. *Test:*
  `fichero-server/tests/unit/workflows/test_in_flight_budget_6671.py`, `test_rate_limit_backs_off_then_pauses_6584.py`.
- `runner.cloud.batch` — **[PARTIAL]** (#5940, #6251; `compute/recipe-steps-at-scale.md` owns it) a provider batch's
  errored or expired lines fail only their pages (`model-error`), a batch the account cannot pay for pauses as `no-credit`,
  a batch id the provider forgot replans its pages; Stop cancels at the provider and keeps what came back. Built against
  fakes; no real run yet.
- `runner.remote.mac` — **[GAP]** (#5951, #5592; `ai/where-models-run.md` §2.2, `compute/targets-and-connection.md`) another
  Mac is an endpoint place with an account state from a real probe; a Mac that stops answering mid-run is `network` for the
  pages it held (they pause, not fail), and the row names the Mac. Nothing today pauses for it.
- `runner.remote.cluster` — **[PARTIAL]** (#5457, #5740; `compute/hpc-runner-acenet.md` `compute.hpc.failure-states-in-words`
  owns it) a Slurm task's `sacct` state is said in words and mapped onto the table; a failed task fails only its pages;
  NODE_FAIL/PREEMPTED retry once, OUT_OF_MEMORY and TIMEOUT retry with a smaller slice, a task that fails twice is set aside
  and offered as "Read these pages again"; a login that lapses (MFA) pauses the watch and says so. Built: the words from
  `sacct`; owed: the retries, the pause on a lapsed session, the row under its recipe step (#5740).
- `runner.remote.hf-jobs` — **[PARTIAL]** (#5398, #5412, #5740; `training/hf_jobs.py`, `remote_read/job.py`) a Job that
  cannot start for want of a token is `key-refused`, one the account cannot pay for `no-credit`, a Job killed mid-way
  `interrupted` with its shard resent once; a cancel before submit sends nothing (#5412, owed); the row sits under its
  recipe step with far-side state, shards and cost (#5740, owed).
- `runner.download` — **[PARTIAL]** (#6592, #5649, #6591) every model download is a `download-model` job that reports its
  bytes and time left, resumes at launch whichever project started it (#5649, owner's ruling owed), and marks a model
  `installed` only after a load check; a failed download is `network` (Retry) or `model-broken` (Download again), never
  silent.
- `runner.security.yolo-weights-pinned` — **[OK]** (#6697; `tests/unit/llm/test_yolo_pinned_and_hashed_6697.py`) the YOLO
  layout weights are a pickle: the download names a commit revision, and a file whose sha256 differs from the pinned one is
  refused as `model-broken` and never reaches `YOLO()`.
- `runner.security.socket-and-keychain` — **[OK]** (#6704, #4818; `tests/unit/security/test_keychain_write_and_socket_mode_6704.py`)
  the engine's Unix socket is mode 0600 right after bind; the keychain write passes the key on stdin (`security -i`), never
  argv, and `security` is run as `/usr/bin/security`; the engine's `httpx` and `httpcore` loggers sit at WARNING so no request
  URL is logged at INFO.

### D. Memory, and the Mac staying usable

- `runner.memory.one-heavy-model` — **[OK]** (#6000, #6673; `recipes-run.memory.one-heavy-model`,
  `recipes-run.memory.one-heavy-model-in-sequence` own it) one heavy model resident at a time on a Mac of 16 GB or less;
  the embed lane waits while a run's Kraken stage has pages; Kraken's models are never released for an embed or a thumbnail
  while its stage has pages left. *Tests:* `fichero-server/tests/unit/jobs/test_one_heavy_when_memory_tight.py`,
  `fichero-server/tests/unit/execution/test_one_heavy_model_in_sequence_6673.py`.
- `runner.memory.hold-not-kill` — **[PARTIAL]** (#6075, #4987; `activity.throttle.hold-when-swapping`,
  `recipes-run.memory.hold-when-paging` own it) new heavy work is held while the Mac pages; a hold that outlasts its
  patience becomes a `memory` pause with the row saying so, never a killed engine. Built: the hold; a page of a run held
  for memory for `throttle.MEMORY_HOLD_PATIENCE_SECONDS` (ten minutes) asks its run to pause, and the paused run records a
  `memory` failure with Continue first (`retry.pause_the_run_for_memory`, `failure.memory_pause_failure`; *test:*
  `fichero-server/tests/unit/jobs/test_kraken_holds_under_swap_and_pressure_6075.py`). Owed: the first paging reading
  reading the previous sample from the run's record, the popover's paging line beside the pause, the measured ceilings
  (`recipes-run.memory.peak-ceiling-per-model-kind`).
- `runner.memory.recorded` — **[OK]** (#6673; `recipes-run.memory.recorded-per-step` owns it) each step records the Mac's
  RAM, the engine's peak, swap, pressure and model loads and unloads, in the run's record and in Save Logs for Support.
  *Test:* `fichero-server/tests/unit/recipes/test_memory_recorded_per_step_6673.py`.
- `runner.measured.runtime-matrix` — **[PARTIAL]** (#6675) every runtime the engine has is measured on the real Mac, not stubbed:
  `scripts/runtime_matrix.py` runs a fixed sample of 5 public test-fixture page images through each runtime's own entry
  point (Kraken segment, Kraken read, MLX vision read, the embedder, spaCy names, YOLO, OpenCV preprocessing, Whisper,
  Apple on macOS 27+), twice in a row, on a scratch state dir and library (never the app's). Per runtime it records: ran
  ok or failed (the failure kind and words from the kinds table), seconds per page with the first page (cold load)
  separate, peak RSS, and how many times the model was loaded across the two passes (1 is right; 2 or more means it
  unloads between pages), plus the Mac's chip, RAM, macOS and free memory at the start. `--remote hf-jobs|cluster` is a
  dry-run only, never a paid job. Output: one JSON file and a Markdown table on stdout; exit 0 even when runtimes fail.
  *Acceptance:* with every runtime stubbed (one ok, one failing, one loading twice) the table and JSON name each result.
  Built: the script, with every runtime stubbed in its test; the MLX model is loaded once per process, and the embedder row runs with `FICHERO_EMBED_IN_PROCESS=1` so its peak RSS includes the model. Owed: Apple (no Python entry in the engine), and counted loads for MLX (read through `mlx_vlm` directly) and Whisper.
  *Test:* `fichero-server/tests/unit/scripts/test_runtime_matrix.py`. `Spec-change: owner, the runtime matrix`.
- `runner.mac.stays-usable` — **[PARTIAL]** (#5819, #6230, #6263; `activity.throttle.use-means-slower`,
  `activity.throttle.in-use-slows-to-half` own it) automatic work goes on while the person uses the Mac, at half the
  performance cores and background QoS; a run the person started begins at once, throttled, never waits for Run now
  (#6263). Built: the one in-use rule; a started run's step is never held for use or battery, only for memory or heat (*test:*
  `fichero-server/tests/unit/jobs/test_started_run_begins_at_once_6263.py`); an import's automatic Kraken reads on half the
  performance cores at utility QoS. Owed: other automatic work in use still drops to the lowest QoS class (#6230), and the
  Air's step hold of #6263, not reproduced.

### E. The hand-run paths (the context menus, the workflow bar, the recipe runner)

- `runner.hand-run.same-contract` — **[PARTIAL]** (#6349, #6354, #4961, #4963) a run started from a context menu
  ("Run the Recipe on This Folder…", Read, Find Lines, Read Again, Retry, Describe, Translate), from the workflow bar or
  from the selection runner goes through the same lane, the same table and the same pause path as a recipe's step; a
  refusal before Start is the typed refusal alert; a failure mid-run is the one alert; a start that resolves to nothing says
  so in words (never "resolved to 0 processable files" from the workflow row itself, #4961); the bar sends no model override
  a workflow cannot take (#4963). Built: the typed refusal on the hand-run paths (uncompiled); owed: the mid-run alert, the
  two scope bugs.
- `runner.hand-run.never-swallowed` — **[GAP]** (#3931, #6602) no hand-run path drops the engine's error body: every
  `.undocumented(statusCode, _)` site that starts work reads the engine's `detail` and shows its words (182 sites drop it,
  #3931); a refused grant shows the engine's reason (#6602).

### F. The engine: one failure, on the run (carried from the former failure-alerts spec, 2026-11-18)

- `run.fail.kinds-table` [PARTIAL] (#6354; built: the kinds, the served model, `classify`, `redact`, the provider and model names in the words, `unexpected` for what the table does not name, and the kind beside the page's legacy category; not built: `_typed_failure` and `_classify_provider_error` answering from the table, so the per-page `error_category`/`error_hint`/`error_action` still come from their own code) — `llm/failure` holds `RunFailure` (`kind`, `words`, `fix`, `actions[]`
  of `{kind, control?, usd?, retry_after_seconds?}`, `provider`, `model`, `step`, `pages_done`, `pages_total`,
  `exception_type`, `detail` (the error's first line, redacted as in C), `refusal: CloudRefusal | None`) and one function
  `classify(exc, text, *, step, provider, model, done, total) -> RunFailure` that is the table above. `_typed_failure` and
  `_classify_provider_error` call it (the per-page `error_category`/`error_hint`/`error_action` stay as they are, now
  from the same table, so a page's reason and the run's agree). Tests:
  `fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py` (each row of the table from its exception; a 401
  under `httpx` words is `key-refused`; a bare `RuntimeError("boom")` is `unexpected` with `exception_type` `RuntimeError`;
  no answer is ever `unknown`; the words name the provider's display name, never the breaker's internals).
- `run.fail.run-carries-its-failure` [PARTIAL] (#6354; built: the row, the status route, the jobs list, the stream and a recipe run's failed stage, a retry clearing it; not built: a stub provider raising each kind with the row, the status route and the jobs list compared end to end) — when a run ends `failed` the runner stores `failure` (the
  `RunFailure`, JSON) on the run row beside `error` (the words stay `error`, so nothing that reads `reason` changes);
  `GET /api/workflow-execution/threads/{id}/status` serves `failure`; `GET /api/activity/jobs` serves it on the failed
  `BackgroundJob` (`failure: RunFailure | None`); a recipe run whose step's run failed carries that run's `failure`
  with `step` filled, its `reason` stays `outcome_why`'s words. A run paused at a cap or by the images rule carries the
  `cap-refused`/`images-refused` failure with its `refusal`, state `paused`. A run paused by a person or by shutdown
  carries none. An OpenAPI regen. Tests:
  `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354.py` (a stub provider that raises each kind;
  the row, the status route and the jobs list agree; a paused-by-person run has `failure: null`),
  `fichero-server/tests/unit/recipes/test_recipe_run_carries_step_failure_6354.py`.
- `run.fail.one-failure-per-attempt` [PARTIAL] (#6354; built: only the run's end writes a failure, a retried run gets a new one with its own `failed_at`; not built: a test that three failing calls leave one failure) — the retry layer's own retries (`llm/retry.py`, `page_retry`) and a
  page's failure write no `failure`; only the run's end does, once; a run retried through Retry / Read them again that
  fails again gets a new `failure` and a new `failed_at`, so the attempt is told apart by `id@failed_at`
  (`activity.jobs.failed-at`). Tests: `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354.py`
  (three calls fail, one `failure`; a retried run has two attempts, each with its own `failed_at`).
- `run.fail.failed-stream-event` [PARTIAL] (#6354; built: the `error` and `systemic_error` events and the `complete` event of a run whose every file failed carry `failure`; the runner has no event named `workflow_failed`) — the execution stream's `workflow_failed` event (and `systemic_error`)
  carries `failure`, so a client on the stream need not poll; the `refused` event stays for the cap pause as built.
  Tests: `fichero-server/tests/unit/workflows/test_failed_event_carries_failure_6354.py`.
- `run.fail.unexpected-is-logged-whole` [OK] (#6354) — an
  `unexpected` failure writes the full traceback to the engine log at ERROR, once, with the run id, so the bug report
  can quote it; the served `detail` is the exception's first line only. Tests:
  `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354.py` (`caplog`: one ERROR with the run id).

### G. The bug report (carried from the former failure-alerts spec, 2026-11-18)

- `run.fail.bug-report-route` [OK] (#6354; owner 2026-11-08: the route builds the report, the app saves it on this Mac and the owner sends it, nothing leaves the Mac automatically, `run.fail.bug-report-destination`) — `POST /api/activity/jobs/{id}/bug-report` builds and answers the report
  for a failed run: `{title, body, attachments: [{name, text}]}` where `title` is "<kind>: <words' first sentence>",
  `body` is plain text and `attachments` are `run.json` (the fields in C) and `log.txt` (the run's Problems log lines,
  `activity.log.problems-first`, redacted). A run that is not failed answers 409 in words. Tests:
  `fichero-server/tests/unit/api/test_bug_report_route_6354.py`.
- `run.fail.bug-report-contents` [PARTIAL] (#6354; built: the failure, the traceback of an `unexpected` failure, the workflow's and the step's names, the provider's and model's display names, pages done and total, start, end, duration, the Problems lines, the engine version and tier, macOS and the Mac model; not built: the app's version and build, which the app adds, and where it ran, in `activity.summary.where-and-model`'s words) — the report carries: the app version, build and tier, the engine version,
  macOS and the Mac model, the failure (kind, words, `exception_type`, `detail`), the redacted traceback of an
  `unexpected` failure (from the engine log, by run id), the workflow's name and the step's, the provider's and model's
  display names, where it ran (`activity.summary.where-and-model`'s words), pages done and total, the run's start and
  end, its duration, and the run's Problems lines. Tests: `fichero-server/tests/unit/api/test_bug_report_route_6354.py`
  (every named field present for a stubbed `unexpected` run).
- `run.fail.bug-report-excludes-the-private` [PARTIAL] (#6354; built: paths, keys, bearer headers, key-shaped values, document and page ids by their names, and a long quoted string in an error message, through `llm/failure.redact`; not built: a person's name from the account chain, a page's text that an error message carries unquoted, and the real engine-log fixtures held to more than their timestamps surviving) — the report never carries: a file path (every `/…/` run is
  replaced by `<path>`, the home folder by `~`, before anything else), a library or project path, a page's text or a
  model's answer, a prompt, a key, token or bearer header (anything matching a key shape or the words `key`, `token`,
  `secret`, `password`, `authorization` with a value), a person's name from the account chain, or a document id. The
  redaction is one function (`llm/failure.redact`) used by `detail`, the traceback and the log lines, and it is tested
  against the real log fixtures in `tests/fixtures/engine_logs/`. Tests:
  `fichero-server/tests/unit/api/test_bug_report_is_redacted_6354.py` (a traceback with a home path, an API key in a
  URL, a bearer header and a page's text in an exception message: none of them in the report; the fixtures' lines).
- `run.fail.bug-report-destination` [GAP] (#6354; question 2 RULED by the owner 2026-11-08) — the report is SAVED on this Mac and the owner sends it: Save Bug Report… writes the `.zip` of the three parts through the Save panel (default name `fichero-bug-<date>-<kind>.zip`, in the folder the person chooses), and the alert then offers Reveal in Finder and the maintainer's address to attach it to; nothing leaves the Mac automatically, no upload, no mail composed without the person, no telemetry; the engine route stays the one source of the report. Tests: `RunBugReportTests` (the zip is written where chosen and nothing is sent; the reveal shows the file; a run with no network behaves the same).

### H. The app: an alert that says what happened and what to do (carried from the former failure-alerts spec, 2026-11-18)

- `run.fail.alert-on-a-failed-run` [GAP] (#6354) — when a run the app shows ends with a `failure`, the app raises ONE
  alert, `RunFailureAlert` (the `CloudRefusalAlert` pattern: a `.alert` on `ContentView` from an observable prompt):
  the title "Fichero stopped this run" (the cap alert's title) or "<Workflow> stopped", the message `words` then `fix`,
  and a button per action in the engine's order, titled: `retry` "Run It Again", `resume` "Resume", `open-settings`
  "Open Settings…", `choose-model` "Choose a Model…", `report-bug` "Send a Bug Report…", `reconnect` "Reconnect…", then
  "Show in Activity" and "Not Now". No raw string, no "Server error". `cap-refused` and `images-refused` are handed to
  `CloudRefusalAlert` with the run to resume (decision 5). Tests:
  `fichero/Tests/Unit/general/Views/RunFailureAlertTests` (buttons from each served kind in the engine's order;
  a cap kind builds a `CloudRefusalPrompt` whose resend resumes the run; an `unexpected` failure offers the report first;
  no kind ever shows the raw `detail` in the message).
- `run.fail.one-alert-per-attempt` [GAP] (#6354) — the app alerts once per `id@failed_at` (`ActivityErrorWindow.seenKey`),
  records the key as seen when the alert is dismissed or acted on, keeps the seen set across launches with the ledger's,
  and never alerts for a failure older than an hour at launch or already seen; a retry that fails again alerts again.
  Tests: `fichero/Tests/Unit/general/Models/RunFailureLedgerTests` (the same failure listed by two polls alerts
  once; a relaunch with the key seen alerts nothing; a new `failed_at` alerts).
- `run.fail.alerts-coalesce-by-cause` [GAP] (#6354) — several runs failing within a minute for one cause and provider
  (`no-credit`, `key-refused`, `rate-limited`, `network`) raise one alert naming them ("3 runs stopped: <Provider> has no
  credit left…") with the same buttons; `retry` retries them all. Tests:
  `fichero/Tests/Unit/general/Models/RunFailureLedgerTests` (three `no-credit` failures, one alert, three ids).
- `run.fail.alert-reaches-a-background-app` [GAP] (#6354; question 3) — when the app is not active the same words go
  out as a user notification (`UNUserNotificationCenter`, asked for once, the first time a run fails); pressing it
  opens the Activity window on the run and raises the alert. With permission refused, the alert waits for the app to
  come to the front. Tests: `fichero/Tests/Unit/general/Models/RunFailureNotificationTests` (the notification's
  text is the alert's; one per attempt; pure content, no `UNUserNotificationCenter` in the test).
- `run.fail.actions-act` [GAP] (#6354) — `retry` calls the run's Retry (`activity.window.one-button`'s), `resume` its
  Resume with the once flags when the refusal asked for them, `open-settings` opens the control the action names
  (`settings.ai.providers` is new: the provider's row, its key field focused), `choose-model` opens the step's model
  choice (Set Up's step for a recipe run, the workflow's model for a hand run), `reconnect` runs
  `engine.silent.originals-one-press-reconnect`'s picker, `report-bug` the flow in D. Tests:
  `fichero/Tests/Unit/general/Views/RunFailureAlertTests` (each action calls its one route on a stub client).
- `run.fail.activity-says-the-kind` [GAP] (#6354) — a failed row in Activity (DONE TODAY's line, the popover's error
  line, the opened run's heading) says the failure's `words` first and its `fix` under them, from `failure`, falling back
  to `reason` for a row with none (an engine from before this); the opened run has the same action buttons as the
  alert. Tests: `fichero/Tests/Unit/general/Models/ActivityRowFailureWordsTests`.

### I. Sending the bug report (carried from the former failure-alerts spec, 2026-11-18)

- `run.fail.report-shows-then-sends` [GAP] (#6354) — "Send a Bug Report…" asks the engine for the report, shows its
  title, body and the names of its attachments, says in one line what is left out (paths, keys, your pages' text), and
  only then saves it (owner 2026-11-08: Save Bug Report…, a `.zip` of the three parts, through the Save panel; the
  owner sends it, nothing leaves the Mac by itself). Tests: `fichero/Tests/Unit/general/App/RunBugReportTests` (the preview text is the engine's;
  nothing is sent before Continue; the zip holds exactly the three parts).

### J. CLI and MCP (carried from the former failure-alerts spec, 2026-11-18)

- `run.fail.cli-says-the-fix` [PARTIAL] (#6354; built: `fichero workflow run --wait` and `fichero workflow status` print a failed run's words, `Fix:` and each action as its command, the bug report first for a bug in Fichero, no traceback, exit 1 from `run --wait`; the commands are the generated ones, `fichero activity-api retry-job`, `fichero activity-api post-job-bug-report` and `fichero providers set-api-key`; not built: `fichero activity jobs` saying it (the generated `fichero activity-api get-jobs` prints `failure` in its JSON), the `bug-report <id> --out <file>` command as named, and exit 1 from `workflow status`) — `fichero workflow run --wait`, `fichero workflow status` and
  `fichero activity jobs` print a failed run's `words`, then `Fix: <fix>`, then each action as the command that does it
  (`fichero workflow retry <id>`, `fichero ai providers set-key <provider>` or the regen's name, `fichero activity
  bug-report <id> --out <file>`); exit 1 for a failure, 3 for a cloud refusal as built; an `unexpected` failure says
  "a bug in Fichero" and the bug-report command first; never a traceback. Tests:
  `fichero-cli/tests/test_cli_run_failure_words_6354`.
- `run.fail.mcp-says-the-fix` [PARTIAL] (#6354; built: a failed run's `failure` reaches the caller intact in the status and jobs answers, and an error `detail` carrying it names the tool for each action, the bug report first for a bug in Fichero; not built: `fichero_workflow_run` with `wait`, which the tool does not have, so no engine error carries `detail.failure` today) — `fichero_workflow_status` and `fichero_activity_jobs` return `failure`
  intact; `fichero_workflow_run` with `wait` returns it on a failed run as `EngineError` with `detail.failure`, the
  message naming the tool for each action (`fichero_workflow_retry`, `fichero_activity_bug_report` from the regen).
  Tests: `fichero-server/tests/unit/mcp/test_mcp_run_failure_6354`.

### K. The failure on a run, carried from the former Activity spec section J (2026-11-18)

Section J (owner 2026-11-13, #6354) owned the alert before this contract existed. Its table of thirteen kinds was superseded by
section 1 above (`runner.kinds.one-table`, `run.fail.kinds-table`) and is gone. Its three behaviours that still stand are below,
unchanged. Nine were deleted as superseded, each by the id that now says it: `activity.failure.never-silent` by
`run.fail.alert-on-a-failed-run` and `runner.ask.one-dialogue-per-cause`; `activity.failure.kind-is-typed-in-the-engine` by
`run.fail.run-carries-its-failure`; `activity.failure.fixed-table` by `run.fail.kinds-table` and `runner.kinds.one-table`;
`activity.failure.app-only-displays` and `activity.failure.row-says-the-same` by `run.fail.activity-says-the-kind` and
`runner.surface.one-row-one-alert`; `activity.failure.one-alert-per-run` by `run.fail.one-alert-per-attempt` and
`run.fail.alerts-coalesce-by-cause`; `activity.failure.alert-names-the-fix` by `run.fail.actions-act`;
`activity.failure.reaches-the-person-off-window` by `run.fail.alert-reaches-a-background-app`;
`activity.failure.unknown-offers-a-report` by `run.fail.bug-report-route`, `run.fail.bug-report-contents` and
`run.fail.report-shows-then-sends`. Where the carried words below name the old kinds (`out-of-credit`, `cap-reached`,
`provider-down`, `disk-full`, `unknown`), read the contract's (`no-credit`, `cap-refused`, `network`, `unexpected`; `disk-full` is
open question 3). No test cited any of the twelve ids.

- `activity.failure.cancelled-is-not-a-failure` — **[PARTIAL]** (#6354; #6005, #4402; engine +
  app) a run, step or page the person stopped ends `cancelled` with "Stopped by you"
  (`activity.run.stop-reaches-in-flight-calls`), carries no `failure`, lights no glyph, raises no
  alert and no notification; so does a run paused by the person or by the engine's own shutdown
  (`activity.run.quit-pauses`). A page a Stop skipped is not counted as failed. *Built:* the
  `cancelled` state and its words. *Not built:* the rule that an alert never fires for it (there is
  no alert yet). *Tests (to write):* in `test_failure_kind_is_typed_6354.py`, a stopped run has
  `failure` null; in `ActivityFailureAlertTests.swift`, it raises nothing.
- `activity.failure.credit-exhausted-pauses` — **[PARTIAL]** (#6354, the pause half needs an issue of
  its own under #6354; #5933, `recipes-run.control.pause-and-resume`; engine; owner 2026-11-13) a
  failure the person can mend, or that mends itself, without losing the run (`out-of-credit`,
  `cap-reached`, `rate-limited`, `key-refused`, `provider-down`, `network`, `disk-full`, `memory`)
  PAUSES the run instead of failing it, and the alert is raised for the pause: the step's run settles `paused` at its
  checkpoint with `failure` set (the same path a review step takes, `activity.run.review-step-pauses`,
  and the one the engine's shutdown takes), the pages already read are kept and counted
  (`activity.failure.partial-results-kept`), the recipe run parks on the paused step
  (`recipes/runner.py` `ParkedOnStepRun`, #5933) and its row reads "Paused: <words>" with Resume,
  and Resume carries on from the failed step over the pages that were not done, never re-reading a
  done page (`activity.retry.one-row`, `activity.durable.idempotent`). The breaker stays open for
  its 30 s, so a Resume pressed before credit is added fails fast again and the alert updates
  rather than repeats. A failure of the other kinds ends the run `failed` as today, with the
  partial results kept. The engine, not the app, decides which kinds pause: `pauses: true` on the
  table's row. *Built:* a quota error is not page-retried (`builder.py:2192-2196`), pause at a
  checkpoint (#5933), park on a paused step. *Not built:* settling `paused` on a fatal provider
  error (today `SystemicErrorDetected` → `failed`, `runner.py:2710`), the recipe parking on it,
  the `failure` on a paused row. *Tests (to write):*
  `test_out_of_credit_pauses_the_run_6354.py` (a 402 on page 4 of
  10 leaves the run `paused` with `failure.kind == "out-of-credit"`, three pages done and kept,
  and Resume after the stub recovers reads pages 4 to 10 only and ends `done`);
  `test_recipe_parks_on_a_paused_step_6354.py` (the recipe row
  reads paused with the step's words and takes the step up again on Resume).
- `activity.failure.partial-results-kept` — **[PARTIAL]** (#6354; #5937, #5758, #4315) whatever a
  run finished before it failed or paused is kept and shown: the pages read stay read, their
  entities and claims stay, the run's account counts them, and the row says how many ("The run is
  paused; the 212 pages it finished are kept"). A failed run reverts only the pages it was in the
  middle of to pending (`runner.py:2773`, `_finalize_documents("failed")`), never the done ones.
  *Built:* the account's done count on a failed run (`activity.run.partial-said-on-a-done-row`,
  `activity.run.step-honest-about-lost-pages`); the revert of in-flight pages (#4315). *Not
  built:* the count in the words, pinned against a mid-run 402. *Tests:*
  `fichero-server/tests/unit/jobs/test_partial_is_said_on_a_done_row_5937.py`; to write, in
  `test_out_of_credit_pauses_the_run_6354.py`, the three done pages are still read after the pause.

## Changes to existing behaviours (made in the integration of 2026-11-18)

1. The former Activity spec §J's table of thirteen kinds (`out-of-credit`, `cap-reached`, `provider-down`,
   `model-not-found`, `disk-full`, `engine-crashed`, `input-unreadable`, `refused-by-a-rule`, `unknown`, …) is superseded by
   the sixteen kinds of section F (`run.fail.kinds-table`, carried from the former failure-alerts spec) and `llm/failure.py`; §J's three
   live behaviours (`activity.failure.credit-exhausted-pauses`, `activity.failure.partial-results-kept`,
   `activity.failure.cancelled-is-not-a-failure`) are section K here since 2026-11-18, the rest deleted as superseded (section K says
   by which id). `disk-full` is a wanted kind the code lacks (listed under "Issues to file" in the plan).
2. The former failure-alerts spec decision 2 ("a failed run is one that ends `failed` … the run stopped at page N of M") is
   amended: `no-credit`, `key-refused`, `network` and `memory` PAUSE and ask (owner 2026-11-13 and 2026-11-18, #6675); the
   words of those rows say "paused", not "stopped". Decision 9 and the `rate-limited` row already pause.
3. `source/recipes-run.md` section 13's last line ("a provider's in-flight or rate limit pauses the run") grows to every
   pausing kind, by pointer to section 1 here.
4. `ai/where-models-run.md` `ai.where.fallback-across-places` stays [GAP] and now says the fallback is never silent and
   never a different model (it already did); it points here for what happens instead (a pause that asks).
5. `source/engine-silent-failures.md`'s "needs attention" row and `compute/hpc-runner-acenet.md`
   `compute.hpc.failure-states-in-words` point at the one table for their kinds.

Not changed: the lanes, the throttle rule, the batch loop, the alert's shape, the bug report.

## Build order

The ordered plan with its tests and the issues each step closes is `reviews/2026-11-18-runner-reliability-plan.md`;
the steps below are the same steps, in the shape the harness reads.

### Stage 1 — The shared foundation

#### Step 1.1 — The table's pause-or-fail and retry columns; no-credit and key-refused pause (#6675)
- Behaviours: `runner.kinds.pause-or-fail-is-the-tables`, `runner.pause.one-path`, `runner.kinds.one-table`, `activity.failure.credit-exhausted-pauses`, `activity.failure.partial-results-kept`
- Tests: fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py, fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py (plus the new pause-or-fail file described under `runner.kinds.pause-or-fail-is-the-tables`)
- Size: M

#### Step 1.2 — Continue from the first item not done, for every pausing kind; the recipe parks on it (#6569)
- Behaviours: `runner.pause.continue-from-first-not-done`, `runner.pause.survives-relaunch`
- Tests: fichero-server/tests/unit/recipes/test_recipe_pause_5933.py, fichero-server/tests/unit/recipes/test_a_page_waits_for_its_inputs_6673.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — One dialogue per cause; the row and the alert (#6354, #6597)
- Behaviours: `runner.ask.one-dialogue-per-cause`, `runner.surface.one-row-one-alert`, `runner.cli-mcp.same-words`, `activity.failure.cancelled-is-not-a-failure`
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift, fichero-server/tests/unit/execution/test_failure_in_words_6212.py
- Depends on: 1.1
- Size: M

### Stage 2 — Each runner on the contract

#### Step 2.1 — Cloud providers: network pauses, LangChain retries off, the batch's kinds (#5944)
- Behaviours: `runner.cloud.provider`, `runner.cloud.batch`
- Tests: fichero-server/tests/unit/workflows/test_in_flight_budget_6671.py, fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py
- Depends on: 1.1
- Size: M

#### Step 2.2 — Local runtimes: Kraken, spaCy, the embedder, MLX (#5267, #6271)
- Behaviours: `runner.local.kraken`, `runner.local.spacy`, `runner.local.embedder`, `runner.local.mlx`, `runner.results.no-silent-loss`, `runner.results.counted-done-only-with-a-result`
- Tests: fichero-server/tests/unit/llm/test_kraken_line_without_outline_is_boxed_6673.py, fichero-server/tests/unit/db/test_embedder_model_missing_says_so.py
- Depends on: 1.1
- Size: L

#### Step 2.3 — Apple, Whisper, YOLO, OpenCV and the downloads (#6288, #6592)
- Behaviours: `runner.local.apple`, `runner.local.whisper-yolo-opencv`, `runner.download`
- Tests: fichero-server/tests/unit/llm/test_spacy_pipelines_as_files_to_spec.py, fichero-server/tests/unit/llm/test_every_download_reports_bytes_6592.py
- Depends on: 2.2
- Size: M

#### Step 2.4 — Remote places: another Mac, the cluster, HF Jobs under their step (#5740)
- Behaviours: `runner.remote.mac`, `runner.remote.cluster`, `runner.remote.hf-jobs`
- Tests: fichero-server/tests/unit/remote_read/test_slurm_target.py, fichero-server/tests/unit/remote_read/test_read_at_scale_job.py
- Depends on: 1.1
- Size: M

### Stage 3 — Memory and the hand-run paths

#### Step 3.1 — Hold, then pause, never kill; the Mac stays usable (#6075, #6230, #6263)
- Behaviours: `runner.memory.hold-not-kill`, `runner.mac.stays-usable`
- Tests: fichero-server/tests/unit/jobs/test_kraken_holds_under_swap_and_pressure_6075.py, fichero-server/tests/unit/jobs/test_throttle.py
- Depends on: 1.1
- Size: M

#### Step 3.2 — Context menus, the workflow bar and the selection runner on the contract (#4961, #4963, #3931)
- Behaviours: `runner.hand-run.same-contract`, `runner.hand-run.never-swallowed`
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift (plus a new Swift test of the workflow bar's scope and override, #4961, #4963, to write)
- Depends on: 1.3
- Size: M

The two stages below are the former failure-alerts spec's build order, carried here on 2026-11-18 with its steps renumbered (its 1.x became 4.x, its 2.x became 5.x); every step keeps #6354. Stage 1 above (the pause-or-fail columns) and Stage 4 (the kinds table and the served model) describe the same table from two sides and are built together.

### Stage 4 — The engine: one failure, on the run

#### Step 4.1 — The kinds table and the served model (#6354)
- Behaviours: `run.fail.kinds-table`, `run.fail.unexpected-is-logged-whole`
- Files: a new `llm/failure` (`RunFailure`, `classify`, `redact`), `execution/runner.py` (`_typed_failure` and `_classify_provider_error` call it), `workflows/circuit_breaker.py` (export `provider_display`)
- Tests: fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py
- Size: M

#### Step 4.2 — The run carries its failure; the stream says it (#6354)
- Behaviours: `run.fail.run-carries-its-failure`, `run.fail.one-failure-per-attempt`, `run.fail.failed-stream-event`
- Files: `execution/runner.py` (the three failure ends and the cap pause), `workflows/activity_store.py` (a `failure` column), `api/routes/workflow_execution/schemas.py` and `core.py` (status), `api/routes/system/activity.py` (`BackgroundJob.failure`), `recipes/runner.py` (the step's failure on the recipe run), the OpenAPI regen
- Tests: fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354, fichero-server/tests/unit/recipes/test_recipe_run_carries_step_failure_6354, fichero-server/tests/unit/workflows/test_failed_event_carries_failure_6354
- Depends on: 4.1
- Size: M

#### Step 4.3 — The bug report, built and redacted (#6354)
- Behaviours: `run.fail.bug-report-route`, `run.fail.bug-report-contents`, `run.fail.bug-report-excludes-the-private`
- Files: a new `api/routes/system/bug_report`, `llm/failure` (`redact`), `core/engine_log.py` (read a run's traceback by id), the regen
- Tests: fichero-server/tests/unit/api/test_bug_report_route_6354, fichero-server/tests/unit/api/test_bug_report_is_redacted_6354
- Depends on: 4.2
- Size: M

#### Step 4.4 — The CLI and MCP say the fix (#6354)
- Behaviours: `run.fail.cli-says-the-fix`, `run.fail.mcp-says-the-fix`
- Files: `fichero-cli/src/fichero_cli/__main__.py` (`workflow_run`, `workflow_status`, the activity commands, a `bug-report` command), `fichero-mcp/src/fichero_mcp/openapi_runtime.py` (`_with_ways_through` grows a `failure` case), the regen outputs
- Tests: fichero-cli/tests/test_cli_run_failure_words_6354, fichero-server/tests/unit/mcp/test_mcp_run_failure_6354
- Depends on: 4.3
- Size: S

### Stage 5 — The app: the alert, once, with its buttons

#### Step 5.1 — The alert and its ledger (#6354)
- Behaviours: `run.fail.alert-on-a-failed-run`, `run.fail.one-alert-per-attempt`, `run.fail.alerts-coalesce-by-cause`
- Files: a new `Views/Shell/RunFailureAlert` and `Models/RunFailurePrompt`, `Models/ActivityErrorLedger.swift` (the alert's seen set beside the popover's), `ActivityStore` (a failed job's `failure`), `ContentView.swift` (the modifier), `CloudRefusalPrompt.swift` (a resume resend)
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests, fichero/Tests/Unit/general/Models/RunFailureLedgerTests
- Depends on: 4.2
- Size: M

#### Step 5.2 — The actions act; Activity says the kind (#6354)
- Behaviours: `run.fail.actions-act`, `run.fail.activity-says-the-kind`
- Files: `RunFailureAlert.swift`, `AISettingsView+Tabs.swift` (`settings.ai.providers` deep link), `ActivityWindowGroups`/`ActivityMonitorRow` (the words and fix), `ActivityPopoverSummary.swift`, the opened run's details
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests, fichero/Tests/Unit/general/Models/ActivityRowFailureWordsTests
- Depends on: 5.1
- Size: M

#### Step 5.3 — Send a Bug Report, and the background app (#6354)
- Behaviours: `run.fail.report-shows-then-sends`, `run.fail.bug-report-destination`, `run.fail.alert-reaches-a-background-app`
- Files: a new `App/Menus/Help/RunBugReport` (beside `SaveLogsForSupport.swift`, sharing its confirm-then-act shape), a new `Models/RunFailureNotification`
- Tests: fichero/Tests/Unit/general/App/RunBugReportTests, fichero/Tests/Unit/general/Models/RunFailureNotificationTests
- Depends on: 4.3, 5.2
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | one alert per cause; the row's words and fix from `failure`; no raw text | `fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift` |
| Availability (Swift) | y | the alert modifier mounted; the hand-run paths reach it | the same |
| Backend (pytest) | y | every kind's pause-or-fail; Continue from the first item not done; each runner's failure a `RunFailure` | `fichero-server/tests/unit/llm/`, `fichero-server/tests/unit/recipes/`, `fichero-server/tests/unit/remote_read/` |
| MCP | y | `failure` intact on a paused recipe run | `fichero-server/tests/unit/mcp/test_mcp_run_failure_6354` |
| CLI | y | words, fix and the Continue command | `fichero-cli/tests/test_cli_run_failure_words_6354` |
| Click-around (XCUITest, Mac) | later | a stub provider's 402 pauses a run; the dialogue's buttons | — |
| Load (#4634) | y | the 100-page run with a provider that runs out of credit at page 40 pauses once and finishes after Continue | `fichero-server/tests/perf/test_recipe_run_100_pages.py` (extend) |

## Accessibility identifiers (carried from the former failure-alerts spec)

`runFailure.alert` · `runFailure.alert.action.<kind>` (`retry`, `resume`, `openSettings`, `chooseModel`, `reportBug`,
`reconnect`) · `runFailure.alert.showInActivity` · `runFailure.alert.notNow` · `runFailure.report.preview` ·
`runFailure.report.continue` · `activity.row.<jobId>.failure` (the words and fix on the row) · `settings.ai.providers`.

## UX completeness (carried from the former failure-alerts spec)

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `runFailure.alert.action.retry` | Run It Again | Starts the same run again from where it stopped | `runFailure.action.retry` | test |
| `runFailure.alert.action.reportBug` | Send a Bug Report… | Shows what the report holds before anything is sent | `runFailure.action.reportBug` | test |
| `runFailure.alert.action.openSettings` | Open Settings… | Opens the setting the failure names | `runFailure.action.openSettings` | test |
| `runFailure.alert.action.chooseModel` | Choose a Model… | Opens this step's model choice | `runFailure.action.chooseModel` | test |
| `runFailure.alert.showInActivity` | Show in Activity | Opens the run in the Activity window | `runFailure.showInActivity` | test |

## Open questions for the owner

1. **Does `network` pause the whole run, or only the pages of the provider that is unreachable?** Recommended: the
   run pauses (the next pages would fail the same way); local steps on pages already read go on.
2. **How long does a `memory` hold wait before it becomes a pause that asks?** Recommended: ten minutes of holding with no
   page admitted, then "Paused: not enough memory for <model>" with Continue and "Choose a smaller model".
3. **A `disk-full` kind.** The §J table named it; the code has none. Recommended: add it (pauses, fix "Free disk space",
   the volume named), filed as its own issue (the plan lists it).

Carried from the former failure-alerts spec (its questions 1 to 6, unanswered when it merged here):

4. **Is a partial run a failed run?** Decision 2 says no: "Done with failures: 3 of 203 pages" finished, and Activity's
   Partial line with Retry is the surface; only a run that ENDS failed, or pauses at a cap or the images rule, alerts. If
   the owner wants an alert when more than some share of pages fail (say a quarter), that is one threshold in the
   runner's `SystemicErrorDetected`, which already ends such a run failed.
5. **Where does the bug report go?** (a) a GitHub issue on the public repo, opened from the app by the person's own
   account (the app has no token; it would open a prefilled new-issue page in the browser, body length capped); (b) a
   mail to the maintainer through the Send Logs path (needs the address that `help.send-logs-to-the-maintainer` still
   lacks); (c) a local file the person attaches by hand (what the spec does until ruled); (d) a maintainer-run endpoint.
   The route builds the same report whichever is chosen.
6. **A notification when the app is in the background?** `run.fail.alert-reaches-a-background-app` asks for
   notification permission the first time a run fails. The alternative is no system notification: the alert waits for the
   app to come to the front, and the Activity pill shows red meanwhile.
7. **Does a recipe stop at a step whose failure will fail every later cloud step** (`no-credit`, `key-refused`,
   `cap-refused`, `network`), or carry on to the next step as it does today and alert once at the end? The spec alerts at
   the step's failure and leaves the recipe's own behaviour to `source/recipes-run.md`.
8. **Is the project's name private?** The bug report leaves out every path and document id; it keeps the workflow's and
   step's names. Whether the project's name and the library's name are in it is the owner's call (default here: out).
9. **Does `rate-limited` alert at all?** The retry layer already waits; a run that still fails is rare. The table alerts
   with "wait a few minutes"; the owner may prefer it silent in Activity with Retry.
