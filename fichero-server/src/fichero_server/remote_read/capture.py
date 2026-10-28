"""A step's capture run for a provider batch, below the run machinery (#5940; the manager's ruling, 2026-10-28, option 1).

The batch's requests must be the step's own vision calls, under the keys the real run will ask them by, so the
step's workflow is resolved, configured and validated exactly as `recipes.runner._run_workflow` does, and its graph
is run in-process under `provider_batch.capturing()`: compiled with an in-memory checkpointer, never registered as a
run (no `_set_workflow_state`, no activity row, no job), so a real run neither joins it nor counts its pages covered.
Under capture the vision tools save nothing (`vision_base.process_vision`) and nothing is called.

ponytail: the card -> workflow steps below mirror `_run_workflow` (lenses, review instructions, tool_config) and the
run body's model choice; recipes/runner.py and execution/runner.py are another lane's files today. The upgrade is one
shared builder both call; until then the route's test must pin that a capture's keys are the replay's keys.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable

from fichero_server.llm import provider_batch as pb


def stand_in(prompt: str, images: list[str]) -> str:
    """The model's place in a capture: one non-empty reading per picture, so a line reader asking for n lines parses
    n answers and asks nothing again (a re-ask would be captured, sent and billed for nothing)."""
    return json.dumps(["·"] * max(1, len(images)), ensure_ascii=False)


def step_workflow(db: Any, card: dict[str, Any], documents: list[str]) -> tuple[Any, Any]:
    """The step's workflow and request, as `_run_workflow` builds them: by the shipped preset's stable id, its lenses,
    review instructions and settings applied to this copy only."""
    from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
    from fichero_server.workflows.default_workflows import resolve_default_workflow, resolve_shipped_workflow
    from fichero_server.workflows.workflow_store import WorkflowStore

    workflow = (WorkflowStore(db).get(card["workflow_id"]) or resolve_default_workflow(card["workflow_id"])
                or resolve_shipped_workflow(db, card["workflow_id"], card["workflow"]))
    if workflow is None:
        raise LookupError(f"the shipped workflow {card['workflow']!r} is in neither this project nor the shipped defaults")
    if card.get("lenses"):
        from fichero_server.recipes.review_profiles import keep_lenses

        workflow = workflow.model_copy(deep=True)
        workflow.nodes, workflow.edges = keep_lenses(workflow.nodes, workflow.edges, card["lenses"])
    if card.get("review_instructions"):
        from fichero_server.recipes.project import read_project_setup
        from fichero_server.recipes.review_profiles import with_instructions

        workflow = workflow.model_copy(deep=True)
        workflow.nodes = with_instructions(workflow.nodes, card["review_instructions"],
                                           read_project_setup(Path(db.path).parent)["answers"])
    if card.get("tool_config"):
        workflow = workflow.model_copy(deep=True)
        for node in workflow.nodes:
            node["config"] = {**(node.get("config") or {}), **(card["tool_config"].get(node.get("tool")) or {})}
    request = ExecuteWorkflowRequest(workflow_id=workflow.id, inputs={"selected_doc_ids": list(documents)},
                                     thread_id=f"capture-{uuid.uuid4().hex[:12]}",
                                     provider_override=card["provider_override"], model_override=card["model_override"],
                                     skip_cache=True)
    return workflow, request


async def capture_step(db: Any, card: dict[str, Any], documents: list[str], *,
                       answer: Callable[[str, list[str]], str] = stand_in) -> list[pb.BatchRequest]:
    """The step's vision calls on `documents`, as batch requests; nothing is called, kept or registered."""
    from langgraph.checkpoint.memory import InMemorySaver

    from fichero_server.api.routes.workflow_execution.core import _validate_workflow_for_execution
    from fichero_server.workflows.runtime import build_initial_state, create_compiled_app_with_checkpointer, to_workflow_def

    from fichero_server.workflows.validation import apply_run_model_override

    workflow, request = step_workflow(db, card, documents)
    _validate_workflow_for_execution(workflow, request, db)  # the same preflight as the real run
    workflow = workflow.model_copy(deep=True)
    apply_run_model_override(workflow.nodes, request.provider_override, request.model_override)  # as the run body does
    app = create_compiled_app_with_checkpointer(to_workflow_def(workflow), checkpointer=InMemorySaver(),
                                                enable_parallel=True, skip_cache=True)
    state = build_initial_state(request.inputs, library_path=str(Path(db.path).parent))
    state.update(workflow_id=request.workflow_id, task_id=request.thread_id,
                 run_model_override={"provider": request.provider_override, "model": request.model_override})
    from fichero_server.llm import set_run_model_choice

    set_run_model_choice(request.provider_override, request.model_override)  # as the run body does, in this context only
    with pb.capturing(answer=answer) as calls:
        await app.ainvoke(state, {"configurable": {"thread_id": request.thread_id}})
    return calls
