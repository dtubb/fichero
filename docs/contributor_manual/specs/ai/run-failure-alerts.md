# A run that does not finish says why, and what to do (#6354)

> Milestone: run-failure-alerts
> Manual: TBD — a "When a run stops" section: what the alert says for each cause, where the failed run is in Activity, and what Send a Bug Report sends and leaves out.

> **Status: DRAFT 2026-11-05** (Fable writes, the maintainer approves; raised by the maintainer 2026-11-05, #6354).
> Extends `ai/cloud-permission-and-spend.md` §C (the typed cloud refusal, `CloudRefusalAlert`, the once words: ALREADY
> BUILT, reused here, not respecified), `ai/where-models-run.md` (`ai.where.dead-provider-says-why`,
> `ai.where.one-retry-policy`) and `ui/activity-and-automatic-work.md` (the job model, `activity.jobs.failed-at`,
> `activity.window.done-today`, `activity.popover.now-plus-next`, `activity.durable.paused-stays-paused`). Iterate on what
> exists: the classifier in `execution/runner.py` becomes the one mapping; nothing here adds a second error vocabulary.
> Tags: **[OK]** behaves this way today · **[PARTIAL]** part built or not wired · **[GAP]** intended, not built.

## The problem

A run that does not finish (no credit, a refused key, a cap, a model that cannot do the step, the network, a bug) ends as
a red row in Activity whose `reason` is whatever string the exception carried. Nothing is raised at the moment it
happens; a person finds it later, reads the string, and has to work out what to do. A bug in Fichero reads like a
provider failure ("Provider call failed. Inspect detailed error and retry."). The CLI prints the same string; the MCP
returns it. Three clients, three readings of one failure.

## What exists today (verified 2026-11-05 against origin/integration c2923fae39; file and function read, nothing run)

**A classifier, used per page and on the stream, not on the run.** `execution/runner.py::_typed_failure` judges the
exception's TYPE first (`ProviderQuotaError` → `quota`; `CloudSpendRefusedError` → `spend_refused` with the typed
refusal; `LocalOnlyViolationError`/`EgressRefusedError` → `egress_refused` with it; `MemoryShortError` → `memory`;
`LocalModelNotInstalledError` → `model_missing`; runtime missing / `AppleUnavailableError` →
`unavailable_in_this_build`), then `_classify_provider_error` judges the message WORDS (`file_unavailable`, `quota`,
`auth`, `model_not_found`, `network`, `server`, `unknown`). Each answer is `{category, message, action}`. It reaches:
the per-page `file_error` event and the progress timeline (`error_category`, `error_hint`, `error_action`;
`activity_store.py` keeps them on the page's step), the `systemic_error` stream event, and the generic `error` stream
event (`error_category` only). It does NOT reach the run row: `update_workflow_run(..., error=words)` stores words
alone, `GET /api/activity/jobs` serves them as `BackgroundJob.reason`, the status route serves them as `error`. A recipe
run's step failure is `outcome_why(status, error)`: the words, or "the engine stopped while this was running; try it
again" for a run paused by shutdown. `unknown` is a real category today: a bug lands there and is told to "inspect
detailed error and retry".

**The provider's cause is typed, with words.** `workflows/circuit_breaker.py::classify_provider_error` sorts a call's
exception into `slow-down` (429), `transient` (5xx, 408, 409, a dropped connection), `fatal` (401, 402,
`insufficient_quota`, the key-refused words) or `terminal` (anything else); `fatal_cause` says `key` or `quota`.
`llm/retry.py` marks the provider dead for 30 s with that cause, and a later call in the window raises
`ProviderQuotaExhaustedError`, `ProviderKeyRefusedError` or `ProviderRateLimitedError`, whose words name the provider
by its display name and the fix (`ai.where.dead-provider-says-why`, PARTIAL #5944). `dead_marks()` lets the Start plan
skip the step before it runs (`ai.cloud.plan-knows-a-dead-key`, OK).

**The cloud refusal is one typed shape with its fixes, and one alert.** `llm/refusal.py` (`CloudRefusal`: kind, scope,
figures, words, `fixes[]`: `raise-to`, `over-cap-once`, `allow-everywhere`, `allow-project`, `allow-once`,
`open-settings` with a control id) rides on `CloudSpendRefusedError`, `EgressRefusedError`, the execute 400's
`detail.refusal`, a run paused at the cap (`spend.stopped_at_cap`, the `refused` stream event) and a page failure.
The app's `CloudRefusalAlert` (a SwiftUI `.alert` on `ContentView`, from `WorkflowExecutionObserver.cloudRefusal`)
shows the words and a button per fix, and re-sends the run; it is raised only from `failWorkflowStart`, a run refused
BEFORE it started. The app does not yet listen for the `refused` event, so a run paused at a cap mid-run raises nothing
(`ai.cloud.alert-on-hand-run-paths`, PARTIAL: "not built: resuming a run paused at a cap"). The CLI exits 3 with the
words; the MCP returns `detail.refusal` intact (`openapi_runtime._with_ways_through`).

**Paused is not failed.** A run paused by a person, by the cap, or by the engine's stop is WAITING, never failed
(`activity.durable.paused-stays-paused` with the #5919 fix; `activity.recipe-run.pause-reaches-its-step`;
`test_a_paused_page_is_paused_not_failed_5919.py`); a run live at shutdown is paused at its checkpoint and resumed.

**Activity shows the failure, in the engine's words, after the fact.** `BackgroundJob` carries `state`, `reason`,
`failed_at`, `finished_at`; DONE TODAY says "<the engine's reason as sent> · 89 of 203 pages"; the opened run lists the
failed pages with one reason each and "Read them again"; the toolbar popover shows the last three failures' first
sentence (`ActivityPopoverSummary.recentErrors`), only those from the last hour or not yet seen
(`ActivityErrorLedger`, keyed `jobId@failed_at`, the seen set kept across launches). A recipe run that lost pages ends
"Done with failures: …" (#6298). That is the whole of what a person is told: a pill, a popover line, a row.

**No alert exists for a run that fails mid-run.** Searched `fichero/`: the only run alerts are `CloudRefusalAlert`
(start-time cloud refusal) and the `importError` banner ("Workflow failed to start: …", a start-time error of any other
kind). No `UNUserNotificationCenter` use anywhere; nothing is raised when the app is in the background.

**A bug report path exists for logs, not for a run.** Help › Send Logs to the Maintainer…
(`help.send-logs-to-the-maintainer`, PARTIAL; `App/Menus/Help/SaveLogsForSupport.swift`): shows what the zip holds and
asks, zips the logs folder (engine log cut to 20 MB) plus `about.txt` (version, build, tier, macOS, model, memory, free
disk, date), skips databases and credentials by name, composes a mail (never sends), falls back to the Save panel with
no mail account. The maintainer's address is a GAP (none in the repo). Nothing attaches a run, its failure or a
traceback; the engine has no route that builds a report.

**CLI and MCP say the string.** `fichero workflow run --wait` prints the terminal event's `error`; `fichero_workflow_status`
returns the status route's `error`. No kind, no fix, no way through, except for the cloud refusal.

**Not built, in one list:** a failure KIND on the run (row, status route, jobs list, recipe run); one engine table from
kind to words, fix and typed actions that every client reads; an alert for a run that fails mid-run, of any kind;
one alert per failed run attempt rather than per page or per retry; the resume half of the cap alert; a bug report built
from a run with the error, the run and the versions, and nothing private; CLI/MCP words carrying the fix and the route.

## Decisions (overrule any in one line)

1. **One mapping, in the engine, on the run.** `_classify_provider_error` moves to `llm/failure` and answers a
   served model, `RunFailure`; the runner stores it on the run row when the run ends failed (or pauses for a cause), and
   every client reads it. The per-page classification keeps using the same function, so a page's reason and the run's
   reason never disagree.
2. **A failed run is one that ends `failed`, or pauses for a cause the person must act on (a cap, the images rule).**
   A run that ends partial ("Done with failures: 3 of 203 pages") FINISHED: Activity's Partial line and Retry cover it,
   no alert (question 1). A run paused by a person or by the engine's own stop raises nothing. A page's failure is not
   the run's.
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

## The table (`run.fail.kinds-table`)

The engine's one mapping. "Judged by" is the exception's type first, its status code or words only when it has no type
of its own (today's `_typed_failure` rule). `<Provider>` and `<Model>` are display names (`circuit_breaker.provider_display`),
never ids or internals; `N`/`M` are the run's pages done and total.

| kind | judged by | words (what happened) | fix (what to do) | actions |
|---|---|---|---|---|
| `no-credit` | `ProviderQuotaExhaustedError`; `fatal_cause == "quota"`; 402, `insufficient_quota`, a key limit | "<Provider> has no credit left, or this key's limit is reached, so the run stopped at page N of M. The N pages done are kept." | "Add credit at <Provider>, or give Fichero a different key or provider, then run it again." | `open-settings` (`settings.ai.providers`), `choose-model`, `retry` |
| `key-refused` | `ProviderKeyRefusedError`; `fatal_cause == "key"`; 401, `KEY_REFUSED_WORDS`; today's `auth` | "<Provider> refused the key Fichero has for it, so the run stopped at page N of M." | "Check the key in Settings › AI › Providers (paste it again, or make a new one), or switch this step to another provider." | `open-settings` (`settings.ai.providers`), `choose-model`, `retry` |
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

### A. The engine: one failure, on the run

- `run.fail.kinds-table` [PARTIAL] (#6354; built: `_typed_failure` and `_classify_provider_error` with today's categories
  and `{category, message, action}`; not built: the kinds above, the served model, `unexpected` in place of `unknown`,
  the provider and model names in the words) — `llm/failure` holds `RunFailure` (`kind`, `words`, `fix`, `actions[]`
  of `{kind, control?, usd?, retry_after_seconds?}`, `provider`, `model`, `step`, `pages_done`, `pages_total`,
  `exception_type`, `detail` (the error's first line, redacted as in C), `refusal: CloudRefusal | None`) and one function
  `classify(exc, text, *, step, provider, model, done, total) -> RunFailure` that is the table above. `_typed_failure` and
  `_classify_provider_error` call it (the per-page `error_category`/`error_hint`/`error_action` stay as they are, now
  from the same table, so a page's reason and the run's agree). Tests:
  `fichero-server/tests/unit/llm/test_run_failure_kinds_6354` (each row of the table from its exception; a 401
  under `httpx` words is `key-refused`; a bare `RuntimeError("boom")` is `unexpected` with `exception_type` `RuntimeError`;
  no answer is ever `unknown`; the words name the provider's display name, never the breaker's internals).
- `run.fail.run-carries-its-failure` [GAP] (#6354) — when a run ends `failed` the runner stores `failure` (the
  `RunFailure`, JSON) on the run row beside `error` (the words stay `error`, so nothing that reads `reason` changes);
  `GET /api/workflow-execution/threads/{id}/status` serves `failure`; `GET /api/activity/jobs` serves it on the failed
  `BackgroundJob` (`failure: RunFailure | None`); a recipe run whose step's run failed carries that run's `failure`
  with `step` filled, its `reason` stays `outcome_why`'s words. A run paused at a cap or by the images rule carries the
  `cap-refused`/`images-refused` failure with its `refusal`, state `paused`. A run paused by a person or by shutdown
  carries none. An OpenAPI regen. Tests:
  `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354` (a stub provider that raises each kind;
  the row, the status route and the jobs list agree; a paused-by-person run has `failure: null`),
  `fichero-server/tests/unit/recipes/test_recipe_run_carries_step_failure_6354`.
- `run.fail.one-failure-per-attempt` [GAP] (#6354) — the retry layer's own retries (`llm/retry.py`, `page_retry`) and a
  page's failure write no `failure`; only the run's end does, once; a run retried through Retry / Read them again that
  fails again gets a new `failure` and a new `failed_at`, so the attempt is told apart by `id@failed_at`
  (`activity.jobs.failed-at`). Tests: `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354`
  (three calls fail, one `failure`; a retried run has two attempts, each with its own `failed_at`).
- `run.fail.failed-stream-event` [GAP] (#6354) — the execution stream's `workflow_failed` event (and `systemic_error`)
  carries `failure`, so a client on the stream need not poll; the `refused` event stays for the cap pause as built.
  Tests: `fichero-server/tests/unit/workflows/test_failed_event_carries_failure_6354`.
- `run.fail.unexpected-is-logged-whole` [PARTIAL] (#6354; built: `logger.exception` on the runner's catch-all) — an
  `unexpected` failure writes the full traceback to the engine log at ERROR, once, with the run id, so the bug report
  can quote it; the served `detail` is the exception's first line only. Tests:
  `fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354` (`caplog`: one ERROR with the run id).

### B. The bug report

- `run.fail.bug-report-route` [GAP] (#6354) — `POST /api/activity/jobs/{id}/bug-report` builds and answers the report
  for a failed run: `{title, body, attachments: [{name, text}]}` where `title` is "<kind>: <words' first sentence>",
  `body` is plain text and `attachments` are `run.json` (the fields in C) and `log.txt` (the run's Problems log lines,
  `activity.log.problems-first`, redacted). A run that is not failed answers 409 in words. Tests:
  `fichero-server/tests/unit/api/test_bug_report_route_6354`.
- `run.fail.bug-report-contents` [GAP] (#6354) — the report carries: the app version, build and tier, the engine version,
  macOS and the Mac model, the failure (kind, words, `exception_type`, `detail`), the redacted traceback of an
  `unexpected` failure (from the engine log, by run id), the workflow's name and the step's, the provider's and model's
  display names, where it ran (`activity.summary.where-and-model`'s words), pages done and total, the run's start and
  end, its duration, and the run's Problems lines. Tests: `fichero-server/tests/unit/api/test_bug_report_route_6354`
  (every named field present for a stubbed `unexpected` run).
- `run.fail.bug-report-excludes-the-private` [GAP] (#6354) — the report never carries: a file path (every `/…/` run is
  replaced by `<path>`, the home folder by `~`, before anything else), a library or project path, a page's text or a
  model's answer, a prompt, a key, token or bearer header (anything matching a key shape or the words `key`, `token`,
  `secret`, `password`, `authorization` with a value), a person's name from the account chain, or a document id. The
  redaction is one function (`llm/failure.redact`) used by `detail`, the traceback and the log lines, and it is tested
  against the real log fixtures in `tests/fixtures/engine_logs/`. Tests:
  `fichero-server/tests/unit/api/test_bug_report_is_redacted_6354` (a traceback with a home path, an API key in a
  URL, a bearer header and a page's text in an exception message: none of them in the report; the fixtures' lines).
- `run.fail.bug-report-destination` [GAP] (#6354; question 2) — where the report goes once built: ruled by the owner.
  Until then the app offers Save Bug Report… (a file the person attaches by hand) and the route is the one source.
  Tests: named with the ruling.

### C. The app: an alert that says what happened and what to do

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

### D. Sending the bug report

- `run.fail.report-shows-then-sends` [GAP] (#6354) — "Send a Bug Report…" asks the engine for the report, shows its
  title, body and the names of its attachments, says in one line what is left out (paths, keys, your pages' text), and
  only then sends it where question 2 rules (until ruled: Save Bug Report…, a `.zip` of the three parts, through the
  Save panel). Tests: `fichero/Tests/Unit/general/App/RunBugReportTests` (the preview text is the engine's;
  nothing is sent before Continue; the zip holds exactly the three parts).

### E. CLI and MCP

- `run.fail.cli-says-the-fix` [GAP] (#6354) — `fichero workflow run --wait`, `fichero workflow status` and
  `fichero activity jobs` print a failed run's `words`, then `Fix: <fix>`, then each action as the command that does it
  (`fichero workflow retry <id>`, `fichero ai providers set-key <provider>` or the regen's name, `fichero activity
  bug-report <id> --out <file>`); exit 1 for a failure, 3 for a cloud refusal as built; an `unexpected` failure says
  "a bug in Fichero" and the bug-report command first; never a traceback. Tests:
  `fichero-cli/tests/test_cli_run_failure_words_6354`.
- `run.fail.mcp-says-the-fix` [GAP] (#6354) — `fichero_workflow_status` and `fichero_activity_jobs` return `failure`
  intact; `fichero_workflow_run` with `wait` returns it on a failed run as `EngineError` with `detail.failure`, the
  message naming the tool for each action (`fichero_workflow_retry`, `fichero_activity_bug_report` from the regen).
  Tests: `fichero-server/tests/unit/mcp/test_mcp_run_failure_6354`.

## Build order (engine first; each step shippable alone, one batch)

### Stage 1 — The engine: one failure, on the run

#### Step 1.1 — The kinds table and the served model (#6354)
- Behaviours: `run.fail.kinds-table`, `run.fail.unexpected-is-logged-whole`
- Files: a new `llm/failure` (`RunFailure`, `classify`, `redact`), `execution/runner.py` (`_typed_failure` and `_classify_provider_error` call it), `workflows/circuit_breaker.py` (export `provider_display`)
- Tests: fichero-server/tests/unit/llm/test_run_failure_kinds_6354
- Size: M

#### Step 1.2 — The run carries its failure; the stream says it (#6354)
- Behaviours: `run.fail.run-carries-its-failure`, `run.fail.one-failure-per-attempt`, `run.fail.failed-stream-event`
- Files: `execution/runner.py` (the three failure ends and the cap pause), `workflows/activity_store.py` (a `failure` column), `api/routes/workflow_execution/schemas.py` and `core.py` (status), `api/routes/system/activity.py` (`BackgroundJob.failure`), `recipes/runner.py` (the step's failure on the recipe run), the OpenAPI regen
- Tests: fichero-server/tests/unit/workflows/test_run_carries_its_failure_6354, fichero-server/tests/unit/recipes/test_recipe_run_carries_step_failure_6354, fichero-server/tests/unit/workflows/test_failed_event_carries_failure_6354
- Depends on: 1.1
- Size: M

#### Step 1.3 — The bug report, built and redacted (#6354)
- Behaviours: `run.fail.bug-report-route`, `run.fail.bug-report-contents`, `run.fail.bug-report-excludes-the-private`
- Files: a new `api/routes/system/bug_report`, `llm/failure` (`redact`), `core/engine_log.py` (read a run's traceback by id), the regen
- Tests: fichero-server/tests/unit/api/test_bug_report_route_6354, fichero-server/tests/unit/api/test_bug_report_is_redacted_6354
- Depends on: 1.2
- Size: M

#### Step 1.4 — The CLI and MCP say the fix (#6354)
- Behaviours: `run.fail.cli-says-the-fix`, `run.fail.mcp-says-the-fix`
- Files: `fichero-cli/src/fichero_cli/__main__.py` (`workflow_run`, `workflow_status`, the activity commands, a `bug-report` command), `fichero-mcp/src/fichero_mcp/openapi_runtime.py` (`_with_ways_through` grows a `failure` case), the regen outputs
- Tests: fichero-cli/tests/test_cli_run_failure_words_6354, fichero-server/tests/unit/mcp/test_mcp_run_failure_6354
- Depends on: 1.3
- Size: S

### Stage 2 — The app: the alert, once, with its buttons

#### Step 2.1 — The alert and its ledger (#6354)
- Behaviours: `run.fail.alert-on-a-failed-run`, `run.fail.one-alert-per-attempt`, `run.fail.alerts-coalesce-by-cause`
- Files: a new `Views/Shell/RunFailureAlert` and `Models/RunFailurePrompt`, `Models/ActivityErrorLedger.swift` (the alert's seen set beside the popover's), `ActivityStore` (a failed job's `failure`), `ContentView.swift` (the modifier), `CloudRefusalPrompt.swift` (a resume resend)
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests, fichero/Tests/Unit/general/Models/RunFailureLedgerTests
- Depends on: 1.2
- Size: M

#### Step 2.2 — The actions act; Activity says the kind (#6354)
- Behaviours: `run.fail.actions-act`, `run.fail.activity-says-the-kind`
- Files: `RunFailureAlert.swift`, `AISettingsView+Tabs.swift` (`settings.ai.providers` deep link), `ActivityWindowGroups`/`ActivityMonitorRow` (the words and fix), `ActivityPopoverSummary.swift`, the opened run's details
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests, fichero/Tests/Unit/general/Models/ActivityRowFailureWordsTests
- Depends on: 2.1
- Size: M

#### Step 2.3 — Send a Bug Report, and the background app (#6354)
- Behaviours: `run.fail.report-shows-then-sends`, `run.fail.bug-report-destination`, `run.fail.alert-reaches-a-background-app`
- Files: a new `App/Menus/Help/RunBugReport` (beside `SaveLogsForSupport.swift`, sharing its confirm-then-act shape), a new `Models/RunFailureNotification`
- Tests: fichero/Tests/Unit/general/App/RunBugReportTests, fichero/Tests/Unit/general/Models/RunFailureNotificationTests
- Depends on: 1.3, 2.2
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | one alert per attempt; buttons from kinds; coalescing | `fichero/Tests/Unit/general/Models/RunFailureLedgerTests`, `…/Views/RunFailureAlertTests.swift` |
| Availability (Swift) | y | the alert modifier mounted on `ContentView` | `RunFailureAlertTests.swift` |
| Backend (pytest) | y | the table, the run row, the routes, the redaction | `fichero-server/tests/unit/llm/test_run_failure_kinds_6354` and the others named above |
| MCP | y | `failure` intact, the tools named | `fichero-server/tests/unit/mcp/test_mcp_run_failure_6354` |
| CLI | y | words, fix, commands, exit codes | `fichero-cli/tests/test_cli_run_failure_words_6354` |
| Click-around (XCUITest, Mac) | later | a stub engine fails a run; the alert's buttons | `fichero/Tests/UI/RunFailureAlertUITests` (not in this milestone) |
| iPhone / iPad | n | | |
| Load | n | | |

## Accessibility identifiers

`runFailure.alert` · `runFailure.alert.action.<kind>` (`retry`, `resume`, `openSettings`, `chooseModel`, `reportBug`,
`reconnect`) · `runFailure.alert.showInActivity` · `runFailure.alert.notNow` · `runFailure.report.preview` ·
`runFailure.report.continue` · `activity.row.<jobId>.failure` (the words and fix on the row) · `settings.ai.providers`.

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `runFailure.alert.action.retry` | Run It Again | Starts the same run again from where it stopped | `runFailure.action.retry` | test |
| `runFailure.alert.action.reportBug` | Send a Bug Report… | Shows what the report holds before anything is sent | `runFailure.action.reportBug` | test |
| `runFailure.alert.action.openSettings` | Open Settings… | Opens the setting the failure names | `runFailure.action.openSettings` | test |
| `runFailure.alert.action.chooseModel` | Choose a Model… | Opens this step's model choice | `runFailure.action.chooseModel` | test |
| `runFailure.alert.showInActivity` | Show in Activity | Opens the run in the Activity window | `runFailure.showInActivity` | test |

## Open questions for the owner (not guessed)

1. **Is a partial run a failed run?** Decision 2 says no: "Done with failures: 3 of 203 pages" finished, and Activity's
   Partial line with Retry is the surface; only a run that ENDS failed, or pauses at a cap or the images rule, alerts. If
   the owner wants an alert when more than some share of pages fail (say a quarter), that is one threshold in the
   runner's `SystemicErrorDetected`, which already ends such a run failed.
2. **Where does the bug report go?** (a) a GitHub issue on the public repo, opened from the app by the person's own
   account (the app has no token; it would open a prefilled new-issue page in the browser, body length capped); (b) a
   mail to the maintainer through the Send Logs path (needs the address that `help.send-logs-to-the-maintainer` still
   lacks); (c) a local file the person attaches by hand (what the spec does until ruled); (d) a maintainer-run endpoint.
   The route builds the same report whichever is chosen.
3. **A notification when the app is in the background?** `run.fail.alert-reaches-a-background-app` asks for
   notification permission the first time a run fails. The alternative is no system notification: the alert waits for the
   app to come to the front, and the Activity pill shows red meanwhile.
4. **Does a recipe stop at a step whose failure will fail every later cloud step** (`no-credit`, `key-refused`,
   `cap-refused`, `network`), or carry on to the next step as it does today and alert once at the end? The spec alerts at
   the step's failure and leaves the recipe's own behaviour to `source/recipes-run.md`.
5. **Is the project's name private?** The bug report leaves out every path and document id; it keeps the workflow's and
   step's names. Whether the project's name and the library's name are in it is the owner's call (default here: out).
6. **Does `rate-limited` alert at all?** The retry layer already waits; a run that still fails is rare. The table alerts
   with "wait a few minutes"; the owner may prefer it silent in Activity with Retry.
