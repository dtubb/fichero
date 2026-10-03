"""#5371: a step that asks a person (LangGraph interrupt(), as `ask_human` does) PAUSES the run and
waits for the answer; it does not fail it.

Why it matters: LangGraph's interrupt is an ordinary Exception subclass, and the node wrapper's
catch-all turned it into SystemicErrorDetected, so the catalogue's grouping confirmation and every
future review step failed the run instead of asking. If this goes red, human-in-the-loop is dead
again. The runner half (settling the stream as paused 'awaiting_review') is in execution/runner.py.
"""
from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.types import NodeDef, WorkflowDef


async def _asks(*args, **kwargs):
    answer = interrupt({"kind": "human_review", "question": "Which grouping?"})
    return {"answer": answer}


def test_an_interrupt_reaches_langgraph_and_the_run_resumes_with_the_answer(monkeypatch):
    monkeypatch.setattr("fichero_server.workflows.builder.get_tool", lambda name: _asks)
    workflow = WorkflowDef(id="wf-review", name="Review", nodes=[NodeDef(id="ask", tool="asks")])
    app = build_graph(workflow, enable_parallel=False, checkpointer=MemorySaver(), skip_cache=True)
    config = {"configurable": {"thread_id": "t-review"}}
    state = {"task_id": "t", "workflow_id": "wf-review", "library_path": "", "inputs": {},
             "outputs": {}, "current_node": "", "completed_nodes": [], "error": None}

    asyncio.run(app.ainvoke(state, config))  # must not raise SystemicErrorDetected
    snapshot = asyncio.run(app.aget_state(config))
    pending = [i.value for i in snapshot.interrupts] or [
        i.value for t in snapshot.tasks for i in t.interrupts]
    assert pending and pending[0]["question"] == "Which grouping?"

    asyncio.run(app.ainvoke(Command(resume="split"), config))
    assert not asyncio.run(app.aget_state(config)).next
