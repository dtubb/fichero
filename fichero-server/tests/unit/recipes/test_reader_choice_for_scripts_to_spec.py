"""How a recipe picks a reader for an unusual script (#5593), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md, "Finding models":
`source.recipe.script-reader-first`, `source.recipe.no-cross-script-reader`, `source.find.found-reader-downloads`,
`source.onboard.nothing-fits-names-nearest`).

WHY: the esoteric-languages run of 2026-10-07 (15 languages, through the CLI). A "Pretrained multilingual Party base
model" with a published CER of 0.1% outranked six Fraktur cards, a printed-Ottoman card and a printed-Syriac card, for
print and handwriting alike; Classical Chinese (`Hant`) was given the Kuzushiji (Japanese cursive) reader with no word
said; Hugging Face readers found for Tamil never reached the Start plan (`downloads: []`); and "nothing fits" named no
nearest reader while its detail was a 4 KB dump of refused card ids.

Through the routes the app and MCP call (`GET /api/recipes/candidates`, `POST /api/recipes/assemble`,
`PUT /api/recipes/project`, `GET /api/recipes/project/start`). Kraken's repository is read from a listing kept in the
test's own model store, as the engine keeps its last fetch; the Hub's answers are recorded; nothing reaches the network.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from fichero_server.recipes import discovery

PARTY = "kraken:zenodo/10.5281/zenodo.20642057@pinned"
GERMAN_PRINTS = "kraken:zenodo/10.5281/zenodo.90000001@pinned"
GERMAN_HANDS = "kraken:zenodo/10.5281/zenodo.90000002@pinned"
OTTOMAN_PRINT = "kraken:zenodo/10.5281/zenodo.90000003@pinned"
KUZUSHIJI = "kraken:zenodo/10.5281/zenodo.13942714@pinned"
TAMIL = "someone/indic-ocr-mlx"


def _row(doi: str, summary: str, scripts: list[str], languages: list[str], cer: float,
         keywords: tuple[str, ...] = ("kraken_pytorch",)) -> dict:
    return {"doi": doi, "concept_doi": "", "summary": summary, "licence": "CC-BY-4.0", "scripts": scripts,
            "languages": languages, "keywords": sorted(keywords), "cer_percent": cer, "size_bytes": 20_000_000,
            "published": "2026-01-01"}


#: The repository records the 2026-10-07 run met, as discovery keeps them (`repository_rows`).
RECORDS = [
    _row("10.5281/zenodo.20642057", "Pretrained multilingual Party base model",
         ["Arab", "Cyrl", "Glag", "Grek", "Latn", "Syrc"], ["deu", "ota", "syr", "chu", "ell"], 0.1,
         ("kraken_pytorch", "fraktur", "multilingual")),
    _row("10.5281/zenodo.90000001", "OCR model for German prints", ["Latf"], ["deu"], 1.3),
    _row("10.5281/zenodo.90000002", "Kraken model for German manuscripts in Kurrent", ["Latf"], ["deu"], 3.9),
    _row("10.5281/zenodo.90000003", "Printed Ottoman Base Model", ["Arab"], ["ota"], 2.0),
    _row("10.5281/zenodo.13942714", "Kuzushiji", ["Jpan"], [], 4.05, ("kraken_pytorch", "japanese", "kuzushiji")),
]


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A model store of the test's own holding the repository listing as last fetched (today), an engine
    allowed to reach the network (which the Hub stub stands in for), and a 16 GB Apple-silicon Mac."""
    from fichero_server.llm.local_inference import LocalInferenceCapabilities
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    root = tmp_path / "store"
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(root))
    monkeypatch.delenv("FICHERO_KRAKEN_DATA_DIR", raising=False)
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    monkeypatch.setattr("fichero_server.llm.local_inference.get_local_inference_capabilities",
                        lambda: LocalInferenceCapabilities(system="Darwin", machine="arm64", is_apple_silicon=True,
                                                           physical_memory_bytes=16 * 1024**3,
                                                           macos_version="26.0"))
    folder = root / discovery.CACHE_FOLDER
    folder.mkdir(parents=True)
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (folder / discovery.REPOSITORY_FILE).write_text(json.dumps({"fetched_at": fetched, "records": RECORDS}))
    monkeypatch.setattr(discovery, "_harvest", lambda: pytest.fail("the repository is read from its last fetch"))
    return get_mlx_model_store()


@pytest.fixture
def hub(monkeypatch):
    """The Hub's answer for Tamil: one MLX OCR build tagged `ta`; every other query finds nothing."""
    asked = []

    async def fetch(task=None, search=None, sort="downloads", limit=20, offset=0, library=None, tags=None):
        key = f"{task or ''}|{','.join(tags or [])}"
        asked.append(key)
        if key == "image-to-text|mlx,ta":
            return [{"modelId": TAMIL, "library_name": "mlx", "pipeline_tag": "image-to-text",
                     "tags": ["mlx", "safetensors", "image-to-text", "ta", "license:apache-2.0"]}]
        return []

    monkeypatch.setattr("fichero_server.api.routes.ai.models._fetch_hf_models", fetch)
    return asked


def _assemble(client, languages, scripts, material="handwriting") -> dict:
    r = client.post("/api/recipes/assemble", json={"purposes": ["transcribe"], "languages": languages,
                                                   "scripts": scripts, "materials": [material], "mac_memory_gb": 32})
    assert r.status_code == 200, r.text
    return r.json()


def _reader(recipe: dict) -> dict:
    return next(s for s in recipe["steps"] if s["job"] == "read-a-line")


def _start_plan(client, recipe: dict, answers: dict) -> dict:
    r = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe})
    assert r.status_code == 200, r.text
    r = client.get("/api/recipes/project/start")
    assert r.status_code == 200, r.text
    return r.json()


# --- source.recipe.script-reader-first ------------------------------------------------------------------


def test_source_recipe_script_reader_first_fraktur_gets_a_fraktur_card_not_the_multilingual_base(client, store):
    """source.recipe.script-reader-first: "one made for the asked script comes before a generic one … A generic
    multilingual card never outranks it, however low its own CER … the same generic card is not chosen for print
    and handwriting alike." Fraktur print gets the German-prints card, Fraktur handwriting the manuscripts card;
    the Party base model (CER 0.1%) is chosen for neither."""
    printed = _reader(_assemble(client, ["de"], ["Latf"], "print"))
    assert printed["card"]["id"] == GERMAN_PRINTS, printed
    assert any(r == "made for Latf" for r in printed["reasons"]) and "made for print" in printed["reasons"]

    written = _reader(_assemble(client, ["de"], ["Latf"], "handwriting"))
    assert written["card"]["id"] == GERMAN_HANDS, written

    # The candidates list ranks them the same way: the Party base model is a candidate, below both.
    r = client.get("/api/recipes/candidates", params={"scripts": "Latf", "languages": "de", "material": "print",
                                                      "mac_memory_gb": 32})
    ranks = {c["id"]: c["rule_rank"] for c in r.json()["items"]}
    assert ranks[GERMAN_PRINTS] == 1 and ranks[PARTY] is not None and ranks[PARTY] > 1


def test_source_recipe_script_reader_first_printed_ottoman_beats_the_base_model_and_pp_ocr(client, store):
    """The Ottoman print card, made for Arabic script and listing Ottoman Turkish, comes before the Party base model
    and the shipped multilingual PP-OCRv6 card, both trained on many scripts."""
    step = _reader(_assemble(client, ["ota"], ["Arab"], "print"))
    assert step["card"]["id"] == OTTOMAN_PRINT, step


def test_source_recipe_script_reader_first_keeps_pp_ocr_for_spanish(client, store):
    """A Latin-script project with no Latin-only card that states a CER for its language keeps PP-OCRv6, the
    reader with a published CER (the flagship's choice is unchanged by the tier)."""
    step = _reader(_assemble(client, ["es"], ["Latn"], "handwriting"))
    assert step["model"] == {"zenodo": "10.5281/zenodo.21788410"}, step


# --- source.recipe.no-cross-script-reader + source.onboard.nothing-fits-names-nearest -------------------


def test_source_recipe_no_cross_script_reader_classical_chinese_is_not_given_the_japanese_reader(client, db, store):
    """source.recipe.no-cross-script-reader: "a Japanese card covers Han, kana and Japanese, never Traditional or
    Simplified Chinese." source.onboard.nothing-fits-names-nearest: the step says nothing reads Traditional Han, in
    one short sentence naming the nearest reader by name, never an id; the Start plan says the same."""
    answers = {"purposes": ["transcribe"], "languages": ["lzh"], "scripts": ["Hant"], "materials": ["handwriting"],
               "mac_memory_gb": 32}
    recipe = _assemble(client, ["lzh"], ["Hant"])
    step = _reader(recipe)
    assert step.get("model") is None and step.get("card") is None, step
    problem = step["problem"]
    assert problem["kind"] == "no-model-for-script"
    assert problem["sentence"].startswith("No reading model here reads Han (Traditional variant) yet.")
    assert "Kuzushiji (reads Japanese, a related script)" in problem["sentence"], problem["sentence"]
    assert [n["card"] for n in problem["nearest"]] == [KUZUSHIJI]
    for raw in ("kraken:", "zenodo", "@", "mlx:", "hf/"):
        assert raw not in problem["sentence"]

    plan = _start_plan(client, recipe, answers)
    [skipped] = [s for s in plan["skipped"] if s["step"] == "read-a-line"]
    assert "No reading model here reads Han (Traditional variant) yet" in skipped["why"]
    assert "Kuzushiji" in skipped["why"] and "zenodo" not in skipped["why"]


def test_source_onboard_nothing_fits_names_nearest_keeps_the_refusals_out_of_the_sentence(client, store):
    """"`detail` is one short line; every refused card and why stays in the structured `refused` list." A Coptic
    project, which no card reads: the sentence is the one plain sentence, the detail counts the refusals by reason
    instead of listing ~45 card ids (it names two per reason), and `refused` names each card."""
    problem = _reader(_assemble(client, ["cop"], ["Copt"]))["problem"]
    assert problem["sentence"] == "No reading model here reads Coptic yet."
    assert len(problem["detail"]) < 300 and problem["detail"].count("@") == 2, problem["detail"]
    assert "more)" in problem["detail"]
    refused = {r["card"]: r["why"] for r in problem["refused"]}
    assert refused[PARTY] == "its card does not cover the project's script"
    assert KUZUSHIJI in refused and len(refused) >= len(RECORDS)


# --- source.find.found-reader-downloads --------------------------------------------------------------------


def test_source_find_found_reader_downloads_a_tamil_reader_found_online_is_offered_in_the_plan(
        client, db, store, hub):
    """source.find.found-reader-downloads: "a Hugging Face reader found by the online search is kept … joins the
    rules for the languages it was found for (never the network at assembly), and where the rules choose it the
    Start plan offers it as a download … a size the Hub did not state is said to be unknown, never zero.\""""
    before = _reader(_assemble(client, ["ta"], ["Taml"]))
    assert before.get("model") is None, "nothing found yet: no Tamil reader"

    r = client.get("/api/recipes/candidates", params={"scripts": "Taml", "languages": "ta", "online": "true",
                                                      "mac_memory_gb": 32})
    found = next(c for c in r.json()["items"] if c["id"] == f"mlx:hf/{TAMIL}@main")
    assert found["in_recipe_rules"] is True and found["rule_rank"] == 1

    asked = list(hub)
    recipe = _assemble(client, ["ta"], ["Taml"])
    assert hub == asked, "assembly reads what the search kept, never the network"
    step = _reader(recipe)
    assert step["model"] == {"hf": TAMIL, "revision": "main"} and step["card"]["source"] == "hugging-face"
    assert "to download first (its size is not stated)" in step["reasons"]

    answers = {"purposes": ["transcribe"], "languages": ["ta"], "scripts": ["Taml"], "materials": ["handwriting"],
               "mac_memory_gb": 32}
    plan = _start_plan(client, recipe, answers)
    [download] = [d for d in plan["downloads"] if d["runtime"] == "mlx"]
    assert download["model"] == TAMIL and "read-a-line" in download["steps"] and download["size_mb"] is None
    assert download["action"] == "model.download" and download["params"] == {"runtime": "mlx", "model": TAMIL}
    assert any(f"wait for {TAMIL.split('/')[-1]} (size not stated)" in r for r in plan["refusals"]), plan["refusals"]
    # The model store downloads it by that name, as it downloads a catalogue model.
    assert store.canonical_id(TAMIL) == TAMIL and store.spec(TAMIL).revision == "main"
    assert not store.is_complete(store.spec(TAMIL))
