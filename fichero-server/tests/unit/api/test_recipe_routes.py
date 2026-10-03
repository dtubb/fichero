"""The recipe routes setup calls (`source.onboard.deterministic-recipe`, `source.recipe.jobs-are-a-registry`).

Why it matters: the setup window, the Inspector, the CLI and MCP must all get the same answer from
the engine. If the route stops returning reasons and gaps, setup shows a recipe nobody can question.
"""
from __future__ import annotations


def test_the_job_registry_is_served_with_its_descriptions(client):
    r = client.get("/api/recipes/jobs")
    assert r.status_code == 200, r.text
    jobs = {j["id"]: j for j in r.json()["items"]}
    assert "find-lines" in jobs and jobs["find-lines"]["description"]


def test_assembling_spanish_letters_names_its_choices_and_reasons(client):
    r = client.post("/api/recipes/assemble", json={
        "purpose": "search", "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16})
    assert r.status_code == 200, r.text
    body = r.json()
    steps = {s["job"]: s for s in body["steps"]}
    assert steps["find-lines"]["model"]["kraken"] == "blla"
    assert steps["read-a-line"]["reasons"]
    assert body["gaps"] == [] and body["problems"] == []


def test_checking_a_recipe_with_code_in_it_names_the_problem(client):
    r = client.post("/api/recipes/check", json={"recipe": {
        "fichero_recipe": 1, "id": "x", "version": "1", "title": "x",
        "steps": [{"id": "a", "job": "find-lines", "settings": {"command": "rm -rf ~"}}]}})
    assert r.status_code == 200
    assert any("command" in p for p in r.json()["problems"])
