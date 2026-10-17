"""The Activity window's finished rows come newest first, each with its own state (#5016,
`activity.window.newest-first-and-clear-all`): what just ran is at the top, not at the end of a long list."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-newest"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Detect Regions"))
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _failed_at(db, subject, when):
    job_id = jobs.enqueue(db, KIND, subject)
    db.execute(
        "UPDATE jobs SET state = 'failed', reason = 'boom', created_at = ?, finished_at = ? WHERE id = ?",
        [when, when, job_id],
    )
    return job_id


def test_failed_rows_are_listed_newest_first_each_with_its_state(held, client):
    old = _failed_at(held, "n:old", "2026-10-01 09:00:00")
    new = _failed_at(held, "n:new", "2026-10-03 09:00:00")
    mid = _failed_at(held, "n:mid", "2026-10-02 09:00:00")

    rows = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] in {old, new, mid}]

    assert [j["id"] for j in rows] == [new, mid, old]
    assert {j["state"] for j in rows} == {"failed"}
