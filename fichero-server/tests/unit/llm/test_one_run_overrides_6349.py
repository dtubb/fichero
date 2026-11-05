"""`ai.cloud.one-run-overrides` (#6349, #6350): "allow cloud once" and "run past the cap once" are one run's: the next run is
refused again, the ledger still books, nothing is written to a setting. And a project's own yes over the app's no reaches the gate."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, run_overrides, spend
from fichero_server.workflows import node_context

PRICED = LLMConfig(provider="openai", model="gpt-test", api_key="k", max_tokens=1000)


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    from fichero_server.llm import usage

    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": (
        {"input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5} if model == "gpt-test" else None))
    monkeypatch.setattr(spend, "app_cap_usd", lambda key: None)
    spend._RESERVED.clear()
    yield
    run_overrides._RUNS.clear()


def _project(tmp_path, answers: str) -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text(answers)
    return str(tmp_path / "P.fichero")


def _in_run(run_id):
    node_context.set_current_node("n", "n", "wf", run_id=run_id)


def test_the_registry_is_the_runs_own():
    run_overrides.set_for_run("run-a", allow_cloud=True)
    _in_run("run-a")
    assert run_overrides.allows_cloud() and not run_overrides.over_cap()
    _in_run("run-b")
    assert not run_overrides.allows_cloud()
    run_overrides.clear("run-a")
    _in_run("run-a")
    assert not run_overrides.allows_cloud()
    run_overrides.set_for_run("run-c")  # asked for none: nothing kept
    assert run_overrides.for_run("run-c") == {}


def test_over_cap_once_lets_the_run_through_and_the_spend_is_still_booked(tmp_path):
    lib = _project(tmp_path, "cloud_allowed: true\ncloud_spend_cap_usd: 0\n")

    async def call():
        async with spend.holding(PRICED, lib):
            pass

    _in_run("run-1")
    with pytest.raises(spend.CloudSpendRefusedError):
        asyncio.run(call())
    run_overrides.set_for_run("run-1", over_cap=True)
    asyncio.run(call())  # past the cap by the person's say
    assert spend.booked_usd(lib) > 0, "the spend is still booked"
    run_overrides.clear("run-1")
    _in_run("run-1")
    with pytest.raises(spend.CloudSpendRefusedError):  # the next run meets the rule again
        asyncio.run(call())


def test_allow_cloud_once_passes_the_gate_for_that_run_only(tmp_path, monkeypatch):
    lib = _project(tmp_path, "cloud_allowed: false\n")
    monkeypatch.setattr("fichero_server.llm.egress.current_library", lambda: lib)
    monkeypatch.setattr(llm, "is_local_only", lambda **kw: False)
    _in_run("run-2")
    with pytest.raises(llm.EgressRefusedError):
        llm._enforce_local_only_provider(PRICED, kind="chat")
    run_overrides.set_for_run("run-2", allow_cloud=True)
    assert llm._enforce_local_only_provider(PRICED, kind="chat") is None  # no raise
    _in_run("run-3")
    with pytest.raises(llm.EgressRefusedError):
        llm._enforce_local_only_provider(PRICED, kind="chat")
    assert "cloud_allowed: false" in (tmp_path / "P.fichero" / "recipe" / "setup.yaml").read_text()  # no setting was written


def test_a_project_yes_over_an_app_no_reaches_the_call_gate(tmp_path, monkeypatch):
    from fichero_server.recipes import places

    lib = _project(tmp_path, "cloud_allowed: true\n")
    monkeypatch.setattr(places, "get_places", lambda: ["this-mac"])  # the app's switch is off
    monkeypatch.setattr("fichero_server.llm.egress.current_library", lambda: lib)
    monkeypatch.setattr(llm, "is_local_only", lambda **kw: False)
    node_context.set_current_node("", "", "", run_id="")
    assert llm._enforce_local_only_provider(PRICED, kind="chat") is None  # no raise: the project's own yes wins for the cloud


def test_the_execute_and_resume_requests_carry_the_two_flags():
    from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest, ResumeWorkflowRequest

    r = ExecuteWorkflowRequest(workflow_id="w", allow_cloud_once=True, over_cap_once=True)
    assert r.allow_cloud_once and r.over_cap_once
    assert not ExecuteWorkflowRequest(workflow_id="w").allow_cloud_once
    assert ResumeWorkflowRequest(over_cap_once=True).over_cap_once
