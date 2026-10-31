"""#6298: the code around a step (which pages it runs on, the recount after it, what it leaves behind) is under the #5684 rule
too: an error there fails that step alone in one plain line, or is noted and the run goes on with its work kept; it never ends
the whole run as `an error in Fichero (TypeError: ...)`. Before a step runs, nothing has been spent, so the step is failed and the
rest go on; after it, the step's end is already saved, so only the bookkeeping is lost and said."""
from __future__ import annotations

import pytest

from tests.unit.recipes.test_recipe_runs_to_spec import (  # noqa: F401, F811  (fixtures)
    RECIPE, _finished, _save, _start, pages, steps,
)

BOOM = "'>' not supported between instances of 'str' and 'int'"


def _run_with(client, monkeypatch, name, only_for_correct):
    from fichero_server.recipes import runner

    real = getattr(runner, name)

    def raising(*args, **kwargs):
        card = next((a for a in args if isinstance(a, dict) and "steps" in a and "card" in a), None)
        if only_for_correct and (card is None or "correct" not in card["steps"]):
            return real(*args, **kwargs)
        raise TypeError(BOOM)

    monkeypatch.setattr(runner, name, raising)
    _save(client, RECIPE)
    return _finished(client, _start(client)["started"]["job_id"])


def _states(run_):
    return {tuple(s["steps"]): s for s in run_["steps"]}


def test_an_error_choosing_a_steps_pages_fails_that_step_alone(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    run_ = _run_with(client, monkeypatch, "_step_pages", True)
    failed = _states(run_)[("correct",)]
    assert failed["state"] == "failed" and "TypeError" not in failed["why"] and "was not run" in failed["why"], failed
    assert ["names"] in steps.ran, "a step that does not need Correct still runs"
    assert "TypeError" not in (run_["reason"] or "")


@pytest.mark.parametrize("name", ["_recount_on_the_folder", "_after_the_step"])
def test_an_error_in_the_bookkeeping_after_a_step_keeps_its_work(client, db, pages, steps, with_material, monkeypatch, name):  # noqa: F811
    run_ = _run_with(client, monkeypatch, name, False)
    assert ["correct"] in steps.ran and ["names"] in steps.ran, "every step still runs"
    assert _states(run_)[("correct",)]["state"] == "done", "the step's own end stands"
    assert "TypeError" not in (run_["reason"] or "")
    assert all("TypeError" not in (s.get("why") or "") for s in run_["steps"])
