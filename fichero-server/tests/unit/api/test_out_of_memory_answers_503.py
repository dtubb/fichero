"""A read that does not fit DuckDB's share answers 503 with a sentence, through the real app's middleware, however the
route reached it (the Air, 2026-10-30: 55 document views answered 500 with a stack trace)."""
from __future__ import annotations

import asyncio

import duckdb
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from fichero_server.api import main


def _refuse():
    raise duckdb.OutOfMemoryException("Out of Memory Error: failed to pin block of size 256.0 KiB (255.9 MiB/256.0 MiB used)\n* more")


async def _on_the_loop():
    _refuse()


async def _in_a_thread():
    await asyncio.to_thread(_refuse)


def _sync_route():  # FastAPI runs it in its thread pool
    _refuse()


@pytest.fixture
def client(monkeypatch):
    routes = [APIRoute("/api/oom-loop", _on_the_loop), APIRoute("/api/oom-thread", _in_a_thread), APIRoute("/api/oom-sync", _sync_route)]
    monkeypatch.setattr(main.app.router, "routes", [*routes, *main.app.router.routes])
    monkeypatch.setattr(main, "_OUT_OF_MEMORY_SAID", set())
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/api/oom-loop", "/api/oom-thread", "/api/oom-sync"])
def test_out_of_memory_is_a_503_with_a_sentence(client, path):
    answer = client.get(path)
    assert answer.status_code == 503
    assert answer.headers["Retry-After"] == "5"
    assert answer.json()["detail"].startswith("The library is short of memory")


def test_it_is_said_once_per_route_not_per_poll(client, monkeypatch):
    said = []
    monkeypatch.setattr(main.logger, "error", lambda *a, **_: said.append(a))
    for _ in range(3):
        client.get("/api/oom-loop")
    client.get("/api/oom-thread")
    assert [a[1] for a in said] == ["/api/oom-loop", "/api/oom-thread"]
    assert "more" not in said[0][2]  # the first line of DuckDB's message, not its advice
