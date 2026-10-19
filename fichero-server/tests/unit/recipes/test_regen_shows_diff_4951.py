"""`source.onboard.regen-shows-diff` (#4951): changing an answer re-assembles the recipe and shows what would change,
step by step, writing nothing; what the person set by hand is kept."""
from __future__ import annotations

from fichero_server.recipes.diff import diff_recipes
from tests.unit.recipes.test_bakeoff_readers import _set_up, folder  # noqa: F401

KRAKEN = {"kraken": "blla"}
READ_A = {"zenodo": "10.5281/zenodo.1"}
READ_B = {"zenodo": "10.5281/zenodo.2"}


def _recipe(*steps):
    return {"steps": list(steps)}


def test_an_added_a_removed_and_a_changed_step_are_each_named():
    saved = _recipe({"id": "lines", "model": KRAKEN}, {"id": "read", "title": "Read", "model": READ_A},
                    {"id": "old", "title": "Old step"})
    fresh = _recipe({"id": "lines", "model": KRAKEN}, {"id": "read", "title": "Read", "model": READ_B},
                    {"id": "dates", "title": "Work out dates"})
    got = {c["step"]: c for c in diff_recipes(saved, fresh)}
    assert set(got) == {"read", "dates", "old"}
    assert got["read"]["kind"] == "changed" and got["read"]["was"] == READ_A and got["read"]["now"] == READ_B
    assert got["dates"]["kind"] == "added" and got["dates"]["words"] == "Work out dates would be added"
    assert got["old"]["kind"] == "removed" and got["old"]["words"] == "Old step would be taken out"


def test_an_unchanged_recipe_has_no_changes_and_no_recipe_is_not_an_error():
    r = _recipe({"id": "lines", "model": KRAKEN})
    assert diff_recipes(r, r) == [] and diff_recipes(None, r)[0]["kind"] == "added" and diff_recipes(r, None)[0]["kind"] == "removed"


def test_assembling_for_a_project_with_a_saved_recipe_says_what_would_change_and_writes_nothing(client, db, folder, with_material):  # noqa: F811
    saved = _set_up(client)
    answers = {"purposes": ["transcribe", "entities"], "languages": ["es"], "scripts": ["Latn"],
               "materials": ["handwriting"], "pages": 1000}
    fresh = client.post("/api/recipes/assemble", json=answers).json()
    assert {c["kind"] for c in fresh["changes"]} == {"added"} and fresh["changes"], "entities adds steps"
    assert client.get("/api/recipes/project").json()["recipe"] == saved, "nothing was written"
    same = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
            "pages": 1000}  # the answers `_set_up` saved
    assert client.post("/api/recipes/assemble", json=same).json()["changes"] == []


def test_a_default_the_engine_added_since_saving_is_not_a_change():
    saved = _recipe({"id": "read", "model": KRAKEN, "settings": {"dpi": 300}})
    fresh = _recipe({"id": "read", "model": KRAKEN, "settings": {"dpi": 300, "new_default": True}})
    assert diff_recipes(saved, fresh) == []
    fresh["steps"][0]["settings"]["dpi"] = 400
    assert [c["step"] for c in diff_recipes(saved, fresh)] == ["read"]
