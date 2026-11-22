"""`activity.failure.bar-one-button-per-action` (#6731): a run's summary lists each failed batch once.

Seen 2026-11-19 (build 31): the recipe-failed bar showed Read the 149 pages…, Read the 137 pages…, Read the 112
pages…, then the same three again. Two workflow steps (lines, then read) carried the same batch runs in their
`failed_batches`, and the summary listed each batch once per step. One entry per batch run and offer; the entry
names every step that carried it.
"""

from __future__ import annotations

import asyncio

from fichero_server.recipes import run_view
from fichero_server.workflows import run_account as accounts
from fichero_server.workflows.run_account import RunAccount, RunOffer


def _account(failed: int) -> RunAccount:
    return RunAccount(state="failed", pages_failed=failed,
                      offer=RunOffer(pages=failed, label=f"Read the {failed} pages that failed"))


ACCOUNTS = {"b1": _account(149), "b2": _account(137), "b3": _account(112)}


def _step(name: str, job: str) -> dict:
    return {"steps": [name], "job": job, "card": "workflow", "child_id": None,
            "failed_batches": [{"child_id": child} for child in ACCOUNTS]}


def test_batches_shared_by_two_steps_are_listed_once(monkeypatch):
    async def run_account(_db, child):
        return ACCOUNTS[child]

    monkeypatch.setattr(accounts, "run_account", run_account)
    steps = [_step("find-lines", "find-lines"), _step("read-a-line", "read-a-line")]

    failed = asyncio.run(run_view.stage_failures(None, steps))

    assert [(f.thread_id, f.offer) for f in failed] == [
        ("b1", "Read the 149 pages that failed"),
        ("b2", "Read the 137 pages that failed"),
        ("b3", "Read the 112 pages that failed"),
    ]
    assert all(f.steps == ["find-lines", "read-a-line"] for f in failed)
    assert sum(f.pages_failed for f in failed) == 149 + 137 + 112
