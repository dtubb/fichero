"""When heavy local work should wait, and why (`activity.throttle.power-heat-memory`, #5358).

Spotlight and Photos analysis wait on the same things: the person working at the Mac, memory
pressure, heat, and battery. The local-model lane asks `why_wait` before it starts a heavy job,
and a long job (training) asks again at each of its own boundaries. The answer is the reason the
job's row shows, or None to go ahead. No setting is added for any of this (dead-simple UX).

Work a person is waiting for (a page of a run they started) does not wait for battery or for
them to stop typing: that would stall the thing they asked for. It still waits for memory and
heat, because those are what make the Mac beachball.

Every probe degrades to "no reason" when it cannot read its signal (not macOS, a framework
missing, a sandbox refusal): an unreadable signal must never park the queue for good.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Callable

logger = logging.getLogger(__name__)

#: The person counts as using the Mac if any input arrived this recently.
IDLE_BEFORE_HEAVY_SECONDS = 30.0
#: How long a battery reading is trusted (it costs a subprocess).
BATTERY_READING_SECONDS = 30.0
#: macOS memory pressure levels (`kern.memorystatus_vm_pressure_level`): 1 normal, 2 warn, 4 critical.
_PRESSURE_WARN = 2
#: The one reason that means "let memory go", not just "wait": a long job stops on it.
MEMORY_REASON = "Waiting: memory is tight"
#: `NSProcessInfoThermalState`: 0 nominal, 1 fair, 2 serious, 3 critical.
_THERMAL_SERIOUS = 2


def _enabled() -> bool:
    # The test suite turns this off by default (tests/conftest.py): the machine running the
    # tests is often in use or on battery, and every queued job would wait. Tests of the
    # throttle turn it on and fake the signals.
    return os.environ.get("FICHERO_JOB_THROTTLE", "1") != "0"


def memory_is_tight() -> str | None:
    from fichero_server.llm.kraken_runtime import _memory_pressure_level

    level = _memory_pressure_level()
    return MEMORY_REASON if level is not None and level >= _PRESSURE_WARN else None


def mac_is_hot() -> str | None:
    try:
        from Foundation import NSProcessInfo

        state = int(NSProcessInfo.processInfo().thermalState())
    except Exception:  # noqa: BLE001 -- no reading is no reason to wait
        return None
    return "Waiting: the Mac is hot" if state >= _THERMAL_SERIOUS else None


def mac_is_in_use() -> str | None:
    try:
        import Quartz

        idle = float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
    except Exception:  # noqa: BLE001 -- no reading is no reason to wait
        return None
    return "Waiting: you're using the Mac" if idle < IDLE_BEFORE_HEAVY_SECONDS else None


_battery: tuple[float, bool] | None = None


def on_battery() -> str | None:
    global _battery
    now = time.monotonic()
    if _battery is None or now - _battery[0] > BATTERY_READING_SECONDS:
        try:
            from Foundation import NSProcessInfo

            low_power = bool(NSProcessInfo.processInfo().isLowPowerModeEnabled())
        except Exception:  # noqa: BLE001
            low_power = False
        try:
            out = subprocess.run(["/usr/bin/pmset", "-g", "ps"], capture_output=True, text=True,
                                 timeout=5).stdout
            draining = "Battery Power" in out
        except Exception:  # noqa: BLE001 -- no reading is no reason to wait
            draining = False
        _battery = (now, draining or low_power)
    return "Waiting: the Mac is on battery" if _battery[1] else None


#: (probe, also for work a person is waiting for?) -- in the order their reasons are given.
PROBES: list[tuple[Callable[[], str | None], bool]] = [
    (memory_is_tight, True),
    (mac_is_hot, True),
    (on_battery, False),
    (mac_is_in_use, False),
]


def why_wait(*, person_waiting: bool = False) -> str | None:
    """The first reason heavy local work should wait now, in words, or None."""
    if not _enabled():
        return None
    for probe, applies_when_waited_for in PROBES:
        if person_waiting and not applies_when_waited_for:
            continue
        reason = probe()
        if reason:
            return reason
    return None
