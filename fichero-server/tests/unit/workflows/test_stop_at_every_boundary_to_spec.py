"""`workflows.stop-cancels-at-every-boundary` (docs/contributor_manual/specs/ui/workflows.md, Step 1.4, #4402): a node's START is
a boundary too, so a Stop or Pause pressed while the node before it ran lands before a serial node's one long call, not after.

WHY: the per-item progress callback covers every looping tool, but a serial node with no loop reports no progress, so its single
call ran to the end whatever was pressed. Stop wins over Pause: a run both paused and stopped is stopped.
"""

from __future__ import annotations

import pytest

from fichero_server.execution.cancellation import (
    WorkflowCancelled,
    WorkflowPaused,
    clear_cancellation,
    clear_pause,
    request_cancellation,
    request_pause,
)
from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import _make_node_function
from fichero_server.workflows.types import NodeDef

RUN = "stop-at-node-start-run"


@pytest.fixture(autouse=True)
def _clean():
    clear_cancellation(RUN)
    clear_pause(RUN)
    yield
    clear_cancellation(RUN)
    clear_pause(RUN)


def _serial_node(calls: list):
    async def one_long_call(inputs: dict, state: dict, llm_config: LLMConfig) -> dict:
        calls.append("ran")
        return {"text": "done"}

    return _make_node_function(
        NodeDef(id="serial", tool="files", label="Serial", config={}), one_long_call,
        LLMConfig(provider="openai", model="gpt-4o-mini"), workflow_config={}, incoming_edges=[],
    )


def _state():
    return {"outputs": {}, "completed_nodes": [], "task_id": RUN}


@pytest.mark.asyncio
async def test_a_stop_pressed_before_a_serial_node_starts_stops_it_unrun():
    calls: list = []
    request_cancellation(RUN)
    with pytest.raises(WorkflowCancelled):
        await _serial_node(calls)(_state())
    assert calls == []


@pytest.mark.asyncio
async def test_a_pause_pressed_before_a_serial_node_starts_pauses_it_unrun():
    calls: list = []
    request_pause(RUN)
    with pytest.raises(WorkflowPaused):
        await _serial_node(calls)(_state())
    assert calls == []


@pytest.mark.asyncio
async def test_stop_wins_over_pause():
    request_pause(RUN)
    request_cancellation(RUN)
    with pytest.raises(WorkflowCancelled):
        await _serial_node([])(_state())


@pytest.mark.asyncio
async def test_a_run_nobody_stopped_runs_the_node():
    calls: list = []
    await _serial_node(calls)(_state())
    assert calls == ["ran"]
