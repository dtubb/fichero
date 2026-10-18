"""`activity.throttle.power-heat-memory`, `activity.run.says-what-it-reads` (#5685): a step that waits on the throttle
says it waits and why, and counts pages. WHY (2026-10-11, the MCP onboarding walk): the run's row said 'running' and
'Running step find-regions: 0 of 1 folder done' while the machine said 'Waiting: you're using the Mac'.
Through `with_accounts` with the account the run would give."""
from __future__ import annotations

import asyncio

from fichero_server.workflows.run_account import RunAccount


def _status():
    return {"state": "running", "reason": "Running step find-regions: 0 of 1 folder done",
            "steps": [{"state": "running", "card": "workflow", "child_id": "c1", "job": "find-regions",
                       "doing": "Finding regions"}]}


def _with(account, monkeypatch):
    from fichero_server.recipes.run_view import with_accounts
    from fichero_server.workflows import run_account

    async def fake(db, child_id):
        return account

    monkeypatch.setattr(run_account, "run_account", fake)
    return asyncio.run(with_accounts(None, _status()))


def test_a_step_waiting_on_the_throttle_says_waiting_and_counts_pages(monkeypatch):
    account = RunAccount(state="running", pages_total=10, pages_done=3, waiting_reason="Waiting: you're using the Mac")
    status = _with(account, monkeypatch)
    assert status["reason"].startswith("Waiting: you're using the Mac"), status["reason"]
    assert "3 of 10 pages" in status["reason"] and "folder" not in status["reason"]
    assert status["waiting_for"] == "Waiting: you're using the Mac"


def test_a_step_not_waiting_still_says_what_it_reads(monkeypatch):
    status = _with(RunAccount(state="running", pages_total=10, pages_done=3), monkeypatch)
    assert status["reason"].startswith("Finding regions: ") and "3 of 10 pages" in status["reason"]
