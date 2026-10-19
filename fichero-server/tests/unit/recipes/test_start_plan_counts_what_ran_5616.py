"""Start's done counts match what ran, and a failed step says how it ended (#5616), tested to the spec
(`source.recipe.done-is-not-redone`, `source.recipe.run-status-is-activity`).

WHY: the MCP review of 2026-10-08 read "Paleographer Review already done on 184 of 203 pages" while both Review
runs in Activity had done 0 pages: with no `model_override` the done check counted a reviewed transcription by ANY
model, from runs outside the recipe. And `last_run`/`last_why` were null on every step though the last run had
failed. Through the done check and `GET /api/recipes/project/start`.
"""
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.models import Artifact, Workflow
from fichero_server.recipes import done, runner
from tests.unit.recipes.test_ended_run_reads_ended_5615 import (  # noqa: F401  (fixtures)
    _interrupted_run,
    _set_up,
    engine,
    pages,
)

REVIEWED = done.REVIEWED


def _review(db, page, *, model, workflow_id):
    db.save(Artifact(document_id=page.id, artifact_type=REVIEWED, content="reviewed", model=model,
                     workflow_id=workflow_id))


def test_a_review_counts_only_when_the_step_made_it(db, pages):
    """A step on its workflow's default (no override) counts only its own workflow's reviews; a step with a model
    counts only that model's."""
    mine = Workflow(name="Paleographer Review", model="")
    other = Workflow(name="Some other review", model="")
    db.save(mine)
    db.save(other)
    first, second = pages
    _review(db, first, model="gpt-4o", workflow_id=other.id)  # a review from a run outside the recipe
    card = {"job": "correct", "workflow_id": mine.id, "model_override": None}
    assert done.is_done(db, card, first.id) is False
    _review(db, second, model="qwen-vl", workflow_id=mine.id)
    assert done.is_done(db, card, second.id) is True
    assert done.is_done(db, {**card, "model_override": "gpt-4o"}, first.id) is True
    assert done.is_done(db, {**card, "model_override": "gpt-4o"}, second.id) is False


def test_the_effective_model_is_the_override_else_the_workflows(db):
    named = Workflow(name="Named model", model="qwen-vl-max")
    db.save(named)
    assert done.effective_model(db, {"model_override": "gpt-4o", "workflow_id": named.id}) == "gpt-4o"
    assert done.effective_model(db, {"model_override": None, "workflow_id": named.id}) == "qwen-vl-max"
    assert done.effective_model(db, {"model_override": None, "workflow_id": None}) is None


def test_a_step_the_last_run_left_unfinished_says_how_it_ended(client, db, pages, with_material):
    """`last_run`/`last_why` on each step the failed run did not finish, as the plan offers it again."""
    from pathlib import Path

    from fichero_server.recipes.project import write_start

    _set_up(client)
    job_id = _interrupted_run(db)
    write_start(Path(db.path).parent, {"started_at": "2026-10-08T09:40:00+00:00", "job_id": job_id, "workflows": [],
                                       "pages": 2})  # Start pressed
    jobs.resume(db)  # the engine starts again: the run is set aside, its steps read ended
    assert jobs.read_job(db, job_id)["state"] == "failed"
    statuses = {s["steps"][0]: s for s in runner.status(db, job_id)["steps"]}
    assert statuses["correct"]["state"] == "not run"

    plan = client.get("/api/recipes/project/start").json()
    by_step = {sid: r for r in plan["runs"] for sid in r["steps"]}
    for sid in ("correct", "names"):
        assert by_step[sid]["last_run"] == "not run", (sid, by_step[sid])
        assert by_step[sid]["last_why"] and "Stopped 3 times" in by_step[sid]["last_why"]
        assert by_step[sid]["note"].startswith("not run last time")
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    assert detail["title"] == "Transcribe + names" and detail["pages"] == 2
