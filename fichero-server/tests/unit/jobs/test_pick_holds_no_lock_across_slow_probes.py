"""Fable review #11: the heavy pick (`_heavy_pick`) and the lane's pick must not be held across a slow probe (`pmset`) or a
write per open project on every scan."""
from __future__ import annotations

from fichero_server.execution import jobs, throttle


def test_the_battery_is_read_before_the_heavy_pick_lock_is_taken(monkeypatch):
    sched = jobs._scheduler
    lane = sched.lanes["local-ml"]
    held_at_reading = []
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: held_at_reading.append(sched._heavy_pick.locked()) or False)
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: False)
    monkeypatch.setattr(sched, "_claim_one", lambda lane: None)
    sched._claim(lane)
    assert held_at_reading == [False], "the slow reading ran inside _heavy_pick"


def test_a_held_reason_is_written_once_not_on_every_scan(monkeypatch):
    sched = jobs._scheduler
    lane = sched.lanes["local-ml"]
    lane.__dict__.pop("_said_held", None)
    writes = []

    class Db:
        def execute(self, sql, params=None):
            writes.append(sql)

    from fichero_server.db import manager as db_manager_module

    monkeypatch.setattr(db_manager_module.db_manager, "open_database", lambda key: Db())
    monkeypatch.setitem(jobs.KINDS, "pick-test", jobs.Kind(run=lambda d, s: None, model="kraken:x", lane="local-ml"))
    lane.libraries.add("lib-a") if hasattr(lane.libraries, "add") else lane.libraries.update({"lib-a": 1})
    try:
        for _ in range(3):
            sched._say_why_background_waits(lane, "Waiting: the Mac is on battery")
        assert len(writes) == 1, f"{len(writes)} writes for one unchanged reason"
        sched._say_why_background_waits(lane, "Waiting: the Mac is hot")
        assert len(writes) == 2, "a changed reason is written at once"
    finally:
        lane.__dict__.pop("_said_held", None)
        if hasattr(lane.libraries, "discard"):
            lane.libraries.discard("lib-a")
        else:
            lane.libraries.pop("lib-a", None)


import asyncio

import pytest


@pytest.mark.asyncio
async def test_a_model_call_that_does_not_answer_says_so_on_its_row(db, test_package, monkeypatch):
    """Fable review #16: a model server that stops answering held the lane's one slot for 15 minutes with the row's last
    reason. The row now says how long it has waited."""
    monkeypatch.setattr(jobs, "SLOW_CALL_SECONDS", 0.2)
    monkeypatch.setattr(jobs, "HOLD_LIMIT_SECONDS", 5.0)
    release = asyncio.Event()

    async def work():
        await asyncio.wait_for(release.wait(), 10)

    task = asyncio.ensure_future(jobs.hold_lane(str(test_package), "read-a-page", "slow-page",
                                                model="omlx:reader", work=work))
    try:
        deadline = asyncio.get_event_loop().time() + 8
        said = None
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
            row = db.execute_fetchone("SELECT reason FROM jobs WHERE subject = 'slow-page'")
            if row and row[0] and "Waiting for the model to answer" in row[0]:
                said = row[0]
                break
        assert said, "the row stayed silent while the call hung"
    finally:
        release.set()
        await asyncio.wait_for(task, 10)
