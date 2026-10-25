"""A local reader (Kraken) and a hosted one use different resources, so Read runs them side by side instead of one after the
other (owner, 2026-10-25, #6127: Kraken took 16 minutes for 20 pages, then the cloud reader started)."""
from __future__ import annotations

import threading

import pytest

from fichero_server.execution import jobs
from fichero_server.recipes import runner

KRAKEN = {"card": "workflow", "job": "read-a-line", "steps": ["a"], "runs_on": "this-mac", "takes": ["lines"],
          "gives": ["line_readings"]}
CLOUD = {"card": "workflow", "job": "read-a-page", "steps": ["b"], "runs_on": "cloud:openrouter", "takes": ["page_image"],
         "gives": ["page_reading"]}


def _run(monkeypatch, cards, work):
    """`_run_batch` over `cards`, each step's work being `work(card)`; the states it ends with."""
    for name, value in {"_step_pages": lambda *a, **k: (["p1"], {}, {}), "_blocked": lambda *a: None,
                        "_await_downloads": lambda *a: None, "_stop_asked": lambda *a: False,
                        "_wait_out_a_pause": lambda *a: None, "_after_the_step": lambda *a, **k: None,
                        "_let_go_after_the_last_served_step": lambda *a: None,
                        "_run_card": lambda db, card, *a, **k: (card["steps"][0], *work(card))}.items():
        monkeypatch.setattr(runner, name, value)
    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: None)
    detail = {"runs": cards, "steps": [{"state": "waiting"} for _ in cards], "batch_states": [None] * len(cards)}
    runner._run_batch(None, "job", detail, {"units": ["p1"]}, {}, "test", final=True)
    return [step["state"] for step in detail["steps"]]


def test_a_local_reader_and_a_hosted_one_run_at_the_same_time(monkeypatch):
    meet = threading.Barrier(2, timeout=10)  # each waits for the other: broken (so failed) if they run one after the other

    def work(card):
        meet.wait()
        return "done", None

    assert _run(monkeypatch, [KRAKEN, CLOUD], work) == ["done", "done"]


@pytest.mark.parametrize("other", [{**CLOUD, "runs_on": "this-mac"}, {**CLOUD, "job": "read-a-line"},
                                   {**CLOUD, "takes": ["line_readings"]}], ids=["both local", "same job", "takes the other's"])
def test_two_steps_that_share_a_resource_or_an_input_run_one_after_the_other(monkeypatch, other):
    now, most = [0], [0]
    lock = threading.Lock()

    def work(card):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        threading.Event().wait(0.2)
        with lock:
            now[0] -= 1
        return "done", None

    assert _run(monkeypatch, [KRAKEN, other], work) == ["done", "done"]
    assert most[0] == 1
