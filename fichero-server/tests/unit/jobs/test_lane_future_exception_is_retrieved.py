"""A call that fails on its lane leaves no "Future exception was never retrieved" behind (the Air, 2026-10-30: 13).

`lane_slot` hands the lane a `hold` that raises the call's error into the lane's Future once the slot was granted;
the caller already has the error, and nobody awaited that Future past the grant, so asyncio reported it at GC with
the same words (a spend cap reached, "Connection error.") as noise.
"""
from __future__ import annotations

import asyncio
import gc

import pytest

from fichero_server.execution import jobs


def test_a_failed_call_on_the_lane_is_not_reported_twice(db, test_package):
    futures = []
    real_wrap = asyncio.wrap_future

    def seen(future, *, loop=None):
        wrapped = real_wrap(future, loop=loop)
        futures.append(wrapped)
        return wrapped

    reported: list[str] = []
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, context: reported.append(context.get("message", "")))

    async def work():
        raise RuntimeError("This project's cloud spend is capped")

    async def go():
        with pytest.raises(RuntimeError, match="capped"):
            await jobs.hold_lane(str(test_package), "read-a-page", "page", model="anthropic/sonnet", work=work,
                                 lane="network")
        for _ in range(100):  # the lane thread finishes the job's row and sets its future
            if db.execute_fetchone("SELECT state FROM jobs WHERE subject = 'page'") == ("failed",):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)

    asyncio.wrap_future = seen
    try:
        loop.run_until_complete(go())
    finally:
        asyncio.wrap_future = real_wrap
    assert futures, "lane_slot wraps the lane's future"
    lane_future = futures[0]
    assert lane_future.done()
    # asyncio reports an exception nobody asked for when the Future is collected: `_log_traceback` is that flag, and
    # asking `exception()` here would clear it -- so the flag is read first.
    assert not lane_future._log_traceback, "the lane's exception was never retrieved"
    assert lane_future.exception() is not None
    del lane_future, futures[:]
    gc.collect()
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()
    assert not [m for m in reported if "never retrieved" in m], reported
