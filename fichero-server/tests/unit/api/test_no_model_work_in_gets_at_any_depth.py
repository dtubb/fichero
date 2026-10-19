"""`activity.read.get-runs-no-model`, at any depth: a GET that reaches a model entry point THROUGH helpers is refused in words."""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

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
            DatabaseEmbeddingMixin._embed_text(object(), "x")
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
