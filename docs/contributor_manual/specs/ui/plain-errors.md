# Plain Errors — every error a person sees is a sentence — Design Spec (#6299)

> Milestone: TBD (proposed: `plain-errors`; until it exists the work lives on #6299 and the issues filed per step)
> Manual: TBD — the user manual needs no section of its own; every section that shows a failure should quote the
> sentence this spec makes it say (the facts are the three cases in section D).
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-30 — awaiting the maintainer's review.** Every
> [GAP] names its test as "(not yet written: <path>)", so `check_specs_have_tests` can guard it once approved.
> Tags: **[OK]** built and seen working · **[PARTIAL]** built, unproven or incomplete · **[GAP]** not built.
> Extends: `ui/activity-and-automatic-work.md` (Activity's error rows and footer, "the reason in words"),
> `transport/library-sharing.md` (pairing and Accounts refusals in words), `harness/engine-startup-lifecycle.md`
> (the engine not there). Counts below are read from integration at 98990d947, not run.

## Intent (the design)

A person never reads Swift or Python. Today the app shows them anyway: Settings › Sharing › Create Account shows
`undocumented(statusCode: 404, OpenAPIRuntime.UndocumentedPayload(headerFields: …, body: …))` for an engine that
answered `{"detail": "multi-user auth is disabled"}`; the pairing sheet shows "Client encountered an error invoking
the operation pair_device_api_pair_post … Transport threw an error … NSURLErrorDomain -1001"; the inspector shows
"Couldn't load artifacts: Unexpected response from artifact service (status: 404)". What the person should observe
instead, on every sheet, banner, alert and Activity row: **one sentence that says what failed, why (in the engine's own
words when the engine gave some), and what to do next.** Never a type name, an enum case, an operation id, a status
code, an error domain or number, or a URL.

Two halves, one rule:

- **The app** has ONE mapper, `PlainError` (new, fichero/fichero/Services/PlainError.swift), and every place that
  turns an error into visible text calls it. It prefers the engine's `detail`; otherwise it words the failure from what
  it knows (a timeout, a refused connection, a status class) and the action that failed.
- **The engine** makes every route's `detail` a sentence a person can read, because the mapper shows it as it is.
  Clients that need to branch read a machine `code` beside the sentence, never the sentence.
- **A guardrail** (scripts/check_plain_error_text.py, new) fails when raw error text reaches a visible string
  anywhere but the mapper, so the 500-odd places fixed here do not grow back.

### What exists today (read 2026-10-30)

| Piece | Where | What it does / misses |
|---|---|---|
| `EngineErrorDetail` | `fichero/fichero-api-client/Sources/FicheroAPIClient/EngineErrorDetail.swift` | Reads `{"detail": …}` from a body or an `UndocumentedPayload`; the 422 array as "field: msg". Used in 23 app files. Good: the mapper builds on it. |
| `EngineErrorBodyMiddleware` | same file | Buffers a non-2xx body so `ClientError.responseBody` is still readable. Good. |
| `AccessError` | `fichero/fichero/Services/AccessError.swift` | Classifies 401/403, TLS, unreachable, in words. Its `.transport(String)` falls back to `error.localizedDescription`, which is where the -1001 dump comes from. |
| Per-store helpers | `engineWords` ×5 (BakeoffStore, KeptExportStore, RecipeSetupStore, SetupStageTryStore, SyncFolderStore), `GuestLibraryChoice.problemWords`, `ActivityStore.runLoadFailureMessage`, `AccountsAddSheetModel.failureWords`, `DocumentInspectorInfoTab.loadErrorMessage` | Each re-solves a slice of the problem. They fold into the mapper. |
| Discarded bodies | 238 `.undocumented(code, _)` sites in 69 files (325 `.undocumented(` sites in all; 396 lines mention it) | The engine's sentence is thrown away at the service; the view can only say "Unexpected response". |
| Enum dumps | `UsersStore.error(from:)` builds `UsersStoreError(message: "\(response)")` | The Create Account text in the issue. |
| Status codes in words | 77 literals like `"Could not read … (HTTP \(code))"`; `ArtifactServiceError.unexpectedResponse` ("status: \(code)"); `APIError.errorDescription` ("HTTP 404: …", "Bad request: …", "Is `fichero serve` running?") | Developer text shown to a person. |
| Raw error into visible text | 490 `error.localizedDescription` outside a log call (252 files), 31 `String(describing: error)`, 15 `"\(error)"` | The ~529 places in the issue. Biggest areas: Models (160), Services (62), Views/Library (59), Views/Inspector (58), Views/Settings (46), Views/Sidebar (44). |
| Engine: exception text as detail | ~290 `detail=str(e)` / `detail=f"…{e}"` in 58 files | A Python message ("'NoneType' object has no attribute…") reaches the mapper as "the engine's words". |
| Engine: fragments | 163 lowercase, unpunctuated details in 30 files (`accounts.py` 56, `pairing.py` 43) | "multi-user auth is disabled", "session required", "invite not found". |
| Engine: id-only not-found | 286 `detail=f"<Kind> not found: {id}"` in 53 files | Shows a UUID to a person. |
| Engine: unhandled | no `exception_handler(Exception)`; Starlette answers a crash with plain-text "Internal Server Error"; the unmatched-path 404 falls back to "Not Found" (`fichero-server/src/fichero_server/api/main.py`, `install_tier_aware_not_found`) | No sentence, and a 500 body that is not even JSON. |
| Text matchers | app: `AccessError` (`"device token expired"`), `PairingPerson.isRequiredRefusal` (`"person required"` prefix), `SyncedHostAsk` (`"invalid or expired"`, `"https"`), `RecipeSetupStore+Material` (`"has no material yet"`); CLI: `fichero-cli/src/fichero_cli/__main__.py` (`"multi-user auth is disabled"`) | Rewording a detail silently breaks these. They move to a `code` first. |

## Prior art / best practices

- **Apple HIG, Alerts** and Foundation's own `LocalizedError` (`errorDescription`, `failureReason`,
  `recoverySuggestion`): say what happened and what to do, in the person's terms, no codes. We adopt the shape (what
  failed · why · what to do) as one sentence; the mapper returns a `String`, not a new error type, because every
  surface already shows a `String`.
- **RFC 9457 Problem Details** (`title`, `detail`, `type`): the engine keeps FastAPI's `{"detail": …}` (already the
  declared `ErrorDetail` in `fichero-server/src/fichero_server/api/errors.py`) and adds an optional `code`, the
  machine half of RFC 9457's `type`, without moving to `application/problem+json` (every client already reads
  `detail`; a media-type change buys nothing here).
- **GOV.UK Design System, error messages**: plain, specific, says how to fix it, no "error" jargon, no blame. Used as
  the wording test for the engine's sentences.
- **Nielsen's heuristic 9** (help users recognise, diagnose and recover from errors).

## The mapper's rules (app)

`PlainError.sentence(for error: Error, failed: String) async -> String?` where `failed` is the action in words
("Couldn't create the account"). Async because a `ClientError` body is read once from `responseBody`. Rules, first
match wins:

1. **Cancelled** (`CancellationError`, `URLError.cancelled`, `error.isCancellationError`) → `nil`: show nothing.
2. **An app error that is already a sentence** (types that conform to a marker protocol `PlainSentence`, starting with
   `AccessError` and the existing worded refusals such as `RemoteClientPairingError`) → `"<failed>. <sentence>"`.
3. **The engine's words**: an `EngineRefusal(status:detail:code:)` (new, thrown by services in place of every
   `.undocumented(code, _)`), or a `ClientError` whose buffered body has a `detail` → `"<failed>. <detail>"`. A string
   detail is shown as written, only capitalised and closed with a full stop; an object detail shows its `message`
   (or `detail`) string; a 422 field array shows the first `msg` only, never the `loc` path ("One of the values was
   not accepted: <msg>.").
4. **The connection** (a `URLError` or `NIOCore.IOError`, also when wrapped as `ClientError.underlyingError`), naming
   the **host name** from the failing URL (host only: no scheme, port or path):
   - timed out → "<failed>: <host> did not answer." plus, for a `.ts.net` host, "Check that Fichero is open on that
     Mac and that Tailscale is connected on both Macs."; for a `.local` host, "Check that Fichero is open on that Mac
     and that both Macs are on the same network."; for this Mac's own engine, "Fichero's engine is restarting; try
     again in a moment."
   - refused / cannot connect → "<host> is not accepting connections: Fichero is not open there, or Sharing is off."
   - host not found / DNS → "<host> could not be found on this network."
   - offline → "This Mac is offline."
   - TLS / pin → `AccessError.tlsPinFailure`'s sentence.
5. **A status with no detail**: 401 sign in again · 403 "you don't have access to this" · 404 "it is no longer
   there, or the engine is older than this app" · 409 "it changed in the meantime; try again" · 413 "it is too large"
   · 429 "too many tries; wait a minute" · 5xx "the engine ran into a problem; try again, and if it keeps happening
   the details are in the engine log".
6. **Anything else** → `"<failed>. Try again."`

Every call logs the raw error once (status, operation id, underlying error, through the app's logger with tokens
redacted), so the words lose nothing a developer needs. The sentences go through the String Catalog.

## Behaviors

### A. The app: one mapper

- `errors.app.one-mapper` — **[GAP]** (#6299) one function, `PlainError.sentence(for:failed:)`, turns any error into
  the text a person sees, by the rules above in that order; it is the only code that reads an error's description for
  display. (not yet written: fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.engine-detail-first` — **[GAP]** (#6299) when the engine sent a `detail`, the person reads it, unchanged
  but for a capital and a full stop, after what failed: a string detail as written; an object detail by its message; a
  422 by its first `msg`, never the field path. (not yet written: fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.connection-names-host-and-fix` — **[GAP]** (#6299) a timeout, refusal, unknown host, offline Mac or
  certificate mismatch says which host (its name only) and what to do, with the Tailscale advice for a `.ts.net` host
  and the same-network advice for a `.local` one; this Mac's own engine not answering says it is restarting.
  Unwraps `ClientError.underlyingError`. (not yet written: fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.status-without-detail` — **[GAP]** (#6299) a status with no usable body is worded by its class (401,
  403, 404, 409, 413, 429, 5xx) with a next step, never the number. (not yet written:
  fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.cancel-is-silent` — **[GAP]** (#6299) a cancelled request shows nothing (the mapper returns nil), so a
  person who closes a sheet never reads "cancelled". (not yet written: fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.never-code-words` — **[GAP]** (#6299) over a corpus of real errors (every case above, an `.undocumented`
  dump, a `ClientError` around each `URLError` code, an `NSError` from each domain the app meets), no sentence matches
  `undocumented`, `statusCode`, `OpenAPIRuntime`, `ClientError`, `Error Domain=`, `NSURLErrorDomain`, an `-1001`-style
  code, `HTTP \d{3}`, `status: \d`, `_api_` operation ids, `https?://`, or `Type.member(`. (not yet written:
  fichero/Tests/Unit/general/Services/PlainErrorScrubTests.swift)
- `errors.app.raw-error-goes-to-log` — **[GAP]** (#6299) each mapped error is logged once, whole (status, operation,
  underlying error), redacted, so the plain sentence never costs a developer the cause. (not yet written:
  fichero/Tests/Unit/general/Services/PlainErrorScrubTests.swift)
- `errors.app.services-keep-the-body` — **[GAP]** (#6299) no service throws away an error body: each
  `.undocumented(code, _)` (238 sites, 69 files) throws `EngineRefusal(status:detail:code:)` read from the payload;
  `UsersStore.error(from:)` stops dumping the response enum. (not yet written:
  fichero/Tests/Unit/general/Services/EngineRefusalTests.swift)
- `errors.app.typed-errors-carry-not-word` — **[GAP]** (#6299) the app's error enums (`APIError`,
  `ArtifactServiceError`, `UsersStoreError` and the rest of the 55 `LocalizedError` types) carry the status, detail and
  code; their own `errorDescription` no longer says "HTTP 404", "status: 404", "Server error:" or "`fichero serve`",
  because only the mapper words them. (not yet written: fichero/Tests/Unit/general/Services/EngineRefusalTests.swift)
- `errors.app.local-helpers-fold-in` — **[GAP]** (#6299) the per-store helpers (the five `engineWords`,
  `problemWords`, `runLoadFailureMessage`, `failureWords`, `loadErrorMessage`) are deleted; their callers call the
  mapper, and each helper's existing tests move to `PlainErrorTests` with their wording kept. (not yet written:
  fichero/Tests/Unit/general/Services/PlainErrorTests.swift)
- `errors.app.every-surface-uses-it` — **[GAP]** (#6299) every sheet, banner, alert, inline error line, Activity footer
  and Activity row that shows a failure gets its text from the mapper; the guardrail's baseline reaches zero. Worked by
  feature area (Settings › Sharing first, then Inspector, Library, Sidebar, Workflow, Shell, the rest), one issue per
  area under the ratchet. (not yet written: fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py, at a
  zero baseline)

### B. The engine: every detail is a sentence for a person

The rule for a `detail`: a whole sentence (capital, full stop) that says what is wrong in the person's terms and, when
there is something to do, what to do. No exception text, Python type, traceback, raw id, URL or internal name
(no "multi-user auth", "bootstrap", "session"). A file name or a host name is fine. A `code` (snake_case) may sit
beside it for clients.

- `errors.engine.detail-is-a-sentence` — **[GAP]** (#6299) a pytest walks every route module's `HTTPException(…,
  detail=…)` and fails on a detail that is not a sentence by the rule (lowercase start, no closing stop, an exception
  interpolated, an id alone), against a shrink-only baseline of today's sites, so no new one lands. (not yet written:
  fichero-server/tests/unit/api/test_error_details_are_sentences_6299.py)
- `errors.engine.code-beside-words` — **[GAP]** (#6299) every refusal a client branches on carries a `code` beside its
  sentence, and the clients switch to it BEFORE any wording changes: `device_token_expired` (AccessError),
  `person_required` (`PairingPerson.isRequiredRefusal`), `pair_code_invalid_or_expired` and `pair_link_not_https`
  (`SyncedHostAsk`), `no_material_yet` (`RecipeSetupStore+Material`), `multiuser_off` (the CLI's check in
  `fichero-cli/src/fichero_cli/__main__.py`). (not yet written:
  fichero-server/tests/unit/api/test_refusals_carry_a_code_6299.py; fichero-cli/tests/test_multiuser_off_reads_the_code_6299.py)
- `errors.engine.fragments-become-sentences` — **[GAP]** (#6299) the 163 fragment details become sentences, first in
  `api/routes/auth/accounts.py` (56) and `api/routes/auth/pairing.py` (43), then `api/routes/document/artifacts.py`
  (8), `api/routes/system/recipes.py` (6), `api/routes/document/segments.py` (6), `api/routes/document/folders.py`,
  `api/routes/document/documents.py` (4 each), `api/routes/system/agent_memory.py`, `api/routes/system/activity.py`,
  `api/routes/kg/entity_curation.py`, `api/routes/ai/model_comparison.py`, `api/routes/ai/hpc.py` (3 each), and the
  ones and twos in `api/routes/interpretation/canvas.py`, `api/routes/document/sources.py`,
  `api/routes/document/editorial.py`, `api/routes/system/conversion.py`, `api/routes/system/changes.py`,
  `api/routes/search/core.py`, `api/routes/library/registry.py`, `api/routes/interpretation/hermeneutics.py`,
  `api/routes/ingest/image_editing.py`, `api/routes/document/source_settings.py`, `api/routes/document/signs.py`,
  `api/routes/document/rights.py`, `api/routes/document/letterforms.py`, `api/routes/document/dataset.py`,
  `api/routes/document/content_representations.py`, `api/routes/claim/claims.py`, `api/routes/auth/authz.py`.
  (not yet written: fichero-server/tests/unit/api/test_accounts_pairing_refusals_are_sentences_6299.py)
- `errors.engine.no-exception-text` — **[GAP]** (#6299) no route puts an exception's text in a `detail`; it logs the
  exception and says what failed. Today ~290 sites in 58 files; the largest: `api/routes/system/recipes.py` (29),
  `api/routes/ingest/export.py` (20), `api/routes/document/transfer.py` (20), `api/routes/training.py` (17),
  `api/routes/workflow/workflows.py` (13), `api/routes/document/documents.py` (12), `api/routes/find_documents.py`
  (11), `api/routes/ai/hpc.py` (10), `api/routes/reading_at_scale.py`, `api/routes/mcp/servers.py` (9 each),
  `api/routes/ai/local_inference.py` (8), `api/routes/workflow/schedules.py`, `api/routes/search/core.py`,
  `api/routes/auth/authz.py` (7 each), `api/routes/workflow/triggers.py`, `api/routes/library/registry.py`,
  `api/routes/document/segments.py` (6 each), `api/routes/document/page_export.py`, `api/routes/check.py`,
  `api/routes/auth/pairing.py` (5 each), and 1–4 each in `api/routes/system/storage.py`,
  `api/routes/system/activity.py`, `api/routes/library/entity_types.py`, `api/routes/kg/entity_curation.py`,
  `api/routes/document/format_import.py`, `api/main.py`, `api/routes/system/actions_registry.py`,
  `api/routes/sync_folders.py`, `api/routes/ingest/core.py`, `api/routes/document/compare_readings.py`,
  `api/routes/document/artifacts.py`, `api/routes/workflow/tasks.py`, `api/routes/workflow/batch.py`,
  `api/routes/system/actions.py`, `api/routes/mcp/tools.py`, `api/routes/library/core.py`, `api/routes/kg/render.py`,
  `api/routes/ingest/iiif.py`, `api/routes/evaluation.py`, `api/routes/document/reading_orders.py`,
  `api/routes/auth/sandbox_access.py`, `api/routes/ai/local_models.py`, `api/routes/workflow_execution/comparison.py`,
  `api/routes/system/settings.py`, `api/routes/system/chat.py`, `api/routes/system/bookmarks.py`,
  `api/routes/system/agent_memory.py`, `api/routes/kg/sparql.py`, `api/routes/kg/predictions.py`,
  `api/routes/kg/claim_search.py`, `api/routes/interpretation/canvas.py`, `api/routes/document/typed_links.py`,
  `api/routes/document/source_settings.py`, `api/routes/document/dataset.py`,
  `api/routes/document/classifications.py`, `api/routes/ai/providers.py`, `api/routes/ai/provider_keys.py`, and
  `workflows/circuit_breaker.py`. (not yet written: fichero-server/tests/unit/api/test_error_details_are_sentences_6299.py,
  the no-exception rule)
- `errors.engine.not-found-by-kind` — **[GAP]** (#6299) a missing thing is named by its kind and what to do ("That
  document is no longer in this project."), never by its id; today 286 `"<Kind> not found: {id}"` sites in 53 files
  (Segment and Document 27 each, Entity 24, Claim 15, Workflow 13, Artifact 8, Task 7, …). The id goes to the log.
  (not yet written: fichero-server/tests/unit/api/test_not_found_names_the_kind_6299.py)
- `errors.engine.unhandled-is-a-sentence` — **[GAP]** (#6299) an exception no route caught answers 500 with JSON
  `{"detail": "Something went wrong in the engine. Try again; the details are in the engine log.", "code": "internal"}`
  and logs the traceback (today: plain-text "Internal Server Error"); an unmatched path's 404 and a wrong method's 405
  say "This engine does not offer that. It may be older than the app." instead of "Not Found" (the tier-gated 404
  keeps its own body). (not yet written: fichero-server/tests/unit/api/test_unhandled_error_is_a_sentence_6299.py)
- `errors.engine.job-reason-plain` — **[GAP]** (#6299; Activity's "the reason in words",
  `ui/activity-and-automatic-work.md`) a job's or a page's `error` field, which Activity rows show, is a sentence by
  the same rule, not `str(exc)`: today `error=str(e)` in `execution/runner.py`, `workflows/executor.py`,
  `workflows/task_workers.py`, `workflows/model_comparison.py`, `workflows/run_scope.py`, `db/__init__.py`,
  `api/routes/mcp/integrations.py`, `api/main.py` (22 sites). (not yet written:
  fichero-server/tests/unit/jobs/test_job_error_is_a_sentence_6299.py)

### C. The guardrail

- `errors.guard.raw-error-text` — **[GAP]** (#6299) scripts/check_plain_error_text.py scans `fichero/fichero/**/*.swift`
  and fails on, outside `PlainError.swift`: (R1) `String(describing:` of an error or response; (R2) `"\(error)"`,
  `"\(err)"`, `"\(response)"` interpolation; (R3) `.localizedDescription` of an error (every one: the mapper already
  handles the types whose descriptions are plain); (R4) a status code in a string literal (`HTTP \(`, `status: \(`,
  `(\(code))`, `\(statusCode)`); (R5) the literal "Unexpected response"; (R6) `.undocumented(<name>, _)`, a discarded
  body. Exempt: a log call's whole argument list, across lines by paren balance (`Logger`/`log.*`/`NSLog`/`print`/
  `os_log`), `#Preview` blocks, and the test targets. It prints file:line, the rule and the fix ("call
  `PlainError.sentence(for:failed:)`"); `--self-test` synthesises one hit per rule and one exempt log line.
  (not yet written: fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py)
- `errors.guard.baseline-shrinks` — **[GAP]** (#6299) today's hits are a per-file count baseline
  (scripts/plain_error_text_baseline.json) like `check_spec_behaviors_are_tagged.py`'s: a new hit fails, a file whose
  count dropped must be lowered (a stale entry fails), `--update-baseline` only ever lowers. Runs in `verify_all.sh
  --fast` with the other `check_*.py`. (not yet written: fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py)

### D. The cases from the issue (test cases)

- `errors.case.pairing-timeout` — **[GAP]** (#6299; `transport/library-sharing.md`, pairing) Connect to Another Mac
  whose `POST /api/pair` times out (a `ClientError` for `pair_device_api_pair_post` around `URLError(.timedOut)`)
  reads, for `https://macbook-air.ts.net`, "Couldn't pair with macbook-air.ts.net: it did not answer. Check that
  Fichero is open on that Mac and that Tailscale is connected on both Macs." and, for `macbook-air.local:8765`, the
  same with "that both Macs are on the same network." — never the operation id, "Transport threw", the domain or
  -1001. The section's catch (`MacRemoteClientPairingSection`) calls the mapper. (not yet written:
  fichero/Tests/Unit/general/Services/PlainErrorCasesTests.swift)
- `errors.case.create-account-multiuser-off` — **[GAP]** (#6299; `transport/library-sharing.md`
  `sharing.settings.three-panes`, Accounts) Create Account with Multi-user off: the engine answers 404
  `{"detail": "Multi-user is off on this Mac. Turn it on in Settings › Sharing › Advanced, then add the account.",
  "code": "multiuser_off"}` (today "multi-user auth is disabled", `api/routes/auth/accounts.py`
  `_multiuser_disabled`, and the same guard in `api/routes/auth/pairing.py`), and the sheet reads "Couldn't create the
  account. Multi-user is off on this Mac. Turn it on in Settings › Sharing › Advanced, then add the account." App
  test: the mapper on today's body gives "Couldn't create the account. Multi-user auth is disabled." (no
  `undocumented`, no 404), and on the new body the sentence above; `UsersStore` throws `EngineRefusal`, not the
  response dump. Engine test: the new detail and code. When `transport/multiuser-always-on.md` removes the switch,
  this refusal goes with it. (not yet written: fichero/Tests/Unit/general/Services/PlainErrorCasesTests.swift;
  fichero-server/tests/unit/api/test_accounts_pairing_refusals_are_sentences_6299.py)
- `errors.case.artifacts-404` — **[GAP]** (#6299) the inspector's artifact list for a document the engine no longer
  has (`GET /api/artifacts/document/{doc_id}` → 404) reads "Couldn't load the artifacts. That document is no longer in
  this project." — not "Unexpected response from artifact service (status: 404)". `ArtifactService` keeps the body
  (`EngineRefusal`), `ArtifactStore` calls the mapper, and the route's detail is by kind
  (`api/routes/document/artifacts.py`, today `"Document not found: {doc_id}"`). An unmatched-path 404 (an engine
  without the route) reads "Couldn't load the artifacts. This engine does not offer that. It may be older than the
  app." (not yet written: fichero/Tests/Unit/general/Services/PlainErrorCasesTests.swift;
  fichero-server/tests/unit/api/test_not_found_names_the_kind_6299.py)

## Build order

### Stage 1 — Engine: the words the app will show

#### Step 1.1 — The sentence rule and the catch-all
- Behaviours: `errors.engine.detail-is-a-sentence`, `errors.engine.unhandled-is-a-sentence`
- Tests: fichero-server/tests/unit/api/test_error_details_are_sentences_6299.py, fichero-server/tests/unit/api/test_unhandled_error_is_a_sentence_6299.py
- Size: S

#### Step 1.2 — Codes beside words, then accounts and pairing in sentences
- Behaviours: `errors.engine.code-beside-words`, `errors.engine.fragments-become-sentences`
- Tests: fichero-server/tests/unit/api/test_refusals_carry_a_code_6299.py, fichero-server/tests/unit/api/test_accounts_pairing_refusals_are_sentences_6299.py, fichero-cli/tests/test_multiuser_off_reads_the_code_6299.py
- Depends on: 1.1
- Size: M (the codes and the app/CLI matcher switch land in the same commit as the rewording, or before it)

#### Step 1.3 — No exception text in a detail
- Behaviours: `errors.engine.no-exception-text`
- Tests: fichero-server/tests/unit/api/test_error_details_are_sentences_6299.py
- Depends on: 1.1
- Size: M (this step fixes the five largest files; the rest burn down under the ratchet, one issue per route area)

#### Step 1.4 — Not-found by kind; job reasons in words
- Behaviours: `errors.engine.not-found-by-kind`, `errors.engine.job-reason-plain`
- Tests: fichero-server/tests/unit/api/test_not_found_names_the_kind_6299.py, fichero-server/tests/unit/jobs/test_job_error_is_a_sentence_6299.py
- Depends on: 1.1
- Size: M

### Stage 2 — App: the mapper and its guard

#### Step 2.1 — PlainError
- Behaviours: `errors.app.one-mapper`, `errors.app.engine-detail-first`, `errors.app.connection-names-host-and-fix`, `errors.app.status-without-detail`, `errors.app.cancel-is-silent`
- Tests: fichero/Tests/Unit/general/Services/PlainErrorTests.swift
- Size: M

#### Step 2.2 — Never code words; the raw error to the log
- Behaviours: `errors.app.never-code-words`, `errors.app.raw-error-goes-to-log`
- Tests: fichero/Tests/Unit/general/Services/PlainErrorScrubTests.swift
- Depends on: 2.1
- Size: S

#### Step 2.3 — The guardrail, baselined
- Behaviours: `errors.guard.raw-error-text`, `errors.guard.baseline-shrinks`
- Tests: fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py
- Depends on: 2.1
- Size: S

### Stage 3 — The three cases, end to end

#### Step 3.1 — Pairing timeout, Create Account, artifacts 404
- Behaviours: `errors.case.pairing-timeout`, `errors.case.create-account-multiuser-off`, `errors.case.artifacts-404`
- Tests: fichero/Tests/Unit/general/Services/PlainErrorCasesTests.swift, fichero-server/tests/unit/api/test_accounts_pairing_refusals_are_sentences_6299.py, fichero-server/tests/unit/api/test_not_found_names_the_kind_6299.py
- Depends on: 1.2, 1.4, 2.2
- Size: S

### Stage 4 — Every surface

#### Step 4.1 — Services keep the body; error types carry, not word
- Behaviours: `errors.app.services-keep-the-body`, `errors.app.typed-errors-carry-not-word`
- Tests: fichero/Tests/Unit/general/Services/EngineRefusalTests.swift, fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py
- Depends on: 3.1
- Size: M (mechanical; one commit per feature area, the guardrail's R6 count falling each time)

#### Step 4.2 — Helpers fold in; every surface through the mapper
- Behaviours: `errors.app.local-helpers-fold-in`, `errors.app.every-surface-uses-it`
- Tests: fichero/Tests/Unit/general/Services/PlainErrorTests.swift, fichero-server/tests/unit/scripts/test_check_plain_error_text_6299.py
- Depends on: 4.1
- Size: M (one issue per feature area, Settings › Sharing first; done when the baseline is empty)

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the mapper's rules, the scrub, the three cases | fichero/Tests/Unit/general/Services/PlainErrorTests.swift, PlainErrorScrubTests.swift, PlainErrorCasesTests.swift, EngineRefusalTests.swift (not yet written) |
| Availability (Swift) | y | no raw error text reaches a view (static) | scripts/check_plain_error_text.py + its pytest (not yet written) |
| Backend (pytest) | y | details are sentences, codes, catch-all, not-found by kind, job reasons | fichero-server/tests/unit/api/test_*_6299.py, fichero-server/tests/unit/jobs/test_job_error_is_a_sentence_6299.py (not yet written) |
| MCP | n | MCP tools pass the engine's `detail` through; they gain the sentences for free | — |
| CLI | y | the CLI branches on `code`, not the sentence | fichero-cli/tests/test_multiuser_off_reads_the_code_6299.py (not yet written) |
| Click-around (XCUITest, Mac) | n | the three cases are pure; a live run is the owner's check on the Air and the Pro | — |
| iPhone (iOS) | n | same mapper; no separate leg | — |
| iPad | n | same | — |
| Load (#4634) | n | — | — |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y (facts only) | the maintainer's; the sentences in section D are the facts |
| Contributor | developer docs | y | this spec; a short "Showing an error" note in the contributor guide pointing at `PlainError` and the guardrail |
| AI / agent | MCP tool description | n | — |
| Scripter | CLI `--help` | n | — |
| Reference | capability/endpoint reference | y | the `code` values beside `ErrorDetail`, generated |

## Accessibility identifiers

None new. The sentence lands in each surface's existing error label; VoiceOver reads the same words a sighted person
sees, which today it does not (it reads the enum dump).

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| (no new controls) | — | — | the mapper's sentences are String Catalog keys (`plainError.*`) | [GAP] PlainErrorTests |

## Open questions for the maintainer

1. **Engine sentences and localisation.** The mapper's own sentences go through the String Catalog; the engine's
   `detail` is English. Recommend: keep it English now; when a locale ships, the app words known `code`s itself and
   shows `detail` only for codes it does not know.
2. **The host name in a timeout.** The issue asks that timeouts name the address tried; the rule here shows the host
   name (`macbook-air.local`) but never the URL, port or scheme. Is the host name enough?
3. **Status 404 for "Multi-user is off".** The engine answers 404 for a switched-off feature; 409 would say "the state
   refuses" (as `POST /api/pair/code` already does). Change the status with the code in Step 1.2, or leave it to
   `transport/multiuser-always-on.md`, which removes the switch?
4. **`localizedDescription` everywhere (R3).** The guard flags every `error.localizedDescription` in visible text, not
   only generated-client errors, because a static scan cannot tell them apart. That also catches `AccessError`, whose
   words are fine; the fix is still one mapper call. Agree?
5. **Milestone.** Create `plain-errors`, or file the steps under the existing "Bugs - Log Errors" or
   "Sharing & Pairing — Dead-Simple UX"?
