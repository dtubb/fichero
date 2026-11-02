"""`activity.summary.one-row-per-run-in-list` (#5960): a recipe run that is a live block is not also a `jobs` row; the list's rows are the
queue, the background kinds, up-next and History. The app's window reads the live blocks (`ActivityLiveRunRowsTests.swift`)."""
from __future__ import annotations

import pytest

from fichero_server.api.routes.system.activity import BackgroundJob, is_live_recipe_run


def _job(task_type, state):
    return BackgroundJob(id="x", task_type=task_type, name="n", current=0, total=0, percent=0.0, state=state)


@pytest.mark.parametrize("state", ["running", "waiting", "paused"])
def test_a_working_waiting_or_paused_recipe_run_is_a_live_block_not_a_row(state):
    assert is_live_recipe_run(_job("run-a-recipe", state))


@pytest.mark.parametrize("task_type,state", [("run-a-recipe", "failed"), ("run-a-recipe", "done"), ("workflow", "running"),
                                             ("embed", "waiting")])
def test_an_ended_recipe_run_and_any_other_kind_stay_rows(task_type, state):
    assert not is_live_recipe_run(_job(task_type, state))
