"""#5747 (`source.project.setup-saves-what-is-sent`, `source.onboard.deterministic-recipe`): saving answers alone to a
project that has no recipe yet assembles and stores the recipe, so Start has one to run. A recipe already stored is
kept (the person's own choices of model stay); a recipe sent explicitly is what is stored."""
from __future__ import annotations

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "material": "print"}


def test_answers_alone_to_a_project_with_no_recipe_store_the_assembled_one(client, db):
    assert client.get("/api/recipes/project").json()["recipe"] is None
    r = client.put("/api/recipes/project", json={"answers": ANSWERS})
    assert r.status_code == 200, r.text
    saved = client.get("/api/recipes/project").json()
    assert saved["recipe"] is not None, "Start would have nothing to run"
    assert "read-a-line" in [s["job"] for s in saved["recipe"]["steps"]]


def test_a_recipe_already_stored_is_kept_when_only_the_answers_are_saved(client, with_material, db):
    recipe = client.post("/api/recipes/assemble", json=ANSWERS).json()
    recipe["title"] = "the person's own"
    client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": recipe})
    client.put("/api/recipes/project", json={"answers": {**ANSWERS, "cloud_allowed": True}})
    assert client.get("/api/recipes/project").json()["recipe"]["title"] == "the person's own"


def test_a_recipe_sent_as_null_is_removed_and_stays_removed(client, db):
    client.put("/api/recipes/project", json={"answers": ANSWERS})
    client.put("/api/recipes/project", json={"recipe": None})
    assert client.get("/api/recipes/project").json()["recipe"] is None
