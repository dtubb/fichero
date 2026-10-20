"""A PEFT/LoRA adapter on the Hub is an adapter that needs its base, never a complete reader
(`source.onboard.model-search-adapters-name-their-base`, #5977). No network: the Hub listing and the model loads are faked."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from fichero_server.recipes import discovery, where_it_runs
from fichero_server.remote_read import job as read_job
from fichero_server.remote_read import runner
from fichero_server.remote_read.package import NotSendable, ReadStep

ADAPTER = "acme/qwen3-vl-ar-lora"
BASE = "Qwen/Qwen3-VL-8B"
LISTING = {"id": ADAPTER, "modelId": ADAPTER, "pipeline_tag": "image-text-to-text", "downloads": 5, "library_name": "peft",
           "tags": ["peft", "safetensors", "lora", "image-text-to-text", "ocr", "htr", "ar", f"base_model:adapter:{BASE}",
                    f"base_model:{BASE}", "license:apache-2.0"]}
RUNS = {"available": True, "where": "Hugging Face Jobs", "flavor": "t4-small", "price_per_hour_usd": 0.4, "why": ""}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(discovery, "remote_compute", lambda **k: RUNS)
    listing = {"v": LISTING}

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        if search or not tags or "mlx" in tags or any(t.startswith("base_model:") for t in tags):
            return []
        return [dict(listing["v"])] if set(tags) <= set(listing["v"]["tags"]) and task in (None, "image-text-to-text") else []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    return listing


def _found():
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    return [c for c in found if ADAPTER in str(c.pin)]


def test_the_base_is_read_from_the_listing_either_way_the_hub_writes_it():
    assert discovery._adapter_base(LISTING) == BASE
    assert discovery._adapter_base({**LISTING, "tags": ["peft", "lora", f"base_model:{BASE}"]}) == BASE
    assert discovery._adapter_base({**LISTING, "library_name": "transformers", "tags": ["safetensors"]}) is None
    assert discovery._adapter_base({**LISTING, "tags": ["peft"]}) is None  # an adapter that does not say its base


def test_an_adapter_is_shown_as_needing_its_base_never_as_a_reader_by_itself(hub):
    (card,) = _found()
    assert "adapter: needs " + BASE in card.offered_because
    assert card.pin["hf"] == ADAPTER and card.pin["base_model"] == BASE
    assert card.offered_only and card.runs_on == discovery.REMOTE_RUNS_ON and card.runs_here
    assert card.size_gb == 0.0  # the base's size is not in the adapter's listing: none is stated


def test_there_is_one_card_and_no_mlx_conversion_lookup_for_an_adapter(hub):
    assert len(_found()) == 1


def test_an_adapter_with_no_safetensors_is_listed_as_unable_to_run_in_words(hub):
    hub["v"] = {**LISTING, "tags": [t for t in LISTING["tags"] if t != "safetensors"]}
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset({"ar"})))
    cards = [c for c in found if ADAPTER in str(c.pin) or ADAPTER in c.id]
    assert all(not c.runs_here for c in cards)
    assert any("safetensors" in c.cannot_run_because for c in cards)


def test_the_places_name_the_base(hub):
    (card,) = _found()
    options = where_it_runs.places_it_can_run(card, this_mac_gb=16, hf_ready=True, clusters=[])
    mac, hf = options
    assert not mac["can"] and hf["can"]
    assert BASE in hf["needs"] and "adapter" in hf["needs"]


def _hub(monkeypatch, files=("adapter_model.safetensors", "adapter_config.json")):
    shas = {ADAPTER: "a" * 40, BASE: "b" * 40}
    monkeypatch.setattr(read_job, "hub_info", lambda repo: {"sha": shas[repo], "siblings": [{"rfilename": f} for f in files]})


def test_the_step_names_the_base_as_the_model_and_the_adapter_on_top(monkeypatch):
    _hub(monkeypatch)
    request = read_job.ReadAtScaleRequest(scope_ids=["a"], reader="vlm", card=ADAPTER, base_model=BASE)
    step = read_job.resolve_step(request, bucket=None)
    assert step["model"] == BASE and step["adapter"] == ADAPTER
    assert step["adapter_revision"] == "a" * 40 and step["model_revision"] == "b" * 40  # both pinned, never main
    assert ReadStep(**{k: v for k, v in step.items() if k in ReadStep.__dataclass_fields__}).describe()["adapter"] == ADAPTER
    plain = read_job.resolve_step(read_job.ReadAtScaleRequest(scope_ids=["a"], reader="vlm", card=BASE), bucket=None)
    assert "adapter" not in plain  # a complete model is loaded as it was


def test_a_bin_only_adapter_is_refused_before_the_job_is_built(monkeypatch):
    _hub(monkeypatch, files=("adapter_model.bin", "adapter_config.json"))
    with pytest.raises(NotSendable, match="adapter_model.safetensors"):
        read_job.resolve_step(read_job.ReadAtScaleRequest(scope_ids=["a"], reader="vlm", card=ADAPTER, base_model=BASE), bucket=None)


def test_a_hub_that_names_no_commit_is_refused(monkeypatch):
    monkeypatch.setattr(read_job, "hub_info", lambda repo: {"siblings": [{"rfilename": "adapter_model.safetensors"}]})
    with pytest.raises(NotSendable, match="no commit"):
        read_job.resolve_step(read_job.ReadAtScaleRequest(scope_ids=["a"], reader="vlm", card=ADAPTER, base_model=BASE), bucket=None)


def test_the_job_installs_peft_only_for_a_step_with_an_adapter():
    assert "peft" not in " ".join(read_job.dependencies_for({"reader": "vlm", "model": BASE}))
    assert any(d.startswith("peft") for d in read_job.dependencies_for({"reader": "vlm", "model": BASE, "adapter": ADAPTER}))
    assert read_job.dependencies_for({"reader": "kraken"}) is None


def test_the_runner_loads_the_base_then_the_adapter_and_merges_it(monkeypatch):
    calls = []

    class Model:
        device = "cpu"

        def merge_and_unload(self):
            calls.append("merge")
            return self

    base = Model()
    transformers = types.SimpleNamespace(
        AutoProcessor=types.SimpleNamespace(from_pretrained=lambda name, **k: calls.append(("processor", name, k.get("revision")))),
        AutoModelForImageTextToText=types.SimpleNamespace(
            from_pretrained=lambda name, **k: (calls.append(("base", name, k.get("revision"), k.get("use_safetensors"))), base)[1]))
    peft = types.SimpleNamespace(PeftModel=types.SimpleNamespace(
        from_pretrained=lambda model, name, **k: (calls.append(("adapter", name)), model)[1]))
    hub = types.SimpleNamespace(snapshot_download=lambda repo, **k: (calls.append(("fetch", repo, k["revision"], k["allow_patterns"])), "/folder")[1])
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    torch = types.SimpleNamespace(bfloat16="bf16")
    kraken = types.ModuleType("kraken")
    kraken.blla = types.SimpleNamespace()
    lib = types.ModuleType("kraken.lib")
    lib.vgsl = types.SimpleNamespace(TorchVGSLModel=types.SimpleNamespace(load_model=lambda p: object()))
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "peft", peft)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "kraken", kraken)
    monkeypatch.setitem(sys.modules, "kraken.lib", lib)
    monkeypatch.setattr("importlib.resources.files", lambda pkg: types.SimpleNamespace(joinpath=lambda n: n))
    runner.vlm_reader(None, {"model": BASE, "adapter": ADAPTER, "prompt": "p",
                                  "model_revision": "b" * 40, "adapter_revision": "a" * 40}, "cpu")
    assert calls == [("processor", BASE, "b" * 40), ("base", BASE, "b" * 40, True),
                     ("fetch", ADAPTER, "a" * 40, ["*.safetensors", "*.json"]), ("adapter", "/folder"), "merge"]
