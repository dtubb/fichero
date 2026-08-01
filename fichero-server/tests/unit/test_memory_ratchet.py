"""The memory ratchet must fire, must tighten, and must admit when it is blind (#4440).

Memory is the failure that actually stops work here — the disk filled mid-gate,
XCUITests have hit 56 GB, builds shed under swap and return exit 65 with green
tests. So it gets the same rule as elapsed time: it may not get heavier, and it
gets lighter over time, measured against the BEST EVER and never against last
week.

Three things this file exists to hold down:

  * The creep. Fifty accepted 5% growths are a 12x growth, and every one of them
    passes any check that compares a run to the run before it. There is a test
    for exactly that for time; this is its equivalent for memory.
  * The granularity lie. Peak RSS is process-wide and monotonic, so a per-test
    number would be the suite's memory wearing a test's name. The measurement is
    session-level and must SAY so everywhere it is read.
  * The blindness. "I could not measure" must never come back looking like
    "nothing regressed".

Every fixture here SYNTHESISES its own violation in a throwaway file. Nothing is
borrowed from the committed baseline — a test that depends on a real recorded
number stops testing anything the day that number changes, and keeps printing
[ok] while it does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perf_ratchet as _ratchet  # noqa: E402


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    """Point the ratchet at throwaway files and at a fixed, fake peak."""
    path = tmp_path / "perf_baseline.json"
    monkeypatch.setattr(_ratchet, "BASELINE_PATH", path)
    monkeypatch.setattr(_ratchet, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.delenv("FICHERO_PERF_NO_HISTORY", raising=False)
    monkeypatch.setattr(_ratchet, "_another_perf_run_is_active", lambda: False)
    monkeypatch.setattr(_ratchet, "_mem_peak_mb", 0.0)
    monkeypatch.setattr(_ratchet, "_mem_peak_test", "")
    return path


def _peak(monkeypatch, mb: float | None) -> None:
    """Make the process report `mb` as its peak RSS (None = cannot measure)."""
    monkeypatch.setattr(_ratchet, "peak_rss_mb", lambda: mb)


def _seed(path: Path, name: str, mb: float) -> None:
    path.write_text(
        json.dumps({name: {"mb": mb, "commit": "seed", "note": "seed"}}),
        encoding="utf-8",
    )


def _best(path: Path, name: str) -> float:
    return json.loads(path.read_text(encoding="utf-8"))[name]["mb"]


NAME = "mem::session::fichero-server/tests/unit"
SCOPE = "fichero-server/tests/unit"


class TestItMayNotGetHeavier:
    def test_a_heavier_run_is_a_regression(self, baseline, monkeypatch):
        _seed(baseline, NAME, 500.0)
        _peak(monkeypatch, 2000.0)
        regressions, status = _ratchet.flush_session_memory(SCOPE)
        assert status == "measured"
        assert len(regressions) == 1
        assert "4.0x" in regressions[0]

    def test_a_regression_does_not_become_the_new_bar(self, baseline, monkeypatch):
        """The whole point: the bar must never drift upward on its own."""
        _seed(baseline, NAME, 500.0)
        _peak(monkeypatch, 8000.0)
        _ratchet.flush_session_memory(SCOPE)
        assert _best(baseline, NAME) == 500.0

    def test_many_small_growths_cannot_creep_past_it(self, baseline, monkeypatch):
        """The #4440 equivalent of test_many_small_slowdowns_cannot_creep_past_it.

        Twenty runs each within the jitter allowance must not ratchet the bar up
        between them — otherwise the window absorbs each growth and the bar
        drifts up with the thing it was meant to catch. Compared against BEST
        EVER, the creep has nowhere to hide, and the run that finally exceeds the
        allowance fails against the ORIGINAL number.
        """
        _seed(baseline, NAME, 500.0)
        for _ in range(20):
            _peak(monkeypatch, 590.0)  # 1.18x — inside the allowance, never tightens
            assert _ratchet.flush_session_memory(SCOPE) == ([], "measured")
        assert _best(baseline, NAME) == 500.0

        _peak(monkeypatch, 650.0)  # 1.3x against the BEST, not against 590
        regressions, _ = _ratchet.flush_session_memory(SCOPE)
        assert regressions, "twenty small growths dragged the bar up with them"

    def test_the_jitter_allowance_does_not_accumulate(self, baseline, monkeypatch):
        _seed(baseline, NAME, 500.0)
        for _ in range(5):
            _peak(monkeypatch, 595.0)
            _ratchet.flush_session_memory(SCOPE)
        assert _best(baseline, NAME) == 500.0


class TestItGetsLighterOverTime:
    def test_a_lighter_run_tightens_the_bar(self, baseline, monkeypatch):
        _seed(baseline, NAME, 2000.0)
        _peak(monkeypatch, 800.0)
        assert _ratchet.flush_session_memory(SCOPE) == ([], "measured")
        assert _best(baseline, NAME) == 800.0

    def test_the_tightened_bar_is_then_enforced(self, baseline, monkeypatch):
        _seed(baseline, NAME, 2000.0)
        _peak(monkeypatch, 800.0)
        _ratchet.flush_session_memory(SCOPE)
        _peak(monkeypatch, 1800.0)  # was fine before, not now
        regressions, _ = _ratchet.flush_session_memory(SCOPE)
        assert regressions

    def test_a_marginal_improvement_does_not_chase_the_luckiest_sample(
        self, baseline, monkeypatch
    ):
        _seed(baseline, NAME, 1000.0)
        _peak(monkeypatch, 990.0)
        _ratchet.flush_session_memory(SCOPE)
        assert _best(baseline, NAME) == 1000.0


class TestItDoesNotCryWolf:
    def test_a_first_run_sets_the_bar_without_failing(self, baseline, monkeypatch):
        _peak(monkeypatch, 1234.0)
        assert _ratchet.flush_session_memory(SCOPE) == ([], "measured")
        assert _best(baseline, NAME) == 1234.0

    def test_a_tiny_footprint_is_never_a_regression(self, baseline, monkeypatch):
        """A bare interpreter is already tens of MB; below the floor a '3x' is
        interpreter startup, not anything anyone can act on."""
        _seed(baseline, NAME, 20.0)
        _peak(monkeypatch, 60.0)  # 3x, but under the noise floor
        assert _ratchet.flush_session_memory(SCOPE) == ([], "measured")
        assert _best(baseline, NAME) == 20.0


class TestTheNumberSaysWhatItIs:
    """Session-level granularity, stated everywhere the number is read."""

    def test_the_measurement_name_says_it_is_the_whole_session(
        self, baseline, monkeypatch
    ):
        """Peak RSS is process-wide. If the name did not say 'session', someone
        would eventually read it as one test's cost and act on it."""
        _peak(monkeypatch, 900.0)
        _ratchet.flush_session_memory(SCOPE)
        (recorded,) = json.loads(baseline.read_text(encoding="utf-8")).keys()
        assert recorded.startswith("mem::session::")
        assert SCOPE in recorded

    def test_a_different_scope_gets_a_different_bar(self, baseline, monkeypatch):
        """One file and the whole suite have genuinely different peaks. Sharing
        one bar means the narrow run tightens it below what the full suite can
        ever meet, and then the ratchet gets switched off."""
        _peak(monkeypatch, 200.0)
        _ratchet.flush_session_memory("tests/unit/test_one_thing.py")
        _peak(monkeypatch, 4000.0)
        regressions, _ = _ratchet.flush_session_memory("tests")
        assert regressions == [], "the narrow run's bar was applied to the wide one"
        assert set(json.loads(baseline.read_text(encoding="utf-8"))) == {
            "mem::session::tests/unit/test_one_thing.py",
            "mem::session::tests",
        }

    def test_the_regression_line_names_where_the_peak_advanced(
        self, baseline, monkeypatch
    ):
        """A pointer to start from — captioned as a pointer, because the mark is
        monotonic and only ever names the FIRST test to reach a level."""
        _seed(baseline, NAME, 500.0)
        monkeypatch.setattr(_ratchet, "_mem_peak_mb", 2000.0)
        monkeypatch.setattr(_ratchet, "_mem_peak_test", "tests/x.py::test_hog")
        _peak(monkeypatch, 2000.0)
        (line,), _ = _ratchet.flush_session_memory(SCOPE)
        assert "tests/x.py::test_hog" in line
        assert "not that test's cost" in line

    def test_memory_and_timing_share_one_file_without_colliding(
        self, baseline, monkeypatch
    ):
        """Two dimensions, one ratchet. A millisecond entry must never be read as
        megabytes — that is a bar in the wrong scale, held forever."""
        baseline.write_text(
            json.dumps({NAME: {"ms": 500.0, "commit": "x", "note": "a TIMING entry"}}),
            encoding="utf-8",
        )
        _peak(monkeypatch, 4000.0)
        regressions, status = _ratchet.flush_session_memory(SCOPE)
        assert status == "measured"
        assert regressions == [], "a millisecond value was judged as megabytes"
        entry = json.loads(baseline.read_text(encoding="utf-8"))[NAME]
        assert entry["mb"] == 4000.0
        assert _ratchet._load_baseline("ms") == {}, "the mb entry leaked into timing"


class TestItKnowsWhenItHasGoneBlind:
    """'I could not measure' must never look like 'nothing regressed' (#4440)."""

    def test_an_unmeasurable_peak_is_reported_as_blind_not_as_a_pass(
        self, baseline, monkeypatch
    ):
        _seed(baseline, NAME, 500.0)
        _peak(monkeypatch, None)
        regressions, status = _ratchet.flush_session_memory(SCOPE)
        assert status.startswith("blind:")
        assert "not a pass" in status
        assert regressions == []

    def test_blindness_writes_nothing(self, baseline, monkeypatch):
        """A blind run must not set a bar, and must not clear one."""
        _seed(baseline, NAME, 500.0)
        _peak(monkeypatch, None)
        _ratchet.flush_session_memory(SCOPE)
        assert _best(baseline, NAME) == 500.0

    def test_blindness_is_distinguishable_from_deliberate_abstention(
        self, baseline, monkeypatch
    ):
        """A shared machine is a decision not to record. A broken instrument is
        not. They need different words because they need different responses."""
        _peak(monkeypatch, 900.0)
        monkeypatch.setattr(_ratchet, "_another_perf_run_is_active", lambda: True)
        _, contended = _ratchet.flush_session_memory(SCOPE)
        assert contended.startswith("skipped:")

        monkeypatch.setenv("FICHERO_PERF_NO_HISTORY", "1")
        monkeypatch.setattr(_ratchet, "_another_perf_run_is_active", lambda: False)
        _, disabled = _ratchet.flush_session_memory(SCOPE)
        assert disabled.startswith("skipped:")

        monkeypatch.delenv("FICHERO_PERF_NO_HISTORY")
        _peak(monkeypatch, None)
        _, blind = _ratchet.flush_session_memory(SCOPE)
        assert blind.startswith("blind:")
        assert not baseline.exists(), "an abstaining or blind run recorded a bar"

    def test_a_deliberate_opt_out_is_not_reported_as_a_broken_instrument(
        self, baseline, monkeypatch
    ):
        """Precedence matters. Someone who switched the ratchet off has already
        decided not to learn anything this run, so failing the gate at them with
        'blind' would be a false alarm — and false alarms are how a guardrail
        gets switched off for good."""
        monkeypatch.setenv("FICHERO_PERF_NO_HISTORY", "1")
        _peak(monkeypatch, None)
        _, status = _ratchet.flush_session_memory(SCOPE)
        assert status.startswith("skipped:")

    def test_a_refused_getrusage_reads_as_blind(self, monkeypatch):
        """Sandboxes do refuse it. The honest answer is None, not zero."""
        import resource

        def _refuse(_who):
            raise OSError("operation not permitted")

        monkeypatch.setattr(resource, "getrusage", _refuse)
        assert _ratchet.peak_rss_mb() is None

    def test_a_wrong_unit_reads_as_blind_rather_than_as_a_lean_run(self, monkeypatch):
        """ru_maxrss is BYTES on macOS and KILOBYTES on Linux. Getting that
        backwards is a 1024x error — a bar nothing can fail, or one nobody can
        meet. A sub-megabyte 'peak' is impossible for a live Python process, so
        it means the unit is wrong, and that must read as blindness."""
        import resource

        class _Tiny:
            ru_maxrss = 4  # 4 bytes on macOS / 4 KB on Linux: neither is real

        monkeypatch.setattr(resource, "getrusage", lambda _who: _Tiny())
        assert _ratchet.peak_rss_mb() is None

    def test_a_zero_peak_reads_as_blind(self, monkeypatch):
        import resource

        class _Zero:
            ru_maxrss = 0

        monkeypatch.setattr(resource, "getrusage", lambda _who: _Zero())
        assert _ratchet.peak_rss_mb() is None

    def test_a_real_measurement_is_plausible(self):
        """The instrument is not stubbed here — if the unit maths is wrong on
        this platform, this is what notices. A live pytest process is somewhere
        between a few tens of MB and a few tens of GB; anything outside that is
        a unit error, not a measurement."""
        mb = _ratchet.peak_rss_mb()
        assert mb is not None, "peak RSS is unreadable on the machine running the suite"
        assert 10.0 < mb < 100_000.0, f"implausible peak RSS: {mb} MB — check the unit"


class TestTheHighWaterHint:
    def test_it_names_the_test_the_mark_advanced_during(self, baseline, monkeypatch):
        _peak(monkeypatch, 100.0)
        _ratchet.note_test_memory("tests/x.py::test_a")
        _peak(monkeypatch, 900.0)
        _ratchet.note_test_memory("tests/x.py::test_b")
        _peak(monkeypatch, 200.0)
        _ratchet.note_test_memory("tests/x.py::test_c")
        peak, test = _ratchet.peak_test_hint()
        assert (peak, test) == (900.0, "tests/x.py::test_b")

    def test_a_later_test_does_not_inherit_an_earlier_peak(self, baseline, monkeypatch):
        """The trap this whole design is built around: the mark is monotonic, so
        a naive reading hands every later test the high-water mark of every
        earlier one. Only an ADVANCE is attributed."""
        _peak(monkeypatch, 5000.0)
        _ratchet.note_test_memory("tests/x.py::test_the_hog")
        _peak(monkeypatch, 5000.0)  # unchanged: this test allocated nothing
        _ratchet.note_test_memory("tests/x.py::test_innocent")
        assert _ratchet.peak_test_hint()[1] == "tests/x.py::test_the_hog"

    def test_being_unable_to_measure_does_not_invent_a_hint(self, baseline, monkeypatch):
        _peak(monkeypatch, None)
        _ratchet.note_test_memory("tests/x.py::test_a")
        assert _ratchet.peak_test_hint() == (0.0, "")
