"""A log line that repeats is written a few times, then collapsed (`engine.repeated-log-line-collapses`).

One warning was written 380,611 times into engine.log. The key is the message TEMPLATE (the arguments may differ),
so "Failed to create embedding for doc1: x" and "... for doc2: y" are the same line.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Admission:
    write: bool
    #: How many repeats were held back in the window that just ended; written once, before this line.
    summary: int | None = None


class RepeatCollapser:
    def __init__(self, limit: int = 5, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._lock = threading.Lock()
        self._state: dict[str, list[float]] = {}          # template -> [window start, count, held back]

    def admit(self, template: str, now: float | None = None) -> Admission:
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._state.get(template)
            if state is None or now - state[0] >= self.window_s:
                summary = int(state[2]) if state and state[2] > 0 else None
                if len(self._state) > 1000:                # ponytail: drop expired windows; a held count may go unsummarised
                    self._state = {k: v for k, v in self._state.items() if now - v[0] < self.window_s}
                self._state[template] = [now, 1, 0]
                return Admission(True, summary)
            state[1] += 1
            if state[1] <= self.limit:
                return Admission(True)
            state[2] += 1
            return Admission(False)


_DEFAULT = RepeatCollapser()


def log_collapsed(
    logger: logging.Logger,
    level: int,
    template: str,
    *args: object,
    collapser: RepeatCollapser | None = None,
    now: float | None = None,
    extra: dict | None = None,
) -> None:
    """`extra` reaches both records, so a site that already `note`d the failure ledger keeps its `ledgered` flag (#6314)."""
    admission = (collapser or _DEFAULT).admit(template, now)
    if admission.summary:
        logger.log(level, "%s — repeated %d times in the last minute", template, admission.summary, extra=extra)
    if admission.write:
        logger.log(level, template, *args, extra=extra)
