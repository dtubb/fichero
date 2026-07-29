from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

import fichero_server.workflows.tools  # noqa: F401  (registers sub_workflow)
from fichero_server.workflows import registry
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state
from fichero_server.workflows.subworkflow import validate_sub_workflow_references
from fichero_server.workflows.types import (
    DataType,
    NodeDef,
    PortDef,
    ToolDef,
    WorkflowDef,
)
from fichero_server.workflows.validation import validate_workflow_preflight


def _tool_def(name: str) -> ToolDef:
    return ToolDef(
        name=name,
        display_name=name,
        category="test",
        input_ports=[
            PortDef(
                id="text",
                name="Text",
                port_type="input",
                data_type=DataType.TEXT,
            )
        ],
        output_ports=[
            PortDef(
                id="text",
                name="Text",
                port_type="output",
                data_type=DataType.TEXT,
            )
        ],
    )


def _install_fake_tool(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    func: Callable[..., Any],
) -> None:
    monkeypatch.setitem(registry.TOOLS, name, func)
    monkeypatch.setitem(registry.TOOL_DEFS, name, _tool_def(name))


def _child_workflow(*, tool: str = "fake_child") -> WorkflowDef:
    return WorkflowDef(
        id="child",
        name="Child",
        provider="",
        model="",
        nodes=[
            NodeDef(
                id="child_node",
                tool=tool,
                inputs={"text": "$.inputs.text"},
            )
        ],
        edges=[],
    )


def _parent_workflow(
    *,
    workflow_ref: str = "child",
    output_mapping: dict[str, str] | None = None,
    extra_config: dict[str, Any] | None = None,
) -> WorkflowDef:
    config = {
        "workflow_ref": workflow_ref,
        "input_contract": [
            {"id": "text", "data_type": "text", "required": True}
        ],
        "output_contract": [
            {"id": "text", "data_type": "text", "required": True}
        ],
        "output_mapping": output_mapping
        if output_mapping is not None
        else {"text": "$.nodes.child_node.text"},
    }
    if extra_config:
        config.update(extra_config)
    return WorkflowDef(
        id="parent",
        name="Parent",
        provider="",
        model="",
        nodes=[
            NodeDef(
                id="sub",
                tool="sub_workflow",
                inputs={"text": "$.inputs.text"},
                config=config,
            )
        ],
        edges=[],
    )


async def _run_parent(parent: WorkflowDef, child: WorkflowDef, text: Any = "hello"):
    state = build_initial_state({"text": text}, library_path="")
    state["inputs"] = {"text": text}
    state["task_id"] = "parent-run"
    state["workflow_id"] = parent.id
    state["sub_workflows"] = {child.id: child, child.name: child}
    return await build_graph(
        parent,
        skip_cache=True,
    ).ainvoke(state)


def test_sub_workflow_parent_sees_only_declared_child_outputs(monkeypatch):
    async def fake_child(inputs, state, llm_config):
        return {
            "text": inputs["text"].upper(),
            "secret": "internal child output",
        }

    _install_fake_tool(monkeypatch, "fake_child", fake_child)

    final_state = asyncio.run(_run_parent(_parent_workflow(), _child_workflow()))

    output = final_state["outputs"]["sub"]
    assert output["text"] == "HELLO"
    assert "secret" not in output
    assert output["_run"]["parent_task_id"] == "parent-run"
    assert output["_run"]["parent_workflow_id"] == "parent"
    assert output["_run"]["parent_node_id"] == "sub"
    assert output["_run"]["child_workflow_id"] == "child"
    assert "sub" in output["_run"]["lineage_path"]


def test_sub_workflow_missing_required_child_output_fails_parent(monkeypatch):
    async def fake_child(inputs, state, llm_config):
        return {"other": "not mapped"}

    _install_fake_tool(monkeypatch, "fake_child", fake_child)

    with pytest.raises(Exception, match="Missing required output 'text'"):
        asyncio.run(_run_parent(_parent_workflow(), _child_workflow()))


def test_sub_workflow_invalid_parent_input_type_fails_before_child_execution(monkeypatch):
    called = False

    async def fake_child(inputs, state, llm_config):
        nonlocal called
        called = True
        return {"text": "should not run"}

    _install_fake_tool(monkeypatch, "fake_child", fake_child)

    with pytest.raises(Exception, match="Invalid input 'text': expected text"):
        asyncio.run(_run_parent(_parent_workflow(), _child_workflow(), text=123))

    assert called is False


def test_sub_workflow_input_schema_fails_before_child_execution(monkeypatch):
    called = False

    async def fake_child(inputs, state, llm_config):
        nonlocal called
        called = True
        return {"text": "should not run"}

    _install_fake_tool(monkeypatch, "fake_child", fake_child)
    parent = _parent_workflow(
        extra_config={
            "input_contract": [
                {
                    "id": "text",
                    "data_type": "text",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^allowed$"},
                }
            ]
        }
    )

    with pytest.raises(Exception, match="does not match schema"):
        asyncio.run(_run_parent(parent, _child_workflow(), text="blocked"))

    assert called is False


def test_sub_workflow_max_depth_guard_fails_before_child_execution(monkeypatch):
    called = False

    async def fake_child(inputs, state, llm_config):
        nonlocal called
        called = True
        return {"text": "should not run"}

    _install_fake_tool(monkeypatch, "fake_child", fake_child)
    parent = _parent_workflow(extra_config={"max_depth": 1})
    state_text = "hello"
    state = build_initial_state({"text": state_text}, library_path="")
    state["inputs"] = {"text": state_text}
    state["task_id"] = "parent-run"
    state["workflow_id"] = parent.id
    state["sub_workflows"] = {"child": _child_workflow()}
    state["sub_workflow_depth"] = 1

    with pytest.raises(Exception, match="exceeded max_depth=1"):
        asyncio.run(build_graph(parent, skip_cache=True).ainvoke(state))

    assert called is False


def test_sub_workflow_direct_cycle_rejected():
    workflow = _parent_workflow(workflow_ref="parent")

    errors = validate_sub_workflow_references(workflow)

    assert len(errors) == 1
    assert "workflow reference cycle detected" in errors[0]


def test_sub_workflow_transitive_cycle_rejected():
    parent = _parent_workflow(workflow_ref="middle")
    middle = WorkflowDef(
        id="middle",
        name="Middle",
        nodes=[
            NodeDef(
                id="nested",
                tool="sub_workflow",
                config={
                    "workflow_ref": "parent",
                    "output_contract": [
                        {"id": "text", "data_type": "text", "required": True}
                    ],
                    "output_mapping": {"text": "$.nodes.any.text"},
                },
            )
        ],
        edges=[],
    )

    errors = validate_sub_workflow_references(
        parent,
        workflow_resolver=lambda ref: {"middle": middle, "parent": parent}.get(ref),
    )

    assert len(errors) == 1
    assert "parent -> middle -> parent" in errors[0]


def test_sub_workflow_dynamic_ref_rejected_by_preflight():
    workflow = _parent_workflow(workflow_ref="$.inputs.workflow")

    errors = validate_workflow_preflight(workflow)

    assert any("workflow_ref must be a literal" in error for error in errors)


def test_sub_workflow_child_error_propagates_with_child_context(monkeypatch):
    async def failing_child(inputs, state, llm_config):
        return {"error": "child boom"}

    _install_fake_tool(monkeypatch, "fake_child", failing_child)

    with pytest.raises(Exception, match="Sub-workflow 'Child' failed"):
        asyncio.run(_run_parent(_parent_workflow(), _child_workflow()))
