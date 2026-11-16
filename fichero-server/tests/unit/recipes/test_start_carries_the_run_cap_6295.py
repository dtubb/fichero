"""`designer.budget.run-cap` (#6295): Start carries the run cap from the request to the run's row (`StartRequest.run_cap_usd` through
`project.start` to `runner.enqueue`); none sent, none kept."""
# ruff: noqa: F811 -- fixtures
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.recipes import runner
from tests.unit.recipes.test_bakeoff_readers import folder  # noqa: F401
from tests.unit.recipes.test_recipe_execution_to_spec import engine, pages  # noqa: F401


def test_start_carries_the_run_cap_from_the_request_to_the_runs_row(client, db, folder, pages, engine, monkeypatch):  # noqa: F811
    """The wiring: `StartRequest.run_cap_usd` through `project.start` to `enqueue`, kept on the run's row; none sent, none kept."""
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "pages": 1000, "mac_memory_gb": 32}
    recipe = client.post("/api/recipes/assemble", json=answers)
    assert recipe.status_code == 200, recipe.text
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe.json()}).status_code == 200
    monkeypatch.setattr(runner, "_run", lambda database, job_id: {})  # the run itself is not under test

    def row_after(body):
        before = {r[0] for r in db.execute_fetchall("SELECT id FROM jobs WHERE kind = ?", [runner.KIND])}
        pressed = client.post("/api/recipes/project/start", json=body)
        assert pressed.status_code == 200, pressed.text
        [new] = {r[0] for r in db.execute_fetchall("SELECT id FROM jobs WHERE kind = ?", [runner.KIND])} - before
        return json.loads(jobs.read_job(db, new)["detail"])

    assert row_after({"run_cap_usd": 3.5})["run_cap_usd"] == 3.5
    assert "run_cap_usd" not in row_after({})
