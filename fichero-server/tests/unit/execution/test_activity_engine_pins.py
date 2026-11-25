"""Pins what the Activity engine's job helpers do today (`execution/jobs.py`).

Characterisation tests: they state the current behaviour, not a spec ruling. Real `db` fixture, no network,
no real library, no files.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fichero_server.execution import jobs


def _finish(db, job_id: str, *, seconds: float, model: str | None = None) -> None:
    """Mark a queued job done, started `seconds` before it finished (and on `model`, when given)."""
    finished = datetime.now(timezone.utc).replace(tzinfo=None)
    started = finished - timedelta(seconds=seconds)
    db.execute(
        "UPDATE jobs SET state = 'done', started_at = ?, finished_at = ?, model = COALESCE(?, model) WHERE id = ?",
        [started, finished, model, job_id],
    )


def test_is_set_aside_recognises_the_two_set_aside_reasons_and_nothing_else():
    assert jobs.is_set_aside("Stopped 2 times by the engine stopping; set aside. Resume to carry on.")
    assert jobs.is_set_aside("Stopped 1 time by the engine stopping")
    assert jobs.is_set_aside("Interrupted 3 times")
    assert not jobs.is_set_aside("Cancelled by the person")
    # A missing reason, or an empty one, is not a set-aside job.
    assert not jobs.is_set_aside(None)
    assert not jobs.is_set_aside("")


def test_seconds_per_item_is_the_median_of_the_latest_done_jobs_and_none_when_none_is_measured(db):
    jobs._ensure(db)
    assert jobs.seconds_per_item(db, "pin-kind") is None

    # Three done jobs of one kind: 1, 3 and 5 seconds. The median is the middle one.
    for subject, seconds in (("a", 1.0), ("b", 5.0), ("c", 3.0)):
        _finish(db, jobs.enqueue(db, "pin-kind", subject), seconds=seconds)
    assert jobs.seconds_per_item(db, "pin-kind") == 3.0

    # A job still queued is not measured, and nor is another kind's job.
    jobs.enqueue(db, "pin-kind", "queued-only")
    _finish(db, jobs.enqueue(db, "other-kind", "x"), seconds=99.0)
    assert jobs.seconds_per_item(db, "pin-kind") == 3.0


def test_details_of_kinds_returns_each_row_of_those_kinds_oldest_first_with_its_parsed_detail(db):
    jobs._ensure(db)
    jobs.enqueue(db, "pin-detail-a", "one", detail=json.dumps({"n": 1}))
    jobs.enqueue(db, "pin-detail-b", "two", detail=json.dumps({"n": 2}))
    jobs.enqueue(db, "pin-detail-a", "three")  # no detail written: it reads back as {}

    rows = jobs.details_of_kinds(db, ("pin-detail-a", "pin-detail-b"))
    assert [detail for _, detail in rows] == [{"n": 1}, {"n": 2}, {}]
    assert all(at.tzinfo is not None for at, _ in rows)  # created_at comes back in UTC

    # A kind with no rows gives an empty list.
    assert jobs.details_of_kinds(db, ("pin-no-such-kind",)) == []


def test_finished_seconds_counts_only_done_jobs_of_the_model_with_or_without_its_runtime_prefix(db):
    jobs._ensure(db)
    assert jobs.finished_seconds(db, "kraken-x") == []

    _finish(db, jobs.enqueue(db, "pin-model", "p1"), seconds=2.0, model="kraken:kraken-x")
    _finish(db, jobs.enqueue(db, "pin-model", "p2"), seconds=4.0, model="kraken-x")
    # A queued job of the model, and a done job of another model, are not counted.
    jobs.enqueue(db, "pin-model", "p3")
    _finish(db, jobs.enqueue(db, "pin-model", "p4"), seconds=9.0, model="kraken-y")

    times = jobs.finished_seconds(db, "kraken-x")
    assert sorted(times) == [2.0, 4.0]
    # The limit caps how many of the most recent are returned.
    assert len(jobs.finished_seconds(db, "kraken-x", limit=1)) == 1


def test_latest_job_id_is_the_newest_job_for_a_kind_and_subject_and_none_when_there_is_none(db):
    jobs._ensure(db)
    assert jobs.latest_job_id(db, "pin-latest", "doc-1") is None

    job = jobs.enqueue(db, "pin-latest", "doc-1")
    assert jobs.latest_job_id(db, "pin-latest", "doc-1") == job
    # A different subject is a different job.
    assert jobs.latest_job_id(db, "pin-latest", "doc-2") is None
