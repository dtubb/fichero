"""A person's choice of reader replaces the step's whole reader set (#6121): the readers the rules added by kind of material
(Apple Vision, a local OCR model) are not run beside the model the person chose. Owner, Test 17: Gemini chosen, Apple Vision read."""
from __future__ import annotations

from fichero_server.recipes.bakeoff import apply_project_overrides

CHOSEN = {"hf": "google/gemini-3.1-flash-lite"}


def _recipe(job, *, scope="project"):
    step = {"id": job, "job": job, "model": {"hf": "org/auto"}, "runs_on": "this-mac",
            "readers": [{"material": "print", "model": {"builtin": "apple-vision"}},
                        {"material": "handwriting", "model": {"hf": "org/glm-ocr"}}]}
    return {"steps": [step], "overrides": [{"scope": scope, "step": job, "card": "chosen", "model": CHOSEN,
                                            "runs_on": "cloud:openrouter"}]}


def test_the_chosen_reader_leaves_no_auto_readers_on_a_page_reading_step():
    recipe = apply_project_overrides(_recipe("read-a-page"), [])
    (step,) = recipe["steps"]
    assert step["model"] == CHOSEN and not step.get("readers")


def test_the_same_for_a_line_reading_step():
    (step,) = apply_project_overrides(_recipe("read-a-line"), [])["steps"]
    assert not step.get("readers")


def test_a_folder_override_changes_neither_the_model_nor_the_readers():
    (step,) = apply_project_overrides(_recipe("read-a-page", scope="folder"), [])["steps"]
    assert step["model"] == {"hf": "org/auto"} and len(step["readers"]) == 2
