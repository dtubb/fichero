"""`activity.summary.cost-so-far` (#5960): a live block carries it, from the run's status; pure, so the shapes are written out."""
from __future__ import annotations

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


def test_the_cost_so_far_sums_the_priced_stages_and_is_null_when_unpriced():
    assert live_stages.cost_so_far(_status()) == 0.4
    status = _status()
    status["steps"][1]["timing"] = StepTiming()
    assert live_stages.cost_so_far(status) is None
