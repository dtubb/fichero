"""Apple Vision in a child process of its own (#5392, `compute.apple-vision.worker-recycles-itself`).

A call stuck inside Apple's text recogniser cannot be interrupted, so it used to be an abandoned thread: it held its memory,
and past `APPLE_VISION_STUCK_CEILING` of them the engine refused every read and told the person to restart it. Here the
calls run in ONE forked child, one at a time (Vision is serial anyway). A call that does not return in time makes the
parent KILL the child; the next call starts a new one. Nothing is left stuck, the memory comes back, and the page that
timed out fails in words.

By default the calls run on the engine's own threads (`vision_base._start_apple_vision_page`), behind the gate and its deadline:
a child forked without exec crashed in Vision (SIGSEGV on the child side of fork, an M1, #7084), and the shipped engine has no
Python of its own to exec (its sandboxed stub hangs). `FICHERO_APPLE_VISION_START=spawn` starts an exec'd child instead (a dev
engine, which has a Python); that child is killed when a call does not return, and a child that crashes fails its page at once
with the signal named. The parent never imports `Vision` itself.
"""
from __future__ import annotations

import importlib
import multiprocessing
import os
import signal
import sys
import threading
import time
from typing import Any

#: A function the child runs, named by where it lives, never pickled: "module:qualified.name".
Ref = tuple[str, str]


class WorkerTimeout(RuntimeError):
    """The child did not answer in time and was killed; the next call starts a new one."""


#: Seconds a spawned child may take to start before its first call.
START_SECONDS = 60.0

_CRASH_SIGNALS = {int(n): n.name for n in (signal.SIGSEGV, signal.SIGBUS, signal.SIGABRT, signal.SIGILL, signal.SIGFPE, signal.SIGTRAP)}


class WorkerBusy(RuntimeError):
    """An earlier call still holds the child and this one waited its whole time for it: nothing was killed."""


class WorkerFailure(RuntimeError):
    """The child died, or its answer could not be sent back; the page fails in these words."""


def in_process() -> bool:
    """True (the default) when the calls run on threads in the engine; False only for FICHERO_APPLE_VISION_START=spawn.
    A fork start is refused: Vision does not survive a fork without exec (#7084)."""
    method = os.environ.get("FICHERO_APPLE_VISION_START", "")
    if method not in ("", "spawn"):
        raise RuntimeError(f"FICHERO_APPLE_VISION_START={method!r}: only 'spawn' is supported; Apple Vision cannot run in a forked child")
    return os.environ.get("FICHERO_APPLE_VISION_IN_PROCESS") == "1" or method != "spawn"


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
    try:
        conn.send("ready")  # the engine charges the child's start (it imports PyObjC) to no page's deadline
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
        context = multiprocessing.get_context("spawn")  # exec'd, never forked (#7084)
        self._conn, child = context.Pipe(duplex=True)
        self._process = context.Process(target=_serve, args=(child,), daemon=True)
        self._process.start()
        child.close()
        self.starts += 1
        try:
            if not self._conn.poll(START_SECONDS) or self._conn.recv() != "ready":
                raise EOFError
        except (EOFError, OSError) as exc:
            self._end()
            raise WorkerFailure("Apple Vision's worker did not start; it starts again for the next one.") from exc

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

    def _how_it_ended(self) -> str:
        """A phrase for how the child ended: " (killed by signal N)" or " (exited with code N)". Empty when the child is not
        one the engine can wait on (a seed's worker has no exit code here) or did not end within a second."""
        join = getattr(self._process, "join", None)
        if join is None or not hasattr(self._process, "exitcode"):
            return ""
        join(1)
        code = self._process.exitcode
        if code is None:
            return ""
        return f" (killed by signal {-code})" if code < 0 else f" (exited with code {code})"

    def call(self, ref: Ref, args: tuple, timeout: float) -> Any:
        """Run one call in the child. WorkerTimeout (the child is killed) when it does not answer in `timeout` seconds;
        WorkerBusy (nothing killed) when an earlier call kept the child for the whole of `timeout`; WorkerFailure when the child died; the call's own exception otherwise."""
        if not self._lock.acquire(timeout=timeout):
            raise WorkerBusy("an earlier Apple Vision call was still running")
        try:
            began = time.monotonic()
            if self._process is None or not self._process.is_alive():
                self._end()
                self._start()
            timeout = max(timeout - (time.monotonic() - began), 0.05)  # the caller's deadline covers the child's start too
            try:
                self._conn.send((ref, args))
                if not self._conn.poll(timeout):
                    self.recycles += 1
                    self._end()
                    raise WorkerTimeout("the Apple Vision call did not return")
                kind, payload = self._conn.recv()
            except (EOFError, OSError) as exc:
                how = self._how_it_ended()
                self._end()
                crash = _CRASH_SIGNALS.get(int(how.rsplit(" ", 1)[-1].rstrip(")"))) if "killed by signal" in how else None
                if crash:  # the same page would crash the same way: the words do not name a passing cause (page_retry)
                    raise WorkerFailure(f"Apple Vision's worker crashed ({crash}) while reading this page; this page was not read again.") from exc
                raise WorkerFailure(f"Apple Vision's worker stopped while reading this page{how}; it starts again for the next one.") from exc
            if kind == "raised":
                raise payload
            return payload
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            self._end()


WORKER = VisionWorker()
