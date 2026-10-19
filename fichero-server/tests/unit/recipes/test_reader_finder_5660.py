"""The Find a Reader sheet's engine half (#5660 item 3), tested through `GET /api/recipes/candidates`.

WHY: on the maintainer's Mac, for a medieval Spanish hand, "Search Online" found nothing a palaeographer would use:
the Hugging Face listings were asked by task and language tag only, which find general vision models, never the HTR
models made for manuscripts (TrOCR fine-tunes, VLMs trained on old hands). Each source's line was a paragraph with an
Activity job id in it. And nothing said plainly whether a card ships with Fichero or is downloaded, and how big.

The Hub and Kraken's repository are stubbed; nothing reaches the network.
"""

from __future__ import annotations

import json

import pytest
from tests.unit.recipes.test_hub_discovery_quality_5594 import (  # noqa: F401  (fixture)
    _source,
    _wait_for,
    store,
)

#: An MLX build of a VLM trained on medieval Spanish hands, found only by name ("htr").
MLX_HTR = {"modelId": "someone/castilian-htr-qwen-mlx-4bit", "pipeline_tag": "image-text-to-text",
           "library_name": "mlx", "tags": ["mlx", "safetensors", "htr", "handwriting", "manuscripts",
                                           "image-text-to-text", "es", "license:apache-2.0"]}
#: A TrOCR fine-tune on medieval Spanish: this build cannot run it, but a person should see it exists.
TROCR = {"modelId": "someone/trocr-spanish-medieval-htr", "pipeline_tag": "image-to-text",
         "library_name": "transformers", "tags": ["transformers", "safetensors", "vision-encoder-decoder", "trocr",
                                                  "htr", "handwritten", "image-to-text", "es", "license:mit"]}


@pytest.fixture
def hub(monkeypatch):
    """The Hub answers the HTR words with the two manuscript models, and the tag listings with nothing."""
    asked: list[tuple[str | None, str | None, tuple]] = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        asked.append((task, search, tuple(tags or ())))
        if search == "htr" and task == "image-text-to-text":
            return [dict(MLX_HTR)]
        if search in ("htr", "trocr", "spanish") and task == "image-to-text":
            return [dict(TROCR)]
        return []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    return asked


def _candidates(client, **params) -> dict:
    r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es", "material": "handwriting",
                                                      "mac_memory_gb": 32, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _searched(client, db) -> dict:
    first = _candidates(client, online="true")
    assert _source(first, "hugging-face")["detail"] == "Searching Hugging Face…"
    _wait_for(db, first["search_job"]["id"])
    return _candidates(client, online="true")


def test_the_online_search_finds_the_htr_models_made_for_manuscripts(client, db, store, hub):
    body = _searched(client, db)
    found = {c["pin"]["hf"]: c for c in body["items"] if c["source"] == "hugging-face"}
    assert set(found) == {MLX_HTR["modelId"], TROCR["modelId"]}, list(found)

    runnable = found[MLX_HTR["modelId"]]
    assert runnable["rule_rank"] is not None and runnable["refused"] is None
    assert "for handwriting" in runnable["offered_because"] and "lists Spanish" in runnable["offered_because"]
    assert runnable["availability"] == "download" and runnable["availability_words"] == "Download (size not stated)"

    trocr = found[TROCR["modelId"]]
    assert trocr["rule_rank"] is None and trocr["availability"] == "not_here"
    assert trocr["refused"].startswith("Fichero cannot run it yet: a TrOCR model")
    assert trocr["availability_words"].startswith("Fichero cannot run it yet (a TrOCR model")
    assert trocr["download"] is None

    # Searched by name for the HTR words and the project's language, beside the tag listings.
    searched_for = {search for _task, search, _tags in hub if search}
    assert {"htr", "manuscript", "trocr", "spanish"} <= searched_for


def test_a_found_model_this_build_cannot_run_is_never_chosen_by_the_rules(client, with_material, db, store, hub):
    _searched(client, db)
    recipe = client.post("/api/recipes/assemble", json={"purposes": ["transcribe"], "languages": ["es"],
                                                        "scripts": ["Latn"], "materials": ["handwriting"]})
    assert recipe.status_code == 200, recipe.text
    assert TROCR["modelId"] not in str(recipe.json()["steps"])


def test_each_source_says_what_it_did_in_one_short_sentence(client, db, store, hub):
    body = _searched(client, db)
    lines = {s["source"]: s["detail"] for s in body["sources"]}
    assert lines["shipped"].startswith(f"{_source(body, 'shipped')['count']} ship")  # then how many are here (#5809)
    assert lines["hugging-face"] == "2 found on Hugging Face"
    assert lines["kraken-repository"] == "0 found on Zenodo"
    for line in lines.values():
        assert len(line) <= 48 and "job" not in line.lower() and "activity" not in line.lower(), line
    offline = _candidates(client)
    assert {s["detail"] for s in offline["sources"] if s["source"] == "kraken-repository"} <= {
        "Not searched", "0 found on Zenodo"}


def test_each_candidate_says_plainly_whether_it_ships_is_here_or_downloads(client, store, monkeypatch, tmp_path):
    """A reader whose weights download says so with its size, even when its card ships with Fichero (CATMuS: the card
    ships, the 16 MB of weights do not); once downloaded it is on this Mac; Apple's recognition ships with macOS."""
    from fichero_server.llm import kraken_runtime

    monkeypatch.setenv("FICHERO_KRAKEN_DATA_DIR", str(tmp_path / "kraken"))
    items = {c["id"]: c for c in _candidates(client)["items"]}
    catmus = items["kraken:zenodo/10.5281/zenodo.12743230@unpinned"]
    assert (catmus["availability"], catmus["availability_words"]) == ("download", "Download (16 MB)")
    assert catmus["download"]["params"] == {"runtime": "kraken", "model": "kraken-catmus-medieval"}
    apple = {c["id"]: c for c in _candidates(client, job="read-a-page")["items"]}["apple:vision/recognize-text@os"]
    assert (apple["availability"], apple["availability_words"]) == ("ships", "Available")

    marker = kraken_runtime._marker_path("kraken-catmus-medieval")
    marker.parent.mkdir(parents=True, exist_ok=True)
    weights = tmp_path / "kraken" / "catmus.mlmodel"
    weights.write_bytes(b"w")
    marker.write_text(json.dumps({"doi": "10.5281/zenodo.12743230", "model_path": str(weights)}))
    again = {c["id"]: c for c in _candidates(client)["items"]}["kraken:zenodo/10.5281/zenodo.12743230@unpinned"]
    assert (again["availability"], again["availability_words"]) == ("installed", "Downloaded (16 MB)")
    assert again["installed"] is True and again["download"] is None
