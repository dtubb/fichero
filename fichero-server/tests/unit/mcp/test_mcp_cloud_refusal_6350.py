"""`ai.cloud.mcp-refuses-in-words` (#6350): a cloud refusal reaches an MCP caller with `detail.refusal` intact and a message naming the
tool's own arguments (`allow_cloud_once`, `over_cap_once`) and the tools that set the caps and the yes."""
from __future__ import annotations

import json

from fichero_mcp import openapi_runtime
from fichero_mcp.openapi_runtime import EngineError, _with_ways_through

CAP = {"message": "capped", "refusal": {"kind": "cap-monthly", "words": "w", "fixes": [
    {"kind": "raise-to", "usd": 10.4}, {"kind": "over-cap-once"}, {"kind": "open-settings", "control": "settings.ai.cloudCaps"}]}}
IMAGES = {"message": "not sent", "refusal": {"kind": "images", "words": "w", "fixes": [
    {"kind": "allow-everywhere"}, {"kind": "allow-project"}, {"kind": "allow-once"}, {"kind": "open-settings"}]}}


def test_a_cap_refusal_keeps_the_refusal_and_names_the_arguments_and_tools():
    out = _with_ways_through(CAP)
    assert out["refusal"] == CAP["refusal"]
    assert "over_cap_once=true" in out["message"] and "fichero_ai_put_cloud_cap" in out["message"]
    assert "allow_cloud_once" not in out["message"]


def test_an_images_refusal_names_allow_cloud_once_and_the_allow_tools():
    out = _with_ways_through(IMAGES)
    assert "allow_cloud_once=true" in out["message"]
    assert "fichero_recipes_allow_cloud" in out["message"] and "fichero_recipes_put_places" in out["message"]


def test_other_details_are_left_alone():
    assert _with_ways_through("plain") == "plain"
    assert _with_ways_through({"message": "x"}) == {"message": "x"}


def test_a_real_cloud_refusal_reaches_the_tool_as_an_engine_error_with_the_refusal_intact():
    import httpx
    from fichero_cli.client import FicheroClient

    body = {"detail": CAP}
    factory = lambda: FicheroClient(base_url="http://engine.test", token="t",  # noqa: E731
                                    transport=httpx.MockTransport(lambda request: httpx.Response(400, json=body)))
    openapi_runtime.configure(factory, factory)
    try:
        openapi_runtime.call("POST", "/api/workflow-execution/execute", json={})
    except EngineError as err:
        said = json.loads(str(err))
        assert said["status"] == 400 and said["detail"]["refusal"] == CAP["refusal"]
        assert "over_cap_once=true" in said["detail"]["message"]
    else:
        raise AssertionError("the refusal did not reach the tool")
