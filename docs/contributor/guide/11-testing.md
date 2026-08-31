# 11. Testing


How Fichero is tested: the layers, where a new test belongs, how to run each area, fixtures, and the rules that keep test runs from taking the machine down.

### The pyramid

Cheapest layer that can catch the defect wins. Bottom-up (from the \#4241 architecture review):

| Layer | Lives in | Status |
|----|----|----|
| Pure unit (config decisions, parsers, builders, splice rules) | `fichero/Tests/Unit/general/` + `fichero-server/tests/unit/` | built, healthy |
| Store/service + stubbed transport (async state machines) | `fichero/Tests/Unit/general/Services/`, `Transport/` | partial — shared kit planned (#4241 step 1) |
| Engine pytest (pipelines, derivatives, fixtures) | `fichero-server/tests/unit/`, `integration/` | built |
| App↔engine contract | `fichero/Tests/Unit/general/Contract/` | built on spawned engine; in-process harness planned (#4241 step 2) |
| CLI unit (dispatch, connection resolution, transport selection) | `fichero-cli/tests/` | built |
| MCP unit (tool schemas, connection, fail-closed auth) | `fichero-mcp/tests/` | built |
| CLI leg (installed `fichero` binary, hermetic) | `fichero-server/tests/integration/test_cli_installed_roundtrip.py` | built |
| MCP leg (shipped `fichero-mcp` tool surface) | `fichero-server/tests/integration/test_mcp_server_contract.py` | built |
| XCUITest (shipping config only, ~8 flows) | `fichero/Tests/UI/general/` | built |

### Where a new test goes

`fichero/Tests/Unit/general/` mirrors `fichero/fichero/`: a test for `Views/Sidebar/…` goes in `Tests/Unit/general/Views/Sidebar/`, a store test in `Models/`, a service test in `Services/`. Two extra buckets with no app mirror: `Transport/` (connection, pairing, TLS, engine lifecycle, `APIClient`) and `Contract/` (app↔engine and wire-contract tests). Harness files stay at the target root (`EngineHarness.swift`, `TestDefaults.swift`, `TestFixtures.swift`; `UITestEngineHarness.swift` and `RequiresEngine.swift` in `Tests/UI/general/`). UI tests group by surface: `Launch/`, `Library/`, `Inspector/`. Rule: **new tests go in the folder matching the code under test** — never at the target roots.

Unit and UI tests each split by destination: `Unit/{general,mac,ios,ipad}` and `UI/{general,mac,ios,ipad}`. The platform-agnostic bulk stays in `general/`; a genuinely platform-only test goes in its platform folder. Test plans live in `fichero/Tests/plans/`, audited statically by `scripts/check_test_plans_runnable.py`, which also prints the scheme/plan matrix and exact `xcodebuild` invocations. Every iOS-family plan selects an idiom canary test that fails loudly when a plan executes on the wrong device family, so no plan can be empty-and-green or silently verify the wrong platform (#4472).

### Running areas

Workers verify their own diff only; the manager owns full-suite runs and Xcode builds.

    # Engine — always with PYTHONPATH relative to YOUR worktree
    PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/ -q
    PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/test_ingest_module.py -q   # one area

    # CLI / MCP products — their own test dirs; each conftest puts the sibling
    # src/ trees on sys.path, so no PYTHONPATH is needed for these two.
    pytest fichero-cli/tests -q
    pytest fichero-mcp/tests -q

    # Never `pytest fichero-server/tests` (pulls the ~50-min perf suite).
    scripts/verify_perf.sh          # perf, deliberately, on its own

    # Guardrails — all of them, before any push
    for s in scripts/check_*.py; do python3 "$s" || break; done

Area-scoped runs are live: `scripts/gate part <area>` runs one area’s leg (lint + build + Swift tests + engine tests + perf ratchet; `scripts/gate areas` lists the areas). It runs the same checks the release gate runs, scoped to one area, so green here means what green means there — minutes instead of ninety. It also times every test against its best-ever result (`fichero-server/tests/perf_baseline.json`): faster tightens the bar permanently; slower fails, and you either re-run on a quiet machine or raise the entry saying what bought the time. The issue you are working on is the unit of performance, not the release.

The whole-tree `pytest fichero-server/tests` form is banned: it silently pulls in the perf suite (~70-minute run, two tests are 73% of it). Those two are slow, not hung; `verify_perf.sh` streams their output. Also check `pgrep -f xcodebuild` before starting the perf suite or a whole-tree run — a perf run plus an Xcode build has pushed the build machine past the load where the OS starts killing processes.

### Fixtures

One shared, versioned fixture library at the repo root:

- `test-fixtures/files/` — tiny REAL specimens (pdf, multi-page pdf, jpg, png, heic, docx, legacy .doc, md, txt, IIIF manifest) plus corrupt/edge specimens (`empty.txt`, `wrong_extension.pdf`, `sample_corrupted.docx`). Every fixture is minimal; a unit test fails any specimen over 1 MB.
- `test-fixtures/coverage-ratchet/` — synthetic reports proving the coverage guardrail fires.

Resolvers — one per language, never hand-rolled paths:

    from tests.fixture_paths import sample_file      # engine tests
    pdf = sample_file("multipage.pdf")               # raises if missing
    let pdf = try TestFixtures.sampleFile("multipage.pdf")  // Tests/Unit/general

Seeded libraries all come from ONE builder — `fichero-server/scripts/seed_test_library.py` (via `tests/integration/_seedlib.py` in pytest). Engine-only fixtures (contract JSON, paleography) stay under `fichero-server/tests/fixtures/`.

### Engine provisioning rules

- A test must NEVER require an already-running backend, and a live plan with no engine must FAIL loudly — never skip, never silently green.
- The ONE spawn-per-run harness is `fichero-server/scripts/test_engine_harness.py`. It seeds the synthetic `--full` library (deterministic ids, every DocType, both workflow shapes), spawns the engine on a temp UDS socket with a disposable app-home and parent-pid orphan accountability, waits bounded for `/api/health`, prints one ready-JSON line, and tears everything down. Consumers: `UITestEngineHarness` (Swift), the `spawned_engine` pytest fixture, and the scripted UX smoke (`scripts/ux_smoke.py`).
- `EngineHarness` (the Swift unit contract suite) still self-provisions a TLS engine; `FICHERO_REPO_ROOT` overrides discovery for both Swift harnesses.

### Memory-safety rules

Unserialized runs have crashed the build machine (a 56 GB XCUITest incident):

- ONE `xcodebuild` at a time, ever.
- Never run the perf suite and an Xcode build together.
- XCUITests: never poll the accessibility tree in a loop; launch-stress suites live only in the embedded plan.
- macOS XCUITests need a GUI session; headless runs time out.
- Workers do not run xcodebuild or full Swift suites — the manager does, serialized.

### Coverage and the habit

Coverage is on in the mac and iPad test plans. The ratchet (`scripts/check_coverage_ratchet.py`) fails any run where line coverage drops below `coverage-baseline.json` minus tolerance and only moves via a deliberate `--update-baseline` commit:

    # engine
    coverage run -m pytest fichero-server/tests/unit && coverage json -o agent-work/coverage/engine.json
    # swift (after a plan run with coverage)
    xcrun xccov view --report --json Result.xcresult > agent-work/coverage/swift.json
    python3 scripts/check_coverage_ratchet.py

Every change ships with tests in the same commit — edge cases, undo paths, and side effects, not just the happy path (write the failing test first for a bug). Reviewers check the coverage delta and the ratchet output. Would more tests have caught more issues? Then more tests.
