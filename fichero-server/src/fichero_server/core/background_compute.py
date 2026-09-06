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
