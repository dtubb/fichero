"""The engine's way out when torch is loaded (#5929, `runtime.torch.exits-cleanly`).

On macOS 27 a process that loaded Kraken's model and ran it on the GPU aborts inside torch's `MetalShaderLibrary` destructor when libc
runs the static destructors at `exit()`: the M4 shows exit -6 and an `.ips` report, after the work and the writes were done. So with
torch loaded the process leaves with `os._exit`, which skips them. A write is never lost for it: every DuckDB connection is
checkpointed and closed first (an unreplayed WAL is the index hazard), the `atexit` functions run, the logs are flushed, and if a
database cannot be closed the process takes the ordinary way out instead (it may abort, but it never leaves a write behind).
Without torch loaded nothing here does anything.
"""
from __future__ import annotations

import logging
import os
import sys


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


def leave(status: int = 0) -> None:
    """Leave with `status` by `os._exit` when torch is loaded and every database closed; otherwise return."""
    if "torch" not in sys.modules:
        return
    try:
        close_everything()
    except Exception as exc:  # noqa: BLE001 -- not closed: the ordinary exit (it may abort, but never loses a write)
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
    os._exit(status)
