"""Set Up › Ready offers a model a step can run with (#5619), tested to the spec
(docs/contributor_manual/specs/source/models-chains-and-projects.md: `source.recipe.fichero-does-it-steps`,
`source.recipe.local-text-models-are-cards`, `source.find.choose-a-model-opens-the-finder`).

WHY: the maintainer's Ready page said "Fichero has no model for Split pages / Work out dates / Find statements yet"
on a Mac with Ollama and MLX models, and Choose a model… did nothing. Split pages and Work out dates need no model
(Fichero's page splitter and date rules); Find statements is a text model's job, and a text model already on this
Mac, or on a server of the person's own, is that model. Through the public routes the app calls
(`POST /api/recipes/assemble`, `PUT /api/recipes/project`, `GET /api/recipes/project/start`,
`GET /api/recipes/candidates`, `POST /api/recipes/project/steps/use-candidate`); this Mac's model store is stubbed
(`mac`) and the provider rows are the test's own app database: nothing is downloaded or called.
"""
from __future__ import annotations

import pytest

from fichero_server.models import Model, Provider, ProviderType
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)


def _assemble(client, **answers):
    body = {"languages": ["en"], "scripts": ["Latn"], "mac_memory_gb": 16, **answers}
    r = client.post("/api/recipes/assemble", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _step(recipe: dict, job: str) -> dict:
    return next(s for s in recipe["steps"] if s["job"] == job)


def _ollama(app_db, url: str):
    """The person's Ollama server at `url`: a chat model and an embedder."""
    row = app_db.save_provider(Provider(name="Ollama", provider_type=ProviderType.ollama, api_base=url))
    app_db.save_model(Model(provider_id=row.id, name="Llama 3.2", model_id="llama3.2:latest"))
    app_db.save_model(Model(provider_id=row.id, name="Nomic Embed", model_id="nomic-embed-text:latest"))
    return row


@pytest.fixture
def ollama(app_db):
    """The person's Ollama server on this Mac."""
    return _ollama(app_db, "http://localhost:11434")


# --- source.recipe.fichero-does-it-steps -------------------------------------------------------------------------


def test_split_pages_and_work_out_dates_are_fichero_s_own_steps_never_no_model(client, db, pages, mac):
    """source.recipe.fichero-does-it-steps: "Split pages runs the built-in page splitter … Work out dates runs
    Fichero's date rules … a step Fichero carries out itself needs no model and never says it has none." Both are
    steps with their built-in, on this Mac, with no problem; the Start plan runs them, skipping neither."""
    recipe = _assemble(client, purposes=["knowledge-graph"], jobs=["split-pages"])
    split, dates = _step(recipe, "split-pages"), _step(recipe, "work-out-dates")
    assert split["model"] == {"builtin": "page-splitter"} and dates["model"] == {"builtin": "date-rules"}
    for step in (split, dates):
        assert step["runs_on"] == "this-mac" and step["uses_cloud"] is False
        assert step.get("problem") is None and step.get("gap") is None
        assert any("free" in why for why in step["reasons"])
    assert not any(g.startswith(("split-pages", "work-out-dates")) for g in recipe["gaps"])

    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["knowledge-graph"], "cloud_allowed": False},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text
    plan = client.get("/api/recipes/project/start").json()
    skipped = {s["step"] for s in plan["skipped"]}
    assert "split-pages" not in skipped and "work-out-dates" not in skipped, plan["skipped"]
    ran = [w["workflow"] for w in plan["workflows"]]
    assert "Split Pages" in ran, ran


# --- source.recipe.local-text-models-are-cards --------------------------------------------------------------------


def test_an_ollama_model_on_this_mac_finds_the_statements_free_and_here(client, db, pages, mac, ollama):
    """source.recipe.local-text-models-are-cards: "every enabled model of the person's Ollama or LM Studio rows (not
    an embedder) … a server on this Mac runs on this Mac, free, and never counts as sending pages off it." A project
    that keeps its pages here gets Find statements with the Ollama model, by name; Start runs it with that model."""
    recipe = _assemble(client, purposes=["statements"], cloud_allowed=False)
    step = _step(recipe, "find-statements")
    assert step["model"] == {"cloud": "ollama", "model": "llama3.2:latest"}, step
    assert step["runs_on"] == "this-mac" and step["uses_cloud"] is False
    assert step["card"]["note"] == "Llama 3.2 on Ollama" and step["card"]["source"] == "installed"
    assert step.get("problem") is None

    r = client.put("/api/recipes/project", json={"answers": {"purposes": ["statements"], "cloud_allowed": False},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text
    plan = client.get("/api/recipes/project/start").json()
    assert "find-statements" not in {s["step"] for s in plan["skipped"]}, plan["skipped"]
    run = next(w for w in plan["workflows"] if "find-statements" in w["steps"])
    assert (run["provider_override"], run["model_override"]) == ("ollama", "llama3.2:latest")


def test_an_embedder_is_never_a_card_for_statements(client, mac, ollama):
    """"… (not an embedder)": the Ollama embedder is never offered for a text job."""
    items = _candidates(client, "find-statements")
    assert any(i["pin"].get("model") == "llama3.2:latest" for i in items)
    assert not any("embed" in str(i["pin"].get("model")) for i in items)


def test_an_ollama_on_another_machine_is_free_but_its_pages_leave(client, mac, app_db):
    """"… one on another machine of the person's own is free but its pages leave this Mac, so it is chosen only
    where the project lets pages leave." Kept here: the step says why it has no model (the cloud question);
    pages may leave: the step runs there, free, and says it leaves this Mac."""
    _ollama(app_db, "http://studio.example.net:11434")
    kept = _step(_assemble(client, purposes=["statements"], cloud_allowed=False), "find-statements")
    assert kept["problem"]["kind"] == "cloud-not-allowed" and kept["problem"]["fix"] == "allow-cloud"

    leaves = _step(_assemble(client, purposes=["statements"], cloud_allowed=True), "find-statements")
    assert leaves["model"] == {"cloud": "ollama", "model": "llama3.2:latest"}
    assert leaves["runs_on"] == "cloud:ollama" and leaves["uses_cloud"] is True
    candidate = next(i for i in _candidates(client, "find-statements") if i["pin"].get("model") == "llama3.2:latest")
    assert candidate["runs_where"] == "own_machine" and candidate["download"] is None


def test_an_mlx_model_in_the_store_finds_the_statements(client, mac):
    """"every MLX model complete in this Mac's model store that reads text (its card made from the store's own
    facts, licence included)": with no Ollama, the installed Qwen2.5-VL 7B (Apache-2.0) does Find statements."""
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

    mac.installed.add("Qwen2.5-VL-7B")
    seven = MANAGED_MLX_MODELS["Qwen2.5-VL-7B"]
    step = _step(_assemble(client, purposes=["statements"], mac_memory_gb=32), "find-statements")
    assert step["model"] == {"hf": seven.repo_id, "revision": seven.revision}, step.get("problem")
    assert step["runs_on"] == "this-mac" and step["card"]["licence"] == "Apache-2.0"
    assert any("already on this Mac" in why for why in step["reasons"])


def test_with_no_text_model_here_the_step_says_so_with_the_finder_as_its_fix(client, mac):
    """With nothing installed the step still says, in words, that no model is here, and its fix is the finder
    (choose-model), never a dead end."""
    step = _step(_assemble(client, purposes=["statements"]), "find-statements")
    assert step["problem"]["kind"] == "no-model-for-job"
    assert step["problem"]["fix"] == "choose-model"


# --- source.find.choose-a-model-opens-the-finder ------------------------------------------------------------------


def _candidates(client, job, **params):
    r = client.get("/api/recipes/candidates", params={"job": job, "scripts": "Latn", "languages": "en", **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_the_finder_answers_for_any_steps_job_and_says_why_it_did_not_search(client, db, pages, mac, ollama):
    """source.find.choose-a-model-opens-the-finder: "The finder answers for any job a card can name … the online
    search looks for readers only, so for any other job it is not run and the source says so." Then Use for This
    Step sets the found model as the step's model."""
    r = client.get("/api/recipes/candidates",
                   params={"job": "find-statements", "scripts": "Latn", "languages": "en", "online": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["search_job"] is None
    hub = next(s for s in body["sources"] if s["source"] == "hugging-face")
    assert hub["state"] == "offline" or (hub["state"] == "not-searched" and "readers only" in hub["detail"]), hub
    installed = next(s for s in body["sources"] if s["source"] == "installed")
    assert installed["count"] >= 1 and "Ollama" in installed["detail"]
    [llama] = [i for i in body["items"] if i["pin"].get("model") == "llama3.2:latest"]
    assert llama["rule_rank"] == 1 and llama["refused"] is None and llama["runs_where"] == "this_mac"

    recipe = {"fichero_recipe": 1, "id": "t/s", "version": "0.1.0", "title": "t",
              "steps": [{"id": "statements", "job": "find-statements", "model": None,
                         "problem": {"sentence": "Fichero has no model for “Find statements” yet."}}]}
    assert client.put("/api/recipes/project", json={"answers": {"purpose": "statements"},
                                                    "recipe": recipe}).status_code == 200
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": "statements", "card": llama["id"]})
    assert used.status_code == 200, used.text
    step = next(s for s in used.json()["recipe"]["steps"] if s["id"] == "statements")
    assert step["model"] == {"cloud": "ollama", "model": "llama3.2:latest"}


def test_an_unknown_job_is_refused_in_words(client):
    r = client.get("/api/recipes/candidates", params={"job": "make-tea", "scripts": "Latn"})
    assert r.status_code == 422 and "make-tea" in r.text
