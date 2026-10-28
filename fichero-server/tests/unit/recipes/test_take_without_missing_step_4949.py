"""`source.recipe.take-without-missing-step` (#4949, record shape ruled 2026-10-17).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: a shared recipe that names a job this Fichero lacks
(made on a newer one) could not be taken at all. It can be taken without that step: the removal is recorded as an override of
kind `removed-step` ("job not available"), and the step is offered back, never put back by itself, once an update has the job.
"""
from __future__ import annotations

import copy

from fichero_server.recipes import recipe as recipes
from fichero_server.recipes.recipe import (
    check_recipe, offered_back, override_kind, put_back, take_without_missing_steps,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"},
         "runs_on": "this-mac"}
NEWER = {"id": "hologram", "job": "read-a-hologram", "model": {"kraken": "blla", "kraken_version": "bundled"},
         "runs_on": "this-mac"}


def _recipe(*steps, overrides=None) -> dict:
    out = {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}
    if overrides is not None:
        out["overrides"] = overrides
    return out


def test_the_recipe_is_taken_without_the_step_and_the_removal_is_recorded():
    """source.recipe.take-without-missing-step: "can be taken without that step. The removal is recorded"."""
    original = _recipe(LINES, NEWER)
    before = copy.deepcopy(original)

    taken = take_without_missing_steps(original)

    assert original == before, "the recipe as shared is untouched"
    assert [s["id"] for s in taken["steps"]] == ["lines"]
    assert taken["overrides"] == [{"step": "hologram", "kind": "removed-step", "reason": "job not available",
                                   "job": "read-a-hologram", "scope": "project", "folder_id": None,
                                   "step_def": NEWER, "index": 1}]
    assert check_recipe(taken) == []


def test_a_recipe_with_no_missing_step_is_taken_as_it_is():
    recipe = _recipe(LINES)
    assert take_without_missing_steps(recipe) == recipe


def test_a_removed_step_is_offered_back_once_its_job_exists_and_not_before(monkeypatch):
    """source.recipe.take-without-missing-step: "offered back after Fichero is updated"."""
    taken = take_without_missing_steps(_recipe(LINES, NEWER))
    assert offered_back(taken) == []

    real = recipes.get_job
    monkeypatch.setattr(recipes, "get_job", lambda job: object() if job == "read-a-hologram" else real(job))

    assert [o["step"] for o in offered_back(taken)] == ["hologram"]


def test_an_override_with_no_kind_is_a_card_override():
    """source.recipe.take-without-missing-step: "an override that states no `kind` is a `card` override"."""
    assert override_kind({"step": "read", "scope": "project", "card": "kraken:x"}) == "card"
    assert override_kind({"step": "x", "kind": "removed-step"}) == "removed-step"


def test_offering_a_step_back_restores_it_exactly(monkeypatch):
    """source.recipe.take-without-missing-step: the override keeps the step as it was, so putting it back (once its job
    exists) gives the recipe that was shared, in the same place, with the record gone."""
    shared = _recipe(LINES, NEWER, {"id": "after", "job": "find-lines", "model": LINES["model"], "runs_on": "this-mac"})
    taken = take_without_missing_steps(shared)

    real = recipes.get_job
    monkeypatch.setattr(recipes, "get_job", lambda job: object() if job == "read-a-hologram" else real(job))
    restored = put_back(taken, "hologram")

    assert restored["steps"] == shared["steps"] and not restored.get("overrides")
    assert [s["id"] for s in taken["steps"]] == ["lines", "after"], "the recipe it came from is untouched"


def test_a_step_that_read_from_the_removed_one_is_caught_by_the_check_not_left_dangling():
    """source.recipe.take-without-missing-step: a step that needed what only the removed step gave is not left dangling:
    the taken recipe fails the check naming that step, so it is never started half-fed."""
    correct = {"id": "correct", "job": "correct", "model": LINES["model"], "runs_on": "this-mac"}
    taken = take_without_missing_steps(_recipe(LINES, NEWER, correct))

    problems = check_recipe(taken)

    assert problems and any("Review the reading" in p and "no earlier step gives" in p for p in problems), problems
