"""`runner.soak.mlx-reading` (#6748): the local MLX reader's model server is started once for a run of many pages, the pages stream
through its read slots no more than the Mac's memory allows at once, and the weights plus the reads in flight stay under the
share of memory the reads may hold. A fake process and no model: what is checked is how often the engine asks for a load."""
from __future__ import annotations

import asyncio

import pytest

import fichero_server.llm.local_inference as li
from fichero_server.llm.local_inference import LocalInferenceServiceManager, LocalServiceState
from tests.unit.llm.test_local_inference_service_manager import FakeProcess, profile

GB = 1024**3


class _Healthy:
    async def get_json(self, url, timeout_seconds):
        return {"status": "ok", "model_loaded": True}


pytestmark = pytest.mark.usefixtures("plenty_of_memory")


@pytest.mark.asyncio
async def test_fifty_pages_in_a_row_load_the_model_once():
    process = FakeProcess()
    manager = LocalInferenceServiceManager(profile(), process, _Healthy(), poll_interval_seconds=0)
    for _page in range(50):
        status = await manager.start()  # what every page's read asks first
        assert status.state == LocalServiceState.healthy
    assert process.start_calls == 1


@pytest.mark.asyncio
async def test_a_crash_mid_run_loads_it_once_more_and_no_more():
    process = FakeProcess()
    manager = LocalInferenceServiceManager(profile(), process, _Healthy(), poll_interval_seconds=0)
    await manager.start()
    process.crash()
    for _page in range(20):
        await manager.start()
    assert process.start_calls == 2


@pytest.mark.asyncio
async def test_pages_streamed_through_the_slots_never_exceed_the_reads_the_memory_allows():
    at_once = li.reads_at_once_for(int(2.9 * GB) + li._MLX_LOAD_MARGIN_BYTES, 8 * GB)
    assert at_once == 1
    now = peak = 0

    async def page():
        nonlocal now, peak
        async with li.local_read_slot(at_once):
            now += 1
            peak = max(peak, now)
            await asyncio.sleep(0.001)
            now -= 1

    await asyncio.gather(*(page() for _ in range(30)))
    assert peak == 1


def test_the_weights_plus_the_reads_in_flight_stay_inside_half_the_mac():
    for total in (8 * GB, 16 * GB, 32 * GB):
        for weights in (2.9 * GB, 5.4 * GB, 9 * GB):
            at_once = li.reads_at_once_for(int(weights) + li._MLX_LOAD_MARGIN_BYTES, total)
            if weights < total * li._LOCAL_READS_SHARE:  # a model that fits at all
                assert weights + (at_once - 1) * li._MLX_LOAD_MARGIN_BYTES <= total * li._LOCAL_READS_SHARE
