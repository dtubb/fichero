"""Reviewer b23 (#6236): while one statement stays past the slow threshold, the watchdog reads duckdb_memory() once for it,
not every tick (each read can still fail a CHECKPOINT beside it); and a temp file DuckDB deletes mid-glob is skipped, never
an aborted tick."""
from __future__ import annotations

import time
from pathlib import Path

from fichero_server.db import busy_evidence


def test_held_versions_read_once_per_slow_statement(monkeypatch):
    reads = []
    monkeypatch.setattr(busy_evidence, "_check_held_versions", lambda alarmed: reads.append(1))
    monkeypatch.setattr(busy_evidence, "_check_spill", lambda alarmed: None)
    with busy_evidence.watch_statement("SELECT 1"):  # starts the watchdog thread if no earlier test did
        pass
    token = next(busy_evidence._tokens)
    busy_evidence._running[token] = (time.monotonic() - 3600, "SELECT slow", "test")
    try:
        time.sleep(3.5)  # three or more ticks with the one statement past the threshold
    finally:
        busy_evidence._running.pop(token, None)
    assert len(reads) == 1, f"{len(reads)} held-versions reads for one slow statement"


def test_a_temp_file_deleted_mid_glob_is_skipped(monkeypatch, tmp_path):
    (tmp_path / "kept.tmp").write_bytes(b"x" * 10)
    gone = tmp_path / "gone.tmp"
    real_glob = Path.glob

    def glob_then_delete(self, pattern):
        yield from real_glob(self, pattern)
        yield gone  # listed, then deleted by DuckDB before its stat

    monkeypatch.setattr(Path, "glob", glob_then_delete)
    monkeypatch.setattr(Path, "is_file", lambda self: True)  # it was a file when listed
    monkeypatch.setattr(busy_evidence, "_live_instances", lambda: [("k", None)])
    monkeypatch.setitem(busy_evidence._temp_dirs, "k", str(tmp_path))
    monkeypatch.setattr(busy_evidence, "SPILL_ALARM_BYTES", 5)
    alarmed: set[str] = set()
    busy_evidence._check_spill(alarmed)  # raised FileNotFoundError before
    assert "spill:k" in alarmed
