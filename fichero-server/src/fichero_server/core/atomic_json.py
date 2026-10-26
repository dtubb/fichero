"""One way to write a model card or marker: whole or not at all, one writer per path at a time (#6137, from #6136).

A plain `write_text` leaves a half-written file if the engine stops mid-write, and two read-modify-writes of one card lose
one of the two. Every card/marker writer goes through `write_json_atomic`; a writer that reads first holds `card_lock`."""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


def card_lock(path: Path) -> threading.Lock:
    """The one lock for a path (shared by every writer of that file in this process)."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(path), threading.Lock())


def write_json_atomic(path: Path, data: Any, *, indent: int | None = 1) -> None:
    """Write `data` as JSON to a temp file beside `path`, then `os.replace` it: a reader sees the old file or the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(data, indent=indent), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
