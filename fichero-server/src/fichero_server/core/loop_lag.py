"""Say when the event loop is held up, and by what (#5843).

`/api/health` is answered on the loop, so anything that holds the loop (a blocking call in an `async def`, or a thread
that keeps the GIL for seconds, like the first `import torch` of a Kraken run) delays it, and the manager's watcher read
a slow health as a dead engine. A watcher thread asks the loop to answer a ping every `PING_SECONDS`; when the answer
comes later than `SLOW_SECONDS` it logs how late and the stack the loop thread was in, so the log names the culprit.

The held engine is the one the app restarts, so a live health field cannot say what held it. The watcher therefore also
writes the last stall (seconds and `module:function` only, no paths or arguments) to `previous_stall.json` under the state
root, and the NEXT engine reports it once in `GET /api/health` `dependencies['previous_stall']` and deletes the file
(`activity.engine.restart-says-why`). The file is only touched from the watcher thread, never on the event loop.
"""
from __future__ import annotations

import asyncio
import faulthandler
import json
import logging
import os
import re
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)

PING_SECONDS = 0.5
SLOW_SECONDS = 1.0
#: A loop that has not run its heartbeat for this long gets every thread's stack dumped, again every this long (#5847).
DUMP_SECONDS = 30.0
#: While a hold lasts, its record is rewritten this often (seconds held, the frame the loop is in now), so an engine killed
#: after a long hold leaves the long figure, not the first one (## 517).
RECORD_SECONDS = 2.0


STALL_FILE = "previous_stall.json"
_FRAME = re.compile(r"^[\w.]+:[\w<>]+$")  # module:function, nothing else: health is unauthenticated


def _stall_path():
    from fichero_server.db.paths import server_state_dir

    return server_state_dir() / STALL_FILE


def culprit(frame) -> str:
    """`module:function` of the innermost fichero_server frame (else the innermost frame) the loop thread is in."""
    best = None
    while frame is not None:
        name = f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_name}"
        if best is None:
            best = name
        if name.startswith("fichero_server"):
            return name
        frame = frame.f_back
    return best or "?"


def record_stall(frame_name: str, seconds: float) -> None:
    """Write the last stall atomically (tmp + replace). Watcher thread only; a failure is logged, never raised."""
    try:
        path = _stall_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"frame": frame_name, "seconds": round(seconds)}))
        os.replace(tmp, path)
    except OSError:  # file IO only; anything else is a bug and should surface (#4420 seam)
        logger.warning("could not record the loop stall", exc_info=True)


def clear_stall() -> None:
    """The loop answered again, or the engine is stopping cleanly: only a stall the engine died in stays on disk."""
    try:
        _stall_path().unlink(missing_ok=True)
    except OSError:  # file IO only (#4420 seam)
        logger.warning("could not clear the loop stall record", exc_info=True)


def take_previous_stall() -> str | None:
    """Read the previous engine's stall once and delete it: `'41s in kraken_runtime:load_model'`, or None. A corrupt
    or missing file is ignored (logged). Call from a thread, not the event loop."""
    try:
        path = _stall_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            frame, seconds = data["frame"], int(data["seconds"])
            if not (isinstance(frame, str) and _FRAME.match(frame)):
                raise ValueError("frame is not module:function")
        except Exception:
            logger.warning("ignoring an unreadable loop-stall record", exc_info=True)
            return None
        finally:
            path.unlink(missing_ok=True)
        return f"{seconds}s in {frame}"
    except Exception:
        logger.warning("could not read the loop-stall record", exc_info=True)
        return None


def _dump_enabled() -> bool:
    """`FICHERO_LOOP_DUMP=0` leaves faulthandler's one process-wide dump timer alone. A test run sets it: the suite arms that
    timer itself for a hung part, and the engine's re-arming every heartbeat would replace it (the watcher still logs and
    records a stall)."""
    return os.environ.get("FICHERO_LOOP_DUMP", "1") != "0"


def _cancel_dump() -> None:
    if _dump_enabled():
        faulthandler.cancel_dump_traceback_later()


def _arm_dump(seconds: float, file) -> None:
    """(Re)arm faulthandler's C watchdog: it needs no GIL, so it fires even when a C call holds the GIL for minutes."""
    if not _dump_enabled():
        return
    faulthandler.cancel_dump_traceback_later()
    faulthandler.dump_traceback_later(seconds, repeat=True, file=file)


def start(loop: asyncio.AbstractEventLoop, *, ping_seconds: float = PING_SECONDS,
          slow_seconds: float = SLOW_SECONDS, dump_seconds: float = DUMP_SECONDS, record_seconds: float = RECORD_SECONDS,
          dump_file=None) -> threading.Event:
    """Watch `loop` from a daemon thread until the returned event is set. The loop's thread is the one calling this."""
    stop = threading.Event()
    loop_thread = threading.get_ident()
    dump_file = sys.stderr if dump_file is None else dump_file  # the engine's stderr is its log

    def heartbeat(answered: threading.Event) -> None:  # runs ON the loop: a frozen loop stops re-arming, and the watchdog fires
        try:
            _arm_dump(dump_seconds, dump_file)
        except (ValueError, OSError, AttributeError):  # a stderr with no file descriptor (captured): no watchdog
            pass
        answered.set()

    try:
        _arm_dump(dump_seconds, dump_file)
    except (ValueError, OSError, AttributeError):
        pass

    def watch() -> None:
        from fichero_server import startup_warnings

        startup_warnings.set_previous_stall(take_previous_stall())
        while not stop.wait(ping_seconds):
            answered = threading.Event()
            asked = time.monotonic()
            try:
                loop.call_soon_threadsafe(heartbeat, answered)
            except RuntimeError:  # the loop is closed: nothing left to watch
                _cancel_dump()
                clear_stall()
                return
            if answered.wait(slow_seconds):
                continue
            frame = sys._current_frames().get(loop_thread)
            where = "".join(traceback.format_stack(frame))[-1500:]
            name = culprit(frame)
            record_stall(name, time.monotonic() - asked)  # now: the app may kill this engine before the loop is free
            while not answered.wait(record_seconds):
                name = culprit(sys._current_frames().get(loop_thread))
                record_stall(name, time.monotonic() - asked)
            clear_stall()  # recovered: a normal relaunch must not report it
            logger.warning("the event loop was held for %.1f s (health answers late); it was in:\n%s",
                           time.monotonic() - asked, where)
        clear_stall()  # stopped cleanly (ponytail: a daemon thread, so a very fast exit may skip this; a stall record only exists mid-hold anyway)

    threading.Thread(target=watch, name="loop-lag-watch", daemon=True).start()
    return stop


def stop_watchdog() -> None:
    """Engine stop: no stack dump after the loop is gone."""
    _cancel_dump()
