"""The window's global run controls (`activity.window.run-controls`, #6588; the owner 2026-11-15: "pause all, restart the ones
we just paused, or stop all"): Pause All pauses every running and waiting piece of work, a person's runs too, and holds
background work; Play (Continue All) lets go exactly what it held, never a row paused by hand; Stop All stops everything and
keeps what was done. Through the routes and the real jobs table."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-run-controls"


@pytest.fixture
def lane(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    scheduler = jobs._Scheduler()
    monkeypatch.setattr(scheduler, "wake", lambda *a, **k: None)  # no lane takes a row: its state is what the test set
    monkeypatch.setattr(jobs, "_scheduler", scheduler)
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None):
    job_id = jobs.enqueue(db, KIND, subject)
    db.execute("UPDATE jobs SET state = ?, reason = ? WHERE id = ?", [state, reason, job_id])
    return job_id


def _state(db, job_id):
    return db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0]


def _summary(client):
    return client.get("/api/activity/jobs").json()["activity"]


def test_pause_all_holds_the_waiting_work_and_play_lets_go_only_that(lane, client):
    a, b = _row(lane, "p:a", "waiting"), _row(lane, "p:b", "waiting")
    by_hand = _row(lane, "p:c", "paused", jobs.PAUSED_REASON)
    jobs.set_paused(False)
    assert _summary(client)["controls"] == "pause"

    answer = client.post("/api/activity/pause-all").json()
    assert sorted(answer["ids"]) == sorted([a, b]) and answer["count"] == 2
    assert [_state(lane, j) for j in (a, b, by_hand)] == ["paused", "paused", "paused"]
    assert jobs.is_paused(), "nothing new starts while Pause All holds"
    assert _summary(client)["controls"] == "play"

    answer = client.post("/api/activity/continue-all").json()
    assert sorted(answer["ids"]) == sorted([a, b])
    assert [_state(lane, j) for j in (a, b)] == ["waiting", "waiting"]
    assert _state(lane, by_hand) == "paused", "a row paused by hand before stays paused"
    assert not jobs.is_paused()
    assert jobs.held_count(lane) == 0
    jobs.set_paused(True)


def test_a_held_run_is_resumed_from_its_checkpoint_by_play(lane, client, monkeypatch):
    from fichero_server.api.routes.system import activity
    from fichero_server.api.routes.workflow_execution import core

    jobs._record(lane, "run-1", kind="workflow", subject="run-1", parent_id=None, state="paused", reason="Paused by you",
                 name="Read the letters")
    lane.execute("UPDATE jobs SET held_by = ? WHERE id = 'run-1'", [jobs.HELD_BY_PAUSE_ALL])
    resumed = []

    async def resume(thread_id, _http, request=None, db=None, library_path=None):
        resumed.append(thread_id)

    monkeypatch.setattr(core, "resume_workflow", resume)
    monkeypatch.setattr(activity, "_resume_runs_later", lambda db, runs: resumed.extend(runs))
    answer = client.post("/api/activity/continue-all").json()
    assert answer["runs_resumed"] == ["run-1"] and resumed == ["run-1"]
    jobs.set_paused(True)


def test_stop_all_stops_everything_and_ends_the_hold(lane, client):
    a, b = _row(lane, "s:a", "waiting"), _row(lane, "s:b", "paused", jobs.PAUSED_REASON)
    assert _summary(client)["stoppable"] == 2
    client.post("/api/activity/pause-all")
    answer = client.post("/api/activity/stop-all").json()
    assert sorted(answer["ids"]) == sorted([a, b])
    assert [_state(lane, j) for j in (a, b)] == ["cancelled", "cancelled"]
    assert jobs.held_count(lane) == 0 and not jobs.is_paused()
    assert _summary(client)["controls"] == "none"
    jobs.set_paused(True)


def test_pause_all_is_one_undo_step(lane, client):
    a = _row(lane, "u:a", "waiting")
    jobs.set_paused(False)
    done = client.post("/api/actions/invoke", json={"name": "activity.pause_all", "params": {}}).json()
    assert _state(lane, a) == "paused"
    undone = client.post("/api/actions/audit/undo", json={"audit_ids": [done["audit_id"]]})
    assert undone.status_code == 200, undone.text
    assert _state(lane, a) == "waiting" and not jobs.is_paused()
    jobs.set_paused(True)
