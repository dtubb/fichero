"""A choice kept for a step the person has since un-ticked goes with the step (owner 2026-10-24).

WHY: Ready said "override 3: names step 'translate-transliterate-normalise', which this recipe does not have" and Start
could not run: the choice for Translate outlived the un-ticked stage, and the recipe check refused the whole plan.
"""

from fichero_server.api.routes.system import recipes as routes


def _answers():
    return {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
            "mac_memory_gb": 16}


def test_a_choice_for_a_step_no_longer_in_the_recipe_is_dropped(with_material):
    plain = routes._assemble(_answers())
    step = plain["steps"][0]["id"]
    gone = {"step": "translate-transliterate-normalise", "scope": "project", "card": "x", "kind": "card"}
    here = {"step": step, "scope": "project", "card": "x", "kind": "card"}
    recipe = routes._assemble(_answers(), overrides=[gone, here])
    steps = [o.get("step") for o in recipe.get("overrides") or []]
    assert "translate-transliterate-normalise" not in steps
    assert step in steps


def test_a_removed_step_record_is_kept(with_material):
    removed = {"step": "translate-transliterate-normalise", "scope": "project", "kind": "removed-step"}
    recipe = routes._assemble(_answers(), overrides=[removed])
    assert removed in (recipe.get("overrides") or [])
