"""A page-read model the person saves replaces the readers the rules added by kind of material (#6269): claude-sonnet-4-6
was saved on read-a-page and the run read the handwriting pages with Apple Vision (`ai.where.no-silent-reader-fallback`)."""
from __future__ import annotations

from fichero_server.recipes.bakeoff import drop_readers_of_changed_models

CHOSEN = {"cloud": "anthropic", "model": "claude-sonnet-4-6"}
READERS = [{"material": "handwriting", "model": {"builtin": "apple-vision"}}]


def _recipe(model, job="read-a-page"):
    return {"steps": [{"id": "read", "job": job, "model": model, "readers": [dict(r) for r in READERS]}]}


def test_a_changed_model_drops_the_steps_readers():
    sent = drop_readers_of_changed_models(_recipe({"hf": "org/auto"}), _recipe(CHOSEN))
    assert not sent["steps"][0].get("readers")


def test_the_same_model_keeps_the_readers():
    sent = drop_readers_of_changed_models(_recipe(CHOSEN), _recipe(CHOSEN))
    assert sent["steps"][0]["readers"] == READERS


def test_a_new_step_keeps_its_readers_and_other_jobs_are_left_alone():
    assert drop_readers_of_changed_models(None, _recipe(CHOSEN))["steps"][0]["readers"] == READERS
    other = drop_readers_of_changed_models(_recipe({"hf": "a"}, "correct"), _recipe(CHOSEN, "correct"))
    assert other["steps"][0]["readers"] == READERS
