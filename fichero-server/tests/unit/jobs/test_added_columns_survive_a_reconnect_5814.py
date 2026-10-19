"""A library made before #5634 has no `jobs.cleared_at`; reading the jobs never errors on it (#5814, `activity.jobs-added-columns`).

The added columns were applied once per process per path, so a connection that came back after an invalidated one
(or a file at the same path made without them) was never altered, and `/api/activity/jobs` failed on every poll
with "column cleared_at not found" (352 times in one log).
"""
from __future__ import annotations

from fichero_server.execution import jobs


def _as_a_library_made_before_5634(db):
    """The jobs table as an older release left it: no added columns."""
    db.execute("DROP TABLE jobs")
    db.execute(jobs._SCHEMA)


def test_a_library_made_before_5634_reads_its_jobs_without_error(db):
    jobs._ensure(db)
    _as_a_library_made_before_5634(db)
    db._jobs_columns_on = None  # a library opened afresh: nothing ensured on this connection

    assert jobs.snapshot(db) == []


def test_a_reconnect_after_an_invalidated_connection_gets_the_columns_again(db):
    jobs._ensure(db)
    jobs.snapshot(db)  # ensured on the first connection
    _as_a_library_made_before_5634(db)  # the file came back without the ALTER

    db._reconnect_after_invalidated()

    assert jobs.snapshot(db) == []
    assert db.execute_fetchone(
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'jobs' AND column_name = 'cleared_at'"
    ) == (1,)


def test_the_columns_are_not_altered_again_on_every_read(db, monkeypatch):
    jobs._ensure(db)
    seen: list[str] = []
    real = db.execute
    monkeypatch.setattr(db, "execute", lambda sql, params=None: (seen.append(sql), real(sql, params))[1])

    jobs.snapshot(db)

    assert not [sql for sql in seen if "ALTER TABLE jobs" in sql]
