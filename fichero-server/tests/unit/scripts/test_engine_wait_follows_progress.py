"""The wait for a spawned engine follows the ENGINE'S progress, not the wall clock (#5187).

WHY: the spawned-engine tests failed under load with "never became healthy in 30s" (and "never
became ready" at 90 s) while nothing was wrong: the engine's ~3 CPU-seconds of startup were starved
on a machine at load 80. A wall-clock deadline cannot tell a starved engine from a hung one, so the
gate either flaked or was excluded. The wait now fails only on what is really wrong -- the engine
exited, burned 10x its work without answering, or made no progress at all -- and says which. If
this regresses, a busy machine fails the gate again, or a real hang waits forever.

Each bound is tripped by a real child process standing in for the engine.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.integration import _engine_wait
from tests.integration._engine_wait import wait_for_engine


@pytest.fixture
def child():
    started: list[subprocess.Popen] = []

    def spawn(code: str) -> subprocess.Popen:
        process = subprocess.Popen([sys.executable, "-c", code])
        started.append(process)
        return process

    yield spawn
    for process in started:
        if process.poll() is None:
            process.kill()
        process.wait(10)


def test_an_engine_that_exits_is_named_at_once(child):
    process = child("import sys; sys.exit(3)")
    assert wait_for_engine(lambda: False, process) == "the engine exited with code 3"


def test_an_engine_that_burns_without_answering_trips_the_cpu_budget(child, monkeypatch):
    monkeypatch.setattr(_engine_wait, "STARTUP_CPU_BUDGET_S", 1.0)
    process = child("while True: pass")
    why = wait_for_engine(lambda: False, process)
    assert why.startswith("the engine used ") and "CPU-seconds without answering (budget 1" in why


def test_an_engine_that_goes_idle_is_a_hang_not_load(child, monkeypatch):
    monkeypatch.setattr(_engine_wait, "STARTUP_STALL_S", 1.5)
    process = child("import time; time.sleep(60)")
    why = wait_for_engine(lambda: False, process)
    assert why.startswith("the engine made no CPU progress for 2 s at ") and why.endswith("a hang, not load")


def test_an_engine_that_answers_is_ready(child):
    process = child("import time; time.sleep(60)")
    polls = iter([False, False, True])
    assert wait_for_engine(lambda: next(polls), process) is None


def test_a_check_that_raises_is_not_listening_yet(child):
    process = child("import time; time.sleep(60)")
    answers = iter([ConnectionError("refused"), True])

    def check():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert wait_for_engine(check, process) is None


def test_the_wall_backstop_names_itself(child, monkeypatch):
    monkeypatch.setattr(_engine_wait, "STARTUP_WALL_CAP_S", 1.0)
    process = child("while True: pass")                 # busy, under budget, never answering
    why = wait_for_engine(lambda: False, process)
    assert why.startswith("the engine was not ready after 1 s (") and why.endswith("CPU-seconds)")
