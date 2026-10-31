"""#6298: the code around a step (which pages it runs on, the recount after it, what it leaves behind, the run's own plan and
end-of-run words) is under the #5684 rule too. An error there never ends the run as `an error in Fichero (TypeError: ...)`, and
never reads as success: a step that could not be run, or whose pages could not be checked afterwards, makes the run end
"Done with failures" in plain words; a run that finished stays finished when only its summary fails. Through the real runner
and Start route, the steps' workflows stubbed."""
from __future__ import annotations

import pytest

from tests.unit.recipes.test_recipe_runs_to_spec import (  # noqa: F401, F811  (fixtures)
    RECIPE, _finished, _save, _start, pages, steps,
)

BOOM = "'>' not supported between instances of 'str' and 'int'"


def _run_with(client, monkeypatch, name, *, only_correct=False, calls=None):
    from fichero_server.recipes import runner

    real = getattr(runner, name)

    def raising(*args, **kwargs):
        if calls is not None:
            calls.append(name)
        card = next((a for a in args if isinstance(a, dict) and "steps" in a and "card" in a), None)
        if only_correct and (card is None or "correct" not in card["steps"]):
            return real(*args, **kwargs)
        raise TypeError(BOOM)

    monkeypatch.setattr(runner, name, raising)
    _save(client, RECIPE)
    return _finished(client, _start(client)["started"]["job_id"])


def _states(run_):
    return {tuple(s["steps"]): s for s in run_["steps"]}


def _plain(run_):
    assert "TypeError" not in (run_["reason"] or "") and BOOM not in (run_["reason"] or ""), run_["reason"]
    assert all("TypeError" not in (s.get("why") or "") for s in run_["steps"])


def test_a_step_whose_pages_cannot_be_worked_out_fails_alone_and_the_run_says_so(client, db, pages, steps, with_material, monkeypatch):
    run_ = _run_with(client, monkeypatch, "_step_pages", only_correct=True)
    failed = _states(run_)[("correct",)]
    assert failed["state"] == "failed" and "was not run" in failed["why"], failed
    assert ["names"] in steps.ran, "a step that does not need Correct still runs"
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "correct" in run_["reason"]
    _plain(run_)


def test_an_error_in_the_recount_still_checks_the_steps_pages_and_the_run_says_so(client, db, pages, steps, with_material, monkeypatch):
    seen: list[str] = []
    from fichero_server.recipes import runner

    real_after = runner._after_the_step
    monkeypatch.setattr(runner, "_after_the_step", lambda *a, **k: (seen.append("after"), real_after(*a, **k))[1])
    run_ = _run_with(client, monkeypatch, "_recount_on_the_folder")
    assert "after" in seen, "the failure accounting still ran"
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "not counted as done" in run_["reason"] and "correct" in run_["reason"], run_["reason"]
    _plain(run_)


def test_an_error_checking_a_steps_pages_does_not_leave_it_reading_done(client, db, pages, steps, with_material, monkeypatch):
    run_ = _run_with(client, monkeypatch, "_after_the_step")
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "not counted as done" in run_["reason"] and "correct" in run_["reason"], run_["reason"]
    assert ["names"] in steps.ran and ["correct"] in steps.ran, "every step still ran"
    _plain(run_)
