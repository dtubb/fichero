"""`run.fail.mcp-says-the-fix` (#6354): a failed run's `failure` reaches an MCP caller intact, and an engine error that carries it names
the tool that does each action; a bug in Fichero names the bug-report tool first."""
from __future__ import annotations

import json

from fichero_mcp import openapi_runtime
from fichero_mcp.openapi_runtime import EngineError, _with_ways_through

FAILURE = {"kind": "no-credit", "words": "OpenRouter has no credit left.", "fix": "Add credit, then run it again.",
           "actions": [{"kind": "open-settings", "control": "settings.ai.providers"}, {"kind": "choose-model"}, {"kind": "retry"}]}
BUG = {"kind": "unexpected", "words": "w", "fix": "This is a bug in Fichero.", "actions": [{"kind": "retry"}, {"kind": "report-bug"}]}


def test_the_message_names_the_tool_for_each_action_and_the_failure_stays_intact():
    out = _with_ways_through({"message": "The run failed.", "failure": FAILURE})
    assert out["failure"] == FAILURE
    assert "Fix: Add credit, then run it again." in out["message"]
    for tool in ("fichero_providers_set_api_key", "fichero_workflow_run", "fichero_activity_retry_job"):
        assert tool in out["message"], tool


def test_a_bug_in_fichero_names_the_bug_report_tool_first():
    message = _with_ways_through({"failure": BUG})["message"]
    assert message.index("fichero_activity_post_job_bug_report") < message.index("fichero_activity_retry_job")


def test_a_detail_with_no_failure_is_left_alone():
    assert _with_ways_through({"message": "x"}) == {"message": "x"}


def test_a_failed_status_answer_reaches_the_caller_with_its_failure_intact_and_an_error_detail_names_the_tools():
    import httpx
    from fichero_cli.client import FicheroClient

    status = {"thread_id": "t1", "status": "failed", "failure": FAILURE}
    ok = lambda: FicheroClient(base_url="http://engine.test", token="t",  # noqa: E731
                               transport=httpx.MockTransport(lambda request: httpx.Response(200, json=status)))
    openapi_runtime.configure(ok, ok)
    assert openapi_runtime.call("GET", "/api/workflow-execution/threads/t1/status")["failure"] == FAILURE
    bad = lambda: FicheroClient(base_url="http://engine.test", token="t",  # noqa: E731
                                transport=httpx.MockTransport(lambda request: httpx.Response(
                                    409, json={"detail": {"message": "The run failed.", "failure": FAILURE}})))
    openapi_runtime.configure(bad, bad)
    try:
        openapi_runtime.call("POST", "/api/workflow-execution/execute", json={})
    except EngineError as err:
        said = json.loads(str(err))["detail"]
        assert said["failure"] == FAILURE and "fichero_activity_retry_job" in said["message"]
    else:
        raise AssertionError("the error did not reach the tool")
