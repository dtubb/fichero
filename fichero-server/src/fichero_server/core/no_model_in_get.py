"""A GET never runs a model, at any depth (`activity.read.get-runs-no-model`, manager ruling 2026-10-19).

The static scan (`tests/unit/api/test_no_model_work_in_gets.py`) sees a handler's own body. This sees what the handler
reaches: a middleware marks every GET/HEAD request in a `ContextVar`, which `asyncio.to_thread` and the threadpool copy into
their threads, and the places a model is loaded or run (`kraken_runtime._kraken_call`, the embedder, `jobs.run_on_lane`)
call `forbid_in_get`, which raises `ModelWorkInGet` there. The route answers 503 in words: a GET returns what is stored, or
says it isn't ready; the read belongs to the model lane.

A task the GET spawned (`create_task`) and a `BackgroundTasks` function copy the mark, but it ends when the response is
complete, so they run free after it; work awaited INSIDE the request (including `asyncio.to_thread`) is the GET and is refused.

Not covered: a thread started with `loop.run_in_executor` or `threading.Thread` begins with no context, so it is not marked.
"""
from __future__ import annotations

import contextlib
from contextvars import ContextVar


class _Mark:
    """One GET request's mark. Active while the request is answered; it ends when the response's last byte is sent, so a
    task the GET spawned, or a `BackgroundTasks` function, that runs after that is not the GET and is not refused."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.active = True


_get_mark: ContextVar[_Mark | None] = ContextVar("fichero_get_request_mark", default=None)


class ModelWorkInGet(RuntimeError):
    """Model work was asked for inside a GET."""


def forbid_in_get(what: str) -> None:
    """Raise if this code is running for a GET request."""
    mark = _get_mark.get()
    if mark is not None and mark.active:
        raise ModelWorkInGet(
            f"{what.capitalize()} was asked for by GET {mark.path}. A GET returns what is stored, or says it isn't ready; "
            "the reading is done by the model lane, one page at a time."
        )


@contextlib.contextmanager
def marked_get(path: str):
    """Mark the code inside as running for a GET (the middleware's job; a test's too)."""
    mark = _Mark(path)
    token = _get_mark.set(mark)
    try:
        yield mark
    finally:
        mark.active = False
        _get_mark.reset(token)


class NoModelWorkInGet:
    """Pure ASGI middleware: marks GET and HEAD requests for the whole of their handling."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("method") in ("GET", "HEAD"):
            with marked_get(scope.get("path", "")) as mark:
                async def watching(message) -> None:
                    # The response is complete: what runs after it (background tasks, a task the GET left running) is
                    # no longer the GET.
                    if message["type"] == "http.response.body" and not message.get("more_body", False):
                        mark.active = False
                    await send(message)

                await self.app(scope, receive, watching)
        else:
            await self.app(scope, receive, send)


def install_handler(app) -> None:
    """Answer `ModelWorkInGet` as 503 with its words."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(ModelWorkInGet)
    async def _refuse(_request: Request, exc: ModelWorkInGet) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
