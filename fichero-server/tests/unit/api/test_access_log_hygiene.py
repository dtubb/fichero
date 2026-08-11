"""The steady-state access-log filter (Daniel, 2026-08-10: heartbeat 200s
"pollute our log every 2 seconds"). Failures and non-steady routes must
still log; the quiet set is exactly the enumerated read-only heartbeat."""

from __future__ import annotations

import logging

from fichero_server.__main__ import _QuietSteadyStateAccessLog


def _record(path: str, status) -> logging.LogRecord:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s", None, None)
    record.args = ("127.0.0.1", "GET", path, "1.1", status)
    return record


def test_steady_state_200s_are_quiet():
    f = _QuietSteadyStateAccessLog()
    for path in (
        "/api/health", "/api/registry", "/api/activity/stream",
        "/api/ingest/status/abc123", "/api/storage/thumbnail/xyz",
        "/api/storage/display/xyz",
    ):
        assert f.filter(_record(path, 200)) is False, path


def test_failures_on_noisy_paths_still_log():
    f = _QuietSteadyStateAccessLog()
    assert f.filter(_record("/api/health", 500)) is True
    assert f.filter(_record("/api/registry", 401)) is True


def test_everything_else_still_logs():
    f = _QuietSteadyStateAccessLog()
    assert f.filter(_record("/api/documents/abc", 200)) is True
    assert f.filter(_record("/api/documents/import", 200)) is True


def test_malformed_records_pass_through():
    f = _QuietSteadyStateAccessLog()
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "free-form", None, None)
    record.args = None
    assert f.filter(record) is True
