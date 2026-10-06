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
#: How every memory reason begins: the one reason that means "let memory go", not just "wait" (a long
#: job stops on it). The full reason (`memory_short`) goes on to give the two numbers it compared.
MEMORY_REASON = "Waiting: memory is tight"
#: `NSProcessInfoThermalState`: 0 nominal, 1 fair, 2 serious, 3 critical.
_THERMAL_SERIOUS = 2


def _enabled() -> bool:
    # The test suite turns this off by default (tests/conftest.py): the machine running the
    # tests is often in use or on battery, and every queued job would wait. Tests of the
    # throttle turn it on and fake the signals.
    return os.environ.get("FICHERO_JOB_THROTTLE", "1") != "0"


#: `kern.memorystatus_vm_pressure_level` 4 is critical.
_PRESSURE_CRITICAL = 4
_THERMAL_NAMES = ("nominal", "fair", "serious", "critical")


# The readings. Each probe below and `machine_state` (the Activity popover's "this Mac" line,
# #5415) read the Mac through these, so the popover shows exactly what the throttle acts on.

def memory_pressure_level() -> int | None:
    """The raw pressure level (1 normal, 2 warn, 4 critical), or None when unreadable."""
    from fichero_server.llm.kraken_runtime import _memory_pressure_level

    return _memory_pressure_level()


def memory_available_bytes() -> int | None:
    """Memory this Mac can hand out now (free + inactive + speculative pages), or None when unreadable."""
    from fichero_server.llm.kraken_runtime import _available_memory_bytes

    return _available_memory_bytes()


def heavy_work_need_bytes() -> int:
    """What heavy local work needs free to start: Kraken's measured floor (#4987), the one number."""
    from fichero_server.llm.kraken_runtime import _kraken_memory_need_bytes

    return _kraken_memory_need_bytes()


def memory_short(
    *,
    available_bytes: Callable[[], int | None] | None = None,
    pressure_level: Callable[[], int | None] | None = None,
) -> str | None:
    """THE memory check (#5524): why heavy local work must wait for memory now, in words with the two
    numbers compared, or None to go ahead. The lane's throttle asks it before it hands out a job and
    Kraken's guard asks it again just before a page loads (`kraken_runtime.assert_memory_available_for_
    kraken`): one rule, one number, so the throttle can no longer release a job the guard then fails
    (they compared different things: pressure at warn here, 2.5 GB free there).

    The rule is the guard's measured one (#4987, ruled 2026-09-28): at least `heavy_work_need_bytes`
    available, and pressure below CRITICAL. Pressure at WARN alone does not hold work: a busy 16 GB Mac
    sits at warn much of the day, and a check run waited hours on it (#5524). An unreadable reading is no
    reason to wait. The readers are injectable so a test never depends on the real machine."""
    need = heavy_work_need_bytes()
    free = (available_bytes or memory_available_bytes)()
    if free is not None and free < need:
        return (f"{MEMORY_REASON}: Kraken and the other local models need about {need / 1024**3:.1f} GB "
                f"of free memory, and this Mac has about {free / 1024**3:.1f} GB free right now")
    level = (pressure_level or memory_pressure_level)()
    if level is not None and level >= _PRESSURE_CRITICAL:
        return (f"{MEMORY_REASON}: this Mac's memory pressure is critical, so starting a model that "
                f"needs about {need / 1024**3:.1f} GB now risks the whole app crashing")
    return None


class MemoryShortError(RuntimeError):
    """Raised where heavy work finds `memory_short` true at the moment it would load (Kraken's guard).
    Not a failure: the job lane puts a stored job back to waiting with this reason and runs it again
    when memory allows, and waits in place with handed-in work (`execution.jobs`, #5524)."""


def thermal_state_level() -> int | None:
    """`NSProcessInfoThermalState` (0 nominal .. 3 critical), or None when unreadable."""
    try:
        from Foundation import NSProcessInfo

        return int(NSProcessInfo.processInfo().thermalState())
    except Exception:  # noqa: BLE001 -- no reading is no reason to wait
        return None


def seconds_since_input() -> float | None:
    """Seconds since the person last touched keyboard or mouse, or None when unreadable."""
    try:
        import Quartz

        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
    except Exception:  # noqa: BLE001 -- no reading is no reason to wait
        return None


def memory_is_tight() -> str | None:
    return memory_short()


def mac_is_hot() -> str | None:
    state = thermal_state_level()
    return "Waiting: the Mac is hot" if state is not None and state >= _THERMAL_SERIOUS else None


def mac_is_in_use() -> str | None:
    idle = seconds_since_input()
    return "Waiting: you're using the Mac" if idle is not None and idle < IDLE_BEFORE_HEAVY_SECONDS else None


_battery: tuple[float, bool] | None = None


def battery_or_low_power() -> bool:
    """On battery power or in Low Power Mode; read at most every `BATTERY_READING_SECONDS`."""
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
    return _battery[1]


def on_battery() -> str | None:
    return "Waiting: the Mac is on battery" if battery_or_low_power() else None


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


def machine_state() -> dict:
    """This Mac's state for the Activity popover (`activity.popover.summary`, #5415): the same
    readings the probes act on, plus `why_wait`, the reason heavy work is held back now (None
    when it may go ahead, or when the throttle is off). An unreadable level is None; an
    unreadable battery or input reading is False, as it is to the probes. No GPU reading: no
    probe for it exists."""
    pressure = memory_pressure_level()
    thermal = thermal_state_level()
    return {
        "memory_pressure": None if pressure is None else (
            "critical" if pressure >= _PRESSURE_CRITICAL
            else "warn" if pressure >= _PRESSURE_WARN else "normal"),
        "thermal_state": None if thermal is None else _THERMAL_NAMES[max(0, min(thermal, 3))],
        "on_battery": on_battery() is not None,
        "in_use": mac_is_in_use() is not None,
        "why_wait": why_wait(),
    }
