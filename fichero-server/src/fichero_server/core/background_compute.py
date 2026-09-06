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
    return _env_positive_int("FICHERO_EMBED_THREADS", max(1, cpu_count() // 2))


def embed_concurrency() -> int:
    """How many embedding calls may run at once. Default 1, so total embedding
    CPU ≈ :func:`embed_threads` (≈ half the machine). ``FICHERO_EMBED_WORKERS``
    overrides (e.g. a headless box that wants to go faster)."""
    return _env_positive_int("FICHERO_EMBED_WORKERS", 1)


def set_background_qos() -> None:
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
            if libsystem.pthread_set_qos_class_self_np(_QOS_CLASS_BACKGROUND, 0) == 0:
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
