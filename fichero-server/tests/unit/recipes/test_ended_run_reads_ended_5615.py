"""A run that has ended reads ended, in words, on every surface (#5615, `activity.ended-run-reads-ended`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md and
docs/contributor_manual/specs/source/models-chains-and-projects.md (`source.recipe.run-status-is-activity`). Seen in
the MCP review of 2026-10-08 on a real project: a recipe run failed "Interrupted 3 times; set aside" while its
Correct stage said running and its names stage waiting; the list named it `run-a-recipe`; the reason gave no cause,
time or next step; failed rows stood at 100 % with nothing done; a page's run history said
`process_died_recovered_on_library_open`.

Through the public routes (`GET /api/activity/jobs`, `GET /api/activity/jobs/{id}`, `POST .../retry`,
`GET /api/recipes/project/runs/{id}`, `GET /api/documents/run-history`). The engine's death is staged as it leaves
the rows (a run row left running after its third try), then the engine's own `resume` runs, as on a project open.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import runner


@pytest.fixture(autouse=True)
def engine(monkeypatch, app_db):
    """A fresh scheduler, paused: nothing picks the run while the test reads it."""
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_paused(True)
    yield
    jobs.set_paused(False)


def _png(path: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (32, 32), (250, 250, 250)).save(str(path), format="PNG")
    return path


@pytest.fixture
def pages(db, tmp_path):
    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i in range(2):
        doc = Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image,
                       path=str(_png(tmp_path / f"p{i}.png")))
        db.save(doc)
        docs.append(doc)
    return docs


def _set_up(client):
    recipe = {"fichero_recipe": 1, "id": "t/onboarding", "version": "0.1.0", "title": "Transcribe + names",
              "steps": [{"id": "correct", "job": "correct", "model": {"cloud": "openai", "model": "gpt-5"},
                         "runs_on": "cloud:openai"},
                        {"id": "names", "job": "find-names-tag-words",
                         "model": {"spacy": "es_core_news_sm", "version": "3.8.0"}}]}
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe", "cloud_allowed": True},
                                                 "recipe": recipe})
    assert r.status_code == 200, r.text


def _interrupted_run(db) -> str:
    """A recipe run as an engine that died on its third try leaves it: running, its Correct stage running with no
    job of its own yet, its names stage waiting."""
    cards = [{"steps": ["correct"], "card": "workflow", "job": "correct"},
             {"steps": ["names"], "card": "workflow", "job": "find-names-tag-words"}]
    job_id = runner.enqueue(db, {"runs": cards, "skipped": []}, documents=None, started_by="owner")
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    detail["steps"] = [{"steps": ["correct"], "card": "workflow", "state": "running", "child_id": None},
                       {"steps": ["names"], "card": "workflow", "state": "waiting", "child_id": None}]
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Running step correct")
    db.execute("UPDATE jobs SET state = 'running', attempts = 3, started_at = ? WHERE id = ?",
               [datetime(2026, 10, 8, 9, 41, tzinfo=timezone.utc), job_id])
    return job_id


def _listed(client, job_id):
    rows = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == job_id]
    assert len(rows) == 1, rows
    return rows[0]


def test_a_set_aside_recipe_run_reads_ended_named_and_offers_resume(client, db, pages, monkeypatch):
    """WHY (#5615 items 1-4): after the engine died three times the run was failed "Interrupted 3 times; set
    aside", but its stages still said running and waiting, the list called it `run-a-recipe` at 100 % with nothing
    done, and nothing said what stopped it, when, or what to do next."""
    _set_up(client)
    job_id = _interrupted_run(db)
    # A project opened with nothing waiting: no lane has loaded the kinds.
    monkeypatch.delitem(jobs.KINDS, runner.KIND, raising=False)
    monkeypatch.setattr(jobs, "_kinds_loaded_once", False)

    jobs.resume(db)  # the engine starts again

    row = _listed(client, job_id)
    assert row["state"] == "failed"
    assert row["name"] == "Run the recipe: Transcribe + names", row["name"]
    assert (row["current"], row["total"], row["percent"]) == (0, 2, 0.0), row
    reason = row["reason"]
    # Said once, short, no clock (#5844; it was a long sentence with UTC times).
    assert reason == "Stopped 3 times by the engine stopping; set aside. Resume to carry on.", reason
    assert row["offer"] == "Resume"

    status = client.get(f"/api/recipes/project/runs/{job_id}").json()
    stages = {s["steps"][0]: s for s in status["steps"]}
    assert stages["correct"]["state"] == "not run", stages
    assert stages["correct"]["why"].startswith("stopped when the run ended, before this step finished: Stopped 3")
    assert stages["names"]["state"] == "not run"
    assert stages["names"]["why"].startswith("the run ended before this step: Stopped 3 times")
    tree = client.get(f"/api/activity/jobs/{job_id}").json()
    assert [s["state"] for s in tree["stages"]] == ["not run", "not run"]
    assert tree["reason"] == reason  # the list and the tree say the same

    r = client.post(f"/api/activity/jobs/{job_id}/retry")  # Resume: the run's own Retry, refused before
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "waiting"


def test_a_failed_workflow_run_with_nothing_done_is_at_0_percent(client, monkeypatch):
    """WHY (#5615 item 4): a failed workflow row said percent 100.0 with current 0 and pages_done 0."""
    class _Store:
        async def list_workflow_runs(self, limit=50):
            return [SimpleNamespace(thread_id="t-review", workflow_id="w1", workflow_name="Paleographer Review",
                                    status="failed", error="Review 2 failed", progress_timeline=[])]

    async def account(db, thread_id, run=None):
        from fichero_server.workflows.run_account import RunAccount

        return RunAccount(state="failed", pages_total=203, pages_done=0, pages_failed=0,
                          pages_left=203)

    monkeypatch.setattr("fichero_server.api.routes.system.activity.get_activity_tracker",
                        lambda db_path: SimpleNamespace(store=_Store()))
    monkeypatch.setattr("fichero_server.workflows.run_account.run_account", account)
    row = next(j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == "t-review")
    assert (row["state"], row["current"], row["total"], row["percent"]) == ("failed", 0, 203, 0.0)


def test_a_page_row_names_its_step_row_and_its_run(client, db):
    """WHY (#5615 item 5): a page's `parent_id` read "thread-…:Review 1 — Abbreviations & Formulary", which looks
    like an id glued to a label. It is its step's row id (every step row is written under "<run>:<step>"), so it
    is looked up like any job; and the row says the run it is for, `run_id`, a plain run id."""
    run, step = "thread-0a1b2c3d4e5f", "Review 1 — Abbreviations & Formulary"
    jobs._record(db, run, kind="workflow", subject=run, parent_id=None, state="running", reason=None,
                 name="Paleographer Review")
    jobs.record_step(db.path, run, step, status="running", name=step)
    page = jobs.enqueue(db, "read-a-page", "a page")
    jobs.set_parent(db, page, jobs.step_id(run, step))

    row = _listed(client, page)
    assert row["parent_id"] == f"{run}:{step}" and row["run_id"] == run
    looked_up = client.get(f"/api/activity/jobs/{row['parent_id']}")
    assert looked_up.status_code == 200 and looked_up.json()["kind"] == "workflow-step"
    assert client.get(f"/api/activity/jobs/{row['run_id']}").json()["kind"] == "workflow"


def test_a_page_run_history_says_how_each_run_ended_in_words(client, db):
    """WHY (#5615 item 6): a page's run history gave a recovered run's outcome as the code
    `process_died_recovered_on_library_open`, and every recorded run as done, failed or not."""
    from fichero_server.models import Document
    from fichero_server.workflows.completion import RECOVERED_REASON

    doc = Document(name="p.png")
    doc.workflow_runs = [
        {"thread_id": "t-old", "workflow_id": "w", "workflow_name": "Transcribe",
         "result": {"status": "failed", "reason": "process_died_recovered_on_library_open"}},
        {"thread_id": "t-ok", "workflow_id": "w", "workflow_name": "Transcribe", "provider": "omlx",
         "model": "qwen", "result": {"status": "completed"}},
    ]
    db.save(doc)
    history = client.get("/api/documents/run-history", params={"ids": [doc.id]}).json()["items"][doc.id]
    runs = {e["thread_id"]: e for e in history if e["source"] == "workflow_run"}
    assert (runs["t-old"]["state"], runs["t-old"]["reason"]) == ("failed", RECOVERED_REASON)
    assert (runs["t-ok"]["state"], runs["t-ok"]["model"]) == ("done", "qwen")
    provenance = client.get(f"/api/documents/{doc.id}/workflow-runs").json()["items"]
    assert provenance[0]["result"]["reason"] == RECOVERED_REASON


def test_a_run_records_the_model_it_ran_with(db):
    """WHY (#5615 item 6): a completed Transcribe run recorded provider '' and model '': its pages took the
    workflow's own (empty) default, not the model the recipe step ran it with (the run's override)."""
    from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
    from fichero_server.execution.runner import _ran_with
    from fichero_server.models import Workflow

    workflow = Workflow(name="Transcribe", nodes=[], edges=[], provider="", model="")
    chosen = ExecuteWorkflowRequest(workflow_id=workflow.id, provider_override="omlx", model_override="qwen-vl")
    assert _ran_with(workflow, chosen) == ("omlx", "qwen-vl")
    own = Workflow(name="Transcribe", nodes=[], edges=[], provider="openai", model="gpt-5")
    assert _ran_with(own, ExecuteWorkflowRequest(workflow_id=own.id)) == ("openai", "gpt-5")
