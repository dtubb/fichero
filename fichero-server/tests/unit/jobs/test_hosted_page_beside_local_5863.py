"""`activity.lane.each-unit-its-own-lane`: a hosted reader's page (no local weights) starts beside a running local page
for a person's run; background hosted pages and a local page behind a local page still wait (#5863). Real lane and rows; work faked."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

KRAKEN, HOSTED = "kraken-page-hb", "hosted-page-hb"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    started: list[str] = []
    gate = threading.Event()

    def work(db, subject):
        started.append(subject)
        gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=work, model="kraken:blla", lane="local-ml", name="Read a page"))
    # a test-only kind: in production a hosted `ask-a-model` call goes to the network lane (`llm.model_call_slot`)
    monkeypatch.setitem(jobs.KINDS, HOSTED, jobs.Kind(run=work, model="openai:gpt-x", lane="local-ml", name="Hosted page"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": None)
    monkeypatch.setattr(jobs, "_kraken_pages_at_once", lambda: 1)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    yield type("Lane", (), {"started": started, "gate": gate})
    gate.set()


def test_is_hosted_names_only_provider_models():
    assert jobs.is_hosted("openai:gpt-x") and jobs.is_hosted("anthropic:claude")
    assert not any(jobs.is_hosted(m) for m in ("kraken:blla", "omlx:big", "ollama:x", "apple:vision", "embedder", None))


def test_an_unknown_provider_counts_as_local():
    """Fail-closed: YOLO, Whisper, a typo, a provider nobody registered never start beside a local page."""
    assert not any(jobs.is_hosted(m) for m in ("yolo:v8", "whisper:large", "nobody-registered:x", "OpenAI-typo:gpt"))


def test_a_persons_hosted_page_starts_beside_a_running_kraken_page(db, lane):
    jobs.enqueue(db, KRAKEN, "k", started_by="owner")
    assert _wait_for(lambda: lane.started == ["k"])
    jobs.enqueue(db, HOSTED, "h", started_by="owner")
    assert _wait_for(lambda: "h" in lane.started), "the hosted page waited behind a local one"


def test_a_background_hosted_page_waits_behind_a_local_page(db, lane):
    jobs.enqueue(db, KRAKEN, "k", started_by="owner")
    assert _wait_for(lambda: lane.started == ["k"])
    jobs.enqueue(db, HOSTED, "h", started_by="automatic")
    time.sleep(0.4)
    assert lane.started == ["k"]


def test_a_hosted_page_does_not_become_the_loaded_model(db, lane):
    jobs.enqueue(db, KRAKEN, "k", started_by="owner")
    assert _wait_for(lambda: lane.started == ["k"])
    jobs.enqueue(db, HOSTED, "h", started_by="owner")
    assert _wait_for(lambda: "h" in lane.started)
    assert not jobs.is_hosted(jobs._scheduler.lanes["local-ml"].loaded_model)
