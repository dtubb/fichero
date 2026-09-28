"""A local MLX model is refused BEFORE it loads when this Mac cannot hold it right now (#5221).

WHY: an MLX model loads its whole weights into unified memory when its process starts. With too
little free, the load takes the app down with it -- the real crash risk, where Kraken's ~2.5 GB is
not (the Kraken guard was relaxed on 2026-09-28 for that reason). Before this there was no check
at all. If this regresses, starting an 8B model on a busy 16 GB Mac crashes instead of saying
"needs ~8 GB, 5 GB free, try the 3B".

The machine is never read: free memory and pressure are injected, as in Kraken's guard tests.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.local_inference import (
    LocalModelHardwareError,
    LocalModelMemoryUnavailableError,
    ManagedLocalInferenceProcess,
    assert_memory_available_for_model,
    mlx_memory_need_bytes,
)
from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS
from tests.unit.llm.test_local_inference_service_manager import profile

GB = 1024**3
BIG = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
SMALL = MANAGED_MLX_MODELS["Qwen2.5-VL-3B"]
NORMAL, WARN, CRITICAL = 1, 2, 4


def _check(spec, free_gb, level=NORMAL):
    assert_memory_available_for_model(
        spec, available_bytes=lambda: int(free_gb * GB), pressure_level=lambda: level,
    )


def test_the_need_grows_with_the_model():
    assert mlx_memory_need_bytes(SMALL) < mlx_memory_need_bytes(BIG)
    assert mlx_memory_need_bytes(BIG) > BIG.download_size_bytes     # weights plus working memory


def test_a_model_that_fits_loads():
    _check(BIG, free_gb=12)


def test_short_memory_is_refused_with_what_it_needs_what_is_free_and_a_smaller_model():
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        _check(BIG, free_gb=6)
    said = str(refusal.value)
    need = mlx_memory_need_bytes(BIG) / GB
    assert f"needs about {need:.1f} GB" in said and "6.0 GB free" in said
    assert SMALL.display_name in said                                # a vision model that fits
    assert isinstance(refusal.value, LocalModelHardwareError)        # the route's 409, as before


def test_no_smaller_model_is_suggested_when_none_fits():
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        _check(BIG, free_gb=1)
    assert "smaller model" not in str(refusal.value)


def test_critical_pressure_refuses_even_with_room():
    with pytest.raises(LocalModelMemoryUnavailableError, match="critical"):
        _check(SMALL, free_gb=40, level=CRITICAL)


def test_warn_pressure_with_room_still_loads():
    """Ruled 2026-09-28 for Kraken, and the same here: a busy Mac sits at warn much of the day."""
    _check(SMALL, free_gb=40, level=WARN)


@pytest.mark.asyncio
async def test_the_process_is_refused_before_it_is_spawned(monkeypatch):
    """The check sits in `start()` BEFORE the subprocess: a refused load spawns nothing."""
    from fichero_server.llm import kraken_runtime, local_inference

    monkeypatch.delenv("FICHERO_SKIP_MLX_MEMORY_GUARD", raising=False)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: 2 * GB)
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: NORMAL)
    process = ManagedLocalInferenceProcess(profile(model_id=BIG.model_id))
    monkeypatch.setattr(process, "_model_spec", lambda: "/models/qwen3-vl-8b")

    async def spawned(*_a, **_k):
        raise AssertionError("the model process was spawned")

    monkeypatch.setattr(local_inference.asyncio, "create_subprocess_exec", spawned)
    with pytest.raises(LocalModelMemoryUnavailableError):
        await process.start()
    assert process.last_error and "needs about" in process.last_error
