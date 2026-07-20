"""Prove the ASGI streaming bridge surfaces chunks one-at-a-time, not buffered.

This is the pure-Python mirror of the Swift `AsgiBridge`: an ASGI app is driven
on a background thread, and each `http.response.body` event is pushed onto a
`queue.Queue` as it is produced. A consumer draining the queue with a blocking
`get()` observes each chunk as it arrives (the GIL is released while `get()`
waits, so the producer thread runs).

Run with the dev venv's pytest:
    /Users/danieltubb/code/fichero/.venv/bin/python -m pytest inmemory-transport/pytest -v
"""

import asyncio
import queue
import threading
import time

# ---------------------------------------------------------------------------
# The bridge under test (identical semantics to Sources/.../AsgiBridge.swift).
# ---------------------------------------------------------------------------


def make_driver(app, scope, request_body=b""):
    """Run app(scope, receive, send) on a background thread; return the event
    queue onto which response events are pushed incrementally."""
    q: queue.Queue = queue.Queue()

    def run():
        async def receive():
            return {"type": "http.request", "body": request_body, "more_body": False}

        async def send(event):
            etype = event["type"]
            if etype == "http.response.start":
                q.put(("start", int(event["status"]), event.get("headers", [])))
            elif etype == "http.response.body":
                q.put(("body", event.get("body", b""), bool(event.get("more_body", False))))

        try:
            asyncio.run(app(scope, receive, send))
            q.put(("done",))
        except BaseException as exc:  # noqa: BLE001
            q.put(("error", repr(exc)))

    threading.Thread(target=run, daemon=True).start()
    return q


def _scope(path="/"):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 0),
        "root_path": "",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

INTERVAL = 0.3


def _streaming_app(n_chunks=3, interval=INTERVAL):
    """An async-generator-driven ASGI app that emits chunks spaced `interval`s
    apart (more_body:true between them)."""

    async def app(scope, receive, send):
        assert scope["type"] == "http"
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )

        async def chunks():
            for i in range(n_chunks):
                await asyncio.sleep(interval)
                yield f"chunk{i}".encode()

        i = 0
        async for body in chunks():
            i += 1
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": i < n_chunks,
                }
            )

    return app


def test_chunks_are_surfaced_incrementally():
    """The consumer must see each chunk as it is produced, not all at the end."""
    q = make_driver(_streaming_app(), _scope("/stream"))

    t0 = time.time()
    arrivals = []  # (text, elapsed)
    status = None
    while True:
        item = q.get()
        tag = item[0]
        if tag == "start":
            status = item[1]
        elif tag == "body":
            arrivals.append((item[1].decode(), time.time() - t0))
        elif tag == "done":
            break
        elif tag == "error":
            raise AssertionError(f"ASGI app errored: {item[1]}")

    assert status == 200
    assert [a[0] for a in arrivals] == ["chunk0", "chunk1", "chunk2"]

    first = arrivals[0][1]
    last = arrivals[-1][1]
    gap = last - first

    # THE KEY ASSERTION: a buffering driver would deliver every chunk at ~the
    # same (final) time; incremental delivery spaces them ~INTERVAL apart.
    print(f"\narrivals: {[(t, round(e, 2)) for t, e in arrivals]}")
    print(f"first={first:.2f}s last={last:.2f}s gap={gap:.2f}s")

    assert gap > INTERVAL * 1.5, (
        f"chunk0 and chunk2 arrived only {gap:.2f}s apart — looks buffered"
    )
    assert first < INTERVAL * 2.0, (
        f"first chunk arrived at {first:.2f}s — too late, looks buffered"
    )
    # Each successive gap ~= one interval.
    for a, b in zip(arrivals, arrivals[1:]):
        step = b[1] - a[1]
        assert step > INTERVAL * 0.5, f"gap between {a[0]} and {b[0]} too small: {step:.2f}s"


def test_body_content_and_completion():
    """Concatenated body is correct and the driver signals clean completion."""
    q = make_driver(_streaming_app(n_chunks=4, interval=0.05), _scope("/stream"))
    body = b""
    done = False
    while True:
        item = q.get()
        if item[0] == "body":
            body += item[1]
        elif item[0] == "done":
            done = True
            break
        elif item[0] == "error":
            raise AssertionError(item[1])
    assert done
    assert body == b"chunk0chunk1chunk2chunk3"
