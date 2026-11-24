"""`recipes-run.timing.plan-says-time-from-measured-pages` (#6810): Start's plan names the time each local step will take on these
pages from this Mac's finished pages of that step's model, with its basis; a step with no finished page says unknown, never 0."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from fichero_server.execution import jobs

from tests.unit.recipes.test_a_page_reader_adds_the_page_step_6259 import LINES_ONLY
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture)


def _plan(client, db):
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.recipes.project import write_project_setup

    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"]}
    write_project_setup(routes._library(db), answers, copy.deepcopy(LINES_ONLY))
    plan = client.get("/api/recipes/project/start")
    assert plan.status_code == 200, plan.text
    return plan.json()


def _finished(db, model, seconds):
    jobs._ensure(db)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    for i, took in enumerate(seconds):  # a job row names a local model with its runtime, the plan without it
        db.execute("INSERT INTO jobs (id, kind, subject, model, state, created_at, started_at, finished_at) "
                   "VALUES (?, 'read-a-line', ?, ?, 'done', ?, ?, ?)",
                   [f"t{i}", f"p{i}", f"kraken:{model}", t0, t0, t0 + timedelta(seconds=took)])


def test_a_local_step_says_its_time_from_this_macs_finished_pages_of_its_model(client, db, mac, pages):
    model = _plan(client, db)["runs"][0]["model_override"]
    _finished(db, model, [20, 25, 400])
    [run] = _plan(client, db)["estimate"]["runs"]
    assert (run["pages"], run["seconds"], run["seconds_basis"]) == (2, 50.0, "measured"), run
    assert "25" in run["seconds_words"] and "3 finished pages" in run["seconds_words"], run["seconds_words"]


def test_a_step_with_no_finished_page_says_unknown_never_zero(client, db, mac, pages):
    [run] = _plan(client, db)["estimate"]["runs"]
    assert (run["seconds"], run["seconds_basis"]) == (None, "unknown"), run
