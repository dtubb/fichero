"""A person's page goes before the other heavy lanes' background work (`activity.throttle.person-heavy-first`; owner's
stalled "Compare on These Pages", 2026-10-19: under memory pressure only one heavy job runs at a time, and the try's
Kraken page waited for 23 thumbnails of 47-61 s each, one after the other, because the thumbnail lane took every slot in
turn). Real lanes, faked work."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs, throttle

BG = "thumbnail-like-person-first"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_a_waiting_persons_model_page_takes_the_next_heavy_slot_before_more_thumbnails(db, monkeypatch):
    events: list[str] = []
    gate = threading.Event()

    def work(_db, subject):
        events.append(f"start:{subject}")
        if subject == "t1":
            gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, BG, jobs.Kind(run=work, model=None, lane="images", name="Thumbnail"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": None)
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: True)  # memory at warn: one heavy job at a time
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    jobs.enqueue(db, BG, "t1")
    assert _wait_for(lambda: "start:t1" in events)
    person = jobs.submit(db, "read-a-page", "page", model="kraken:blla", fn=lambda: events.append("person-page") or "ok")
    jobs.enqueue(db, BG, "t2")  # more thumbnails queued behind the first
    jobs.enqueue(db, BG, "t3")
    time.sleep(0.5)
    gate.set()
    assert person.result(timeout=30) == "ok"
    assert _wait_for(lambda: "start:t3" in events)
    assert events.index("person-page") < events.index("start:t2")  # the person's page went first


def test_a_try_waiting_or_running_says_what_for_in_a_field_beside_its_spinner(db):
    """`recipes.try.says-what-it-waits-for`: the try's result carries `waiting_for` in words while its job waits or runs."""
    import json

    from fichero_server.recipes import samples

    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, reason, created_at, started_by) "
               "VALUES ('try-1', ?, 'find-lines', 'running', 'Copying the sample pages for Find Lines', now(), 'owner')",
               [samples.TRY_KIND])
    followed = samples._following_its_job(db, {"state": "waiting", "job_id": "try-1"})
    assert followed["waiting_for"] == "Copying the sample pages for Find Lines"
    assert json.dumps(followed)  # plain data, as the route returns it
