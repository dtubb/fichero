"""A project keeps its setup answers and its recipe (`source.project.has-settings`, #4951).

Why it matters: without this, setup's answers vanish when the window closes and Start has nothing
to start; the Inspector cannot show or edit a project's recipe. They are files in the project folder
(`recipe/recipe.yaml`, `recipe/setup.yaml`) so they travel with the project and can be shared. Saving
is audited and undoable like every change, and it refuses keys or code: a recipe is data. If the
answers' own `scripts` (writing systems) were refused, no setup could ever be saved.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.models import ActionAudit

ANSWERS = {"purpose": "transcribe", "languages": ["es"], "scripts": ["Latn"], "material": "handwriting",
           "pages": 374, "cloud_allowed": False, "ingest_mode": "link"}


def _recipe(client):
    return client.post("/api/recipes/assemble", json={
        "purpose": "transcribe", "languages": ["es"], "scripts": ["Latn"], "mac_memory_gb": 16}).json()


def test_a_project_never_set_up_has_nothing_saved(client):
    r = client.get("/api/recipes/project")
    assert r.status_code == 200, r.text
    assert r.json() == {"answers": None, "recipe": None}


def test_saved_answers_and_recipe_come_back_and_live_in_the_project_folder(client, test_package):
    recipe = _recipe(client)
    r = client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": recipe})
    assert r.status_code == 200, r.text
    back = client.get("/api/recipes/project").json()
    assert back["answers"] == ANSWERS and back["recipe"]["steps"] == recipe["steps"]
    assert (Path(test_package) / "recipe" / "recipe.yaml").is_file()
    assert (Path(test_package) / "recipe" / "setup.yaml").is_file()


def test_saving_is_undoable(client, db):
    client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": None})
    [audit] = [a for a in db.query(ActionAudit) if a.action_name == "project.save_setup"]
    undone = client.post(f"/api/actions/audit/{audit.id}/undo")
    assert undone.status_code == 200, undone.text
    assert client.get("/api/recipes/project").json() == {"answers": None, "recipe": None}


def test_a_key_in_a_recipe_is_refused_and_nothing_is_written(client, test_package):
    r = client.put("/api/recipes/project",
                   json={"answers": ANSWERS, "recipe": {"steps": [{"job": "correct", "api_key": "sk-x"}]}})
    assert r.status_code == 422
    assert "never code or credentials" in r.text
    assert not (Path(test_package) / "recipe").exists()
