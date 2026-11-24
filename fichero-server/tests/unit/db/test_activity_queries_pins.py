"""Pins what the Activity pane's read-only queries return today (`db/activity_queries.py`).

Real `db` fixture, rows written by plain INSERTs (no model, no network, no library outside the test package).
These are characterisation tests: they state the current behaviour, not a spec ruling.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.db import activity_queries as q
from fichero_server.execution import jobs

NOW = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def _job(db, job_id, kind, state, *, subject="s", created=NOW, started=None, finished=None, parent=None, deleted=False):
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, finished_at, "
        "target, detail, parent_id, deleted_at) VALUES (?, ?, ?, ?, 0, 't', ?, ?, ?, 'local', NULL, ?, ?)",
        [job_id, kind, subject, state, created, started, finished, parent, NOW if deleted else None],
    )


def test_stage_rows_lists_live_jobs_of_the_kinds_asked_and_honours_since(db):
    jobs._ensure(db)
    _job(db, "a1", "embed-pin", "running", subject="page-1", created=NOW)
    _job(db, "a2", "embed-pin", "done", subject="page-2", created=EARLIER)
    _job(db, "a3", "other-pin", "waiting", subject="page-3", created=NOW)
    _job(db, "a4", "embed-pin", "waiting", subject="page-4", created=NOW, deleted=True)

    everything = q.stage_rows(db, ["embed-pin"], None)
    assert sorted(everything) == [("embed-pin", "done", "page-2"), ("embed-pin", "running", "page-1")]

    recent = q.stage_rows(db, ["embed-pin", "other-pin"], datetime(2026, 11, 21, tzinfo=timezone.utc))
    assert sorted(recent) == [("embed-pin", "running", "page-1"), ("other-pin", "waiting", "page-3")]

    assert q.stage_rows(db, ["no-such-kind-pin"], None) == []


def test_running_job_kinds_has_one_entry_per_running_job(db):
    jobs._ensure(db)
    _job(db, "r1", "kind-r-pin", "running")
    _job(db, "r2", "kind-r-pin", "running")
    _job(db, "r3", "kind-s-pin", "waiting")

    assert sorted(q.running_job_kinds(db)) == ["kind-r-pin", "kind-r-pin"]

    _job(db, "r4", "kind-empty-pin", "done")
    assert "kind-empty-pin" not in q.running_job_kinds(db)


def test_job_times_returns_the_four_fields_or_none_when_there_is_no_job(db):
    jobs._ensure(db)
    start = datetime(2026, 11, 23, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 11, 23, 9, 2, tzinfo=timezone.utc)
    _job(db, "t1", "kind-t-pin", "done", created=NOW, started=start, finished=end)

    got = q.job_times(db, "t1")
    assert got is not None
    state, created, started, finished = got
    assert state == "done"
    assert created.replace(tzinfo=timezone.utc) == NOW
    assert started.replace(tzinfo=timezone.utc) == start
    assert finished.replace(tzinfo=timezone.utc) == end

    assert q.job_times(db, "no-such-job-pin") is None


def test_parent_kind_and_id_names_the_parent_and_is_none_without_one(db):
    jobs._ensure(db)
    _job(db, "p1", "parent-pin", "running")
    _job(db, "c1", "child-pin", "running", parent="p1")
    _job(db, "orphan", "child-pin", "running")

    assert q.parent_kind_and_id(db, "c1") == ("p1", "parent-pin")
    assert q.parent_kind_and_id(db, "orphan") is None
    assert q.parent_kind_and_id(db, "no-such-job-pin") is None


def test_run_workflow_name_is_the_name_else_the_id_and_none_for_no_run(db):
    db.execute(
        "INSERT INTO workflowrunrecords (id, workflow_id, workflow_name, status, started_at) VALUES (?, ?, ?, 'done', ?)",
        ["run-named-pin", "wf-id-pin", "Named workflow", NOW],
    )
    db.execute(
        "INSERT INTO workflowrunrecords (id, workflow_id, workflow_name, status, started_at) VALUES (?, ?, NULL, 'done', ?)",
        ["run-unnamed-pin", "wf-id-only-pin", NOW],
    )

    assert q.run_workflow_name(db, "run-named-pin") == "Named workflow"
    assert q.run_workflow_name(db, "run-unnamed-pin") == "wf-id-only-pin"
    assert q.run_workflow_name(db, "no-such-run-pin") is None
