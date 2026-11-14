"""After a quit the open starts nothing; the launch alert lists what stopped and Continue lets the chosen go (#6584).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.launch.nothing-starts-one-alert`,
`activity.run.failed-is-never-requeued-by-itself`. WHY (owner 2026-11-13 night): every launch took up whatever was running
or queued at quit, and a user's failed recipe seemed to restart over and over. Through `jobs.resume` (what a library open
calls), the two routes and the real jobs table.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

KIND = "t-launch"


@pytest.fixture
def held(db, monkeypatch):
    ran: list[str] = []
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: ran.append(subject), model=None, name="Read a page"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a fresh engine: nothing of the old one is live
    jobs.set_paused(True)  # while the rows are set up as the quit left them
    db.ran = ran
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None, **cols):
    job_id = jobs.enqueue(db, KIND, subject)
    sets = ", ".join(["state = ?", "reason = ?", *(f"{c} = ?" for c in cols)])
    db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", [state, reason, *cols.values(), job_id])
    return job_id


def _state(db, job_id):
    return db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])


def test_the_open_starts_nothing_and_pauses_what_the_quit_left_unfinished(held, client):
    running = _row(held, "l:running", "running", None, attempts=1)
    thrice = _row(held, "l:thrice", "running", None, attempts=jobs.MAX_ATTEMPTS)
    queued = _row(held, "l:queued", "waiting", None)
    pausing = _row(held, "l:pausing", "running", jobs.PAUSING)
    failed = _row(held, "l:failed", "failed", "Out of credit on OpenRouter", finished_at=jobs.utc_now())
    done = _row(held, "l:done", "done", None, finished_at=jobs.utc_now())

    jobs.resume(held)  # the open after the quit
    jobs.set_paused(False)  # background work is on: the lane runs anything left waiting, and must find nothing

    import time
    time.sleep(0.5)
    assert held.ran == [], "nothing started by itself"
    for job_id in (running, thrice, queued):
        assert _state(held, job_id) == ("paused", jobs.QUIT_REASON), job_id
    assert _state(held, pausing) == ("paused", jobs.PAUSED_REASON), "a pause the person asked for keeps its words"
    assert _state(held, failed) == ("failed", "Out of credit on OpenRouter"), "a failed run stays failed, never re-run"
    assert _state(held, done)[0] == "done"
    listed = client.get("/api/activity/stopped-at-quit").json()
    assert [i["id"] for i in listed["items"]] == [running, thrice, queued] and listed["count"] == 3
    assert listed["items"][0]["name"] == "Read a page"


def test_continue_lets_only_the_chosen_rows_go(held, client):
    one = _row(held, "c:1", "running", None)
    two = _row(held, "c:2", "waiting", None)
    three = _row(held, "c:3", "running", None)
    jobs.resume(held)
    assert {_state(held, i)[0] for i in (one, two, three)} == {"paused"}

    r = client.post("/api/activity/stopped-at-quit/continue", json={"ids": [one, two]})

    assert r.status_code == 200, r.text
    assert sorted(r.json()["continued_ids"]) == sorted([one, two])
    assert _state(held, one)[0] == "waiting" and _state(held, two)[0] == "waiting"
    assert _state(held, three) == ("paused", jobs.QUIT_REASON), "the row not chosen stays paused"
    assert [i["id"] for i in client.get("/api/activity/stopped-at-quit").json()["items"]] == [three]
    assert client.post("/api/activity/stopped-at-quit/continue", json={}).json()["count"] == 0, "nothing chosen: nothing"
    assert client.post("/api/activity/stopped-at-quit/continue", json={"all": True}).json()["continued_ids"] == [three]


def test_a_second_open_does_not_touch_what_the_first_paused_or_what_a_person_paused(held):
    stopped = _row(held, "s:1", "running", None)
    jobs.resume(held)
    by_person = _row(held, "s:2", "paused", jobs.PAUSED_REASON)

    jobs.resume(held)  # the app relaunched again before anyone chose

    assert _state(held, stopped) == ("paused", jobs.QUIT_REASON)
    assert _state(held, by_person) == ("paused", jobs.PAUSED_REASON)
    assert held.ran == []
