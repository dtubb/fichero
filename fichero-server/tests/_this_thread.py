"""A fake for `time.sleep` that stands in for the calling test's thread only.

`monkeypatch.setattr(module.time, "sleep", fake)` replaces the one global `time.sleep`: every lane, watchdog or worker
thread an earlier test left running then sleeps through the fake too, its sleeps counted as the test's (the
order-dependent 5819 / 5806 failures) or, with a no-op fake, spinning. Other threads keep the real sleep."""
from __future__ import annotations

import threading
import time
from typing import Callable

_real_sleep = time.sleep


def sleep_here(fake: Callable[[float], object]) -> Callable[[float], None]:
    me = threading.get_ident()

    def sleep(seconds: float) -> None:
        if threading.get_ident() == me:
            fake(seconds)
        else:
            _real_sleep(seconds)

    return sleep
