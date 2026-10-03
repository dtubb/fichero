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


def test_setup_reads_its_purposes_from_the_engine(client):
    """The purposes, their labels and whether each runs by itself come from one list in the engine,
    so setup, the Inspector and the manual never disagree (`source.onboard.purpose-first`)."""
    r = client.get("/api/recipes/purposes")
    assert r.status_code == 200, r.text
    items = {p["id"]: p for p in r.json()["items"]}
    assert items["transcribe"]["runs_by_itself"] is True
    assert items["decipher"]["runs_by_itself"] is False
    assert all(p["title"] and p["description"] for p in items.values())


def test_an_assembled_step_names_its_card(client):
    r = client.post("/api/recipes/assemble", json={
        "purpose": "search", "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16})
    step = next(s for s in r.json()["steps"] if s["job"] == "find-lines")
    assert step["card"]["id"].startswith("kraken:") and step["uses_cloud"] is False
