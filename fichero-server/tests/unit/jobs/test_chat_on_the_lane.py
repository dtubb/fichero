"""Chat's model calls are jobs on the lanes too, outside any run (#5358).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md: `activity.run.lane-cap-per-mac`
("the cap on concurrent model calls is one per Mac"; "chat outside a run" was its gap) and the
local-model lane's "local-model calls outside a run (chat)". Written from the spec's text, and
driven through the public surface: questions asked with `POST /api/chat`, and Activity read with
`GET /api/activity/jobs`. Only the model is a stub: a cloud chat model that answers from memory.
"""
from __future__ import annotations

import threading

import pytest

from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import _wait_for
from tests.unit.jobs.test_text_calls_on_the_lane import ChatModel


@pytest.fixture
def cloud(monkeypatch):
    from fichero_server.api.routes.system import chat

    model = ChatModel()
    model.bind_tools = lambda tools: model  # a chat model that is offered tools and uses none
    monkeypatch.setattr(chat, "get_langchain_model", lambda config, *a, **k: model)
    return model


def _ask(client, results, question):
    r = client.post("/api/chat", json={"message": question, "provider": "openai", "model": "gpt-5"})
    results.append(r)


def test_activity_run_lane_cap_per_mac__chat_outside_a_run_shares_the_network_lane(client, cloud, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`: "the cap on concurrent model calls is one per Mac".
    With the network lane one wide and the first answer held, a second question waits for the lane,
    shown in Activity as a call to the model; both are answered once the first is."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    results: list = []
    first = threading.Thread(target=_ask, args=(client, results, "Who sold the house?"), daemon=True)
    second = threading.Thread(target=_ask, args=(client, results, "When?"), daemon=True)
    try:
        first.start()
        assert cloud.first_call.wait(30)
        second.start()
        assert _wait_for(lambda: any(
            j["task_type"] == "ask-a-model" and j["state"] == "waiting"
            for j in client.get("/api/activity/jobs").json()["jobs"]), seconds=30)
        assert cloud.calls == 1 and cloud.peak == 1
    finally:
        cloud.gate.set()  # a failure above must not leave the questions waiting forever
    first.join(60)
    second.join(60)
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert cloud.calls == 2 and cloud.peak == 1
