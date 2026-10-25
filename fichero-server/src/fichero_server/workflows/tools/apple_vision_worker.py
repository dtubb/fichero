"""Apple Vision in a child process of its own (#5392, `compute.apple-vision.worker-recycles-itself`).

A call stuck inside Apple's text recogniser cannot be interrupted, so it used to be an abandoned thread: it held its memory,
and past `APPLE_VISION_STUCK_CEILING` of them the engine refused every read and told the person to restart it. Here the
calls run in ONE forked child, one at a time (Vision is serial anyway). A call that does not return in time makes the
parent KILL the child; the next call starts a new one. Nothing is left stuck, the memory comes back, and the page that
timed out fails in words.

Forked, not exec'd, for the reason `db/embed_process.py` gives: the shipped engine has no Python of its own, and re-execing
its sandboxed stub hangs. The parent already has the ObjC runtime loaded (importing `vision_base` pulls in Quartz, as
`media/quartz_warm` and the page renderers do), so the child is started with OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES, as
the embedder's is; whether real Vision survives that fork is checked on the M4. `FICHERO_APPLE_VISION_START=spawn` execs a
child instead (a dev engine, which has a Python). The parent never imports `Vision` itself: only the child runs the calls.

This module imports nothing heavy, so the gate can load it without the ObjC runtime.
"""
from __future__ import annotations

import importlib
import multiprocessing
import os
import sys
import threading
from typing import Any

#: A function the child runs, named by where it lives, never pickled: "module:qualified.name".
Ref = tuple[str, str]


class WorkerTimeout(RuntimeError):
    """The child did not answer in time and was killed; the next call starts a new one."""


class WorkerBusy(RuntimeError):
    """An earlier call still holds the child and this one waited its whole time for it: nothing was killed."""


class WorkerFailure(RuntimeError):
    """The child died, or its answer could not be sent back; the page fails in these words."""


def in_process() -> bool:
    """FICHERO_APPLE_VISION_IN_PROCESS=1 runs the calls on threads in the engine, as before (tests and bare tools)."""
    return os.environ.get("FICHERO_APPLE_VISION_IN_PROCESS") == "1"


def reference(fn: Any) -> Ref | None:
    """Where the child finds `fn`, or None when it is not a module-level function a child could look up."""
    module, name = getattr(fn, "__module__", None), getattr(fn, "__qualname__", None)
    if not module or not name or "<locals>" in name:
        return None
    return module, name


def _resolve(ref: Ref) -> Any:
    module = sys.modules.get(ref[0]) or importlib.import_module(ref[0])
    target: Any = module
    for part in ref[1].split("."):
        target = getattr(target, part)
    return target


def _serve(conn: Any) -> None:
    """The child: answer calls one at a time until the pipe closes. Never returns to the engine's code."""
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
    try:
        while True:
            try:
                ref, args = conn.recv()
            except EOFError:
                break
            try:
                answer: tuple[str, Any] = ("ok", _resolve(ref)(*args))
            except BaseException as exc:  # noqa: BLE001 -- handed to the parent, which raises it for the page
                answer = ("raised", exc)
            try:
                conn.send(answer)
            except Exception as exc:  # noqa: BLE001 -- the answer would not pickle
                conn.send(("raised", WorkerFailure(f"Apple Vision's answer could not be sent back: {type(exc).__name__}: {exc}")))
    finally:
        os._exit(0)


class VisionWorker:
    """The one child, started when first needed and again after a kill."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Any = None
        self._conn: Any = None
        self.starts = 0  # how many children have been started; a test reads it
        self.recycles = 0  # how many were killed because a call did not return

    def _start(self) -> None:
        method = os.environ.get("FICHERO_APPLE_VISION_START", "fork")
        context = multiprocessing.get_context("spawn" if method == "spawn" else "fork")
        self._conn, child = context.Pipe(duplex=True)
        self._process = context.Process(target=_serve, args=(child,), daemon=True)
        self._process.start()
        child.close()
        self.starts += 1

    def _end(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass  # the pipe is already gone; the process is ended below either way
        if self._process is not None and self._process.is_alive():
            self._process.kill()
            self._process.join(5)
        self._process = self._conn = None

    def call(self, ref: Ref, args: tuple, timeout: float) -> Any:
        """Run one call in the child. WorkerTimeout (the child is killed) when it does not answer in `timeout` seconds,
        counting the wait for an earlier call; WorkerFailure when the child died; the call's own exception otherwise."""
        if not self._lock.acquire(timeout=timeout):
            raise WorkerBusy("an earlier Apple Vision call was still running")
        try:
            if self._process is None or not self._process.is_alive():
                self._end()
                self._start()
            try:
                self._conn.send((ref, args))
                if not self._conn.poll(timeout):
                    self.recycles += 1
                    self._end()
                    raise WorkerTimeout("the Apple Vision call did not return")
                kind, payload = self._conn.recv()
            except (EOFError, OSError) as exc:
                self._end()
                raise WorkerFailure("Apple Vision's worker stopped while reading this page; it starts again for the next one.") from exc
            if kind == "raised":
                raise payload
            return payload
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            self._end()


WORKER = VisionWorker()
