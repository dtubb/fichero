"""The app manages memory, not the person: a local model load that does not fit NOW waits, after the
engine lets go of its own idle models; only a model too big for this Mac fails at once (#5537).

WHY: on the 8 GB Air (2026-10-06) every 3B vision page was refused -- 'needs about 5.0 GB free; this
Mac has 2.2 GB free' -- while macOS's `memory_pressure` said 64% free, and the same trained 3B had
read 6 pages there before the guard. Three faults: the free reading left out what macOS reclaims by
compressing; the need was an unmeasured weights x 1.2 + 1.5 GB; and a refusal failed the page (about
50 s each, the server started first) instead of waiting. Spec: compute/jobs-and-fine-tuning.md,
'Models in memory', rules 2-4 and 7.

Nothing reads this Mac: every reading (macOS's free percentage, physical memory, raw free pages,
pressure, process footprints) is injected.
"""
from __future__ import annotations

from functools import partial

import pytest

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as routes
from fichero_server.execution import throttle
from fichero_server.execution.throttle import MemoryShortError, PeakMemory
from fichero_server.llm import LLMConfig, kraken_runtime, local_inference
from fichero_server.llm.local_inference import (
    LocalModelMemoryShortError,
    LocalModelMemoryUnavailableError,
    assert_memory_available_for_model,
    mlx_memory_need_bytes,
    wait_for_memory_to_load,
)
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
from tests.unit.llm.test_local_model_choice import _served, mac  # noqa: F401 -- the fixture

GB = 1024**3
THREE_B = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]
EIGHT_B = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
NORMAL, CRITICAL = 1, 4


def _air(free_gb: float = 2.2, percent: int = 64):
    """The 8 GB Air's readings as the issue gives them: raw free pages and macOS's free percentage."""
    return partial(kraken_runtime._available_memory_bytes, free_percent=lambda: percent,
                   physical_bytes=lambda: 8 * GB, reclaimable_bytes=lambda: int(free_gb * GB))


def _check(available, *, pressure=NORMAL, ram_gb=8):
    return partial(assert_memory_available_for_model, available_bytes=available,
                   pressure_level=lambda: pressure, physical_bytes=lambda: ram_gb * GB)


# --- 1. measure what macOS can hand out ----------------------------------------------------------


def test_available_memory_is_what_memory_pressure_reports_not_raw_free_pages():
    """64% of 8 GB is what macOS can hand out; the 2.2 GB of free + inactive + speculative pages is not."""
    assert _air()() == int(8 * GB * 64 // 100)


def test_the_raw_mach_reading_stands_in_when_macos_percentage_cannot_be_read():
    available = kraken_runtime._available_memory_bytes(
        free_percent=lambda: None, physical_bytes=lambda: 8 * GB, reclaimable_bytes=lambda: int(2.2 * GB))
    assert available == int(2.2 * GB)
    assert kraken_runtime._available_memory_bytes(
        free_percent=lambda: None, physical_bytes=lambda: None, reclaimable_bytes=lambda: None) is None


def test_on_the_air_a_3b_load_proceeds():
    """The regression itself: raw free 2.2 GB, 64% free by pressure -> the 3B loads."""
    assert _check(_air())(THREE_B) is None, "no refusal: the load goes ahead"


def test_on_the_air_the_trained_3b_proceeds(tmp_path):
    """The trained Mosquera 3B (its own 3.07 GB of weights) read 6 pages on this Mac before the guard."""
    from tests.unit.llm.test_mlx_memory_guard import _landed_store

    student = _landed_store(tmp_path, weights_bytes=3_073_721_056).spec("fichero-trained/student")
    assert _check(_air())(student) is None


# --- 2. the need is the weights plus a margin; too big for this Mac is refused up front ----------


def test_the_need_is_the_resident_weights_plus_a_margin():
    assert mlx_memory_need_bytes(THREE_B) == THREE_B.download_size_bytes + local_inference._MLX_LOAD_MARGIN_BYTES
    assert mlx_memory_need_bytes(THREE_B) < 4 * GB


def test_the_override_still_sets_the_need(monkeypatch):
    monkeypatch.setenv("FICHERO_MLX_MEMORY_NEED_MB", "1024")
    assert mlx_memory_need_bytes(EIGHT_B) == GB


def test_an_8b_on_an_8_gb_mac_is_refused_up_front_with_a_model_that_fits():
    """Never waited for: no amount of waiting makes 8 GB hold it. Even with the whole Mac free."""
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        _check(lambda: 8 * GB)(EIGHT_B)
    assert not isinstance(refusal.value, MemoryShortError)
    assert "8.0 GB" in str(refusal.value) and THREE_B.display_name in str(refusal.value)


def test_the_8b_fits_a_16_gb_mac():
    assert _check(lambda: 12 * GB, ram_gb=16)(EIGHT_B) is None


def test_short_memory_is_a_wait_not_a_failure():
    with pytest.raises(LocalModelMemoryShortError) as short:
        _check(lambda: 2 * GB)(THREE_B)
    assert isinstance(short.value, MemoryShortError)
    said = str(short.value)
    assert said.startswith(throttle.MEMORY_REASON)
    assert f"needs about {mlx_memory_need_bytes(THREE_B) / GB:.1f} GB" in said and "2.0 GB free" in said


def test_critical_pressure_still_refuses_the_load_even_with_room():
    with pytest.raises(LocalModelMemoryShortError, match="critical"):
        _check(lambda: 7 * GB, pressure=CRITICAL)(THREE_B)


# --- 3. short of memory: release the engine's idle models, then wait, then fail with the reason ---


@pytest.mark.asyncio
async def test_one_model_fills_the_budget_and_another_is_asked_for(monkeypatch):
    """The engine holds Kraken's reader; the 3B does not fit beside it. The engine lets go of its own
    idle model first, and the 3B loads without the page ever waiting."""
    monkeypatch.setitem(kraken_runtime._RESIDENT, "reader", ("model", object()))
    available = lambda: (2 if kraken_runtime._RESIDENT else 5) * GB  # noqa: E731
    noted = []
    await wait_for_memory_to_load(THREE_B, check=_check(available), note=noted.append, limit_seconds=0)
    assert not kraken_runtime._RESIDENT, "Kraken's idle reader must be released"
    assert noted == [], "the page never had to wait"


@pytest.mark.asyncio
async def test_kraken_in_use_is_not_released(monkeypatch):
    """A page being read is never interrupted (rule 3)."""
    monkeypatch.setitem(kraken_runtime._RESIDENT, "reader", ("model", object()))
    with kraken_runtime._INFERENCE_LOCK:
        assert local_inference.release_idle_engine_models() == []
    assert kraken_runtime._RESIDENT


@pytest.mark.asyncio
async def test_still_short_the_page_waits_with_the_reason_and_loads_when_memory_returns(monkeypatch):
    readings = iter([2, 2, 6])  # short at two looks; back on the third
    noted = []
    await wait_for_memory_to_load(THREE_B, check=_check(lambda: next(readings) * GB),
                                  release=lambda: [], note=noted.append, look_again_seconds=0)
    assert len(noted) == 2, "the page waited twice, saying why each time"
    assert noted[0].startswith(throttle.MEMORY_REASON) and "2.0 GB free" in noted[0]


@pytest.mark.asyncio
async def test_short_past_the_limit_fails_with_the_reason():
    with pytest.raises(LocalModelMemoryUnavailableError) as failed:
        await wait_for_memory_to_load(THREE_B, check=_check(lambda: 2 * GB), release=lambda: [],
                                      limit_seconds=0, look_again_seconds=0)
    said = str(failed.value)
    assert "needs about 3.9 GB" in said and "2.0 GB free" in said and "Waited" in said


@pytest.mark.asyncio
async def test_too_big_fails_at_once_without_waiting():
    noted = []
    with pytest.raises(LocalModelMemoryUnavailableError):
        await wait_for_memory_to_load(EIGHT_B, check=_check(lambda: 8 * GB), release=lambda: [],
                                      note=noted.append)
    assert noted == []


@pytest.mark.asyncio
async def test_stop_ends_the_wait():
    class Stopped(Exception):
        pass

    with pytest.raises(Stopped):
        await wait_for_memory_to_load(THREE_B, check=_check(lambda: 2 * GB), release=lambda: [],
                                      stopped=lambda: Stopped())


def test_the_wait_is_said_on_the_pages_row():
    """`note_call_reason` writes on the row of the lane slot the call holds (what Activity shows)."""
    from fichero_server.execution import jobs

    class Db:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

    db = Db()
    row, holding = jobs._call_row.set((db, "job-1")), jobs._holding.set(True)
    try:
        jobs.note_call_reason("Waiting: memory is tight: …")
    finally:
        jobs._call_row.reset(row)
        jobs._holding.reset(holding)
    assert db.calls == [("UPDATE jobs SET reason = ? WHERE id = ?", ["Waiting: memory is tight: …", "job-1"])]


# --- 5. decided before the model server starts ---------------------------------------------------


def _short_mac(monkeypatch, free_gb):
    monkeypatch.delenv("FICHERO_SKIP_MLX_MEMORY_GUARD", raising=False)
    state = {"free": free_gb * GB}
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: state["free"])
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: NORMAL)
    monkeypatch.setattr(kraken_runtime, "_physical_memory_bytes", lambda: 8 * GB)
    monkeypatch.setattr(local_inference, "release_idle_engine_models", lambda: [])
    return state


@pytest.mark.asyncio
async def test_a_page_short_of_memory_never_starts_the_server(mac, monkeypatch):  # noqa: F811
    """A refusal is decided before any process starts (it took ~50 s a page), and fails only after
    the stated limit, with the reason."""
    mac.install("Qwen2.5-VL-3B")
    _short_mac(monkeypatch, 2)
    monkeypatch.setattr(local_inference, "MEMORY_WAIT_LIMIT_SECONDS", 0)
    with pytest.raises(llm.LocalModelHardwareError, match="Waited"):
        await llm._ensure_managed_local_provider_ready(
            LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"), capability="vision")
    manager = routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID]
    assert not manager.process.is_running(), "the model server was started for a load that does not fit"


@pytest.mark.asyncio
async def test_a_page_waits_then_the_server_starts_when_memory_returns(mac, monkeypatch):  # noqa: F811
    mac.install("Qwen2.5-VL-3B")
    _short_mac(monkeypatch, 2)
    looks = []  # another app quits while the page waits: free from the third look on

    def available():
        looks.append(1)
        return (2 if len(looks) < 3 else 6) * GB

    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", available)
    monkeypatch.setattr(local_inference, "MEMORY_LOOK_AGAIN_SECONDS", 0)
    await llm._ensure_managed_local_provider_ready(
        LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"), capability="vision")
    assert len(looks) >= 3, "the page waited for memory before the server started"
    assert _served() == "Qwen2.5-VL-3B"
    assert routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID].process.is_running()


@pytest.mark.asyncio
async def test_a_model_already_loaded_is_not_checked_again(mac, monkeypatch):  # noqa: F811
    """It already holds its memory: re-asking would count it twice and refuse a model that is running."""
    mac.install("Qwen2.5-VL-3B")
    three = mac.loaded("Qwen2.5-VL-3B")
    _short_mac(monkeypatch, 0)
    monkeypatch.setattr(local_inference, "MEMORY_WAIT_LIMIT_SECONDS", 0)
    await llm._ensure_managed_local_provider_ready(LLMConfig(provider="omlx", model="Qwen2.5-VL-3B"))
    assert three.process.stops == 0


# --- 4. the run's account says its peak memory ---------------------------------------------------


def test_peak_memory_keeps_the_highest_reading_of_engine_and_model_server():
    engine, server = iter([1 * GB, 3 * GB, 2 * GB]), iter([None, 4 * GB, 3 * GB])
    peak = PeakMemory(engine=lambda: next(engine), servers=lambda: next(server))
    for _ in range(3):
        peak.sample()
    assert peak.record() == {"engine_peak_memory_bytes": 3 * GB, "model_server_peak_memory_bytes": 4 * GB}


def test_peak_memory_without_a_model_server_says_only_the_engine():
    peak = PeakMemory(engine=lambda: GB, servers=lambda: None)
    peak.start()
    peak.stop()
    assert peak.record() == {"engine_peak_memory_bytes": GB}


def test_the_run_status_carries_the_peaks():
    from fichero_server.api.routes.workflow_execution.threads import RunUsageResponse

    usage = RunUsageResponse.model_validate(
        {"model_calls": 0, "engine_peak_memory_bytes": 3 * GB, "model_server_peak_memory_bytes": 4 * GB})
    assert usage.engine_peak_memory_bytes == 3 * GB and usage.model_server_peak_memory_bytes == 4 * GB


def test_footprint_of_this_process_is_read_or_none():
    import os

    reading = throttle.footprint_bytes(os.getpid())
    assert reading is None or reading > 0
    assert throttle.footprint_bytes(0x7FFFFFFF) is None


def test_model_server_pids_lists_only_running_engine_servers(mac):  # noqa: F811
    assert routes.model_server_pids() == []

