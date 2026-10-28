"""The engine's RSS past a share of this Mac's memory, and DuckDB's spill past its threshold, each log one line once
(owner's north star: slow-path logging, #6236)."""
from __future__ import annotations

import logging
import threading

from fichero_server.core import duckdb_session
from fichero_server.db import Database, busy_evidence

GIB = 1024**3


def _said(caplog, words):
    return [r.getMessage() for r in caplog.records if words in r.getMessage()]


def test_rss_says_each_share_once(caplog, monkeypatch):
    monkeypatch.setattr(duckdb_session, "physical_memory_bytes", lambda: 16 * GIB)
    peaks = iter([2 * GIB, 5 * GIB, 6 * GIB, 13 * GIB, 13 * GIB])
    main = threading.current_thread()  # a watchdog already running (an earlier test's) must not take these
    monkeypatch.setattr(busy_evidence, "_peak_rss_bytes", lambda: next(peaks) if threading.current_thread() is main else 0)
    said: set[float] = set()
    with caplog.at_level(logging.WARNING, logger=busy_evidence.__name__):
        for _ in range(5):
            busy_evidence._check_rss(said)
    lines = _said(caplog, "engine RSS")
    assert len(lines) == 2, lines  # 5 GiB passes a quarter; 13 GiB passes three quarters (half said with it)
    assert "5.0 GiB" in lines[0] and "25%" in lines[0]
    assert "13.0 GiB" in lines[1] and "75%" in lines[1]


def test_spill_says_once_per_instance(caplog, monkeypatch, tmp_path):
    monkeypatch.setattr(busy_evidence, "SPILL_ALARM_BYTES", -1)  # any spill, even none, passes it
    db = Database(tmp_path / "spill.duckdb")
    try:
        alarmed: set[str] = set()
        with caplog.at_level(logging.WARNING, logger=busy_evidence.__name__):
            busy_evidence._check_spill(alarmed)
            busy_evidence._check_spill(alarmed)
        lines = [r.getMessage() for r in caplog.records  # this thread's: a running watchdog says it too, once
                 if r.threadName == threading.current_thread().name and "DuckDB spilled" in r.getMessage()]
        assert len([x for x in lines if "spill.duckdb" in x]) == 1, lines
    finally:
        db.close()
