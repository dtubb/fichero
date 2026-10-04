"""One provider's calls never take the whole network lane (#5358).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.run.lane-cap-per-mac`
("a cap per provider" was its gap) and the lane table: the network lane is "a few, per provider
rate limit; the limit is the provider's, not the CPU's". Written from the spec's text, and driven
through the public surface: real entity-extraction runs started with
`POST /api/workflow-execution/execute`. Only the models are stubs: one provider's calls hang (as
under a rate limit), the other's answer at once, each reached through the real `llm.chat` path.
"""
from __future__ import annotations

import threading

import pytest

from fichero_server.execution import jobs
from tests.unit.jobs.test_run_tree_rolls_up import _workflow
from tests.unit.jobs.test_runs_are_jobs import _execute, _status, _tree, _wait_for, no_embedding_model  # noqa: F401
from tests.unit.jobs.test_text_calls_on_the_lane import ChatModel, pages  # noqa: F401


class HeldModel(ChatModel):
    """A provider whose calls hang, as under a rate limit, until released one at a time."""

    def __init__(self):
        super().__init__()
        self.releases = threading.Semaphore(0)

    async def ainvoke(self, messages, *a, **k):
        import asyncio

        with self.lock:
            self.calls += 1
            self.live += 1
            self.peak = max(self.peak, self.live)
        try:
            await asyncio.to_thread(self.releases.acquire, True, 60)
            return await ChatModel.ainvoke(ChatModel(), messages)
        finally:
            with self.lock:
                self.live -= 1


@pytest.fixture
def providers(monkeypatch):
    """`openai`'s calls hang until released; `anthropic`'s answer at once."""
    import fichero_server.llm as llm
    from fichero_server.workflows import validation

    stuck, quick = HeldModel(), ChatModel()
    monkeypatch.setattr(llm, "get_langchain_model",
                        lambda config, *a, **k: stuck if config.provider == "openai" else quick)
    monkeypatch.setattr(validation, "validate_workflow_llm_preflight", lambda *a, **k: [])
    yield stuck, quick
    for _ in range(50):
        stuck.releases.release()


def _anthropic(db):
    wf = _workflow(db, "claude-sonnet-4")
    wf.provider = "anthropic"
    db.save(wf)
    return wf


def test_activity_run_lane_cap_per_mac__one_provider_alone_keeps_the_whole_lane(client, db, pages, providers, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`, the cap per provider, work-conserving: a Mac using
    one provider loses no slot to a share held for nobody. Three runs on one provider, alone on a
    three-wide lane, make three calls at once."""
    stuck, _quick = providers
    monkeypatch.setitem(jobs.LANES, "network", 3)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    runs = [_execute(client, _workflow(db, "gpt-5"), pages) for _ in range(3)]
    assert _wait_for(lambda: stuck.live == 3)
    assert stuck.peak == 3
    for _ in range(9):
        stuck.releases.release()
    assert _wait_for(lambda: all(_status(client, run) == "completed" for run in runs))


def test_activity_run_lane_cap_per_mac__a_stuck_provider_leaves_room_for_another(client, db, pages, providers, monkeypatch):
    """Behaviour `activity.run.lane-cap-per-mac`, the cap per provider: a provider stuck on a rate
    limit holding the whole three-wide lane (a fourth of its runs waiting too) gives up a slot to
    another provider's waiting call as soon as one of its calls ends, ahead of its own older
    waiting call: the other run's three calls each wait for at most one of the stuck provider's
    calls, and the stuck runs still finish when the hang ends."""
    stuck, quick = providers
    monkeypatch.setitem(jobs.LANES, "network", 3)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    slow = [_execute(client, _workflow(db, "gpt-5"), pages) for _ in range(4)]
    # Three hold the lane; the fourth's call waits, older than any of the other provider's.
    assert _wait_for(lambda: stuck.live == 3 and any(
        c["state"] == "waiting" for step in _tree(client, slow[3])["children"] for c in step["children"]))
    fast = _execute(client, _anthropic(db), pages)
    released = 0
    while _status(client, fast) != "completed" and released < 6:
        # Its next call is waiting for the lane (as `GET /api/activity/jobs/{run}` shows); then one
        # of the stuck provider's calls ends.
        assert _wait_for(lambda: _status(client, fast) == "completed" or any(
            c["state"] == "waiting" for step in _tree(client, fast)["children"] for c in step["children"]))
        if _status(client, fast) == "completed":
            break
        before = quick.calls
        stuck.releases.release()
        released += 1
        assert _wait_for(lambda: quick.calls > before or _status(client, fast) == "completed", seconds=30)
    assert _status(client, fast) == "completed" or _wait_for(lambda: _status(client, fast) == "completed")
    assert quick.calls == 3 and released <= 3
    for _ in range(12):
        stuck.releases.release()
    assert _wait_for(lambda: all(_status(client, run) == "completed" for run in slow))
