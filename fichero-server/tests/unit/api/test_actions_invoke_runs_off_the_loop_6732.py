"""#6732: POST /api/actions/invoke runs the action off the event loop, so a bulk delete of runs never holds up the
Activity polls (they waited 2-23 s behind it)."""
from __future__ import annotations

import asyncio

from fichero_server.actions import registry


def test_an_invoked_action_does_not_run_on_the_event_loop(client, monkeypatch):
    real = registry.invoke
    on_loop: list[bool] = []

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return real(*args, **kwargs)

    monkeypatch.setattr(registry, "invoke", spy)
    response = client.post("/api/actions/invoke", json={"name": "workflow_run.delete", "params": {"thread_ids": ["no-such-run"]}})
    assert response.status_code == 200, response.text
    assert on_loop == [False]
