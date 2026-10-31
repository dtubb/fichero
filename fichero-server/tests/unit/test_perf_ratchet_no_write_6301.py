"""The perf ratchet writes its baselines only when FICHERO_PERF_TIGHTEN=1 (Fixes #6301)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perf_ratchet as _ratchet  # noqa: E402


@pytest.fixture
def ratchet(tmp_path, monkeypatch):
    """Point the ratchet at throwaway files, baseline always writable by tests."""
    baseline = tmp_path / "perf_baseline.json"
    monkeypatch.setattr(_ratchet, "BASELINE_PATH", baseline)
    monkeypatch.setattr(_ratchet, "HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.delenv("FICHERO_PERF_NO_HISTORY", raising=False)
    monkeypatch.setattr(_ratchet, "_another_perf_run_is_active", lambda: False)
    # Clear any previous session state
    _ratchet._session.clear()
    _ratchet._query_session.clear()
    return baseline


def _baseline_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


class TestTighteningControlledByEnvVar:
    """With FICHERO_PERF_TIGHTEN unset, the baseline is never written."""

    def test_first_measurement_does_not_write_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """A first measurement leaves the baseline file unchanged (doesn't create it)."""
        assert not ratchet.exists()
        _ratchet.record("entities.list.full", 100.0)
        assert not ratchet.exists(), "baseline written with FICHERO_PERF_TIGHTEN unset"

    def test_faster_measurement_does_not_tighten_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """A faster measurement leaves the committed baseline untouched."""
        # Seed the baseline first (simulating a committed baseline)
        ratchet.write_text(json.dumps({"entities.list.full": {"ms": 200.0, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        initial_content = _baseline_bytes(ratchet)

        # Now run a faster measurement
        _ratchet.record("entities.list.full", 100.0)

        # Baseline should be unchanged
        assert _baseline_bytes(ratchet) == initial_content, "baseline was tightened with FICHERO_PERF_TIGHTEN unset"

    def test_query_count_first_measurement_does_not_write_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """A first query-count measurement leaves the baseline file unchanged."""
        assert not ratchet.exists()
        _ratchet.note_query_count("queries.GET./api/documents", 5)
        _ratchet.flush_query_session()
        assert not ratchet.exists(), "baseline written with FICHERO_PERF_TIGHTEN unset"

    def test_query_count_faster_measurement_does_not_tighten_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """A faster query-count measurement leaves the committed baseline untouched."""
        # Seed the baseline with a count entry
        ratchet.write_text(json.dumps({"queries.GET./api/documents": {"count": 10, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        initial_content = _baseline_bytes(ratchet)

        # Now run a faster measurement
        _ratchet.note_query_count("queries.GET./api/documents", 3)
        _ratchet.flush_query_session()

        # Baseline should be unchanged
        assert _baseline_bytes(ratchet) == initial_content, "count baseline was tightened with FICHERO_PERF_TIGHTEN unset"

    def test_session_flush_first_measurement_does_not_write_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """flush_session() with no baseline writes nothing when tightening not set."""
        assert not ratchet.exists()
        _ratchet.note_test_duration("tests/x.py::test_a", 0.500)
        _ratchet.flush_session()
        assert not ratchet.exists(), "baseline written with FICHERO_PERF_TIGHTEN unset"

    def test_session_flush_faster_measurement_does_not_write_baseline_when_tightening_not_set(self, ratchet, monkeypatch):
        """flush_session() with a faster measurement leaves baseline unchanged."""
        # Seed with existing entry
        ratchet.write_text(json.dumps({"test::tests/x.py::test_a": {"ms": 500.0, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        initial_content = _baseline_bytes(ratchet)

        # Run faster session
        _ratchet.note_test_duration("tests/x.py::test_a", 0.200)
        _ratchet.flush_session()

        # Baseline unchanged
        assert _baseline_bytes(ratchet) == initial_content, "session baseline was written with FICHERO_PERF_TIGHTEN unset"


class TestTighteningAllowedWhenSet:
    """With FICHERO_PERF_TIGHTEN=1, the baseline is written as expected."""

    def test_first_measurement_writes_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """A first measurement creates the baseline when FICHERO_PERF_TIGHTEN=1."""
        assert not ratchet.exists()
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.record("entities.list.full", 100.0)
        assert ratchet.exists()
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["entities.list.full"]["ms"] == 100.0

    def test_faster_measurement_tightens_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """A faster measurement tightens the baseline when FICHERO_PERF_TIGHTEN=1."""
        ratchet.write_text(json.dumps({"entities.list.full": {"ms": 200.0, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.record("entities.list.full", 100.0)
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["entities.list.full"]["ms"] == 100.0
        assert "tightened from" in data["entities.list.full"]["note"]

    def test_query_count_first_measurement_writes_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """A first query-count measurement creates the baseline when FICHERO_PERF_TIGHTEN=1."""
        assert not ratchet.exists()
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.note_query_count("queries.GET./api/documents", 5)
        _ratchet.flush_query_session()
        assert ratchet.exists()
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["queries.GET./api/documents"]["count"] == 5

    def test_query_count_faster_measurement_tightens_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """A faster query-count measurement tightens the baseline when FICHERO_PERF_TIGHTEN=1."""
        ratchet.write_text(json.dumps({"queries.GET./api/documents": {"count": 10, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.note_query_count("queries.GET./api/documents", 3)
        _ratchet.flush_query_session()
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["queries.GET./api/documents"]["count"] == 3
        assert "tightened from" in data["queries.GET./api/documents"]["note"]

    def test_session_flush_writes_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """flush_session() writes baseline when FICHERO_PERF_TIGHTEN=1."""
        assert not ratchet.exists()
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.note_test_duration("tests/x.py::test_a", 0.500)
        _ratchet.flush_session()
        assert ratchet.exists()
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["test::tests/x.py::test_a"]["ms"] == 500.0

    def test_session_flush_tightens_baseline_when_tightening_is_set(self, ratchet, monkeypatch):
        """flush_session() tightens baseline when FICHERO_PERF_TIGHTEN=1."""
        ratchet.write_text(json.dumps({"test::tests/x.py::test_a": {"ms": 500.0, "commit": "seed", "note": "seed"}}), encoding="utf-8")
        monkeypatch.setenv("FICHERO_PERF_TIGHTEN", "1")
        _ratchet.note_test_duration("tests/x.py::test_a", 0.200)
        _ratchet.flush_session()
        data = json.loads(ratchet.read_text(encoding="utf-8"))
        assert data["test::tests/x.py::test_a"]["ms"] == 200.0
        assert "tightened from" in data["test::tests/x.py::test_a"]["note"]


class TestReportingWithNoBaseline:
    """When there's no baseline and FICHERO_PERF_TIGHTEN is not set, report correctly."""

    def test_first_timing_measurement_reports_no_baseline(self, ratchet, monkeypatch, capsys):
        """A first timing measurement reports correctly but doesn't write baseline."""
        # Clear history disable to see the actual message
        monkeypatch.delenv("FICHERO_PERF_NO_HISTORY", raising=False)
        _ratchet.record("entities.list.full", 100.0)
        captured = capsys.readouterr()
        # Should report that baseline is set, but not write it
        assert "baseline set" in captured.out

    def test_first_query_count_measurement_reports_no_baseline(self, ratchet, monkeypatch, capsys):
        """A first query-count measurement reports correctly but doesn't write."""
        _ratchet.note_query_count("queries.GET./api/documents", 5)
        regressions = _ratchet.flush_query_session()
        assert regressions == []
        assert not ratchet.exists()
