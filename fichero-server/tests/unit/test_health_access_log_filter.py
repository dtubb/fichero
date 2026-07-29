"""#1000 — uvicorn access-log filter that drops /api/health poll spam.

The SwiftUI app polls /api/health continuously; logging every poll buries
the lines that matter when diagnosing a real backend problem.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero_server.api.main import _HealthAccessLogFilter  # noqa: E402


def _access_record(path: str) -> logging.LogRecord:
    """Mimic a uvicorn.access record: args = (client, method, path, ver, status)."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %s',
        args=("127.0.0.1:50000", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_filter_drops_plain_health_poll():
    assert _HealthAccessLogFilter().filter(_access_record("/api/health")) is False


def test_filter_drops_health_poll_with_query():
    f = _HealthAccessLogFilter()
    assert f.filter(_access_record("/api/health?library_path=/x")) is False


def test_filter_keeps_other_endpoints():
    f = _HealthAccessLogFilter()
    assert f.filter(_access_record("/api/documents")) is True
    assert f.filter(_access_record("/api/workflows/tools")) is True
    # A path that merely contains "health" elsewhere is not the poll.
    assert f.filter(_access_record("/api/library/health-report")) is True


def test_filter_keeps_records_without_request_args():
    # Non-access records (plain messages, no tuple args) pass through.
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "startup", None, None)
    assert _HealthAccessLogFilter().filter(rec) is True
