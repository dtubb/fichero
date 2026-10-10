"""The model lane runs as many reads of the engine's local model at once as the plan says (#5654 item 5,
`compute.memory.reads-follow-memory`).

WHY: on the demo (2026-10-10) the start plan said the Paleographer Review "reads 4 pages at once", but the
review read one page at a time: every model call in a library's work takes a slot on the model lane, and
the model lane ran one job at a time, so the read slots (`local_inference.local_reads_at_once`) and the
server's batch (`MLX_VLM_MAX_NUM_SEQS`) never saw more than one request. The 16 GB test of the rule ran
with no library, so no lane, and passed.

Through the real lane (a real library, the real scheduler's threads); the model call is a sleep, physical
memory is injected.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server import llm
from fichero_server.execution import jobs
from fichero_server.llm import LLMConfig, kraken_runtime, local_inference
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

GB = 1024**3
THREE_B = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]


class _Counter:
    def __init__(self):
        self.now = 0
        self.peak = 0
        self.lock = threading.Lock()

    def enter(self):
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)

    def leave(self):
        with self.lock:
            self.now -= 1


async def _pages(library: str, counter: _Counter, n: int = 8, model: str = "Qwen2.5-VL-3B"):
    config = LLMConfig(provider="omlx", model=model)

    async def page(i):
        async with llm.model_call_slot(config, library=library, subject=f"page {i}"):
            counter.enter()
            try:
                await asyncio.sleep(0.3)
            finally:
                counter.leave()

    await asyncio.gather(*(page(i) for i in range(n)))


@pytest.fixture
def memory_free(monkeypatch):
    """Memory is not busy and nothing holds the lane (heat, battery, the Mac in use)."""
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "memory_is_busy", lambda: False)
    monkeypatch.setattr(throttle, "why_wait", lambda person_waiting=False, **_: None)


@pytest.mark.asyncio
async def test_on_a_16_gb_mac_the_lane_reads_as_many_pages_at_once_as_the_plan_says(
        test_package, monkeypatch, memory_free):
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", lambda: 16 * GB)
    plan = local_inference.local_read_plan(THREE_B)
    assert "4 pages at once" in plan

    counter = _Counter()
    await _pages(str(test_package), counter)

    assert counter.peak == local_inference.local_reads_at_once(THREE_B) == 4


@pytest.mark.asyncio
async def test_on_an_8_gb_mac_the_lane_reads_one_page_at_a_time_as_the_plan_says(
        test_package, monkeypatch, memory_free):
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", lambda: 8 * GB)
    assert "one page at a time" in local_inference.local_read_plan(THREE_B)

    counter = _Counter()
    await _pages(str(test_package), counter, n=4)

    assert counter.peak == 1


@pytest.mark.asyncio
async def test_other_work_on_the_model_lane_never_runs_beside_the_reads(test_package, monkeypatch, memory_free):
    """Only the same local model's calls share the lane; a Kraken page waits for them all to end."""
    from fichero_server.db.manager import db_manager

    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", lambda: 16 * GB)
    counter = _Counter()
    beside: list[int] = []

    def kraken_page():
        beside.append(counter.now)

    library = str(test_package)

    async def reads_then_kraken():
        reading = asyncio.ensure_future(_pages(library, counter, n=4))
        deadline = time.monotonic() + 10
        while counter.now == 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        db = db_manager.get_database(library)
        future = jobs.submit(db, "read-a-line", "kraken page", model="kraken:kraken-mccatmus", fn=kraken_page)
        await asyncio.wrap_future(future)
        await reading

    await reads_then_kraken()

    assert beside == [0]
    assert counter.peak == 4
