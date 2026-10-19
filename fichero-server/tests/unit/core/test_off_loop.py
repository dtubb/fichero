"""`@off_loop` (#5843): a plain def route that FastAPI serves, a test can await, and that runs off the event loop."""
from __future__ import annotations

import asyncio
import threading
import time

from fastapi import APIRouter, FastAPI, Query
from fastapi.testclient import TestClient

from fichero_server.core.off_loop import off_loop

router = APIRouter()
seen: dict[str, int] = {}


@router.get("/double")
@off_loop
def double(n: int = Query(default=1)) -> dict[str, int]:
    seen["thread"] = threading.get_ident()
    return {"n": n * 2}


def test_it_serves_with_its_query_parameters_and_runs_in_a_worker_thread():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/double", params={"n": 4}).json() == {"n": 8}
    assert seen["thread"] != threading.get_ident()
    assert "n" in app.openapi()["paths"]["/double"]["get"]["parameters"][0]["name"]


def test_it_can_still_be_awaited_and_leaves_the_loop_free():
    @off_loop
    def slow() -> int:
        time.sleep(1.0)
        return 7

    async def go() -> tuple[int, float]:
        work = asyncio.ensure_future(slow())
        await asyncio.sleep(0.1)
        started = time.monotonic()
        await asyncio.sleep(0)
        took = time.monotonic() - started
        return await work, took

    value, took = asyncio.run(go())
    assert value == 7 and took < 0.5
