"""A remote read's time queued and time run (`activity.resources.everything-measured`, decision 42, #6588).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. Acceptance: a cluster job of 40 min queued and 12 min run reads both.
Each shard is stamped when it is sent, first seen running and seen ended; the read sums them. Nothing measured is None.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fichero_server.remote_read import job


def _iso(t: datetime) -> str:
    return t.isoformat()


def test_forty_minutes_queued_and_twelve_run_read_both():
    t0 = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
    shards = {"0": {"state": "landed", "submitted_at": _iso(t0), "running_at": _iso(t0 + timedelta(minutes=40)),
                    "ended_at": _iso(t0 + timedelta(minutes=52))}}
    out = job.times(shards, price_per_hour_usd=None, now=t0 + timedelta(hours=2))
    assert out["queued_seconds"] == 40 * 60 and out["run_seconds"] == 12 * 60
    assert out["node_hours"] == round(12 / 60, 4) and out["cost_usd"] is None, "no price: no cost made up"


def test_shards_add_up_and_one_still_going_counts_to_now():
    t0 = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
    now = t0 + timedelta(minutes=30)
    shards = {
        "0": {"submitted_at": _iso(t0), "running_at": _iso(t0 + timedelta(minutes=5)), "ended_at": _iso(t0 + timedelta(minutes=15))},
        "1": {"submitted_at": _iso(t0), "running_at": _iso(t0 + timedelta(minutes=10)), "ended_at": None},  # running
        "2": {"submitted_at": _iso(t0), "running_at": None, "ended_at": None},  # still queued
    }
    out = job.times(shards, price_per_hour_usd=2.0, now=now)
    assert out["queued_seconds"] == (5 + 10 + 30) * 60
    assert out["run_seconds"] == (10 + 20) * 60
    assert out["cost_usd"] == round(0.5 * 2.0, 4), "half an hour run at $2 an hour"


def test_shards_sent_before_the_stamps_measure_nothing():
    out = job.times({"0": {"state": "landed"}}, price_per_hour_usd=3.0)
    assert out == {"queued_seconds": None, "run_seconds": None, "node_hours": None, "cost_usd": None}
