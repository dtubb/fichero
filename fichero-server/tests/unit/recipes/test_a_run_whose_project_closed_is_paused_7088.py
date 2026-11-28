"""#7088: a recipe run that meets its project's closed connection is paused in the words of that cause, "Paused: the project
closed" (`activity.engine.close-pauses-running-work`), never failed as "The run stopped on an error in Fichero". Through the
real runner and Start route, the steps' workflows stubbed."""
from __future__ import annotations

import duckdb

from tests.unit.recipes.test_recipe_runs_to_spec import (  # noqa: F401, F811  (fixtures)
    RECIPE, _save, _start, _status, _wait, pages, steps,
)


def test_a_run_that_meets_its_closed_project_is_paused_not_failed(client, db, pages, steps, with_material, monkeypatch):  # noqa: F811
    from fichero_server.execution import jobs
    from fichero_server.recipes import runner

    def closed(*args, **kwargs):
        raise duckdb.ConnectionException(f"Connection Error: Connection already closed: the library {db.path} was closed")

    monkeypatch.setattr(runner, "_tree", closed)
    _save(client, RECIPE)
    job_id = _start(client)["started"]["job_id"]
    assert _wait(lambda: jobs.read_job(db, job_id)["state"] in ("paused", "failed", "done", "cancelled")), jobs.read_job(db, job_id)
    row = jobs.read_job(db, job_id)
    assert (row["state"], row["reason"]) == ("paused", jobs.PAUSED_PROJECT_CLOSED), row
    assert "error in Fichero" not in (_status(client, job_id)["reason"] or "")
