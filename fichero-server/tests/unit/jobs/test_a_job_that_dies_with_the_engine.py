"""`activity.durable.dies-with-the-engine`: work the engine was doing when it died never reads "running" for good.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. WHY (2026-10-11, the hardening pass): an agent
and a person read Activity after a crash and must be told what happened to every job, in words, with a way on.
Checked live on a scratch engine killed (-9) during an import, a recipe run and its workflow step: on restart the
import's pages and the recipe run carried on from their checkpoints, the workflow run read "Interrupted: the engine
stopped at HH:MM", and nothing sat "running". Here the same, with the rows a kill leaves on disk written directly
(a kill runs no close hooks), then the project opened as the engine opens it.
"""
from __future__ import annotations

import asyncio

import ast
from pathlib import Path

from _scan_files import scan_rglob

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.workflows.activity import get_activity_tracker


def _killed_mid_job(db, kind: str, subject: str, attempts: int = 1) -> str:
    """A row as a kill leaves it: running, never finished."""
    job_id = jobs.enqueue(db, kind, subject, started_by="owner")
    db.execute("UPDATE jobs SET state = 'running', attempts = ?, started_at = now() WHERE id = ?", [attempts, job_id])
    return job_id


def _open_as_the_engine_does(test_package):
    """The engine starting again: a new manager has nothing open, and opening the project runs its resume."""
    db_manager.close_database(test_package)
    return db_manager.get_database(test_package)


def test_no_job_is_left_running_after_the_engine_died(client, db, test_package, monkeypatch):
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)  # nothing is taken up while we read
    jobs.load_kinds()
    page = _killed_mid_job(db, "thumbnail", "doc-1")
    download = _killed_mid_job(db, "download-model", "spacy:es_core_news_sm")
    recipe = _killed_mid_job(db, "run-a-recipe", "recipe:killed")
    poisoned = _killed_mid_job(db, "download-model", "spacy:en_core_web_sm", attempts=jobs.MAX_ATTEMPTS)
    thread = "thread-killed000001"
    asyncio.run(get_activity_tracker(str(db.path)).store.save_workflow_run(
        thread_id=thread, workflow_id="wf", workflow_name="Detect Segments (Kraken)", status="running"))

    db = _open_as_the_engine_does(test_package)

    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE state = 'running'")[0] == 0, "nothing reads running"
    for job_id in (page, download, recipe):
        row = jobs.read_job(db, job_id)
        assert (row["state"], row["reason"]) == ("waiting", "Interrupted; carries on"), (job_id, row)
    listed = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}
    set_aside = listed[poisoned]
    assert set_aside["state"] == "failed" and set_aside["reason"] == "Stopped 3 times by the engine stopping; set aside. Resume to carry on."
    assert set_aside["offer"] == "Resume" and set_aside["failed_at"], set_aside
    run = listed[thread]
    assert run["state"] == "failed" and run["reason"].startswith("Interrupted: the engine stopped at"), run

    retried = client.post(f"/api/activity/jobs/{poisoned}/retry")
    assert retried.status_code == 200 and retried.json()["state"] == "waiting", retried.text
    listed = client.get("/api/activity/jobs").json()["jobs"]
    after = [j for j in listed if j["task_type"] == "download-model"]
    assert len(after) == 1 and after[0]["failed_at"] is None, [(j["id"], j["task_type"], j["state"]) for j in listed]


def test_every_kind_a_restart_may_find_is_registered_when_the_queue_first_looks():
    """WHY: after a restart a project's waiting rows are run by kinds `load_kinds` registers; a module missing from
    its list (the model download's, Find the Documents') left its rows waiting with no runner, named by their id
    ("download-model") and with no Resume offered, until something else happened to register it."""
    src = Path(jobs.__file__).resolve().parents[1]
    registering = set()
    for path in scan_rglob(src, "*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        if "register_job_kinds" in names:
            registering.add("fichero_server." + path.relative_to(src).with_suffix("").as_posix().replace("/", "."))
    registered_by_others = {"fichero_server.checking.line_check", "fichero_server.checking.tie_text"}  # checking.job
    assert registering - set(jobs._KIND_MODULES) - registered_by_others == set()
