"""#5800 (`source.recipe.done-is-not-redone` sibling, `source.onboard.rerun-rewrites-nothing`): a saved reader pin the
plan cannot run is never quietly kept as the old reader. The plan refuses it in words, naming the pin and the step,
and Start refuses; the recipe stays as saved."""
from __future__ import annotations

from tests.unit.api.test_add_a_layer_later import (  # noqa: F401  (fixtures)
    hold_the_run,
    project,
)

UNKNOWN = {"zenodo": "10.5281/zenodo.99"}


def _swap(client, pin):
    saved = client.get("/api/recipes/project").json()
    for step in saved["recipe"]["steps"]:
        if step["job"] == "read-a-line":
            step["model"] = pin
    r = client.put("/api/recipes/project", json={"answers": saved["answers"], "recipe": saved["recipe"]})
    assert r.status_code == 200, r.text


def test_the_plan_refuses_a_reader_pin_it_cannot_run_in_words(client, project):  # noqa: F811
    _swap(client, UNKNOWN)
    plan = client.get("/api/recipes/project/start").json()
    said = [r for r in plan["refusals"] if "10.5281/zenodo.99" in r]
    assert said and "is not a model Fichero can find here: choose another reader for" in said[0], plan["refusals"]


def test_start_refuses_and_queues_nothing(client, db, project):  # noqa: F811
    _swap(client, UNKNOWN)
    before = client.get("/api/recipes/project/runs").json()["items"]
    r = client.post("/api/recipes/project/start")
    assert r.status_code == 422, r.text
    assert client.get("/api/recipes/project/runs").json()["items"] == before


def test_a_runnable_reader_pin_is_not_refused(client, project):  # noqa: F811
    _swap(client, {"hf": "mlx-community/swapped-vlm-4bit", "revision": "main"})
    assert client.get("/api/recipes/project/start").json()["refusals"] == []
