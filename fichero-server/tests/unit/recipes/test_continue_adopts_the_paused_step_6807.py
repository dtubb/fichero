"""#6807 `recipes-run.restart.continue-adopts-the-paused-step`: after a quit the launch alert lists a recipe run once, and
Continue on it resumes its step's paused run from the checkpoint and the recipe waits on that run (it does not start the
step again). Driven through the alert's own routes; only the resume of the workflow run is recorded."""
from __future__ import annotations

import asyncio
import json

import pytest

from fichero_server.execution import jobs, runner as engine
from fichero_server.recipes import runner
from fichero_server.workflows.activity import get_activity_tracker


@pytest.fixture
def quit_recipe(db, monkeypatch):
    runner.register_job_kinds()
    jobs.set_paused(True)  # the lane starts nothing: the rows below are what the open left
    detail = {"runs": [{"card": "workflow", "job": "find-lines", "steps": ["Find lines"]}],
              "steps": [{"steps": ["Find lines"], "card": "workflow", "state": "running", "child_id": None}]}
    recipe = jobs.enqueue(db, runner.KIND, "recipe:6807", detail=json.dumps(detail))
    step = jobs.enqueue(db, "workflow", "thread-6807")
    jobs.set_parent(db, step, recipe)
    db.execute("UPDATE jobs SET state = 'running' WHERE id IN (?, ?)", [recipe, step])
    store = get_activity_tracker(str(db.path)).store
    asyncio.run(store.save_workflow_run(thread_id=step, workflow_id="w", workflow_name="Find lines", python_code="",
                                        execution_log="", status="paused"))
    asyncio.run(store.update_workflow_run(step, error=engine.QUIT_PAUSED_ERROR))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.resume(db)  # the open: what was running is held with the quit's reason
    resumed: list[str] = []
    monkeypatch.setattr(runner, "_resume_step_run", lambda database, thread, recipe=None: resumed.append(thread))

    async def fake_resume(thread_id, request=None, db=None):
        resumed.append(thread_id)

    monkeypatch.setattr("fichero_server.api.routes.workflow_execution.core.resume_workflow", fake_resume)
    yield db, recipe, step, resumed
    jobs.set_paused(False)


def test_the_alert_lists_the_recipe_once_and_continue_resumes_its_step_run_once_and_the_recipe_adopts_it(client, quit_recipe):
    db, recipe, step, resumed = quit_recipe
    listed = client.get("/api/activity/stopped-at-quit").json()
    assert [i["id"] for i in listed["items"]] == [recipe], "the step's run is part of the recipe, not a second row"

    answer = client.post("/api/activity/stopped-at-quit/continue", json={"all": True}).json()

    assert answer["continued_ids"] == [recipe]
    assert resumed == [step], "the paused step run is resumed once, from its checkpoint"
    row = jobs.read_job(db, recipe)
    assert json.loads(row["detail"])["awaiting"]["child"] == step, "the recipe waits on that run instead of starting the step again"
    assert row["state"] == "waiting"


def test_the_opens_recovery_queues_no_embed_or_names_draft_for_a_page_an_unfinished_run_does_once_at_its_end(db, monkeypatch):
    """The alert listed 3 embeds beside the recipe: the open re-queued the pages' import-time embed though the recipe's Search does it."""
    from fichero_server.importers import derivatives
    from fichero_server.importers.derivatives import EMBED_KIND, NLP_KIND, THUMBNAIL_KIND
    from fichero_server.models import DocType, Document, FileType, Status

    docs = [Document(name=f"p{i}.jpg", doc_type=DocType.file, file_type=FileType.image, status=Status.pending,
                     page_content="text") for i in range(3)]
    for d in docs:
        db.save(d)
    cards = [{"card": "workflow", "job": "read-a-line"}, {"card": "workflow", "job": "find-names-tag-words"},
             {"card": "embed", "job": "make-a-vector"}]
    for ids in ([d.id for d in docs[:2]], None):  # the run's pages named, then a run over every page
        db.execute("DELETE FROM jobs")
        jobs._ensure(db)
        run_id = jobs._insert(db, runner.KIND, "held-run", None, "import")
        db.execute("UPDATE jobs SET state = 'paused', detail = ? WHERE id = ?", [json.dumps({"runs": cards, "documents": ids}), run_id])
        monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: True)
        derivatives.queue_derivatives(docs, library_path=str(db.path), db=db, arrived=False)

        def count(kind):
            return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [kind])[0]

        assert count(THUMBNAIL_KIND) == 3
        assert (count(EMBED_KIND), count(NLP_KIND)) == ((1, 1) if ids else (0, 0)), "only the run's own pages are left to it"


def test_a_recipe_run_the_quit_stopped_names_its_paused_step_run_and_says_the_step_is_paused(quit_recipe, client):
    """`recipes-run.restart.run-row-counts-pages-after-restart`: the stopped run's step list read `running` with no run behind it
    (so the row counted "0 of 0"); the step is tied to the run the quit paused and says paused, in the status and in Activity's tree."""
    db, recipe, step, _resumed = quit_recipe
    [only] = runner.status(db, recipe)["steps"]
    assert (only["state"], only["child_id"]) == ("paused", step)
    shown = client.get(f"/api/activity/jobs/{recipe}").json()
    assert [s["state"] for s in shown["stages"]] == ["paused"]
