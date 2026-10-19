"""`source.onboard.correct-off-unless-a-corrector-is-here` (#5677).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, an end-to-end onboarding):
choosing Read brought a Correct step pinned to Qwen2.5-VL 7B (5.7 GB) though no corrector was on the Mac. Correct is
off unless a corrector is already available (on this Mac, or in a cloud the project allows) or the person asks; when
off, the recipe and the Start plan say so in one line with what turning it on would cost. Through the routes the app
calls; only this Mac's model store (which models are installed) and its memory are stubbed.
"""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "mac_memory_gb": 32, "cloud_allowed": False}


def _assemble(client, **more):
    r = client.post("/api/recipes/assemble", json={**ANSWERS, **more})
    assert r.status_code == 200, r.text
    return r.json()


def _jobs(recipe) -> list[str]:
    return [s["job"] for s in recipe["steps"]]


def test_with_no_corrector_here_correct_is_off_and_says_what_it_would_cost(client, with_material, mac):
    recipe = _assemble(client)
    assert "correct" not in _jobs(recipe), recipe["steps"]
    (off,) = [o for o in recipe["left_off"] if o["job"] == "correct"]
    assert "off" in off["sentence"] and "GB" in off["sentence"], off
    assert "read-a-line" in _jobs(recipe) or "read-a-page" in _jobs(recipe), "reading stays"


def test_with_a_corrector_already_here_correct_is_still_out_until_asked(client, with_material, mac):
    """#5812 (0d2ddeeff) reversed this test's first form: a corrector at hand no longer puts Correct in; the
    answer drives the plan. What it changes is the cost line: nothing to download."""
    mac.installed.update({"Qwen2.5-VL-7B", "Qwen2.5-VL-3B"})
    recipe = _assemble(client)
    assert "correct" not in _jobs(recipe)
    (off,) = [o for o in recipe["left_off"] if o["job"] == "correct"]
    assert "already" in off["sentence"], off


def test_asked_for_it_is_in_even_to_download(client, with_material, mac):
    asked = _assemble(client, job_answers={"correct_with_a_second_model": True})
    assert "correct" in _jobs(asked)
    ticked = _assemble(client, jobs=["correct"])
    assert "correct" in _jobs(ticked)


def test_the_start_plan_says_it_is_off(client, mac, pages):
    recipe = _assemble(client)
    r = client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": recipe})
    assert r.status_code == 200, r.text
    plan = client.get("/api/recipes/project/start").json()
    assert any("Correct" in line and "GB" in line for line in plan["left_off"]), plan["left_off"]
