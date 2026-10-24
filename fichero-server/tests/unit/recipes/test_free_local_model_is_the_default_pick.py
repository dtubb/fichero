"""`source.find.free-local-model-is-the-default-pick`: a step with no reader chosen yet shows the top-ranked model that runs on this
Mac at no cost as already chosen (Kraken for Find Lines and Find Regions); the recipe's and a person's own choice win.

Tested through `GET /api/recipes/candidates`, the list the finder draws its radio from."""
from __future__ import annotations

from tests.unit.recipes.test_step_choices_on_the_plan import project  # noqa: F401  (fixture)
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

KRAKEN_LINES = "kraken:builtin/blla@bundled"
APPLE_LINES = "apple:vision/find-lines@os"


def _items(client, job, **params):
    r = client.get("/api/recipes/candidates", params={"scripts": "Latn", "languages": "es", "material": "handwriting",
                                                     "mac_memory_gb": 32, "job": job, **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_with_no_project_recipe_the_bundled_kraken_line_finder_is_already_chosen(client, with_material, mac):  # noqa: F811
    chosen = [i["id"] for i in _items(client, "find-lines") if i["chosen"]]
    assert chosen == [KRAKEN_LINES]


def test_the_recipes_own_reader_still_wins(client, project):  # noqa: F811
    items = _items(client, "find-lines", step="find-lines")
    assert [i["id"] for i in items if i["chosen"]] == [KRAKEN_LINES]  # the recipe's step card, not a second pick
    client.post("/api/recipes/project/steps/use-candidate", json={"step": "find-lines", "card": APPLE_LINES})
    after = _items(client, "find-lines", step="find-lines")
    assert [i["id"] for i in after if i["chosen"]] == [APPLE_LINES], "a person's choice is the one marked, never also the default"


def test_exactly_one_is_ever_marked(client, with_material, mac):  # noqa: F811
    for job in ("find-lines", "find-regions", "read-a-line"):
        assert sum(i["chosen"] for i in _items(client, job)) <= 1


def test_the_default_is_flagged_so_it_can_still_be_saved(client, with_material, mac):  # noqa: F811
    default = [i for i in _items(client, "find-lines") if i["chosen"]]
    assert [i["default_pick"] for i in default] == [True], "no step reader saved: the marked one is a default"


def test_a_real_choice_is_not_flagged_as_a_default(client, project):  # noqa: F811
    real = _items(client, "find-lines", step="find-lines")
    assert [(i["id"], i["default_pick"]) for i in real if i["chosen"]] == [(KRAKEN_LINES, False)]


def test_the_default_is_the_pick_assemble_makes(client, with_material, mac):  # noqa: F811
    """One answer to "which model does this step use": the finder's default and the assembled recipe's step card agree, for
    every step the recipe has."""
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "mac_memory_gb": 32, "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    for step in recipe["steps"]:
        card = (step.get("card") or {}).get("id")
        if not card or step["job"] not in ("find-lines", "read-a-line"):
            continue
        marked = [i["id"] for i in _items(client, step["job"]) if i["chosen"]]
        assert marked == [card], f"{step['job']}: the finder defaults to {marked}, assemble picks {card}"
