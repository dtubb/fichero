"""A slot held past the hold limit under a still-live call says so, not that its run had ended (#5938,
`activity.lane.one-model-at-a-time`; Fable runner review 2 MED 7)."""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    monkeypatch.setattr(jobs, "HOLD_LIMIT_SECONDS", 0.1)


def test_a_call_still_live_at_the_hold_limit_is_not_said_to_have_ended_with_its_run(db, test_package):
    async def go():
        async with jobs.lane_slot(str(test_package), "ask-a-model", "slow page", model="omlx:reader", run_id="run-5938", lane="local-ml"):
            await asyncio.sleep(0.3)  # the call outlives the limit

    asyncio.run(go())
    for _ in range(60):
        state, reason = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = ?", ["slow page"])
        if state not in ("running", "waiting"):
            break
        time.sleep(0.1)
    assert "had ended" not in (reason or ""), reason
    assert "had not answered" in (reason or ""), reason
