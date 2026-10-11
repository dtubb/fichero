"""`source.recipe.names-models-and-where`: a YOLO layout model is pinned by its name (`{yolo: <name>}`), the form the
shipped card and Use This write, and the recipe check knows it.

Seen 2026-10-11 on a first-run onboarding: after the YOLO card was chosen for Find regions, Ready said "step 1
(find-regions): the model ['yolo'] is not pinned in a known form (…)", a raw engine sentence about a pin the
engine wrote itself. A pin the check does not know is said in words, never as a Python list of its keys.
"""

from __future__ import annotations

from fichero_server.recipes.recipe import check_recipe


def _recipe(model) -> dict:
    return {"fichero_recipe": 1, "id": "r", "version": "1", "title": "Regions",
            "steps": [{"id": "find-regions", "job": "find-regions", "model": model}]}


def test_a_yolo_pin_passes_the_check():
    problems = check_recipe(_recipe({"yolo": "yolo-doclaynet-11n"}))
    assert not [p for p in problems if "pinned" in p], problems


def test_the_shipped_yolo_card_pin_passes_the_check():
    from fichero_server.recipes.discovery import known_cards

    pins = [c.pin for c in known_cards(include_not_built=True) if "find-regions" in c.jobs and "yolo" in c.pin]
    assert pins, "the shipped YOLO card is in the catalogue"
    for pin in pins:
        assert not [p for p in check_recipe(_recipe(pin)) if "pinned" in p]


def test_an_unknown_pin_is_said_in_words_not_as_a_list_of_keys():
    (problem,) = [p for p in check_recipe(_recipe({"weights": "x.pt"})) if "find-regions" in p]
    assert "[" not in problem and "'" not in problem, problem
    assert problem.startswith("Step 1 (find-regions)") or "step 1 (find-regions)" in problem
