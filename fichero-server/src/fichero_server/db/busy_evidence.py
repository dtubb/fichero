"""Who is inside a DuckDB call right now -- the evidence a busy refusal names (#5185).

Its own module, apart from `db/manager.py`, because this reads thread identity (to leave out the
calling thread) and the connection pool must never touch it: the #2508 guard
(`test_single_connection_guardrail.py`) forbids `get_ident` in the pool module outright, so a
diagnostic there would be indistinguishable from a per-thread pool key.
"""

from __future__ import annotations

import sys
import threading
import traceback


def threads_in_a_database_call() -> list[str]:
    """Other threads executing a DuckDB statement right now, as "thread: engine frame" -- the
    evidence a busy refusal carries when the writer is a connection the manager does not own
    (#5185): which code, on which thread, is writing at that moment."""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        if ident == threading.get_ident():
            continue
        stack = traceback.extract_stack(frame)
        if not stack or "execute" not in (stack[-1].line or ""):
            continue
        ours = [f for f in stack if "/fichero_server/" in f.filename.replace("\\", "/")]
        where = ours[-1] if ours else stack[-1]
        path = where.filename.replace("\\", "/").rsplit("/fichero_server/", 1)[-1]
        out.append(f"{names.get(ident, ident)}: {path}:{where.lineno} {where.name}")
    return out
