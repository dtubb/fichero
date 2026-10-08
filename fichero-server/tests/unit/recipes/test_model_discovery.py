"""Finding models beyond the shipped cards (#5519; `source/models-chains-and-projects.md`, "Finding models
beyond the shipped cards", step 1 of "One guided path to a good model", `source.find.installed-count`,
`source.find.kraken-repository`, `source.find.hub-runs-here`, `source.find.rules-see-candidates`).

Why it matters: setup said "no reader fits" for Japanese, Chinese and Fraktur while a vision model sat
installed on the Mac and Kraken's repository holds Fraktur and Kuzushiji readers; and the Hub search
found GGUF chat models the app cannot run. Every test goes through the real routes; the network is
replaced by responses recorded on 2026-10-07 (`tests/fixtures/model_discovery/`): htrmopo's records for
five real repository models, and the Hub's answers to the exact queries discovery makes for Japanese.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from fichero_server.recipes import discovery

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "model_discovery"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An empty model store of the test's own, and an engine allowed to reach the network."""
    root = tmp_path / "store"
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(root))
    monkeypatch.delenv("FICHERO_KRAKEN_DATA_DIR", raising=False)
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    return get_mlx_model_store()


def _snapshot(store, repo: str, revision: str, *, config: dict | None, readme: str = "",
              weights: str = "model.safetensors") -> Path:
    snap = store.cache_dir / f"models--{repo.replace('/', '--')}" / "snapshots" / revision
    snap.mkdir(parents=True)
    if config is not None:
        (snap / "config.json").write_text(json.dumps(config))
    (snap / weights).write_bytes(b"w" * 4096)
    if readme:
        (snap / "README.md").write_text(readme)
    return snap


def _recorded_listing() -> dict:
    """htrmopo's listing as `get_listing` returns it, from the recorded records, plus one record that is
    not a Kraken reader (a copy of the Kuzushiji record made a segmentation model) to be left out."""
    from htrmopo.record import v0RepositoryRecord, v1RepositoryRecord

    raw = json.loads((FIXTURES / "kraken_repository_listing.json").read_text())
    segmenter = copy.deepcopy(raw["10.5281/zenodo.13942714"])
    segmenter["v0"].update(doi="10.5281/zenodo.99999999", concept_doi="10.5281/zenodo.99999998",
                           model_type=["segmentation"])
    raw["10.5281/zenodo.99999999"] = segmenter
    listing = {}
    for doi, versions in raw.items():
        listing[doi] = {}
        for version, fields in versions.items():
            fields = dict(fields, publication_date=datetime.fromisoformat(fields["publication_date"]))
            cls = v1RepositoryRecord if version == "v1" else v0RepositoryRecord
            listing[doi][version] = cls(**fields)
    return listing


@pytest.fixture
def repository(monkeypatch):
    calls = []

    def harvest():
        calls.append(1)
        return _recorded_listing()

    monkeypatch.setattr(discovery, "_harvest", harvest)
    return calls


@pytest.fixture
def hub(monkeypatch):
    """The Hub's recorded answers, keyed as discovery asks: task and filter tags."""
    responses = json.loads((FIXTURES / "hugging_face_ja.json").read_text())["responses"]
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        key = f"{task or ''}|{','.join(tags or [])}"
        asked.append(key)
        return copy.deepcopy(responses.get(key, []))

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    return asked


def _candidates(client, **params):
    r = client.get("/api/recipes/candidates", params={"mac_memory_gb": 32, **params})
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {c["id"]: c for c in body["items"]}, {s["source"]: s for s in body["sources"]}


# --- installed models count ---------------------------------------------------------------------------


def test_an_installed_vision_model_is_a_reader_candidate_with_a_card_from_its_own_config(client, store):
    _snapshot(store, "someone/Kanji-VL-4bit", "abc", config={"model_type": "qwen2_5_vl", "vision_config": {}},
              readme="---\nlicense: apache-2.0\nlanguage:\n- ja\n- zh\n---\n# Kanji VL\n")
    _snapshot(store, "someone/Text-Only-4bit", "def", config={"model_type": "qwen3"})
    _snapshot(store, "someone/Reader-GGUF", "ghi", config=None, weights="model-q4.gguf")

    body, items, sources = _candidates(client, scripts="Jpan", languages="ja")

    card = items["mlx:installed/someone/Kanji-VL-4bit@abc"]
    assert card["source"] == "installed" and "installed on this Mac" in card["offered_because"]
    assert card["languages"] == ["ja", "zh"] and card["licence"] == "apache-2.0" and card["open_licence"]
    assert card["scripts"] is None  # unstated, so never invisible to the rules for a script
    assert card["rule_rank"] == 1 and card["refused"] is None
    assert "unmeasured" in card["measured"]
    assert not any("Text-Only" in i or "GGUF" in i for i in items)
    assert sources["installed"]["count"] == 1


def test_a_model_fichero_trained_is_a_candidate_and_the_recipe_chooses_an_installed_reader_for_japanese(
        client, store):
    trained = store.cache_dir / "models--fichero-trained--kuzushiji" / "snapshots" / "trained"
    trained.mkdir(parents=True)
    (trained / "fichero-card.json").write_text(json.dumps({"display_name": "Kuzushiji reader",
                                                           "min_memory_bytes": 4 * 1024**3}))
    (trained / "adapters.safetensors").write_bytes(b"w" * 2048)

    _, items, _ = _candidates(client, scripts="Jpan", languages="ja")
    card = items["mlx:installed/fichero-trained/kuzushiji@trained"]
    assert card["licence"] == "trained by you" and card["rule_rank"] == 1

    r = client.post("/api/recipes/assemble", json={"purpose": "transcribe", "languages": ["ja"],
                                                   "scripts": ["Jpan"], "mac_memory_gb": 32})
    assert r.status_code == 200, r.text
    step = next(s for s in r.json()["steps"] if s["job"] == "read-a-line")
    assert step.get("gap") is None, step
    assert step["card"]["source"] == "installed"
    assert step["model"] == {"hf": "fichero-trained/kuzushiji", "revision": "trained"}
    assert any("unmeasured" in reason for reason in step["reasons"])


def test_an_installed_model_is_run_and_scored_like_a_catalogue_one(client, store):
    """The Start plan runs the installed card's pin on this Mac's model server, and the bake-off can score
    it (it is on this Mac), so it is a real candidate, not a name."""
    from fichero_server.recipes.assemble import Answers
    from fichero_server.recipes.bakeoff import candidates
    from fichero_server.recipes.start import _override

    _snapshot(store, "someone/Kanji-VL-4bit", "abc", config={"vision_config": {}},
              readme="---\nlicense: mit\n---\n")
    a = Answers(purposes=("transcribe",), languages=frozenset({"ja"}), scripts=frozenset({"Jpan"}),
                mac_memory_gb=32)
    rows = candidates(a, discovery.known_cards(a, include_not_built=True), volume=10)
    row = next(r for r in rows if r["card"] == "mlx:installed/someone/Kanji-VL-4bit@abc")
    assert row["reader"] == "vision" and row["not_scored"] is None
    assert _override({"hf": "someone/Kanji-VL-4bit", "revision": "abc"}) == ("omlx", "someone/Kanji-VL-4bit")


# --- Kraken's repository ------------------------------------------------------------------------------


def test_kraken_repository_readers_for_fraktur_are_found_cached_and_ranked(client, store, repository):
    body, items, sources = _candidates(client, scripts="Latf", languages="sv", online="true")
    assert sources["kraken-repository"]["state"] == "searched" and repository == [1]

    swedish = items["kraken:zenodo/10.5281/zenodo.20702142@pinned"]
    # The record names Swedish, the project's language, so its published CER is ranked on.
    assert swedish["cer_published"] == pytest.approx(0.012) and swedish["rule_rank"] == 1
    assert swedish["source"] == "kraken-repository" and swedish["licence"] == "CC-BY-4.0"
    assert "unmeasured" in swedish["measured"]
    assert "kraken:zenodo/10.5281/zenodo.19188500@pinned" in items  # stated Latf
    # A Latn record whose card says Fraktur covers Fraktur too.
    assert "Latf" in items["kraken:zenodo/10.5281/zenodo.7933402@pinned"]["scripts"]
    # The shipped McCATMuS card is not listed twice; a segmentation model is not a reader.
    assert not any("13788177@pinned" in i or "99999999" in i for i in items)

    # Read again from the cache, with no network: the listing is not fetched twice in a day.
    _, again, sources = _candidates(client, scripts="Latf", languages="de")
    assert sources["kraken-repository"]["state"] == "cached" and repository == [1]
    # Not the project's language: the CER is shown in words, not ranked on.
    assert again["kraken:zenodo/10.5281/zenodo.20702142@pinned"]["cer_published"] is None
    assert "not your languages" in again["kraken:zenodo/10.5281/zenodo.20702142@pinned"]["offered_because"]


def test_after_a_search_the_recipe_has_a_fraktur_and_a_kuzushiji_reader_instead_of_a_gap(client, store, repository):
    gap = client.post("/api/recipes/assemble", json={"purpose": "transcribe", "languages": ["de"],
                                                     "scripts": ["Latf"], "mac_memory_gb": 32}).json()
    assert next(s for s in gap["steps"] if s["job"] == "read-a-line").get("gap")

    _candidates(client, scripts="Latf", online="true")
    for scripts, languages in ((["Latf"], ["de"]), (["Jpan"], ["ja"])):
        r = client.post("/api/recipes/assemble", json={"purpose": "transcribe", "languages": languages,
                                                       "scripts": scripts, "mac_memory_gb": 32})
        step = next(s for s in r.json()["steps"] if s["job"] == "read-a-line")
        assert step.get("gap") is None and step["card"]["source"] == "kraken-repository", step
        assert "zenodo" in step["model"] and any("Kraken's model repository" in x for x in step["reasons"])


# --- Hugging Face -------------------------------------------------------------------------------------


def test_the_hub_search_offers_only_builds_this_mac_runs_each_saying_why(client, store, repository, hub):
    body, items, sources = _candidates(client, scripts="Jpan", languages="ja", online="true")
    assert sources["hugging-face"]["state"] == "searched"
    found = {i: c for i, c in items.items() if c["source"] == "hugging-face"}
    assert "mlx:hf/mlx-community/GLM-OCR-4bit@main" in found
    assert "mlx:hf/masahiroid/manga-ocr-base-mlx@main" in found
    assert all("gguf" not in i.lower() for i in found)  # the Jackrong/*-GGUF chat models the old search found
    # A safetensors original is offered as its MLX conversion, saying so.
    sarashina = found["mlx:hf/tokimoa/sarashina2.2-ocr-mlx-4bit@main"]
    assert "MLX conversion of sbintuitions/sarashina2.2-ocr" in sarashina["offered_because"]
    # Found readers join the rules since they download like a catalogue model (#5593,
    # `source.find.found-reader-downloads`): each is ranked, or refused with its reason.
    assert all(c["offered_because"] and c["in_recipe_rules"] is True for c in found.values())
    assert all((c["rule_rank"] is None) == (c["refused"] is not None) for c in found.values())
    lfm = found["mlx:hf/LiquidAI/LFM2.5-VL-3B-MLX-4bit@main"]
    assert lfm["open_licence"] is False and "licence" in lfm["refused"]  # license:other
    # Asked by task and language tag, never by keyword, and MLX by its tag.
    assert "image-to-text|mlx,ja" in hub and all("mlx" in k or k.endswith("|ja") for k in hub)


def test_working_offline_reaches_no_network_and_says_so(client, store, repository, hub, monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    _, _, sources = _candidates(client, scripts="Jpan", languages="ja", online="true")
    assert sources["kraken-repository"]["state"] == "offline"
    assert sources["hugging-face"]["state"] == "offline" and "offline" in sources["hugging-face"]["detail"]
    assert repository == [] and hub == []


def test_without_online_nothing_is_fetched(client, store, repository, hub):
    _, _, sources = _candidates(client, scripts="Hani", languages="zh")
    assert sources["kraken-repository"]["state"] == "not-searched"
    assert sources["hugging-face"]["state"] == "not-searched"
    assert repository == [] and hub == []


def test_an_unknown_script_is_refused_in_words(client, store):
    r = client.get("/api/recipes/candidates", params={"scripts": "Zzzq"})
    assert r.status_code == 422 and "script" in r.text


def test_scripts_cover_their_parts():
    assert {"Jpan", "Hani", "Hans"} <= discovery.covered_scripts({"Hani", "Hira", "Kana"})
    assert "Hani" in discovery.covered_scripts({"Jpan"})
    assert discovery.covered_scripts({"Latn"}) == {"Latn"}
