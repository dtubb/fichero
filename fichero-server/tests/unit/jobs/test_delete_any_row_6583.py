"""Delete works on every row Activity lists, and deleted work stays gone (#6583).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.window.delete-any-row`.
WHY (owner 2026-11-13): Delete in the window acted only on workflow runs; a job of its own (a failed recipe run, a
paused download, a queued group of thumbnails) could not be deleted at all, and Clear Failed only hid failures.
Through the route and the real jobs table; nothing runs (background work is paused for the test).
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-delete"
GROUP_KIND = "t-delete-thumbs"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Try a stage"))
    monkeypatch.setitem(jobs.KINDS, GROUP_KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Make thumbnails"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, kind, subject, state, reason=None):
    job_id = jobs.enqueue(db, kind, subject)
    db.execute("UPDATE jobs SET state = ?, reason = ?, finished_at = CASE WHEN ? IN ('done', 'failed', 'cancelled') "
               "THEN now() ELSE NULL END WHERE id = ?", [state, reason, state, job_id])
    return job_id


def _listed(client):
    return {j["id"]: j["state"] for j in client.get("/api/activity/jobs").json()["jobs"]}


def _state(db, job_id):
    return db.execute_fetchone("SELECT state, reason, cleared_at IS NOT NULL FROM jobs WHERE id = ?", [job_id])


def test_delete_takes_a_failed_a_paused_a_done_row_and_a_whole_group__and_skips_what_runs(held, client):
    failed = _row(held, KIND, "d:failed", "failed", "Anthropic has no credit left")
    paused = _row(held, KIND, "d:paused", "paused", jobs.PAUSED_REASON)
    done = _row(held, KIND, "d:done", "done")
    running = _row(held, KIND, "d:running", "running")
    thumbs = [_row(held, GROUP_KIND, f"g:{i}", "waiting") for i in range(3)]
    listed = _listed(client)
    assert failed in listed and paused in listed and f"waiting:{GROUP_KIND}" in listed

    jobs._scheduler.running_ids = lambda: [running]  # the lane runs this one now
    r = client.post("/api/activity/jobs/delete",
                    json={"ids": [failed, paused, done, running, f"waiting:{GROUP_KIND}"]})

    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["deleted_ids"]) == sorted([failed, paused, done, *thumbs])
    assert body["skipped_ids"] == [running], "a job running now is skipped, and said so"
    listed = _listed(client)
    for job_id in (failed, paused, done, *thumbs):
        assert job_id not in listed, f"{job_id} is still listed"
    assert f"waiting:{GROUP_KIND}" not in listed, "the group's row is gone with its jobs"
    assert running in listed
    # Kept, not destroyed; what waited or was paused is cancelled so no lane picks it; the failure keeps its reason.
    assert _state(held, failed) == ("failed", "Anthropic has no credit left", True)
    assert _state(held, paused) == ("cancelled", "Deleted by you", True)
    assert _state(held, done)[0] == "done" and _state(held, done)[2]
    assert all(_state(held, t) == ("cancelled", "Deleted by you", True) for t in thumbs)


def test_deleted_work_stays_gone_after_a_relaunch_and_a_retry_lists_it_again(held, client):
    failed = _row(held, KIND, "d:failed2", "failed", "the model is not downloaded")
    waiting = _row(held, KIND, "d:waiting2", "waiting")
    assert client.post("/api/activity/jobs/delete", json={"ids": [failed, waiting]}).json()["deleted_ids"]

    jobs.resume(held)  # the next open

    listed = _listed(client)
    assert failed not in listed and waiting not in listed
    assert _state(held, waiting)[0] == "cancelled", "a deleted waiting job never comes back to run"
    assert client.post(f"/api/activity/jobs/{failed}/retry").json()["state"] == "waiting"
    assert _listed(client).get(failed) == "waiting", "a Retry asked of a deleted row lists it again"


def test_delete_takes_a_run_with_everything_under_it(held, client):
    run = _row(held, KIND, "d:run", "failed", "2 of 3 pages were not read")
    page = _row(held, KIND, "d:run:page", "failed", "timed out")
    held.execute("UPDATE jobs SET parent_id = ? WHERE id = ?", [run, page])

    r = client.post("/api/activity/jobs/delete", json={"ids": [run]})

    assert r.json()["deleted_ids"] == [run]
    assert _state(held, page)[2], "the row under the run is marked with it"
    assert run not in _listed(client) and page not in _listed(client)


def test_clear_finished_takes_every_ended_job_of_its_own_and_leaves_the_rest(held, client):
    done = [_row(held, GROUP_KIND, f"cf:{i}", "done") for i in range(3)]
    failed = _row(held, KIND, "cf:failed", "failed", "no model")
    stopped = _row(held, KIND, "cf:stopped", "cancelled", "Stopped by you")
    waiting = _row(held, KIND, "cf:waiting", "waiting")

    r = client.post("/api/activity/jobs/delete", json={"states": ["done", "failed", "cancelled"]})

    assert r.status_code == 200, r.text
    assert sorted(r.json()["deleted_ids"]) == sorted([*done, failed, stopped])
    assert _state(held, waiting)[0] == "waiting" and not _state(held, waiting)[2], "work still to do is left"
    assert all(_state(held, d)[2] for d in done)
    assert client.post("/api/activity/jobs/delete", json={"states": ["done"]}).json()["count"] == 0, "nothing left"


def test_an_unknown_id_is_skipped_not_an_error(held, client):
    r = client.post("/api/activity/jobs/delete", json={"ids": ["no-such-job"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted_ids": [], "skipped_ids": ["no-such-job"], "count": 0}


def test_delete_is_an_audited_action(held):
    from fichero_server.actions.registry import registry

    assert "job.delete" in registry.names()
