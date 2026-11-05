"""`run.fail.failed-stream-event` (#6354): the stream's error events carry `failure`, so a client need not poll."""

from __future__ import annotations

from fichero_server.execution import runner


def test_the_failure_is_built_by_the_one_table_and_never_raises():
    class _Wf:
        name, provider, model = "Read pages", "openrouter", "some/model"

    out = runner._run_failure(RuntimeError("boom"), "boom", _Wf(), done=3, total=10)
    assert out["kind"] == "unexpected" and out["step"] == "Read pages" and out["provider"] == "OpenRouter"
    assert out["pages_done"] == 3 and out["pages_total"] == 10
    assert runner._run_failure(None, "", object())["kind"] == "unexpected"
