"""`activity.throttle.power-heat-memory`: a deliberate wait is not a stall.

Seen 2026-10-11: "Processing imported pages" sat at "Waiting: you're using the Mac", 27 of 184, and the import
queue's watchdog said "Processing imported pages stalled at 27 of 184" every minute. The throttle holding the
queue's background work while the person uses the Mac is a ruling, not a fault; the watchdog says "stalled" only
when nothing is holding the work on purpose, and looks again later.
"""

from __future__ import annotations

import time

from fichero_server.execution import throttle
from fichero_server.importers import derivatives


def _watch(monkeypatch, why: dict) -> list[str]:
    said: list[str] = []
    monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.05)
    monkeypatch.setattr(throttle, "why_wait", lambda **_k: why["now"])
    monkeypatch.setattr(derivatives, "_emit_queue_progress",
                        lambda library, done, total, stalled=False: said.append("stalled") if stalled else None)
    monkeypatch.setattr(derivatives, "_emit_queue_activity", lambda path, **k: said.append(k["message"]))
    return said


def test_the_watchdog_does_not_call_a_throttled_queue_stalled(monkeypatch, tmp_path):
    why = {"now": "Waiting: you're using the Mac"}
    said = _watch(monkeypatch, why)
    library = str(tmp_path / "held-by-the-throttle.fichero")
    (tmp_path / "held-by-the-throttle.fichero").mkdir()
    with derivatives._progress_lock:
        derivatives._progress[library] = {"done": 27, "total": 184}
    try:
        derivatives._arm_stall_watchdog(library)
        time.sleep(0.3)
        assert said == [], said
        # The hold clears and still nothing moves: that is a stall, said once the watchdog looks again.
        why["now"] = None
        deadline = time.monotonic() + 3
        while not said and time.monotonic() < deadline:
            time.sleep(0.05)
        assert "Processing imported pages stalled at 27 of 184" in said
    finally:
        derivatives._disarm_stall_watchdog()
        with derivatives._progress_lock:
            derivatives._progress.pop(library, None)


def test_the_watchdog_says_nothing_into_a_library_that_is_gone(monkeypatch, tmp_path):
    """A library deleted (or moved away) while its queue was watched is not reported stalled, and nothing is written
    into it (2026-10-11: a test library's watchdog fired after teardown and wrote "stalled at 0 of 2" into a database
    that was no longer there)."""
    said = _watch(monkeypatch, {"now": None})
    library = str(tmp_path / "gone.fichero")
    with derivatives._progress_lock:
        derivatives._progress[library] = {"done": 0, "total": 2}
    try:
        derivatives._arm_stall_watchdog(library)
        time.sleep(0.3)
        assert said == [], said
        with derivatives._progress_lock:
            assert library not in derivatives._progress, "a gone library's queue is dropped"
    finally:
        derivatives._disarm_stall_watchdog()
        with derivatives._progress_lock:
            derivatives._progress.pop(library, None)
