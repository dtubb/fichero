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


@pytest.mark.parametrize("priority, gate, inside, threads", [
    ("fast", (2, None), 2, 4), ("fast", (2, None), 1, 8), ("fast", (1, "x"), 1, 8), ("background", (1, "x"), 0, 4)])
def test_a_running_run_says_the_threads_each_page_reads_on(monkeypatch, priority, gate, inside, threads):
    # `recipes-run.memory.threads-fill-the-cores` (#6229): the cores the run's priority gives, split by the pages inside
    # the gate now, by the one rule the Kraken seam sets torch's threads by (review b24: never the gate's number)
    from fichero_server.core import background_compute

    monkeypatch.setattr(kraken_runtime, "pages_at_once_and_why", lambda person: gate)
    monkeypatch.setattr(kraken_runtime._INFERENCE_LOCK, "pages_inside", lambda: inside)
    assert kraken_runtime.threads_each(8 if priority == "fast" else 4) == threads
    monkeypatch.setattr("fichero_server.core.compute_preferences.priority_for", lambda person: priority)
    monkeypatch.setattr(background_compute, "cpu_count", lambda: 8)
    monkeypatch.setattr(background_compute, "embed_threads", lambda: 4)

    status = RecipeRunStatus(**asyncio.run(with_accounts(None, _status())))

    assert status.threads_each == threads
