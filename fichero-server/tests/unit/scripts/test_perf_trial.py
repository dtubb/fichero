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


class TestTheEnginesShare:
    """The engine's edit+undo on the Mac is a NECESSARY condition for the 100 ms edit gate,
    not the gate: the app's UndoManager and redraw come on top. It is its own measurement,
    and it must say "engine" -- calling it a Release build would be a false label."""

    ENGINE = {"model": "Mac15,3", "os": "macOS 26.0", "build_configuration": "engine"}

    def test_it_is_gated_at_the_same_budget(self):
        runs = [[300.0], *([[20.0, 30.0, 40.0]] * 5)]
        assert trial.judge(_result(runs, measurement="engine-edit-undo", machine=self.ENGINE)).status == "PASS"

    def test_it_refuses_a_release_label_and_the_app_measurements_refuse_engine(self):
        runs = [[300.0], *([[20.0, 30.0, 40.0]] * 5)]
        release = {**self.ENGINE, "build_configuration": "Release"}
        assert trial.judge(_result(runs, measurement="engine-edit-undo", machine=release)).status == "REFUSED"
        assert trial.judge(_result(runs, measurement="edit-undo", machine=self.ENGINE)).status == "REFUSED"


class TestTheRungsMeasuresFollowTheMethod:
    """`dev-workflows.quality.perf-method` (#6600): the `perf` rung's figures are judged by this method, not by a copy of it."""

    BASELINE = {
        "tolerances": {"wall_ms": 0.05, "peak_rss_mb": 0.03, "disk_kib": 0},
        "figures": {"wall_ms|test_entity_list|Mac16,10": {"median": 100.0}, "disk_kib|library|Mac16,10": {"median": 0}},
    }

    @staticmethod
    def _m(warm, measure="wall_ms", scenario="test_entity_list", model="Mac16,10", cold=250.0, **over):
        r = {"measure": measure, "scenario": scenario, "machine": {"model": model}, "thermal_state": "nominal", "idle": True,
             "runs": [{"value": cold, "cold": True}, *({"value": v} for v in warm)]}
        r.update(over)
        return r

    def test_the_rung_s_measures_follow_the_trial_method_cold_discarded_median_thermal_void_keyed_by_machine_and_tolerance_from_the_file(self):
        # one cold and three warm runs, idle and nominal, inside tolerance: PASS, and the cold 250 is not in the median
        ok = trial.judge_measure(self._m([101.0, 102.0, 103.0]), self.BASELINE)
        assert (ok.status, ok.median) == ("PASS", 102.0)
        # 8% over the baseline median is a FAIL naming the figure and the machine; 4% over passes (5% from the file)
        bad = trial.judge_measure(self._m([108.0, 108.0, 108.0]), self.BASELINE)
        assert bad.status == "FAIL" and "Mac16,10" in bad.reasons[0] and "108" in bad.reasons[0] and "100" in bad.reasons[0]
        assert trial.judge_measure(self._m([104.0, 104.0, 104.0]), self.BASELINE).status == "PASS"
        # the cold run counted in the median is refused by shape
        warm_as_cold = self._m([101.0, 102.0, 103.0])
        warm_as_cold["runs"][0].pop("cold")
        assert trial.judge_measure(warm_as_cold, self.BASELINE).status == "REFUSED"
        # `fair` is VOID, and so is a busy machine
        assert trial.judge_measure(self._m([100.0] * 3, thermal_state="fair"), self.BASELINE).status == "VOID"
        assert trial.judge_measure(self._m([100.0] * 3, idle=False), self.BASELINE).status == "VOID"
        # 100, 100 and 130 ms disagree by 30% of the median: INCONCLUSIVE, never best-of
        assert trial.judge_measure(self._m([100.0, 100.0, 130.0]), self.BASELINE).status == "INCONCLUSIVE"
        # a figure for another machine is never compared with the baseline's: it is recorded, not compared
        other = trial.judge_measure(self._m([500.0] * 3, model="Mac14,2"), self.BASELINE)
        assert other.status == "PASS" and "not compared" in other.reasons[0]
        # a tolerance missing from the file is REFUSED naming the measure
        missing = trial.judge_measure(self._m([1.0] * 3, measure="cpu_ms"), self.BASELINE)
        assert missing.status == "REFUSED" and "cpu_ms" in missing.reasons[0]
        # no thermal state, no machine, too few runs: REFUSED, never a quiet pass
        assert trial.judge_measure(self._m([100.0] * 3, thermal_state=None), self.BASELINE).status == "REFUSED"
        assert trial.judge_measure(self._m([100.0] * 3, machine={}), self.BASELINE).status == "REFUSED"
        assert trial.judge_measure(self._m([100.0] * 2), self.BASELINE).status == "REFUSED"
        # a zero-tolerance measure (disk left behind) fails on any growth
        assert trial.judge_measure(self._m([40.0] * 3, measure="disk_kib", scenario="library"), self.BASELINE).status == "FAIL"
