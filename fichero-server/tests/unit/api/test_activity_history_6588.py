"""`GET /api/activity/history` (#6588, spec `activity.window.bottom-panel`, decisions 22-25).

The Activity Monitor's graphs read one typed answer: pages done and failed, dollars and tokens per minute, the minutes' totals
per runtime, and today's spend by provider. Everything is derived from what the engine keeps (page jobs' `finished_at` and
`state`, and the calls' `detail["usage"]`); nothing is recorded for it.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs as job_queue


def _add(db, state, finished, *, kind="transcribe-page", parent="run1", usage=None, target=None):
    job_queue._ensure(db)
    detail = json.dumps({"usage": usage}) if usage else None
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, attempts, created_at, finished_at, parent_id, detail, target) "
        "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), kind, "p", state, finished, finished,
         parent, detail, target])


@pytest.fixture
def priced(monkeypatch):
    from fichero_server.llm import usage

    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})


def _minute(offset):
    return (utc_now().replace(second=30, microsecond=0) - timedelta(minutes=offset))


def test_an_empty_library_answers_all_zero_buckets(client):
    body = client.get("/api/activity/history?minutes=60").json()
    assert len(body["buckets"]) == 60
    starts = [b["start"] for b in body["buckets"]]
    assert starts == sorted(starts) and starts[0].endswith(("Z", "+00:00"))
    assert all(b["pages_done"] == b["pages_failed"] == b["tokens"] == 0 and b["spend_usd"] == 0.0 for b in body["buckets"])
    assert body["today_spend_usd"] == 0.0 and body["today_spend_by_provider"] == {}
    assert body["by_runtime"] == {}


def test_thirty_pages_over_ten_minutes_land_in_their_minutes(client, db):
    for i in range(30):
        _add(db, "done", _minute(1 + i % 10), usage=None, kind=f"k{i}")
    body = client.get("/api/activity/history?minutes=30").json()
    done = [b["pages_done"] for b in body["buckets"]]
    assert sum(done) == 30 and len(done) == 30
    assert done[-11:-1] == [3] * 10 and done[-1] == 0
    assert body["by_runtime"]["this-mac"] == 30


def test_failed_pages_are_counted_apart_and_runs_are_not_pages(client, db):
    _add(db, "done", _minute(2), kind="a")
    _add(db, "failed", _minute(2), kind="b")
    _add(db, "done", _minute(2), kind="workflow", parent=None)  # a run, not a page
    bucket = client.get("/api/activity/history?minutes=10").json()["buckets"][-3]
    assert (bucket["pages_done"], bucket["pages_failed"]) == (1, 1)


def test_a_priced_call_lands_in_its_minute_and_in_todays_total_by_provider(client, db, priced):
    when = utc_now() - timedelta(minutes=3)
    call = {"provider": "anthropic", "model": "m", "input_tokens": 1000, "output_tokens": 100, "place": "provider"}
    _add(db, "done", when, usage=[call])
    body = client.get("/api/activity/history?minutes=10").json()
    hits = [b for b in body["buckets"] if b["spend_usd"]]
    assert len(hits) == 1 and hits[0]["spend_usd"] == pytest.approx(0.002) and hits[0]["tokens"] == 1100
    assert body["by_runtime"]["cloud"] == 1
    if when.date() == utc_now().date():
        assert body["today_spend_by_provider"] == {"anthropic": pytest.approx(0.002)}
        assert body["today_spend_usd"] == pytest.approx(0.002)


def test_minutes_are_bounded(client):
    assert client.get("/api/activity/history?minutes=4").status_code == 422
    assert client.get("/api/activity/history?minutes=1441").status_code == 422
    assert len(client.get("/api/activity/history").json()["buckets"]) == 60
