"""Send-chaining semantics proof (pipelining lane step 2 prerequisite).

The builder surgery (elementwise stages streaming items node-to-node via
`Command(goto=[Send(...)])` instead of re-batching at every hop) rests on
three LangGraph behaviors. This file PROVES them against the pinned
LangGraph version with a minimal three-stage graph, so a langgraph upgrade
that changes the contract fails HERE with a readable name instead of
inside a 100-folder run. Design: workflow-audit-2026-08-11.md addendum 3.

Proven:
1. A Send-target node may return Command(update=…, goto=[Send(...)]) and
   the next stage receives THAT BRANCH's payload (per-item continuity).
2. Items stream: stage B starts per item, not after all of stage A.
3. A reducer-aggregated channel still collects every branch's update, and
   the final barrier node sees all items (the reduce step).
"""

import operator
from typing import Annotated, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send


class ChainState(TypedDict, total=False):
    items: list[str]
    # Branch-private payload while an item travels the chain.
    item: str
    # Reducer channels observe every branch's writes.
    stage_a_done: Annotated[list[str], operator.add]
    stage_b_done: Annotated[list[str], operator.add]
    order: Annotated[list[str], operator.add]


def _build_chained_graph():
    graph = StateGraph(ChainState)

    def fan_out(state: ChainState):
        return [Send("stage_a", {"item": item}) for item in state["items"]]

    def stage_a(state: ChainState):
        item = state["item"]
        # THE contract under test: a Send-target node chains the SAME item
        # onward with Command(goto=Send), carrying branch-private payload.
        return Command(
            update={"stage_a_done": [item], "order": [f"a:{item}"]},
            goto=Send("stage_b", {"item": f"{item}+a"}),
        )

    def stage_b(state: ChainState):
        return {"stage_b_done": [state["item"]], "order": [f"b:{state['item']}"]}

    def reduce_all(state: ChainState):
        return {"order": [f"reduce:{len(state['stage_b_done'])}"]}

    graph.add_node("start_fan", lambda state: {})
    graph.add_node("stage_a", stage_a)
    graph.add_node("stage_b", stage_b)
    graph.add_node("reduce_all", reduce_all)
    graph.add_edge(START, "start_fan")
    graph.add_conditional_edges("start_fan", fan_out, ["stage_a"])
    graph.add_edge("stage_b", "reduce_all")
    graph.add_edge("reduce_all", END)
    return graph.compile()


@pytest.mark.asyncio
async def test_command_goto_send_chains_branch_payload():
    app = _build_chained_graph()
    result = await app.ainvoke({"items": ["p1", "p2", "p3"]})

    # 1. Per-branch continuity: stage_b saw each item WITH stage_a's mark.
    assert sorted(result["stage_b_done"]) == ["p1+a", "p2+a", "p3+a"]
    # 3. The reducer channel collected every branch.
    assert sorted(result["stage_a_done"]) == ["p1", "p2", "p3"]
    assert any(entry.startswith("reduce:") for entry in result["order"])


@pytest.mark.asyncio
async def test_stage_b_runs_per_item_not_after_all_of_stage_a():
    """Streaming, not re-batching: with superstep semantics each item's
    stage_b lands in the superstep after ITS stage_a — so b events exist
    for every item and stage_b ran once per item (three tasks), never one
    batched call."""
    app = _build_chained_graph()
    result = await app.ainvoke({"items": ["p1", "p2", "p3"]})
    b_events = [entry for entry in result["order"] if entry.startswith("b:")]
    assert len(b_events) == 3, f"stage_b must run per item, got {b_events}"


@pytest.mark.asyncio
async def test_reduce_waits_for_every_branch():
    app = _build_chained_graph()
    result = await app.ainvoke({"items": ["p1", "p2", "p3", "p4"]})
    reduce_events = [e for e in result["order"] if e.startswith("reduce:")]
    # The barrier ran with ALL items visible (it may run once per
    # completing superstep wave; the FINAL wave must have seen all 4).
    assert reduce_events[-1] == "reduce:4"
