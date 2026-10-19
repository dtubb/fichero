"""Set Up's steps, as the maintainer's own test asked for them (#5660 items 1 and 4).

Item 1, "Translate or normalise › Into what" is several: as written, abbreviations expanded and normalised spelling
are three of the page model's reading levels (#5651, #5653), and a person may want all three. The answer is a list;
each level asked is one run that writes a transcription at that level (or a translation); a project saved with one
value reads as a list of one.

Item 4, the person chooses who runs Find names: spaCy on this Mac (the shipped pipeline, the default), Apple
Intelligence (where this build and this Mac have it, else said "not available yet"), an MLX model, or a cloud model
(Claude) through the provider settings. The use-candidate route keeps the choice and the Start plan runs with it.

Through the routes Set Up calls; this Mac's model store is stubbed (`mac`), nothing is downloaded or run.
"""

from __future__ import annotations

import pytest

from fichero_server.recipes.answers import normalise_levels
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_models_ux_5619 import ollama  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)

QWEN = {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"}
LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def _normalise(target):
    step = {"id": "normalise", "job": "translate-transliterate-normalise", "model": QWEN,
            "settings": {} if target is None else {"target": target}}
    return {"fichero_recipe": 1, "id": "t/levels", "version": "0.1.0", "title": "t", "steps": [LINES, READ, step]}


def _level_runs(plan):
    return [r for r in plan["runs"] if "normalise" in r["steps"]]


# --- item 1 ---------------------------------------------------------------------------------------------------


def test_into_what_is_a_list_and_a_single_saved_value_reads_as_one():
    assert normalise_levels(["normalised", "as-written", "abbreviations-expanded"]) == (
        ["as_written", "expanded", "regularised"], [])  # cascade order, the engine's spelling
    assert normalise_levels("normalised") == (["regularised"], [])  # a project saved before #5660
    assert normalise_levels(["expanded", "translation:Spanish"]) == (["expanded", "translation:es"], [])
    levels, problems = normalise_levels(["sideways"])
    assert levels == ["sideways"] and "no level 'sideways'" in problems[0]


def test_each_level_asked_is_a_run_that_writes_that_level(mac):
    plan = plan_start(_normalise(["as_written", "expanded"]), stays_local=True)
    runs = _level_runs(plan)
    assert [r["tool_config"]["analyze"]["reading_level"] for r in runs] == ["as_written", "expanded"]
    assert all(r["tool_config"]["analyze"]["reading_kind"] == "transcription" for r in runs)
    assert all(r["provider_override"] == "omlx" for r in runs)  # the step's model reads each one
    assert "abbreviation" in runs[1]["tool_config"]["analyze"]["prompt"]
    assert not [s for s in plan["skipped"] if s["step"] == "normalise"]


def test_the_old_single_answer_still_gives_one_run(mac):
    [run] = _level_runs(plan_start(_normalise("normalised"), stays_local=True))
    assert run["tool_config"]["analyze"]["reading_level"] == "regularised"


def test_a_translation_asked_beside_the_levels_is_a_translation_run(mac):
    runs = _level_runs(plan_start(_normalise(["regularised", "translation:en"]), stays_local=True))
    configs = [r["tool_config"]["analyze"] for r in runs]
    assert [(c["reading_kind"], c["reading_level"]) for c in configs] == [
        ("transcription", "regularised"), ("translation", None)]
    assert "into English" in configs[1]["prompt"]


def test_a_step_run_per_level_is_named_once_where_it_waits_for_its_model(mac):
    """Two levels are two runs of one step: the download they wait for, and the refusal that names it, list the
    step once (B found "steps correct, translate-transliterate-normalise, translate-transliterate-normalise")."""
    recipe = _normalise(["as_written", "expanded"])
    recipe["steps"].insert(2, {"id": "correct", "job": "correct", "model": QWEN, "runs_on": "this-mac"})
    plan = plan_start(recipe, stays_local=True)
    [download] = [d for d in plan["downloads"] if d["runtime"] == "mlx"]
    assert download["steps"] == ["correct", "normalise"]
    said = " ".join(" ".join(i["steps"]) for i in plan["start_downloads"]["items"])  # what Ready says it fetches
    assert said.count("normalise") == 1, said


def test_set_up_carries_the_list_to_the_step(client, db, pages, mac):
    answers = {"purposes": ["translate-normalise"], "languages": ["es"], "scripts": ["Latn"],
               "materials": ["handwriting"], "mac_memory_gb": 32,
               "job_answers": {"normalise_how_far": ["as-written", "normalised"]}}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    [step] = [s for s in recipe.json()["steps"] if s["job"] == "translate-transliterate-normalise"]
    assert step["settings"] == {"target": ["as_written", "regularised"]}
    assert step.get("model"), step  # the Qwen VL cards write the levels
    refused = client.post("/api/recipes/assemble", json={**answers, "job_answers": {"normalise_how_far": ["sideways"]}})
    assert refused.status_code == 422 and "no level 'sideways'" in refused.json()["detail"]


# --- item 4 ---------------------------------------------------------------------------------------------------


def _names(client, **params):
    r = client.get("/api/recipes/candidates", params={"job": "find-names-tag-words", "scripts": "Latn",
                                                      "languages": "es", **params})
    assert r.status_code == 200, r.text
    return {c["id"]: c for c in r.json()["items"]}


@pytest.fixture
def claude_row(app_db):
    from fichero_server.models import Model, Provider, ProviderType

    row = app_db.save_provider(Provider(name="Anthropic", provider_type=ProviderType("anthropic")))
    app_db.save_model(Model(provider_id=row.id, name="Claude Sonnet", model_id="claude-sonnet-4-5"))
    return row


def test_find_names_offers_spacy_apple_mlx_and_the_cloud_saying_what_runs(client, mac, monkeypatch):
    monkeypatch.setattr("fichero_server.llm.local_model_choice.apple_intelligence_in_this_build", lambda: False)
    items = _names(client)
    spacy = items["spacy:pkg/es_core_news_sm@bundled"]
    assert spacy["rule_rank"] == 1 and spacy["availability"] == "ships"  # the default: the shipped pipeline
    apple = items["apple:intelligence/foundation-models@os"]
    assert apple["availability"] == "not_here" and apple["rule_rank"] is None
    assert apple["availability_words"] == ("Fichero cannot run it yet (Apple Intelligence is not available in this "
                                           "build or on this Mac)")
    mlx = [c for c in items.values() if c["id"].startswith("mlx:text/")]
    assert mlx and all(c["availability"] == "download" and c["download"]["runtime"] == "mlx" for c in mlx)
    claude = items["anthropic:claude@settings"]
    assert claude["availability"] == "not_here" and "add Claude (Anthropic) in Settings" in claude["availability_words"]


def test_a_configured_cloud_model_is_offered_and_kept_where_pages_may_leave(client, mac, claude_row, with_material):
    items = _names(client)
    [card] = [c for c in items.values() if c["pin"] == {"cloud": "anthropic", "model": "claude-sonnet-4-5"}]
    assert card["runs_where"] == "provider" and card["refused"] and "cloud" in card["refused"]
    assert "anthropic:claude@settings" not in items  # configured: no "add it first" card
    allowed = _names(client, cloud_allowed=True)
    assert allowed[card["id"]]["refused"] is None


@pytest.mark.parametrize("who", ["mlx", "apple", "cloud"])
def test_the_person_chooses_who_finds_names_and_the_run_honours_it(client, db, pages, mac, claude_row, monkeypatch,
                                                                   who, with_material):
    monkeypatch.setattr("fichero_server.llm.local_model_choice.apple_intelligence_in_this_build", lambda: True)
    answers = {"purposes": ["transcribe", "entities"], "languages": ["es"], "scripts": ["Latn"],
               "materials": ["handwriting"], "cloud_allowed": who == "cloud", "mac_memory_gb": 32}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe.json()}).status_code == 200
    [step] = [s for s in recipe.json()["steps"] if s["job"] == "find-names-tag-words"]
    assert step["model"].get("spacy"), step  # spaCy until the person chooses

    items = _names(client, cloud_allowed=who == "cloud")
    card = {"mlx": next(c for c in items.values() if c["id"].startswith("mlx:text/")),
            "apple": items["apple:intelligence/foundation-models@os"],
            "cloud": next(c for c in items.values() if c["pin"].get("cloud") == "anthropic"
                          and c["pin"]["model"] == "claude-sonnet-4-5")}[who]
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": step["id"], "card": card["id"]})
    assert used.status_code == 200, used.text

    plan = client.get("/api/recipes/project/start").json()
    [run] = [r for r in plan["runs"] if r["job"] == "find-names-tag-words"]
    expected = {"mlx": ("omlx", None), "apple": ("apple", "apple-intelligence"),
                "cloud": ("anthropic", "claude-sonnet-4-5")}[who]
    assert run["provider_override"] == expected[0]
    assert expected[1] is None or run["model_override"] == expected[1]


@pytest.mark.parametrize("apple_here", [True, False])
def test_the_offered_choices_never_outrank_a_model_the_person_has(client, mac, ollama, monkeypatch, apple_here):
    """`source.recipe.local-text-models-are-cards`: a text model already here (an Ollama model on this Mac) is the
    finder's rank 1, whether or not this Mac has Apple Intelligence; the choices item 4 adds are the person's to
    make (`in_recipe_rules: false`, no rank), never the rules' (the M4, which has the bridge, ranked Apple first)."""
    monkeypatch.setattr("fichero_server.llm.local_model_choice.apple_intelligence_in_this_build", lambda: apple_here)
    r = client.get("/api/recipes/candidates", params={"job": "find-statements", "scripts": "Latn", "languages": "en"})
    items = {c["id"]: c for c in r.json()["items"]}
    [llama] = [c for c in items.values() if c["pin"].get("model") == "llama3.2:latest"]
    assert llama["rule_rank"] == 1 and llama["in_recipe_rules"] is True
    apple = items["apple:intelligence/foundation-models@os"]
    assert apple["rule_rank"] is None and apple["in_recipe_rules"] is False
    assert (apple["refused"] is None) == apple_here  # offered, or said that it cannot run here
