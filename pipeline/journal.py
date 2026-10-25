"""Append-only JSONL journal; state is the journal replayed (pipeline.one-state-machine, resume-from-journal).
`intent`/`done` pairs bracket every side effect; `Lock` is the one flock dispatchers take (pipeline.journal-lock)."""
from __future__ import annotations

import fcntl
import json
import os
import time

from pipeline import STATE


def path():
    return STATE / "journal.jsonl"


def append(event: str, **fields) -> dict:
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

    def __init__(self, name: str = "journal", wait: bool = True):
        self.p, self.wait, self.fd = STATE / f"{name}.lock", wait, None

    def __enter__(self):
        self.p.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.p, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX | (0 if self.wait else fcntl.LOCK_NB))
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
