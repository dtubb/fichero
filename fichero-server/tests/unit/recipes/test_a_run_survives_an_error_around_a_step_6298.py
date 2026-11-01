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


def _stored(db, run_):
    """The steps as the run stored them, before `status` reads them."""
    import json

    from fichero_server.execution import jobs

    return {tuple(s["steps"]): s for s in json.loads(jobs.read_job(db, run_["job_id"])["detail"])["steps"]}


def _plain(run_):
    assert "TypeError" not in (run_["reason"] or "") and BOOM not in (run_["reason"] or ""), run_["reason"]
    assert all("TypeError" not in (s.get("why") or "") for s in run_["steps"])


def test_a_step_whose_pages_cannot_be_worked_out_fails_alone_and_the_run_says_so(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    run_ = _run_with(client, monkeypatch, "_step_pages", only_correct=True)
    stored = _stored(db, run_)[("correct",)]
    assert stored["state"] == "failed" and stored["outright_in_a_row"] == 1 and "was not run" in stored["why"], stored
    failed = _states(run_)[("correct",)]
    assert failed["state"] == "failed" and "was not run" in failed["why"], failed
    assert ["names"] in steps.ran, "a step that does not need Correct still runs"
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "correct" in run_["reason"]
    _plain(run_)


def test_an_error_in_the_recount_still_checks_the_steps_pages_and_the_run_says_so(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    seen: list[str] = []
    from fichero_server.recipes import runner

    real_after = runner._after_the_step
    monkeypatch.setattr(runner, "_after_the_step", lambda *a, **k: (seen.append("after"), real_after(*a, **k))[1])
    run_ = _run_with(client, monkeypatch, "_recount_on_the_folder")
    stored = _stored(db, run_)[("correct",)]
    assert stored["state"] == "partial" and stored["failed_ids"], stored
    assert "after" in seen, "the failure accounting still ran"
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "not counted as done" in run_["reason"] and "correct" in run_["reason"], run_["reason"]
    _plain(run_)


def test_an_error_checking_a_steps_pages_does_not_leave_it_reading_done(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    run_ = _run_with(client, monkeypatch, "_after_the_step")
    stored = _stored(db, run_)[("correct",)]
    assert stored["state"] == "partial" and stored["failed_ids"], stored
    assert run_["state"] == "failed" and run_["reason"].startswith("Done with failures"), run_["reason"]
    assert "not counted as done" in run_["reason"] and "correct" in run_["reason"], run_["reason"]
    assert ["names"] in steps.ran and ["correct"] in steps.ran, "every step still ran"
    _plain(run_)


def test_a_run_that_finished_stays_done_when_only_its_summary_fails(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    run_ = _run_with(client, monkeypatch, "_failures_words")
    assert run_["state"] == "done", (run_["state"], run_["reason"])  # a done run keeps no reason: "failed" would carry the raw words
    _plain(run_)


def test_an_error_in_the_plan_ends_the_run_in_plain_words_with_its_work_kept(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    run_ = _run_with(client, monkeypatch, "_tree")
    assert run_["state"] == "failed"
    assert "stopped on an error in Fichero" in run_["reason"] and "kept" in run_["reason"], run_["reason"]
    _plain(run_)


def test_a_step_that_cannot_choose_its_pages_beside_another_is_not_started_there(db, monkeypatch):  # noqa: F811
    from fichero_server.recipes import runner

    def boom(*a, **k):
        raise TypeError(BOOM)

    monkeypatch.setattr(runner, "_step_pages", boom)
    detail = {"runs": [{"steps": ["a"], "card": "workflow"}, {"steps": ["b"], "card": "workflow"}],
              "steps": [{"state": "waiting"}, {"state": "waiting"}]}
    assert runner._start_beside(db, "job", detail, {"folder": None, "units": []}, {}, "owner", 1) is None


def test_the_step_list_keeps_a_stored_partial_over_its_jobs_done_6319(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    """#6319: `status` copied the step's job state over the stored one, so a step stored `partial` read `done` in the list.
    This is the #6298 could-not-check partial (no failed pages on its account), which a done job does not clear. The Start
    plan offers it again, and the run summary's `not_run` does not list it (it ran)."""
    from fichero_server.execution import jobs
    from fichero_server.recipes import runner

    run_ = _run_with(client, monkeypatch, "_after_the_step")
    correct = _stored(db, run_)[("correct",)]
    assert jobs.read_job(db, correct["child_id"])["state"] == "done"  # its job did finish
    assert _states(run_)[("correct",)]["state"] == "partial", _states(run_)[("correct",)]
    assert runner.unfinished_steps(db)["correct"]["state"] == "partial"  # Start offers it again
    summary = client.get(f"/api/recipes/project/runs/{run_['job_id']}/summary").json()
    assert "correct" not in [s["steps"][0] for s in summary["not_run"]], summary["not_run"]


def _lost_pages_run(client, db, monkeypatch):
    """A run whose `correct` step is stored as a lost-pages partial (one batch, `failed_pages`), its job's account faked
    clean (no failed page; the stubbed workflows cannot re-read a page), as after a Retry or Read Again."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.workflows import run_account

    run_ = _run_with(client, monkeypatch, "_after_the_step")
    detail = json.loads(jobs.read_job(db, run_["job_id"])["detail"])
    step = next(s for s in detail["steps"] if s["steps"] == ["correct"])
    step.update(failed_pages=[{"page": "IMG_1", "reason": "no lines"}], pages_lost=1, why="0 of 1 pages done; 1 failed",
                failed_batches=[{"folder": None, "state": "partial", "child_id": step["child_id"], "why": "x"}])
    jobs.save_detail(db, run_["job_id"], json.dumps(detail))
    real = run_account.run_account

    async def account(db_, thread_id, **k):
        found = await real(db_, thread_id, **k)
        if thread_id != step["child_id"]:
            return found
        found = found or run_account.build_account(status="done", reason=None, state={}, pending_writes=(), started_at=None,
                                                   run_usage=None, live_peaks={}, waiting_reason=None, scope_ids=None)
        return found.model_copy(update={"pages_failed": 0, "failures": []})

    monkeypatch.setattr(run_account, "run_account", account)
    return run_["job_id"]


def test_a_lost_pages_partial_stays_partial_when_its_jobs_account_is_clean_6319(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    """The step list records what the run did, as the run's "Done with failures" words do: a Retry or Read Again inside the run
    does not change it (the next Start does)."""
    job_id = _lost_pages_run(client, db, monkeypatch)
    step = _states(client.get(f"/api/recipes/project/runs/{job_id}").json())[("correct",)]
    assert step["state"] == "partial" and step["failed_pages"], step


def test_the_plan_offers_a_partial_step_in_its_words_beside_a_proposal_6319(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    """The Start plan names the step "partial last time", and a partial joins a Start beside a proposal."""
    from pathlib import Path

    from fichero_server.recipes.project import write_proposed

    _run_with(client, monkeypatch, "_after_the_step")
    write_proposed(Path(db.path).parent, {"layers": ["entities"], "steps": ["names"]})
    runs = {tuple(r["steps"]): r for r in client.get("/api/recipes/project/start").json()["runs"]}
    assert runs[("correct",)]["last_run"] == "partial" and runs[("correct",)]["note"].startswith("partial last time"), runs


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_a_job_that_failed_or_stopped_still_overrides_a_stored_partial_6319(client, db, pages, steps, with_material, monkeypatch, state):  # noqa: F811
    """Only a job that reads `done` leaves the stored partial in place; a failed or cancelled job is what the step reads."""
    run_ = _run_with(client, monkeypatch, "_after_the_step")
    db.execute("UPDATE jobs SET state = ? WHERE id = ?", (state, _stored(db, run_)[("correct",)]["child_id"]))
    assert _states(client.get(f"/api/recipes/project/runs/{run_['job_id']}").json())[("correct",)]["state"] == state
