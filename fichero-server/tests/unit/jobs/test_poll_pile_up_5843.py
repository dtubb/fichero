"""#5843: polls arrived faster than they finished and piled up beside Kraken. One query in flight per poll route,
and a jobs table of any size answers the Activity snapshot at once."""
from __future__ import annotations

import asyncio
import logging
import time

from fichero_server.core import single_flight as single_flight_module
from fichero_server.core.single_flight import single_flight
from fichero_server.execution import jobs


def test_concurrent_polls_run_one_query_and_the_others_get_its_answer():
    runs = []

    @single_flight
    async def poll(key: str = "a") -> dict:
        runs.append(key)
        await asyncio.sleep(0.2)
        return {"key": key}

    async def go():
        first = [asyncio.ensure_future(poll(key="a")) for _ in range(12)]
        other = asyncio.ensure_future(poll(key="b"))
        return await asyncio.gather(*first, other)

    answers = asyncio.run(go())
    assert runs == ["a", "b"]  # twelve callers of "a": one query; "b" is its own
    assert all(a == {"key": "a"} for a in answers[:12]) and answers[12] == {"key": "b"}
    assert poll.single_flight_stats["served"] == 11
    asyncio.run(poll(key="a"))  # a poll after the first finished runs again
    assert runs == ["a", "b", "a"]


def test_a_sync_route_runs_in_a_thread_and_a_slow_poll_is_logged_with_its_callers(caplog, monkeypatch):
    monkeypatch.setattr(single_flight_module, "SLOW_MS", 50)

    @single_flight
    def poll(key: str = "a") -> list:
        time.sleep(0.15)
        return [1, 2, 3]

    async def go():
        return await asyncio.gather(poll(key="a"), poll(key="a"))

    with caplog.at_level(logging.INFO, logger=single_flight_module.__name__):
        assert asyncio.run(go()) == [[1, 2, 3], [1, 2, 3]]
    line = next(r.getMessage() for r in caplog.records if "poll" in r.getMessage())
    assert "test_poll_pile_up_5843.poll" in line and "3 rows" in line and "1 callers" in line


def test_a_ten_thousand_row_jobs_table_is_read_as_one_row_per_group(db):
    jobs._ensure(db)
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, created_at, started_by) "
        "SELECT 'w' || i, CASE WHEN i % 2 = 0 THEN 'make-thumbnail' ELSE 'embed-for-search' END, 'doc' || i, "
        "CASE WHEN i < 9990 THEN 'waiting' WHEN i < 9995 THEN 'running' ELSE 'failed' END, "
        "now() - to_seconds(10000 - i), 'automatic' FROM range(10000) t(i)")
    jobs.snapshot(db)  # the first call may add columns
    started = time.monotonic()
    rows = jobs.snapshot(db)
    assert time.monotonic() - started < 1.0  # generous: the shape below is the point; a full fetch of 10k rows is not
    queue = [r for r in rows if r["state"] != "failed"]
    # One row per kind (#5839): its running and waiting jobs together, Running while one is really going.
    assert sorted(r["kind"] for r in queue) == ["embed-for-search", "make-thumbnail"]
    assert sum(r["count"] for r in queue) == 9995 and all(r["state"] == "running" for r in queue)
    assert {r["id"] for r in queue} == {"waiting:make-thumbnail", "waiting:embed-for-search"}
    assert len([r for r in rows if r["state"] == "failed"]) == 5


def test_the_real_snapshot_sql_runs_on_duckdb_with_watched_and_person_started_jobs(db):
    """The ordering reads `watched` and `started_by`, which the select list does not carry (review 269: a DISTINCT
    over the select list made DuckDB refuse the ORDER BY, and every Activity poll would have failed)."""
    jobs._ensure(db)
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, created_at, started_by, watched) VALUES "
        "('bulk', 'make-thumbnail', 'a', 'waiting', now() - to_seconds(30), 'automatic', FALSE), "
        "('mine', 'make-thumbnail', 'b', 'waiting', now() - to_seconds(20), 'recipe', FALSE), "
        "('look', 'make-thumbnail', 'c', 'waiting', now() - to_seconds(10), 'automatic', TRUE), "
        "('going', 'embed-for-search', 'd', 'running', now() - to_seconds(40), 'automatic', FALSE), "
        "('p1', 'nlp', 'e', 'paused', now() - to_seconds(5), 'automatic', FALSE)")
    rows = jobs.snapshot(db)
    thumbs = next(r for r in rows if r["kind"] == "make-thumbnail")
    assert thumbs["count"] == 3 and thumbs["subject"] == "c"  # the watched job stands for its kind: first in the lane
    assert thumbs["id"] == "waiting:make-thumbnail"
    assert next(r for r in rows if r["kind"] == "embed-for-search")["state"] == "running"  # fetched twice, listed once
    assert [r["kind"] for r in rows].count("embed-for-search") == 1
    assert next(r for r in rows if r["kind"] == "nlp")["state"] == "paused"
