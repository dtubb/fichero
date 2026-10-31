"""#6298: a failed job logs its full traceback, not just the exception message."""

from __future__ import annotations

import logging


from fichero_server.execution import jobs


def test_a_failed_job_logs_traceback(caplog, db, jobs_run_by_the_test, monkeypatch):
    """A job that raises TypeError should log with exc_info=True in the warning record.

    This test verifies the fix for #6298 where a failed job did not log its full traceback.
    The original code at jobs.py:3701 used logger.warning without exc_info=True.
    """

    # Create a mock job that will raise a TypeError (like the reported bug)
    def fail_with_type_error(_db, subject):
        raise TypeError("'>' not supported between instances of 'str' and 'int'")

    # Register it as a test kind
    jobs.register_kind("test-fail", run=fail_with_type_error, model=None)

    try:
        # Enqueue a job that will fail
        job_id = jobs.enqueue(db, "test-fail", "subject-xyz")

        # Get the row for our job
        row = db.execute_fetchone("SELECT * FROM jobs WHERE id = ?", [job_id])

        # Get the lane
        lane = jobs._scheduler.lanes["local-ml"]

        # Patch wake to prevent thread spawning (jobs_run_by_the_test does this too, but we need it explicit)
        monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)

        # Run the job through _run (the method that has the exception handling with exc_info)
        with caplog.at_level(logging.WARNING, logger="fichero_server.execution.jobs"):
            jobs._scheduler._run(lane, db, db, row, None)

        # Check that there's a warning about the failed job
        log_text = caplog.text
        assert f"job {job_id}" in log_text and "failed" in log_text, (
            f"Expected job failure log, got: {log_text}"
        )

        # Find the log record that corresponds to our job failure
        job_fail_records = [
            r
            for r in caplog.records
            if "job" in r.getMessage() and "failed" in r.getMessage()
        ]
        assert len(job_fail_records) >= 1, (
            f"Expected at least one job failure log, got: {[r.getMessage() for r in caplog.records]}"
        )

        # The failure log should have exc_info set (the traceback) - this is the fix for #6298
        failure_log = job_fail_records[0]
        assert failure_log.exc_info is not None, (
            "Job failure log should have exc_info set to capture the traceback"
        )
        assert failure_log.exc_info[0] is TypeError, (
            "exc_info should contain the exception type"
        )

    finally:
        if "test-fail" in jobs.KINDS:
            del jobs.KINDS["test-fail"]
