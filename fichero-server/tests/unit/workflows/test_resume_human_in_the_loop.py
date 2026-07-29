"""#2529: resuming a workflow paused on interrupt() with the human's answer.

The resume endpoint used to call ``ainvoke(inputs)`` unconditionally, which does
NOT deliver a value back to a LangGraph ``interrupt()`` — the human's answer was
dropped. The endpoint now picks ``Command(resume=answer)`` when an answer is
supplied. These cover the selection logic and prove the underlying LangGraph
mechanism (Command(resume=...) actually reaches interrupt()).
"""

from __future__ import annotations

from typing import TypedDict

import pytest


def test_resume_argument_uses_command_for_human_answer():
    from fichero_server.api.routes.workflow_execution.core import _resume_argument
    from fichero_server.api.routes.workflow_execution.schemas import ResumeWorkflowRequest
    from langgraph.types import Command

    arg = _resume_argument(ResumeWorkflowRequest(answer="Bogotá"))
    assert isinstance(arg, Command)
    assert arg.resume == "Bogotá"


def test_resume_argument_falls_back_to_inputs_then_none():
    from fichero_server.api.routes.workflow_execution.core import _resume_argument
    from fichero_server.api.routes.workflow_execution.schemas import ResumeWorkflowRequest

    assert _resume_argument(ResumeWorkflowRequest(inputs={"x": 1})) == {"x": 1}
    assert _resume_argument(ResumeWorkflowRequest()) is None
    assert _resume_argument(None) is None


def test_falsy_but_present_answer_still_uses_command():
    """answer=0/'' is a real answer — must resume via Command, not fall through."""
    from fichero_server.api.routes.workflow_execution.core import _resume_argument
    from fichero_server.api.routes.workflow_execution.schemas import ResumeWorkflowRequest
    from langgraph.types import Command

    arg = _resume_argument(ResumeWorkflowRequest(answer=""))
    assert isinstance(arg, Command)
    assert arg.resume == ""


@pytest.mark.asyncio
async def test_command_resume_delivers_answer_to_interrupt():
    """The mechanism the endpoint relies on: Command(resume=x) reaches interrupt()."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, interrupt

    class S(TypedDict):
        question: str
        answer: str

    def ask(state: S) -> S:
        # Pauses here; the value passed to Command(resume=...) becomes the return.
        reply = interrupt({"question": state["question"]})
        return {"answer": reply}

    graph = StateGraph(S)
    graph.add_node("ask", ask)
    graph.add_edge(START, "ask")
    graph.add_edge("ask", END)
    app = graph.compile(checkpointer=MemorySaver())

    config = {"configurable": {"thread_id": "t-hitl"}}
    first = await app.ainvoke({"question": "What does this say?"}, config=config)
    # Run is suspended on the interrupt — no answer yet.
    assert "__interrupt__" in first
    assert "answer" not in first

    resumed = await app.ainvoke(Command(resume="ilegible"), config=config)
    assert resumed["answer"] == "ilegible"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
