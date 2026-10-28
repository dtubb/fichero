"""A second Review the reading model (#6257): answering yes to "Add a second model to review in turn?" adds a second
`correct` step, `correct-2`, after the first with its own model; its text goes to the first's corrected reading, so they
review in turn. Whether the second compares instead is the owner's call (spec `source.recipe.second-reviewer`).
Through the assemble route."""
from __future__ import annotations

from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "mac_memory_gb": 32, "cloud_allowed": False}
ASKED = {"correct_with_a_second_model": True}


def _ids(client, **answers):
    r = client.post("/api/recipes/assemble", json={**ANSWERS, **answers})
    assert r.status_code == 200, r.text
    return [(s["id"], s["job"]) for s in r.json()["steps"]], r.json()


def test_yes_adds_a_second_correct_step_after_the_first(client, with_material, mac):  # noqa: F811
    steps, _ = _ids(client, job_answers={**ASKED, "correct_with_another_model": True})
    ids = [i for i, j in steps if j == "correct"]
    assert ids == ["correct", "correct-2"], steps


def test_without_the_answer_or_without_correct_there_is_one_or_none(client, with_material, mac):  # noqa: F811
    steps, _ = _ids(client, job_answers=ASKED)
    assert [i for i, j in steps if j == "correct"] == ["correct"]
    steps, _ = _ids(client, job_answers={"correct_with_another_model": True})
    assert not [i for i, j in steps if j == "correct"], steps
