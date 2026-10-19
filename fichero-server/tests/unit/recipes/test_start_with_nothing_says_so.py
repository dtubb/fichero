"""`source.project.automatic-after-first-yes`: Start on a project with nothing in it says so in words and runs
nothing.

Seen 2026-10-11 on a first-run onboarding: the folder chosen in Set Up never reached the project, and Start ran the
recipe anyway; the run ended "step … not run on 1 of 0 folders (pages in no folder: …)". A project with no pages
refuses Start, saying there is nothing to run on and how to add material, and no run is queued.
"""

from __future__ import annotations

from fichero_server.api.routes.system.recipes import NO_MATERIAL
from tests.unit.recipes.test_recipe_execution_to_spec import _recipe, _runs, _save, _steps, engine, pages  # noqa: F401 (fixtures)


def test_start_on_an_empty_project_is_refused_in_words(client, db, tmp_path):
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))

    plan = client.get("/api/recipes/project/start").json()
    (empty,) = [r for r in plan["refusals"] if r == NO_MATERIAL]
    assert "add" in empty.lower() and "/api/" not in empty, empty

    r = client.post("/api/recipes/project/start")
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == NO_MATERIAL, r.json()
    assert _runs(client) == [], "a run was queued on a project with nothing in it"


def test_start_with_pages_is_not_refused_for_material(client, db, pages, tmp_path):
    _save(client, _recipe(tmp_path, *_steps(tmp_path)))
    plan = client.get("/api/recipes/project/start").json()
    assert not [r for r in plan["refusals"] if r == NO_MATERIAL], plan["refusals"]
