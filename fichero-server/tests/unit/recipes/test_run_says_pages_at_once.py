"""The run's status says how many pages it reads at once and why, as fields from the gate, never a parsed sentence
(`recipes-run.memory.gate-shown`, #6217; ruling 3)."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.api.routes.system.recipes import RecipeRunStatus
from fichero_server.llm import kraken_runtime
from fichero_server.recipes.run_view import with_accounts


def _status(state="running", started_by="owner"):
    return {"job_id": "r1", "state": state, "reason": None, "steps": [], "skipped": [], "started_by": started_by}


@pytest.mark.parametrize("gate, words", [((2, None), None), ((1, "the Mac is paging"), "the Mac is paging")])
def test_a_running_run_carries_the_gates_number_and_its_reason(monkeypatch, gate, words):
    asked = []
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: asked.append(person) or gate)

    status = RecipeRunStatus(**asyncio.run(with_accounts(None, _status())))

    assert (status.pages_at_once, status.pages_at_once_reason) == (gate[0], words)
    assert asked == [True]  # the owner started it: a person's run


def test_a_run_an_import_started_is_asked_as_background_work(monkeypatch):
    asked = []
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: asked.append(person) or (1, "x"))

    asyncio.run(with_accounts(None, _status(started_by="import")))

    assert asked == [False]


def test_a_run_not_going_says_nothing_about_pages_at_once(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (2, None))

    status = RecipeRunStatus(**asyncio.run(with_accounts(None, _status(state="done"))))

    assert status.pages_at_once is None and status.pages_at_once_reason is None


def test_the_gate_names_which_hold_makes_it_one(monkeypatch):
    monkeypatch.setattr("fichero_server.core.compute_preferences.priority_for", lambda person: "fast")
    monkeypatch.setattr("fichero_server.execution.throttle.memory_is_busy", lambda: True)
    monkeypatch.setattr("fichero_server.execution.throttle.paging_now_on_this_mac", lambda: True)

    assert kraken_runtime.pages_at_once_and_why(True) == (1, "the Mac is paging")
    assert kraken_runtime.pages_at_once(True) == 1


@pytest.mark.parametrize("inside, set_last, threads", [(2, 4, 4), (1, 8, 8), (0, 8, None)])
def test_a_running_run_says_the_threads_each_page_reads_on(monkeypatch, inside, set_last, threads):
    # `recipes-run.memory.threads-fill-the-cores` (#6229, #6240): what the pages read on now, torch's one process-wide
    # pool as the Kraken seam last set it; nothing while no Kraken page is inside the gate (a step on another engine,
    # or between pages), never the cores divided by a guess (review b25)
    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: (2, None))
    monkeypatch.setattr(kraken_runtime._INFERENCE_LOCK, "pages_inside", lambda: inside)
    monkeypatch.setattr(kraken_runtime, "_THREADS_NOW", set_last, raising=False)

    status = RecipeRunStatus(**asyncio.run(with_accounts(None, _status())))

    assert status.threads_each == threads
