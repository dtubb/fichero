"""#5372: a scheduled or file-triggered run of a STORED workflow starts.

Why it matters: the scheduler and the file watcher pass the stored workflow, whose nodes are plain
dicts, to `execute_workflow`, which handed it straight to `build_graph`; every scheduled and
file-triggered single run died with an AttributeError before doing anything, while
`ui/automation.md` tagged them as working. If this goes red, automation is silently dead again.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from fichero_server.workflows import builder
from fichero_server.workflows.types import WorkflowDef


def _stored_workflow():
    """The shape `WorkflowStore.get` returns: attributes, with nodes and edges as plain dicts."""
    return SimpleNamespace(
        id="wf-stored",
        name="Stored",
        description="",
        nodes=[{"id": "n1", "tool": "noop", "config": {}}],
        edges=[],
    )


def test_execute_workflow_accepts_a_stored_workflow_with_dict_nodes(monkeypatch):
    seen = {}

    class _Graph:
        async def ainvoke(self, state, *a, **k):
            return {**state, "completed_nodes": ["n1"]}

    def fake_build_graph(workflow, *a, **k):
        seen["type"] = type(workflow)
        return _Graph()

    monkeypatch.setattr(builder, "build_graph", fake_build_graph)
    result = asyncio.run(builder.execute_workflow(workflow=_stored_workflow(), inputs={}))
    assert seen["type"] is WorkflowDef
    assert result.get("error") is None
