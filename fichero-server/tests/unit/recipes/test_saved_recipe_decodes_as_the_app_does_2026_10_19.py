"""Set Up > About the Material read "The data couldn't be read because it is missing" (owner, 2026-10-19, build 9add4f3c7):
`source.project.has-settings`. The app decodes the saved recipe as the generated `AssembledRecipe`, whose `problems` and
`gaps` are required; the recipe a project stored came from the rules (`_assemble`) without `problems`, which only the
/assemble route adds. WHY: the project's own recipe must read back in the shape the contract promises."""
from __future__ import annotations

from fichero_server.api.routes.system.recipes import AssembledRecipe

ANSWERS = {"purposes": ["search"], "languages": ["es"], "scripts": ["Latn"], "pages": 10, "mac_memory_gb": 16}


def _read_as_the_app_does(client) -> dict:
    saved = client.get("/api/recipes/project")
    assert saved.status_code == 200, saved.text
    recipe = saved.json()["recipe"]
    AssembledRecipe.model_validate(recipe)  # a required field missing is the app's keyNotFound
    return recipe


def test_answers_saved_alone_read_back_a_whole_recipe(client, with_material):
    assert client.put("/api/recipes/project", json={"answers": ANSWERS}).status_code == 200
    assert isinstance(_read_as_the_app_does(client)["problems"], list)


def test_a_recipe_stored_without_problems_reads_back_whole(client, with_material):
    recipe = client.post("/api/recipes/assemble", json=ANSWERS).json()
    del recipe["problems"]
    assert client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": recipe}).status_code == 200
    assert isinstance(_read_as_the_app_does(client)["problems"], list)


def test_use_this_hands_back_a_recipe_the_app_can_adopt(client, with_material):
    """Use This's reply is adopted by the app as an AssembledRecipe; one it cannot read left the screen unchanged and
    its next save put the stale copy over the choice (owner, 2026-10-19)."""
    assert client.put("/api/recipes/project", json={"answers": ANSWERS}).status_code == 200
    step = _read_as_the_app_does(client)["steps"][0]
    items = client.get("/api/recipes/candidates", params={"job": step["job"], "scripts": "Latn", "languages": "es"}).json()["items"]
    card = next(i for i in items if i.get("pin") and i["id"] != (step.get("card") or {}).get("id"))
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": step["id"], "card": card["id"]})
    assert used.status_code == 200, used.text
    AssembledRecipe.model_validate(used.json()["recipe"])
    assert isinstance(used.json()["recipe"]["problems"], list)
