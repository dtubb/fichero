"""Activity order (`activity.window.history-group` and `activity.window.next-in-run-order`, #5839, #5851; owner 2026-10-19:
"the order is unclear"): a project's live run is at the top, the queues beside it follow, and everything that has ended
(a stopped, interrupted or failed run, batch, recipe run, try or queue row) is folded below as History."""
from __future__ import annotations

import pytest

from fichero_server.api.routes.system.activity import BackgroundJob, order_for_activity


def _job(job_id, task_type, state):
    return BackgroundJob(id=job_id, task_type=task_type, name=job_id, current=0, total=0, percent=0.0, state=state)


def test_each_projects_live_run_is_on_top_and_ended_rows_are_folded_below():
    for project in ("a", "b"):  # two projects: each endpoint answers for its own library
        listed = [_job(f"{project}-old-failed", "workflow", "failed"), _job(f"{project}-queue", "embed", "waiting"),
                  _job(f"{project}-old-stopped", "workflow", "cancelled"), _job(f"{project}-live", "workflow", "running")]
        ordered = order_for_activity(listed)
        assert [j.id for j in ordered] == [f"{project}-live", f"{project}-queue", f"{project}-old-failed",
                                           f"{project}-old-stopped"]
        assert [j.group for j in ordered] == ["live", "live", "earlier", "earlier"]


@pytest.mark.parametrize("task_type", ["run-a-recipe", "try-a-stage", "batch", "embed", "workflow"])
@pytest.mark.parametrize("state", ["failed", "cancelled", "interrupted", "done"])
def test_an_ended_row_of_any_kind_is_history_not_live(task_type, state):
    ordered = order_for_activity([_job("ended", task_type, state), _job("live", "workflow", "running")])
    assert [j.id for j in ordered] == ["live", "ended"] and ordered[1].group == "earlier"


def test_a_paused_run_is_still_live():
    assert order_for_activity([_job("old", "workflow", "failed"), _job("p", "workflow", "paused")])[0].id == "p"
