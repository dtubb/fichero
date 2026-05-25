# Unified Verification Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One gate — ⌘U in Xcode and one terminal command — that runs lint + build + run-smoke + tests across the Swift app, Python engine, and CLI, failing loudly if any leg fails.

**Architecture:** A single Python gate script (`verify_python.sh`) is the source of truth for the Python legs. A Swift XCTest (`CrossLanguageGateTests`) shells out to it, so ⌘U (which already compiles + runs the Swift suite) also runs every Python leg and fails on any failure. `verify_all.sh` = `swiftlint` + `xcodebuild test`; because the gate test lives inside the Swift suite, that one command transitively runs everything. A single seeder (`seed_test_library.py`) is the ground-truth library for the Python contract walker, the new CLI contract test, and the Swift harness.

**Tech Stack:** Python 3.12 (FastAPI, httpx, pytest), Swift (XCTest), uvicorn, bash, swiftlint, ruff, xcodebuild.

**Conventions (read before starting):**
- All Python commands set `PYTHONPATH=fichero-engine/src` and use `.venv/bin/<tool>` from the repo root (`/Users/danieltubb/code/fichero-0.0.2`).
- Engine test env contract (match `tests/conftest.py` and the contract walker): `FICHERO_FEATURE_TIER=dev`, `FICHERO_SKIP_DEFAULT_WORKFLOWS=1`, `FICHERO_DISABLE_AUTH=1`.
- A spawned engine must carry `FICHERO_PARENT_PID=<spawner pid>` so it self-terminates (watcher in `fichero/api/main.py`) and never orphans on a port.
- Commit after each task. Conventional commits (`test:`, `feat:`, `chore:`). Local on `0.0.2`; do not push.

---

### Task 1: Shared seeder shim

Make the scripts-only `seed()` importable from tests, so the contract walker and the CLI test seed the **same** library the Swift harness does.

**Files:**
- Create: `fichero-engine/tests/integration/_seedlib.py`
- Test: `fichero-engine/tests/integration/test_seedlib_shim.py`

- [ ] **Step 1: Write the failing test**

```python
# fichero-engine/tests/integration/test_seedlib_shim.py
"""The shared seeder shim builds a library and reports derived ground truth."""


def test_seed_builds_library_with_derived_counts(tmp_path):
    from tests.integration._seedlib import seed

    summary = seed(tmp_path / "shim.fichero")

    # Counts are derived by querying the library back (never hand-declared).
    assert summary["expected"]["documents_total"] == 4
    assert summary["expected"]["children_of_collection"] == 2
    assert summary["expected"]["entities"] == 3
    assert summary["expected"]["claims"] == 3
    assert summary["expected"]["workflows"] == 1
    assert summary["expected"]["artifacts_for_letter"] == 1
    # Seeded IDs are exposed by name.
    assert summary["keys"]["collection"] == "test-collection"
    assert summary["keys"]["doc_letter"] == "test-doc-letter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/integration/test_seedlib_shim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.integration._seedlib'`.

- [ ] **Step 3: Write the shim**

```python
# fichero-engine/tests/integration/_seedlib.py
"""Import the scripts-only seeder as a module so tests share one fixture builder.

`seed_test_library.py` lives in `fichero-engine/scripts/` (not on PYTHONPATH),
so we load it by path. Both the contract walker and the CLI contract test import
`seed` from here, guaranteeing all three clients (engine, CLI, Swift) validate
against the identical ground-truth library.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SEEDER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_test_library.py"

_spec = importlib.util.spec_from_file_location("seed_test_library", _SEEDER_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import wiring
    raise ImportError(f"could not load seeder at {_SEEDER_PATH}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

seed = _module.seed  # (path: Path) -> dict with {path, expected, keys, ids}

__all__ = ["seed"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/integration/test_seedlib_shim.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add fichero-engine/tests/integration/_seedlib.py fichero-engine/tests/integration/test_seedlib_shim.py
git commit -m "test: shared seeder shim so walker + CLI test reuse seed_test_library"
```

---

### Task 2: Unify the contract walker on the shared seeder

Replace the walker's bespoke inline `_seed()` (3 ad-hoc rows: `walk-doc-1`/`walk-ent-1`/`walk-claim-1`) with the shared seeder, and point path-param substitution at the seeded IDs.

**Files:**
- Modify: `fichero-engine/tests/integration/test_contract_endpoint_walk.py:43-72,89-98`

- [ ] **Step 1: Replace the seeded-ID constants and `_seed`**

Replace lines 40-72 (the `SEED_*` constants, `_PARAM_VALUES`, `_PARAM_FALLBACK`, and `_seed`) with:

```python
# Seeded IDs reused across path-param substitution so nested list endpoints
# (e.g. /entities/{entity_id}/documents) reach their serialize path instead of
# 404-ing before the response_model is exercised. Sourced from the shared
# seeder (one ground-truth library for engine + CLI + Swift).
SEED_DOC_ID = "test-doc-letter"
SEED_ENTITY_ID = "test-ent-person"
SEED_CLAIM_ID = "test-claim-1"

_PARAM_VALUES = {
    "doc_id": SEED_DOC_ID,
    "document_id": SEED_DOC_ID,
    "entity_id": SEED_ENTITY_ID,
    "claim_id": SEED_CLAIM_ID,
}
_PARAM_FALLBACK = "contract-walk-nonexistent"
```

(Delete the old `def _seed(db): ...` function entirely — the seeder replaces it. The KG imports `ClaimType`/`EpistemicStatus`/`KnowledgeClaim`/`KnowledgeEntity` at lines 33-38 are now unused; remove them, keeping the `Document` import only if still referenced elsewhere — it is not, so remove the model imports block at lines 32-38.)

- [ ] **Step 2: Rewrite the fixture to use the shared seeder**

Replace the fixture body (lines 89-98, the `package_path` creation + `db = ...; _seed(db)`) with:

```python
@pytest.fixture
def walk_client(tmp_path):
    from tests.integration._seedlib import seed

    package_path = tmp_path / "walk.fichero"
    seed(package_path)  # builds the full deterministic library + closes the db
```

(Leave the rest of the fixture — the `AppDatabase` override, `dependency_overrides`, `TestClient(..., raise_server_exceptions=False)`, and teardown — unchanged.)

- [ ] **Step 3: Run the walker to verify it still passes**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/integration/test_contract_endpoint_walk.py -v`
Expected: PASS (same test count as before; the walk asserts non-500 + no-bare-array against the richer seeded library).

- [ ] **Step 4: Lint**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/tests/integration/test_contract_endpoint_walk.py`
Expected: `All checks passed!` (confirms the removed imports left no F401).

- [ ] **Step 5: Commit**

```bash
git add fichero-engine/tests/integration/test_contract_endpoint_walk.py
git commit -m "test: contract walker seeds via shared seed_test_library (one ground-truth lib)"
```

---

### Task 3: CLI live-contract test

The CLI mirror of the Swift `AppEngineContractTests`: spawn a real engine on an ephemeral port, seed a library, drive the **real** `FicheroClient`, and assert returned values == seeder ground truth. Closes the CLI's mock-only gap.

**Files:**
- Create: `fichero-engine/tests/integration/test_cli_engine_contract.py`

- [ ] **Step 1: Write the failing test (fixture + assertions)**

```python
# fichero-engine/tests/integration/test_cli_engine_contract.py
"""Live CLI<->engine contract test — the CLI mirror of the Swift
AppEngineContractTests.

Spawns a real uvicorn on an ephemeral port (so it never contends with the app's
:8765 or the Swift harness), seeds a disposable library via the shared seeder,
and drives the real cli.FicheroClient against it. Asserts the values the CLI
decodes equal the library's ground truth — proving the CLI's hand-written
request/parse layer faithfully matches the engine, the gap mock tests can't cover.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from fichero.cli import FicheroClient

REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_UVICORN = REPO_ROOT / ".venv" / "bin" / "uvicorn"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if r.status_code == 200 and r.json().get("status") == "healthy":
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def cli_against_seed(tmp_path_factory):
    """Spawn an engine on a free port, seed a library, yield (client, summary)."""
    if not VENV_UVICORN.exists():
        pytest.skip(f"venv uvicorn not found at {VENV_UVICORN}")

    from tests.integration._seedlib import seed

    workdir = tmp_path_factory.mktemp("cli-itest")
    library = workdir / "library.fichero"
    summary = seed(library)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "fichero-engine" / "src"),
        "FICHERO_DISABLE_AUTH": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        # Isolate the app DB so we never lock-fight a real one.
        "FICHERO_BASE_PATH": str(workdir / "base"),
        # Self-terminate if this pytest process dies (no orphan engines).
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    proc = subprocess.Popen(
        [str(VENV_UVICORN), "fichero.api.main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_healthy(base_url):
            pytest.skip("spawned engine never became healthy")
        client = FicheroClient(base_url=base_url, library_path=str(library), token=None)
        try:
            yield client, summary
        finally:
            client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _expected(summary, key):
    return summary["expected"][key]


def test_cli_documents_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_documents()) == _expected(summary, "documents_total")
    children = client.list_documents(parent_id=summary["keys"]["collection"])
    assert len(children) == _expected(summary, "children_of_collection")


def test_cli_workflows_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_workflows()) == _expected(summary, "workflows")


def test_cli_entities_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_entities()) == _expected(summary, "entities")


def test_cli_claims_match_library(cli_against_seed):
    client, summary = cli_against_seed
    assert len(client.list_claims()) == _expected(summary, "claims")


def test_cli_artifacts_match_library(cli_against_seed):
    client, summary = cli_against_seed
    arts = client.list_artifacts(summary["keys"]["doc_letter"], include_descendants=False)
    assert len(arts) == _expected(summary, "artifacts_for_letter")


def test_cli_create_read_delete_round_trip(cli_against_seed):
    client, _ = cli_against_seed
    created = client.create_entity("ITest Entity", entity_type="other")
    fetched = client.get_entity(created.id)
    assert fetched.id == created.id
    assert fetched.canonical_name == "ITest Entity"
    client.delete_entity(created.id)
```

- [ ] **Step 2: Run to verify it passes (this is integration TDD — the test exercises real wiring, so it should pass once written if the CLI/engine agree)**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/integration/test_cli_engine_contract.py -v`
Expected: 6 passed. If a `len()` assertion fails, that is a **real CLI↔engine contract bug** to investigate (the test is correct by construction — counts come from the seeder). If it skips, the venv/uvicorn is missing.

- [ ] **Step 3: Lint**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/tests/integration/test_cli_engine_contract.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add fichero-engine/tests/integration/test_cli_engine_contract.py
git commit -m "test: live CLI<->engine contract test (CLI mirror of AppEngineContractTests)"
```

---

### Task 4: `verify_python.sh` — the Python gate (single source of truth)

**Files:**
- Create: `scripts/verify_python.sh` (repo root `scripts/`)

- [ ] **Step 1: Confirm `scripts/` exists**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && ls scripts/`
Expected: lists existing scripts (e.g. `build_backend_bundle.sh`). If absent, `mkdir -p scripts`.

- [ ] **Step 2: Establish the green unit baseline (find env-flaky tests to deselect)**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -20`
Expected: note any failures. Per the contract handoff, ~5 embedding tests fail when the fastembed model is unavailable. Capture their node IDs (e.g. `grep -i embed`). If they fail purely from a missing model (not a code bug), they'll be deselected in Step 3 via `-k "not embedding"`. If they pass on this machine, drop the `-k` filter.

- [ ] **Step 3: Write the gate script**

```bash
# scripts/verify_python.sh
#!/usr/bin/env bash
# Single source of truth for the Python side of the unified verification gate:
# lint + unit tests + GET-contract walk + backend start-smoke + CLI smoke + the
# live CLI<->engine contract test. Exits non-zero on the first failed leg.
# Invoked by CrossLanguageGateTests.swift (so ⌘U runs it) and, later, the autoloop.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
export PYTHONPATH="fichero-engine/src"
PY=".venv/bin/python"
PYTEST=".venv/bin/pytest"
RUFF=".venv/bin/ruff"
UVICORN=".venv/bin/uvicorn"

fail=0
run() {  # run "<label>" <cmd...>
  local label="$1"; shift
  echo "── $label ──"
  if "$@"; then echo "✅ $label"; else echo "❌ $label"; fail=1; fi
}

# 1. Lint (ruff == "pylint")
run "ruff" "$RUFF" check fichero-engine/src/ fichero-engine/tests/ fichero-engine/scripts/

# 2. Backend unit tests (includes the mocked CLI unit tests).
#    `-k "not embedding"` skips tests that need an unavailable fastembed model;
#    drop the filter if those models are present on this machine (see Task 4 Step 2).
run "backend unit" "$PYTEST" fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived -q -k "not embedding"

# 3. GET contract walk (every list endpoint serializes against its response_model).
run "contract walk" "$PYTEST" fichero-engine/tests/integration/test_contract_endpoint_walk.py -q

# 4. Backend start-smoke: boot the engine, confirm it serves /health, tear down.
echo "── backend start-smoke ──"
SMOKE_PORT=8799
FICHERO_DISABLE_AUTH=1 FICHERO_FEATURE_TIER=dev FICHERO_SKIP_DEFAULT_WORKFLOWS=1 \
  FICHERO_BASE_PATH="$(mktemp -d)" FICHERO_PARENT_PID=$$ \
  "$UVICORN" fichero.api.main:app --port "$SMOKE_PORT" >/dev/null 2>&1 &
SMOKE_PID=$!
ok=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 0.5
done
kill "$SMOKE_PID" 2>/dev/null; wait "$SMOKE_PID" 2>/dev/null
if [ "$ok" = 1 ]; then echo "✅ backend start-smoke"; else echo "❌ backend start-smoke"; fail=1; fi

# 5. CLI smoke: the CLI imports and its entrypoint runs.
run "cli import" "$PY" -c "import fichero.cli"
run "cli --help" "$PY" -m fichero --help

# 6. Live CLI<->engine contract test.
run "cli contract" "$PYTEST" fichero-engine/tests/integration/test_cli_engine_contract.py -q

echo
if [ "$fail" = 0 ]; then echo "✅✅ verify_python: ALL PASS"; else echo "❌❌ verify_python: FAILURES ABOVE"; fi
exit "$fail"
```

- [ ] **Step 4: Make executable and run it**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && chmod +x scripts/verify_python.sh && scripts/verify_python.sh; echo "exit=$?"`
Expected: each leg prints `✅`, ends with `✅✅ verify_python: ALL PASS` and `exit=0`. If a leg fails, fix it (or, for embedding, confirm the `-k` filter from Step 2).

- [ ] **Step 5: Confirm no orphan engine remains**

Run: `lsof -nP -iTCP:8799 -sTCP:LISTEN 2>/dev/null && echo "ORPHAN" || echo "clean"`
Expected: `clean`.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_python.sh
git commit -m "feat: verify_python.sh — single-source Python gate (lint+tests+walk+smoke+cli contract)"
```

---

### Task 5: `CrossLanguageGateTests.swift` — bolt the Python gate onto ⌘U

**Files:**
- Create: `fichero/fichero-tests/CrossLanguageGateTests.swift`

- [ ] **Step 1: Write the gate test**

```swift
//
//  CrossLanguageGateTests.swift
//  FicheroTests
//
//  Makes ⌘U run the entire Python side of the gate. Shells out to the single
//  source-of-truth verify_python.sh and fails the Swift suite if any Python leg
//  (lint, unit, contract walk, backend smoke, CLI smoke, CLI contract) fails.
//  Skips (not fails) when the script/venv is absent, so a Swift-only checkout
//  still passes — mirroring EngineHarness.
//

import XCTest

@MainActor
final class CrossLanguageGateTests: XCTestCase {
    func test_python_gate_passes() throws {
        guard let repo = EngineHarness.repoRoot() else {
            throw XCTSkip("Repo root not found — skipping Python gate.")
        }
        let script = repo.appendingPathComponent("scripts/verify_python.sh")
        guard FileManager.default.fileExists(atPath: script.path) else {
            throw XCTSkip("verify_python.sh not found — skipping Python gate.")
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [script.path]
        process.currentDirectoryURL = repo
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        let output = String(data: data, encoding: .utf8) ?? "<no output>"
        add(XCTAttachment(string: output))  // visible in the test report

        XCTAssertEqual(
            process.terminationStatus, 0,
            "verify_python.sh failed — see attached output for the failing leg."
        )
    }
}
```

- [ ] **Step 2: Run just this test via Xcode MCP**

Run (Xcode MCP): `RunSomeTests` with `tabIdentifier: "windowtab1"`, tests `[{ "targetName": "FicheroTests", "testIdentifier": "CrossLanguageGateTests" }]`.
Expected: 1 passed. (It builds the test target, runs `verify_python.sh`, asserts exit 0. Takes a couple minutes — it runs the whole Python gate.)

- [ ] **Step 3: Lint the new file**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && swiftlint lint fichero/fichero-tests/CrossLanguageGateTests.swift`
Expected: `0 violations`.

- [ ] **Step 4: Commit**

```bash
git add fichero/fichero-tests/CrossLanguageGateTests.swift
git commit -m "test: CrossLanguageGateTests runs verify_python.sh so ⌘U gates the whole product"
```

---

### Task 6: `verify_all.sh` — the one terminal command

**Files:**
- Create: `scripts/verify_all.sh`

- [ ] **Step 1: Write the script**

```bash
# scripts/verify_all.sh
#!/usr/bin/env bash
# One command to verify the whole product: Swift lint + the full Xcode test run
# (which compiles the app = frontend build, runs 688 Swift tests + the live
# AppEngineContractTests, and runs CrossLanguageGateTests → verify_python.sh,
# i.e. the entire Python side). This is what Daniel runs in a terminal and what
# the autoloop will call later. Same coverage as ⌘U.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

fail=0

echo "── swiftlint ──"
if swiftlint lint --quiet fichero/fichero/; then echo "✅ swiftlint"; else echo "❌ swiftlint"; fail=1; fi

echo "── xcodebuild test (Swift suite + CrossLanguageGate → Python gate) ──"
if xcodebuild test \
    -project fichero/fichero.xcodeproj \
    -scheme Fichero \
    -destination 'platform=macOS' \
    -skipPackagePluginValidation \
    -resultBundlePath "$(mktemp -d)/verify.xcresult"; then
  echo "✅ xcodebuild test"
else
  echo "❌ xcodebuild test"; fail=1
fi

echo
if [ "$fail" = 0 ]; then echo "✅✅ verify_all: ALL PASS"; else echo "❌❌ verify_all: FAILURES ABOVE"; fi
exit "$fail"
```

- [ ] **Step 2: Make executable and run it**

Run: `cd /Users/danieltubb/code/fichero-0.0.2 && chmod +x scripts/verify_all.sh && scripts/verify_all.sh; echo "exit=$?"`
Expected: `✅ swiftlint`, `✅ xcodebuild test`, `✅✅ verify_all: ALL PASS`, `exit=0`. (Several minutes — runs everything. Note: this duplicates a manual ⌘U; run when you want the terminal/one-command path.)

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_all.sh
git commit -m "feat: verify_all.sh — one command runs the full cross-language gate"
```

---

### Task 7: Final ⌘U verification + docs

**Files:**
- Modify: `docs/CLAUDE.md` (add the gate to the Build+Test+Lint section)

- [ ] **Step 1: Full ⌘U run (the real acceptance test)**

Run (Xcode MCP): `RunAllTests` with `tabIdentifier: "windowtab1"`.
Expected: all Swift tests pass **including** `CrossLanguageGateTests/test_python_gate_passes` (which transitively ran the entire Python gate). 0 failed, 0 unexpected skips. Retry once if Xcode returns an "incomplete result bundle" (known transient).

- [ ] **Step 2: Confirm a clean machine afterwards**

Run: `lsof -nP -iTCP:8765,8799 -sTCP:LISTEN 2>/dev/null && echo "ORPHAN" || echo "clean"; ls -d /var/folders/*/*/T/fichero-itest-* /var/folders/*/*/T/cli-itest* 2>/dev/null | wc -l`
Expected: `clean`; temp-dir count not growing unboundedly across runs (note any cleanup follow-up).

- [ ] **Step 3: Document the gate**

Add to `docs/CLAUDE.md` Build+Test+Lint section:

```markdown
## Unified verification gate

One command / one ⌘U runs lint + build + run-smoke + tests for the Swift app,
Python engine, and CLI:

- **Xcode:** ⌘U. `CrossLanguageGateTests` shells out to `scripts/verify_python.sh`,
  so the Swift run also runs every Python leg and fails if any fails.
- **Terminal / autoloop:** `scripts/verify_all.sh` (= swiftlint + `xcodebuild test`).
- **Python only:** `scripts/verify_python.sh` (the single source of truth).

All contract tests seed via `fichero-engine/scripts/seed_test_library.py`.
```

- [ ] **Step 4: Commit**

```bash
git add docs/CLAUDE.md
git commit -m "docs: document the unified verification gate (⌘U + verify_all.sh)"
```

---

## Self-Review

**Spec coverage:**
- Unified `verify_python.sh` source of truth → Task 4. ✓
- `verify_all.sh` one command → Task 6. ✓
- ⌘U runs everything via a Swift gate test → Task 5. ✓
- CLI live-contract test (mirror of Swift) → Task 3. ✓
- Unified seeder across walker + CLI + Swift → Tasks 1–2 (and the Swift harness already uses the same script). ✓
- Lint (swiftlint + ruff) → Tasks 4 & 6. ✓ ("xcode lint" = clean compile via `xcodebuild test`, per spec interpretation.)
- Backend build+run (start-smoke) → Task 4 Step 3 leg 4. ✓
- Frontend build+run → `xcodebuild test` compiles + `AppEngineContractTests` exercise the live service layer (Task 6 / existing). ✓
- CLI build+run → `import fichero.cli` + `python -m fichero --help` + live contract calls (Task 4 legs 5–6, Task 3). ✓
- No orphan engine / port hygiene → `FICHERO_PARENT_PID` in Task 3 fixture & Task 4 smoke; verified Task 5 Step (implicit) + Task 7 Step 2. ✓
- Out of scope (walker writes, autoloop) → not in any task, as intended. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. The only conditional is the documented `-k "not embedding"` filter (Task 4 Step 2 establishes whether it's needed) — explicit, not a placeholder.

**Type/name consistency:** `seed()` returns `{expected, keys, ids}` (Task 1) and is consumed identically in Tasks 2–3. CLI methods (`list_documents`, `list_workflows`, `list_entities`, `list_claims`, `list_artifacts`, `create_entity`/`get_entity`/`delete_entity`) match the real `cli/client.py` signatures. `EngineHarness.repoRoot()` (Task 5) exists and is `@MainActor`/`static`. Script names (`verify_python.sh`, `verify_all.sh`) are consistent across Tasks 4–7.
