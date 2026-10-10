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
* an **entries** card splits a diary or register into its dated entries with the Diary Entries splitter
  (`workflows/tools/diary_entries.py`) and the step's model, over the pages that have text (#5581);
* a **prepare** card gives each faded page a prepared rendition, its contrast raised, that lines and reading then
  read; the original is kept (`recipes/prepare.py`, #5580);
* an **embed** card (search) queues the embed job (`make-a-vector`) for each page and waits for them;
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
from collections import Counter
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs
from fichero_server.recipes.assemble import PURPOSES, TOOL_PURPOSES

KIND = "run-a-recipe"
#: Purposes that run by themselves after Start (the "just do it" ones; `recipes/assemble.PURPOSES`).
AUTOMATIC_PURPOSES = frozenset(PURPOSES) - TOOL_PURPOSES
_CHECK_POLL_SECONDS = 0.5
#: Cards that line or read pages: a blank verso is left out of them (#5579).
_NOT_ON_BLANK_VERSOS = frozenset({"find-lines", "read-a-line", "read-a-page"})


def _library(db: Any) -> Path:
    return Path(db.path).parent


def _plan(db: Any) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.start import plan_start

    setup = read_project_setup(_library(db))
    answers = setup["answers"] or {}
    stays_local = not answers.get("cloud_allowed", False)
    # New material runs only what What runs by itself ticks; with Nothing runs automatically, nothing (#5478).
    return plan_start(setup["recipe"], stays_local=stays_local, automatic=answers.get("automatic"),
                      job_answers=answers.get("job_answers"))


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
    before Start, or on a "tools" purpose, nothing runs (`source.onboard.*`). One whose recipe cannot run
    leaves a failed row saying why (`refused`, #5575). Returns the row's job id, or None when nothing was asked."""
    if not document_ids:
        return None
    if _why_no_recipe_on_add(db) is not None:
        return None
    plan = _plan(db)
    if plan["refusals"] or not plan["runs"]:
        return refused(db, plan, list(document_ids))
    return enqueue(db, plan, documents=list(document_ids), started_by="import")


def _why_no_recipe_on_add(db: Any) -> str | None:
    """Why an import runs no recipe at all, in words; None when it runs the recipe's plan. The one gate
    `material_arrived` and `what_runs_by_itself` share."""
    from fichero_server.recipes.project import read_project_setup, read_start

    library = _library(db)
    if read_start(library) is None:
        return "Start has not been pressed: nothing in a project runs by itself before the first yes"
    answers = read_project_setup(library)["answers"] or {}
    # Any ticked "just do it" purpose runs the recipe over what the import brought.
    if AUTOMATIC_PURPOSES.isdisjoint(answers.get("purposes") or ()):
        return "no purpose that runs by itself is ticked: a tools purpose runs only by hand"
    # Nothing runs automatically is the person's choice, not a refusal: no row at all (#5478, #5575).
    if not (answers.get("automatic") or {}).get("runs", True):
        return "What runs by itself is 'Nothing runs automatically'"
    return None


def what_runs_by_itself(db: Any) -> dict[str, list[dict[str, Any]]]:
    """What runs by itself in this project (#5362, `activity.auto.what-runs-by-itself`): on an import
    (`on_add`) and on a correction of a page's text (`on_correction`), each entry a job kind with its name,
    whether it runs and why. Read from the same gates the import and the correction use: the derivative
    stages, the NLP setting, the recipe's first yes, purposes and What runs by itself, and the Start plan's
    runs and skipped steps. Reads only; nothing runs."""
    from fichero_server.actions.page_text_cache import REEMBED_KIND, REREAD_NAMES_KIND
    from fichero_server.importers.derivatives import EMBED_KIND, NLP_KIND, THUMBNAIL_KIND
    from fichero_server.importers.nlp_draft import auto_nlp_enabled

    def entry(job: str, runs: bool, why: str, steps: list[str] | None = None) -> dict[str, Any]:
        return {"job": job, "name": jobs.kind_name(job), "runs": runs, "why": why, "steps": steps or []}

    names = auto_nlp_enabled()
    names_why = ("names are read automatically (Settings > General > Ingestion)" if names else
                 "names are not read automatically (Settings > General > Ingestion is off)")
    on_add = [entry(THUMBNAIL_KIND, True, "every page added gets its picture"),
              entry(EMBED_KIND, True, "every page added is made searchable by meaning"),
              entry(NLP_KIND, names, names_why)]
    why_not = _why_no_recipe_on_add(db)
    if why_not is not None:
        on_add.append(entry(KIND, False, f"the project's recipe does not run on an import: {why_not}"))
    else:
        plan = _plan(db)
        if plan["refusals"] or not plan["runs"]:
            refusals = "; ".join(plan["refusals"]) or "nothing in this recipe can run"
            on_add.append(entry(KIND, False, f"the project's recipe cannot run on an import: {refusals}"))
        for run in plan["runs"]:
            on_add.append(entry(run["job"], True, "the project's recipe runs it on what an import brings",
                                list(run.get("steps") or [])))
        for skipped in plan["skipped"]:
            on_add.append({"job": None, "name": skipped["step"], "runs": False, "why": skipped["why"],
                           "steps": [skipped["step"]]})
    on_correction = [entry(REEMBED_KIND, True, "a corrected page is made searchable again"),
                     entry(REREAD_NAMES_KIND, names, names_why)]
    return {"on_add": on_add, "on_correction": on_correction}


def refused(db: Any, plan: dict[str, Any], documents: list[str]) -> str:
    """An import the recipe cannot run on leaves one `run-a-recipe` row in Activity, failed, that says why and
    what fixes it (`source.onboard.auto.on-add-refusal-said`, #5575): the plan's refusals, in its words (each
    names its fix: download the model, choose another). The new pages are not read."""
    why = "; ".join(plan["refusals"]) or "nothing in this recipe can run"
    noun = "page" if len(documents) == 1 else "pages"
    words = (f"Not run on the {len(documents)} new {noun} this import brought: {why}. "
             "Set Up… › Ready shows the plan and each fix")
    detail = {"runs": [], "skipped": plan["skipped"], "documents": documents, "refusals": plan["refusals"]}
    return jobs.record_not_run(db, KIND, f"recipe:{uuid.uuid4()}", reason=words, detail=json.dumps(detail),
                               started_by="import")


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
    if card.get("tool_config"):
        # The step's settings from setup's answers (which kinds of names, #5478), on this run's copy only.
        workflow = workflow.model_copy(deep=True)
        for node in workflow.nodes:
            node["config"] = {**(node.get("config") or {}), **(card["tool_config"].get(node.get("tool")) or {})}
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

    async def go() -> dict[str, Any] | None:
        await _record_step_run_accepted(db, thread_id, workflow, request)
        jobs.set_parent(db, thread_id, parent)
        return await _until_ended(db, thread_id, asyncio.ensure_future(
            _run_step_workflow(thread_id=thread_id, workflow=workflow, request=request, db=db)), parent)

    dead = asyncio.run(go())
    _closed_stops_the_recipe(db, thread_id, parent)
    if dead is not None:  # the run's row ended and the run never came back: its row says how
        return thread_id, ("done" if dead["state"] == "done" else "failed"), dead["reason"] or dead["state"]
    status, error = _step_run_outcome(thread_id)
    return thread_id, ("done" if status == "completed" else "failed"), error


#: How long a step's run may go on after its row has ended (its last writes, its documents settled) before the
#: recipe stops waiting on it (#5608).
_DEAD_CHILD_GRACE_SECONDS = 30.0


async def _until_ended(db: Any, child: str, run: "asyncio.Future", parent: str | None = None) -> dict[str, Any] | None:
    """Wait for a step's run, never on a dead one (#5608): None when the run returns; its row when the row ended
    (done, failed, cancelled) or its project closed, and the run did not return within the grace after. Stop on the
    recipe's row (`parent`) stops the run through its own Stop and waits for it to wind down (#5609)."""
    ended_at: float | None = None
    stopping = False
    while True:
        done, _ = await asyncio.wait({run}, timeout=_CHECK_POLL_SECONDS)
        if done:
            run.result()
            return None
        if not stopping:
            stopping = _stop_child_if_asked(db, parent, child)
        row = jobs.read_job(db, child) if jobs._still_open(db) else {"state": "cancelled",
                                                                      "reason": jobs.CLOSED_BEFORE_RUN}
        if row is None or row["state"] not in ("done", "failed", "cancelled"):
            ended_at = None
            continue
        ended_at = ended_at or time.monotonic()
        if time.monotonic() - ended_at >= _DEAD_CHILD_GRACE_SECONDS:
            return row


def request_cancel(db: Any, job_id: str) -> str:
    """Stop on a recipe run's row (#5609, `activity.jobs-are-a-tree`): a waiting or paused run ends cancelled now;
    a running one is asked to stop: the step it is running is stopped through that step's own Stop and every step
    after it is not run; the row says it is stopping until then (and a run stopping when the engine went away is
    not taken up again, `jobs.resume`). Returns `cancelled`, or `stopping` while the running step winds down."""
    from fichero_server.execution.cancellation import request_cancellation

    state = jobs._job_row(db, job_id)[1]
    if state in ("waiting", "paused"):
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if state != "running":
        return state
    request_cancellation(job_id)
    jobs.say_stopping(db, job_id)
    return "stopping"


def _stop_asked(job_id: str | None) -> bool:
    from fichero_server.execution.cancellation import cancellation_requested

    return cancellation_requested(job_id)


def _stop_child_if_asked(db: Any, parent: str | None, child: str) -> bool:
    """The recipe run was stopped: its running step's job is stopped through the one job Stop (`jobs.cancel_job`).
    True once asked (asked once)."""
    if not _stop_asked(parent) or not jobs._still_open(db):
        return False
    try:
        jobs.cancel_job(db, child)
    except KeyError:  # its row is not written yet: asked again at the next look
        return False
    return True


def _closed_stops_the_recipe(db: Any, child: str | None = None, parent: str | None = None) -> None:
    """A step ended because its project closed or is closing (#5608): the recipe run stops here, its row left
    running (not failed: nothing it did failed), and the project's next open carries it on (`jobs.resume`,
    "Interrupted; carries on"); no step runs on a closed project. A run a person stopped (`parent`) ends stopped
    instead, and is not carried on (#5609)."""
    from fichero_server.workflows.run_account import closed_mid_run

    if not jobs._still_open(db) or (child is not None and closed_mid_run(child)):
        if _stop_asked(parent):
            raise jobs.JobCancelled("Stopped by you; the project was closed as the run stopped")
        raise jobs.JobOutOfReach("Interrupted: the project was closed; carries on when it opens again")


def _run_by_reader(db: Any, card: dict[str, Any], documents: list[str], kinds: dict[str, str], parent: str,
                   step: dict[str, Any]) -> tuple[str, str, str | None]:
    """A reading card with a reader per kind (#5578): one workflow run per reader, each page read by
    `readers[kind]` when the recipe has one for its kind, else by the card's own reader. Each run is listed on the
    step (`readers`); the step's child is the first run that failed, else the first."""
    groups: dict[str | None, list[str]] = {}
    for doc_id in documents:
        kind = kinds.get(doc_id)
        groups.setdefault(kind if kind in card["readers"] else None, []).append(doc_id)
    ran = []
    for kind, pages in groups.items():
        if _stop_asked(parent) and ran:  # stopped: the readers after the one stopped do not run (#5609)
            break
        child, state, why = _run_workflow(db, {**card, **card["readers"][kind]} if kind else card, pages, parent)
        ran.append({"material": kind, "pages": len(pages), "model": (card["readers"][kind] if kind else card)
                    ["model_override"], "child_id": child, "state": state, "why": why})
    step["readers"] = ran
    failed = [r for r in ran if r["state"] != "done"]
    first = (failed or ran)[0]
    why = "; ".join(f"{r['pages']} {r['material'] or 'other'} pages: {r['why'] or r['state']}" for r in failed)
    return first["child_id"], first["state"], why or None


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

    from fichero_server.execution.cancellation import link_child, unlink_child

    finddocs_job.register_job_kinds()
    child = finddocs_job.start(db, FindDocumentsRequest(scope_ids=documents, accept_above=card.get("accept_above")),
                               started_by=started_by, watched=False)
    link_child(parent, child)  # Stop on the recipe run reaches its next folder or page at once (#5609)
    try:
        return _wait(db, child, parent)
    finally:
        unlink_child(child)


def _run_entries(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                 step: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """A diary or register split into its dated entries (`source.onboard.auto.diary-entries`, #5581): the Diary
    Entries workflow's own splitter, with the step's model, over the pages that have text. The step's account
    (`entries`) says how many pages it split, how many had no text, and what it made of their entries."""
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Document
    from fichero_server.workflows.tools.diary_entries import split_pages_into_entries

    pages = [page for page in (db.get(Document, doc_id) for doc_id in documents) if page is not None]
    with_text = [page for page in pages if (page.page_content or "").strip()]
    config = LLMConfig(provider=card["provider"], model=card["model"])
    try:
        _made, totals, errors, _lines = asyncio.run(split_pages_into_entries(
            db, with_text, config, stop=lambda: _stop_asked(parent)))
    except Exception as exc:  # noqa: BLE001 -- the model's failure, in its words, on the step
        step["entries"] = {"pages": len(with_text), "without_text": len(pages) - len(with_text)}
        return None, "failed", f"the entries were not split: {exc}"
    step["entries"] = {"pages": len(with_text), "without_text": len(pages) - len(with_text), **totals}
    if _stop_asked(parent):  # stopped before its next page (#5609): `pages` says how many it split
        return None, "cancelled", "Stopped by you"
    if errors:
        return None, "failed", "; ".join(errors)
    return None, "done", None


def _run_prepare(db: Any, documents: list[str], parent: str,
                 step: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """Each faded page gets a prepared rendition (`source.onboard.auto.prepare-damaged-images`, #5580); the step's
    account (`prepared`) says how many it prepared, how many were clear and how many had no image to look at."""
    from fichero_server.recipes.prepare import prepare_pages

    step["prepared"] = prepare_pages(db, documents, parent, stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):  # stopped before its next page (#5609): the account counts the pages it looked at
        return None, "cancelled", "Stopped by you"
    return None, "done", None


def _run_regions(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                 step: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """Each page image's regions found by the step's YOLO model and saved as its regions (`prep.yolo.regions-card`,
    #5525); the step's account (`regions_found`) says how many pages and regions, and pages with no image."""
    from fichero_server.recipes.regions import find_regions

    step["regions_found"] = find_regions(db, documents, parent, card["model"], stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):
        return None, "cancelled", "Stopped by you"
    return None, "done", None


def _wait(db: Any, child: str, parent: str) -> tuple[str, str, str | None]:
    """The card's own job, a child of the recipe's row, waited on until it ends (any end), or until its project
    closes (#5608)."""
    jobs.set_parent(db, child, parent)
    stopping = False
    while True:
        _closed_stops_the_recipe(db, parent=parent)
        if not stopping:
            stopping = _stop_child_if_asked(db, parent, child)
        row = jobs.read_job(db, child)
        if row["state"] in ("done", "failed", "cancelled"):
            return child, row["state"], row["reason"] if row["state"] != "done" else None
        time.sleep(_CHECK_POLL_SECONDS)


def _run_embed(db: Any, documents: list[str], parent: str, started_by: str) -> tuple[str | None, str, str | None]:
    """Search: the embed job (`make-a-vector`, the one that follows every correction) queued for each page, as a
    child of the recipe's row, and waited for (#5574). A page already waiting to be embedded keeps its job."""
    from fichero_server.actions.page_text_cache import REEMBED_KIND

    children = [jobs.enqueue(db, REEMBED_KIND, doc_id, started_by=started_by) for doc_id in documents]
    for child in children:
        jobs.set_parent(db, child, parent)
    while True:
        if _stop_asked(parent):  # stopped (#5609): the run stops waiting; a page's embed job, which a correction
            return None, "cancelled", "Stopped by you"  # may share, is left to finish (it is cheap and kept)
        rows = [jobs.read_job(db, child) for child in children]
        if all(r["state"] in ("done", "failed", "cancelled") for r in rows):
            failed = [r for r in rows if r["state"] != "done"]
            if not failed:
                return None, "done", None
            return None, "failed", (f"{len(failed)} of {len(rows)} pages were not embedded: "
                                    f"{failed[0]['reason'] or failed[0]['state']}")
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


def _run_publish(db: Any, card: dict[str, Any], parent: str) -> tuple[str | None, str, str | None]:
    """The project as an 11ty static site, through the one site export (`source.job.publish`); again rewrites it.
    Stopped (#5609), it ends before its next page and the site is left unfinished."""
    from fichero_server.export_service import export_eleventy_site

    export_eleventy_site(db, card["folder"], overwrite=True, package_path=_library(db),
                         stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):
        return None, "cancelled", "Stopped by you"
    return None, "done", None


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.execution.cancellation import clear_cancellation

    job_id = jobs.job_id_for(db, KIND, subject)
    try:
        return _run(db, job_id)
    finally:
        clear_cancellation(job_id)


#: Why the steps after a stopped one do not run (#5609).
STOPPED_BEFORE = "the run was stopped before this step"


def _run(db: Any, job_id: str) -> dict[str, Any]:
    from fichero_server.recipes.start import count_pages  # noqa: F401  (the same material Start counts)

    row = jobs.read_job(db, job_id)
    # Said at once: working out each step's pages can take a while on a big project (#5610, #5606).
    jobs.save_detail(db, job_id, row["detail"] or "{}", reason="Getting ready: working out which pages each step needs")
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
        if _stop_asked(job_id):  # Stop on the run's row: no step after the stopped one runs (#5609)
            step.update(state="not run", why=STOPPED_BEFORE)
            continue
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
        if documents and _reads_page_images(card.get("job")):
            # A recording is not a page: the steps that read page images leave it out and say so, instead of
            # failing the step on a file they can never read (2026-10-10, found in the Dev Embedded app).
            recordings = _recordings(db, documents)
            if recordings:
                documents = [d for d in documents if d not in recordings]
                step["recordings_left_out"] = len(recordings)
        kinds: dict[str, str] = {}
        if card.get("job") in _NOT_ON_BLANK_VERSOS and documents:
            # The pages sorted by kind (#5578); blank ones, the backs of leaves as their images show or a page a
            # person called blank, are not lined or read (#5579).
            from fichero_server.recipes import sorting

            kinds = sorting.kinds(db, documents, list(card.get("readers") or {}))
            blank = [d for d in documents if kinds.get(d) == sorting.BLANK]
            if blank:
                documents = [d for d in documents if kinds.get(d) != sorting.BLANK]
                step["blank_versos"] = len(blank)
            if card.get("readers"):
                step["kinds"] = dict(sorted(Counter(kinds.get(d) or "unsorted" for d in documents).items()))
        if not documents:
            step.update(state="done", child_id=None, why="already done on every page")
            continue
        step["state"] = "running"
        jobs.save_detail(db, job_id, json.dumps(detail),
                         reason=jobs.STOPPING if _stop_asked(job_id) else f"Running step {named}")
        if card["card"] == "workflow" and card.get("readers"):
            child, state, why = _run_by_reader(db, card, documents, kinds, job_id, step)
        elif card["card"] == "workflow":
            child, state, why = _run_workflow(db, card, documents, job_id)
        elif card["card"] == "check":
            child, state, why = _run_check(db, card, documents, job_id, started_by)
        elif card["card"] == "find-documents":
            child, state, why = _run_find_documents(db, card, documents, job_id, started_by)
        elif card["card"] == "entries":
            child, state, why = _run_entries(db, card, documents, job_id, step)
        elif card["card"] == "prepare":
            child, state, why = _run_prepare(db, documents, job_id, step)
        elif card["card"] == "regions":
            child, state, why = _run_regions(db, card, documents, job_id, step)
        elif card["card"] == "publish":
            child, state, why = _run_publish(db, card, job_id)
        elif card["card"] == "embed":
            child, state, why = _run_embed(db, documents, job_id, started_by)
        else:
            child, state, why = _run_export(db, card, documents)
        if state != "done" and _stop_asked(job_id):  # it was stopped with the run (#5609)
            state, why = "cancelled", "Stopped by you"
        step.update(state=state, child_id=child, why=why)
        if card["card"] == "workflow" and state == "done":
            # The step changed these pages' work: every kept export rewrites them (#5485).
            from fichero_server import kept_export

            kept_export.queue_rewrites(db, documents)
        if state not in ("done", "cancelled"):
            problems.append(f"step {named} {state}: {why or 'no reason given'}")
    finished = sum(1 for s in steps if s["state"] == "done")
    if _stop_asked(job_id):  # the row ends cancelled, saying who stopped it and what was done (#5609)
        words = f"Stopped by you; {finished} of {len(steps)} steps done" + (
            f" ({'; '.join(problems)})" if problems else "")
        jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
        raise jobs.JobCancelled(words)
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
    for card, step in zip(detail.get("runs", []), steps):
        step["job"] = card.get("job")  # what the stage does, by its last job (a reading, names, dates)
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
            "steps": steps, "skipped": detail.get("skipped", []), "refusals": detail.get("refusals", []),
            "started_by": row["started_by"]}


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
                           qos=set_utility_qos, name="Run the recipe",
                           cancel=request_cancel)


#: What a page image gives: a job that takes only these reads page images, so a recording is no input for it.
_FROM_A_PAGE_IMAGE = frozenset({"page_image", "lines", "line_readings", "regions", "signs"})


def _reads_page_images(job_id: str | None) -> bool:
    from fichero_server.recipes.jobs import get_job

    job = get_job(job_id or "")
    if job is None or not job.takes:
        return False
    return all(set(take.split("|")) <= _FROM_A_PAGE_IMAGE for take in job.takes)


def _recordings(db: Any, documents: list[str]) -> set[str]:
    from fichero_server.models import Document

    found = set()
    for doc_id in documents:
        doc = db.get(Document, doc_id)
        kind = str(getattr(getattr(doc, "file_type", None), "value", getattr(doc, "file_type", "")) or "")
        if kind in ("audio", "video"):
            found.add(doc_id)
    return found
