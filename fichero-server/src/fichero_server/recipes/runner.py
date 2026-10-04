"""Running a started recipe (#5390): `source.recipe.start-runs-the-steps`, `source.recipe.step-skipped-says-why`,
`source.onboard.just-do-it`, `source.onboard.tools-not-automation`.

One `run-a-recipe` job in Activity runs the Start plan's cards in order over the project's material (every
page, and every file that has no pages), or, after an import, over the pages that import brought:

* a **workflow** card runs as a workflow run through the real runner, the same helpers a chain's steps use
  (`api/routes/workflow/chains.py`), so a run is the one job tree the activity spec draws (a `workflow` row,
  its steps and pages beneath it);
* a **check** card is a check run (`checking/job.py`);
* an **export** card is the project's synced folder (`sync_folder.py`): the folder the step names is tied
  (once) and the pages are written, or a folder already tied rewrites them.

Each card's job is a child of the recipe's row. A card starts only when the one before it has finished; one
that fails stops those after it, which say "not run". The plan's skipped steps are kept on the row with why.
The recipe job only waits on its cards, so it has its own lane, one at a time: two recipes never wait on
each other's checks.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs

KIND = "run-a-recipe"
#: Purposes that run by themselves after Start (the "just do it" ones; `recipes/assemble.PURPOSES`).
AUTOMATIC_PURPOSES = frozenset({"transcribe", "entities", "search", "knowledge-graph", "map-places"})
_CHECK_POLL_SECONDS = 0.5


def _library(db: Any) -> Path:
    return Path(db.path).parent


def _plan(db: Any) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.start import plan_start

    setup = read_project_setup(_library(db))
    stays_local = not (setup["answers"] or {}).get("cloud_allowed", False)
    return plan_start(setup["recipe"], stays_local=stays_local)


def enqueue(db: Any, plan: dict[str, Any], *, documents: list[str] | None, started_by: str) -> str:
    """Queue one run of the plan; `documents` None is all the project's material."""
    detail = {"runs": plan["runs"], "skipped": plan["skipped"], "documents": documents}
    words = "Waiting to run the recipe" + (f" on {len(documents)} new pages" if documents is not None else "")
    return jobs.enqueue_remote(db, KIND, f"recipe:{uuid.uuid4()}", target="this-mac", detail=json.dumps(detail),
                               reason=words, started_by=started_by)


def material_arrived(db: Any, document_ids: list[str]) -> str | None:
    """An import brought new material: after Start, a "just do it" project runs its recipe over it alone;
    before Start, or on a "tools" purpose, nothing runs (`source.onboard.*`)."""
    from fichero_server.recipes.project import read_project_setup, read_start

    if not document_ids:
        return None
    library = _library(db)
    if read_start(library) is None:
        return None
    if (read_project_setup(library)["answers"] or {}).get("purpose") not in AUTOMATIC_PURPOSES:
        return None
    plan = _plan(db)
    if plan["refusals"] or not plan["runs"]:
        return None
    return enqueue(db, plan, documents=list(document_ids), started_by="import")


def _run_workflow(db: Any, card: dict[str, Any], documents: list[str], parent: str) -> tuple[str, str, str | None]:
    """A workflow card through the real runner: (child id, state, why)."""
    from fichero_server.api.routes.workflow.chains import (
        _load_step_workflow,
        _record_step_run_accepted,
        _run_step_workflow,
        _step_run_outcome,
        _validate_step_workflow,
    )
    from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
    from fichero_server.execution.runner import WorkflowEventHub, _set_workflow_state

    thread_id = f"thread-{uuid.uuid4().hex[:12]}"
    workflow = _load_step_workflow(db, card["workflow_id"])
    if workflow is None:
        return thread_id, "failed", f"the shipped workflow {card['workflow']!r} is not in this build"
    # Registered up front, as a chain's steps are, so the run's stream and status know the thread.
    _set_workflow_state(thread_id, {"workflow_id": card["workflow_id"], "workflow_name": workflow.name,
                                    "status": "accepted", "events": WorkflowEventHub(), "error": None,
                                    "final_state": None})
    request = ExecuteWorkflowRequest(workflow_id=card["workflow_id"], inputs={"selected_doc_ids": documents},
                                     thread_id=thread_id, provider_override=card["provider_override"],
                                     model_override=card["model_override"], skip_cache=True)
    try:
        _validate_step_workflow(workflow, request, db)
    except Exception as exc:  # noqa: BLE001 -- the run's own preflight says why; the recipe records it
        return thread_id, "failed", str(getattr(exc, "detail", exc))

    async def go() -> None:
        await _record_step_run_accepted(db, thread_id, workflow, request)
        jobs.set_parent(db, thread_id, parent)
        await _run_step_workflow(thread_id=thread_id, workflow=workflow, request=request, db=db)

    asyncio.run(go())
    status, error = _step_run_outcome(thread_id)
    return thread_id, ("done" if status == "completed" else "failed"), error


def _run_check(db: Any, card: dict[str, Any], documents: list[str], parent: str,
               started_by: str) -> tuple[str, str, str | None]:
    from fichero_server.checking import job as check_job
    from fichero_server.checking.job import CheckRunRequest

    check_job.register_job_kinds()
    child = check_job.start(db, CheckRunRequest(layer=card["layer"], scope_ids=documents, provider=card["provider"],
                                                model=card["model"], prompt_file=card.get("prompt")),
                            started_by=started_by)["job_id"]
    jobs.set_parent(db, child, parent)
    while True:
        row = jobs.read_job(db, child)
        if row["state"] in ("done", "failed", "cancelled"):
            return child, row["state"], row["reason"] if row["state"] != "done" else None
        time.sleep(_CHECK_POLL_SECONDS)


def _run_export(db: Any, card: dict[str, Any], documents: list[str]) -> tuple[str | None, str, str | None]:
    from fichero_server import sync_folder

    tied = {f["path"]: f["id"] for f in sync_folder._folders(db)}
    folder = card.get("folder")
    if folder and str(Path(folder)) not in tied:
        sync_folder.tie(db, folder, card.get("formats") or list(sync_folder.FORMATS))
        return None, "done", None
    if not tied:
        return None, "failed", "no synced folder is tied, and the step names none"
    sync_folder.queue_rewrites(db, documents)
    return None, "done", None


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.recipes.start import count_pages  # noqa: F401  (the same material Start counts)

    job_id = jobs.job_id_for(db, KIND, subject)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    started_by = row["started_by"] or "owner"
    documents = detail.get("documents")
    if documents is None:
        documents = db.unit_of_work_ids()
    steps = [{"steps": card["steps"], "card": card["card"], "state": "waiting", "child_id": None}
             for card in detail["runs"]]
    detail["steps"] = steps
    failed_at = None
    for card, step in zip(detail["runs"], steps):
        if failed_at is not None:
            step["state"] = "not run"
            continue
        named = ", ".join(card["steps"])
        step["state"] = "running"
        jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Running step {named}")
        if card["card"] == "workflow":
            child, state, why = _run_workflow(db, card, documents, job_id)
        elif card["card"] == "check":
            child, state, why = _run_check(db, card, documents, job_id, started_by)
        else:
            child, state, why = _run_export(db, card, documents)
        step.update(state=state, child_id=child, why=why)
        if state != "done":
            failed_at = f"step {named} {state}: {why or 'no reason given'}"
    words = (f"Stopped: {failed_at}; the steps after it were not run" if failed_at else
             f"Done: {len(steps)} steps run" + (f", {len(detail['skipped'])} skipped (see why)"
                                                 if detail["skipped"] else ""))
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    if failed_at:
        raise RuntimeError(words)
    return {"steps": steps}


def status(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no recipe run {job_id}")
    detail = json.loads(row["detail"] or "{}")
    steps = detail.get("steps") or [{"steps": c["steps"], "card": c["card"], "state": "waiting", "child_id": None}
                                    for c in detail.get("runs", [])]
    return {"job_id": job_id, "state": row["state"], "reason": row["reason"], "documents": detail.get("documents"),
            "steps": steps, "skipped": detail.get("skipped", [])}


def runs(db: Any) -> list[dict[str, Any]]:
    """Every recipe run of the project, newest first."""
    return [status(db, row["id"]) for row in jobs.find_jobs(db, kinds=[KIND])]


def register_job_kinds() -> None:
    from fichero_server.core.background_compute import set_utility_qos

    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="recipes",
                           qos=set_utility_qos, name="Run the recipe")
