"""A run's account: one record of how a run went, read by its status and by Activity alike (#5555, #5498).

Activity showed a ten-page run as "running, total 0" while the run's status counted its pages: the two read
different records (Activity the run's saved timeline, the status the checkpoint). Both now read this one
account, built from the run's record (state, why, started, `run_usage`), its checkpoint (each page's result
in each fanned-out step) and its pages' rows in the job table (what a page is waiting for):

* pages done, failed and left, and each failure's reason, page by page;
* what the run is waiting for, when a page waits (memory, the lane);
* the estimate of the time left, from this run's own pace;
* the engine's and the model servers' peak memory (#5537), live while it runs;
* interrupted, when the engine stopped, or its project was closed, before the run finished
  (`mark_interrupted_runs`, `closing_runs`);
* the offer at the end: "Read the 3 pages that failed" (or "... not done" after an interruption), one
  action (`read_again`) that runs the same workflow, with the same model, over those pages only.

A page counts as done when every fanned-out step that has started has done it (and every step that read all
its pages in one call, from that step's per-page results, #5654), and as failed when any step
failed it (a page a step skipped because the step before failed it is that one failure, not two).
"""
from __future__ import annotations

import asyncio

from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel, Field, PrivateAttr

from fichero_server.core.timeutil import ensure_utc, utc_now
from fichero_server.workflows.run_progress import MAX_FAILURES_LISTED, item_error, results_by_step

#: How an interrupted run's reason starts; `account_state` reads a run whose reason starts so as interrupted.
INTERRUPTED_PREFIX = "Interrupted: the engine stopped"
#: A recipe's step run cut off by the engine's stop: the recipe run, taken up again, reads its pages not done itself, so the
#: step run offers no second run (`recipes-run.journey.resume-after-crash`, #5357).
RECIPE_CARRIES_ON = "its recipe run carries on from its checkpoint"
#: How a run's record and rows read when the engine stopped under it and its checkpoint holds it for the person's Resume
#: (owner 2026-11-21: interrupted runs resume from the launch alert; `held_at_open`).
HELD_PREFIX = "Paused: the engine stopped"
#: The rest of a held run's words: what its Resume does.
HELD_RESUMES = "Resume carries on from its last finished page"
#: How a run's reason starts when its project was closed while it ran (#5608).
CLOSED_PREFIX = "Interrupted: the project was closed"
#: The words the older open-time sweep wrote (`workflows/activity_store._STALE_RUN_ERROR`).
_LEGACY_INTERRUPTED_PREFIX = "Run interrupted"


class PageFailure(BaseModel):
    """One page the run could not do, and why."""

    page: str = Field(description="The page's file name.")
    document_id: str | None = None
    reason: str
    retried: bool = Field(False, description="It failed for a passing cause, was read once more, and failed again.")


class RunOffer(BaseModel):
    """What the run offers at its end: read the pages it did not do, as one action."""

    action: str = Field("read-again", description="POST /api/workflow-execution/threads/{thread_id}/read-again")
    pages: int
    label: str = Field(description='"Read the 3 pages that failed", or "Read the 4 pages not done"')


class RunAccount(BaseModel):
    """How a run went, page by page (#5555): what its status and Activity both show."""

    state: str = Field(description="running, waiting, paused, done, failed, cancelled or interrupted")
    pages_total: int = 0
    pages_done: int = 0
    pages_failed: int = 0
    pages_left: int = 0
    pages_done_in_order: int = Field(0, description=(
        "The first N pages in sidebar order that are finished (read or failed): a page finished ahead counts when the "
        "gap before it closes, so progress reads in order (recipes-run.order.done-in-order-shown, #6186)."))
    failures: list[PageFailure] = Field(default_factory=list,
                                        description=f"The first {MAX_FAILURES_LISTED} failed pages, with why.")
    retried: int = Field(0, description="Pages read once more after a passing cause (a model loading, memory).")
    waiting_reason: str | None = Field(None, description="What a page of the run is waiting for, in words.")
    reason: str | None = Field(None, description="Why the run failed, stopped or was interrupted.")
    interrupted: bool = False
    estimate_seconds_left: float | None = Field(None, description="At this run's own pace so far; null "
                                                "until a page is done or when nothing is left.")
    # Physical FOOTPRINT (Activity Monitor's Memory): resident + compressed + swapped pages, so it can exceed the Mac's
    # RAM when the Mac swapped, and is larger than the RSS a sampler reads (#5758).
    engine_peak_memory_bytes: int | None = None
    model_server_peak_memory_bytes: int | None = None
    offer: RunOffer | None = None
    _not_done_ids: list[str] = PrivateAttr(default_factory=list)

    @property
    def not_done_ids(self) -> list[str]:
        """The pages (document ids) the offer reads again."""
        return list(self._not_done_ids)


_STATES = {"accepted": "waiting", "running": "running", "paused": "paused", "completed": "done",
           "failed": "failed", "cancelled": "cancelled", "stopped": "cancelled", "error": "failed"}


def account_state(status: str | None, reason: str | None) -> str:
    state = _STATES.get((status or "").lower(), status or "running")
    if state == "failed" and reason and reason.startswith((INTERRUPTED_PREFIX, CLOSED_PREFIX, _LEGACY_INTERRUPTED_PREFIX)):
        return "interrupted"
    return state


def _source_documents(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The documents the run fanned out over, in fan-out order (index i is file i)."""
    files = state.get("files")
    outputs = state.get("outputs")
    if not isinstance(outputs, dict):
        return []
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        docs = output.get("documents")
        if isinstance(docs, list) and docs and (not isinstance(files, list) or output.get("files") == files):
            return [d if isinstance(d, dict) else {} for d in docs]
    return []


def _one_call_steps(state: dict[str, Any], fanned: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The per-page results of each step that read every page in one call, not fanned out (#5654): its
    output's `results`, one per file, in file order, each with its error. A fanned-out step's aggregate
    (in `parallel_results` already) is not counted twice."""
    outputs = state.get("outputs")
    if not isinstance(outputs, dict):
        return {}
    files = state.get("files")
    documents = _source_documents(state)
    found: dict[str, list[dict[str, Any]]] = {}
    for node, output in outputs.items():
        results = output.get("results") if isinstance(output, dict) else None
        if (str(node) in fanned or "success_count" in output or not isinstance(results, list) or not results
                or not all(isinstance(r, dict) and r.get("file") for r in results)
                or (isinstance(files, list) and len(results) != len(files))):
            continue
        found[str(node)] = [
            {"index": i, "file": r["file"], "error": r.get("error"),
             "document_id": (documents[i].get("id") if i < len(documents) else None)}
            for i, r in enumerate(results)]
    return found


def _stopped_pages(state: dict[str, Any] | None) -> int:
    """Pages a person stopped alone: counted from the cancelled results themselves, never as total - done - failed (a page a step
    skips by design, or a step total above the files, would read as stopped)."""
    state = state if isinstance(state, dict) else {}
    steps = results_by_step(state, ())
    steps.update(_one_call_steps(state, steps))
    return len({item.get("index", item.get("file")) for items in steps.values() for item in items if item.get("cancelled")})


def partial_words(state: dict[str, Any] | None) -> str | None:
    """"Partial: N of M pages read (...)" for a run that finished with some pages failed or stopped, else None. The run's row
    stays `done` and the reason carries the word, until a real partial state exists (#5937)."""
    account = build_account(status="completed", reason=None, state=state)
    stopped = _stopped_pages(state)
    if not (account.pages_failed or stopped):
        return None
    lost = [f"{n} {word}" for n, word in ((account.pages_failed, "failed"), (stopped, "stopped")) if n]
    return f"Partial: {account.pages_done} of {account.pages_total} pages read ({', '.join(lost)})"


def build_account(*, status: str | None, reason: str | None, state: dict[str, Any] | None,
                  pending_writes: Iterable[Any] = (), started_at: datetime | None = None,
                  run_usage: dict[str, Any] | None = None, live_peaks: dict[str, int] | None = None,
                  waiting_reason: str | None = None, scope_ids: list[str] | None = None,
                  now: datetime | None = None) -> RunAccount:
    """The account from what the run recorded. Pure: every input is passed in."""
    state = state if isinstance(state, dict) else {}
    steps = results_by_step(state, pending_writes)
    steps.update(_one_call_steps(state, steps))
    pages: dict[Any, dict[str, Any]] = {}
    for node, items in steps.items():
        last: dict[Any, dict[str, Any]] = {}
        for item in items:  # a page read twice in one step: its last result counts
            last[item.get("index", item.get("file"))] = item
        for key, item in last.items():
            page = pages.setdefault(key, {"file": item.get("file"), "document_id": item.get("document_id"),
                                          "ok": set(), "error": None, "retried": False})
            page["retried"] = page["retried"] or bool(item.get("retried"))
            if item.get("cancelled"):
                continue
            error = item_error(item)
            if error:
                if page["error"] is None or (not item.get("upstream_failed") and page.get("upstream")):
                    page["error"], page["upstream"] = error, bool(item.get("upstream_failed"))
            else:
                page["ok"].add(node)
    done = [k for k, p in pages.items() if p["error"] is None and len(p["ok"]) == len(steps)]
    failed = [k for k, p in pages.items() if p["error"] is not None]
    files = state.get("files")
    totals = [len(files) if isinstance(files, list) else 0, len(pages)]
    totals += [i["total"] for items in steps.values() for i in items if isinstance(i.get("total"), int)]
    total = max(totals)
    if not total and scope_ids:  # stopped before the run reached its pages
        total = len(scope_ids)
    run_state = account_state(status, reason)
    if not pages and run_state == "done":
        # A run whose steps read every page in one call and say nothing page by page (Find Names, Work Out Dates):
        # done is every page it was given, never "0 of 92" after 1,193 names (#5706).
        done = list(range(total))
    left = max(0, total - len(done) - len(failed))
    position = {f: i for i, f in enumerate(files)} if isinstance(files, list) else {}
    settled = {k if isinstance(k, int) else position.get(k) for k in [*done, *failed]}  # a fan-out index, or a file
    in_order = next((i for i in range(total) if i not in settled), total)

    account = RunAccount(
        state=run_state, pages_total=total, pages_done=len(done), pages_failed=len(failed), pages_left=left,
        pages_done_in_order=in_order, failures=[PageFailure(page=str(p["file"] or "?").rsplit("/", 1)[-1], document_id=p["document_id"],
                              reason=p["error"], retried=p["retried"])
                  for _k, p in sorted(((k, pages[k]) for k in failed), key=lambda kp: str(kp[0]))
                  ][:MAX_FAILURES_LISTED],
        retried=sum(1 for p in pages.values() if p["retried"]),
        waiting_reason=waiting_reason if run_state in ("running", "waiting") else None,
        reason=reason if run_state in ("failed", "cancelled", "interrupted") else None,
        interrupted=run_state == "interrupted",
    )
    finished = len(done) + len(failed)
    if run_state == "running" and started_at is not None and finished and left:
        elapsed = (ensure_utc(now or utc_now()) - ensure_utc(started_at)).total_seconds()
        account.estimate_seconds_left = round(max(0.0, elapsed) / finished * left, 1)
    usage = run_usage if isinstance(run_usage, dict) else {}
    for name in ("engine_peak_memory_bytes", "model_server_peak_memory_bytes"):
        setattr(account, name, (live_peaks or {}).get(name) or usage.get(name))

    # The pages not done, by id: the run's own documents by fan-out index, else the failed pages' ids, else
    # (nothing reached) the pages the run was scoped to.
    documents = _source_documents(state)
    if documents:
        done_keys = set(done)
        ids = [str(d.get("id")) for i, d in enumerate(documents) if d.get("id") and i not in done_keys]
    elif pages:
        ids = [str(pages[k]["document_id"]) for k in failed if pages[k]["document_id"]]
    else:
        ids = [str(i) for i in (scope_ids or []) if i]
    if run_state in ("done", "failed", "cancelled", "interrupted") and ids and (len(failed) or left) \
            and not (run_state == "interrupted" and reason and RECIPE_CARRIES_ON in reason):
        account._not_done_ids = ids
        noun = "page" if len(ids) == 1 else "pages"
        label = (f"Read the {len(ids)} {noun} that failed" if not left else f"Read the {len(ids)} {noun} not done")
        account.offer = RunOffer(pages=len(ids), label=label)
    return account


def waiting_reason(db: Any, thread_id: str) -> str | None:
    """What a page of this run is waiting for, from its row (a memory wait says so there, #5537)."""
    from fichero_server.execution import jobs

    return jobs.waiting_reason_under(db, thread_id)


def _live_peaks(thread_id: str) -> dict[str, int]:
    from fichero_server.execution.runner import _get_workflow_state

    live = _get_workflow_state(thread_id) or {}
    peak = live.get("peak_memory")
    return peak.record() if peak is not None else {}


#: Accounts of finished runs, which do not change: Activity lists every recent failed run on each poll.
_FINISHED: dict[str, RunAccount] = {}
_FINISHED_LIMIT = 500


async def _checkpoint(db: Any, thread_id: str) -> tuple[dict[str, Any], list[Any]]:
    from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer

    import asyncio

    # Opened off the loop (the connect and the table setup wait on the database) and closed when the read ends: a
    # poll opened one per call and never closed it, 121 in a 34-minute run (RSS investigation, #5843).
    checkpointer = await asyncio.to_thread(
        lambda: AsyncDuckDBCheckpointer.from_db_path(db.path, setup_once=True))
    async with checkpointer:
        found = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    if not found:
        return {}, []
    return found.checkpoint.get("channel_values", {}) or {}, list(found.pending_writes or [])


def _title_failed_pages(db: Any, failures: list[PageFailure]) -> None:
    """Each failed page named as the Reader names it (`views.page_title`), never its file's basename: a PDF's
    page child is stored under a storage name (`fichero_upload_…`) that Activity would otherwise show."""
    from fichero_server.api.routes.system.views import page_title
    from fichero_server.db import get_read
    from fichero_server.models import Document

    for failure in failures:
        doc = get_read(db, Document, failure.document_id) if failure.document_id else None
        if doc is None:
            continue  # gone since the run: the file name the run recorded is all there is
        parent = get_read(db, Document, doc.parent_id) if doc.parent_id else None
        failure.page = page_title(parent, doc, doc.sequence or 1) if parent else page_title(doc, None, doc.sequence or 1)


async def run_account(db: Any, thread_id: str, *, run: Any = None, state: dict[str, Any] | None = None,
                      pending_writes: Iterable[Any] | None = None) -> RunAccount | None:
    """The account of one run, or None when the project has no record of it. `run`, `state` and
    `pending_writes` are passed by a caller that has already read them (the status route)."""
    if run is None:
        from fichero_server.workflows.activity import get_activity_tracker

        run = await get_activity_tracker(str(db.path)).store.get_workflow_run(thread_id)
    if run is None:
        return None
    cached = _FINISHED.get(thread_id)
    if cached is not None and cached.state == account_state(run.status, run.error):
        return cached
    if state is None:
        state, pending_writes = await _checkpoint(db, thread_id)
    # A record from before a column existed lacks it: the account says less, it never fails (#5555).
    scope = getattr(run, "resolved_scope", None)
    scope = scope if isinstance(scope, dict) else {}
    # Off the loop (#6176): both read the project's rows, which wait on the transaction gate behind a writer; on the loop
    # that stalled the whole engine, health included, for seconds.
    waiting = await asyncio.to_thread(waiting_reason, db, thread_id)
    account = build_account(status=run.status, reason=run.error, state=state, pending_writes=pending_writes or (),
                            started_at=getattr(run, "started_at", None), run_usage=getattr(run, "run_usage", None),
                            live_peaks=_live_peaks(thread_id), waiting_reason=waiting,
                            scope_ids=scope.get("resolved_ids") or scope.get("requested_ids"))
    await asyncio.to_thread(_title_failed_pages, db, account.failures)
    if account.state in ("done", "failed", "cancelled", "interrupted"):
        if len(_FINISHED) >= _FINISHED_LIMIT:
            _FINISHED.pop(next(iter(_FINISHED)))
        _FINISHED[thread_id] = account
    return account


def forget(thread_id: str) -> None:
    """A run's record changed after it ended (read again, deleted): its account is read afresh."""
    _FINISHED.pop(thread_id, None)


def stopped_at_words(when: datetime | None, prefix: str = INTERRUPTED_PREFIX) -> str:
    """'the engine stopped at 14:05' (or `prefix` at 14:05) in this Mac's time, or without a time when none
    is known."""
    if when is None:
        return prefix
    local = ensure_utc(when).astimezone()
    return f"{prefix} at {local.strftime('%H:%M')}"


#: Runs whose project was closed while they ran in this engine, by thread id: when it closed (#5608). Kept until
#: a run starts again on the thread (`run_started`); bounded.
_CLOSED_MID_RUN: dict[str, datetime] = {}
_CLOSED_MID_RUN_LIMIT = 500


def closing_runs(db: Any) -> list[str]:
    """A project is closing (#5608): each of its runs in flight in this engine leaves the live set and is noted
    with when. Its own later writes do not end it (`closed_mid_run`). A run with a checkpoint to go on from is
    PAUSED (#6596, `activity.engine.close-pauses-running-work`): asked to pause at its boundary, as quit does, and
    its record and rows say "Paused: the project closed" now, before the connection closes; the row's Continue
    resumes it from its checkpoint. A run with nothing to resume from, or a recipe's step run (its recipe run carries
    it on), is asked to stop, and the project's next open marks it interrupted, "the project was closed at HH:MM"
    (`mark_interrupted_runs`). Called by the database manager before the connection closes."""
    from fichero_server.db import activity_records as records
    from fichero_server.execution import jobs
    from fichero_server.execution.cancellation import request_cancellation, request_pause
    from fichero_server.execution.runner import _running_workflows
    from fichero_server.workflows import activity_store
    from fichero_server.workflows.run_status import is_terminal

    live = {tid for tid, s in list(_running_workflows.items()) if not is_terminal(s.get("status"))}
    now = utc_now()
    closing = [tid for tid, _started in activity_store.unfinished_runs(db) if tid in live]
    for thread_id in closing:
        while len(_CLOSED_MID_RUN) >= _CLOSED_MID_RUN_LIMIT:
            _CLOSED_MID_RUN.pop(next(iter(_CLOSED_MID_RUN)))
        _CLOSED_MID_RUN[thread_id] = now
        _running_workflows.pop(thread_id, None)
        if _resumable_after_close(db, thread_id):
            request_pause(thread_id)
            records.update_run(db, thread_id, {"status": "paused", "error": jobs.PAUSED_PROJECT_CLOSED})
            jobs.pause_run_rows(db, thread_id, jobs.PAUSED_PROJECT_CLOSED)
        else:
            request_cancellation(thread_id)  # its pages not yet handed in are not read with the project closed
    return closing


def _has_checkpoint(db: Any, thread_id: str) -> bool:
    """Whether a run has a checkpoint to go on from; False while the checkpoint table does not exist yet."""
    from fichero_server.db import activity_queries

    try:
        return activity_queries.has_root_checkpoint(db, thread_id)
    except Exception:  # noqa: BLE001 -- no checkpoint table yet: nothing to resume from
        return False


def _resumable_after_close(db: Any, thread_id: str) -> bool:
    """Whether a run its project's close stops can be paused and resumed (#6596): it has a checkpoint to go on from,
    and it is not a recipe's step run, which its recipe run carries on itself (`RECIPE_CARRIES_ON`)."""
    from fichero_server.execution import jobs

    return _has_checkpoint(db, thread_id) and jobs.parent_kind(db, thread_id) != "run-a-recipe"


def closed_mid_run(thread_id: str) -> bool:
    """Whether this run's project was closed while it ran: the runner's own end does not end its record."""
    return thread_id in _CLOSED_MID_RUN


def run_started(thread_id: str) -> None:
    """A run starts (again) on this thread: a close before it is no longer its story."""
    _CLOSED_MID_RUN.pop(thread_id, None)


def held_at_open(error: str | None) -> bool:
    """Whether a paused run's error says the open held it for the launch alert (`mark_interrupted_runs`): a run of its own,
    not a recipe's step run, which its recipe run's row stands for (one alert item per run)."""
    return bool(error) and error.startswith(HELD_PREFIX) and not error.endswith(RECIPE_CARRIES_ON)


def _hold(db: Any, thread_id: str, ended: datetime | None) -> None:
    """Hold a run the engine's stop cut off, that has a checkpoint: its record and rows `paused` with `HELD_PREFIX` words, to
    wait for the person's Resume (owner 2026-11-21). A recipe's step run says its recipe run carries it on, and the recipe's
    row notes it as the run to adopt (`awaiting`), so the recipe's Resume resumes it and no page is read twice."""
    import json

    from fichero_server.db import activity_records as records
    from fichero_server.execution import jobs

    words = f"{stopped_at_words(ended, HELD_PREFIX)}; {HELD_RESUMES}"
    parent = jobs.parent_of(db, thread_id)
    if parent is not None and jobs.parent_kind(db, thread_id) == "run-a-recipe":
        words += f"; {RECIPE_CARRIES_ON}"
        detail = json.loads(jobs.read_job(db, parent)["detail"] or "{}")
        running = [i for i, step in enumerate(detail.get("steps") or []) if step.get("state") == "running"]
        if running:
            # ponytail: two steps running beside each other note only the first; the other's pages start again in a new run
            # (their done pages stay done, `ran_on`). Noting each is the upgrade.
            cards = detail.get("runs") or []
            card = cards[running[0]] if running[0] < len(cards) else {}
            detail["awaiting"] = {"card": card.get("id"), "child": thread_id}
            jobs.save_detail(db, parent, json.dumps(detail))
    records.update_run(db, thread_id, {"status": "paused", "error": words})
    jobs.pause_run_rows(db, thread_id, words)


def mark_interrupted_runs(db: Any) -> list[str]:
    """On opening a project, a run this engine did not finish that has a checkpoint is HELD (`_hold`): paused, listed by the
    launch alert, resumed from its last finished page only when the person says so (owner 2026-11-21). Every other run this
    engine did not finish is marked interrupted (#5555): its record
    and its job row say "Interrupted: the engine stopped at HH:MM, before this run finished", the time being
    the last work the run recorded; a run whose project was closed while it ran says "Interrupted: the
    project was closed at HH:MM, before this run finished", the time of the close (#5608). Its checkpoint is
    kept, so its account still counts the pages done and left, and offers to read the pages not done
    (`read_again`). A run alive in this engine is left alone; one its project's close stopped is not alive
    (`closing_runs`). Returns the runs marked; the caller settles their documents."""
    from fichero_server.execution import jobs
    from fichero_server.execution.runner import _running_workflows
    from fichero_server.workflows import activity_store
    from fichero_server.workflows.run_status import is_terminal

    live = {tid for tid, s in list(_running_workflows.items()) if not is_terminal(s.get("status"))}
    marked: list[str] = []
    for thread_id, started_at in activity_store.unfinished_runs(db):
        if thread_id in live:
            continue
        closed_at = _CLOSED_MID_RUN.get(thread_id)
        if closed_at is not None:
            ended = closed_at
            words = stopped_at_words(closed_at, CLOSED_PREFIX)
        else:
            heard = [t for t in (jobs.last_heard(db, thread_id), started_at) if t is not None]
            ended = max(ensure_utc(t) for t in heard) if heard else None
            words = stopped_at_words(ended)
            if _has_checkpoint(db, thread_id):
                _hold(db, thread_id, ended)
                forget(thread_id)
                continue
        reason = f"{words}, before this run finished"
        if jobs.parent_kind(db, thread_id) == "run-a-recipe":
            reason += f"; {RECIPE_CARRIES_ON}"
        # It ends when it stopped, the time its words name, not when this open noticed (#6588: "1 h" for 3 minutes' work).
        activity_store.mark_run_failed(db, thread_id, reason, ensure_utc(ended).replace(tzinfo=None) if ended else None)
        jobs.fail_run_rows(db, thread_id, reason)
        forget(thread_id)
        marked.append(thread_id)
    return marked


__all__ = ["CLOSED_PREFIX", "HELD_PREFIX", "HELD_RESUMES", "INTERRUPTED_PREFIX", "RECIPE_CARRIES_ON", "PageFailure", "RunAccount", "RunOffer", "build_account",
           "closed_mid_run", "closing_runs", "forget", "held_at_open", "mark_interrupted_runs", "run_account", "run_started",
           "stopped_at_words"]
