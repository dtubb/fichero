"""A live call keeps its slot past the hold limit (#5938, `activity.lane.hold-limit-keeps-the-slot`; Fable runner review 2 MED 7,
lead's call at ## 668): no other heavy job starts beside it and nothing unloads until its body returns; the row's words change."""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setattr(jobs, "HOLD_LIMIT_SECONDS", 0.1)
    monkeypatch.setattr(jobs, "SLOW_CALL_SECONDS", 0.1)
    # A call waiting on its answer is slow, never stuck: past the stuck-lane deadline it keeps the one slot too (#6213).
    monkeypatch.setattr(jobs, "STUCK_MODEL_JOB_SECONDS", 0.1)


def test_past_the_limit_no_other_heavy_job_starts_until_the_body_returns(db, test_package):
    events: list[str] = []

    async def first():
        async with jobs.lane_slot(str(test_package), "ask-a-model", "slow page", model="omlx:reader", run_id="run-a", lane="local-ml"):
            events.append("first start")
            await asyncio.sleep(0.6)  # well past the limit
            events.append("first end")

    async def second():
        await asyncio.sleep(0.3)  # asks after the limit has passed
        async with jobs.lane_slot(str(test_package), "ask-a-model", "next page", model="other:model", run_id="run-b", lane="local-ml"):
            events.append("second start")

    async def go():
        await asyncio.gather(first(), second())

    asyncio.run(asyncio.wait_for(go(), 60))
    assert events == ["first start", "first end", "second start"], events


def test_past_the_limit_the_row_says_it_keeps_its_place(db, test_package):
    seen: list[str] = []

    async def go():
        async with jobs.lane_slot(str(test_package), "ask-a-model", "slow page", model="omlx:reader", run_id="run-c", lane="local-ml"):
            await asyncio.sleep(0.5)
            seen.append(db.execute_fetchone("SELECT reason FROM jobs WHERE subject = ?", ["slow page"])[0] or "")

    asyncio.run(go())
    assert "keeps its place; Stop ends it" in seen[0], seen
    for _ in range(60):
        state = db.execute_fetchone("SELECT state FROM jobs WHERE subject = ?", ["slow page"])[0]
        if state not in ("running", "waiting"):
            break
        time.sleep(0.1)
    assert state == "done"
