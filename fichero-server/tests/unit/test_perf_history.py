"""The performance ratchet must actually fire, and must actually tighten (#4439).

The rule it enforces: Fichero may not get slower, and it gets faster over time.
A guardrail nobody has watched fail is a guess, so these drive both directions —
a slower run fails, a faster run permanently lowers the bar — plus the edges
that would otherwise make it useless (never fires) or infuriating (fires on a
busy laptop).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perf_ratchet as _history  # noqa: E402

# Captured before any fixture stubs it out, so the one test that needs the REAL
# contention guard can still reach it.
_REAL_CONTENTION_GUARD = _history._another_perf_run_is_active


@pytest.fixture
def ratchet(tmp_path, monkeypatch):
    """Point the ratchet at throwaway files, on a machine it believes is quiet.

    The contention guard must be stubbed or these tests are not deterministic:
    it greps for any process matching `pytest.*tests/perf`, and this file's own
    invocation can match, as can any other perf run in flight. When it fires,
    `record` and `flush_session` correctly refuse to write anything — and every
    assertion here about what got written then fails for a reason that has
    nothing to do with the ratchet's logic. Observed live: 16 failures from a
    full-suite run happening in another window.

    The guard itself is exercised deliberately in TestConcurrentRuns, which
    stubs it the other way.
    """
    baseline = tmp_path / "perf_baseline.json"
    monkeypatch.setattr(_history, "BASELINE_PATH", baseline)
    monkeypatch.setattr(_history, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.delenv("FICHERO_PERF_NO_HISTORY", raising=False)
    monkeypatch.setattr(_history, "_another_perf_run_is_active", lambda: False)
    return baseline


def _seed(path: Path, name: str, ms: float) -> None:
    path.write_text(
        json.dumps({name: {"ms": ms, "commit": "seed", "note": "seed"}}), encoding="utf-8"
    )


def _best(path: Path, name: str) -> float:
    return json.loads(path.read_text(encoding="utf-8"))[name]["ms"]


class TestItMayNotGetSlower:
    def test_a_slower_run_fails_even_though_it_is_inside_the_budget(self, ratchet):
        """The #4439 defect: 0.4s -> 3.9s, under the 4s budget, must still fail."""
        _seed(ratchet, "entities.list.full", 400.0)
        with pytest.raises(AssertionError) as excinfo:
            _history.record("entities.list.full", 3900.0)
        message = str(excinfo.value)
        assert "RATCHET, not a budget" in message
        assert "400.0 ms" in message

    def test_the_failure_says_how_to_accept_a_real_slowdown(self, ratchet):
        """A guardrail with no stated way out gets bypassed by deleting it."""
        _seed(ratchet, "claims.list", 100.0)
        with pytest.raises(AssertionError) as excinfo:
            _history.record("claims.list", 1000.0)
        message = str(excinfo.value)
        assert "perf_baseline.json" in message
        assert "what bought the time" in message

    def test_a_regression_does_not_become_the_new_baseline(self, ratchet):
        """The whole point: the bar must never drift upward on its own."""
        _seed(ratchet, "claims.list", 100.0)
        with pytest.raises(AssertionError):
            _history.record("claims.list", 5000.0)
        assert _best(ratchet, "claims.list") == 100.0

    def test_many_small_slowdowns_cannot_creep_past_it(self, ratchet):
        """Fifty accepted 5% slips are a 12x slowdown. Measured against BEST,
        not against last run, so the creep has nowhere to hide."""
        _seed(ratchet, "claims.list", 100.0)
        for _ in range(20):
            _history.record("claims.list", 120.0)  # inside jitter, never tightens
        assert _best(ratchet, "claims.list") == 100.0
        with pytest.raises(AssertionError):
            _history.record("claims.list", 140.0)


class TestItGetsFasterOverTime:
    def test_a_faster_run_tightens_the_bar(self, ratchet):
        _seed(ratchet, "documents.list", 1000.0)
        _history.record("documents.list", 400.0)
        assert _best(ratchet, "documents.list") == 400.0

    def test_the_tightened_bar_is_then_enforced(self, ratchet):
        _seed(ratchet, "documents.list", 1000.0)
        _history.record("documents.list", 400.0)
        with pytest.raises(AssertionError):
            _history.record("documents.list", 900.0)  # was fine before, not now

    def test_a_marginal_improvement_does_not_chase_the_luckiest_sample(self, ratchet):
        """Chasing every 1% win would make every other machine fail forever."""
        _seed(ratchet, "documents.list", 1000.0)
        _history.record("documents.list", 990.0)
        assert _best(ratchet, "documents.list") == 1000.0


class TestItDoesNotCryWolf:
    def test_ordinary_jitter_passes(self, ratchet):
        """Not raising IS the point — but a test with no visible assertion
        looks identical to a dead one, so also confirm the baseline held
        (neither treated as a regression nor accidentally tightened)."""
        _seed(ratchet, "documents.list", 200.0)
        _history.record("documents.list", 260.0)  # 1.3x — a busy machine
        assert _best(ratchet, "documents.list") == 200.0

    def test_a_tiny_measurement_is_never_a_regression(self, ratchet):
        _seed(ratchet, "batch_cache_key", 2.0)
        _history.record("batch_cache_key", 20.0)  # 10x, but 20 ms — meaningless
        assert _best(ratchet, "batch_cache_key") == 2.0

    def test_the_jitter_allowance_does_not_accumulate(self, ratchet):
        """Tolerance is measured against BEST forever, not against last run."""
        _seed(ratchet, "claims.list", 100.0)
        _history.record("claims.list", 130.0)
        _history.record("claims.list", 130.0)
        assert _best(ratchet, "claims.list") == 100.0


class TestItSurvivesItsOwnFiles:
    def test_a_first_run_sets_the_baseline(self, ratchet):
        _history.record("brand.new", 1234.0)
        assert _best(ratchet, "brand.new") == 1234.0

    def test_each_measurement_keeps_its_own_bar(self, ratchet):
        _history.record("a.thing", 100.0)
        _history.record("b.thing", 5000.0)
        assert _best(ratchet, "a.thing") == 100.0
        assert _best(ratchet, "b.thing") == 5000.0

    def test_a_corrupt_baseline_fails_loudly_rather_than_silently_resetting(self, ratchet):
        """A ratchet that quietly starts over is not a ratchet."""
        ratchet.write_text("{ not json", encoding="utf-8")
        with pytest.raises(AssertionError) as excinfo:
            _history.record("claims.list", 100.0)
        assert "restore it from git" in str(excinfo.value)

    def test_every_run_is_logged_including_the_failures(self, ratchet):
        _seed(ratchet, "claims.list", 100.0)
        _history.record("claims.list", 110.0)
        with pytest.raises(AssertionError):
            _history.record("claims.list", 900.0)
        rows = [
            json.loads(line)
            for line in _history.HISTORY_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [r["verdict"] for r in rows] == ["ok", "REGRESSION"]


class TestTheEscapeHatch:
    def test_a_thrashing_machine_records_nothing_at_all(self, ratchet, monkeypatch):
        """Neither a bad number nor a lucky one may reach the baseline."""
        _seed(ratchet, "claims.list", 100.0)
        monkeypatch.setenv("FICHERO_PERF_NO_HISTORY", "1")
        _history.record("claims.list", 99999.0)
        _history.record("claims.list", 1.0)
        assert _best(ratchet, "claims.list") == 100.0


class TestConcurrentRuns:
    """The gate's perf leg and a direct run can execute at the same time."""

    def test_a_second_writer_cannot_corrupt_the_ratchet(self, ratchet):
        """Observed live: two pytest processes on the same baseline file.

        A plain write can interleave and truncate. os.replace is atomic, so a
        reader sees the old file or the new one — never a half-written one, and
        never a silently absent guardrail.
        """
        _history.record("a.thing", 100.0)
        _history.record("b.thing", 200.0)
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert set(data) == {"a.thing", "b.thing"}, "a write dropped another entry"

    def test_no_temp_files_are_left_behind(self, ratchet):
        _history.record("a.thing", 100.0)
        leftovers = list(ratchet.parent.glob("*.tmp"))
        assert not leftovers, f"atomic write leaked temp files: {leftovers}"

    def test_a_contended_run_records_nothing(self, ratchet, monkeypatch):
        """A number measured while another perf run competes is unreliable, and
        a ratchet keeps its numbers forever — so it must not keep this one."""
        _seed(ratchet, "claims.list", 100.0)
        monkeypatch.setattr(_history, "_another_perf_run_is_active", lambda: True)
        _history.record("claims.list", 9999.0)   # would fail if it were judged
        _history.record("claims.list", 1.0)      # would tighten if it were kept
        assert _best(ratchet, "claims.list") == 100.0

    def test_being_unable_to_tell_does_not_block_the_suite(self, ratchet, monkeypatch):
        """pgrep missing or failing must not stop perf from running at all.

        Calls the guard DIRECTLY. Going through `record` would prove nothing:
        the fixture stubs the guard out to keep these tests deterministic, so a
        broken pgrep would never be reached and the test would pass while
        checking nothing.
        """
        def _boom(*_args, **_kwargs):
            raise OSError("pgrep unavailable")
        monkeypatch.setattr(_history.subprocess, "run", _boom)
        assert _REAL_CONTENTION_GUARD() is False

        # ...and the suite still records normally when it cannot tell.
        _history.record("claims.list", 100.0)
        assert _best(ratchet, "claims.list") == 100.0


class TestEveryTestIsTimed:
    """The automatic path: durations collected in memory, compared once."""

    @pytest.fixture(autouse=True)
    def _clear(self):
        _history._session.clear()
        yield
        _history._session.clear()

    def test_a_fast_test_is_not_recorded_at_all(self, ratchet):
        """Most of ~7,500 tests run in single-digit ms where noise dwarfs any
        real change. Recording them would be thousands of meaningless bars."""
        _history.note_test_duration("tests/x.py::test_quick", 0.001)
        assert _history.flush_session() == []
        assert not ratchet.exists()

    def test_a_slow_test_gets_a_bar_then_is_held_to_it(self, ratchet):
        _history.note_test_duration("tests/x.py::test_slow", 0.500)
        assert _history.flush_session() == []
        assert _best(ratchet, "test::tests/x.py::test_slow") == 500.0

        _history.note_test_duration("tests/x.py::test_slow", 5.000)
        regressions = _history.flush_session()
        assert len(regressions) == 1
        assert "10.0x" in regressions[0]

    def test_a_regression_does_not_overwrite_the_bar(self, ratchet):
        _history.note_test_duration("tests/x.py::test_slow", 0.500)
        _history.flush_session()
        _history.note_test_duration("tests/x.py::test_slow", 5.000)
        _history.flush_session()
        assert _best(ratchet, "test::tests/x.py::test_slow") == 500.0

    def test_getting_faster_tightens_the_bar(self, ratchet):
        _history.note_test_duration("tests/x.py::test_slow", 1.000)
        _history.flush_session()
        _history.note_test_duration("tests/x.py::test_slow", 0.400)
        assert _history.flush_session() == []
        assert _best(ratchet, "test::tests/x.py::test_slow") == 400.0

    def test_the_fastest_observation_in_a_session_wins(self, ratchet):
        """A retry or a parametrised case is judged on its best, as across runs."""
        _history.note_test_duration("tests/x.py::test_slow", 2.000)
        _history.note_test_duration("tests/x.py::test_slow", 0.400)
        _history.flush_session()
        assert _best(ratchet, "test::tests/x.py::test_slow") == 400.0

    def test_the_whole_session_is_written_once(self, ratchet, monkeypatch):
        """Per-test writes would shell out to git thousands of times."""
        calls = []
        real = _history.os.replace
        monkeypatch.setattr(_history.os, "replace",
                            lambda a, b: (calls.append(1), real(a, b))[1])
        for i in range(20):
            _history.note_test_duration(f"tests/x.py::test_{i}", 0.100)
        _history.flush_session()
        assert len(calls) == 1, f"expected one atomic write, got {len(calls)}"
