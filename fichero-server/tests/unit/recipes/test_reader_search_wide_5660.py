"""Search wide every time; the bake-off decides (#5660, ruled by the maintainer 2026-10-11; #5665's comma reader).

WHY: Set Up offered the rules' top three Kraken readers. A language with no Kraken reader got nothing worth trying,
and the readers made for old hands on Hugging Face (found by their tags, not their names) and the person's own remote
endpoints never took part. The ruling: search Kraken's repository, Hugging Face and the configured remote endpoints
every time, not as a fallback; found readers join the bake-off as contenders, at most two of each kind so a run stays
affordable, with its cost said before it starts; whichever wins is the default, not a fixed ranking.

Hugging Face is stubbed at its one fetch (`_fetch_hf_models`), keyed as the search asks it.
"""

from __future__ import annotations

import asyncio
import pytest

from fichero_server.recipes import bakeoff, discovery
from fichero_server.recipes.assemble import Answers, Card
from fichero_server.recipes.cards import all_seed_cards
from fichero_server.training import evaluation
from tests.unit.recipes.test_bakeoff_contenders_5660 import claude_row  # noqa: F401  (fixture)

COMMA = "wjbmattingly/comma-qwen-3.5-0.8b-full-33k"
KURRENT = "dh-unibe/trocr-kurrent"
COMMA_GGUF = "mradermacher/comma-qwen-3.5-9b-full-GGUF"

LISTINGS = {
    COMMA: {"id": COMMA, "pipeline_tag": "image-text-to-text", "downloads": 900, "library_name": "transformers",
            "tags": ["transformers", "safetensors", "qwen3_5", "image-text-to-text", "ocr", "htr",
                     "handwritten-text-recognition", "manuscripts", "palaeography", "catmus", "medieval-latin", "la",
                     "license:apache-2.0"]},
    KURRENT: {"id": KURRENT, "pipeline_tag": "image-to-text", "downloads": 4000, "library_name": "transformers",
              "tags": ["transformers", "safetensors", "vision-encoder-decoder", "image-to-text", "htr", "de",
                       "license:mit"]},
    COMMA_GGUF: {"id": COMMA_GGUF, "pipeline_tag": "image-text-to-text", "downloads": 50, "library_name": "gguf",
                 "tags": ["gguf", "htr", "catmus", "la", "license:apache-2.0"]},
}


@pytest.fixture
def hub(monkeypatch, tmp_path):
    """The Hub, by tag: a listing answers every query whose tags it carries (and whose task it is)."""
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        asked.append((task, tuple(tags or ()), search))
        if search or not tags or "mlx" in tags or any(t.startswith("base_model:") for t in tags):
            return []
        return [dict(m) for m in LISTINGS.values()
                if set(tags) <= set(m["tags"]) and (task is None or m["pipeline_tag"] == task)]

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    return asked


def _repo(card):
    """The Hub repository a card names, whichever runtime pin it carries (a TrOCR card pins `trocr`, #5981)."""
    return card.pin.get("hf") or card.pin.get("trocr") or card.pin.get("kraken_hf")


def _search(languages):
    found, _ = asyncio.run(discovery.search_hugging_face(frozenset(languages)))
    return found


def test_a_latin_project_finds_the_comma_reader_by_its_tags_and_it_runs_here(hub):
    found = _search({"la"})
    by_repo = {_repo(c): c for c in found}
    comma = by_repo[COMMA]
    assert comma.runs_here and comma.id == f"mlx:hf/{COMMA}@main"
    assert "in Fichero's MLX catalogue" in comma.offered_because and "lists Latin" in comma.offered_because
    # Found by the tags it is published under, never by a name search for "htr" (which misses it).
    assert any(tags == ("htr",) for _task, tags, search in hub if search is None)
    # The GGUF build is listed with how it could run, never offered as if it ran.
    gguf = by_repo[COMMA_GGUF]
    assert not gguf.runs_here and "GGUF build: cannot run yet" in gguf.offered_because
    # Ranked by language match, then downloads: the Latin readers before the German one with more downloads.
    order = [_repo(c) for c in found]
    assert order.index(COMMA) < order.index(COMMA_GGUF) < order.index(KURRENT)


def test_a_german_project_finds_trocr_kurrent_and_it_runs_here_since_5981(hub):
    """Was "cannot run yet" (#5660); #5981 made a TrOCR model a card that reads the lines Kraken found, on this Mac."""
    found = _search({"de"})
    kurrent = next(c for c in found if _repo(c) == KURRENT)
    assert kurrent.runs_here and kurrent.pin == {"trocr": KURRENT}
    assert "TrOCR" in kurrent.offered_because and "lists German" in kurrent.offered_because
    assert _repo(found[0]) == KURRENT  # it lists the project's language: first
    assert any(tags == ("de", "htr") for _task, tags, search in hub)


def test_the_comma_reader_is_a_card_the_bake_off_takes_for_latin(app_db, monkeypatch):
    """#5665: Daniel wants it in the bake-off. It is a shipped card, fetched by Fichero's MLX catalogue."""
    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: False)
    a = Answers(purposes=("transcribe",), languages=frozenset({"la"}), scripts=frozenset({"Latn"}),
                materials=("handwriting",), mac_memory_gb=16)
    named = {c["card"]: c for c in bakeoff.candidates(a, list(all_seed_cards()), volume=100)}
    comma = next(c for card, c in named.items() if COMMA in card)
    assert comma["role"] == "contender" and comma["reader"] == "vision" and comma["model"] == COMMA
    # At most two of each kind, and no fixed ranking crowns three Kraken readers.
    kinds = [bakeoff._family(next(x for x in all_seed_cards() if x.id == card)) for card in named
             if any(x.id == card for x in all_seed_cards())]
    assert max(kinds.count(k) for k in set(kinds)) <= bakeoff.PER_KIND
    assert all(c["role"] != "rule rank" for c in named.values())


def test_a_language_with_no_kraken_reader_still_gets_hugging_face_and_remote_contenders(app_db, claude_row,
                                                                                      monkeypatch):
    """A German Kurrent project: no Kraken reader covers its script, yet a Hub reader and the person's remote
    endpoint take part, and the cost of reading the sample is said before it starts."""
    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: False)
    a = Answers(purposes=("transcribe",), languages=frozenset({"de"}), scripts=frozenset({"Latf"}),
                materials=("handwriting",), mac_memory_gb=16, cloud_allowed=True)
    found_on_hub = Card(id="mlx:hf/someone/kurrent-vl-mlx@main", pin={"hf": "mlx-community/kurrent-vl", "revision": "main"},
                        jobs=discovery.READER_JOBS, scripts=None, languages=frozenset({"de"}), material=frozenset(),
                        open_licence=True, source="hugging-face", note="kurrent-vl")
    chosen = bakeoff.candidates(a, [*all_seed_cards(), found_on_hub], volume=1000, sample_pages=10)
    kinds = {bakeoff._family(c) for c in [*all_seed_cards(), found_on_hub, *bakeoff.cloud_readers()]
             if c.id in {x["card"] for x in chosen}}
    # A Latin-script reader reads Fraktur (#5516), so a Kraken one may take part; the Hub and cloud readers do too.
    assert {"mlx", "cloud"} <= kinds
    cloud = next(x for x in chosen if not x["local"] and x["not_scored"] is None)
    assert "10 pages" in cloud["run_cost_usd"]["from"]  # priced on the sample, not the whole volume

    monkeypatch.setattr(bakeoff, "ground_truth", lambda db, page_ids: ([{"document_id": f"p{i}", "name": "p",
                                                                         "lines": 30} for i in range(10)], []))
    said = bakeoff.next_run(None, a, [*all_seed_cards(), found_on_hub], volume=1000)
    assert said["pages"] == 10 and said["sentence"].startswith("The comparison costs ")
    assert "1 cloud reader on 10 pages" in said["sentence"]


def test_the_finder_lists_the_remote_endpoints_every_time(client, claude_row):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "la", "mac_memory_gb": 16})
    assert r.status_code == 200, r.text
    sources = {s["source"]: s for s in r.json()["sources"]}
    assert sources["remote-endpoints"]["count"] == 1 and "remote endpoints" in sources["remote-endpoints"]["detail"]
    remote = [c for c in r.json()["items"] if c["source"] == "remote"]
    assert remote and all("remote endpoint" in c["offered_because"] for c in remote if c["id"] != "anthropic:claude@settings")
    # Offered, never the rules': the bake-off measures it.
    assert all(c["in_recipe_rules"] is False for c in remote)
    # The comma reader is listed for Latin too, as a shipped card.
    assert any(COMMA in c["id"] for c in r.json()["items"])


def test_keeping_a_search_with_a_trocr_and_a_kraken_card_does_not_fail_on_hf(hub, tmp_path, monkeypatch):
    """The defaults matrix's search pass said "the Hugging Face search failed: 'hf'" on every set: `keep_hub` read `pin["hf"]` of a
    TrOCR card (pin `trocr`) and a Kraken repository card (pin `kraken_hf`), which only carry their own key."""
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    found = _search({"de"})
    assert any("hf" not in c.pin for c in found), "the fixture must hold a card without an hf pin"
    discovery.keep_hub(found, frozenset({"de"}))  # raised KeyError: 'hf'
    assert all(c["repo"] for c in discovery.cached_hub().values())
