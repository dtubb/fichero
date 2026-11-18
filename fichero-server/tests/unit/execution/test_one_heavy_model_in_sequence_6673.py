"""`recipes-run.memory.one-heavy-model-in-sequence` (#6673): while a run's Kraken stage has pages left, the embed lane takes
no embed and Kraken's resident models are not released for one."""
from __future__ import annotations

import sys
import threading
import time
import types

import pytest

from fichero_server.execution import jobs


@pytest.fixture(autouse=True)
def fresh_scheduler(monkeypatch, app_db):
    """The reset tests/unit/jobs/conftest.py gave these tests before they moved: a new scheduler and the mode
    "automatic" per test, since the scheduler, its foreground streak and the pause are process-wide."""
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    jobs.set_mode("automatic")
    yield
    jobs.set_mode("automatic")


EMBED = "embed-in-sequence"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_no_embed_starts_while_the_kraken_stage_has_pages_in_flight(db, monkeypatch):
    events: list[str] = []
    in_flight = {"on": True}
    monkeypatch.setitem(jobs.KINDS, EMBED, jobs.Kind(run=lambda _db, subject: events.append(f"embed:{subject}"),
                                                    model="embedder", lane="embed", name="Embed for search"))
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: in_flight["on"])
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    jobs.enqueue(db, EMBED, "d1")
    time.sleep(1.5)  # long enough for the embed lane to have looked
    assert events == []  # the run's Kraken pages are left: the embed waits for the end
    in_flight["on"] = False
    assert _wait_for(lambda: events == ["embed:d1"], 60.0)


def test_kraken_models_are_not_released_while_its_stage_has_pages_left(monkeypatch):
    released: list[str] = []
    runtime = types.SimpleNamespace(
        _RESIDENT={"mccatmus": object()}, _INFERENCE_LOCK=threading.Lock(),
        release_resident_models=lambda reason: released.append(reason))
    monkeypatch.setitem(sys.modules, "fichero_server.llm.kraken_runtime", runtime)
    monkeypatch.setitem(sys.modules, "fichero_server.db.embeddings", None)
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: True)
    assert jobs.release_idle_models(besides={"embedder"}) == []
    assert released == []
    monkeypatch.setattr(jobs, "_kraken_pages_in_flight", lambda: False)
    assert jobs.release_idle_models(besides={"embedder"}) == ["Kraken"]
    assert released == ["memory is tight"]
