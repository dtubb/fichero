"""`activity.summary.eta-basis` (#5960): a live block carries it, from the run's status; pure, so the shapes are written out."""
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


def test_the_time_left_is_the_runs_own_pace_and_says_so_until_a_page_is_done_then_nothing():
    assert live_stages.eta(_status()) == (130.0, "this run's pace")
    status = _status()
    status["steps"][1]["account"] = _account(0, 20)
    assert live_stages.eta(status) == (None, None)
