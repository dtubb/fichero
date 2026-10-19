"""#5846: Kraken on one page sat minutes at ~290% CPU with 12.8 GB swap, 20 pages started at once, and coremltools warned.

Found: torch's own thread count was bounded but the OpenMP/BLAS pools around it were not; four pages at once entered
Kraken's path (the vision slot is four wide); and the coremltools warning names a backend Kraken does not use.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types

from fichero_server.llm import kraken_runtime
from fichero_server.workflows.tools.vision_base import one_page_at_a_time


def _clean_env(monkeypatch):
    """Registered with monkeypatch so what a test sets is restored, whether or not the variable existed."""
    for name in kraken_runtime._THREAD_POOL_ENV:
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


def test_the_native_thread_pools_are_bounded_to_the_lane(monkeypatch):
    _clean_env(monkeypatch)
    kraken_runtime.bound_native_thread_pools(3)
    import os

    assert {os.environ[n] for n in kraken_runtime._THREAD_POOL_ENV} == {"3"}
    monkeypatch.setenv("OMP_NUM_THREADS", "7")  # a person's own setting wins
    kraken_runtime.bound_native_thread_pools(3)
    assert os.environ["OMP_NUM_THREADS"] == "7"


def test_a_kraken_call_bounds_torch_threads_and_interop(monkeypatch):
    _clean_env(monkeypatch)
    seen = {}
    fake = types.SimpleNamespace(set_num_threads=lambda n: seen.__setitem__("threads", n),
                                 set_num_interop_threads=lambda n: seen.__setitem__("interop", n))
    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setattr(kraken_runtime, "require_installed", lambda: None)
    monkeypatch.setattr(kraken_runtime, "assert_memory_available_for_kraken", lambda: None)
    monkeypatch.setattr(kraken_runtime, "_release_when_idle", lambda: None)
    monkeypatch.setattr("fichero_server.core.compute_preferences.apply_to_this_thread", lambda priority: 2)
    assert kraken_runtime._kraken_call(lambda: "read") == "read"
    assert seen == {"threads": 2, "interop": 1}


def test_kraken_takes_one_page_at_a_time_and_other_readers_are_not_held():
    async def peak(mode):
        gate, live, high = one_page_at_a_time(mode), 0, 0

        async def page():
            nonlocal live, high
            async with gate():
                live += 1
                high = max(high, live)
                await asyncio.sleep(0.01)
                live -= 1

        await asyncio.gather(*(page() for _ in range(6)))
        return high

    assert asyncio.run(peak("kraken")) == 1
    assert asyncio.run(peak("llm")) > 1


def test_the_coreml_predict_warning_is_dropped_and_others_are_kept():
    logger = logging.getLogger("coremltools.models.model")
    kraken_runtime.quiet_coreml_warning()
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Catch()
    logger.addHandler(handler)
    try:
        logger.warning("You will not be able to run predict() on this Core ML model. Underlying exception message was: x")
        logger.warning("something else coremltools says")
    finally:
        logger.removeHandler(handler)
    assert records == ["something else coremltools says"]
