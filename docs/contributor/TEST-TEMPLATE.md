# Test Template — the tests every surface must have

> Companion to `TESTING-CONSTITUTION.md`. The constitution says *what* the loop is
> (spec → approve → test → code); **this is the checklist so you never have to remember
> which tests to write.** Copy the "Per-surface matrix" into a spec's *Test matrix*
> section, then create the files. The `check_specs_have_tests.py` guardrail keeps the spec
> and its tests bound together.

When you start a surface (a view, a feature, an endpoint — e.g. the Library icon view, the
KG tables), you owe tests across the legs the surface touches. Not every surface touches
every leg; the matrix says which, and each leg below is a **fill-in-the-blank skeleton
grounded in the real harness** so writing it is mechanical.

## Per-surface matrix (copy into the spec's *Test matrix* section)

| Leg | Required when… | Pins | Lives in |
|-----|----------------|------|----------|
| **Pure rule** (Swift) | there is any non-trivial logic (a filter, a mapping, a state machine) | the rule, off-main, no UI | `fichero/Tests/Unit/**/<Area>Tests.swift` |
| **Availability** (Swift) | a capability must be REACHABLE in a surface | "this surface wires this capability" | same, source-string via `AppSource.root()` |
| **Snapshot/Preview** (Swift) | a surface has a VISUAL design to defend (layout, states, empty/error) | the rendered surface matches its committed reference — headless, no launch, no engine | `fichero/Tests/Unit/**/<Area>SnapshotTests.swift` (+ `__Snapshots__/`) |
| **Backend** (pytest) | the surface calls an endpoint / writes data | the endpoint's contract + that data was DELIVERED | `fichero-server/tests/**` |
| **MCP** | the capability should be agent-reachable | the MCP tool maps + routes | `fichero-mcp/tests/test_mcp_full.py` |
| **CLI** | the capability should be scriptable | the CLI command wires the endpoint | `fichero-cli/tests/test_*.py` |
| **Click-around** (XCUITest, Mac) | a user drives it in the UI | the end-to-end path: click → effect | `fichero/Tests/UI/**` (subclass `FicheroUISessionTests`) |
| **iPad/iOS** | the surface ships on touch | the touch path exists | `fichero/Tests/UI/ios`, `…/ipad` + the `fichero-ui-ios/ipad` plans |
| **Load** (#4634) | the surface acts on many rows | bounded, no peg, timed | `fichero-server/tests/perf/**` |

**Hard-gate (Testing Constitution Art. 4):** the cross-surface **invariant** (same result
from backend, MCP, CLI, UX) and **capability availability** are hard-gates. The rest is
tracked debt — but the matrix is how you SEE the debt instead of forgetting it.

---

## Skeletons

### 1. Pure rule (Swift, off-main)
```swift
@testable import Fichero
import XCTest
/// spec: <area> — `<behavior.id>`.
final class <Area>RuleTests: XCTestCase {
    func testRule() {
        XCTAssertEqual(<Type>.<pureFunc>(<input>), <expected>)
    }
}
```

### 2. Availability (Swift — "the capability is present in this surface")
```swift
private static func appSource(_ p: String) throws -> String {
    try String(contentsOf: AppSource.root().appendingPathComponent(p), encoding: .utf8)
}
func testSurfaceWiresCapability() throws {
    let src = try Self.appSource("Views/<Path>/<View>.swift")
    XCTAssertTrue(src.contains("<the wiring token>"), "<surface> must wire <capability>")
}
```

### 2b. Snapshot/preview (Swift — headless UI, the cheap design-led check below XCUITest)
Render a view + fixture to a deterministic image and compare to a committed reference
(`Tests/Unit/general/SnapshotSupport.swift`, `ImageRenderer`-based — no dependency). This is
the layer the 87 `#Preview`s should feed. First run for a new name RECORDS the reference and
fails (never a silent pass); commit the PNG like any reviewed artifact. Baselines are recorded
on **macOS 26** (the deployment floor); a 26↔27 render drift is real signal.
```swift
@Test @MainActor
func <surface>EmptyStateReadsCalm() throws {
    try assertSnapshot(of: <View>(<fixture>), size: .init(width: 320, height: 200),
                       named: "<surface>-empty")   // 1st run records; commit __Snapshots__/<name>.png
}
```
**One render, two uses:** the same `ImageRenderer` pass that asserts a snapshot also *is* the
**doc screenshot** the DOC-TEMPLATE requires for the user manual. Capture the surface once, at
its seeded/fixture state, and both the Test matrix (this leg) and the Documentation matrix
(user-manual screenshot) are satisfied — no separate screenshot step, and the manual image can
never drift from what the test pins. See `DOC-TEMPLATE.md` → user-manual leg.

### 3. Backend (pytest — prove DELIVERY, not just a 200; see check_import_tests_prove_delivery)
```python
def test_<verb>_persists(client, db):
    r = client.post("/api/<route>", json={...})
    assert r.status_code == 200
    assert r.json()["id"]                 # evidence something was delivered
    assert db.get(<Model>, r.json()["id"]) is not None
```

### 4. MCP (mirror `test_mcp_full.py`: a fake client records the call)
```python
def test_<tool>_routes(monkeypatch):
    fake = FakeClient(); ...
    mcp_full.<tool>(<Input>(...))
    assert fake.calls[-1][0] == "<client_method>"
```

### 5. CLI (typer runner; assert it dials the right endpoint)
```python
def test_<command>_wires_endpoint(monkeypatch):
    result = runner.invoke(cli_main.app, ["<group>", "<command>", ...])
    assert result.exit_code == 0
    assert recorded_path == "/api/<route>"
```

### 6. Click-around (XCUITest — the weak leg; this is the whole point of the template)
Subclass `FicheroUISessionTests` — it gives you a launched app over a **seeded** library
(auto-skips when no venv/seeder). Drive by **accessibility identifiers**, assert the effect.
```swift
@MainActor
final class <Area>FlowUITests: FicheroUISessionTests {
    func testUserDoesThingAndSeesResult() {
        waitForLibraryReady()
        // 1. reach the surface (a mode button / sidebar row by its a11y id)
        app.buttons["<surface.entry.id>"].firstMatch.tap()
        // 2. act (select a seeded row, invoke the verb)
        let row = app.descendants(matching: .any)
            .matching(identifier: "<row.id.for(seeded.ids[...])>").firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: readyTimeout))
        row.rightClick(); app.menuItems["<verb.id>"].tap()
        // 3. assert the effect (the row is gone / a value changed)
        XCTAssertFalse(row.waitForExistence(timeout: 5))
    }
}
```
**Prerequisite for this leg (per surface):** the views need **stable accessibility
identifiers** on their key controls and rows (e.g. `.accessibilityIdentifier("kg.entity.row.\(id)")`,
`"kg.menu.delete"`). No a11y ids ⇒ the click-around test can't find anything. **Adding the
ids is part of building the surface, not an afterthought** — list them in the spec.

### 7. iPad/iOS
Same as the click-around skeleton, but the test targets the `fichero-ui-ipad` / `fichero-ui-ios`
plans; keep it to the touch path (tap, not right-click) and the reduced first-run IA.

### 8. Load (#4634)
```python
def test_<verb>_1k_is_bounded(client, benchmark):
    ids = seed_many(1000)
    # act on 1000; assert it completes within budget and concurrency stays bounded
```

---

## The process — any surface, turn the crank

The same abstract procedure prepares design-led testing for every surface (KG tables today,
Library icon view next, and on through all of them). Each step has a guardrail gate, so the
process is enforced, not remembered.

1. **Scaffold.** `cp docs/contributor/specs/_TEMPLATE.md docs/contributor/specs/<surface>.md`
   (or `specs/<area>/<surface>.md`). The scaffold already contains the Intent / Behaviors /
   **Test matrix** / **Accessibility identifiers** / Open-questions sections.
   · *Gate:* `_`-prefixed scaffolds are skipped; real specs are tracked.
2. **Behaviors.** Write one line per behavior with a stable id (`<surface>.<behavior>`) and a
   tag ([OK]/[MISSING]/[PARTIAL]). These ids are what tests cite.
3. **Approve.** The creative director approves the *intent*; flip `Status: DRAFT → APPROVED`.
   · *Gate:* an APPROVED spec MUST be cited by ≥1 test, carry a Test-matrix section
   (`check_specs_have_tests.py`, Rules B + C), **and declare `Milestone: <name>`** matching a
   GitHub milestone of the same name (`check_spec_milestones.py`). On approval, create or rename
   the milestone to the spec name and point its description back at the spec — the link is
   bidirectional (spec name == milestone name == test tag). Tag the tests to the same area name:
   Swift `@Tag` (`TestTags.swift`), pytest markers (`fichero-server/pyproject.toml`).
4. **Fill the matrix.** Tick the legs this surface touches; list the **accessibility
   identifiers** the click-around leg needs (add them to the views as you build).
5. **Test-first, per leg.** One file per ticked leg, from the skeletons above; the docstring
   cites the behavior id. Hard-gate legs (cross-surface invariant + availability) first.
6. **Implement** until the tests pass; add the a11y ids alongside the views.
7. **Verify.** `python scripts/check_specs_have_tests.py` + the full gate (`verify_all.sh`
   runs every `check_*.py`, including this one).

Weakest leg today is **click-around** — treat its skeleton as non-optional for any surface a
user touches. A surface without a click-around test is not "done", it's "unproven in the one
way the user actually experiences it".

## Worked reference
`kg-interactions.md` and `kg-tables.md` carry filled-in Test matrices. Use them as examples
when you spec the Library icon view (or any new surface).
