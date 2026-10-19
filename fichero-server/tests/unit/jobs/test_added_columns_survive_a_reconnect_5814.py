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


def _columns(db) -> set[str]:
    return {r[0] for r in db.execute_fetchall(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'")}


def test_opening_a_library_made_before_5634_adds_the_columns_without_any_read(db):
    jobs._ensure(db)
    _as_a_library_made_before_5634(db)
    assert "cleared_at" not in _columns(db)

    db._apply_added_jobs_columns()  # the open-time step, on the write connection

    assert {"target", "detail", "parent_id", "run_after", "watched", "cleared_at"} <= _columns(db)


def test_opening_a_library_with_no_jobs_table_makes_none(db):
    db.execute("DROP TABLE IF EXISTS jobs")

    db._apply_added_jobs_columns()

    assert not _columns(db)


def test_a_column_that_cannot_be_added_is_logged_once_and_the_list_still_reads(db, monkeypatch, caplog):
    jobs._ensure(db)
    _as_a_library_made_before_5634(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, created_at, finished_at) "
               "VALUES ('j1', 'find-lines', 'p1', 'failed', 1, now(), now())")
    monkeypatch.setattr(jobs, "_ADDED_COLUMNS", ("ALTER TABLE no_such_table ADD COLUMN IF NOT EXISTS x TEXT",))
    monkeypatch.setattr(jobs, "_ALTER_FAILURES_LOGGED", set())
    db._jobs_columns_on = None

    with caplog.at_level("ERROR", logger=jobs.logger.name):
        for _ in range(3):
            listed = jobs.snapshot(db)

    assert [row["id"] for row in listed] == ["j1"]  # every failed job is listed: nothing can be marked cleared
    assert len([r for r in caplog.records if "could not apply" in r.getMessage()]) == 1


def test_the_columns_added_at_open_are_checkpointed_not_left_in_the_wal(db, monkeypatch):
    jobs._ensure(db)
    _as_a_library_made_before_5634(db)
    seen: list[str] = []
    real = db.conn

    class Spy:
        def execute(self, sql, *args):
            seen.append(sql)
            return real.execute(sql, *args)

    monkeypatch.setattr(db, "conn", Spy())

    db._apply_added_jobs_columns()
    assert "CHECKPOINT" in seen and seen.index("CHECKPOINT") > max(i for i, q in enumerate(seen) if "ALTER TABLE jobs" in q)

    seen.clear()
    db._apply_added_jobs_columns()  # nothing to add the second time: no checkpoint
    assert "CHECKPOINT" not in seen
