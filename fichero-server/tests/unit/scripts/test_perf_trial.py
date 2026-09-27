"""The speed trial's METHOD, pinned rule by rule (slice 12, #4940; segment-editor.md).

Each test feeds `perf_trial.judge` the kind of run the rule exists to catch. These are the
`source.perf.*` behaviours: a gate that two people follow to the same answer.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "perf_trial.py"
_SPEC = importlib.util.spec_from_file_location("perf_trial", _SCRIPT)
assert _SPEC and _SPEC.loader
trial = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = trial
_SPEC.loader.exec_module(trial)


def _result(runs, measurement="frame", **overrides):
    result = {
        "measurement": measurement,
        "fixture": "dense-page-20000",
        "shape_count": 20000,
        "machine": {"model": "iPhone12,8", "os": "iOS 26.0", "build_configuration": "Release"},
        "thermal_state": "nominal",
        "idle": True,
        "date": "2026-09-27",
        "runs": [{"values_ms": values, "peak_memory_mb": 300.0} for values in runs],
    }
    result.update(overrides)
    return result


COLD = [40.0]
STEADY = [[8.0, 9.0, 12.0]] * 5


class TestWorstFrameNotMean:
    def test_one_dropped_frame_fails_a_run_whose_mean_is_fine(self):
        """`source.perf.worst-frame-not-mean`: a mean of ~9 ms hides the 30 ms frame a person feels."""
        runs = [COLD, *([[8.0] * 99 + [30.0]] * 5)]
        verdict = trial.judge(_result(runs))
        assert verdict.status == "FAIL"
        assert verdict.worst_ms == 30.0

    def test_steady_frames_under_the_budget_pass(self):
        verdict = trial.judge(_result([COLD, *STEADY]))
        assert verdict.status == "PASS"
        assert verdict.worst_ms == 12.0


class TestFiveRunsMedian:
    def test_the_cold_run_is_discarded(self):
        """A 40 ms cold first run must not fail a warm trial."""
        assert trial.judge(_result([COLD, *STEADY])).status == "PASS"

    def test_fewer_than_one_cold_and_five_runs_is_refused(self):
        verdict = trial.judge(_result([COLD, *STEADY[:3]]))
        assert verdict.status == "REFUSED"

    def test_runs_that_disagree_are_inconclusive_not_the_best_of_five(self):
        """`source.perf.five-runs-median`: spread over a tenth of the median is not an answer."""
        runs = [COLD, [10.0], [10.0], [10.0], [10.0], [14.0]]
        verdict = trial.judge(_result(runs))
        assert verdict.status == "INCONCLUSIVE"


class TestNamesItsMachine:
    def test_a_result_with_no_machine_is_refused(self):
        """`source.perf.names-its-machine`."""
        assert trial.judge(_result([COLD, *STEADY], machine={})).status == "REFUSED"

    def test_a_debug_build_is_refused(self):
        machine = {"model": "Mac15,3", "os": "macOS 26.0", "build_configuration": "Debug"}
        verdict = trial.judge(_result([COLD, *STEADY], machine=machine))
        assert verdict.status == "REFUSED"
        assert any("Release" in r for r in verdict.reasons)

    def test_a_result_with_no_fixture_is_refused(self):
        """`source.perf.declared-fixture`: a number must say which committed page it measured."""
        assert trial.judge(_result([COLD, *STEADY], fixture=None)).status == "REFUSED"


class TestVoidWhenThrottled:
    def test_a_throttled_run_is_void_not_failing(self):
        """`source.perf.void-when-throttled`: slow because hot is not slow code."""
        verdict = trial.judge(_result([COLD, *([[40.0]] * 5)], thermal_state="serious"))
        assert verdict.status == "VOID"
        assert verdict.exit_code == 2

    def test_a_busy_machine_is_void(self):
        assert trial.judge(_result([COLD, *STEADY], idle=False)).status == "VOID"

    def test_an_unreadable_thermal_state_is_refused_not_passed(self):
        """A gate that cannot read its input fails rather than passing quietly."""
        verdict = trial.judge(_result([COLD, *STEADY], thermal_state=None))
        assert verdict.status == "REFUSED"
        assert verdict.exit_code == 1


class TestBaselineOrFail:
    def _baseline(self, median):
        return {"frame|iPhone12,8|dense-page-20000": {"median_ms": median, "date": "2026-09-20", "os": "iOS 26.0"}}

    def test_a_regression_past_the_noise_band_fails_even_under_the_gate(self):
        """`source.perf.baseline-or-fail`: 12 ms is under 16.7, and 20% worse than 10 ms."""
        verdict = trial.judge(_result([COLD, *STEADY]), self._baseline(10.0))
        assert verdict.status == "FAIL"
        assert any("regressed" in r for r in verdict.reasons)

    def test_inside_the_noise_band_passes(self):
        assert trial.judge(_result([COLD, *STEADY]), self._baseline(11.5)).status == "PASS"

    def test_an_improvement_says_to_update_the_baseline_in_the_same_commit(self):
        verdict = trial.judge(_result([COLD, *STEADY]), self._baseline(15.0))
        assert verdict.status == "PASS"
        assert any("SAME COMMIT" in r for r in verdict.reasons)

    def test_update_writes_only_a_pass_and_records_the_machine(self, tmp_path):
        results = tmp_path / "r.json"
        baseline = tmp_path / "b.json"
        results.write_text(json.dumps(_result([COLD, *STEADY])))
        assert trial.main([str(results), "--baseline", str(baseline), "--update"]) == 0
        entry = json.loads(baseline.read_text())["frame|iPhone12,8|dense-page-20000"]
        assert (entry["median_ms"], entry["os"], entry["build_configuration"]) == (12.0, "iOS 26.0", "Release")

        results.write_text(json.dumps(_result([COLD, *([[30.0]] * 5)])))
        assert trial.main([str(results), "--baseline", str(baseline), "--update"]) == 1
        assert json.loads(baseline.read_text())["frame|iPhone12,8|dense-page-20000"]["median_ms"] == 12.0


class TestMemoryGrowth:
    def test_memory_that_grows_with_the_shape_count_fails_whatever_the_figure(self):
        """`source.perf.memory-growth`: x3 from 5,000 to 20,000 shapes is growth with the count."""
        result = _result([COLD, *STEADY], memory_by_shape_count={"5000": 100.0, "20000": 300.0})
        verdict = trial.judge(result)
        assert verdict.status == "FAIL"
        assert any("in proportion" in r for r in verdict.reasons)

    def test_flat_memory_passes(self):
        result = _result([COLD, *STEADY], memory_by_shape_count={"5000": 300.0, "20000": 330.0})
        assert trial.judge(result).status == "PASS"


class TestTheEditGate:
    def test_one_edit_and_undo_is_gated_at_a_tenth_of_a_second(self):
        runs = [[300.0], *([[40.0, 60.0, 95.0]] * 5)]
        assert trial.judge(_result(runs, measurement="edit-undo")).status == "PASS"
        runs = [[300.0], *([[40.0, 60.0, 120.0]] * 5)]
        assert trial.judge(_result(runs, measurement="edit-undo")).status == "FAIL"
