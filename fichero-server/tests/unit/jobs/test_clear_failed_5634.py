"""Clear Failed clears the failed jobs the Activity window lists (#5634).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.window.clear-failed`.
WHY: the maintainer pressed Clear Failed and nothing changed. It deleted only workflow runs; a failed
job of its own (a recipe run, a model download, Detect Regions) could not be cleared at all, so its row
and the toolbar's error glyph stayed forever. Through the routes and the real jobs table.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs


KIND = "t-clear"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Detect Regions"))
    jobs.set_paused(True)  # nothing runs: what is listed is what is tested
    yield db
    jobs.set_paused(False)


def _failed(db, kind, subject, reason="Kraken not installed"):
    job_id = jobs.enqueue(db, kind, subject)
    db.execute("UPDATE jobs SET state = 'failed', reason = ?, finished_at = now() WHERE id = ?", [reason, job_id])
    return job_id


def _listed(client):
    return {j["id"]: j["state"] for j in client.get("/api/activity/jobs").json()["jobs"]}


def test_clear_failed_clears_every_failed_job_listed_and_keeps_the_rest(held, client):
    kind = KIND
    one = _failed(held, kind, "clear:1")
    two = _failed(held, kind, "clear:2", reason="the model is not downloaded")
    waiting = jobs.enqueue(held, kind, "clear:waits")
    listed = _listed(client)
    assert listed[one] == "failed" and listed[two] == "failed"

    r = client.post("/api/activity/jobs/clear-failed")

    assert r.status_code == 200, r.text
    assert sorted(r.json()["cleared_ids"]) == sorted([one, two]) and r.json()["count"] == 2
    listed = _listed(client)
    assert one not in listed and two not in listed, "a cleared failure is no longer listed"
    assert any(job_id == waiting or job_id.startswith("paused:") or job_id.startswith("waiting:")
               for job_id in listed), "work that has not failed is untouched"
    # Kept, not destroyed: the row and its reason are still in the table.
    assert held.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [one]) == (
        "failed", "Kraken not installed")
    assert client.post("/api/activity/jobs/clear-failed").json()["count"] == 0, "nothing left to clear"


def test_a_cleared_job_retried_is_listed_again(held, client):
    kind = KIND
    job_id = _failed(held, kind, "clear:retry")
    client.post("/api/activity/jobs/clear-failed")
    assert job_id not in _listed(client)

    assert client.post(f"/api/activity/jobs/{job_id}/retry").json()["state"] == "waiting"
    held.execute("UPDATE jobs SET state = 'failed', finished_at = now() WHERE id = ?", [job_id])

    assert _listed(client).get(job_id) == "failed", "a retry that fails again is a new failure, listed"


def test_clear_failed_is_an_audited_action(held, client):
    from fichero_server.actions.registry import registry

    assert "job.clear_failed" in registry.names()
