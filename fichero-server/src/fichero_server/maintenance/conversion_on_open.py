"""Start the whole-project conversion when a library opens (#5222, #5088; ruled 2026-09-20).

`convert_project` (the preflight, the proved snapshot, the lock, the resume, the courtesy) was
built and pinned and nothing called it, so every page curated before the page model stayed one
rerun away from losing its correction (#5075). This is the one caller.

- **After the open-time migrations, never delaying the open.** `DatabaseManager.get_database`
  calls `start` once the library's migrations have run and the connection is cached; the
  work runs on a daemon thread and `start` returns at once. Pages not yet converted read
  through from their stored geometry exactly as before (`list_document_segments`).
- **The running engine only.** One thread per library in this process; `convert_project`'s own
  lock refuses a second runner anywhere else.
- **Stops at a page boundary** when the library closes (`stop`): a page is one transaction, so a
  close mid-run leaves each page fully converted or untouched, and the next open carries on.
- **Announced only through the status route** (`GET /api/conversion/status`, the app's pill).

Off under `FICHERO_SKIP_PROJECT_CONVERSION=1` (the test suite sets it, as it does the
derivative resume, so no test's library converts behind its back), and never for the engine's
global library, which holds presets, not pages.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_runs: dict[str, tuple[threading.Thread, threading.Event]] = {}
_lock = threading.Lock()


def start(db: Any, package_path: str | Path) -> threading.Thread | None:
    """Begin converting this library in the background, or do nothing. Never blocks."""
    if os.environ.get("FICHERO_SKIP_PROJECT_CONVERSION") == "1":
        return None
    from fichero_server.db.paths import is_global_library_package

    if is_global_library_package(Path(package_path)):
        return None
    key = str(package_path)
    with _lock:
        running = _runs.get(key)
        if running is not None and running[0].is_alive():
            return running[0]
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_run, args=(db, Path(package_path), stop_event),
            name="project-conversion", daemon=True,
        )
        _runs[key] = (thread, stop_event)
        thread.start()
        return thread


def _run(db: Any, package_path: Path, stop_event: threading.Event) -> None:
    from fichero_server.maintenance.project_conversion import (
        ConversionAlreadyRunning,
        convert_project,
    )

    try:
        run = convert_project(db, package_path, should_stop=stop_event.is_set)
    except ConversionAlreadyRunning as exc:
        logger.info("project conversion not started: %s", exc)
    except Exception:  # noqa: BLE001 -- a background thread: logged, and the next open retries
        # The run records every REFUSAL itself (disk, snapshot) as a verdict the status route
        # shows. What lands here is "could not reach a verdict" (ConversionPreflightFailed) or
        # the library closing under it; neither converted anything a page-level record would
        # miss, because a page is one transaction.
        logger.exception("project conversion stopped without a verdict: %s", package_path)
    else:
        if run is not None:
            logger.info("project conversion %s: %s", package_path, run.verdict.value)


def stop(package_path: str | Path | None = None, *, wait: float = 30.0) -> None:
    """Ask the runner(s) to stop at the next page boundary, and wait for them.

    Called BEFORE a library's connection is closed, so the runner never writes to a closed
    database. `None` stops every library's runner (engine shutdown)."""
    with _lock:
        keys = list(_runs) if package_path is None else [str(package_path)]
        runs = [_runs.pop(key) for key in keys if key in _runs]
    for _thread, stop_event in runs:
        stop_event.set()
    for thread, _stop_event in runs:
        if thread is not threading.current_thread():
            thread.join(wait)
