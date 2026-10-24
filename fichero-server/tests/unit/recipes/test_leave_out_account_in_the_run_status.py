"""The run status answers for a run with a Leave Out stage: its account is the stage's own typed field `leave_out`, not
`left_out` (the list of pages a lining or reading stage left out, #5691), which the account dict broke on validation
(release blocker, ## 1134; `designer.clean.leaves-out-non-text`, #6070)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import _finished, _recipe, engine, pages  # noqa: F401  (fixtures)
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, _save
from tests.unit.recipes.test_recipe_execution_to_spec import _start

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
