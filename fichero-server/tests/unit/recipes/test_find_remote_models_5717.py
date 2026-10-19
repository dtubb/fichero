"""The finder offers models that run on the person's remote compute (#5717, `source.find.models-that-run-remotely`).

WHY: a vision model too big for this Mac, with no MLX conversion, was never offered, however well it reads old hands:
the search kept only builds this Mac runs. It is now a card that says where it would run (Hugging Face Jobs, the
remote compute the engine can send reading to), what that costs an hour and how big it is; with no remote compute set
up it is listed as unavailable, with why. It is offered, never the rules' choice. The finder names the sources it
searched and the ones it did not.

The Hub and the Jobs service are stubbed: no network, no token.
"""

from __future__ import annotations

import asyncio

import pytest
from fichero_server.llm.local_model_facts import GIB
from fichero_server.recipes import discovery
from fichero_server.recipes.assemble import Answers
from fichero_server.training import hf_jobs

BIG = "acme/big-vl-72b"
LISTING = {"id": BIG, "pipeline_tag": "image-text-to-text", "downloads": 300, "library_name": "transformers",
           "safetensors": {"total": 72_000_000_000},
           "tags": ["transformers", "safetensors", "image-text-to-text", "ocr", "htr", "es", "license:apache-2.0"]}
RUNS = {"available": True, "where": "Hugging Face Jobs", "flavor": "t4-small", "price_per_hour_usd": 0.4, "why": ""}
NONE_SET_UP = {"available": False, "where": "Hugging Face Jobs", "flavor": "t4-small", "price_per_hour_usd": None,
               "why": "No Hugging Face token: add one in Settings (AI providers, Hugging Face) to run models there."}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        if search or not tags or "mlx" in tags or any(t.startswith("base_model:") for t in tags):
            return []  # no MLX build, and no MLX conversion of it
        return [dict(LISTING)] if set(tags) <= set(LISTING["tags"]) and task in (None, LISTING["pipeline_tag"]) else []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)


def _found(remote, monkeypatch):
    monkeypatch.setattr(discovery, "remote_compute", lambda **k: remote)
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset({"es"})))
    return next(c for c in found if c.pin["hf"] == BIG)


def test_a_vision_model_with_no_mlx_conversion_is_listed_as_running_on_remote_compute(hub, monkeypatch):
    card = _found(RUNS, monkeypatch)
    assert card.runs_on == "cloud:huggingface-jobs" and card.runs_here and card.offered_only
    assert card.size_gb == round(72_000_000_000 * 2 / GIB, 1)  # 72 billion weights at two bytes each
    words = card.offered_because
    assert "runs on remote compute" in words and "Hugging Face Jobs" in words and "$0.40 an hour" in words
    assert "pages leave this Mac" in words
    assert discovery.candidate_place(card) == "provider"
    assert discovery.candidate_availability(card) == ("elsewhere", "Runs on remote compute (Hugging Face Jobs)")


def test_with_no_remote_compute_it_is_listed_as_unavailable_with_why(hub, monkeypatch):
    card = _found(NONE_SET_UP, monkeypatch)
    assert not card.runs_here and card.offered_only
    assert "No Hugging Face token" in card.cannot_run_because
    state, words = discovery.candidate_availability(card)
    assert state == "not_here" and "No Hugging Face token" in words


def test_a_remote_model_is_kept_offered_to_the_person_and_never_to_the_rules_or_the_downloader(hub, monkeypatch):
    card = _found(RUNS, monkeypatch)
    discovery.keep_hub([card], frozenset({"es"}))
    kept = [c for c in discovery.hub_cards(frozenset({"es"}), runnable_only=False) if c.pin["hf"] == BIG]
    assert len(kept) == 1 and kept[0].runs_on == "cloud:huggingface-jobs" and kept[0].offered_only
    assert kept[0].id == f"remote:hf/{BIG}@main" and kept[0].size_gb == round(72_000_000_000 * 2 / GIB, 1)
    assert "$0.40 an hour" in kept[0].offered_because
    # The rules' own view of the Hub readers has none of it, and nothing offers to download it to this Mac.
    assert [c for c in discovery.hub_cards(frozenset({"es"})) if c.pin["hf"] == BIG] == []
    assert discovery.hub_spec(BIG) is None


def test_the_remote_compute_is_the_account_the_person_set_up_and_its_listed_price(monkeypatch):
    class NoToken:
        def __init__(self):
            raise hf_jobs.NoHuggingFaceToken("No Hugging Face token: add one in Settings.")

    monkeypatch.setattr(hf_jobs, "HfJobsTarget", NoToken)
    off = discovery.remote_compute()
    assert off["available"] is False and "No Hugging Face token" in off["why"]

    class Account:
        def price_per_hour(self, flavor):
            return {"t4-small": 0.4}.get(flavor)

    monkeypatch.setattr(hf_jobs, "HfJobsTarget", Account)
    on = discovery.remote_compute()
    assert on == {"available": True, "where": "Hugging Face Jobs", "flavor": hf_jobs.DEFAULT_FLAVOR,
                  "price_per_hour_usd": 0.4, "why": ""}

    class Offline(Account):
        def price_per_hour(self, flavor):
            raise ConnectionError("no network")

    monkeypatch.setattr(hf_jobs, "HfJobsTarget", Offline)
    unpriced = discovery.remote_compute()
    assert unpriced["available"] is True and unpriced["price_per_hour_usd"] is None  # said unknown, never invented


def test_the_finder_names_the_sources_it_searched_and_those_it_did_not(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setattr(discovery, "remote_compute", lambda **k: RUNS)
    a = Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                materials=("handwriting",), mac_memory_gb=16)
    _cards, sources = discovery.discover(a, online=False)
    by = {s["source"]: s for s in sources}
    assert {"kraken-repository", "hugging-face", "remote-compute"} <= set(by)
    assert by["remote-compute"]["detail"] == "Remote compute: Hugging Face Jobs"
    for name, words in (("transkribus", "Transkribus"), ("htr-united", "HTR-United")):
        assert by[name]["state"] == "not-searched" and words in by[name]["detail"] and by[name]["count"] == 0
    monkeypatch.setattr(discovery, "remote_compute", lambda **k: NONE_SET_UP)
    _cards, sources = discovery.discover(a, online=False)
    assert {s["source"]: s for s in sources}["remote-compute"]["detail"] == "Remote compute: not set up (needs a token)"
    assert all(len(s["detail"]) <= 48 for s in sources)  # one short sentence each (#5660 item 3)
