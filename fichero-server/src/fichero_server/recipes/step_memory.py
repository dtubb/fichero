"""What a step did to this Mac's memory, kept on the step in the run's record and written to the engine log, which Save Logs
for Support carries (`recipes-run.memory.recorded-per-step`, #6673)."""
from __future__ import annotations

import logging
from typing import Any, Callable

from fichero_server.core import perf
from fichero_server.execution import throttle

logger = logging.getLogger(__name__)

#: `kern.memorystatus_vm_pressure_level` as words.
PRESSURE_WORDS = {1: "normal", 2: "high", 4: "critical"}
_GIB = 1024**3


class StepMemory:
    """One step's reading: `start()` before it runs, `finish()` after. The readers are injectable so a test never reads the Mac."""

    def __init__(self, *, ram: Callable[[], int | None] | None = None, pressure: Callable[[], int | None] | None = None,
                 peak: throttle.PeakMemory | None = None, loads: Callable[[], tuple[int, int]] | None = None) -> None:
        from fichero_server.llm.kraken_runtime import _physical_memory_bytes

        self._ram = ram or _physical_memory_bytes
        self._pressure = pressure or throttle.memory_pressure_level
        self._peak = peak or throttle.PeakMemory()
        self._loads = loads or perf.model_load_totals
        self._levels: list[int] = []
        self._counts = (0, 0)

    def _read_pressure(self) -> None:
        level = self._pressure()
        if level is not None:
            self._levels.append(level)

    def start(self) -> "StepMemory":
        self._counts = self._loads()
        self._read_pressure()
        self._peak.start()
        return self

    def finish(self) -> dict[str, Any]:
        """The step's reading: only what was read."""
        self._peak.stop()
        self._read_pressure()
        loads, unloads = self._loads()
        out: dict[str, Any] = {"model_loads": loads - self._counts[0], "model_unloads": unloads - self._counts[1]}
        ram = self._ram()
        if ram is not None:
            out["ram_bytes"] = ram
        out.update(self._peak.pressure())
        if self._peak.swap_end is not None:
            out["swap_used_bytes"] = self._peak.swap_end
        if self._levels:
            out["memory_pressure"] = PRESSURE_WORDS.get(max(self._levels), str(max(self._levels)))
        return out


def merged(held: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """A step runs once per batch: loads and unloads and swap growth add up, peaks and the pressure keep the worst."""
    if not held:
        return dict(new)
    out = dict(held)
    for key, value in new.items():
        if key in ("model_loads", "model_unloads", "swap_growth_bytes"):
            out[key] = out.get(key, 0) + value
        elif key == "memory_pressure":
            order = list(PRESSURE_WORDS.values())
            out[key] = max(value, out.get(key, value), key=lambda w: order.index(w) if w in order else -1)
        elif isinstance(value, int):
            out[key] = max(value, out.get(key, value))
        else:
            out[key] = value
    return out


def words(step_name: str, memory: dict[str, Any]) -> str:
    """The log line for one step's reading, as a person reads it afterwards."""
    parts = [f"{memory['model_loads']} model loads, {memory['model_unloads']} unloads"]
    for key, label in (("ram_bytes", "Mac RAM"), ("engine_peak_rss_since_start_bytes", "engine peak"),
                       ("swap_used_bytes", "swap")):
        if key in memory:
            parts.append(f"{label} {memory[key] / _GIB:.1f} GB")
    if "memory_pressure" in memory:
        parts.append(f"memory pressure {memory['memory_pressure']}")
    return f"run step {step_name}: " + "; ".join(parts)


def record(step: dict[str, Any], step_name: str, memory: dict[str, Any]) -> None:
    """Add a batch's reading to the step in the run's record and write its line to the engine log."""
    step["memory"] = merged(step.get("memory"), memory)
    logger.info(words(step_name, memory))
