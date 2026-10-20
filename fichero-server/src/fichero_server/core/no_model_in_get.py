"""A GET never runs a model, at any depth (`activity.read.get-runs-no-model`, manager ruling 2026-10-19).

The static scan (`tests/unit/api/test_no_model_work_in_gets.py`) sees a handler's own body. This sees what the handler
reaches: a middleware marks every GET/HEAD request in a `ContextVar`, which `asyncio.to_thread` and the threadpool copy into
their threads, and the places a model is loaded or run (`kraken_runtime._kraken_call`, the embedder, `jobs.run_on_lane`)
call `forbid_in_get`, which raises `ModelWorkInGet` there. The route answers 503 in words: a GET returns what is stored, or
says it isn't ready; the read belongs to the model lane.

One exception (`activity.read.get-embeds-its-own-query`): a GET may embed its own query text, bounded, by `embed_query_in_get`.

Everything the request awaits keeps the mark (its tasks, `single_flight` flights, `gather`, `asyncio.to_thread`). The three
fire-and-forget sites (the auto-embed, the activity tracker's recovery, `on_background_loop`) are spawned with `spawn_free`,
and a `BackgroundTasks` function runs after the response, when the mark has ended.

Not covered: a thread started with `loop.run_in_executor` or `threading.Thread` begins with no context, so it is not marked.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import contextvars
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


def in_get() -> bool:
    mark = _get_mark.get()
    return mark is not None and mark.active


#: How long a GET waits for its own query embedding (`activity.read.get-embeds-its-own-query`).
QUERY_EMBED_SECONDS = 5.0


class QueryEmbeddingBusy(ModelWorkInGet):
    """The embedder could not answer a GET's query in time."""


# One worker: a query embed waits behind another and the wait is the bound. Its threads start with no context, so the
# embed they run is not marked.
_query_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="fichero-query-embed")


def embed_query_in_get(embed):
    """Run `embed()` (one query's vector) for a GET, within `QUERY_EMBED_SECONDS`; 503 in words if the embedder is busy or
    still loading. A late embed finishes on its thread, so the next GET finds the model loaded."""
    future = _query_pool.submit(embed)
    try:
        return future.result(timeout=QUERY_EMBED_SECONDS)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise QueryEmbeddingBusy(
            f"The search model is busy or still loading (waited {QUERY_EMBED_SECONDS:g} s). Try the search again in a moment."
        ) from None


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


def spawn_free(spawn, *args):
    """Call `spawn(*args)` (a `create_task`, a `run_coroutine_threadsafe`) with a fresh context, so the task it makes is not
    the GET that asked for it. For the known fire-and-forget sites only (the auto-embed, the activity tracker's recovery,
    `on_background_loop`); a task whose result the request awaits (a `single_flight`, a `gather`) IS the request and keeps
    the mark."""
    return contextvars.Context().run(spawn, *args)


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
