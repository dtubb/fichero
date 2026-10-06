"""A run's account: one record of how a run went, read by its status and by Activity alike (#5555, #5498).

Activity showed a ten-page run as "running, total 0" while the run's status counted its pages: the two read
different records (Activity the run's saved timeline, the status the checkpoint). Both now read this one
account, built from the run's record (state, why, started, `run_usage`), its checkpoint (each page's result
in each fanned-out step) and its pages' rows in the job table (what a page is waiting for):

* pages done, failed and left, and each failure's reason, page by page;
* what the run is waiting for, when a page waits (memory, the lane);
* the estimate of the time left, from this run's own pace;
* the engine's and the model servers' peak memory (#5537), live while it runs;
* interrupted, when the engine stopped before the run finished (`mark_interrupted_runs`);
* the offer at the end: "Read the 3 pages that failed" (or "... not done" after an interruption), one
  action (`read_again`) that runs the same workflow, with the same model, over those pages only.

A page counts as done when every fanned-out step that has started has done it, and as failed when any step
failed it (a page a step skipped because the step before failed it is that one failure, not two).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from pydantic import BaseModel, Field, PrivateAttr

from fichero_server.core.timeutil import ensure_utc, utc_now
from fichero_server.workflows.run_progress import MAX_FAILURES_LISTED, item_error, results_by_step

#: How an interrupted run's reason starts; `account_state` reads a run whose reason starts so as interrupted.
INTERRUPTED_PREFIX = "Interrupted: the engine stopped"
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
    failures: list[PageFailure] = Field(default_factory=list,
                                        description=f"The first {MAX_FAILURES_LISTED} failed pages, with why.")
    retried: int = Field(0, description="Pages read once more after a passing cause (a model loading, memory).")
    waiting_reason: str | None = Field(None, description="What a page of the run is waiting for, in words.")
    reason: str | None = Field(None, description="Why the run failed, stopped or was interrupted.")
    interrupted: bool = False
    estimate_seconds_left: float | None = Field(None, description="At this run's own pace so far; null "
                                                "until a page is done or when nothing is left.")
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
    if state == "failed" and reason and reason.startswith((INTERRUPTED_PREFIX, _LEGACY_INTERRUPTED_PREFIX)):
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


def build_account(*, status: str | None, reason: str | None, state: dict[str, Any] | None,
                  pending_writes: Iterable[Any] = (), started_at: datetime | None = None,
                  run_usage: dict[str, Any] | None = None, live_peaks: dict[str, int] | None = None,
                  waiting_reason: str | None = None, scope_ids: list[str] | None = None,
                  now: datetime | None = None) -> RunAccount:
    """The account from what the run recorded. Pure: every input is passed in."""
    state = state if isinstance(state, dict) else {}
    steps = results_by_step(state, pending_writes)
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
    left = max(0, total - len(done) - len(failed))

    run_state = account_state(status, reason)
    account = RunAccount(
        state=run_state, pages_total=total, pages_done=len(done), pages_failed=len(failed), pages_left=left,
        failures=[PageFailure(page=str(p["file"] or "?").rsplit("/", 1)[-1], document_id=p["document_id"],
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
    if run_state in ("done", "failed", "cancelled", "interrupted") and ids and (len(failed) or left):
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

    found = await AsyncDuckDBCheckpointer.from_db_path(db.path).aget_tuple(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    if not found:
        return {}, []
    return found.checkpoint.get("channel_values", {}) or {}, list(found.pending_writes or [])


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
    account = build_account(status=run.status, reason=run.error, state=state, pending_writes=pending_writes or (),
                            started_at=getattr(run, "started_at", None), run_usage=getattr(run, "run_usage", None),
                            live_peaks=_live_peaks(thread_id),
                            waiting_reason=waiting_reason(db, thread_id),
                            scope_ids=scope.get("resolved_ids") or scope.get("requested_ids"))
    if account.state in ("done", "failed", "cancelled", "interrupted"):
        if len(_FINISHED) >= _FINISHED_LIMIT:
            _FINISHED.pop(next(iter(_FINISHED)))
        _FINISHED[thread_id] = account
    return account


def forget(thread_id: str) -> None:
    """A run's record changed after it ended (read again, deleted): its account is read afresh."""
    _FINISHED.pop(thread_id, None)


def stopped_at_words(when: datetime | None) -> str:
    """'the engine stopped at 14:05' in this Mac's time, or without a time when none is known."""
    if when is None:
        return INTERRUPTED_PREFIX
    local = ensure_utc(when).astimezone()
    return f"{INTERRUPTED_PREFIX} at {local.strftime('%H:%M')}"


def mark_interrupted_runs(db: Any) -> list[str]:
    """On opening a project, every run this engine did not finish is marked interrupted (#5555): its record
    and its job row say "Interrupted: the engine stopped at HH:MM, before this run finished", the time being
    the last work the run recorded. Its checkpoint is kept, so its account still counts the pages done and
    left, and offers to read the pages not done (`read_again`). A run alive in this engine (a project closed
    and opened again mid-run) is left alone. Returns the runs marked; the caller settles their documents."""
    from fichero_server.execution import jobs
    from fichero_server.execution.runner import _running_workflows
    from fichero_server.workflows import activity_store
    from fichero_server.workflows.run_status import is_terminal

    live = {tid for tid, s in list(_running_workflows.items()) if not is_terminal(s.get("status"))}
    marked: list[str] = []
    for thread_id, started_at in activity_store.unfinished_runs(db):
        if thread_id in live:
            continue
        heard = [t for t in (jobs.last_heard(db, thread_id), started_at) if t is not None]
        reason = f"{stopped_at_words(max(ensure_utc(t) for t in heard) if heard else None)}, before this run finished"
        activity_store.mark_run_failed(db, thread_id, reason)
        jobs.fail_run_rows(db, thread_id, reason)
        forget(thread_id)
        marked.append(thread_id)
    return marked


__all__ = ["INTERRUPTED_PREFIX", "PageFailure", "RunAccount", "RunOffer", "build_account", "forget",
           "mark_interrupted_runs", "run_account", "stopped_at_words"]
