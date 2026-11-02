"""`activity.summary.stage-counts`, `.eta-basis`, `.cost-so-far` (#5960): a live block carries its stages in Set Up's order, the time left with
its basis, and the cost so far, from the run's status; pure, so the shapes are written out."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity import recipe_block
from fichero_server.recipes import live_stages
from fichero_server.recipes.run_view import StepTiming
from fichero_server.workflows.run_account import RunAccount


def _account(done, total, failed=0, left_s=None, state="running"):
    return RunAccount(state=state, pages_total=total, pages_done=done, pages_failed=failed, pages_left=total - done - failed,
                      estimate_seconds_left=left_s)


def _status():
    return {"state": "running", "reason": None, "steps": [
        {"steps": ["prepare-the-image"], "job": "prepare-the-image", "state": "done", "account": _account(20, 20)},
        {"steps": ["find-lines", "read-a-line"], "job": "read-a-line", "state": "running", "account": _account(7, 20, 1, 130.0),
         "timing": StepTiming(cost_usd=0.4)},
        {"steps": ["find-names-tag-words"], "job": "find-names-tag-words", "state": "waiting", "account": None}],
        "skipped": [{"step": "find-statements", "why": "no model"}]}


def test_stages_come_in_set_ups_order_with_their_pages_and_a_skipped_one_says_skipped():
    rows = live_stages.stage_counts(_status())
    by = {r["stage"]: r for r in rows}
    assert by["prepare-images"] | {"done": 20, "total": 20} == by["prepare-images"] and by["prepare-images"]["state"] == "done"
    assert by["read"]["state"] == "running" and (by["read"]["done"], by["read"]["failed"], by["read"]["total"]) == (7, 1, 20)
    assert by["names"]["state"] == "waiting" and by["names"]["total"] == 0
    assert by["statements"]["state"] == "skipped"
    order = [r["stage"] for r in rows]
    assert order.index("prepare-images") < order.index("read") < order.index("names")


def test_a_failed_stage_outranks_a_running_one():
    status = _status()
    status["steps"].append({"steps": ["read-a-line"], "job": "read-a-line", "state": "failed", "account": _account(0, 20)})
    assert {r["stage"]: r for r in live_stages.stage_counts(status)}["read"]["state"] == "failed"




def test_the_block_carries_all_three():
    class Job:
        id, name, state, reason = "r1", "Run the recipe", "running", None

    block = recipe_block(Job(), _status(), "Read workflow")
    assert block.seconds_left == 130.0 and block.eta_basis == "this run's pace" and block.cost_usd == 0.4
    assert [s.stage for s in block.stages][0] == "prepare-images"
    fields = app.openapi()["components"]["schemas"]["LiveBlock"]["properties"]
    assert {"stages", "seconds_left", "eta_basis", "cost_usd"} <= set(fields)
