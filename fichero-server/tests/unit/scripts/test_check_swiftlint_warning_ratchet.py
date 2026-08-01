"""The SwiftLint warning-count ratchet guardrail FIRES (#4446).

Guardrails must match granularity: every rule ships with a fixture proving it
fires. Running the real `swiftlint` binary against a synthetic Swift tree
would be slow and would depend on whatever rules happen to be installed —
instead these tests monkeypatch `_run_swiftlint` (white-box import) to return
canned violation lists, exercising the ratchet logic itself: ~30 lines from
"here are N warnings" to pass/fail/tighten, independent of SwiftLint's own
behavior. The one real-binary integration point (missing SWIFT_SRC / missing
`swiftlint` on PATH -> BLIND) is also covered, and
fichero-server/tests/unit/scripts/test_guardrails_fail_on_missing_input.py
(#4382) separately proves this script fails in a genuinely empty tree end to
end, real subprocess included.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_swiftlint_warning_ratchet.py"


def _import_script():
    spec = importlib.util.spec_from_file_location("check_swiftlint_warning_ratchet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_baseline(path: Path, count: int) -> None:
    path.write_text(
        json.dumps({"swift.lint_warnings": {"count": count, "note": "seed"}}),
        encoding="utf-8",
    )


def _violations(*rule_ids: str) -> list[dict]:
    """One Warning-severity violation per rule_id given, e.g. two of the same
    rule: `_violations("todo", "todo")`."""
    return [{"severity": "Warning", "rule_id": rule_id} for rule_id in rule_ids]


class TestRatchetFires:
    def test_more_warnings_than_best_fires(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo", "line_length"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 1

    def test_one_more_warning_is_still_a_regression(self, tmp_path, monkeypatch):
        """No tolerance: unlike a timing, SwiftLint is deterministic over a
        fixed tree, so one extra warning is never explained by the machine."""
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 1

    def test_the_regression_does_not_become_the_new_baseline(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo", "todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)
        module.main(["--baseline", str(baseline)])
        assert json.loads(baseline.read_text())["swift.lint_warnings"]["count"] == 1

    def test_the_worst_rule_is_named_in_the_failure_output(self, tmp_path, monkeypatch, capsys):
        module = _import_script()
        monkeypatch.setattr(
            module, "_run_swiftlint",
            lambda: _violations("file_length", "file_length", "file_length", "todo"),
        )
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)
        module.main(["--baseline", str(baseline)])
        out = capsys.readouterr().out
        assert "file_length" in out
        assert out.index("file_length") < out.index("todo")


class TestRatchetPasses:
    def test_fewer_warnings_tightens_the_bar(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=10)
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 0
        assert json.loads(baseline.read_text())["swift.lint_warnings"]["count"] == 1

    def test_the_tightened_bar_is_then_enforced(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=10)
        module.main(["--baseline", str(baseline)])  # tightens to 1
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo"))  # 2, was fine before
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 1

    def test_an_equal_count_passes_without_rewriting(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=2)
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 0
        assert json.loads(baseline.read_text())["swift.lint_warnings"]["note"] == "seed"

    def test_errors_are_not_counted_as_warnings(self, tmp_path, monkeypatch):
        """swiftlint's own exit code already gates on errors elsewhere
        (scripts/verify_all.sh's plain `swiftlint lint` step) — this ratchet
        must count only Warning-severity entries, not Error ones."""
        module = _import_script()
        monkeypatch.setattr(
            module, "_run_swiftlint",
            lambda: _violations("todo") + [{"severity": "Error", "rule_id": "force_cast"}],
        )
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 0  # 1 warning, matches baseline — the Error is ignored here

    def test_first_run_sets_the_baseline(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "line_length"))
        baseline = tmp_path / "baseline.json"
        rc = module.main(["--baseline", str(baseline)])
        assert rc == 0
        assert json.loads(baseline.read_text())["swift.lint_warnings"]["count"] == 2


class TestUpdateBaseline:
    def test_update_baseline_records_the_measured_count_unconditionally(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo", "todo", "todo"))
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, count=1)  # smaller than the new measurement
        rc = module.main(["--baseline", str(baseline), "--update-baseline"])
        assert rc == 0
        assert json.loads(baseline.read_text())["swift.lint_warnings"]["count"] == 3

    def test_update_baseline_creates_the_default_baseline_from_scratch(self, tmp_path, monkeypatch):
        """The real bug this guards against: --update-baseline with no
        --baseline flag is exactly how a fresh default baseline gets created
        (this is how scripts/swiftlint_warning_baseline.json itself was
        seeded) — the "default baseline must exist" BLIND check must not
        block its own creation mechanism."""
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo"))
        default_baseline = tmp_path / "does-not-exist-yet.json"
        monkeypatch.setattr(module, "DEFAULT_BASELINE", default_baseline)
        rc = module.main(["--update-baseline"])
        assert rc == 0
        assert json.loads(default_baseline.read_text())["swift.lint_warnings"]["count"] == 1


class TestGoingBlind:
    def test_swiftlint_missing_from_path_is_blind(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module.shutil, "which", lambda _name: None)
        r_baseline = tmp_path / "baseline.json"
        _seed_baseline(r_baseline, count=1)
        rc = module.main(["--baseline", str(r_baseline)])
        assert rc == module.BLIND_EXIT_CODE

    def test_missing_swift_source_tree_is_blind(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "SWIFT_SRC", tmp_path / "does-not-exist")
        r_baseline = tmp_path / "baseline.json"
        _seed_baseline(r_baseline, count=1)
        rc = module.main(["--baseline", str(r_baseline)])
        assert rc == module.BLIND_EXIT_CODE

    def test_unparseable_swiftlint_output_is_blind(self, tmp_path, monkeypatch):
        """Synthesize the exact violation: something that looks like it ran
        but produced garbage — must not be silently treated as 0 warnings."""
        module = _import_script()

        def _boom():
            raise module.Blind("swiftlint produced unparseable output")

        monkeypatch.setattr(module, "_run_swiftlint", _boom)
        r_baseline = tmp_path / "baseline.json"
        _seed_baseline(r_baseline, count=1)
        rc = module.main(["--baseline", str(r_baseline)])
        assert rc == module.BLIND_EXIT_CODE

    def test_a_corrupt_baseline_is_blind_not_a_silent_reset(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "_run_swiftlint", lambda: _violations("todo"))
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{ not json", encoding="utf-8")
        rc = module.main(["--baseline", str(baseline)])
        assert rc == module.BLIND_EXIT_CODE

    def test_default_baseline_missing_is_blind_not_a_silent_pass(self, tmp_path, monkeypatch):
        """The exact scenario test_guardrails_fail_on_missing_input.py
        (#4382) checks: this script alone in an empty directory, so its
        committed default baseline genuinely doesn't exist."""
        module = _import_script()
        monkeypatch.setattr(module, "DEFAULT_BASELINE", tmp_path / "does-not-exist.json")
        rc = module.main([])
        assert rc == module.BLIND_EXIT_CODE


class TestTheRealBinaryIntegration:
    """One test that actually shells out to `swiftlint`, so a change to its
    JSON reporter's field names (the one thing the monkeypatched tests above
    cannot catch) is still caught. Skips gracefully if swiftlint isn't
    installed — CI and every contributor's machine that runs the Swift gate
    has it, but this Python test suite alone should not require it."""

    def test_real_swiftlint_against_the_actual_repo_returns_a_plausible_count(self):
        import shutil

        if shutil.which("swiftlint") is None:
            import pytest
            pytest.skip("swiftlint not installed")
        module = _import_script()
        count, top_rules = module.measure()
        assert count >= 0
        assert isinstance(top_rules, list)
