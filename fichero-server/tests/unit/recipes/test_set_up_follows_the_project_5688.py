"""Set Up follows the project as saved (#5688), tested to the spec: `source.onboard.material.which-hand`,
`source.find.choose-a-model-opens-the-finder` and `source.onboard.stages.compares-candidates`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the overnight MCP walk (2026-10-11): list-hands ignored the saved period and offered Kurrent (German) to a
Spanish project; the finder said `chosen: false` for every card, the step's own included; a Names try compared one
candidate though another pipeline was installed.
"""

from __future__ import annotations

import pytest

from fichero_server.recipes import discovery

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "period": "16th century"}


def _save(client, answers=ANSWERS, jobs=()):
    recipe = client.post("/api/recipes/assemble", json={**answers, "jobs": list(jobs)}).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    return recipe


def test_the_hands_offered_follow_the_projects_saved_period_and_language(client, with_material, db):
    _save(client)
    listed = client.get("/api/recipes/hands").json()
    ids = {h["id"] for h in listed["items"]}
    assert listed["period_years"] == [1501, 1600]
    assert "procesal" in ids and "kurrent" not in ids and "caroline-minuscule" not in ids


def test_the_steps_own_model_is_chosen_when_no_step_is_named(client, with_material, db):
    recipe = _save(client, jobs=["find-regions"])
    own = next(s for s in recipe["steps"] if s["job"] == "find-regions")["card"]["id"]
    items = client.get("/api/recipes/candidates", params={"job": "find-regions", "scripts": "Latn"}).json()["items"]
    assert [i["id"] for i in items if i["chosen"]] == [own]


def test_an_installed_spacy_pipeline_is_a_names_candidate(monkeypatch):
    from fichero_server.llm import local_models

    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: name in {"es_core_news_sm",
                                                                                         "es_core_news_md"})
    cards = {c.pin.get("spacy") for c in discovery.installed_spacy_cards(frozenset({"es"}), seed=())}
    assert {"es_core_news_sm", "es_core_news_md"} <= cards and "es_core_news_lg" not in cards
