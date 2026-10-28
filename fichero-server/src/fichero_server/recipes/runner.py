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
* a **table** card (`extract-to-a-table`) asks the step's prototype's questions of each of its documents and entries
  among the pages, with the step's model, and lands the answers as their attributes, each citing its words
  (`recipes/table.py`, #5636);
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
import concurrent.futures
import contextlib
import contextvars
import json
import logging
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

from fichero_server.db import document_tree
from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowCancelled, WorkflowPaused
from fichero_server.recipes.assemble import PURPOSES, TOOL_PURPOSES

KIND = "run-a-recipe"
#: Purposes that run by themselves after Start (the "just do it" ones; `recipes/assemble.PURPOSES`).
AUTOMATIC_PURPOSES = frozenset(PURPOSES) - TOOL_PURPOSES
_CHECK_POLL_SECONDS = 0.5
#: Cards that line or read pages: a blank verso is left out of them (#5579).
_NOT_ON_BLANK_VERSOS = frozenset({"find-lines", "read-a-line", "read-a-page"})
#: Below this reader's certainty a page's names are noise (#5694: 741 people found in text read at ~70% CER).
#: ponytail: one bar for every reader; measure per reader (its certainty against checked lines) when one misleads.
NAMES_MIN_CONFIDENCE = 0.7
#: The steps that find names in a page's text.
_NAMES_JOBS = frozenset({"find-names-tag-words"})


def reading_confidence(db: Any, doc_id: str) -> float | None:
    """How sure the reader was of the page's lines: the mean of each line's newest machine certainty, a line a
    person read counting as sure. None when no reader gave one (a vision model's reading): not gated."""
    from fichero_server.models import ContentRepresentation

    newest: dict[str, Any] = {}
    for r in db.query(ContentRepresentation, document_id=doc_id):
        if r.segment_id and r.kind == "transcription" and not getattr(r, "retracted_at", None):
            if r.segment_id not in newest or r.created_at > newest[r.segment_id].created_at:
                newest[r.segment_id] = r
    sure = [1.0 if getattr(r.provenance_kind, "value", r.provenance_kind) == "human" else r.machine_confidence
            for r in newest.values()]
    sure = [c for c in sure if c is not None]
    if not sure:
        # A reader whose result became the page's pass (Kraken finding and reading the lines in one go) keeps its
        # certainty on the pass's lines, not on readings (#5704: the reading journey's unsure page went ungated).
        from fichero_server.llm.working_lines import working_lines

        found = working_lines(db, doc_id)
        sure = [s.confidence for s in (found.lines if found else []) if getattr(s, "confidence", None) is not None]
    return sum(sure) / len(sure) if sure else None


def reading_too_uncertain(db: Any, doc_id: str) -> bool:
    """The page's reading is below the bar a page's text is judged by (#5694 Names, #5675 Find the Documents);
    False when its reader gave no certainty."""
    sure = reading_confidence(db, doc_id)
    return sure is not None and sure < NAMES_MIN_CONFIDENCE


def too_uncertain_for_names(db: Any, documents: list[str]) -> list[dict[str, str]]:
    """The pages whose reading is too uncertain to find names in, each named with why (#5694)."""
    from fichero_server.models import Document

    out = []
    for doc_id in documents:
        sure = reading_confidence(db, doc_id)
        if sure is not None and sure < NAMES_MIN_CONFIDENCE:
            out.append({"page_id": doc_id, "page": getattr(db.get(Document, doc_id), "name", None) or doc_id,
                        "why": f"its reading is too uncertain to find names in (the reader was {sure:.0%} sure, "
                               f"below {NAMES_MIN_CONFIDENCE:.0%}); read it with a better reader first"})
    return out


def _library(db: Any) -> Path:
    return Path(db.path).parent


def _plan(db: Any) -> dict[str, Any]:
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.start import plan_start

    setup = read_project_setup(_library(db))
    answers = setup["answers"] or {}
    from fichero_server.recipes import places

    stays_local = not places.may_leave_to(answers, "cloud")
    # New material runs only what What runs by itself ticks; with Nothing runs automatically, nothing (#5478).
    return plan_start(setup["recipe"], stays_local=stays_local, automatic=answers.get("automatic"),
                      job_answers=answers.get("job_answers"), db=db)


def enqueue(db: Any, plan: dict[str, Any], *, documents: list[str] | None, started_by: str,
            redo: list[str] | None = None, folder_id: str | None = None) -> str:
    """Queue one run of the plan; `documents` None is all the project's material, or with `folder_id` that
    folder's (`source.recipe.folder-scoped-start`); `redo` names the steps to run again on pages that already have
    their output (`source.recipe.done-is-not-redone`). The downloads the plan found under way are kept on the run,
    so each step on one waits for it to land (`awaited`, #5660)."""
    awaited = [{"steps": d["steps"], "job_id": d["job_id"], "name": d.get("name") or d["model"]}
               for d in plan.get("downloads") or [] if d.get("downloading")]
    detail = {"runs": plan["runs"], "skipped": plan["skipped"], "documents": documents, "redo": list(redo or []),
              "folder_id": folder_id, "awaited": awaited,
              # Its name and page count in Activity (#5615), as they were when it was queued.
              "title": _recipe_title(db), "pages": _pages_counted(db, documents)}
    words = "Waiting to run the recipe" + (f" on {len(documents)} new pages" if documents is not None else
                                           " on one folder" if folder_id else "")
    return jobs.enqueue_remote(db, KIND, f"recipe:{uuid.uuid4()}", target="this-mac", detail=json.dumps(detail),
                               reason=words, started_by=started_by)


def _recipe_title(db: Any) -> str | None:
    from fichero_server.recipes.project import read_project_setup

    try:
        return (read_project_setup(_library(db))["recipe"] or {}).get("title") or None
    except Exception:  # noqa: BLE001 -- a run is queued without its title; its row is named without one
        return None


def _pages_counted(db: Any, documents: list[str] | None) -> int | None:
    from fichero_server.recipes.done import pages_for

    try:
        return len(pages_for(db, {}, documents))
    except Exception:  # noqa: BLE001 -- the row is named without its count
        return None


def name_and_pages(db: Any, job_id: str) -> tuple[str, int | None]:
    """A recipe run's name in Activity, "Run the recipe: Transcribe + names", and the pages it runs over (#5615):
    never the kind's id ("run-a-recipe"). A run queued before these were kept is named by the project's recipe, its
    pages counted now."""
    detail = json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}")
    title = detail.get("title") or _recipe_title(db)
    pages = detail.get("pages")
    if pages is None:
        pages = _pages_counted(db, detail.get("documents"))
    name = jobs.kind_name(KIND)
    return (f"{name}: {title}" if title else name), pages


def material_arrived(db: Any, document_ids: list[str]) -> str | None:
    """An import brought new material: after Start, a "just do it" project runs its recipe over it alone;
    before Start, or on a "tools" purpose, nothing runs (`source.onboard.*`). One whose recipe cannot run
    leaves a failed row saying why (`refused`, #5575). Returns the row's job id, or None when nothing was asked."""
    if not document_ids:
        return None
    if _why_no_recipe_on_add(db) is not None:
        return None
    plan = _plan(db)
    if not plan["refusals"] and plan["runs"]:
        from fichero_server.recipes.start import queue_downloads

        try:
            # As Start does (#5664): the run fetches the models it needs, and its steps on them wait.
            queue_downloads(db, plan, started_by="import")
        except ValueError as exc:  # a model that cannot be downloaded at all
            plan["refusals"] = [str(exc)]
    if plan["refusals"] or not plan["runs"]:
        return refused(db, plan, list(document_ids))
    return enqueue(db, plan, documents=list(document_ids), started_by="import")


def stages_the_run_takes(db: Any, run_id: str | None) -> set[str]:
    """The import-time work a queued recipe run does itself, once after reading (ruling 5, #6186): the per-page embed when
    the run has a Search stage, the names draft when it has a names stage. None for no run or a refused one (a failed row)."""
    from fichero_server.importers.derivatives import EMBED_KIND, NLP_KIND

    row = jobs.read_job(db, run_id) if run_id else None
    if row is None or row["state"] in ("failed", "cancelled"):
        return set()
    cards = json.loads(row["detail"] or "{}").get("runs") or []
    return ({EMBED_KIND} if any(c.get("card") == "embed" for c in cards) else set()) | (
        {NLP_KIND} if any(c.get("job") == "find-names-tag-words" for c in cards) else set())


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
        else:  # ruling 5 (#6186): the run's Search and names stages take the import's embed and names draft
            once = "Search and names run once at the end of the recipe's reading, not on each page added"
            for item in on_add:
                if (item["job"] == EMBED_KIND and any(r.get("card") == "embed" for r in plan["runs"])) or (
                        item["job"] == NLP_KIND and any(r.get("job") == "find-names-tag-words" for r in plan["runs"])):
                    item["runs"], item["why"] = False, once
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


def _run_workflow(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                  adopt: str | None = None) -> tuple[str, str, str | None]:
    """A workflow card through the real runner: (child id, state, why). `adopt`: the run this recipe parked on, taken up again
    instead of starting a new one (nothing is read twice, #5933)."""
    if adopt:
        return _adopt_step_run(adopt, parent)
    from fichero_server.api.routes.workflow.chains import (
        _load_step_workflow,
        _record_step_run_accepted,
        _run_step_workflow,
        _validate_step_workflow,
    )
    from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
    from fichero_server.execution.runner import (
        LIVE_CHECK_LOCK,
        WorkflowEventHub,
        _set_workflow_state,
        live_run_reading,
        reader_key,
    )

    from fichero_server.workflows.default_workflows import resolve_shipped_workflow

    thread_id = f"thread-{uuid.uuid4().hex[:12]}"
    # By the shipped preset's stable id; a project seeded before ids were stable holds it under another (#5497).
    workflow = _load_step_workflow(db, card["workflow_id"]) or resolve_shipped_workflow(
        db, card["workflow_id"], card["workflow"])
    if workflow is None:
        return thread_id, "failed", (f"the shipped workflow {card['workflow']!r} is in neither this project nor "
                                     "the shipped defaults")
    if card.get("lenses"):
        # The review's lenses turned on in setup (#5723): a pass whose lens is off is not run.
        from fichero_server.recipes.review_profiles import keep_lenses

        workflow = workflow.model_copy(deep=True)
        workflow.nodes, workflow.edges = keep_lenses(workflow.nodes, workflow.edges, card["lenses"])
    if card.get("review_instructions"):
        from fichero_server.recipes.review_profiles import with_instructions

        workflow = workflow.model_copy(deep=True)
        from pathlib import Path

        from fichero_server.recipes.project import read_project_setup

        workflow.nodes = with_instructions(workflow.nodes, card["review_instructions"],
                                           read_project_setup(Path(db.path).parent)["answers"])
    if card.get("tool_config"):
        # The step's settings from setup's answers (which kinds of names, #5478), on this run's copy only.
        workflow = workflow.model_copy(deep=True)
        for node in workflow.nodes:
            node["config"] = {**(node.get("config") or {}), **(card["tool_config"].get(node.get("tool")) or {})}
    request = ExecuteWorkflowRequest(workflow_id=workflow.id, inputs={"selected_doc_ids": documents},
                                     thread_id=thread_id, provider_override=card["provider_override"],
                                     model_override=card["model_override"], skip_cache=True)
    # Pages a live run of the same reader already reads are joined, not read beside (#5848): the step reads the rest
    # itself and then waits for that run, so a resume and a Retry, or two Starts, never read a page twice.
    reader = reader_key(workflow, request)
    with LIVE_CHECK_LOCK:  # decided under the lock, never waited under it: start_run takes it on the loop
        live = live_run_reading(str(db.path), workflow.id, documents, reader)
        covered = bool(live) and live[1] >= set(documents)
        if live and not covered:
            documents = [d for d in documents if d not in live[1]]
            request.inputs = {"selected_doc_ids": documents}
        if not covered:
            # Registered up front, as a chain's steps are, so the run's stream and status know the thread.
            _set_workflow_state(thread_id, {"workflow_id": workflow.id, "workflow_name": workflow.name,
                                            "db_path": str(db.path), "documents": [str(d) for d in documents],
                                            "reader": reader, "status": "accepted", "events": WorkflowEventHub(),
                                            "error": None, "final_state": None})
    if covered:
        return _join_live_run(live[0], parent)
    try:
        _validate_step_workflow(workflow, request, db)
    except Exception as exc:  # noqa: BLE001 -- the run's own preflight says why; the recipe records it
        return thread_id, "failed", str(getattr(exc, "detail", exc))

    async def go() -> dict[str, Any] | None:
        from fichero_server.execution.cancellation import link_child, unlink_child

        await _record_step_run_accepted(db, thread_id, workflow, request)
        jobs.set_parent(db, thread_id, parent)
        link_child(parent, thread_id)  # a tool's own between-pages check sees the recipe's Stop at once
        try:
            return await _until_ended(db, thread_id, asyncio.ensure_future(
                _run_step_workflow(thread_id=thread_id, workflow=workflow, request=request, db=db)), parent)
        finally:
            unlink_child(thread_id)

    dead = asyncio.run(go())
    _closed_stops_the_recipe(db, thread_id, parent)
    if dead is not None:  # the run's row ended and the run never came back: its row says how
        return thread_id, ("done" if dead["state"] == "done" else "failed"), dead["reason"] or dead["state"]
    status, error = _settled_outcome(thread_id, parent)
    error = None if status == "completed" else outcome_why(status, error)
    if status == "completed" and live:  # the pages the live run reads: this step is done when that run is
        joined = _join_live_run(live[0], parent)
        if joined[1] != "done":
            return joined
    return thread_id, ("done" if status == "completed" else "failed"), error


class ParkedOnStepRun(Exception):
    """A step's run is paused: the recipe parks (a stored row that leaves the recipes lane) until that run is resumed, instead of
    sleeping in its slot, which would hold every other recipe back (the lane is one wide; ## 656)."""

    def __init__(self, thread_id: str):
        super().__init__(thread_id)
        self.thread_id = thread_id


def _settled_outcome(thread_id: str, parent: str) -> tuple[str, str | None]:
    """A step run's outcome. A run paused (by the recipe's Pause, or by a person on that run's own row) is not failed and the
    recipe does not move on from it: it parks (`ParkedOnStepRun`) and is taken up again when the run is resumed (#5933). A Stop
    on the recipe returns the paused outcome for the caller's Stop handling."""
    from fichero_server.api.routes.workflow.chains import _step_run_outcome

    status, error = _step_run_outcome(thread_id)
    if status == "paused" and not _stop_asked(parent):
        raise ParkedOnStepRun(thread_id)
    return status, error


def _adopt_step_run(thread_id: str, parent: str) -> tuple[str, str, str | None]:
    """The run this recipe parked on, taken up again: still paused, it parks again; live, it is waited for; ended, its outcome is
    the step's. (child id, state, why)."""
    from fichero_server.api.routes.workflow.chains import _step_run_outcome
    from fichero_server.execution.runner import LIVE_RUN_STATUSES

    while _step_run_outcome(thread_id)[0] in LIVE_RUN_STATUSES and not _stop_asked(parent):
        time.sleep(_CHECK_POLL_SECONDS)
    status, error = _settled_outcome(thread_id, parent)
    return thread_id, ("done" if status == "completed" else "failed"), (None if status == "completed" else outcome_why(status, error))


def _park(db: Any, job_id: str, detail: dict[str, Any], card: dict[str, Any], thread_id: str) -> None:
    """Park the recipe on a paused step run: remember the run, go back to waiting (off the lane), come back soon to look again."""
    detail["awaiting"] = {"card": card.get("id"), "child": thread_id}
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Paused with its run")
    jobs.come_back_after(db, job_id, PAUSED_LOOK_AGAIN_SECONDS)
    raise jobs.JobDeferred("Paused with its run")


def _wait_out_a_pause(db: Any, job_id: str) -> None:
    """The recipe's Pause lands between steps: the recipe goes back to waiting (off the lane) and the next step does not start until
    Resume; a Stop ends it."""
    from fichero_server.execution.cancellation import pause_requested

    if pause_requested(job_id) and not _stop_asked(job_id):
        jobs.come_back_after(db, job_id, PAUSED_LOOK_AGAIN_SECONDS)
        raise jobs.JobDeferred("Paused between steps")


def _resume_step_run(db: Any, thread_id: str, recipe_id: str | None = None) -> None:
    """Resume a step's paused run from its checkpoint on the engine's background loop, without waiting for it (the PUT answers at
    once). A resume that fails is said on the recipe's row, never left silent."""
    from fichero_server.api.routes.workflow_execution import core
    from fichero_server.execution.runner import on_background_loop

    from fichero_server.db.manager import db_manager

    key = jobs._key(db)

    def said(done: Any) -> None:
        exc = done.exception()
        if exc is not None and recipe_id is not None:
            try:
                # This runs on the engine's loop thread, not the request's: say it through the store's own open connection.
                document_tree.set_job_reason(db_manager.open_database(key) or db, recipe_id, f"Could not resume its step: {exc}")
            except Exception:  # noqa: BLE001 -- the row is what we can say it on; the log has the rest
                logger.exception("could not say the failed resume of %s on %s", thread_id, recipe_id)
            logger.warning("recipe %s: resuming its step run %s failed: %s", recipe_id, thread_id, exc)

    on_background_loop(core.resume_workflow(thread_id, None, db=db)).add_done_callback(said)


def _awaited_child(db: Any, job_id: str) -> str | None:
    """The step run a parked recipe is waiting on, if it is parked on one."""
    row = jobs.read_job(db, job_id)
    return ((json.loads(row["detail"] or "{}")).get("awaiting") or {}).get("child")


def pause_recipe(db: Any, job_id: str, paused: bool) -> str:
    """Pause or Resume on a recipe run's row (`activity.recipe-run.pause-reaches-its-step`, #5933). Held for lack of this, Pause on a
    running recipe answered `running` and nothing happened. A running recipe is asked to pause at its next step and its step's run
    in flight is paused; the row says so. Resume lets it go on and resumes that run from its checkpoint. A waiting or paused row is
    the plain pause of a stored job. Returns the row's state."""
    from fichero_server.execution.cancellation import clear_pause, pause_requested, request_pause

    state = jobs._job_row(db, job_id)[1]
    if paused:
        if state != "running":
            return jobs.pause_stored(db, job_id, True, state)
        request_pause(job_id)
        child = jobs.running_child(db, job_id)
        if child is not None:
            try:
                jobs.pause_job(db, child, True)
            except (ValueError, KeyError):  # a step that is not a run has nothing to pause here; the recipe's flag holds it
                pass
        jobs.say_pausing(db, job_id)
        return "running"
    if not pause_requested(job_id):
        awaited = _awaited_child(db, job_id)
        try:
            awaited_state = jobs._job_row(db, awaited)[1] if awaited is not None else None
        except KeyError:  # the job row is gone; the run may not be (pay-twice risk): the retake adopts it from its own state
            from fichero_server.execution.runner import _get_workflow_state

            run = _get_workflow_state(awaited)
            if run is not None:  # keep 'awaiting': adopting reads the run's own outcome, nothing is read again
                if run.get("status") == "paused":
                    _resume_step_run(db, awaited, job_id)
                document_tree.release_waiting_job(db, job_id, clear_reason=True)
                jobs.wake_lane(db)
                return jobs._job_row(db, job_id)[1]
            row = jobs.read_job(db, job_id)
            detail = json.loads(row["detail"] or "{}")
            detail.pop("awaiting", None)
            jobs.save_detail(db, job_id, json.dumps(detail), reason="Its step run is gone; the recipe starts that step again")
            document_tree.release_waiting_job(db, job_id)
            jobs.wake_lane(db)
            return jobs.pause_stored(db, job_id, False, state)
        if awaited_state == "paused":
            # A person paused the step's run itself: Resume on the recipe resumes that run (the recipe adopts it when it is taken up).
            clear_pause(awaited)
            _resume_step_run(db, awaited, job_id)
            document_tree.release_waiting_job(db, job_id, clear_reason=True)
            jobs.wake_lane(db)
            return jobs._job_row(db, job_id)[1]
        return jobs.pause_stored(db, job_id, False, state)
    clear_pause(job_id)
    child = jobs.running_child(db, job_id)
    if child is not None:
        clear_pause(child)  # still winding down to its pause: let it go on
        if jobs._job_row(db, child)[1] == "paused":
            _resume_step_run(db, child, job_id)
    document_tree.clear_job_reason_if(db, job_id, (jobs.PAUSING, "Paused with its run"))
    document_tree.release_waiting_job(db, job_id)  # a parked recipe is taken up now
    jobs.wake_lane(db)
    return jobs._job_row(db, job_id)[1]


def outcome_why(status: str, error: str | None) -> str:
    """Why a step's run did not complete, in words: its own error, else how it ended. A run paused by the engine's
    shutdown (live runs are paused at their checkpoint) says so; never blank, so a failure always says why."""
    if error and str(error).strip():
        return str(error).strip()
    if status == "paused":
        return "the engine stopped while this was running; try it again"
    if status in ("cancelled", "stopped"):
        return "it was stopped before it finished"
    return f"the run ended {status or 'without a result'} and gave no reason"


def _join_live_run(live: str, parent: str) -> tuple[str, str, str | None]:
    """Wait for the run already reading these pages and report its outcome as this step's (#5848); the why names it
    by its workflow. A run that is paused is not waited on: it is not live (`LIVE_RUN_STATUSES`), so the wait ends."""
    from fichero_server.api.routes.workflow.chains import _step_run_outcome
    from fichero_server.execution.runner import LIVE_RUN_STATUSES, _get_workflow_state

    while _step_run_outcome(live)[0] in LIVE_RUN_STATUSES:
        if _stop_asked(parent):
            break
        time.sleep(_CHECK_POLL_SECONDS)
    status, error = _step_run_outcome(live)
    if status == "paused" and not _stop_asked(parent):
        raise ParkedOnStepRun(live)  # the joined run was paused: the recipe parks and frees its slot (#5933)
    name = (_get_workflow_state(live) or {}).get("workflow_name") or "the same step"
    if status == "completed":
        return live, "done", f"joined the run of {name} already reading these pages"
    return live, "failed", error or f"the run of {name} already reading these pages ended {status}"


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
        child = jobs.running_child(db, job_id)  # a recipe parked on a paused step run stops that run too
        jobs.cancel_waiting(db, job_id)
        if child is not None:
            jobs.pass_stopper(job_id, child)
            try:
                jobs.cancel_job(db, child)
            except (ValueError, KeyError):
                logger.info("recipe %s stopped; its step run %s was not stopped by it", job_id, child)
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
    jobs.pass_stopper(parent, child)
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
                    ["model_override"], "child_id": child, "state": state, "why": why,
                    **({k: card["readers"][kind].get(k) for k in ("sentence", "card_id", "note", "runs_on")} if kind else {})})
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


def _run_catalogue(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                   step: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """The Catalogue stage (`catalogue.folder-description-fields`, #6087): a description on each folder above the run's
    pages, deepest first, redone only where what it covers changed. The step's account (`catalogue`) counts them."""
    from fichero_server.llm import LLMConfig
    from fichero_server.recipes.catalogue_step import describe_folders

    step["catalogue"] = account = describe_folders(
        db, documents, LLMConfig(provider=card["provider"], model=card["model"]), run_id=parent,
        stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):
        return None, "cancelled", "Stopped by you"
    if account["failed"]:
        return None, "failed", "; ".join(account["failed"])
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
    """Each page image's regions found by the step's model (Kraken's segmenter, or a YOLO model) and saved as its
    regions (`prep.regions.open-default`, `prep.yolo.regions-card`); the step's account (`regions_found`) says how
    many pages and regions, and pages with no image."""
    from fichero_server.recipes.regions import find_regions

    step["regions_found"] = find_regions(db, documents, parent, card["model"], stop=lambda: _stop_asked(parent),
                                         provider=card.get("provider") or "yolo",
                                         say=lambda words: jobs.say(db, parent, words))
    if _stop_asked(parent):
        return None, "cancelled", "Stopped by you"
    return None, "done", None


def _run_table(db: Any, card: dict[str, Any], documents: list[str], parent: str,
               step: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """Extract to a table (`structured.extract.step-in-a-recipe`, #5636): the step's prototype's questions asked of
    each of its documents and entries among the pages, with the step's model, the answers landing as their
    attributes (`recipes/table.py`). The step's account (`table`) counts the units, the values, the statuses, the
    refusals and the values kept because a person (or no run) set them; `table_refusals` names each refused answer
    and why."""
    from fichero_server.recipes import table

    try:
        account = table.extract(db, documents, prototype=card["prototype"], provider=card["provider"],
                                model=card["model"], run_id=parent, step=",".join(card["steps"]),
                                stop=lambda: _stop_asked(parent))
    except Exception as exc:  # noqa: BLE001 -- an unknown prototype or one with no fields, said on the step
        return None, "failed", f"the table was not filled: {exc}"
    refusals, errors = account.pop("refusals"), account.pop("errors")
    step["table"] = {"prototype": card["prototype"], **account}
    if refusals:
        step["table_refusals"] = refusals
    if _stop_asked(parent):
        return None, "cancelled", "Stopped by you"
    if errors:
        return None, "failed", f"{len(errors)} of {account['asked']} units were not answered: {'; '.join(errors[:3])}"
    return None, "done", None


def _run_at_scale(db: Any, card: dict[str, Any], documents: list[str], parent: str,
                  started_by: str) -> tuple[str | None, str, str | None]:
    """A read the plan placed on the project's cluster or on Hugging Face Jobs (`source.recipe.placement-by-scale`,
    `source.recipe.step-runs-on-huggingface`): sent there as one read-at-scale run under this step, and waited on as any
    child; a place that refuses fails the step by name. The person's yes is read now, not when the plan was made: pages
    may leave only while the project says so, the app allows the place, and (Hugging Face) the monthly cap is above $0."""
    from fichero_server.models.compute_requests import ReadAtScaleRequest
    from fichero_server.recipes.answers import spend_cap
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.remote_read import job as read_job

    from fichero_server.recipes import places

    on_hf = card["target"] == read_job.TARGET
    answers = read_project_setup(_library(db))["answers"]
    where = "Hugging Face" if on_hf else f"the cluster {card['target']}"
    if not places.may_leave_to(answers, "huggingface" if on_hf else "acenet"):
        return None, "failed", f"pages may not leave this Mac; this step was placed on {where}"
    if on_hf:
        from fichero_server.recipes.train_offers import spend_this_month

        cap = spend_cap(answers)
        if cap <= 0:
            return None, "failed", "this step was placed on Hugging Face, but the monthly spend cap is $0: set a cap in setup first"
        spent = spend_this_month(db, cap=cap)["spent_at_most_usd"]
        if spent >= cap:  # the cap is a ceiling on what is already sent, not only a switch (#6173)
            return None, "failed", (f"this step was placed on Hugging Face, but this month's spend (at most ${spent:.2f}) "
                                    f"has reached the ${cap:.2f} cap")
    if (out := read_job.out_under(db, parent)) is not None:  # resumed: the read already sent is waited on, never sent again
        return _wait(db, out, parent)
    try:
        child = read_job.start(db, ReadAtScaleRequest(scope_ids=documents, reader="kraken", card=card["model_override"],
                                                      target=card["target"], pages_may_leave=True,
                                                      parent_job_id=parent), started_by=started_by,
                               stage=tuple(card.get("stage") or ("read",)))["job_id"]  # a card queued before stages: the read alone
    except Exception as exc:  # noqa: BLE001 -- no key, no sign-in, a reader that cannot leave: said, never read here
        return None, "failed", f"could not send the read to {where}: {exc}"
    return _wait(db, child, parent)


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
    """Search: the embed job (`make-a-vector`, the one that follows every correction) queued for the pages in batches, as
    children of the recipe's row, and waited for (#5574, #5954)."""
    from fichero_server.actions.page_text_cache import queue_reembed_batches

    # Pages in batches of 64, one job each (one forward pass and one append per batch, `runtime.embed.once-per-text-version`
    # #5954); a page already embedded from its current text is left alone inside the job.
    children = queue_reembed_batches(db, documents, started_by=started_by)
    for child in children:
        jobs.set_parent(db, child, parent)
    while True:
        if _stop_asked(parent):  # stopped (#5609): the run stops waiting; a page's embed job, which a correction
            return None, "cancelled", "Stopped by you"  # may share, is left to finish (it is cheap and kept)
        rows = [jobs.read_job(db, child) for child in children]
        if all(r["state"] in ("done", "failed", "cancelled") for r in rows):
            failed = [r for r in rows if r["state"] != "done"]
            if not failed:
                search_embedded(parent, documents)
                return None, "done", None
            return None, "failed", (f"{len(failed)} of {len(rows)} batches of pages were not embedded: "
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


logger = logging.getLogger(__name__)


def could_not_start(card: dict[str, Any], exc: Exception) -> str:
    """One plain line for a step whose work raised before it could report an end (#5684): what the person can do,
    never the technical text, which goes to the log. A native library that would not load (a dlopen, a missing
    dylib) is said as such."""
    from fichero_server.recipes.jobs import get_job

    known = get_job(card.get("job") or "")
    topic = known.topic if known else None
    title = topic.title if topic else ", ".join(card["steps"])
    text = str(exc)
    if isinstance(exc, (ImportError, OSError)) and any(w in text for w in ("dlopen", "Library not loaded", ".dylib",
                                                                             ".so")):
        return f"{title} could not start: a library it needs would not load on this Mac. Restart Fichero, or reinstall."
    first = (text.strip().splitlines() or [type(exc).__name__])[0]
    return f"{title} could not start: {first[:160]}"


def run(db: Any, subject: str) -> dict[str, Any]:
    from fichero_server.execution.cancellation import clear_cancellation

    job_id = jobs.job_id_for(db, KIND, subject)
    try:
        return _run(db, job_id)
    finally:
        clear_cancellation(job_id)


#: Why the steps after a stopped one do not run (#5609).
STOPPED_BEFORE = "the run was stopped before this step"


def _await_downloads(db: Any, job_id: str, detail: dict[str, Any], card: dict[str, Any]) -> str | None:
    """Wait for the downloads this card's steps need that were under way when Start was pressed (`awaited`, #5660):
    the step runs once each has landed. Why it cannot run, in words, when one ended without landing or the run was
    stopped while waiting; None to run it. A download that has landed is noted, so later batches do not wait."""
    for entry in detail.get("awaited") or []:
        if entry.get("landed") or not set(entry["steps"]) & set(card["steps"]):
            continue
        said = False
        while True:
            _closed_stops_the_recipe(db, parent=job_id)
            if _stop_asked(job_id):
                return STOPPED_BEFORE
            row = jobs.read_job(db, entry["job_id"])
            if row is None or row["state"] == "done":  # a row cleared away is a download that finished
                entry["landed"] = True
                break
            if row["state"] in ("failed", "cancelled"):
                # `source.recipe.download-failure-waits`: the other steps run; this one says so and how to go on.
                return (f"Model download failed: {entry['name']} did not download ({row['reason'] or row['state']}). "
                        "Retry it in Activity, or choose the step's next candidate in Set Up")
            if not said:
                jobs.save_detail(db, job_id, json.dumps(detail),
                                 reason=f"Waiting for {entry['name']} to download for step {', '.join(card['steps'])}")
                said = True
            time.sleep(_CHECK_POLL_SECONDS)
    return None


#: ponytail: the most pages a batch hands a step at once (`source.recipe.batch-at-archive-scale`, rule 9 of
#: `compute/jobs-and-fine-tuning.md`): a batch is one folder, or this many of its pages, whichever is smaller. A
#: photograph cut into pages counts once (its pages go with it), so a batch can hold a few more pages than this.
#: Rule 9's "about 500"; change it with a measurement, not a guess.
BATCH_PAGE_LIMIT = 500

#: id -> (parent id, doc type, file type) for every live document.
_Tree = dict[str, tuple[str | None, str, str]]


def _tree(db: Any) -> _Tree:
    """Every live document, read once a run (one query, not one a page)."""
    from fichero_server.db.document_tree import live_tree

    return {doc_id: tuple(node) for doc_id, node in live_tree(db).items()}


def folder_scope(db: Any, folder_id: str, tree: _Tree | None = None) -> set[str]:
    """The folder and every live document under it, at any depth (`source.recipe.folder-scoped-start`). LookupError
    when it is not a live document of this project."""
    tree = _tree(db) if tree is None else tree
    if folder_id not in tree:
        raise LookupError(f"{folder_id} is not a folder in this project")
    children: dict[str, list[str]] = {}
    for doc_id, (parent, _kind, _type) in tree.items():
        if parent is not None:
            children.setdefault(parent, []).append(doc_id)
    scope, todo = {folder_id}, [folder_id]
    while todo:
        for child in children.get(todo.pop(), ()):
            if child not in scope:
                scope.add(child)
                todo.append(child)
    return scope


def _is_photograph(tree: _Tree, doc_id: str) -> bool:
    _parent, kind, file_type = tree.get(doc_id, (None, "", ""))
    return kind == "file" and file_type == "image"


def _units(db: Any, brought: list[str] | None, folder_id: str | None, tree: _Tree) -> list[str]:
    """What the run is batched by, in the material's order: each page, except a page cut from a photograph, which
    is its photograph (cut before or during the run, a photograph is one unit, so the batches are the same on a
    resume). Only the folder's, given one."""
    from fichero_server.recipes.done import pages_for

    within = folder_scope(db, folder_id, tree) if folder_id else None
    units: list[str] = []
    seen: set[str] = set()
    for page in pages_for(db, {}, brought):
        if page not in tree:
            continue
        parent, kind, _type = tree[page]
        unit = parent if kind == "chunk" and parent is not None and _is_photograph(tree, parent) else page
        if unit in seen or (within is not None and unit not in within):
            continue
        seen.add(unit)
        units.append(unit)
    return units


def _folder_of(tree: _Tree, doc_id: str) -> str | None:
    """A page's nearest folder; None for a page in no folder."""
    seen = {doc_id}
    parent = tree.get(doc_id, (None, "", ""))[0]
    while parent is not None and parent in tree and parent not in seen:
        if tree[parent][1] == "folder":
            return parent
        seen.add(parent)
        parent = tree[parent][0]
    return None


def _batches(tree: _Tree, units: list[str], limit: int) -> list[dict[str, Any]]:
    """The run's batches (`source.recipe.batch-at-archive-scale`): by folder, in the material's order, each at most
    `limit` units; `last` marks a folder's last batch. No material is one empty batch, so every step still says
    what it found."""
    by_folder: dict[str | None, list[str]] = {}
    for unit in units:
        by_folder.setdefault(_folder_of(tree, unit), []).append(unit)
    out = [{"folder": folder, "units": these[i:i + limit], "last": i + limit >= len(these)}
           for folder, these in by_folder.items() for i in range(0, len(these), limit)]
    return out or [{"folder": None, "units": [], "last": True}]


def _card_pages(db: Any, card: dict[str, Any], units: list[str], tree: _Tree) -> list[str]:
    """The pages a card runs on in one batch: for a split, the batch's photographs; for any other card, its pages,
    a photograph cut into pages (before the run or earlier in it) giving its pages. One query a batch."""
    photographs = [u for u in units if _is_photograph(tree, u)]
    if card.get("job") == "split-pages":
        return photographs
    from fichero_server.db.document_tree import live_chunks_of

    cut = live_chunks_of(db, photographs)
    return [page for unit in units for page in (cut.get(unit) or [unit])]


#: How bad a step's end on a batch is: over the batches, the worst end is the step's.
_WORSE = {"done": 0, "partial": 1, "cancelled": 2, "not run": 3, "failed": 4}


#: How soon a recipe run that its Pause withdrew looks at its pause again (it comes back waiting, not done).
PAUSED_LOOK_AGAIN_SECONDS = 5.0


def _settle(step: dict[str, Any], state: str, child: str | None, why: str | None) -> None:
    """A step's end on one batch, added to its end over the run: a worse end before stands. A step not run on a
    batch names no job (its state is its own, not an earlier batch's job's, `status`)."""
    if step["state"] in _WORSE and _WORSE[step["state"]] > _WORSE.get(state, 0):
        return
    kept = None if state == "not run" else step.get("child_id")
    step.update(state=state, child_id=child if child is not None else kept, why=why)


def _add(step: dict[str, Any], scratch: dict[str, Any]) -> None:
    """A batch's account of a step (pages done, left out, by kind, what it made), added to the step's."""
    for key, value in scratch.items():
        before = step.get(key)
        if isinstance(value, list):
            step[key] = (before or []) + value
        elif isinstance(value, dict):
            merged = dict(before or {})
            for k, v in value.items():
                both = isinstance(v, int) and isinstance(merged.get(k, 0), int)
                merged[k] = merged.get(k, 0) + v if both else v
            step[key] = merged
        elif isinstance(value, int) and isinstance(before, int):
            step[key] = before + value
        else:
            step[key] = value


def _folders_words(detail: dict[str, Any]) -> str:
    """`activity.run.progress-per-folder`: "3 of 800 folders done"."""
    total = detail.get("folders_total") or 0
    return f"{detail.get('folders_done', 0)} of {total} {'folder' if total == 1 else 'folders'} done"


def _served_steps(cards: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """(index, store id) of the cards the engine's served model runs: the id the server serves (`model_to_serve`: `omlx/` stripped,
    the default names mapped, the canonical id), which is what the idle stop compares; a card naming no model runs the default."""
    from fichero_server.llm.local_model_choice import model_to_serve

    return [(i, model_to_serve(c.get("model_override"))) for i, c in enumerate(cards)
            if (c.get("provider_override") or "").lower() == "omlx"]


def _let_go_after_the_last_served_step(job_id: str, cards: list[dict[str, Any]], index: int) -> None:
    """The hold ends with the batch's last step that uses the served model, not at the batch's end: the steps after it
    (embedding, the tail) have no use for it, and the lane may need the memory."""
    served = _served_steps(cards)
    module = sys.modules.get("fichero_server.api.routes.ai.local_inference")
    if module is not None and served and index > served[-1][0]:
        module.let_go_served_models(job_id)


@contextlib.contextmanager
def _holding_the_served_model(job_id: str, cards: list[dict[str, Any]]):
    """The engine's served model is not idle-stopped while a batch runs: spaCy's steps sit between two of its users
    (`source.recipe.step-major-per-batch`). Let go at the batch's end; nothing is held if no server was ever started."""
    module = sys.modules.get("fichero_server.api.routes.ai.local_inference")
    if module is not None:
        module.hold_served_models(job_id, {m for _, m in _served_steps(cards)})
    try:
        yield
    finally:
        if module is not None:
            module.let_go_served_models(job_id)


def _run(db: Any, job_id: str) -> dict[str, Any]:
    try:
        return _run_the_plan(db, job_id)
    finally:  # stopped, failed, paused or done: a page saved before Search got to it is embedded after all (#6126)
        try:
            end_search_watch(db, job_id, (jobs.read_job(db, job_id) or {}).get("started_by") or "owner")
        except Exception:  # noqa: BLE001 -- never replace the run's own result or error with a queueing failure
            logger.exception("run %s: the embeds left to Search could not be queued", job_id)


def _run_the_plan(db: Any, job_id: str) -> dict[str, Any]:
    from fichero_server.execution.cancellation import pause_requested

    if pause_requested(job_id):
        # Paused with its run: wait, and write nothing else. Re-picked every PAUSED_LOOK_AGAIN_SECONDS, a paused run that
        # did its work first submitted a page row each time for the lane to withdraw (437: ~17k rows overnight).
        jobs.come_back_after(db, job_id, PAUSED_LOOK_AGAIN_SECONDS)
        raise jobs.JobDeferred("Paused with its run")
    row = jobs.read_job(db, job_id)
    # Said at once: working out each step's pages can take a while on a big project (#5610, #5606).
    jobs.save_detail(db, job_id, row["detail"] or "{}", reason="Getting ready: working out which pages each step needs")
    detail = json.loads(row["detail"] or "{}")
    started_by = row["started_by"] or "owner"
    cards = detail["runs"]
    if not (detail.get("steps") and "batches_done" in detail):  # a resumed run keeps its checkpoint
        detail["steps"] = [{"steps": card["steps"], "card": card["card"], "state": "waiting", "child_id": None}
                           for card in cards]
        detail["batches_done"], detail["batch_states"] = 0, [None] * len(cards)
    steps = detail["steps"]
    _read_old_shapes(steps)
    tree = _tree(db)
    batches = _batches(tree, _units(db, detail.get("documents"), detail.get("folder_id"), tree), BATCH_PAGE_LIMIT)
    if any(card["card"] == "embed" for card in cards):  # Search is in the plan: it embeds these pages once (#6126)
        units = {u for batch in batches for u in batch["units"]}  # a photograph's cut pages are saved under it
        start_search_watch(job_id, units | {doc for doc, (parent, _k, _t) in tree.items() if parent in units})
    detail["batches_total"] = len(batches)
    detail["folders_total"] = len({b["folder"] for b in batches if b["units"]})
    detail["folders_done"] = sum(1 for b in batches[:detail["batches_done"]] if b["last"] and b["units"])
    problems: list[str] = []
    halted: str | None = None
    for number, batch in enumerate(batches):
        if number < detail["batches_done"]:  # finished before an interruption (`source.recipe.batch-checkpoint`)
            continue
        with _holding_the_served_model(job_id, cards):  # one MLX load per batch, kept through spaCy's steps
            problems = _run_batch(db, job_id, detail, batch, tree, started_by, final=number == len(batches) - 1)
        if _stop_asked(job_id):  # a person's Stop ends the run after this batch; a failure does not (#5540)
            break
        detail["batches_done"], detail["batch_states"] = number + 1, [None] * len(cards)
        detail["folders_done"] += 1 if batch["last"] and batch["units"] else 0
        halted = _halted(cards, steps)
        jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Running the recipe: {_folders_words(detail)}")
        if halted:  # a step that did nothing on batch after batch: its model is broken, not a page (#5540)
            break
    finished = sum(1 for s in steps if s["state"] in ("done", "partial"))
    total = detail["folders_total"]
    folders = f"; {_folders_words(detail)}" if total else ""
    if _stop_asked(job_id):  # the row ends cancelled, saying who stopped it and what was done (#5609)
        words = f"{jobs.stopped_by(job_id)}; {finished} of {len(steps)} steps done{folders}" + (
            f" ({'; '.join(problems)})" if problems else "")
        jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
        raise jobs.JobCancelled(words)
    over = f" over {total} {'folder' if total == 1 else 'folders'}" if total else ""
    failures = _failures_words(db, cards, steps, total)
    if halted:
        words = f"Stopped: {halted}{folders}"
    elif failures:
        words = f"Done with failures: {failures}{folders}"
    else:
        words = f"Done: {len(steps)} steps run{over}" + (f", {len(detail['skipped'])} skipped (see why)"
                                                         if detail["skipped"] else "")
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words)
    if halted or failures:
        raise RuntimeError(words)
    return {"steps": steps}


#: ponytail: a step that does none of a batch's pages on this many batches in a row stops the run (#5540,
#: provisional): its model is missing or broken, and carrying on would only fail every folder after. A guess at
#: "more than bad luck"; change it with a ruling.
OUTRIGHT_IN_A_ROW = 3


def _note_batch(step: dict[str, Any], batch: dict[str, Any], state: str, child: str | None, why: str | None) -> None:
    """A batch a step failed on, was not run on, or failed some pages of, kept on the step (`failed_batches`):
    the run carries on past it (#5540), and its end, its summary and Read Again name it."""
    step.setdefault("failed_batches", []).append(
        {"folder": batch["folder"], "state": state, "child_id": child, "why": why})


def _did_no_page(db: Any, card: dict[str, Any], child: str | None, scratch: dict[str, Any]
                 ) -> tuple[bool, int, list[Any]]:
    """(whether the step did none of the batch's pages, the pages it failed, those pages with why) from its workflow
    runs' own accounts (#5555); a run with no account never reached a page. A step that is not a workflow cannot say
    which pages it did, so it did none."""
    if card["card"] != "workflow":
        return True, 0, []
    from fichero_server.workflows import run_account as accounts

    children = [r["child_id"] for r in scratch.get("readers") or [] if r.get("child_id")] or [child]
    done = failed = 0
    lost: list[Any] = []
    for thread_id in children:
        account = asyncio.run(accounts.run_account(db, thread_id)) if thread_id else None
        if account is not None:
            done, failed = done + account.pages_done, failed + account.pages_failed
            lost += account.failures
    return done == 0, failed, lost


def _partial_words(done_pages: int, lost: list[Any], failed: int) -> str:
    """"2 of 5 pages done; 3 failed: IMG_001: Kraken could not read its lines; ...": a step that lost pages says which
    and why (`activity.run.step-honest-about-lost-pages`); the first few named, the rest counted."""
    named = "; ".join(f"{f.page}: {f.reason}" for f in lost[:3])
    more = f"; and {failed - 3} more" if failed > 3 else ""
    return f"{done_pages} of {done_pages + failed} pages done; {failed} failed: {named}{more}"


def _halted(cards: list[dict[str, Any]], steps: list[dict[str, Any]]) -> str | None:
    """Why the run stops: a step that failed outright on `OUTRIGHT_IN_A_ROW` batches in a row; None to carry on."""
    for card, step in zip(cards, steps):
        if step.get("outright_in_a_row", 0) >= OUTRIGHT_IN_A_ROW:
            why = next((b["why"] for b in reversed(step.get("failed_batches") or []) if b["state"] == "failed"), None)
            return (f"step {', '.join(card['steps'])} failed on {step['outright_in_a_row']} folders in a row "
                    f"without doing a page ({why or 'no reason given'})")
    return None


def _failures_words(db: Any, cards: list[dict[str, Any]], steps: list[dict[str, Any]], total: int) -> str:
    """"step lines, read failed on 1 of 4 folders (B: why)": each cause said once, with every step it failed or
    did not run ("2 steps (correct; translate) did not run: why"), never once a step (seen 2026-10-11: one download
    failure said eight times). With no folders counted, no count ("1 of 0 folders" was said)."""
    from fichero_server.models import Document

    def name(folder: str | None) -> str:
        doc = db.get(Document, folder) if folder else None
        return doc.name if doc is not None else "pages in no folder"

    # (verb, why) -> the steps, and the folders, it was said of; in the order first met.
    causes: dict[tuple[str, str], dict[str, dict]] = {}
    for card, step in zip(cards, steps):
        named = ", ".join(card["steps"])
        for state, verb in (("failed", "failed"), ("partial", "lost pages"), ("not run", "did not run")):
            for b in step.get("failed_batches") or []:
                if b["state"] != state:
                    continue
                cause = causes.setdefault((verb, b["why"] or "no reason given"), {"steps": {}, "folders": {}})
                cause["steps"][named] = None
                cause["folders"][b["folder"]] = None
    out = []
    for (verb, why), cause in causes.items():
        named = list(cause["steps"])
        head = f"step {named[0]}" if len(named) == 1 else f"{len(named)} steps ({'; '.join(named)})"
        if not total:
            out.append(f"{head} {verb}: {why}")
            continue
        folders = list(cause["folders"])
        shown = ", ".join(name(f) for f in folders[:3]) + (f" and {len(folders) - 3} more" if len(folders) > 3 else "")
        out.append(f"{head} {verb} on {len(folders)} of {total} {'folder' if total == 1 else 'folders'} "
                   f"({shown}: {why})")
    return "; ".join(out)


#: The reading jobs that may run side by side: a local reader (Kraken) and a hosted one use different resources, so the
#: run takes about as long as the slower (owner, #6127: Kraken, then the cloud reader, 16 min + the cloud's time).
_BESIDE = frozenset({"read-a-line", "read-a-page"})


def _beside(cards: list[dict[str, Any]], states: list[Any], detail: dict[str, Any], index: int) -> int | None:
    """The index of the step after this one when it can run at the same time (a local reading step and a hosted one that
    neither takes what the other gives, and no download to wait for), else None. Only the next step: ponytail, a
    wider reach when a recipe has two such pairs."""
    after = index + 1
    if after >= len(cards) or states[after] is not None:
        return None
    one, other = cards[index], cards[after]
    if one.get("job") not in _BESIDE or other.get("job") not in _BESIDE or one["job"] == other["job"]:
        return None
    if "takes" not in one or "takes" not in other:  # a card queued before cards declared their inputs waits on all before
        return None
    if str(one.get("runs_on", "")).startswith("cloud") == str(other.get("runs_on", "")).startswith("cloud"):
        return None
    if set(one.get("gives") or ()) & set(other["takes"]) or set(other.get("gives") or ()) & set(one["takes"]):
        return None
    if any(set(e["steps"]) & set(other["steps"]) and not e.get("landed") for e in detail.get("awaited") or []):
        return None
    return after


class _Beside(NamedTuple):
    documents: list[str]
    scratch: dict[str, Any]
    kinds: dict[str, str]
    future: concurrent.futures.Future


def _asked_again(card: dict[str, Any], redo: set[str]) -> dict[str, Any]:
    """A reading card asked to read again: every line, not just the unread ones (`source.recipe.read-resumes-per-line`)."""
    if card.get("job") != "read-a-line" or not redo.intersection(card["steps"]):
        return card
    return {**card, "tool_config": {**(card.get("tool_config") or {}),
                                    "transcribe": {**((card.get("tool_config") or {}).get("transcribe") or {}),
                                                   "read_all_lines": True}}}


def _text_is_the_hosted_readers(card: dict[str, Any]) -> dict[str, Any]:
    """The local reader's card for a read that runs beside a hosted one: it writes its lines' readings but not the page's
    text, which is the model's whichever finishes first (`source.recipe.kraken-lines-cloud-reads`)."""
    if str(card.get("runs_on", "")).startswith("cloud"):
        return card
    tool_config = card.get("tool_config") or {}
    return {**card, "tool_config": {**tool_config, "transcribe": {**(tool_config.get("transcribe") or {}),
                                                                  "update_page_content": False,
                                                                  "force_ocr": False}}}


def _start_beside(db: Any, job_id: str, detail: dict[str, Any], batch: dict[str, Any], tree: _Tree, started_by: str,
                  index: int) -> _Beside | None:
    """Step `index` started on its own thread while the step before it runs; its end is taken when its turn comes."""
    card, step = detail["runs"][index], detail["steps"][index]
    documents, scratch, kinds = _step_pages(db, card, step, batch, tree, detail)
    card = _text_is_the_hosted_readers(_asked_again(card, set(detail.get("redo") or [])))
    if not documents or _stop_asked(job_id):
        return None
    pool = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="recipe-beside")
    future = pool.submit(contextvars.copy_context().run, _run_card, db, card, documents, kinds, job_id, scratch, started_by)
    pool.shutdown(wait=False)
    return _Beside(documents, scratch, kinds, future)


def _in_the_cards_folders(db: Any, card: dict[str, Any], documents: list[str], tree: _Tree) -> list[str]:
    """A run for one folder's reader keeps that folder's pages, and every run of the step leaves out the pages of the
    other folders that have a reader of their own (the innermost folder wins; `source.try.use-this-scope`, #6135)."""
    def scope_of(folder: str) -> set[str]:
        try:
            return folder_scope(db, folder, tree)
        except LookupError:  # the folder was trashed after Start planned: it holds no pages, and nothing else breaks
            return set()

    others = {f: scope_of(f) for f in card.get("exclude_folders") or []}
    inside = scope_of(card["folder_id"]) if card.get("folder_id") else None
    return [d for d in documents
            if (inside is None or d in inside)
            and not any(d in scope and (inside is None or scope < inside) for scope in others.values())]


def _step_pages(db: Any, card: dict[str, Any], step: dict[str, Any], batch: dict[str, Any], tree: _Tree,
                detail: dict[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, str]]:
    """The pages a step works on in this batch, as it is about to run: (pages, its scratch notes, the pages' kinds)."""
    from fichero_server.recipes.done import split_done

    redo = set(detail.get("redo") or [])
    scratch: dict[str, Any] = {}
    # The pages are worked out now, so pages a split made earlier in this batch are among them.
    documents = _card_pages(db, card, batch["units"], tree)
    if card.get("folder_id") or card.get("exclude_folders"):
        documents = _in_the_cards_folders(db, card, documents, tree)
    if card["card"] == "catalogue":  # last, over every page the run covered; a folder already described is left
        from fichero_server.recipes.done import pages_for

        documents = pages_for(db, card, detail.get("documents"))
    elif not redo.intersection(card["steps"]):
        documents, scratch["already_done"] = split_done(db, card, documents, own=set(step.get("ran_on") or []))
    if documents and _reads_page_images(card.get("job")):
        # A recording is not a page: the steps that read page images leave it out and say so, instead of
        # failing the step on a file they can never read (2026-10-10, found in the Dev Embedded app).
        recordings = _recordings(db, documents)
        if recordings:
            documents = [d for d in documents if d not in recordings]
            scratch["recordings_left_out"] = len(recordings)
    kinds: dict[str, str] = {}
    if card.get("job") in _NOT_ON_BLANK_VERSOS and documents:
        # The pages sorted by kind (#5578); blank ones, the backs of leaves as their images show or a page a
        # person called blank, are not lined or read (#5579).
        from fichero_server.recipes import sorting

        kinds = sorting.kinds(db, documents, list(card.get("readers") or {}))
        blank = [d for d in documents if kinds.get(d) == sorting.BLANK]
        if blank:
            documents = [d for d in documents if kinds.get(d) != sorting.BLANK]
            scratch["blank_versos"] = len(blank)
            # Each page left out, named with why (#5691): a count alone left "Read 91 of 92" unexplained.
            from fichero_server.models import Document as _Document

            def _why(doc: Any) -> str:
                attrs = getattr(doc, "attributes", None) or {}
                return sorting.PERSON_BLANK_WHY if attrs.get(sorting.SET_BY) == sorting.BY_PERSON else \
                    sorting.BLANK_WHY

            scratch["left_out"] = [{"page_id": d, "page": getattr(doc, "name", None) or d, "why": _why(doc)}
                                   for d in blank for doc in (db.get(_Document, d),)]
        if card.get("readers"):
            scratch["kinds"] = dict(sorted(Counter(kinds.get(d) or "unsorted" for d in documents).items()))
    if card.get("job") in _NAMES_JOBS and documents:
        uncertain = too_uncertain_for_names(db, documents)
        if uncertain:
            gone = {e["page_id"] for e in uncertain}
            documents = [d for d in documents if d not in gone]
            scratch["left_out"] = [*(scratch.get("left_out") or []), *uncertain]
    return documents, scratch, kinds


def _run_batch(db: Any, job_id: str, detail: dict[str, Any], batch: dict[str, Any], tree: _Tree,
               started_by: str, *, final: bool) -> list[str]:
    """`_run_batch_steps`, and whatever ended it, a step still running beside another is waited for: it is never left
    running unseen, for a resume to start again (a page read twice)."""
    ahead: dict[int, _Beside | None] = {}  # a step already running beside the one before it
    try:
        return _run_batch_steps(db, job_id, detail, batch, tree, started_by, ahead, final=final)
    finally:
        for beside in ahead.values():
            if beside is not None:
                concurrent.futures.wait([beside.future])


def _run_batch_steps(db: Any, job_id: str, detail: dict[str, Any], batch: dict[str, Any], tree: _Tree,
                     started_by: str, ahead: dict[int, _Beside | None], *, final: bool) -> list[str]:
    """Every step on one batch, in order (`source.recipe.batch-at-archive-scale`); each step's end on it is saved
    as it ends, so a resume runs only the steps still to do on it (`source.recipe.batch-checkpoint`). The problems."""
    from fichero_server.recipes.done import NOTES as done_notes

    cards, steps, states = detail["runs"], detail["steps"], detail["batch_states"]
    redo = set(detail.get("redo") or [])
    # This batch's own ends, for `_blocked`: a step waits on what an earlier step gave on these pages.
    here = [{"state": state or "waiting"} for state in states]
    problems: list[str] = []
    for index, (card, step) in enumerate(zip(cards, steps)):
        _let_go_after_the_last_served_step(job_id, cards, index)
        if states[index] is not None:  # done on this batch before an interruption
            continue
        named = ", ".join(card["steps"])
        # A step already running beside the one before it keeps the pages it started on: its pages are not worked out again
        # mid-flight (they would be counted done, or read twice), and its end is taken as it ended, Stop included.
        early = ahead.pop(index, None)
        if _stop_asked(job_id) and early is None:  # Stop on the run's row: no step after the stopped one runs (#5609)
            here[index]["state"] = "not run"
            _settle(step, "not run", None, STOPPED_BEFORE)
            continue
        blocked = _blocked(cards, here, index) or _await_downloads(db, job_id, detail, card)
        if blocked:
            here[index]["state"] = "not run"
            _settle(step, "not run", None, blocked)
            _note_batch(step, batch, "not run", None, blocked)
            problems.append(f"step {named} not run: {blocked}")
            continue
        if card["card"] in ("publish", "catalogue") and not final:  # written once, at the end, over the whole run
            continue
        if early is not None:
            documents, scratch, kinds = early.documents, early.scratch, early.kinds
        else:
            documents, scratch, kinds = _step_pages(db, card, step, batch, tree, detail)
        if not documents:
            _add(step, scratch)
            here[index]["state"] = states[index] = "done"
            if step["state"] == "waiting":
                step.update(state="done", child_id=None, why="already done on every page")
            jobs.save_detail(db, job_id, json.dumps(detail))
            continue
        if early is None:  # a step already running beside the one before it is not held back: it is running
            _wait_out_a_pause(db, job_id)  # Pause between steps holds the next step until Resume or Stop (#5933)
        # Running on this batch: its state is its own until this batch's job ends, not an earlier batch's job's.
        before, before_child = step["state"], step.get("child_id")
        step.update(state="running", child_id=None)
        jobs.save_detail(db, job_id, json.dumps(detail), reason=jobs.STOPPING if _stop_asked(job_id) else
                         f"Running step {named}: {_folders_words(detail)}")
        waiting_on = detail.get("awaiting") or {}
        adopt = waiting_on.get("child") if waiting_on.get("card") == card.get("id") else None
        done_notes.pop(job_id, None)
        if card.get("job") in PAGE_NOTED_JOBS:
            # Each page the step finishes is noted on the run's detail as it finishes (`done.page_finished`), saved at once.
            def _noted(key: str, step: dict[str, Any] = step) -> None:
                step.setdefault("ran_on", []).append(key)
                jobs.save_detail(db, job_id, json.dumps(detail))

            done_notes[job_id] = _noted
        card = _asked_again(card, redo)
        if early is None and not adopt and (after := _beside(cards, states, detail, index)) is not None:
            ahead[after] = _start_beside(db, job_id, detail, batch, tree, started_by, after)
            if ahead[after] is not None:
                card = _text_is_the_hosted_readers(card)
        try:
            if early is not None:  # it has been running beside the step before: its end is what this step ended with
                child, state, why = early.future.result()
            else:
                child, state, why = _run_card(db, card, documents, kinds, job_id, scratch, started_by, adopt)
            detail.pop("awaiting", None)
        except (jobs.JobCancelled, jobs.JobDeferred, jobs.JobOutOfReach):
            raise  # the queue's own: stopped, to come back later, out of reach
        except ParkedOnStepRun as parked:  # its step's run is paused: park, off the lane, until it is resumed (#5933)
            _park(db, job_id, detail, card, parked.thread_id)
        except WorkflowPaused as paused:  # a page waiting for the lane was withdrawn by the run's Pause (#5863, 434)
            # The run is not done: the row goes back to waiting and resumes from its checkpoint, after a pause's grace.
            jobs.come_back_after(db, job_id, PAUSED_LOOK_AGAIN_SECONDS)
            raise jobs.JobDeferred("Paused with its run") from paused
        except WorkflowCancelled:  # withdrawn by the run's Stop: stopped, not failed
            child, (state, why) = None, ("cancelled", "Stopped by you")
        except Exception as exc:  # noqa: BLE001 -- the step fails alone, said in one line; the rest still run (#5684)
            logger.exception("recipe step %s could not start", named)
            child, state, why = None, "failed", could_not_start(card, exc)
        done_notes.pop(job_id, None)
        if state != "done" and _stop_asked(job_id):  # it was stopped with the run (#5609)
            state, why = "cancelled", "Stopped by you"
        if state == "done" and card.get("job") in RAN_ON_JOBS:
            scratch["ran_on"] = list(documents)  # a page it looked at and found nothing on is done (#5706)
        _add(step, scratch)
        # An earlier batch's worse end stands (`_settle`).
        step.update(state=before if before != "running" else "waiting", child_id=before_child)
        _settle(step, state, child, why)
        if child is not None and all(b.get("child_id") != child for b in step.get("batch_jobs") or []):
            # each batch's job, kept in the checkpoint: the step is timed over all of them (#6215)
            step.setdefault("batch_jobs", []).append({"folder": batch["folder"], "child_id": child})
        here[index]["state"] = states[index] = state
        _after_the_step(db, card, step, batch, documents, state, child, why, scratch, problems, named)
        jobs.save_detail(db, job_id, json.dumps(detail))  # the step's end on this batch is a checkpoint
    return problems


def _run_card(db: Any, card: dict[str, Any], documents: list[str], kinds: dict[str, str], job_id: str,
              scratch: dict[str, Any], started_by: str, adopt: str | None = None) -> tuple[str | None, str, str | None]:
    """One step's work on a batch's pages, by its card: (its job, its end, why)."""
    if card.get("place") in ("cluster", "huggingface"):
        child, state, why = _run_at_scale(db, card, documents, job_id, started_by)
    elif card["card"] == "workflow" and card.get("readers"):
        child, state, why = _run_by_reader(db, card, documents, kinds, job_id, scratch)
    elif card["card"] == "workflow":
        child, state, why = _run_workflow(db, card, documents, job_id, adopt)
    elif card["card"] == "check":
        child, state, why = _run_check(db, card, documents, job_id, started_by)
    elif card["card"] == "find-documents":
        child, state, why = _run_find_documents(db, card, documents, job_id, started_by)
    elif card["card"] == "entries":
        child, state, why = _run_entries(db, card, documents, job_id, scratch)
    elif card["card"] == "catalogue":
        child, state, why = _run_catalogue(db, card, documents, job_id, scratch)
    elif card["card"] == "prepare":
        child, state, why = _run_prepare(db, documents, job_id, scratch)
    elif card["card"] == "leave-out":
        from fichero_server.recipes.leave_out import run_step

        child, state, why = run_step(db, documents, job_id, scratch, stop=lambda: _stop_asked(job_id))
    elif card["card"] == "regions":
        child, state, why = _run_regions(db, card, documents, job_id, scratch)
    elif card["card"] == "table":
        child, state, why = _run_table(db, card, documents, job_id, scratch)
    elif card["card"] == "publish":
        child, state, why = _run_publish(db, card, job_id)
    elif card["card"] == "embed":
        child, state, why = _run_embed(db, documents, job_id, started_by)
    else:
        child, state, why = _run_export(db, card, documents)
    return child, state, why


def _after_the_step(db: Any, card: dict[str, Any], step: dict[str, Any], batch: dict[str, Any], documents: list[str],
                    state: str, child: str | None, why: str | None, scratch: dict[str, Any], problems: list[str],
                    named: str) -> None:
    """What a step's end on a batch leaves: kept exports rewritten, its failed batches noted, the problem said."""
    if card["card"] == "workflow" and state == "done":
        # The step changed these pages' work: every kept export rewrites them (#5485).
        from fichero_server import kept_export

        kept_export.queue_rewrites(db, documents)
    if state == "done":  # under `here`, training starts by itself once the corrections reach the threshold (#5440)
        from fichero_server.recipes import train_offers

        try:
            train_offers.start_when_ready(db)
        except Exception as exc:  # noqa: BLE001 -- the step's own end stands whatever training does
            logger.exception("could not ask whether training is due after step %s", named)
            problems.append(f"training could not be checked after step {named}: {exc}")
    if state in ("done", "failed"):
        # The run carries on past a failed batch (#5540, provisional): the step's failed pages are kept on it,
        # and a step that did none of a batch's pages counts towards stopping the run (`_halted`).
        none_done, pages_failed, lost = _did_no_page(db, card, child, scratch)
        if state == "done" and card.get("job") == "read-a-line":
            # A page whose reader gave no text for every line, or most (`source.read.line-with-no-writing-is-read`),
            # is a lost page though its node succeeded: the step is partial and names it with the reason.
            from fichero_server.models import Document
            from fichero_server.recipes.done import failed_reads
            from fichero_server.workflows.run_account import PageFailure

            counted = {f.document_id for f in lost}
            for page, reason in failed_reads(db, documents, mark_blank=True):
                if page not in counted:
                    doc = db.get(Document, page)
                    lost.append(PageFailure(page=doc.name if doc else page, document_id=page, reason=reason))
                    pages_failed += 1
        if state == "done":
            step["pages_tried"] = step.get("pages_tried", 0) + len(documents)  # clean batches count too
        if state == "done" and pages_failed and step["state"] in ("done", "partial"):
            # Some pages were lost: the step is PARTIAL, never done, and says which and why. Every batch adds its own
            # pages to the step's list and counts, so a run over many folders reports all of them.
            step["state"] = "partial"
            step["failed_pages"] = [*(step.get("failed_pages") or []),
                                    *({"page": f.page, "reason": f.reason} for f in lost)]
            step["pages_lost"] = step.get("pages_lost", 0) + pages_failed
            from fichero_server.workflows.run_account import PageFailure

            step["why"] = why = _partial_words(
                max(0, step["pages_tried"] - step["pages_lost"]),
                [PageFailure(page=f["page"], reason=f["reason"]) for f in step["failed_pages"]], step["pages_lost"])
        outright = state == "failed" and none_done
        step["outright_in_a_row"] = step.get("outright_in_a_row", 0) + 1 if outright else 0
        if state == "failed" or pages_failed:
            # A batch that lost pages is noted "partial": the recipe's row then ends "Done with failures", never plain Done.
            _note_batch(step, batch, "partial" if state == "done" else state, child,
                        why or (f"{pages_failed} pages failed" if pages_failed else None))
    if state not in ("done", "cancelled") or step["state"] == "partial":
        problems.append(f"step {named} {step['state'] if step['state'] == 'partial' else state}: {why or 'no reason given'}")


def _blocked(cards: list[dict[str, Any]], steps: list[dict[str, Any]], index: int) -> str | None:
    """Why the card at `index` cannot run, or None (#5498): it needs a kind of thing that only earlier cards of
    this run give, and none of them finished. A kind no earlier card gives is the material's own (pages already
    read), so the card never waits for it. A card queued before cards declared their inputs waits on every card
    before it, as runs did then."""
    card = cards[index]
    before = list(zip(cards[:index], steps[:index]))
    if "takes" not in card:
        unfinished = [", ".join(c["steps"]) for c, s in before if s["state"] not in ("done", "partial")]
        return f"step {unfinished[0]} did not finish, and this step comes after it" if unfinished else None
    for take in card["takes"]:
        kinds = set(take.split("|"))
        givers = [(c, s) for c, s in before if kinds.intersection(c.get("gives") or ())]
        if givers and all(s["state"] not in ("done", "partial") for _c, s in givers):
            which = "; ".join(f"step {', '.join(c['steps'])} {s['state']}" for c, s in givers)
            needs = " or ".join(sorted(kinds)).replace("_", " ")
            return f"it needs {needs}, which no earlier step gave ({which})"
    return None


#: The steps whose output may leave no trace on a page (a page naming no one; a page clear enough to need no
#: preparing): the pages each ran on are kept on the run, so the next plan counts them done (#5706).
RAN_ON_JOBS = frozenset({"find-names-tag-words", "prepare-the-image"})
#: The steps that note each page as they finish it (`done.page_finished`): Leave Out and Names.
PAGE_NOTED_JOBS = frozenset({"find-names-tag-words", "leave-out"})
#: What a step is doing, by its last job, as the run's line says it (#5685).
_DOING = {"find-lines": "Finding the lines", "leave-out": "Leaving out what is not writing", "read-a-line": "Reading the lines", "read-a-page": "Reading the pages",
          "correct": "Correcting the readings", "find-names-tag-words": "Finding names",
          "find-statements": "Finding statements", "prepare-the-image": "Preparing the images",
          "find-regions": "Finding regions", "split-pages": "Splitting the pages"}
_READERS = {"kraken": "Kraken", "apple": "Apple Vision", "spacy": "spaCy"}


def doing_words(card: dict[str, Any]) -> str:
    """"Reading the lines with Kraken": the step's job and who does it, never its step ids (#5685)."""
    job = card.get("job") or ""
    said = _DOING.get(job, f"Running {job or 'a step'}")
    provider = (card.get("provider_override") or card.get("provider") or "").lower()
    model = card.get("model_override") or card.get("model")
    reader = _READERS.get(provider) or (str(model).rsplit("/", 1)[-1] if model and provider else None)
    return f"{said} with {reader}" if reader else said


#: The cards whose run makes a job of its own under the run: a step that makes none (regions, prepare, embed, table, publish)
#: must not borrow the run's newest unfinished row, which is a download or an earlier step winding down (Fable review #12).
_CARDS_WITH_A_JOB = ("workflow", "check", "find-documents", "entries")


def _read_old_shapes(steps: list[dict[str, Any]]) -> None:
    """A run saved while Leave Out wrote its account under `left_out` (the list of pages left out as blank, #5691) holds a dict
    there: read it as `leave_out`, as it is written now, and `left_out` as the empty list. `status` only reads (the stored row is
    never rewritten); a run carried on (`_run`) takes the new shape on its next checkpoint, before `_add` touches the key."""
    for step in steps:
        if isinstance(step.get("left_out"), dict):
            step["leave_out"], step["left_out"] = step["left_out"], []


#: Per running recipe run with a Search stage: the pages it covers, the pages Search has embedded, the pages whose own embed
#: was left to Search. In memory: the run executes in this process, and `end_search_watch` settles it whatever the end.
_search_lock = threading.Lock()
_search_watch: dict[str, dict[str, set[str]]] = {}


def start_search_watch(run_id: str, pages: set[str]) -> None:
    """From here until `end_search_watch`, a saved page of `pages` leaves its embed to the run's Search stage
    (`activity.run.stages-before-search-do-not-embed`, #6126)."""
    with _search_lock:
        _search_watch[run_id] = {"covers": set(pages), "embedded": set(), "left": set()}


def search_embedded(run_id: str, pages: list[str]) -> None:
    """Search embedded these pages: a later stage that saves one embeds it again at once."""
    with _search_lock:
        if run_id in _search_watch:
            _search_watch[run_id]["embedded"].update(pages)


def leave_embed_to_search(doc_id: str) -> bool:
    """True, and noted, when a running run covers the page and Search has not embedded it yet: its embed is Search's."""
    with _search_lock:
        for watch in _search_watch.values():
            if doc_id in watch["covers"] and doc_id not in watch["embedded"]:
                watch["left"].add(doc_id)
                return True
    return False


def end_search_watch(db: Any, run_id: str, started_by: str) -> None:
    """The run ended, however: the pages whose embed was left to Search and that Search never reached (the run stopped or
    failed first) are queued now; the embed job leaves a page already embedded from its text alone (#5954)."""
    from fichero_server.actions.page_text_cache import queue_reembed_batches

    with _search_lock:
        watch = _search_watch.pop(run_id, None)
    missed = sorted(watch["left"] - watch["embedded"]) if watch else []
    if missed:
        queue_reembed_batches(db, missed, started_by=started_by)


def status(db: Any, job_id: str) -> dict[str, Any]:
    """A recipe run: its state and each card's, read from the card's own job (the row Activity shows) once it
    has one, so this and Activity are one account (#5498). A run still waiting says what it waits for. Read as
    committed: a poll under a run's held write answers with what it has (#6178)."""
    from fichero_server.db import read_committed

    return read_committed(db, _status, db, job_id)


def _status(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no recipe run {job_id}")
    detail = json.loads(row["detail"] or "{}")
    steps = detail.get("steps") or [{"steps": c["steps"], "card": c["card"], "state": "waiting", "child_id": None}
                                    for c in detail.get("runs", [])]
    _read_old_shapes(steps)
    for card, step in zip(detail.get("runs", []), steps):
        step["job"] = card.get("job")  # what the stage does, by its last job (a reading, names, dates)
        step["doing"] = doing_words(card)
        step["note"] = card.get("note")  # Start's count of what was already done, kept on the run (#6091)
    for step in steps:
        if (step["state"] == "running" and not step.get("child_id") and row["state"] == "running"
                and step.get("card") in _CARDS_WITH_A_JOB):
            # The step learns its job's id only when the job returns: while it runs, its job is the run's
            # newest job not yet ended, so the status points at it (#5654).
            step["child_id"] = jobs.running_child(db, job_id)
        child = jobs.read_job(db, step["child_id"]) if step.get("child_id") else None
        if child is not None:
            step["state"] = child["state"]
            if child["state"] in ("failed", "cancelled") and not step.get("why"):
                step["why"] = child["reason"]
    if row["state"] in ("done", "failed", "cancelled"):
        # The run has ended: a step it left waiting or running did not run, or stopped with it (#5615); never
        # "running" under a failed run (the engine stopped mid-step, and the run was set aside).
        ended = row["reason"] or row["state"]
        for step in steps:
            if step["state"] == "waiting":
                step.update(state="not run", why=f"the run ended before this step: {ended}")
            elif step["state"] == "running":
                step.update(state="not run", why=f"stopped when the run ended, before this step finished: {ended}")
    reason = row["reason"]
    if row["state"] == "waiting":
        ahead = [r["id"] for r in jobs.find_jobs(db, kinds=[KIND], states=["running"]) if r["id"] != job_id]
        if ahead:
            reason = f"Waiting for the recipe run {ahead[0]} to finish: recipe runs go one at a time"
    return {"job_id": job_id, "state": row["state"], "reason": reason, "documents": detail.get("documents"),
            "steps": steps, "awaited": detail.get("awaited") or [], "skipped": detail.get("skipped", []), "refusals": detail.get("refusals", []),
            "started_by": row["started_by"], "folder_id": detail.get("folder_id"),
            # `activity.run.progress-per-folder`: written by the run as it goes; absent before it starts.
            "folders_done": detail.get("folders_done"), "folders_total": detail.get("folders_total")}


def started_plan(db: Any, job_id: str) -> dict[str, Any]:
    """What a run was started with: its cards and the steps it skipped, as it holds them."""
    row = jobs.read_job(db, job_id)
    detail = json.loads((row or {}).get("detail") or "{}")
    return {"runs": detail.get("runs", []), "skipped": detail.get("skipped", []), "redo": detail.get("redo") or []}


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
    """Every recipe run of the project, newest first, read as committed (#6178)."""
    from fichero_server.db import read_committed

    return read_committed(db, lambda: [status(db, row["id"]) for row in jobs.find_jobs(db, kinds=[KIND])])


def register_job_kinds() -> None:
    from fichero_server.core.background_compute import set_utility_qos

    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="recipes",
                           qos=set_utility_qos, name="Run the recipe",
                           cancel=request_cancel, pause=pause_recipe)


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
