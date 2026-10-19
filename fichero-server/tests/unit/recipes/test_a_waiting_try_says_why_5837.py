"""Compare on These Pages that has to wait for its turn says what it waits for, in the engine's words, not a spinner
alone (#5837, `source.onboard.stages.try-waiting-says-why`)."""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.recipes import samples


def test_a_try_waiting_for_the_lane_carries_the_jobs_reason(db, monkeypatch):
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "waiting", "reason": None})
    monkeypatch.setattr(jobs, "state_and_reason", lambda db, job_id: ("waiting", "Waiting for the model lane: Kraken read"))

    result = samples._following_its_job(db, {"state": "waiting", "job_id": "j1"})

    assert result["comparison"] == {"state": "waiting", "reason": "Waiting for the model lane: Kraken read"}


def test_a_running_try_or_a_bakeoffs_own_comparison_is_left_alone(db, monkeypatch):
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "running", "reason": None})
    monkeypatch.setattr(jobs, "state_and_reason", lambda db, job_id: ("running", None))
    assert "comparison" not in samples._following_its_job(db, {"state": "waiting", "job_id": "j1"})

    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "waiting", "reason": None})
    monkeypatch.setattr(jobs, "state_and_reason", lambda db, job_id: ("waiting", "x"))
    own = {"state": "waiting", "job_id": "j1", "comparison": {"state": "waiting", "reason": "bakeoff's"}}
    assert samples._following_its_job(db, own)["comparison"]["reason"] == "bakeoff's"


def test_a_running_try_whose_page_waits_says_so_too(db, monkeypatch):
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "running", "reason": "Waiting: the model lane"})
    monkeypatch.setattr(jobs, "state_and_reason", lambda db, job_id: ("running", "Waiting: the model lane"))

    result = samples._following_its_job(db, {"state": "waiting", "job_id": "j1"})

    assert result["comparison"]["reason"] == "Waiting: the model lane"
