"""Append-only JSONL journal: for a worker the truth is its journal, git and the handoff file
(dev-workflows.run.records-are-truth; ported from pipeline/journal.py 2026-11-01). `intent`/`done` pairs bracket every
side effect; `Lock` is the one flock the watcher and the test runs take."""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

# The Builder's state directory: FICHERO_BUILDER_STATE, else $XDG_STATE_HOME/fichero-builder, else ~/.local/state/fichero-builder.
STATE = Path(os.environ.get("FICHERO_BUILDER_STATE") or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
             / "fichero-builder")


def path():
    return STATE / "journal.jsonl"


REQUIRED = {"item": ("issue", "task", "title", "window", "worktree", "ids", "key"), "since": ("issue", "task", "sha", "key")}


def append(event: str, **fields) -> dict:
    missing = [k for k in REQUIRED.get(event, ()) if k not in fields]
    if missing:  # an incomplete item or since line can never be written again
        raise ValueError(f"journal {event} line lacks {', '.join(missing)}")
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **fields}
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def read() -> list[dict]:
    p = path()
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []


def open_intents() -> list[dict]:
    """Intent lines with no matching done line: side effects to reconcile against the world on resume."""
    key = lambda e: (e["task"], e["what"], e.get("ref", ""))  # noqa: E731
    done = {key(e) for e in read() if e["event"] == "done"}
    return [e for e in read() if e["event"] == "intent" and key(e) not in done]


class Lock:
    """flock on a file under the state dir; wait=False raises BlockingIOError when someone else holds it."""

    WARN_S = 30  # a wait longer than this is a row (soak 2026-11-02: a landing sat 16 min in flock with no word)

    def __init__(self, name: str = "journal", wait: bool = True, what: str = ""):
        self.name, self.p, self.wait, self.fd, self.what = name, STATE / f"{name}.lock", wait, None, what

    def __enter__(self):
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.p, os.O_RDWR | os.O_CREAT, 0o644)
        if not self.wait or self.name == "journal":  # the journal's own lock is held for a line: never a row about itself
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | (0 if self.wait else fcntl.LOCK_NB))
            except BlockingIOError:
                os.close(self.fd)  # a refused try keeps no descriptor (speed 3 retries every second)
                raise
        else:
            t0, said = time.time(), False
            while True:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not said and time.time() - t0 > self.WARN_S:
                        holder = os.pread(self.fd, 200, 0).decode(errors="replace").strip() or "?"
                        append("lock", state="waiting", name=self.name, holder=holder, what=self.what, pid=os.getpid(),
                               detail=f"waiting for {self.name} held by {holder}")
                        said = True
                        print(f"waiting for the {self.name} lock, held by {holder} ...", file=sys.stderr, flush=True)  # a CLI says so (manager 2026-11-02)
                    time.sleep(1)
            if said:
                append("lock", state="acquired", name=self.name, what=self.what, pid=os.getpid(), seconds=int(time.time() - t0))
        if self.name != "journal":  # who holds it, for the next one who waits
            os.ftruncate(self.fd, 0)
            os.pwrite(self.fd, f"{os.getpid()} {self.what}".encode(), 0)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def ladder_slots(n: int) -> list[str]:
    """The ladder locks [check].parallel allows: `ladder`, `ladder-2`, ... (speed 3)."""
    return ["ladder"] + [f"ladder-{i}" for i in range(2, max(1, n) + 1)]


def ladder_slots_known() -> list[str]:
    """Every ladder lock ever used here: a landing that must not pull a pinned copy from under a check probes them all."""
    return sorted({"ladder", *(p.name[:-5] for p in STATE.glob("ladder-*.lock") if p.name[7:-5].isdigit())})


HEAVY_ENV = "FICHERO_HEAVY_HELD"  # set for what `builder heavy` runs: it already holds the lock


YIELD_POLL_S = 2  # how often a yielding job looks again for waiting checks


def heavy_waiters() -> int:
    """Checks waiting for the heavy lock right now: one `heavy-wait.<pid>.<thread>` file each, a dead pid's file is dropped."""
    n = 0
    for p in STATE.glob("heavy-wait.*"):
        try:
            os.kill(int(p.name.split(".")[1]), 0)
            n += 1
        except (ValueError, IndexError, OSError):
            p.unlink(missing_ok=True)
    return n


@contextlib.contextmanager
def heavy(what: str, yields: bool = False):
    """One heavy job at a time on this machine (owner 2026-11-02): xcodebuild, the full engine suite and the guards rung take it,
    and so do check, build --dev, verify-all and `builder test` through those. A wait over Lock.WARN_S says who holds it. A
    child of `builder heavy` already holds it and passes straight through. Quick things (ruff, swiftlint, one test file) never ask.
    A waiting job leaves a marker; a `yields` job (the post-landing dev build) takes the lock only while no marker stands, so a queued
    check always outranks it (manager 2026-11-03: a harness-only batch's build held it 46 min while guards waited)."""
    if os.environ.get(HEAVY_ENV):
        yield
        return
    lk = Lock("heavy", what=what)
    if yields:
        said = False
        while True:
            if not heavy_waiters():
                try:
                    lk = Lock("heavy", wait=False, what=what)
                    lk.__enter__()
                    break
                except BlockingIOError:
                    pass
            if not said:
                append("lock", state="yielding", name="heavy", what=what, pid=os.getpid(), detail="a check waits for the heavy lock: the build waits")
                said = True
            time.sleep(YIELD_POLL_S)
    else:
        marker = STATE / f"heavy-wait.{os.getpid()}.{threading.get_ident()}"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(what)
        try:
            lk.__enter__()
        finally:
            marker.unlink(missing_ok=True)
    try:
        yield
    finally:
        lk.__exit__(None, None, None)
