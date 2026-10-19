"""A GET never runs a model, at any depth (`activity.read.get-runs-no-model`, manager ruling 2026-10-19).

The static scan (`tests/unit/api/test_no_model_work_in_gets.py`) sees a handler's own body. This sees what the handler
reaches: a middleware marks every GET/HEAD request in a `ContextVar`, which `asyncio.to_thread` and the threadpool copy into
their threads, and the places a model is loaded or run (`kraken_runtime._kraken_call`, the embedder, `jobs.run_on_lane`)
call `forbid_in_get`, which raises `ModelWorkInGet` there. The route answers 503 in words: a GET returns what is stored, or
says it isn't ready; the read belongs to the model lane.

Not covered: a thread started with `loop.run_in_executor` or `threading.Thread` begins with no context, so it is not marked.
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar

_get_path: ContextVar[str | None] = ContextVar("fichero_get_request_path", default=None)


class ModelWorkInGet(RuntimeError):
    """Model work was asked for inside a GET."""


def forbid_in_get(what: str) -> None:
    """Raise if this code is running for a GET request."""
    path = _get_path.get()
    if path is not None:
        raise ModelWorkInGet(
            f"{what.capitalize()} was asked for by GET {path}. A GET returns what is stored, or says it isn't ready; "
            "the reading is done by the model lane, one page at a time."
        )


@contextlib.contextmanager
def marked_get(path: str):
    """Mark the code inside as running for a GET (the middleware's job; a test's too)."""
    token = _get_path.set(path)
    try:
        yield
    finally:
        _get_path.reset(token)


class NoModelWorkInGet:
    """Pure ASGI middleware: marks GET and HEAD requests for the whole of their handling."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("method") in ("GET", "HEAD"):
            with marked_get(scope.get("path", "")):
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def install_handler(app) -> None:
    """Answer `ModelWorkInGet` as 503 with its words."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(ModelWorkInGet)
    async def _refuse(_request: Request, exc: ModelWorkInGet) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
