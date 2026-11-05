"""`run.fail.unexpected-is-logged-whole` (#6354): a run that dies in a node writes one ERROR with the run id and its traceback."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_the_catch_all_logs_the_whole_traceback_once_with_the_run_id(monkeypatch, caplog):
    """`run.fail.unexpected-is-logged-whole`: a run that dies in a node writes ONE ERROR to the engine log with the run id and the
    traceback (`exc_info`), driven through the real background runner."""
    import tempfile

    from fichero_server.db import Database
    from tests.unit.workflows.test_run_step_failure_legibility import _drive_failing_run

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "fichero.duckdb")
        try:
            with caplog.at_level(logging.ERROR):
                await _drive_failing_run(monkeypatch, db, "run-log-1")
        finally:
            db.close()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and "run-log-1" in r.getMessage()]
    assert len(errors) == 1 and errors[0].exc_info and errors[0].exc_info[0] is RuntimeError
