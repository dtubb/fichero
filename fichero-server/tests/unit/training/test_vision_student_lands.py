"""A vision model trained with LoRA comes home as an MLX model (#5398, `compute.tune.convert-for-mlx`)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import line_reader
from fichero_server.llm import mlx_model_store as store_module
from fichero_server.llm.mlx_model_store import MLXModelStore
from fichero_server.training import mlx_landing
from fichero_server.training.mlx_landing import ConversionFailed, land_vision_student

CARD = {"display_name": "Sergio notebooks reader (Qwen2.5-VL 7B, Gemini-taught)",
        "summary": "Taught by google/gemini-3-flash-preview on 9,000 lines.",
        "base": "Qwen/Qwen2.5-VL-7B-Instruct", "base_licence": "Apache-2.0",
        "teacher": "google/gemini-3-flash-preview", "not_for_release": True}


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = MLXModelStore(root=tmp_path / "mlx")
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: s)
    return s


def _job_output(tmp_path):
    out = tmp_path / "out"
    (out / "adapter").mkdir(parents=True)
    (out / "adapter" / "adapter_model.safetensors").write_bytes(b"lora")
    (out / "merged").mkdir()
    (out / "merged" / "model-00001-of-00001.safetensors").write_bytes(b"bf16 weights")
    return out


def _fake_convert(merged, dest):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "model.safetensors").write_bytes(b"4-bit weights")
    (dest / "config.json").write_text("{}")


def test_the_student_lands_as_an_mlx_model_that_loads_by_name(store, tmp_path):
    """WHY: the student must be usable where the teacher was, as an MLX model of the omlx row, named
    by its id; the store resolves it like any downloaded model."""
    model_id = land_vision_student(_job_output(tmp_path), job_id="j1", name="sergio-qwen7b", card=CARD,
                                   convert=_fake_convert)
    assert model_id == "fichero-trained/sergio-qwen7b"
    assert store.resolve_model_path(model_id) == str(store.trained_dir(model_id))
    (entry,) = [e for e in store.list_catalog_entries() if e.model_id == model_id]
    assert entry.installed and entry.license_label == "not for release" and "Not for release" in entry.note
    card = store.trained_card(model_id)
    assert card["base"] == CARD["base"] and card["teacher"] == CARD["teacher"] and card["lines_per_call"] == 1


def test_the_adapter_always_stays_and_the_merged_copy_goes(store, tmp_path):
    """WHY: the adapter is the small, exact result of the training (`compute.tune.adapter-always-returns`);
    the merged bf16 copy is as large as the base (~15 GB) and is only needed for the conversion."""
    out = _job_output(tmp_path)
    model_id = land_vision_student(out, job_id="j1", name="sergio", card=CARD, convert=_fake_convert)
    adapter = store.root / "adapters" / "sergio" / "adapter_model.safetensors"
    assert adapter.read_bytes() == b"lora" and store.trained_card(model_id)["adapter_path"] == str(adapter.parent)
    assert not (out / "merged").exists()


def test_a_job_without_an_adapter_or_a_merged_model_lands_nothing(store, tmp_path):
    out = _job_output(tmp_path)
    (out / "adapter" / "adapter_model.safetensors").unlink()
    (out / "adapter").rmdir()
    with pytest.raises(ConversionFailed, match="adapter"):
        land_vision_student(out, job_id="j1", name="s", card=CARD, convert=_fake_convert)
    assert store.trained_model_ids() == []


def test_the_conversion_is_mlx_vlm_four_bit_in_the_mlx_runtime(monkeypatch, tmp_path):
    """WHY: the MLX runtime's own Python has mlx_vlm (the engine's may not, in a release); a convert
    that writes no weights is a failure by name, never an empty model in the store."""
    monkeypatch.setattr("fichero_server.llm.mlx_runtime.get_mlx_runtime",
                        lambda: SimpleNamespace(require_python_path=lambda: "/runtime/python"))
    seen = []
    with pytest.raises(ConversionFailed, match="no weights"):
        mlx_landing.convert_for_mlx(tmp_path / "merged", tmp_path / "dest", run=seen.append)
    (command,) = seen
    assert command[:3] == ["/runtime/python", "-m", "mlx_vlm.convert"]
    assert command[-3:] == ["-q", "--q-bits", "4"]


def test_the_line_reader_asks_a_student_one_line_at_a_time(store, tmp_path):
    """WHY: the student learned to read one picture per question; asked eight at once it is asked a
    task it never learned. Any other model keeps the reader's batch of eight."""
    model_id = land_vision_student(_job_output(tmp_path), job_id="j1", name="sergio", card=CARD,
                                   convert=_fake_convert)
    assert line_reader.lines_per_call(SimpleNamespace(provider="omlx", model=model_id)) == 1
    assert line_reader.lines_per_call(SimpleNamespace(provider="omlx", model=f"omlx/{model_id}")) == 1
    assert line_reader.lines_per_call(SimpleNamespace(provider="openrouter", model="google/gemini-3-flash-preview")) == 8


def test_one_card_two_builds_the_hf_weights_for_linux_and_mlx_for_this_mac(store, tmp_path):
    """WHY (`compute.engine.same-card-resolves-by-platform`): the student reads 100k pages on a Linux
    GPU (transformers, vLLM) and a few on this Mac (MLX); one card names both builds, so the same model
    is chosen whichever runs it."""
    model_id = land_vision_student(_job_output(tmp_path), job_id="j1", name="sergio", card=CARD, convert=_fake_convert,
                                   hf_build={"bucket": "historian/fichero-training", "merged": "j1/out/merged",
                                             "adapter": "j1/out/adapter"})
    builds = store.trained_card(model_id)["builds"]
    assert builds["mlx"] == {"model_id": model_id, "path": str(store.trained_dir(model_id)), "bits": 4,
                             "runs_on": "Apple silicon"}
    assert builds["hf"]["bucket"] == "historian/fichero-training" and builds["hf"]["merged"] == "j1/out/merged"
    assert "merged_here" not in builds["hf"], "the 17 GB copy is not kept here unless asked"


def test_the_merged_weights_can_be_kept_here_when_asked(store, tmp_path):
    """WHY: to run the student on a Linux GPU without Hugging Face (ACENET), the person may want the
    standard weights on hand; asked for, they are kept beside the MLX build, not deleted."""
    model_id = land_vision_student(_job_output(tmp_path), job_id="j1", name="sergio", card=CARD, convert=_fake_convert,
                                   keep_merged=True)
    here = store.trained_card(model_id)["builds"]["hf"]["merged_here"]
    assert (tmp_path / "mlx" / "hf" / "sergio" / "model-00001-of-00001.safetensors").read_bytes() == b"bf16 weights"
    assert here.endswith("hf/sergio")
