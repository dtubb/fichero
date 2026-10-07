"""Running a started recipe (#5390): `source.recipe.start-runs-the-steps`, `source.recipe.step-skipped-says-why`,
`source.onboard.just-do-it`, `source.onboard.tools-not-automation`.

One `run-a-recipe` job in Activity runs the Start plan's cards in order over the project's material (every
page, and every file that has no pages), or, after an import, over the pages that import brought:

* a **workflow** card runs as a workflow run through the real runner, the same helpers a chain's steps use
  (`api/routes/workflow/chains.py`), so a run is the one job tree the activity spec draws (a `workflow` row,
  its steps and pages beneath it);
* a **check** card is a check run (`checking/job.py`);
* a **find-documents** card is a Find the Documents run (`finddocs/job.py`) over the pages' folders, accepting by
  itself only what the step's `accept_above` allows;
* an **export** card is the project's synced folder (`sync_folder.py`): the folder the step names is tied
  (once) and the pages are written, or a folder already tied rewrites them.

Each card's job is a child of the recipe's row. A card starts only when the one before it has finished. Each card
declares what it takes and gives (the job registry's kinds, `start.card_inputs`); one that fails stops only the cards
that need what it would have given and no other earlier card gave, and those say "not run" and why (#5498): names
read the uncorrected lines when Correct fails. The plan's skipped steps are kept on the row with why. A run's step
states are read from the steps' own jobs (the rows Activity shows), so run-status and Activity cannot disagree.
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
from fichero_server.recipes.assemble import PURPOSES, TOOL_PURPOSES

KIND = "run-a-recipe"
#: Purposes that run by themselves after Start (the "just do it" ones; `recipes/assemble.PURPOSES`).
AUTOMATIC_PURPOSES = frozenset(PURPOSES) - TOOL_PURPOSES
_CHECK_POLL_SECONDS = 0.5


def _library(db: Any) -> Path:
    return Path(db.path).parent


def _plan(db: Any) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.start import plan_start

    setup = read_project_setup(_library(db))
    stays_local = not (setup["answers"] or {}).get("cloud_allowed", False)
    return plan_start(setup["recipe"], stays_local=stays_local)


def enqueue(db: Any, plan: dict[str, Any], *, documents: list[str] | None, started_by: str,
            redo: list[str] | None = None) -> str:
    """Queue one run of the plan; `documents` None is all the project's material; `redo` names the steps to run
    again on pages that already have their output (`source.recipe.done-is-not-redone`)."""
    detail = {"runs": plan["runs"], "skipped": plan["skipped"], "documents": documents, "redo": list(redo or [])}
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
    # Any ticked "just do it" purpose runs the recipe over what the import brought.
    if AUTOMATIC_PURPOSES.isdisjoint((read_project_setup(library)["answers"] or {}).get("purposes") or ()):
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

    from fichero_server.workflows.default_workflows import resolve_shipped_workflow

    thread_id = f"thread-{uuid.uuid4().hex[:12]}"
    # By the shipped preset's stable id; a project seeded before ids were stable holds it under another (#5497).
    workflow = _load_step_workflow(db, card["workflow_id"]) or resolve_shipped_workflow(
        db, card["workflow_id"], card["workflow"])
    if workflow is None:
        return thread_id, "failed", (f"the shipped workflow {card['workflow']!r} is in neither this project nor "
                                     "the shipped defaults")
    # Registered up front, as a chain's steps are, so the run's stream and status know the thread.
    _set_workflow_state(thread_id, {"workflow_id": workflow.id, "workflow_name": workflow.name,
                                    "status": "accepted", "events": WorkflowEventHub(), "error": None,
                                    "final_state": None})
    request = ExecuteWorkflowRequest(workflow_id=workflow.id, inputs={"selected_doc_ids": documents},
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
                                                model=card["model"], prompt_file=card.get("prompt"),
                                                check=card.get("check", "model")),
                            started_by=started_by)["job_id"]
    return _wait(db, child, parent)


def _run_find_documents(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                        started_by: str) -> tuple[str, str, str | None]:
    """Find the Documents over the step's pages (each with its folder), accepting by itself only what the project's
    setting allows (`finddocs.recipe-step`, #5550)."""
    from fichero_server.finddocs import job as finddocs_job
    from fichero_server.models.found_documents import FindDocumentsRequest

    finddocs_job.register_job_kinds()
    child = finddocs_job.start(db, FindDocumentsRequest(scope_ids=documents, accept_above=card.get("accept_above")),
                               started_by=started_by, watched=False)
    return _wait(db, child, parent)


def _wait(db: Any, child: str, parent: str) -> tuple[str, str, str | None]:
    """The card's own job, a child of the recipe's row, waited on until it ends."""
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


def _run_publish(db: Any, card: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """The project as an 11ty static site, through the one site export (`source.job.publish`); again rewrites it."""
    from fichero_server.export_service import export_eleventy_site

    export_eleventy_site(db, card["folder"], overwrite=True, package_path=_library(db))
    return None, "done", None


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.recipes.start import count_pages  # noqa: F401  (the same material Start counts)

    job_id = jobs.job_id_for(db, KIND, subject)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    started_by = row["started_by"] or "owner"
    from fichero_server.recipes.done import pages_for, split_done

    brought = detail.get("documents")  # None: all the project's material
    redo = set(detail.get("redo") or [])
    steps = [{"steps": card["steps"], "card": card["card"], "state": "waiting", "child_id": None}
             for card in detail["runs"]]
    detail["steps"] = steps
    problems: list[str] = []
    for index, (card, step) in enumerate(zip(detail["runs"], steps)):
        named = ", ".join(card["steps"])
        blocked = _blocked(detail["runs"], steps, index)
        if blocked:
            step.update(state="not run", why=blocked)
            problems.append(f"step {named} not run: {blocked}")
            continue
        # The pages are worked out now, so pages a split made earlier in this run are among them.
        documents = pages_for(db, card, brought)
        if not redo.intersection(card["steps"]):
            documents, done = split_done(db, card, documents)
            step["already_done"] = done
        if not documents:
            step.update(state="done", child_id=None, why="already done on every page")
            continue
        step["state"] = "running"
        jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Running step {named}")
        if card["card"] == "workflow":
            child, state, why = _run_workflow(db, card, documents, job_id)
        elif card["card"] == "check":
            child, state, why = _run_check(db, card, documents, job_id, started_by)
        elif card["card"] == "find-documents":
            child, state, why = _run_find_documents(db, card, documents, job_id, started_by)
        elif card["card"] == "publish":
            child, state, why = _run_publish(db, card)
        else:
            child, state, why = _run_export(db, card, documents)
        step.update(state=state, child_id=child, why=why)
        if card["card"] == "workflow" and state == "done":
            # The step changed these pages' work: every kept export rewrites them (#5485).
            from fichero_server import kept_export

            kept_export.queue_rewrites(db, documents)
        if state != "done":
            problems.append(f"step {named} {state}: {why or 'no reason given'}")
    finished = sum(1 for s in steps if s["state"] == "done")
    words = (f"Stopped: {'; '.join(problems)}; {finished} of {len(steps)} steps done" if problems else
             f"Done: {len(steps)} steps run" + (f", {len(detail['skipped'])} skipped (see why)"
                                                 if detail["skipped"] else ""))
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    if problems:
        raise RuntimeError(words)
    return {"steps": steps}


def _blocked(cards: list[dict[str, Any]], steps: list[dict[str, Any]], index: int) -> str | None:
    """Why the card at `index` cannot run, or None (#5498): it needs a kind of thing that only earlier cards of
    this run give, and none of them finished. A kind no earlier card gives is the material's own (pages already
    read), so the card never waits for it. A card queued before cards declared their inputs waits on every card
    before it, as runs did then."""
    card = cards[index]
    before = list(zip(cards[:index], steps[:index]))
    if "takes" not in card:
        unfinished = [", ".join(c["steps"]) for c, s in before if s["state"] != "done"]
        return f"step {unfinished[0]} did not finish, and this step comes after it" if unfinished else None
    for take in card["takes"]:
        kinds = set(take.split("|"))
        givers = [(c, s) for c, s in before if kinds.intersection(c.get("gives") or ())]
        if givers and all(s["state"] != "done" for _c, s in givers):
            which = "; ".join(f"step {', '.join(c['steps'])} {s['state']}" for c, s in givers)
            needs = " or ".join(sorted(kinds)).replace("_", " ")
            return f"it needs {needs}, which no earlier step gave ({which})"
    return None


def status(db: Any, job_id: str) -> dict[str, Any]:
    """A recipe run: its state and each card's, read from the card's own job (the row Activity shows) once it
    has one, so this and Activity are one account (#5498). A run still waiting says what it waits for."""
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no recipe run {job_id}")
    detail = json.loads(row["detail"] or "{}")
    steps = detail.get("steps") or [{"steps": c["steps"], "card": c["card"], "state": "waiting", "child_id": None}
                                    for c in detail.get("runs", [])]
    for step in steps:
        child = jobs.read_job(db, step["child_id"]) if step.get("child_id") else None
        if child is not None:
            step["state"] = child["state"]
            if child["state"] in ("failed", "cancelled") and not step.get("why"):
                step["why"] = child["reason"]
    reason = row["reason"]
    if row["state"] == "waiting":
        ahead = [r["id"] for r in jobs.find_jobs(db, kinds=[KIND], states=["running"]) if r["id"] != job_id]
        if ahead:
            reason = f"Waiting for the recipe run {ahead[0]} to finish: recipe runs go one at a time"
    return {"job_id": job_id, "state": row["state"], "reason": reason, "documents": detail.get("documents"),
            "steps": steps, "skipped": detail.get("skipped", [])}


def started_plan(db: Any, job_id: str) -> dict[str, Any]:
    """What a run was started with: its cards and the steps it skipped, as it holds them."""
    row = jobs.read_job(db, job_id)
    detail = json.loads((row or {}).get("detail") or "{}")
    return {"runs": detail.get("runs", []), "skipped": detail.get("skipped", [])}


def unfinished_steps(db: Any) -> dict[str, dict[str, str]]:
    """The recipe steps whose latest finished run did not do them, {step: {"state", "why"}} (#5498): the plan
    offers them again ("failed last time ...; runs again") rather than dropping them, so retrying is Start,
    not a guessed `redo`. A step a later run did is done with; a run still going is not looked at."""
    out: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for row in jobs.find_jobs(db, kinds=[KIND], states=["done", "failed", "cancelled"]):
        for step in status(db, row["id"])["steps"]:
            for sid in step["steps"]:
                if sid in seen:
                    continue
                seen.add(sid)
                if step["state"] not in ("done", "waiting", "running"):
                    out[sid] = {"state": step["state"], "why": step.get("why") or "no reason given"}
    return out


def runs(db: Any) -> list[dict[str, Any]]:
    """Every recipe run of the project, newest first."""
    return [status(db, row["id"]) for row in jobs.find_jobs(db, kinds=[KIND])]


def register_job_kinds() -> None:
    from fichero_server.core.background_compute import set_utility_qos

    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="recipes",
                           qos=set_utility_qos, name="Run the recipe")
