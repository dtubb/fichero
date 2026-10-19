"""When heavy local work should wait, and why (`activity.throttle.power-heat-memory`, #5358).

Spotlight and Photos analysis wait on the same things: memory pressure, heat, battery and a
build. The person working at the Mac slows background work (its background QoS), never stops it (#5819). The local-model lane asks `why_wait` before it starts a heavy job,
and a long job (training) asks again at each of its own boundaries. The answer is the reason the
job's row shows, or None to go ahead. No setting is added for any of this (dead-simple UX).

Work a person is waiting for (a page of a run they started) does not wait for battery or for
them to stop typing: that would stall the thing they asked for. It still waits for memory and
heat, because those are what make the Mac beachball.

Every probe degrades to "no reason" when it cannot read its signal (not macOS, a framework
missing, a sandbox refusal): an unreadable signal must never park the queue for good.
"""
from __future__ import annotations
from fichero_server.media import quartz_warm  # (#5745: warm() resolves Quartz names under a lock at first use)

import logging
import os
import subprocess
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: The person counts as using the Mac if any input arrived this recently.
IDLE_BEFORE_HEAVY_SECONDS = 30.0
#: How long a battery reading is trusted (it costs a subprocess). Short, so work held for battery
#: starts soon after the Mac is plugged in (`activity.throttle.recheck-when-it-clears`, #5621).
BATTERY_READING_SECONDS = 10.0
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
    """Memory this Mac can hand out now, as macOS counts it (`memory_pressure`'s free percentage of
    physical memory, #5537; `kraken_runtime._available_memory_bytes`), or None when unreadable."""
    from fichero_server.llm.kraken_runtime import _available_memory_bytes

    return _available_memory_bytes()


def heavy_work_need_bytes() -> int:
    """What heavy local work needs free to start: Kraken's measured floor (#4987), the one number."""
    from fichero_server.llm.kraken_runtime import _kraken_memory_need_bytes

    return _kraken_memory_need_bytes()


def _two_amounts_that_differ(need: int, free: int) -> tuple[str, str]:
    """The two amounts in GB, as `need > free` reads (#5524): one decimal, or two where one decimal
    would round them to the same number ('needs about 2.5 GB ... has about 2.5 GB free' told the person
    nothing was wrong). Where even two decimals agree, the free amount is shown as just under."""
    for places in (1, 2):
        shown = (f"{need / 1024**3:.{places}f}", f"{free / 1024**3:.{places}f}")
        if shown[0] != shown[1]:
            return shown
    return shown[0], f"just under {shown[1]}"


def memory_short(
    *,
    available_bytes: Callable[[], int | None] | None = None,
    pressure_level: Callable[[], int | None] | None = None,
    need_bytes: int | None = None,
    what: str = "Kraken and the other local models",
) -> str | None:
    """THE memory check (#5524): why heavy local work must wait for memory now, in words with the two
    numbers compared, or None to go ahead. The lane's throttle asks it before it hands out a job and
    Kraken's guard asks it again just before a page loads (`kraken_runtime.assert_memory_available_for_
    kraken`): one rule, one number, so the throttle can no longer release a job the guard then fails
    (they compared different things: pressure at warn here, 2.5 GB free there).

    The rule is the guard's measured one (#4987, ruled 2026-09-28): at least `heavy_work_need_bytes`
    available, and pressure below CRITICAL. Pressure at WARN alone does not hold work: a busy 16 GB Mac
    sits at warn much of the day, and a check run waited hours on it (#5524). An unreadable reading is no
    reason to wait. The readers are injectable so a test never depends on the real machine.

    `need_bytes`/`what`: a model with its own need (a local MLX model's load, #5537) asks the same
    question with its own number and name."""
    need = heavy_work_need_bytes() if need_bytes is None else need_bytes
    free = (available_bytes or memory_available_bytes)()
    if free is not None and free < need:
        verb = "need" if what.endswith("models") else "needs"
        need_gb, free_gb = _two_amounts_that_differ(need, free)
        return (f"{MEMORY_REASON}: {what} {verb} about {need_gb} GB "
                f"of free memory, and this Mac has about {free_gb} GB free right now")
    level = (pressure_level or memory_pressure_level)()
    if level is not None and level >= _PRESSURE_CRITICAL:
        return (f"{MEMORY_REASON}: this Mac's memory pressure is critical, so starting a model that "
                f"needs about {need / 1024**3:.1f} GB now risks the whole app crashing")
    return None


def footprint_bytes(pid: int) -> int | None:
    """A process's physical footprint now (what Activity Monitor calls its Memory), or None when it
    cannot be read. `proc_pid_rusage(pid, RUSAGE_INFO_V0)`'s `ri_phys_footprint`, in-process via
    ctypes; works for this engine and the model servers it started (same user)."""
    import ctypes
    import ctypes.util

    class _RusageInfoV0(ctypes.Structure):  # <sys/resource.h> rusage_info_v0
        _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(name, ctypes.c_uint64) for name in (
            "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups",
            "ri_pageins", "ri_wired_size", "ri_resident_size", "ri_phys_footprint",
            "ri_proc_start_abstime", "ri_proc_exit_abstime")]

    try:
        libsystem = ctypes.CDLL(ctypes.util.find_library("System"))
        info = _RusageInfoV0()
        if libsystem.proc_pid_rusage(int(pid), 0, ctypes.byref(info)) != 0:
            return None
    except Exception:  # noqa: BLE001 -- not macOS, or the process is gone
        return None
    return int(info.ri_phys_footprint)


def peak_rss_bytes() -> int | None:
    """This process's peak resident set so far, in bytes (`getrusage` ru_maxrss: bytes on macOS), or None."""
    import resource

    try:
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (OSError, ValueError):
        return None


def swap_used_bytes() -> int | None:
    """The swap in use now, in bytes (`sysctlbyname("vm.swapusage")`'s xsw_usage, in-process via ctypes: no
    subprocess per sample), or None when it cannot be read."""
    import ctypes
    import ctypes.util

    class _SwapUsage(ctypes.Structure):  # <sys/sysctl.h> xsw_usage
        _fields_ = [("total", ctypes.c_uint64), ("avail", ctypes.c_uint64), ("used", ctypes.c_uint64),
                    ("pagesize", ctypes.c_uint32), ("encrypted", ctypes.c_bool)]

    try:
        usage, size = _SwapUsage(), ctypes.c_size_t(ctypes.sizeof(_SwapUsage))
        libc = ctypes.CDLL(ctypes.util.find_library("System"))
        if libc.sysctlbyname(b"vm.swapusage", ctypes.byref(usage), ctypes.byref(size), None, 0) != 0:
            return None
    except Exception:  # noqa: BLE001 -- not macOS
        return None
    return int(usage.used)


class PeakMemory:
    """The peak memory of the engine and of the model servers it started, over one run (#5537): the
    run's account says what the run took, which is how the need of a model is re-measured
    (`llm.local_inference._MLX_LOAD_MARGIN_BYTES`). A daemon thread samples both every
    `interval` seconds while the run runs.
    ponytail: sampled, so a spike shorter than the interval can be missed; one second is well under
    a page's read. The readers are injectable so a test never reads the real machine."""

    def __init__(self, *, engine: Callable[[], int | None] | None = None,
                 servers: Callable[[], int | None] | None = None, interval: float = 1.0,
                 rss: Callable[[], int | None] | None = None, swap: Callable[[], int | None] | None = None) -> None:
        self._engine = engine or (lambda: footprint_bytes(os.getpid()))
        self._servers = servers or _model_servers_footprint
        self._interval = interval
        self._rss = rss or peak_rss_bytes
        self._swap = swap or swap_used_bytes
        self.rss_peak: int | None = None
        self.swap_start: int | None = self._safe(self._swap)
        self.swap_end: int | None = None
        self.engine_peak: int | None = None
        self.server_peak: int | None = None
        self._stop = None
        self._thread = None

    @staticmethod
    def _safe(read: Callable[[], int | None]) -> int | None:
        try:
            return read()
        except Exception:  # noqa: BLE001 -- a reading must never fail the run
            return None

    def sample(self) -> None:
        rss = self._safe(self._rss)  # swap is read at start and end only: once per run, not once a second
        if rss is not None and rss > (self.rss_peak or 0):
            self.rss_peak = rss
        for attr, read in (("engine_peak", self._engine), ("server_peak", self._servers)):
            try:
                value = read()
            except Exception:  # noqa: BLE001 -- a reading must never fail the run
                value = None
            if value is not None and value > (getattr(self, attr) or 0):
                setattr(self, attr, value)

    def start(self) -> "PeakMemory":
        import threading

        self._stop = threading.Event()

        def loop() -> None:
            while True:
                self.sample()
                if self._stop.wait(self._interval):
                    return

        self._thread = threading.Thread(target=loop, name="run-peak-memory", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        self.sample()
        self.swap_end = self._safe(self._swap)

    def pressure(self) -> dict[str, int]:
        """What the run did to this Mac's memory: the engine's peak resident set SINCE THE ENGINE STARTED (getrusage keeps a lifetime peak, not this run's) and how far swap grew during the run. The honest
        load: the physical footprint in `record` counts pages in the compressor and overstates it (M4 2026-10-17:
        19.7 GB footprint, 6.9 GB resident, swap flat). Only what was read."""
        out = {}
        if self.rss_peak is not None:
            out["engine_peak_rss_since_start_bytes"] = self.rss_peak
        if self.swap_start is not None and self.swap_end is not None:
            out["swap_growth_bytes"] = max(0, self.swap_end - self.swap_start)
        return out

    def record(self) -> dict[str, int]:
        """The peaks for the run's account (`run_usage`), only those read."""
        out = {}
        if self.engine_peak is not None:
            out["engine_peak_memory_bytes"] = self.engine_peak
        if self.server_peak is not None:
            out["model_server_peak_memory_bytes"] = self.server_peak
        return out


def _model_servers_footprint() -> int | None:
    """What the model servers this engine started hold together now, or None when none runs."""
    from fichero_server.api.routes.ai.local_inference import model_server_pids

    readings = [r for r in (footprint_bytes(pid) for pid in model_server_pids()) if r is not None]
    return sum(readings) if readings else None


class MemoryShortError(RuntimeError):
    """Raised where heavy work finds `memory_short` true at the moment it would load (Kraken's guard).
    Not a failure: the job lane puts a stored job back to waiting with this reason and runs it again
    when memory allows, and waits in place with handed-in work (`execution.jobs`, #5524)."""


def memory_is_busy() -> bool:
    """Memory pressure is at warn or above (`activity.throttle.one-heavy-when-memory-tight`, #5622): heavy
    work goes on, but one job at a time between the heavy lanes. False when the throttle is off or the
    level cannot be read."""
    if not _enabled():
        return False
    level = memory_pressure_level()
    return level is not None and level >= _PRESSURE_WARN


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
        quartz_warm.warm()
        import Quartz

        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
    except Exception:  # noqa: BLE001 -- no reading is no reason to wait
        return None


def memory_is_tight() -> str | None:
    return memory_short()


def model_need(model: str | None, *, loaded: bool = False) -> dict[str, Any]:
    """What one job's model needs free to start, for `memory_short` (#5654): a model on this Mac's model
    server its own need under its own name (`local_inference.mlx_memory_need_bytes`), or, already loaded (its
    weights in use), one more read's margin; a Kraken page, Kraken's floor under Kraken's name. Anything else
    (no model, one the catalogue does not size): the shared floor, {}."""
    provider, _, name = (model or "").partition(":")
    if provider == "kraken":
        return {"what": "Kraken"}
    if provider != "omlx" or not name:
        return {}
    from fichero_server.llm import local_inference
    from fichero_server.llm.local_model_choice import model_to_serve
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    try:
        spec = get_mlx_model_store().spec(model_to_serve(name))
    except KeyError:
        return {}
    if loaded:
        return {"need_bytes": local_inference._MLX_LOAD_MARGIN_BYTES, "what": f"{spec.display_name}'s next read"}
    return {"need_bytes": local_inference.mlx_memory_need_bytes(spec), "what": spec.display_name}


def mac_is_hot() -> str | None:
    state = thermal_state_level()
    return "Waiting: the Mac is hot" if state is not None and state >= _THERMAL_SERIOUS else None


IN_USE_REASON = "Waiting: you're using the Mac"
BUILD_REASON = "Waiting: a build is running"


def only_slows(reason: str | None) -> bool:
    """A reason that slows a long job between its items but never stops it: the person using the Mac, or a build
    (#5819, "work goes slower and at lower priority; it never stops"). Memory, heat and battery still hold."""
    return reason in (IN_USE_REASON, BUILD_REASON)


def mac_is_in_use() -> str | None:
    idle = seconds_since_input()
    return IN_USE_REASON if idle is not None and idle < IDLE_BEFORE_HEAVY_SECONDS else None


#: Programs whose running means the person is building: background work holds back for them (#5819).
#: Only what lives while compiling: Xcode's own build service (SWBBuildService) runs for as long as Xcode is open.
BUILD_PROCESSES = "xcodebuild|swift-build|swift-frontend|clang"
#: How long a build reading is trusted (it costs a subprocess).
BUILD_READING_SECONDS = 10.0
_build: tuple[float, bool] | None = None


def a_build_is_running() -> str | None:
    """A build is running on this Mac (Xcode, SwiftPM): background work holds back so the build is quick.
    Read at most every `BUILD_READING_SECONDS`; unreadable is no reason."""
    global _build
    now = time.monotonic()
    if _build is None or now - _build[0] > BUILD_READING_SECONDS:
        try:
            building = subprocess.run(["/usr/bin/pgrep", "-x", BUILD_PROCESSES], capture_output=True,
                                      timeout=1).returncode == 0
        except Exception:  # noqa: BLE001 -- no reading is no reason to wait
            building = False
        _build = (now, building)
    return BUILD_REASON if _build[1] else None


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
    (a_build_is_running, False),
]


def _started() -> bool:
    """*Start* is on (`activity.mode.start-stop`, #5621): all waiting work is treated as work a person
    is waiting for, so battery and a build do not hold it; memory and heat still do."""
    from fichero_server.execution.jobs import is_started

    return is_started()


def why_wait(*, person_waiting: bool = False, model: str | None = None, loaded: bool = False) -> str | None:
    """The first reason heavy local work should wait now, in words, or None. While *Start* is on, every
    caller is answered as for work a person waits for (one place, so the lane, the rows, the popover's
    `machine.why_wait` and a long job's own checks agree). For one job, `model` (and whether the lane has
    it `loaded`) makes the memory check that model's own need, named (`model_need`, #5654)."""
    if not _enabled():
        return None
    person_waiting = person_waiting or _started()
    need = model_need(model, loaded=loaded) if model else {}
    for probe, applies_when_waited_for in PROBES:
        if person_waiting and not applies_when_waited_for:
            continue
        reason = memory_short(**need) if probe is memory_is_tight and need else probe()
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
