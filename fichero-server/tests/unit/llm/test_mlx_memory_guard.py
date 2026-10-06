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


def assert_fits(spec, free_gb, level=NORMAL):
    assert_memory_available_for_model(
        spec, available_bytes=lambda: int(free_gb * GB), pressure_level=lambda: level,
    )


def test_the_need_grows_with_the_model():
    assert mlx_memory_need_bytes(SMALL) < mlx_memory_need_bytes(BIG)
    assert mlx_memory_need_bytes(BIG) > BIG.download_size_bytes     # weights plus working memory


def test_a_model_that_fits_loads():
    assert_fits(BIG, free_gb=12)


def test_short_memory_is_refused_with_what_it_needs_what_is_free_and_a_smaller_model():
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        assert_fits(BIG, free_gb=6)
    said = str(refusal.value)
    need = mlx_memory_need_bytes(BIG) / GB
    assert f"needs about {need:.1f} GB" in said and "6.0 GB free" in said
    assert SMALL.display_name in said                                # a vision model that fits
    assert isinstance(refusal.value, LocalModelHardwareError)        # the route's 409, as before


def test_no_smaller_model_is_suggested_when_none_fits():
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        assert_fits(BIG, free_gb=1)
    assert "smaller model" not in str(refusal.value)


def test_critical_pressure_refuses_even_with_room():
    with pytest.raises(LocalModelMemoryUnavailableError, match="critical"):
        assert_fits(SMALL, free_gb=40, level=CRITICAL)


def test_warn_pressure_with_room_still_loads():
    """Ruled 2026-09-28 for Kraken, and the same here: a busy Mac sits at warn much of the day."""
    assert_fits(SMALL, free_gb=40, level=WARN)


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


# --- #5534: a landed model is guarded like its base; alternatives can do the step ---------------

TEXT_ONLY = [spec for spec in MANAGED_MLX_MODELS.values() if "vision" not in spec.capabilities]


def test_a_vision_model_refused_is_offered_only_models_that_read_images():
    """WHY: the stock 3B, refused while reading a page, was told 'use a smaller model: Qwen3 4B
    Instruct, Llama 3.2 3B Instruct' -- text-only models that cannot read the page at all."""
    assert TEXT_ONLY, "the catalogue has text-only models that fit, or this test proves nothing"
    for spec, free_gb in ((BIG, 6), (SMALL, 4.5)):
        with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
            assert_fits(spec, free_gb=free_gb)
        said = str(refusal.value)
        for other in TEXT_ONLY:
            assert other.display_name not in said, f"offered {other.display_name}, which reads no images: {said}"


def _landed_store(tmp_path, *, weights_bytes: int):
    """A model store holding one landed student of the 3B, its weights a sparse file of the real
    size (no disk is used), with the card training writes."""
    import json

    from fichero_server.llm.mlx_model_store import MLXModelStore

    store = MLXModelStore(root=tmp_path / "mlx")
    folder = store.trained_dir("fichero-trained/student")
    folder.mkdir(parents=True)
    (folder / "fichero-card.json").write_text(json.dumps(
        {"display_name": "Student line reader", "base": "Qwen/Qwen2.5-VL-3B-Instruct"}))
    with open(folder / "model.safetensors", "wb") as weights:
        weights.truncate(weights_bytes)
    return store


def test_a_landed_model_needs_what_its_weights_and_its_base_need(tmp_path):
    """WHY: a landed model's spec said 0 bytes, so the guard thought it needed 1.5 GB; it started
    where its own base was refused, and died loading with no reason given."""
    store = _landed_store(tmp_path, weights_bytes=3_073_721_056)
    spec = store.spec("fichero-trained/student")
    assert spec.download_size_bytes == 3_073_721_056
    assert spec.min_memory_bytes == SMALL.min_memory_bytes, "the base's memory floor"
    assert abs(mlx_memory_need_bytes(spec) - mlx_memory_need_bytes(SMALL)) < 0.2 * GB


@pytest.mark.asyncio
async def test_a_landed_model_is_refused_before_it_is_spawned_like_its_base(monkeypatch, tmp_path):
    """The stock 3B was refused at 4.5 GB free; the student of the same size must be too."""
    from fichero_server.llm import kraken_runtime, local_inference, mlx_model_store

    store = _landed_store(tmp_path, weights_bytes=3_073_721_056)
    monkeypatch.setattr(mlx_model_store, "get_mlx_model_store", lambda: store)
    monkeypatch.delenv("FICHERO_SKIP_MLX_MEMORY_GUARD", raising=False)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: int(4.5 * GB))
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: NORMAL)
    process = ManagedLocalInferenceProcess(profile(model_id="fichero-trained/student"))
    monkeypatch.setattr(process, "_model_spec", lambda: "/models/student")

    async def spawned(*_a, **_k):
        raise AssertionError("the model process was spawned")

    monkeypatch.setattr(local_inference.asyncio, "create_subprocess_exec", spawned)
    with pytest.raises(LocalModelMemoryUnavailableError) as refusal:
        await process.start()
    assert "Student line reader needs about" in str(refusal.value)
    for other in TEXT_ONLY:
        assert other.display_name not in str(refusal.value)
