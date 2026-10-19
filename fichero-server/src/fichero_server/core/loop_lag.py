"""Say when the event loop is held up, and by what (#5843).

`/api/health` is answered on the loop, so anything that holds the loop (a blocking call in an `async def`, or a thread
that keeps the GIL for seconds, like the first `import torch` of a Kraken run) delays it, and the manager's watcher read
a slow health as a dead engine. A watcher thread asks the loop to answer a ping every `PING_SECONDS`; when the answer
comes later than `SLOW_SECONDS` it logs how late and the stack the loop thread was in, so the log names the culprit.
"""
from __future__ import annotations

import asyncio
import faulthandler
import logging
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)

PING_SECONDS = 0.5
SLOW_SECONDS = 1.0
#: A loop that has not run its heartbeat for this long gets every thread's stack dumped, again every this long (#5847).
DUMP_SECONDS = 30.0


def _arm_dump(seconds: float, file) -> None:
    """(Re)arm faulthandler's C watchdog: it needs no GIL, so it fires even when a C call holds the GIL for minutes."""
    faulthandler.cancel_dump_traceback_later()
    faulthandler.dump_traceback_later(seconds, repeat=True, file=file)


def start(loop: asyncio.AbstractEventLoop, *, ping_seconds: float = PING_SECONDS,
          slow_seconds: float = SLOW_SECONDS, dump_seconds: float = DUMP_SECONDS,
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
        while not stop.wait(ping_seconds):
            answered = threading.Event()
            asked = time.monotonic()
            try:
                loop.call_soon_threadsafe(heartbeat, answered)
            except RuntimeError:  # the loop is closed: nothing left to watch
                faulthandler.cancel_dump_traceback_later()
                return
            if answered.wait(slow_seconds):
                continue
            where = "".join(traceback.format_stack(sys._current_frames().get(loop_thread)))[-1500:]
            answered.wait()
            logger.warning("the event loop was held for %.1f s (health answers late); it was in:\n%s",
                           time.monotonic() - asked, where)

    threading.Thread(target=watch, name="loop-lag-watch", daemon=True).start()
    return stop


def stop_watchdog() -> None:
    """Engine stop: no stack dump after the loop is gone."""
    faulthandler.cancel_dump_traceback_later()
