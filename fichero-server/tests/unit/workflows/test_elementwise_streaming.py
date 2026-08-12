"""Elementwise Send-chaining, end to end through the REAL builder.

Pipelining lane step 2 (design: workflow-audit addendum 3; graph
semantics proven in test_send_chaining_semantics.py). With
FICHERO_STREAM_ELEMENTWISE on, a files → transcribe → extract_entities
workflow streams each item through both stages via Command(goto=Send):
the entities stage runs once PER ITEM with THAT item's transcription as
its text input — never one batched call over the aggregate. With the
flag off, today's batch shape is unchanged. A mid-chain failure
propagates a marker so downstream aggregates still reach their totals
instead of hanging the deferred-emission barrier (#837).
"""

import pytest

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef


def _workflow() -> WorkflowDef:
    return WorkflowDef(
        id="wf-streaming",
        name="Streaming Chain",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="transcribe", tool="transcribe", config={}),
            NodeDef(id="entities", tool="extract_entities", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="transcribe", source_port="files", target_port="files"),
            EdgeDef(source="transcribe", target="entities", source_port="text", target_port="text"),
        ],
    )


def _stub_tools(monkeypatch, calls: dict):
    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/a.png", "/tmp/b.png", "/tmp/c.png"], "documents": []}

    async def transcribe_tool(inputs, state, llm_config):
        files = inputs.get("files") or []
        name = files[0].rsplit("/", 1)[-1] if files else "?"
        calls.setdefault("transcribe", []).append(name)
        if name == "boom.png":
            return {"text": "", "error": "provider refused"}
        return {"text": f"text-of-{name}", "value": None}

    async def entities_tool(inputs, state, llm_config):
        calls.setdefault("entities", []).append(inputs.get("text", ""))
        return {"entities": {}, "text": inputs.get("text", ""), "value": None}

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool",
        lambda tool_name: {
            "files": files_tool,
            "transcribe": transcribe_tool,
            "extract_entities": entities_tool,
        }.get(tool_name),
    )


@pytest.mark.asyncio
async def test_flag_on_streams_each_item_through_both_stages(monkeypatch):
    monkeypatch.setenv("FICHERO_STREAM_ELEMENTWISE", "1")
    calls: dict = {}
    _stub_tools(monkeypatch, calls)

    initial = build_initial_state({}, library_path="")
    initial["workflow_id"] = "wf-streaming"
    final = await build_graph(_workflow(), enable_parallel=True).ainvoke(initial)

    # entities ran once PER ITEM, each with its own item's transcription —
    # never one batched call over the aggregate.
    assert sorted(calls["entities"]) == [
        "text-of-a.png",
        "text-of-b.png",
        "text-of-c.png",
    ]
    # Both stages aggregated: downstream consumers still see complete outputs.
    assert final.get("outputs", {}).get("transcribe") is not None
    assert final.get("outputs", {}).get("entities") is not None


@pytest.mark.asyncio
async def test_flag_off_keeps_the_batch_shape(monkeypatch):
    monkeypatch.delenv("FICHERO_STREAM_ELEMENTWISE", raising=False)
    calls: dict = {}
    _stub_tools(monkeypatch, calls)

    initial = build_initial_state({}, library_path="")
    initial["workflow_id"] = "wf-streaming"
    final = await build_graph(_workflow(), enable_parallel=True).ainvoke(initial)

    # Unchanged today-shape: one entities call over the aggregate text.
    assert len(calls["entities"]) == 1
    assert final.get("outputs", {}).get("entities") is not None


@pytest.mark.asyncio
async def test_mid_chain_failure_propagates_and_never_hangs(monkeypatch):
    monkeypatch.setenv("FICHERO_STREAM_ELEMENTWISE", "1")
    calls: dict = {}

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/a.png", "/tmp/boom.png", "/tmp/c.png"], "documents": []}

    async def transcribe_tool(inputs, state, llm_config):
        files = inputs.get("files") or []
        name = files[0].rsplit("/", 1)[-1] if files else "?"
        if name == "boom.png":
            return {"text": "", "error": "provider refused"}
        return {"text": f"text-of-{name}", "value": None}

    async def entities_tool(inputs, state, llm_config):
        calls.setdefault("entities", []).append(inputs.get("text", ""))
        return {"entities": {}, "text": inputs.get("text", ""), "value": None}

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool",
        lambda tool_name: {
            "files": files_tool,
            "transcribe": transcribe_tool,
            "extract_entities": entities_tool,
        }.get(tool_name),
    )

    initial = build_initial_state({}, library_path="")
    initial["workflow_id"] = "wf-streaming"
    final = await build_graph(_workflow(), enable_parallel=True).ainvoke(initial)

    # The failed item's marker travelled the chain: entities ran for the two
    # good items only, and the aggregate still completed (no barrier hang).
    assert sorted(calls["entities"]) == ["text-of-a.png", "text-of-c.png"]
    assert final.get("outputs", {}).get("entities") is not None
