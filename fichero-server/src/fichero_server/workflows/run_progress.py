"""A run's progress in a few hundred bytes: which step, how many files done, which failed (#5401).

A run's status used to be its whole LangGraph state: every fanned-out file's document record and
every pending task, 526 KB for a 50-photo run (3 MB when a 71-photo run finished). An agent polling
over MCP cannot read that, and a person never needs it to know how far a run has got. This keeps
what answers "how is it going": the current step, and per fanned-out step the files done,
succeeded, failed and cancelled, with the first failures by file.

While a fan-out runs, LangGraph does not advance the checkpoint until every file is done: the
finished files sit in the checkpoint's pending writes. So progress reads both the state's
`parallel_results` and the pending writes to that channel, or a running fan-out would read 0 done
until the moment it finished.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

#: Failures listed by file per step; the counts are always complete.
MAX_FAILURES_LISTED = 10


class FileFailure(BaseModel):
    """One file a step could not do."""

    file: str = Field(description="The file's name (not its full path).")
    error: str


class StepProgress(BaseModel):
    """One fanned-out step's per-file outcomes."""

    node: str
    total: int | None = Field(None, description="Files this step fans out over, when known.")
    done: int
    succeeded: int
    failed: int
    cancelled: int
    failures: list[FileFailure] = Field(default_factory=list,
                                        description=f"The first {MAX_FAILURES_LISTED} failures by file.")


class RunProgress(BaseModel):
    """How far a run has got."""

    current_node: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    files_total: int = 0
    steps: list[StepProgress] = Field(default_factory=list)


def _item_error(item: dict[str, Any]) -> str | None:
    result = item.get("result")
    error = item.get("error") or (result.get("error") if isinstance(result, dict) else None)
    if error:
        return str(error)
    return "failed" if item.get("success") is False else None


def _step(node: str, items: list[dict[str, Any]]) -> StepProgress:
    by_index: dict[Any, dict[str, Any]] = {}
    for item in items:  # a retried file appears twice; its last result counts
        by_index[item.get("index", id(item))] = item
    unique = list(by_index.values())
    total = next((i["total"] for i in unique if isinstance(i.get("total"), int)), None)
    cancelled = [i for i in unique if i.get("cancelled")]
    failed = [i for i in unique if not i.get("cancelled") and _item_error(i)]
    failures = [FileFailure(file=Path(str(i.get("file") or "?")).name, error=_item_error(i) or "")
                for i in sorted(failed, key=lambda i: i.get("index", 0))[:MAX_FAILURES_LISTED]]
    return StepProgress(node=node, total=total, done=len(unique), succeeded=len(unique) - len(failed) - len(cancelled),
                        failed=len(failed), cancelled=len(cancelled), failures=failures)


def summarize_run_state(state: dict[str, Any] | None, pending_writes: Iterable[Any] = ()) -> RunProgress:
    """Progress from a checkpoint's state and its pending writes (task_id, channel, value)."""
    state = state if isinstance(state, dict) else {}
    per_node: dict[str, list[dict[str, Any]]] = {}

    def add(results: Any) -> None:
        if isinstance(results, dict):
            for node, items in results.items():
                per_node.setdefault(str(node), []).extend(i for i in (items or []) if isinstance(i, dict))

    add(state.get("parallel_results"))
    for write in pending_writes or ():
        if isinstance(write, (tuple, list)) and len(write) >= 3 and write[1] == "parallel_results":
            add(write[2])
    files = state.get("files")
    return RunProgress(
        current_node=state.get("current_node"),
        completed_nodes=[str(n) for n in (state.get("completed_nodes") or [])],
        files_total=len(files) if isinstance(files, list) else 0,
        steps=[_step(node, items) for node, items in per_node.items()],
    )
