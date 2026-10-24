"""The run status answers for a run with a Leave Out stage: its account is the stage's own typed field `leave_out`, not
`left_out` (the list of pages a lining or reading stage left out, #5691), which the account dict broke on validation
(release blocker, ## 1134; `designer.clean.leaves-out-non-text`, #6070)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import _finished, _recipe, engine, pages  # noqa: F401  (fixtures)
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, _save
from tests.unit.recipes.test_recipe_execution_to_spec import _start

import pytest


@pytest.fixture(autouse=True)
def _memory_is_not_the_question(monkeypatch):
    """The stub reader loads nothing: the memory guard (`throttle.memory_short`) must not hold it on a busy test Mac."""
    monkeypatch.setattr("fichero_server.execution.throttle.memory_short", lambda **kw: None)


LEAVE = {"id": "leave", "job": "leave-out", "model": {"builtin": "leave-out-rules"}}


def test_the_run_status_is_200_with_the_leave_out_account_after_a_run(client, db, pages, tmp_path, engine, monkeypatch,
                                                                       with_material):
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, **kw: engine.recognize(image_path, None))
    _save(client, _recipe(tmp_path, LINES, LEAVE))
    job_id = _start(client)
    _finished(client, job_id)

    r = client.get(f"/api/recipes/project/runs/{job_id}")

    assert r.status_code == 200, r.text
    (stage,) = [s for s in r.json()["steps"] if s["job"] == "leave-out"]
    assert stage["state"] == "done", stage
    assert {"pages", "left_out", "why", "refused"} <= set(stage["leave_out"]), stage  # the stub pages have no lines to judge
    assert not stage.get("left_out"), "the blank-pages list is not the Leave Out account"
    assert client.get(f"/api/recipes/project/runs/{job_id}/summary").status_code == 200


def test_a_run_saved_with_the_account_under_left_out_still_answers(client, db, pages, tmp_path, engine, monkeypatch, with_material):
    """A run saved before the fix holds the Leave Out account at the stage's `left_out`: it is read as `leave_out`, status and
    summary answer 200, and the stored row is left as it was."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, **kw: engine.recognize(image_path, None))
    _save(client, _recipe(tmp_path, LINES, LEAVE))
    job_id = _start(client)
    _finished(client, job_id)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"])
    today = {"pages": 2, "left_out": 1, "why": {"off the page": 1}, "refused": 0}
    for step in detail["steps"]:
        if step["card"] == "leave-out":  # today's stored shape: the account at `left_out`
            step.pop("leave_out", None)
            step["left_out"] = today
    jobs.save_detail(db, job_id, json.dumps(detail))
    stored = jobs.read_job(db, job_id)["detail"]

    r = client.get(f"/api/recipes/project/runs/{job_id}")
    assert r.status_code == 200, r.text
    (stage,) = [s for s in r.json()["steps"] if s["job"] == "leave-out"]
    assert stage["leave_out"] == today and not stage.get("left_out"), stage
    assert client.get(f"/api/recipes/project/runs/{job_id}/summary").status_code == 200
    assert jobs.read_job(db, job_id)["detail"] == stored, "the stored row is never rewritten"


class _EngineDied(BaseException):
    """The worker ends as the engine's death ends it: nothing in the run gets to write its row."""


def test_a_run_in_the_old_shape_is_resumed_after_a_quit_and_finishes(client, db, pages, tmp_path, engine, monkeypatch,
                                                                     with_material):
    """Today's runs hold the Leave Out account at `left_out`. One lost with the engine and carried on (resume, then Retry) takes the
    new shape before the runner adds to it, finishes, and its status answers 200."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.llm import kraken_runtime
    from fichero_server.recipes import leave_out
    from tests.unit.recipes.test_recipe_execution_to_spec import _wait

    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, **kw: engine.recognize(image_path, None))
    real, calls = leave_out.leave_out_pages, []

    def dies_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise _EngineDied()
        return real(*args, **kwargs)

    monkeypatch.setattr(leave_out, "leave_out_pages", dies_once)
    _save(client, _recipe(tmp_path, LINES, LEAVE))
    job_id = _start(client)
    assert _wait(lambda: len(calls) >= 1)
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    today = {"pages": 1, "left_out": 0, "why": {}, "refused": 0}
    for step in detail["steps"]:
        if step["card"] == "leave-out":
            step["left_out"] = today  # the shape saved before the fix
    jobs.save_detail(db, job_id, json.dumps(detail))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state IN ('running', 'failed')", [job_id])
    jobs.resume(db)
    r = client.post(f"/api/activity/jobs/{job_id}/retry")
    assert r.status_code in (200, 409), r.text
    run = _finished(client, job_id)

    assert run["state"] == "done", run
    r = client.get(f"/api/recipes/project/runs/{job_id}")
    assert r.status_code == 200, r.text
    (stage,) = [s for s in r.json()["steps"] if s["job"] == "leave-out"]
    assert stage["state"] == "done" and "pages" in stage["leave_out"] and not stage.get("left_out"), stage
