"""End the test process with `os._exit` once everything is closed, so torch's exit-time destructor cannot segfault (#5903).

torch 2.14's `at::native::mps::MetalShaderLibrary::~MetalShaderLibrary` crashes when libc runs the static destructors at
`exit()`: candidate 11's whole api suite passed and the process still exited 139. It happens only with libtorch loaded, so this
runs only then. The exit code is pytest's OWN (`session.exitstatus`, saved after every other `pytest_sessionfinish`), so a failing
suite still exits non-zero. Every DuckDB connection is checkpointed and closed first, so nothing is left to replay at the next
open (the WAL-replay index hazard); if that cannot be done the process exits the ordinary way instead.
"""
from __future__ import annotations

import logging
import os
import sys

_status: int | None = None


def remember(session) -> None:
    """Save pytest's final exit status (call after the other sessionfinish hooks, which may change it)."""
    global _status
    _status = int(session.exitstatus)


def close_everything() -> None:
    """Checkpoint and close every database this process opened; raises if one is left open."""
    from fichero_server.db import app as app_module
    from fichero_server.db.manager import db_manager

    db_manager.checkpoint_all()
    db_manager.close_all()
    app_module.checkpoint_app_db()
    if app_module._app_db is not None:
        app_module._app_db.close()
    if db_manager._databases:
        raise RuntimeError(f"still open: {sorted(db_manager._databases)}")


def leave(config=None) -> None:
    """The hook body (pytest_unconfigure, last): leave with pytest's status when torch is loaded and all is closed."""
    if _status is None or "torch" not in sys.modules or hasattr(config, "workerinput"):
        return
    try:
        close_everything()
    except Exception as exc:  # noqa: BLE001 -- not closed: take the ordinary exit (it may crash, but never loses a write)
        print(f"fast exit skipped, a database could not be closed: {exc}", file=sys.stderr)
        return
    try:
        import atexit

        atexit._run_exitfuncs()
    except Exception:  # noqa: BLE001
        pass
    logging.shutdown()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 -- a closed pipe
            pass
    os._exit(_status)
