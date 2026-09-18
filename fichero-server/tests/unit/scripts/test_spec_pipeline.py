"""Unit tests for scripts/spec_pipeline.py.

Proves the deterministic hand-off state machine (creative director, 2026-09-18): every
illegal state a-g fires, a clean fixture passes, `queue` orders deterministically, `brief`
renders the behavior + issue + standing rules, `--offline` reports its own blindness rather
than reporting green by absence, and a missing specs dir exits 2. Also proves the four
refinements (creative director, 2026-09-18 follow-up): rule (c) exempts arrow ("→ #N
increment K") citations, the baseline ratchet fails only on NEW illegal states and on a
baselined entry that no longer occurs, rule (g) sees an empty milestone via the dedicated
milestone listing, and `queue --kind retag` lists the doc-fixable (b/d/e) debt grouped by
spec. Runs OFFLINE — GitHub data is always injected via a fixture (env var or monkeypatched
function), never the network.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "spec_pipeline.py"
_SPEC = importlib.util.spec_from_file_location("spec_pipeline", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _seed_test_file(tmp_path: Path, rel: str, body: str) -> Path:
    # rel is relative to tmp_path itself, matching the TEST_ROOTS the _isolate fixture sets
    # (tmp_path/"fichero"/"Tests" and tmp_path/"fichero-server"/"tests").
    root = tmp_path / rel
    root.parent.mkdir(parents=True, exist_ok=True)
    root.write_text(body, encoding="utf-8")
    return root.parent


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own specs dir, test roots, and baseline file; nothing here should
    touch the real repo tree or the network. `get_milestones` is left as the REAL
    implementation unless a test stubs it (via `_fake_issues`'s default or explicitly) — so
    the env-var-injection test for it still exercises real code."""
    specs_dir = tmp_path / "docs" / "contributor_manual" / "specs"
    monkeypatch.setattr(_mod, "SPECS_DIR", specs_dir)
    monkeypatch.setattr(_mod, "TEST_ROOTS", [tmp_path / "fichero" / "Tests", tmp_path / "fichero-server" / "tests"])
    monkeypatch.setattr(_mod, "AGENT_WORK_DIR", tmp_path / "agent-work")
    monkeypatch.setattr(_mod, "BASELINE_PATH", tmp_path / "spec_pipeline_baseline.json")
    monkeypatch.delenv("SPEC_PIPELINE_FAKE_ISSUES", raising=False)
    monkeypatch.delenv("SPEC_PIPELINE_FAKE_MILESTONES", raising=False)
    return tmp_path


def _seed(tmp_path: Path, body: str, rel: str = "ui/example.md") -> None:
    p = _mod.SPECS_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _fake_issues(monkeypatch, issues: list[dict]) -> None:
    monkeypatch.setattr(_mod, "get_issues", lambda offline: None if offline else issues)
    # Default milestones view derived from the faked issues' own milestone titles, so a
    # test that doesn't care about rule (g) doesn't need to stub it explicitly. A test that
    # DOES care about rule (g) re-stubs `get_milestones` itself, after calling this.
    titles = sorted({(i.get("milestone") or {}).get("title") for i in issues if i.get("milestone")})
    monkeypatch.setattr(_mod, "get_milestones", lambda offline: None if offline else [{"title": t} for t in titles])


def _capture_json(fn, /, **kwargs) -> list:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(**kwargs)
    return json.loads(buf.getvalue())


def _check(offline=False, strict=False, update_baseline=False):
    return _mod.cmd_check(offline=offline, strict=strict, update_baseline=update_baseline)


CLEAN_SPEC = """# Example — Design Spec

> Milestone: modes-to-panes
> Manual: TBD — n/a for this fixture

## Behaviors

- `m2p.thing-works` — **[OK]** the thing works. Pinned by `ThingWorksTests`. (#100)
- `m2p.thing-broken` — **[BROKEN]** the thing is broken. (#101)
"""

ISSUES_CLEAN = [
    {"number": 100, "state": "CLOSED", "milestone": {"title": "modes-to-panes"}, "labels": [], "title": "thing works", "assignees": []},
    {"number": 101, "state": "OPEN", "milestone": {"title": "modes-to-panes"}, "labels": [], "title": "thing broken", "assignees": []},
]


def test_clean_fixture_passes(tmp_path, monkeypatch):
    _seed(tmp_path, CLEAN_SPEC)
    _seed_test_file(tmp_path, "fichero/Tests/ThingWorksTests.swift", "struct ThingWorksTests {}")
    _fake_issues(monkeypatch, ISSUES_CLEAN)
    assert _check() == 0


# Rule (a): broken/gap/partial/missing with no cited issue.
RULE_A_SPEC = """# Spec

## Behaviors

- `m2p.no-issue` — **[BROKEN]** this cites nothing.
"""


def test_rule_a_broken_with_no_issue_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


# Rule (b): cites a CLOSED issue while still tagged broken.
RULE_B_SPEC = """# Spec

## Behaviors

- `m2p.stale-tag` — **[BROKEN]** cites a closed issue. (#200)
"""


def test_rule_b_closed_issue_still_broken_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_B_SPEC)
    _fake_issues(monkeypatch, [
        {"number": 200, "state": "CLOSED", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    assert _check() == 1


# Rule (c): cited issue's milestone != the spec's declared milestone — PLAIN citation only.
RULE_C_SPEC = """# Spec

> Milestone: modes-to-panes

## Behaviors

- `m2p.wrong-milestone` — **[GAP]** cites an issue on the wrong milestone. (#300)
"""

RULE_C_ARROW_SPEC = """# Spec

> Milestone: modes-to-panes

## Behaviors

- `m2p.superseded` — **[GAP]** superseded by an epic increment on another milestone. (→ #300 increment 2)
"""


def test_rule_c_milestone_mismatch_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_C_SPEC)
    _fake_issues(monkeypatch, [
        {"number": 300, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "x", "assignees": []},
    ])
    # The spec's own declared milestone ("modes-to-panes") also exists on GitHub, so this
    # test isolates rule (c) — it shouldn't also trip rule (g). "workflows" itself has no
    # spec, but rule (g) only flags a milestone that HAS ISSUES with no spec, so leaving it
    # off the live-milestones list here (only its issue exists, via get_issues) keeps rule
    # (g) irrelevant to this test.
    monkeypatch.setattr(_mod, "get_milestones", lambda offline: [{"title": "modes-to-panes"}])
    assert _check() == 1


def test_rule_c_arrow_citation_is_exempt(tmp_path, monkeypatch):
    # Same cross-milestone shape as the failing case above, but cited with "→" — a
    # deliberate pointer to another tracked epic, not a milestone-hygiene mistake.
    _seed(tmp_path, RULE_C_ARROW_SPEC)
    _fake_issues(monkeypatch, [
        {"number": 300, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "x", "assignees": []},
    ])
    monkeypatch.setattr(_mod, "get_milestones", lambda offline: [{"title": "modes-to-panes"}])
    assert _check() == 0


# Rule (d): [OK] with no test, and [OK] citing a test that doesn't exist.
RULE_D_NO_TEST = """# Spec

## Behaviors

- `m2p.ok-no-test` — **[OK]** works, cites nothing.
"""

RULE_D_MISSING_TEST = """# Spec

## Behaviors

- `m2p.ok-missing-test` — **[OK]** works. Pinned by `NoSuchTests`.
"""


def test_rule_d_ok_with_no_test_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_NO_TEST)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_ok_with_nonexistent_test_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_ok_with_real_test_passes(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("NoSuchTests", "RealThingTests"))
    _seed_test_file(tmp_path, "fichero/Tests/RealThingTests.swift", "struct RealThingTests {}")
    _fake_issues(monkeypatch, [])
    assert _check() == 0


# --- rule (d) recognizer shapes (creative-director, 2026-09-18 follow-up): a spec citing
# `FooTests.method` or a pytest node id is MORE precise than a bare class name, and that
# precision should be verified, not discarded — a cited method that doesn't exist in its
# class IS a real finding, not just a reformatting nuisance.

SWIFT_TEST_CLASS_WITH_METHODS = """struct FooTests {
    func testAlpha() {}
    func testBeta() {}
}
"""

PYTEST_CLASS_WITH_METHODS = """class TestFoo:
    def test_alpha(self):
        pass

    def test_beta(self):
        pass


def test_top_level():
    pass
"""


def test_rule_d_bare_pytest_style_class_resolves(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("NoSuchTests", "TestFoo"))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_class_dot_method_resolves_when_method_exists(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("Pinned by `NoSuchTests`.", "Pinned by `FooTests.testAlpha`."))
    _seed_test_file(tmp_path, "fichero/Tests/FooTests.swift", SWIFT_TEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_class_dot_method_fails_when_method_missing(tmp_path, monkeypatch):
    # The class is real; the cited METHOD is not — this must still fail, not silently pass
    # just because the class resolves.
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("Pinned by `NoSuchTests`.", "Pinned by `FooTests.testNoSuchMethod`."))
    _seed_test_file(tmp_path, "fichero/Tests/FooTests.swift", SWIFT_TEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_class_dot_method_fails_when_class_missing(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("Pinned by `NoSuchTests`.", "Pinned by `GhostTests.testAlpha`."))
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_swift_path_ending_in_tests_swift_resolves(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.",
        "Pinned by `fichero/Tests/Unit/general/FooTests.swift`."))
    _seed_test_file(tmp_path, "fichero/Tests/Unit/general/FooTests.swift", SWIFT_TEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_swift_path_ending_in_tests_swift_fails_when_missing(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.",
        "Pinned by `fichero/Tests/Unit/general/GhostTests.swift`."))
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_pytest_bare_file_resolves(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace("Pinned by `NoSuchTests`.", "Pinned by `test_foo.py`."))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_pytest_node_id_class_and_method_resolves(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.", "Pinned by `test_foo.py::TestFoo::test_alpha`."))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_pytest_node_id_fails_when_method_missing(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.", "Pinned by `test_foo.py::TestFoo::test_no_such_method`."))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_pytest_node_id_top_level_function_resolves(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.", "Pinned by `test_foo.py::test_top_level`."))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


def test_rule_d_pytest_node_id_fails_when_top_level_function_missing(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.", "Pinned by `test_foo.py::test_does_not_exist`."))
    _seed_test_file(tmp_path, "fichero-server/tests/test_foo.py", PYTEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 1


def test_rule_d_source_symbol_dot_method_is_not_a_test_citation(tmp_path, monkeypatch):
    # `WorkflowSavePolicy.canAutoSave` is a SOURCE reference, not a test — the class name
    # doesn't look like a test class (no "Tests" suffix / "Test" prefix), so it must not be
    # treated as an (unresolvable) test citation. This behavior cites a real class
    # separately so it still passes overall.
    spec = RULE_D_MISSING_TEST.replace(
        "Pinned by `NoSuchTests`.",
        "See `WorkflowSavePolicy.canAutoSave`. Pinned by `FooTests`.")
    _seed(tmp_path, spec)
    _seed_test_file(tmp_path, "fichero/Tests/FooTests.swift", SWIFT_TEST_CLASS_WITH_METHODS)
    _fake_issues(monkeypatch, [])
    assert _check() == 0


# Rule (e): [OK] citing an issue that is still OPEN.
RULE_E_SPEC = """# Spec

## Behaviors

- `m2p.ok-open-issue` — **[OK]** works. Pinned by `SomeTests`. (#400)
"""


def test_rule_e_ok_cites_open_issue_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_E_SPEC)
    _seed_test_file(tmp_path, "fichero/Tests/SomeTests.swift", "struct SomeTests {}")
    _fake_issues(monkeypatch, [
        {"number": 400, "state": "OPEN", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    assert _check() == 1


def test_rule_e_ok_cites_closed_issue_passes(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_E_SPEC)
    _seed_test_file(tmp_path, "fichero/Tests/SomeTests.swift", "struct SomeTests {}")
    _fake_issues(monkeypatch, [
        {"number": 400, "state": "CLOSED", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    assert _check() == 0


# Rule (g): a live GitHub milestone with no spec — including one with ZERO issues, which
# `gh issue list` alone would never surface (the blind spot the second fetch closes).
def test_rule_g_empty_milestone_with_no_spec_fails(tmp_path, monkeypatch):
    _seed(tmp_path, CLEAN_SPEC)  # declares Milestone: modes-to-panes, nothing else
    _fake_issues(monkeypatch, ISSUES_CLEAN)
    monkeypatch.setattr(_mod, "get_milestones", lambda offline: [
        {"title": "modes-to-panes"},
        {"title": "some-orphan-surface"},  # no spec declares this milestone; zero issues
    ])
    assert _check() == 1


def test_rule_g_workstream_bucket_milestone_is_exempt(tmp_path, monkeypatch):
    _seed(tmp_path, CLEAN_SPEC)
    _seed_test_file(tmp_path, "fichero/Tests/ThingWorksTests.swift", "struct ThingWorksTests {}")
    _fake_issues(monkeypatch, ISSUES_CLEAN)
    monkeypatch.setattr(_mod, "get_milestones", lambda offline: [
        {"title": "modes-to-panes"},
        {"title": "Bugs"},
    ])
    assert _check() == 0


# --offline: never green-by-absence.
def test_offline_reports_blindness_and_only_runs_offline_rules(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, RULE_B_SPEC)  # would fail rule (b) online; offline can't see it
    rc = _check(offline=True)
    out = capsys.readouterr().out
    assert "OFFLINE" in out
    assert rc == 0  # rule (a) is satisfied (it cites #200); rule (b) is invisible offline


def test_offline_still_catches_offline_rule_a(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    assert _check(offline=True) == 1


# Missing specs dir -> exit 2 (via main(), which gates on SPECS_DIR.exists()).
def test_missing_specs_dir_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "SPECS_DIR", tmp_path / "does_not_exist")
    assert _mod.main(["check"]) == 2
    assert _mod.main(["queue"]) == 2
    assert _mod.main(["brief", "whatever"]) == 2


def test_status_exits_0_even_with_missing_specs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_mod, "SPECS_DIR", tmp_path / "does_not_exist")
    assert _mod.main(["status"]) == 0


# --- baseline ratchet ------------------------------------------------------------------

def test_update_baseline_writes_sorted_and_idempotent(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)  # one rule-a illegal state
    _fake_issues(monkeypatch, [])
    assert _check(update_baseline=True) == 0
    assert _mod.BASELINE_PATH.exists()
    first = _mod.BASELINE_PATH.read_text(encoding="utf-8")
    data = json.loads(first)
    assert data == [{"rule": "a", "spec": str(_mod.SPECS_DIR / "ui/example.md").replace("\\", "/"), "key": "m2p.no-issue"}]
    # Re-running --update-baseline with nothing changed is a byte-for-byte no-op.
    assert _check(update_baseline=True) == 0
    assert _mod.BASELINE_PATH.read_text(encoding="utf-8") == first


def test_check_passes_against_its_own_baseline(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    _fake_issues(monkeypatch, [])
    assert _check(update_baseline=True) == 0
    assert _check() == 0  # same illegal state, now baselined debt, not a fresh failure


def test_check_fails_on_new_illegal_state_not_in_baseline(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    _fake_issues(monkeypatch, [])
    assert _check(update_baseline=True) == 0
    # A second, un-baselined illegal state appears.
    _seed(tmp_path, RULE_B_SPEC, "ui/second.md")
    _fake_issues(monkeypatch, [
        {"number": 200, "state": "CLOSED", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    assert _check() == 1


def test_check_fails_when_baselined_entry_no_longer_occurs(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    _fake_issues(monkeypatch, [])
    assert _check(update_baseline=True) == 0
    # Fixed at the source, but nobody re-ran --update-baseline to shrink the list.
    _seed(tmp_path, CLEAN_SPEC.replace("m2p.thing-broken", "m2p.no-issue-renamed"))
    _fake_issues(monkeypatch, ISSUES_CLEAN)
    _seed_test_file(tmp_path, "fichero/Tests/ThingWorksTests.swift", "struct ThingWorksTests {}")
    assert _check() == 1


# --- queue ordering: deterministic by (milestone priority, tag severity, spec order) -----

QUEUE_SPEC = """# Spec

> Milestone: workflows

## Behaviors

- `q.gap-workflows` — **[GAP]** a gap on workflows. (#501)
- `q.broken-workflows` — **[BROKEN]** a broken on workflows. (#502)
"""

QUEUE_SPEC_2 = """# Spec 2

> Milestone: modes-to-panes

## Behaviors

- `q.partial-m2p` — **[PARTIAL]** a partial on modes-to-panes. (#503)
"""


def test_queue_orders_by_milestone_priority_then_tag_severity(tmp_path, monkeypatch):
    _seed(tmp_path, QUEUE_SPEC, "ui/workflows.md")
    _seed(tmp_path, QUEUE_SPEC_2, "ui/modes-to-panes.md")
    issues = [
        {"number": 501, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "gap", "assignees": []},
        {"number": 502, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "broken", "assignees": []},
        {"number": 503, "state": "OPEN", "milestone": {"title": "modes-to-panes"}, "labels": [], "title": "partial", "assignees": []},
    ]
    monkeypatch.setattr(_mod, "get_issues", lambda offline: issues)
    items = _capture_json(_mod.cmd_queue, milestone_filter=None, limit=None, as_json=True, offline=False)
    ids = [it["id"] for it in items]
    # modes-to-panes outranks workflows (priority list); within workflows, BROKEN before GAP.
    assert ids == ["q.partial-m2p", "q.broken-workflows", "q.gap-workflows"]


def test_queue_excludes_claimed_and_closed_issues(tmp_path, monkeypatch):
    _seed(tmp_path, QUEUE_SPEC, "ui/workflows.md")
    issues = [
        {"number": 501, "state": "CLOSED", "milestone": {"title": "workflows"}, "labels": [], "title": "gap", "assignees": []},
        {"number": 502, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "broken", "assignees": [{"login": "someone"}]},
    ]
    monkeypatch.setattr(_mod, "get_issues", lambda offline: issues)
    items = _capture_json(_mod.cmd_queue, milestone_filter=None, limit=None, as_json=True, offline=False)
    assert items == []


def test_queue_limit_truncates_after_sorting(tmp_path, monkeypatch):
    _seed(tmp_path, QUEUE_SPEC, "ui/workflows.md")
    _seed(tmp_path, QUEUE_SPEC_2, "ui/modes-to-panes.md")
    issues = [
        {"number": 501, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "gap", "assignees": []},
        {"number": 502, "state": "OPEN", "milestone": {"title": "workflows"}, "labels": [], "title": "broken", "assignees": []},
        {"number": 503, "state": "OPEN", "milestone": {"title": "modes-to-panes"}, "labels": [], "title": "partial", "assignees": []},
    ]
    monkeypatch.setattr(_mod, "get_issues", lambda offline: issues)
    items = _capture_json(_mod.cmd_queue, milestone_filter=None, limit=1, as_json=True, offline=False)
    assert [it["id"] for it in items] == ["q.partial-m2p"]


# --- queue --kind retag: the doc-fixable (b/d/e) debt, grouped by spec -------------------

RETAG_SPEC = """# Spec

## Behaviors

- `retag.stale` — **[BROKEN]** cites a closed issue. (#600)
- `retag.no-test` — **[OK]** works, cites nothing.
"""


def test_queue_retag_lists_rule_b_and_d_grouped_by_spec(tmp_path, monkeypatch):
    _seed(tmp_path, RETAG_SPEC, "ui/retag.md")
    _fake_issues(monkeypatch, [
        {"number": 600, "state": "CLOSED", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    items = _capture_json(_mod.cmd_queue, milestone_filter=None, limit=None, as_json=True, offline=False, kind="retag")
    rules = {it["rule"] for it in items}
    assert rules == {"b", "d"}
    assert all(it["spec"].endswith("ui/retag.md") for it in items)


def test_queue_default_kind_is_code(tmp_path, monkeypatch):
    _seed(tmp_path, RETAG_SPEC, "ui/retag.md")
    _fake_issues(monkeypatch, [
        {"number": 600, "state": "CLOSED", "milestone": None, "labels": [], "title": "x", "assignees": []},
    ])
    # Default queue (code work) excludes the rule-b/d debt entirely: #600 is CLOSED so
    # retag.stale isn't dispatchable code work either — the default queue is empty here.
    items = _capture_json(_mod.cmd_queue, milestone_filter=None, limit=None, as_json=True, offline=False)
    assert items == []


# --- brief ---------------------------------------------------------------------------

def test_brief_renders_behavior_issue_and_rules(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, RULE_A_SPEC)
    monkeypatch.setattr(_mod, "get_issues", lambda offline: [
        {"number": 999, "state": "OPEN", "milestone": None, "labels": [], "title": "the issue title", "assignees": []},
    ])
    # RULE_A_SPEC's behavior cites no issue; use a spec that does for a fuller render.
    _seed(tmp_path, """# Spec

## Behaviors

- `m2p.briefable` — **[GAP]** something to brief. (#999)
""", "ui/briefable.md")
    rc = _mod.cmd_brief("m2p.briefable", offline=False)
    out = capsys.readouterr().out
    assert rc == 0
    assert "m2p.briefable" in out
    assert "#999" in out
    assert "the issue title" in out
    assert "git stash" in out  # standing rules present
    assert "swiftc -parse" in out
    assert "status:in-progress" in out


def test_brief_unknown_behavior_fails(tmp_path, monkeypatch):
    _seed(tmp_path, RULE_A_SPEC)
    assert _mod.cmd_brief("no.such.behavior", offline=True) == 1


# --- status: always exits 0 -----------------------------------------------------------

def test_status_counts_by_tag(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, CLEAN_SPEC)
    rc = _mod.cmd_status()
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK spec_pipeline status" in out


# --- agent-work ------------------------------------------------------------------------

def test_agent_work_triages_folded_historical_untriaged(tmp_path, monkeypatch, capsys):
    agent_work = tmp_path / "agent-work"
    agent_work.mkdir()
    (agent_work / "folded.md").write_text("some review notes", encoding="utf-8")
    (agent_work / "historical.md").write_text("HISTORICAL\n\nold stuff", encoding="utf-8")
    (agent_work / "untriaged.md").write_text("nobody has looked at this", encoding="utf-8")
    monkeypatch.setattr(_mod, "AGENT_WORK_DIR", agent_work)
    _seed(tmp_path, f"# Spec\n\nSources folded in: {agent_work / 'folded.md'}\n")
    rc = _mod.cmd_agent_work()
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 FOLDED" in out
    assert "1 HISTORICAL" in out
    assert "1 UNTRIAGED" in out
    assert "untriaged.md" in out


def test_agent_work_missing_dir_is_info_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(_mod, "AGENT_WORK_DIR", tmp_path / "no-such-dir")
    rc = _mod.cmd_agent_work()
    out = capsys.readouterr().out
    assert rc == 0
    assert "INFO" in out


# --- env-var fake-data injection (the other supported fixture path) --------------------

def test_env_var_fake_issues_injection(tmp_path, monkeypatch):
    fake_path = tmp_path / "fake_issues.json"
    fake_path.write_text(json.dumps(ISSUES_CLEAN), encoding="utf-8")
    monkeypatch.setenv("SPEC_PIPELINE_FAKE_ISSUES", str(fake_path))
    result = _mod.get_issues(offline=False)
    assert result == ISSUES_CLEAN


def test_env_var_fake_milestones_injection(tmp_path, monkeypatch):
    fake = [{"title": "modes-to-panes", "state": "open"}]
    fake_path = tmp_path / "fake_milestones.json"
    fake_path.write_text(json.dumps(fake), encoding="utf-8")
    monkeypatch.setenv("SPEC_PIPELINE_FAKE_MILESTONES", str(fake_path))
    result = _mod.get_milestones(offline=False)
    assert result == fake


# --- truncation guard (2026-09-18 bug): `gh issue list --limit N` returning exactly N
# results proves nothing about what comes after — a low limit against a large repo (4139
# issues here, limit was 1000) made rules c/e/f/g silently blind to everything older than
# the fetch window while `check` still reported green. `_check_not_truncated` must fail
# loud, and `get_issues` must actually call it.

def test_check_not_truncated_raises_when_result_count_equals_limit():
    with pytest.raises(SystemExit) as exc_info:
        _mod._check_not_truncated([{"n": 1}, {"n": 2}, {"n": 3}], limit=3, source="test fetch")
    assert exc_info.value.code == 2


def test_check_not_truncated_raises_when_result_count_exceeds_limit():
    # Shouldn't happen with a real `--limit`, but the check is a >= guard, not a ==
    # coincidence check — prove it doesn't require an exact match.
    with pytest.raises(SystemExit) as exc_info:
        _mod._check_not_truncated([{"n": 1}, {"n": 2}, {"n": 3}, {"n": 4}], limit=3, source="test fetch")
    assert exc_info.value.code == 2


def test_check_not_truncated_passes_when_below_limit():
    _mod._check_not_truncated([{"n": 1}, {"n": 2}], limit=3, source="test fetch")  # no raise


def _fake_gh_process(stdout: str, returncode: int = 0):
    class _FakeCompletedProcess:
        pass

    proc = _FakeCompletedProcess()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = ""
    return proc


def test_get_issues_fails_when_fetch_hits_the_limit(monkeypatch):
    monkeypatch.setattr(_mod, "GH_ISSUE_FETCH_LIMIT", 2)
    monkeypatch.setattr(_mod.shutil, "which", lambda name: "/usr/bin/gh")
    fake_issues = [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "OPEN"}]
    monkeypatch.setattr(_mod.subprocess, "run", lambda *a, **k: _fake_gh_process(json.dumps(fake_issues)))
    with pytest.raises(SystemExit) as exc_info:
        _mod.get_issues(offline=False)
    assert exc_info.value.code == 2


def test_get_issues_passes_when_fetch_is_below_the_limit(monkeypatch):
    monkeypatch.setattr(_mod, "GH_ISSUE_FETCH_LIMIT", 3)
    monkeypatch.setattr(_mod.shutil, "which", lambda name: "/usr/bin/gh")
    fake_issues = [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "OPEN"}]
    monkeypatch.setattr(_mod.subprocess, "run", lambda *a, **k: _fake_gh_process(json.dumps(fake_issues)))
    result = _mod.get_issues(offline=False)
    assert result == fake_issues


# --- pipeline.check.gh-failure-exits-2: without --offline, a missing `gh` exits 2 rather
# than silently skipping every GitHub-dependent rule (2026-09-18, spec-pipeline.md's own
# rule-d burn-down).

def test_get_issues_fails_when_gh_is_missing(monkeypatch):
    monkeypatch.setattr(_mod.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as exc_info:
        _mod.get_issues(offline=False)
    assert exc_info.value.code == 2


# --- pipeline.not-in-gate: the script's name must never match verify_all.sh's `check_*.py`
# auto-discovery glob (`scripts/verify_all.sh`'s `for guardrail in scripts/check_*.py`) — a
# rename back to that pattern would silently pull a network-dependent check into the offline
# gate.

def test_script_name_does_not_match_verify_all_check_glob():
    import fnmatch
    assert not fnmatch.fnmatch(_SCRIPT.name, "check_*.py")
