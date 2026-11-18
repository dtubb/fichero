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
> **What it builds on, by name.** The failure kinds table is `ai/run-failure-alerts.md` `run.fail.kinds-table`, built as
> `fichero-server/src/fichero_server/llm/failure.py` (`RunFailure`, `classify`, `row_words`). The pause path is the one
> `execution/cancellation.request_pause` → `_finish_as_paused` path that a person's Pause, the spend cap
> (`llm/spend._ask_run_to_pause`) and a rate limit (`llm/retry._pause_the_run_for`) already take. The surface is the
> Activity pane (`ui/activity-pane.md`: the states table, `activity.pane.failure-with-its-fix-in-the-row`,
> `activity.pane.blocked-under-its-blocker`) and the alert of `run.fail.alert-on-a-failed-run`. The recipe's own rules are
> `source/recipes-run.md` section 13 (a page waits for its inputs; models fetched first; no empty done).

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
  reason on the row, a retry is bounded, a dead lease returns the row to waiting. `activity-and-automatic-work.md`
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

The kinds are those `llm/failure.py` serves today (the sixteen below); `run-failure-alerts.md` keeps the words and the
fixes. This spec adds, per kind, **pause-or-fail**, **retryable by the engine**, and **which runners can raise it**. The
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

## Behaviours

### A. The table and the path (shared by every runner)

- `runner.kinds.one-table` — **[PARTIAL]** (#6354, #6597) every runner's failure is classified by `llm/failure.classify`
  and nothing else: the recipe runner, the workflow runner, the lane (`execution/jobs.failed_reason`), the remote-read loop
  (`remote_read/job.py`), the cloud-batch loop, the training job and the download job. Built: `failure.py` with sixteen
  kinds; `jobs.failed_reason` writes the kind's row words; the workflow run row carries `failure`. Not built: the per-page
  `error_category` still comes from `execution/runner._classify_provider_error`'s own words; the remote-read, cloud-batch,
  training and download paths write their own strings. *Test:* `fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py`
  (extend: each runner's failure path through a stub yields a `RunFailure`, never a bare string).
- `runner.kinds.pause-or-fail-is-the-tables` — **[GAP]** (#6675, #6569, #6354) each kind's pause-or-fail rule (section 1)
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
  cause, forgets the pause (`forget_rate_limit_pause`, `forget_cap_stop`), and takes up the first item not done; done pages
  are never re-read; Retry inside a run redoes only the failed pages and the step list updates. Built for the rate limit and
  the cap; owed for the other causes and the recipe parking. *Test:* `fichero-server/tests/unit/recipes/test_recipe_pause_5933.py`,
  `fichero-server/tests/unit/recipes/test_a_page_waits_for_its_inputs_6673.py` (extend: a continued run makes only the missing calls).
- `runner.pause.survives-relaunch` — **[OK]** (#6584) a run paused for a cause is still paused after a relaunch, with its
  cause; the open continues only work that was running when the app quit. *Test:*
  `fichero-server/tests/unit/jobs/test_durable_5357.py`, the tests cited by `activity.relaunch.only-running-work-resumes`.
- `runner.ask.one-dialogue-per-cause` — **[GAP]** (#6675, #6354) a pausing kind that needs the person (`no-credit`,
  `key-refused`, `cap-refused`, `images-refused`, `export-folder-gone`) raises ONE dialogue per provider per run, from
  the one alert (`run.fail.alert-on-a-failed-run`): the provider, the key or account, the kind, the provider's own words
  (redacted), what is paused (run, step, pages done of total), and the buttons the table names (Open provider page,
  Continue, Stop run). A `rate-limited`, `network`, `memory` or `interrupted` pause raises no dialogue: the row says it and
  Continue enables when the wait is up. *Test:* `fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift` (extend: a `no-credit`
  pause builds one prompt with those buttons; two pages meeting it build one prompt).
- `runner.surface.one-row-one-alert` — **[PARTIAL]** (#6354, #6597, #6599) the failure is shown in the Activity row (the
  kind's ≤ 8 row words and its fix button; `activity.pane.failure-with-its-fix-in-the-row`), in the opened run, and as the
  one alert; a job row never carries exception text (`activity.failure.no-raw-text-ever`). Built: `failed_reason` writes row
  words; the row's fix button has words. Not built: `failure` on every job row (jobs of their own, downloads, remote shards).
  *Test:* `fichero-server/tests/unit/execution/test_failure_in_words_6212.py`, `ActivityErrorRow` tests.
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
  `fichero-server/tests/unit/llm/test_kraken_line_without_outline_is_boxed_6673.py`; to write for #6271.
- `runner.results.counted-done-only-with-a-result` — **[PARTIAL]** (#6271, #6673) a page is done for a step only when the
  step's result is there (lines on the working pass, a reading on each line, a judgement "blank"); a page with no result and
  no judgement is neither done nor silent. Built for the steps §13 covers; owed for `read-a-line`'s done check against pages
  Kraken never saw (#6271).

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
  Built: the classification, the in-flight budget as a slow-down, the per-provider cap, the rate-limit pause. *Test:*
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

### D. Memory, and the Mac staying usable

- `runner.memory.one-heavy-model` — **[OK]** (#6000, #6673; `recipes-run.memory.one-heavy-model`,
  `recipes-run.memory.one-heavy-model-in-sequence` own it) one heavy model resident at a time on a Mac of 16 GB or less;
  the embed lane waits while a run's Kraken stage has pages; Kraken's models are never released for an embed or a thumbnail
  while its stage has pages left. *Tests:* `fichero-server/tests/unit/jobs/test_one_heavy_when_memory_tight.py`,
  `fichero-server/tests/unit/execution/test_one_heavy_model_in_sequence_6673.py`.
- `runner.memory.hold-not-kill` — **[PARTIAL]** (#6075, #4987; `activity.throttle.hold-when-swapping`,
  `recipes-run.memory.hold-when-paging` own it) new heavy work is held while the Mac pages; a hold that outlasts its
  patience becomes a `memory` pause with the row saying so, never a killed engine. Built: the hold; owed: the pause, the
  popover's paging line, the measured ceilings (`recipes-run.memory.peak-ceiling-per-model-kind`).
- `runner.memory.recorded` — **[OK]** (#6673; `recipes-run.memory.recorded-per-step` owns it) each step records the Mac's
  RAM, the engine's peak, swap, pressure and model loads and unloads, in the run's record and in Save Logs for Support.
  *Test:* `fichero-server/tests/unit/recipes/test_memory_recorded_per_step_6673.py`.
- `runner.mac.stays-usable` — **[PARTIAL]** (#5819, #6230, #6263; `activity.throttle.use-means-slower`,
  `activity.throttle.in-use-slows-to-half` own it) automatic work goes on while the person uses the Mac, at half the
  performance cores and background QoS; a run the person started begins at once, throttled, never waits for Run now
  (#6263). Built: the one in-use rule; owed: half the cores (#6230), the started run beginning at once (#6263).

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

## Changes to existing behaviours (made in the integration of 2026-11-18)

1. `ui/activity-and-automatic-work.md` §J's table of thirteen kinds (`out-of-credit`, `cap-reached`, `provider-down`,
   `model-not-found`, `disk-full`, `engine-crashed`, `input-unreadable`, `refused-by-a-rule`, `unknown`, …) is superseded by
   the sixteen kinds of `run-failure-alerts.md` and `llm/failure.py`; §J keeps its two behaviours
   (`activity.failure.credit-exhausted-pauses`, `activity.failure.partial-results-kept`) and now cites this contract for the
   pause rule. `disk-full` is a wanted kind the code lacks (listed under "Issues to file" in the plan).
2. `ai/run-failure-alerts.md` decision 2 ("a failed run is one that ends `failed` … the run stopped at page N of M") is
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
- Behaviours: `runner.kinds.pause-or-fail-is-the-tables`, `runner.pause.one-path`, `runner.kinds.one-table`
- Tests: fichero-server/tests/unit/llm/test_run_failure_kinds_6354.py, fichero-server/tests/unit/llm/test_rate_limit_backs_off_then_pauses_6584.py (plus the new pause-or-fail file described under `runner.kinds.pause-or-fail-is-the-tables`)
- Size: M

#### Step 1.2 — Continue from the first item not done, for every pausing kind; the recipe parks on it (#6569)
- Behaviours: `runner.pause.continue-from-first-not-done`, `runner.pause.survives-relaunch`
- Tests: fichero-server/tests/unit/recipes/test_recipe_pause_5933.py, fichero-server/tests/unit/recipes/test_a_page_waits_for_its_inputs_6673.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — One dialogue per cause; the row and the alert (#6354, #6597)
- Behaviours: `runner.ask.one-dialogue-per-cause`, `runner.surface.one-row-one-alert`, `runner.cli-mcp.same-words`
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

## Open questions for the owner

1. **Does `network` pause the whole run, or only the pages of the provider that is unreachable?** Recommended: the
   run pauses (the next pages would fail the same way); local steps on pages already read go on.
2. **How long does a `memory` hold wait before it becomes a pause that asks?** Recommended: ten minutes of holding with no
   page admitted, then "Paused: not enough memory for <model>" with Continue and "Choose a smaller model".
3. **A `disk-full` kind.** The §J table named it; the code has none. Recommended: add it (pauses, fix "Free disk space",
   the volume named), filed as its own issue (the plan lists it).
