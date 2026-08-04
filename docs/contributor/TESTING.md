# Testing

How Fichero is tested: the layers, where a new test belongs, how to run each
area, fixtures, and the rules that keep test runs from taking the machine
down. This documents what is BUILT today; anything not yet landed is marked
**(planned)**.

## The pyramid

Cheapest layer that can catch the defect wins. From the #4241 architecture
review, bottom-up:

| Layer | Lives in | Status |
|---|---|---|
| Pure unit (config decisions, parsers, builders, splice rules) | `fichero/Tests/Unit/general/` + `fichero-server/tests/unit/` | built, healthy |
| Store/service + stubbed transport (async state machines) | `fichero/Tests/Unit/general/Services/`, `Transport/` | partial — one ad-hoc `MockTransportURLProtocol`; shared kit **(planned, #4241 step 1)** |
| Engine pytest (pipelines, derivatives, fixtures) | `fichero-server/tests/unit/`, `integration/` | built |
| App↔engine contract (in-process, no uvicorn/TLS) | `fichero/Tests/Unit/general/Contract/` | built on spawned uvicorn; in-process `InMemoryEngineApp` harness **(planned, #4241 step 2)** |
| CLI unit (dispatch, connection resolution, transport selection) | `fichero-cli/tests/` | built |
| MCP unit (tool schemas, connection, fail-closed auth) | `fichero-mcp/tests/` | built |
| CLI leg (installed `fichero` binary, hermetic) | `fichero-server/tests/integration/test_cli_installed_roundtrip.py` | built |
| MCP leg (shipped `fichero-mcp` tool surface) | `fichero-server/tests/integration/test_mcp_server_contract.py` | built |
| XCUITest (shipping config only, ~8 flows) | `fichero/Tests/UI/general/` | built |

## Where a new test goes

`fichero/Tests/Unit/general/` mirrors `fichero/fichero/`: a test for
`Views/Sidebar/…` goes in `Tests/Unit/general/Views/Sidebar/`, a store test in
`Models/`, a service test in `Services/`. Two extra buckets that have no app
mirror:

- `Transport/` — connection, pairing, TLS, engine-lifecycle, `APIClient`.
- `Contract/` — app↔engine and wire-contract tests (engine-harness suites).

Harness files stay at the target root (`EngineHarness.swift`,
`TestDefaults.swift`, `TestFixtures.swift`; `UITestEngineHarness.swift` and
`RequiresEngine.swift` in `Tests/UI/general/`). UI tests group by surface:
`Launch/`, `Library/`, `Inspector/`.

Rule: **new tests go in the folder matching the code under test.** Do not add
files to the target roots.

## Running areas

Workers verify their own diff only; the manager owns full-suite runs and
Xcode builds (see `AGENTS.md`).

```bash
# Engine — always with PYTHONPATH relative to YOUR worktree
PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/ -q
PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/test_ingest_module.py -q   # one area

# CLI / MCP products — their own test dirs; each conftest puts the sibling
# src/ trees on sys.path, so no PYTHONPATH is needed for these two.
pytest fichero-cli/tests -q
pytest fichero-mcp/tests -q

# Never `pytest fichero-server/tests` (pulls the ~50-min perf suite).
scripts/verify_perf.sh          # perf, deliberately, on its own

# Swift — manager-run via the fichero-tests.xctestplan (FicheroTests target)
# Guardrails — all of them, before any push
for s in scripts/check_*.py; do python3 "$s" || break; done
```

`gate unit --area sidebar` style area-running **(planned)** — until the gate
harness lands, scope pytest by file/folder and Swift tests by test-plan
selection.

## Fixtures

One shared, versioned fixture library at the repo root:

- `test-fixtures/files/` — tiny REAL specimens (pdf, multi-page pdf, jpg,
  png, heic, docx, legacy .doc, md, txt, IIIF manifest) plus corrupt/edge
  specimens (`empty.txt`, `wrong_extension.pdf` — PNG bytes behind a .pdf
  name — and `sample_corrupted.docx`). Size discipline: every fixture
  minimal; a unit test fails any specimen over 1 MB.
- `test-fixtures/coverage-ratchet/` — synthetic reports proving the coverage
  guardrail fires.

Resolvers — one per language, never hand-rolled paths:

```python
from tests.fixture_paths import sample_file      # engine tests
pdf = sample_file("multipage.pdf")               # raises if missing
```

```swift
let pdf = try TestFixtures.sampleFile("multipage.pdf")  // Tests/Unit/general
```

Seeded libraries all come from ONE builder —
`fichero-server/scripts/seed_test_library.py` (via
`tests/integration/_seedlib.py` in pytest). `--with-files` additionally
imports real specimens as file-backed documents and two extra canonical
workflows; the default output is unchanged. Engine-only fixtures (contract
JSON, paleography) stay under `fichero-server/tests/fixtures/`.

## Engine provisioning rules

- A test must NEVER require an already-running backend. Hermetic legs spawn
  their own engine on an ephemeral port with a temp `HOME` and a seeded temp
  library (`tests/integration/_cli_live.py` is the reference fixture) —
  nothing touches `:8765` or a real library.
- Swift suites that need an engine use `EngineHarness` /
  `UITestEngineHarness` (env `FICHERO_REPO_ROOT` overrides discovery).

## Memory-safety rules

Unserialized runs have crashed this machine (56 GB XCUITest incident):

- ONE `xcodebuild` at a time, ever. Check `pgrep -f xcodebuild` before
  starting a perf suite or any build.
- Never run the perf suite and an Xcode build together.
- XCUITests: never poll the accessibility tree in a loop (tree-snapshot
  polling is the 56 GB pathology); launch-stress suites live ONLY in the
  embedded plan.
- macOS XCUITests need a GUI session; headless runs time out.
- Workers do not run xcodebuild or full Swift suites — the manager does,
  serialized.

## Coverage

Coverage is ON in `fichero-tests.xctestplan` and `fichero-ipad.xctestplan`.
The ratchet (`scripts/check_coverage_ratchet.py`) fails any run where line
coverage drops below `coverage-baseline.json` minus tolerance, prints the
top-20 least-covered production files, and only moves via a deliberate
`--update-baseline` commit. Produce inputs with:

```bash
# engine
coverage run -m pytest fichero-server/tests/unit && coverage json -o agent-work/coverage/engine.json
# swift (after a plan run with coverage)
xcrun xccov view --report --json Result.xcresult > agent-work/coverage/swift.json
python3 scripts/check_coverage_ratchet.py
```

## The habit

Every change ships with tests in the same commit — edge cases, undo paths,
and side effects, not just the happy path (write the failing test first for a
bug). Reviewers check the coverage delta and the ratchet output as part of
review. Would more tests have caught more issues? Then more tests.
