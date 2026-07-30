# Default-workflow E2E lane — manager scheduling notes (#4326)

New opt-in verification lane, landed 2026-07-30. Nothing is wired into any
gate — the manager schedules it by hand, exactly like `verify_perf.sh`.

## What exists

1. **`scripts/verify_workflows.sh`** (+ driver `scripts/verify_workflows.py`)
   — seeds a disposable fixture library (`seed_test_library.py --with-files`
   into a throwaway `FICHERO_BASE_PATH`, named `global.fichero` so the
   server's own first-open path seeds the shipped default workflows and the
   #4325 keyless bootstrap points every AI tier at the on-device Apple
   provider), boots uvicorn on loopback, then runs every direct-runnable
   default preset through `POST /api/workflow-execution/execute`. Asserts
   per run: `status=completed` (#4316 vocabulary), #4313 provenance fields
   (`run_id`/`workflow_id`/`step_name`) on every artifact the run wrote, and
   non-empty `page_content` for transcription-family workflows. One
   parseable `WORKFLOW-E2E | name=… | status=PASS|FAIL|SKIP | …` line per
   workflow; `WORKFLOW-E2E-SUMMARY` at the end; exit 0 only when 0 failed.
   Missing host capabilities (Apple Intelligence via fm-bridge, Apple Vision
   via PyObjC) produce loud SKIP lines, never silent passes. The driver
   auto-builds `fm-bridge` from source on first run (`--no-build-bridge` to
   disable).

2. **`fichero-server/tests/integration/test_workflow_tool_smoke.py`** —
   generated per-tool smoke: every executable registered tool (#4322
   palette contract) gets one canned invocation through the registry with
   the real `tool(inputs, state, llm_config)` calling convention; LLM-backed
   tools run on the built-in deterministic `mock` provider, pure tools run
   for real. Opt-in via `FICHERO_WORKFLOW_E2E=1` (plus `-m slow` semantics),
   so the normal gate stays fast and never collects it into a slow path
   (tests/integration is outside the gates anyway).

## How to schedule

- **First run: post-release, in daylight, at the console.** Real model
  calls; Apple Vision needs a GUI session (headless/ssh runs stall — see
  the macOS XCUITest memory note; same constraint applies here).
- **Serialize** with xcodebuild and full pytest — one heavy job at a time.
- Full sweep budget defaults to 25 min (`--budget 1500`), 300 s per
  workflow (`--timeout 300`). Over-budget workflows are SKIPPED loudly so
  the run always terminates; re-run with `--only '<regex>'` to cover the
  remainder.
- Red lines are pre-formatted for filing: each `status=FAIL` line carries
  `name=`, `step=`, `error=`. File one issue per FAIL line.
- `status=SKIP` means the HOST lacked a capability (or budget) — the
  workflow is unverified, not healthy. Schedule on capable hardware.
- Per-tool smoke:
  `FICHERO_WORKFLOW_E2E=1 PYTHONPATH=fichero-server/src .venv/bin/pytest
  fichero-server/tests/integration/test_workflow_tool_smoke.py -q`

## First run (2026-07-30, this machine, real on-device models)

`WORKFLOW-E2E-SUMMARY | total=37 | passed=32 | failed=4 | skipped=1 |
seconds=76.6` — full sweep well under budget. Apple Vision + Apple
Intelligence both live (the driver built fm-bridge from source). The
per-tool smoke passes 119/119 in ~30 s.

The 4 reds are SHIPPED-CODE findings (not fixed tonight — purely-additive
release constraint; file as issues):

1. **`1 · Import → Artifacts`** — the `import_receipt` artifact carries
   `run_id`/`step_name` but **no `workflow_id`** (#4313 provenance gap in
   `workflows/tools/import_artifacts.py`).
2. **`Group Same Documents`** — `similarity` json.loads()es the vision
   response, but the keyless default vision model is `apple-vision` (OCR):
   the response can never be JSON, so the preset always dies with
   "Expecting value: line 1 column 1" on a factory-default install. Same
   root cause seen in the tool smoke (strict `_RawSimilarityResult`).
   Needs a JSON-capable vision LLM or a graceful refusal.
3. **`Split Chapters`** — fails with `no such file:
   'files/test-doc-fixture-pdf.pdf'`: the tool does not resolve the
   document's library-relative `path` against the library root (every
   other file-consuming tool in the sweep handles the same doc fine).
4. **`Transcribe (Auto-Detect)`** — live execution ends with "Workflow
   stream ended before exit node(s) completed": the classify route_map
   fan-out completes one branch but the run-completion contract still
   expects the other branches' exit nodes (#4324 follow-up).

Also noteworthy: the built-in `mock` provider (#1566) covers `chat`/
`chat_structured` but NOT the vision path — `llm.vision()` falls through
to LangChain and raises "Unknown LLM provider: 'mock'". The per-tool smoke
stubs the vision seam to work around it; a `mock` branch in `vision()`
would let whole vision workflows run in debug for free.

`Translate (DeepL)` is SKIP: the configured DeepL key gets 403 — an
external-provider condition, out of scope for the on-device lane (the
driver classifies quota/credential runtime errors as loud SKIPs).

Pre-existing breakage found while building (also needs an issue):
`fichero-server/tests/integration/test_catalogue_workflow_execution_e2e.py`
has a SyntaxError (lines 17–20: a `from tests.fixture_paths import …` line
spliced inside another import's parentheses) — the FICHERO_INTEGRATION=1
opt-in path cannot even collect.

## Suggested cadence

- Post-release daylight run first (validates the lane itself on real data).
- Then: after any change to `resources/default_workflows/*.json`,
  `workflows/tools/`, `workflows/builder.py`, or the LLM dispatch layer.
- The lane is disposable-state only; it never touches real libraries.
