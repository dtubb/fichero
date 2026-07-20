import Foundation

/// The reusable core of the streaming bridge — a small chunk of Python that runs
/// an ASGI app on a background *Python* thread and surfaces each response event
/// through a thread-safe `queue.Queue`.
///
/// Why a `queue.Queue` and not a Swift callback exposed to Python?
///  - `queue.Queue.get()` blocks by waiting on a `threading.Condition`, and
///    CPython releases the GIL while blocked. So when Swift (on the worker thread)
///    calls `q_get`, the producer thread running the ASGI app gets the GIL and
///    can push the next chunk. The handoff is genuinely incremental: Swift wakes
///    up per event, not once at the end.
///  - It sidesteps the danger of Python calling *into* Swift (via PythonKit
///    `PythonFunction`) from a thread that doesn't own the right GIL state.
///
/// The producer puts tagged tuples onto the queue:
///   ("start",  status:int, headers:[(str,str)])   — from http.response.start
///   ("body",   body:bytes, more_body:bool)         — per http.response.body event
///   ("done",)                                       — app returned cleanly
///   ("error",  message:str)                         — app raised
enum AsgiBridge {
    static let source = #"""
import threading
import asyncio
import queue
import traceback


def make_scope(method, raw_path, headers):
    """Build a minimal ASGI HTTP scope. `headers` is a list of (str, str)."""
    if "?" in raw_path:
        path, qs = raw_path.split("?", 1)
    else:
        path, qs = raw_path, ""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": qs.encode("utf-8"),
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers],
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 0),
        "root_path": "",
    }


def make_driver(app, scope, request_body=b""):
    """Start `app(scope, receive, send)` on a background thread; return the queue
    onto which response events are pushed incrementally."""
    q = queue.Queue()

    def run():
        async def receive():
            # Single-shot request body, then keep the connection "open" but idle.
            return {"type": "http.request", "body": request_body, "more_body": False}

        async def send(event):
            etype = event["type"]
            if etype == "http.response.start":
                headers = [
                    (k.decode("latin-1"), v.decode("latin-1"))
                    for k, v in event.get("headers", [])
                ]
                q.put(("start", int(event["status"]), headers))
            elif etype == "http.response.body":
                q.put(("body", event.get("body", b""), bool(event.get("more_body", False))))

        try:
            asyncio.run(app(scope, receive, send))
            q.put(("done",))
        except BaseException as exc:  # noqa: BLE001 - surface everything to Swift
            q.put(("error", repr(exc) + "\n" + traceback.format_exc()))

    threading.Thread(target=run, daemon=True).start()
    return q


def q_get(q):
    """Blocking get. Releases the GIL while waiting, so the producer thread runs."""
    return q.get()


def exec_module(code, name="_dyn"):
    """Exec `code` into a fresh module namespace and return it. Used by tests to
    define synthetic ASGI apps or import the real app."""
    import types

    m = types.ModuleType(name)
    exec(code, m.__dict__)
    return m
"""#
}
