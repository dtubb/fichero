"""Balanced throttling for heavy BACKGROUND passes (embedding, derivatives, …).

Daniel's rule — the user's machine must ALWAYS stay usable ([[user-machine-
always-useful]]). A bulk import once pegged 4+ cores (450% CPU) embedding images
and froze the app; hand-throttling with ``taskpolicy -b`` was a band-aid. This
module makes the throttle the DEFAULT:

- **Bounded to a fraction of the machine** — not all cores (greedy), not one
  (too slow). The dominant cost is the embedder's ONNX intra-op threads, capped
  by :func:`embed_threads`; how many embeds run at once is :func:`embed_concurrency`.
  Both default to a balanced ~half-the-cores budget and are env-configurable.
- **Low OS priority** — background work runs at background QoS
  (:func:`set_background_qos`), so it yields CPU to whatever the user is doing in
  the foreground.

Embeddings stay ON (Daniel wants them — they power semantic search); they are
just made background-nice by default so a big import can never hog the machine.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

#: QOS_CLASS_BACKGROUND from <sys/qos.h> — the lowest, throttled, yields-to-all
#: class Apple's scheduler defines. Matches Daniel's `taskpolicy -b`, per thread.
_QOS_CLASS_BACKGROUND = 0x09
_QOS_CLASS_UTILITY = 0x11


def cpu_count() -> int:
    return os.cpu_count() or 4


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r; using %d", name, raw, default)
        return default
    return value if value > 0 else default


def embed_threads() -> int:
    """ONNX intra-op threads PER embedding call — the dominant CPU lever.

    Balanced default ≈ half the cores (min 1). ``FICHERO_EMBED_THREADS`` overrides.
    Combined with :func:`embed_concurrency` (default 1) this keeps total embedding
    CPU near half the machine even under a bulk import.
    """
    from fichero_server.execution.throttle import slowed_for_use

    # Half again while the person uses the Mac: slower, never stopped (#5819).
    return slowed_for_use(_env_positive_int("FICHERO_EMBED_THREADS", max(1, cpu_count() // 2)))


def embed_concurrency() -> int:
    """How many embedding calls may run at once. Default 1, so total embedding
    CPU ≈ :func:`embed_threads` (≈ half the machine). ``FICHERO_EMBED_WORKERS``
    overrides (e.g. a headless box that wants to go faster)."""
    return _env_positive_int("FICHERO_EMBED_WORKERS", 1)


def set_background_qos(qos_class: int = _QOS_CLASS_BACKGROUND) -> None:
    """Drop the CALLING thread to background priority so its CPU yields to the
    foreground. Best-effort and never raises — a throttle that crashes the worker
    it throttles would be worse than the greed it prevents.

    macOS (the ship target): per-thread QoS via ``pthread_set_qos_class_self_np``
    (== ``taskpolicy -b``, but scoped to this thread, not the whole process).
    Elsewhere / on failure: POSIX ``nice`` as a fallback.
    """
    if sys.platform == "darwin":
        try:
            import ctypes
            import ctypes.util

            libsystem = ctypes.CDLL(ctypes.util.find_library("System"))
            # int pthread_set_qos_class_self_np(qos_class_t, int relative_priority)
            if libsystem.pthread_set_qos_class_self_np(qos_class, 0) == 0:
                return
        except Exception as exc:  # noqa: BLE001 — best-effort, fall through to nice
            logger.debug("pthread QoS set failed (%s); falling back to nice", exc)
    try:
        # On Linux setpriority(PRIO_PROCESS, 0, …) applies to the calling THREAD
        # (distinct tid), so this nices just this worker. On macOS it is a
        # per-process fallback only reached if the QoS call above failed.
        os.setpriority(os.PRIO_PROCESS, 0, 10)
    except (AttributeError, OSError) as exc:  # pragma: no cover - platform dependent
        logger.debug("nice fallback failed: %s", exc)


def set_utility_qos() -> None:
    """Drop the CALLING thread to UTILITY priority: below anything the person is
    touching, above background. For work the person asked for and is WAITING on
    (a page being segmented), where background is the wrong class: measured
    2026-09-20 on one 3063x2000 page, warm, Kraken segmentation took 19 s at the
    default class, 23 s at utility and 426 s at background (#4959). Background
    stays right for work nobody is waiting on (embedding a library)."""
    set_background_qos(_QOS_CLASS_UTILITY)


def current_thread_qos_class() -> int | None:
    """The calling thread's macOS QoS class, or None off macOS / on failure.

    Lets a test PROVE the throttle is per-thread: an embedding worker reads
    ``_QOS_CLASS_BACKGROUND`` while the serving/main thread does not — i.e. the
    embedder is de-prioritized WITHOUT touching request-serving (Daniel:
    "throttle the embedding worker, not the main app").
    """
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        libsystem = ctypes.CDLL(ctypes.util.find_library("System"))
        # pthread_t is a POINTER — declare it, or ctypes truncates the 64-bit
        # handle to a C int and the get-qos call dereferences garbage (crash).
        libsystem.pthread_self.restype = ctypes.c_void_p
        libsystem.pthread_get_qos_class_np.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_int),
        ]
        qos = ctypes.c_uint(0)
        # int pthread_get_qos_class_np(pthread_t, qos_class_t*, int* rel_prio)
        thread = libsystem.pthread_self()
        if libsystem.pthread_get_qos_class_np(thread, ctypes.byref(qos), None) == 0:
            return int(qos.value)
    except Exception as exc:  # noqa: BLE001 — best-effort introspection
        logger.debug("pthread_get_qos_class_np failed: %s", exc)
    return None


# -----------------------------------------------------------------------------
# Cheap, non-blocking process CPU% — so the Activity surface can show the user
# roughly how much compute the app is using right now (Daniel: "a way to see how
# much CPU something is using"). Per-JOB attribution is expensive and fragile;
# a process-wide percent, sampled between polls, is the honest cheap answer.
# -----------------------------------------------------------------------------
_cpu_sample_lock = threading.Lock()
#: (wall_clock, cumulative_process_cpu_seconds) of the previous sample.
_cpu_last_sample: tuple[float, float] | None = None


def _process_cpu_seconds() -> float:
    """Cumulative CPU seconds (user+system) this process has consumed."""
    t = os.times()  # user, system, children_user, children_system, elapsed
    return t.user + t.system + t.children_user + t.children_system


def process_cpu_percent() -> float | None:
    """Process CPU% since the LAST call — 100.0 == one core fully busy, so a
    value can exceed 100 on multiple cores. Non-blocking: it diffs against the
    previous sample rather than sleeping. The first call primes the sampler and
    returns None (no interval to measure yet). Best-effort; never raises.
    """
    global _cpu_last_sample
    try:
        now = time.monotonic()
        cpu = _process_cpu_seconds()
    except Exception as exc:  # noqa: BLE001 — a metric must never break its caller
        logger.debug("process_cpu_percent sample failed: %s", exc)
        return None
    with _cpu_sample_lock:
        prev = _cpu_last_sample
        _cpu_last_sample = (now, cpu)
    if prev is None:
        return None
    wall_delta = now - prev[0]
    if wall_delta <= 0:
        return None
    return round((cpu - prev[1]) / wall_delta * 100.0, 1)


# -----------------------------------------------------------------------------
# Memory and energy of this process from proc_pid_rusage RUSAGE_INFO_V6 (#5358):
# no root, probed on the M4. macOS only; anywhere else every value is None.
# -----------------------------------------------------------------------------
_RUSAGE_V6_FIELDS = (
    "ri_user_time ri_system_time ri_pkg_idle_wkups ri_interrupt_wkups ri_pageins ri_wired_size "
    "ri_resident_size ri_phys_footprint ri_proc_start_abstime ri_proc_exit_abstime ri_child_user_time "
    "ri_child_system_time ri_child_pkg_idle_wkups ri_child_interrupt_wkups ri_child_pageins "
    "ri_child_elapsed_abstime ri_diskio_bytesread ri_diskio_byteswritten ri_cpu_time_qos_default "
    "ri_cpu_time_qos_maintenance ri_cpu_time_qos_background ri_cpu_time_qos_utility ri_cpu_time_qos_legacy "
    "ri_cpu_time_qos_user_initiated ri_cpu_time_qos_user_interactive ri_billed_system_time "
    "ri_serviced_system_time ri_logical_writes ri_lifetime_max_phys_footprint ri_instructions ri_cycles "
    "ri_billed_energy ri_serviced_energy ri_interval_max_phys_footprint ri_runnable_time ri_flags "
    "ri_user_ptime ri_system_ptime ri_pinstructions ri_pcycles ri_energy_nj ri_penergy_nj "
    "ri_secure_time_in_system ri_secure_ptime_in_system ri_neural_footprint "
    "ri_lifetime_max_neural_footprint ri_interval_max_neural_footprint ri_conclave_footprint "
    "ri_page_wait_time_mach ri_page_cache_hits"
).split()
#: sys/resource.h ends v6 with `uint64_t ri_reserved[6]`: the kernel writes the whole struct, so a buffer one field
#: short is overwritten past its end (464 bytes in all).
_RUSAGE_V6_RESERVED = 6
_energy_last_sample: tuple[float, int] | None = None
_libproc: list = []  # [CDLL, struct class], built once


def process_rusage(pid: int | None = None) -> dict[str, int] | None:
    """{memory_bytes, energy_nj, instructions, cycles} for a pid (default: this process), or None."""
    import ctypes
    import sys

    if sys.platform != "darwin":
        return None
    try:
        if not _libproc:
            fields = ([("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in _RUSAGE_V6_FIELDS]
                      + [("ri_reserved", ctypes.c_uint64 * _RUSAGE_V6_RESERVED)])
            # Slice assignment, not extend: two first polls at once still leave exactly [CDLL, struct class].
            _libproc[:] = [ctypes.CDLL("/usr/lib/libproc.dylib"),
                           type("rusage_info_v6", (ctypes.Structure,), {"_fields_": fields})]
        lib, info = _libproc[0], _libproc[1]()
        if lib.proc_pid_rusage(pid or os.getpid(), 6, ctypes.byref(info)) != 0:
            return None
        return {
            "memory_bytes": info.ri_phys_footprint,
            "energy_nj": info.ri_energy_nj,
            "instructions": info.ri_instructions,
            "cycles": info.ri_cycles,
        }
    except Exception as exc:  # noqa: BLE001 — a metric must never break its caller
        logger.debug("process_rusage failed: %s", exc)
        return None


def _descendant_pids(root: int) -> list[int]:
    """The pids below ``root`` (children, their children, ...) from libproc's `proc_listchildpids`, which returns the
    count of pids (probed on the M4); no subprocess, so it cannot block the caller. [] when libproc is not loaded."""
    import ctypes

    if not _libproc:
        process_rusage()  # loads libproc once
    if not _libproc:
        return []
    found, queue = [], [root]
    while queue:
        buf = (ctypes.c_int * 256)()
        count = _libproc[0].proc_listchildpids(queue.pop(), buf, ctypes.sizeof(buf))
        for child in list(buf)[: max(0, min(count, 256))]:
            found.append(child)
            queue.append(child)
    return found


def process_tree_rusage() -> dict[str, int] | None:
    """`process_rusage` summed over this process and every process below it (its Kraken and line-extraction
    helpers, #5358); a child that cannot be read adds nothing."""
    total = process_rusage()
    if total is None:
        return None
    for pid in _descendant_pids(os.getpid()):
        child = process_rusage(pid)
        if child:
            total = {k: total[k] + child[k] for k in total}
    return total


def process_energy_watts(usage: dict[str, int] | None = None) -> float | None:
    """Average power since the LAST call, in watts; the first call primes it and returns None. ``usage`` is the
    caller's `process_tree_rusage()` when it has one, so a poll reads the tree once."""
    global _energy_last_sample
    usage = usage or process_tree_rusage()
    if usage is None:
        return None
    now = time.monotonic()
    with _cpu_sample_lock:
        prev = _energy_last_sample
        _energy_last_sample = (now, usage["energy_nj"])
    if prev is None or now <= prev[0]:
        return None
    return round(max(0, usage["energy_nj"] - prev[1]) / 1e9 / (now - prev[0]), 2)  # a child that exited takes its total with it
