"""`activity.read.get-runs-no-model`, at any depth: a GET that reaches a model entry point THROUGH helpers is refused in words."""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import BackgroundTasks, FastAPI

from fichero_server.core import no_model_in_get
from fichero_server.core.no_model_in_get import ModelWorkInGet, NoModelWorkInGet, forbid_in_get


def _app() -> FastAPI:
    from fichero_server.llm import kraken_runtime

    app = FastAPI()
    app.add_middleware(NoModelWorkInGet)
    no_model_in_get.install_handler(app)

    def deep_helper():  # two calls down, in a worker thread: the scan cannot see this
        return kraken_runtime._kraken_call(lambda: "read")

    @app.get("/indirect")
    async def indirect():
        return await asyncio.to_thread(deep_helper)

    @app.post("/indirect")
    async def indirect_post():
        forbid_in_get("a read")  # a POST is not a GET: nothing is refused
        return {"ok": True}

    return app


def _call(method: str, path: str) -> httpx.Response:
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as client:
            return await client.request(method, path)

    return asyncio.run(go())


def test_a_get_reaching_kraken_through_a_helper_thread_is_refused_in_words():
    response = _call("GET", "/indirect")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "GET /indirect" in detail and "isn't ready" in detail and "model lane" in detail


def test_a_post_is_not_refused():
    assert _call("POST", "/indirect").status_code == 200


def test_the_embedder_and_the_lane_refuse_inside_a_get_and_not_outside():
    from fichero_server.db.embeddings import DatabaseEmbeddingMixin
    from fichero_server.execution import jobs

    with no_model_in_get.marked_get("/api/thing"):
        with pytest.raises(ModelWorkInGet):
            DatabaseEmbeddingMixin._embed_text(object(), "x", role="passage")  # a query is allowed, bounded
        with pytest.raises(ModelWorkInGet):
            DatabaseEmbeddingMixin._embed_texts(object(), ["x"])
        with pytest.raises(ModelWorkInGet):
            jobs.run_on_lane_blocking(None, "k", "s", model="kraken:x", fn=lambda: 1)
        with pytest.raises(ModelWorkInGet):
            asyncio.run(jobs.run_on_lane(None, "k", "s", model="kraken:x", fn=lambda: 1))
    forbid_in_get("a read")  # outside any GET: allowed


def test_the_mark_does_not_leak_past_the_request():
    with no_model_in_get.marked_get("/a"):
        pass
    forbid_in_get("a read")


def test_work_that_outlives_the_get_is_not_the_get():
    """Review 109: a task the GET spawned and a BackgroundTasks function copy the context, but run after the response."""
    app = FastAPI()
    app.add_middleware(NoModelWorkInGet)
    no_model_in_get.install_handler(app)
    outcomes: dict[str, str] = {}
    gate: list[asyncio.Event] = []

    def background():
        try:
            forbid_in_get("a read")
            outcomes["background"] = "allowed"
        except ModelWorkInGet:
            outcomes["background"] = "refused"

    async def spawned():
        await gate[0].wait()  # the response is complete by now
        try:
            forbid_in_get("a read")
            outcomes["spawned"] = "allowed"
        except ModelWorkInGet:
            outcomes["spawned"] = "refused"

    @app.get("/starts-things")
    async def starts_things(tasks: BackgroundTasks):
        tasks.add_task(background)
        outcomes["task"] = asyncio.ensure_future(spawned())  # type: ignore[assignment]
        try:
            forbid_in_get("a read")
            outcomes["inside"] = "allowed"
        except ModelWorkInGet:
            outcomes["inside"] = "refused"
        return {"ok": True}

    async def go():
        gate.append(asyncio.Event())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            assert (await client.get("/starts-things")).status_code == 200
        gate[0].set()
        await outcomes["task"]  # type: ignore[misc]

    asyncio.run(go())
    assert outcomes["inside"] == "refused", "work in the request itself is the GET"
    assert outcomes["background"] == "allowed", "a background task runs after the response"
    assert outcomes["spawned"] == "allowed", "a task left running past the response is not the GET"


def test_a_task_spawned_during_a_get_runs_its_model_call_even_while_the_get_is_still_answering():
    """Review 361 MED 2: the auto-embed, the activity tracker's recovery, work started at a library open are spawned by a
    GET and run while it is still going. Only the request's own task and its to_thread are refused."""
    app = FastAPI()
    app.add_middleware(NoModelWorkInGet)
    no_model_in_get.install_handler(app)
    seen: dict[str, str] = {}

    def attempt(name: str) -> None:
        try:
            forbid_in_get("a read")
            seen[name] = "allowed"
        except ModelWorkInGet:
            seen[name] = "refused"

    async def spawned():
        attempt("spawned task")
        await asyncio.to_thread(attempt, "its to_thread")

    @app.get("/spawns")
    async def spawns():
        await asyncio.ensure_future(spawned())  # awaited, so the GET is still answering while it runs
        await asyncio.create_task(asyncio.sleep(0))
        await asyncio.to_thread(attempt, "the request's to_thread")
        attempt("the request")
        return {"ok": True}

    @app.middleware("http")
    async def a_base_http_middleware(request, call_next):  # the framework's child task keeps the request's mark
        return await call_next(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            assert (await client.get("/spawns")).status_code == 200

    asyncio.run(go())
    assert seen == {
        "spawned task": "allowed", "its to_thread": "allowed",
        "the request's to_thread": "refused", "the request": "refused",
    }
