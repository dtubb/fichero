"""While a recipe step runs, the recipe run's status points at that step's job, with its account (#5654 item 7,
`activity.run.account`).

WHY: on the demo (2026-10-10) the recipe's run status said child_id null and account null while its review step
ran: the step learns its run's id only when the run returns, so for the whole step the status had nothing to
point at, and nothing to count pages from.

Through the public surface with the real lanes: a real `run-a-recipe` job whose step is a real workflow run, held
mid-step by the network lane (its pages wait for it); read through `GET /api/recipes/project/runs/{id}`.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from fichero_server.db.manager import db_manager
from tests.unit.jobs.test_closed_mid_run_5608 import (  # noqa: F401
    _first_child,
    _recipe,
    _waiting_pages,
    lane_held,
)
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)


def _run_status(client, job_id):
    r = client.get(f"/api/recipes/project/runs/{job_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_running_step_names_its_run_and_carries_its_account(client, test_package, workflow, pages, cloud,
                                                              lane_held):
    db = db_manager.get_database(test_package)
    recipe = _recipe(db, workflow, pages, steps=("read", "names"))
    assert _wait_for(lambda: _first_child(db, recipe) is not None, 60)
    child = _first_child(db, recipe)
    assert _wait_for(lambda: _waiting_pages(db, child) == 3, 60)

    read, names = _run_status(client, recipe)["steps"]

    assert read["state"] == "running"
    assert read["child_id"] == child
    assert read["account"] is not None and read["account"]["pages_total"] == 3
    assert names["child_id"] is None and names["account"] is None  # not started: no job yet

    lane_held.set()
    assert _wait_for(lambda: _run_status(client, recipe)["state"] in ("done", "failed"), 120)
