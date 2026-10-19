"""Say when the event loop is held up, and by what (#5843).

`/api/health` is answered on the loop, so anything that holds the loop (a blocking call in an `async def`, or a thread
that keeps the GIL for seconds, like the first `import torch` of a Kraken run) delays it, and the manager's watcher read
a slow health as a dead engine. A watcher thread asks the loop to answer a ping every `PING_SECONDS`; when the answer
comes later than `SLOW_SECONDS` it logs how late and the stack the loop thread was in, so the log names the culprit.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)

PING_SECONDS = 0.5
SLOW_SECONDS = 1.0


def start(loop: asyncio.AbstractEventLoop, *, ping_seconds: float = PING_SECONDS,
          slow_seconds: float = SLOW_SECONDS) -> threading.Event:
    """Watch `loop` from a daemon thread until the returned event is set. The loop's thread is the one calling this."""
    stop = threading.Event()
    loop_thread = threading.get_ident()

    def watch() -> None:
        while not stop.wait(ping_seconds):
            answered = threading.Event()
            asked = time.monotonic()
            try:
                loop.call_soon_threadsafe(answered.set)
            except RuntimeError:  # the loop is closed: nothing left to watch
                return
            if answered.wait(slow_seconds):
                continue
            where = "".join(traceback.format_stack(sys._current_frames().get(loop_thread)))[-1500:]
            answered.wait()
            logger.warning("the event loop was held for %.1f s (health answers late); it was in:\n%s",
                           time.monotonic() - asked, where)

    threading.Thread(target=watch, name="loop-lag-watch", daemon=True).start()
    return stop
