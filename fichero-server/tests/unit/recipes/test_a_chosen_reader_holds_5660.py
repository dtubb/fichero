"""A reader a person chose for a step holds, everywhere, however often Set Up is read again (#5660 item 8).

WHY: the maintainer chose another reader in Set Up, went back and forth, and CATMuS was back: the choice felt like
a suggestion the defaults overrode. Through the routes Set Up calls, in the order it calls them (assemble the
recipe from the answers, save it, choose a reader for the step, then read the setup, assemble again, read the
Start plan and the finder, several times), the chosen reader stays the step's reader, the Start plan reads with
it, and the finder marks it as the step's choice. Also when the answers change so that the finder no longer
lists the chosen reader for them: a choice is the person's, not the rules' to take back.
"""

from __future__ import annotations

import json

from fichero_server.recipes.cards import kraken_reader_for

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "cloud_allowed": False}


def _assemble_and_save(client, answers):
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    saved = client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe.json()})
    assert saved.status_code == 200, saved.text
    return saved.json()["recipe"]


def _reader(recipe):
    return next(s for s in recipe["steps"] if s["job"] == "read-a-line")


def _card(step):
    return (step.get("card") or {}).get("id")


def _candidates(client, step=None, languages="es"):
    params = {"job": "read-a-line", "scripts": "Latn", "languages": languages, "material": "handwriting"}
    if step:
        params["step"] = step
    r = client.get("/api/recipes/candidates", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_a_chosen_reader_holds_through_every_read_of_set_up(client, db, pages, mac):
    recipe = _assemble_and_save(client, ANSWERS)
    step = _reader(recipe)
    default = _card(step)
    other = next(c for c in _candidates(client) if c["rule_rank"] and c["id"] != default
                 and c["id"].startswith("kraken:"))  # another Kraken reader: the run reads with it by name

    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": step["id"], "card": other["id"]})
    assert used.status_code == 200, used.text

    for _lap in range(3):
        assert _reader(client.get("/api/recipes/project").json()["recipe"])["model"] == other["pin"]
        again = _assemble_and_save(client, ANSWERS)  # Set Up proposes the recipe again and saves it
        assert _reader(again)["model"] == other["pin"] and _card(_reader(again)) == other["id"]
        plan = client.get("/api/recipes/project/start").json()
        [run] = [r for r in plan["runs"] if "read-a-line" in r["steps"]]
        assert run["model_override"] == kraken_reader_for(other["pin"])  # the Start plan reads with it
        listed = _candidates(client, step=step["id"])
        assert [c["id"] for c in listed if c["chosen"]] == [other["id"]]
        assert listed[0]["id"] == other["id"]  # the step's choice first in the finder


def test_a_choice_holds_when_the_answers_change(client, db, pages, mac):
    """The finder lists a Hugging Face reader only for the languages it was found for; when the answers change, the
    rules no longer see it. The step still reads with the reader the person chose, saying so, rather than falling
    back to the default (the hole that brought CATMuS back)."""
    from fichero_server.recipes import discovery

    found = discovery._hf_card({"modelId": "someone/trocr-castellano-htr-mlx", "pipeline_tag": "image-to-text",
                                "library_name": "mlx", "tags": ["mlx", "es", "htr", "license:mit"]},
                               "an OCR model (image-to-text)", "an MLX build", frozenset({"es"}))
    discovery.keep_hub([found], frozenset({"es"}))
    recipe = _assemble_and_save(client, ANSWERS)
    step = _reader(recipe)
    chosen = next(c for c in _candidates(client) if c["id"] == found.id)
    used = client.post("/api/recipes/project/steps/use-candidate", json={"step": step["id"], "card": chosen["id"]})
    assert used.status_code == 200, used.text

    for languages in (["es", "la"], ["la"], ["es"]):
        changed = _assemble_and_save(client, {**ANSWERS, "languages": languages})
        assert _reader(changed)["model"] == chosen["pin"], languages
        assert "chosen by you" in json.dumps(_reader(changed)).lower()


def test_the_default_reader_follows_the_material_not_one_list(client, db, pages, mac):
    """The rules rank by fit (`source.recipe.script-reader-first`): the script, then the material the card states,
    then a published CER. A Spanish hand and an English typescript get different readers; a language is a hard
    constraint where a card lists its languages (the shipped Latin-script readers state 'any')."""
    hand = _reader(client.post("/api/recipes/assemble", json=ANSWERS).json())
    typed = _reader(client.post("/api/recipes/assemble", json={**ANSWERS, "languages": ["en"],
                                                                "materials": ["typescript"]}).json())
    assert hand["model"] == {"zenodo": "10.5281/zenodo.21788410"}  # PP-OCRv6: states handwriting and a CER
    assert typed["model"] == {"zenodo": "10.5281/zenodo.13788177"}  # McCATMuS: the one that states typescript
