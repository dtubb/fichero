"""A failed job's row reason is the failure kind's row words, never exception text (#6597).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.failure.no-raw-text-ever`. The reason is at most eight words,
no full stop, no exception type, path or bracket; the full text lives in the row's detail for Copy Details.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import _wait_for

KIND = "t-raw-text-job"
RAW = "bad value in /Users/someone/Letters/page 1.txt [line 3]"


@pytest.fixture
def kind(db, monkeypatch):
    def run(_db, subject):
        raise TypeError(RAW)

    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=run, model=None, name="Raw text job"))
    jobs.load_kinds()
    return db


def test_a_job_raising_a_type_error_with_a_path_lists_no_exception_text(kind, client):
    job_id = jobs.enqueue(kind, KIND, "one")
    assert _wait_for(lambda: jobs.read_job(kind, job_id)["state"] == "failed", 60), jobs.read_job(kind, job_id)
    row = next(j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == job_id)
    reason = row["reason"]
    assert "Error" not in reason and "/Users/" not in reason and "[" not in reason, reason
    assert 1 <= len(reason.split()) <= 8 and not reason.endswith("."), reason
    stored = jobs.read_job(kind, job_id)
    assert stored["reason"] == reason
    detail = json.loads(stored["detail"])
    assert RAW in detail["error"] and detail["error_type"] == "TypeError"  # Copy Details keeps everything
