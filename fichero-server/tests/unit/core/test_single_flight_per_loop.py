"""`single_flight` shares a flight only within one event loop (the Air, 2026-10-30: 8 run-status polls answered 500).

The engine runs two uvicorn servers -- the UDS one and the TCP sharing one -- each on its own loop in its own thread.
The in-flight Future is the first loop's; a poll of the same route and arguments arriving on the second loop awaited
it and got "RuntimeError: ... got Future <Future pending> attached to a different loop".
"""
from __future__ import annotations

import asyncio
import threading

from fichero_server.core.single_flight import single_flight


def test_the_same_poll_on_two_loops_does_not_share_a_future():
    calls = []

    @single_flight
    async def poll(*, db):
        calls.append(threading.current_thread().name)
        await asyncio.sleep(1.0)  # in flight while the other loop's poll arrives
        return "ok"

    class _Db:
        path = "/a/library"

        def execute(self):
            pass

    results: dict[str, object] = {}

    def on_a_loop(name: str, after: float) -> None:
        async def go():
            await asyncio.sleep(after)
            return await poll(db=_Db())
        try:
            results[name] = asyncio.run(go())
        except BaseException as exc:  # noqa: BLE001 -- the assertion
            results[name] = f"{type(exc).__name__}: {str(exc)[:80]}"

    uds = threading.Thread(target=on_a_loop, args=("uds", 0.0), name="uds")
    tcp = threading.Thread(target=on_a_loop, args=("tcp", 0.3), name="tcp")
    uds.start()
    tcp.start()
    uds.join(10)
    tcp.join(10)
    assert results == {"uds": "ok", "tcp": "ok"}, results
    assert sorted(calls) == ["tcp", "uds"], "each loop ran its own flight"
