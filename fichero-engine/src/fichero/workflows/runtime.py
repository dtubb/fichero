"""
Shared workflow runtime helpers.

This module centralizes how we build/compile workflow graphs and construct
initial execution state so all entry points (single workflow execution, batch,
scheduler, watchers) can reuse one runtime path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fichero.workflows.builder import build_graph
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef


def to_workflow_def(workflow: Any) -> WorkflowDef:
    """
    Normalize a Workflow model/object into WorkflowDef.

    Accepts both:
    - WorkflowDef (returned unchanged)
    - Workflow model-like objects with .id/.name/.nodes/.edges attributes
    """
    if isinstance(workflow, WorkflowDef):
        return workflow

    def _as_mapping(obj: Any) -> dict[str, Any]:
        if isinstance(obj, dict):
            return obj
        return vars(obj)

    def _edge_def(edge: Any) -> EdgeDef:
        data = dict(_as_mapping(edge))
        aliases = {
            "sourceNodeId": "source",
            "targetNodeId": "target",
            "sourcePort": "source_port",
            "targetPort": "target_port",
        }
        for old, new in aliases.items():
            if old in data and not data.get(new):
                data[new] = data.pop(old)
        data["source_port"] = data.get("source_port") or "output"
        data["target_port"] = data.get("target_port") or "input"
        return EdgeDef.model_validate(data)

    return WorkflowDef(
        id=workflow.id,
        name=workflow.name,
        description=getattr(workflow, "description", "") or "",
        provider=getattr(workflow, "provider", "") or "",
        model=getattr(workflow, "model", "") or "",
        nodes=[
            NodeDef(
                id=_as_mapping(n)["id"],
                tool=_as_mapping(n)["tool"],
                label=_as_mapping(n).get("label", ""),
                inputs=_as_mapping(n).get("inputs", {}),
                config=_as_mapping(n).get("config", {}),
                provider_name=(
                    _as_mapping(n).get("provider_name")
                    or _as_mapping(n).get("providerName")
                    or ""
                ),
                model_name=(
                    _as_mapping(n).get("model_name")
                    or _as_mapping(n).get("modelName")
                    or ""
                ),
            )
            for n in workflow.nodes
        ],
        edges=[_edge_def(e) for e in workflow.edges],
    )


def create_compiled_app(
    workflow_def: Any,
    *,
    db_path: str | Path,
    enable_parallel: bool = True,
    event_callback: Callable | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    skip_cache: bool = False,
) -> tuple[Any, AsyncDuckDBCheckpointer]:
    """
    Build and compile a workflow app with a checkpointer.

    Returns:
        (compiled_app, checkpointer)
    """
    workflow_def = to_workflow_def(workflow_def)
    workflow_def = apply_default_provider_model(workflow_def)
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(db_path)
    app_or_graph = build_graph(
        workflow_def,
        enable_parallel=enable_parallel,
        event_callback=event_callback,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        skip_cache=skip_cache,
    )

    # Compatibility path: older call sites may receive an uncompiled graph.
    if hasattr(app_or_graph, "compile"):
        return app_or_graph.compile(checkpointer=checkpointer), checkpointer
    return app_or_graph, checkpointer


def create_compiled_app_with_checkpointer(
    workflow_def: Any,
    *,
    checkpointer: AsyncDuckDBCheckpointer,
    enable_parallel: bool = True,
    event_callback: Callable | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    skip_cache: bool = False,
) -> Any:
    """
    Build and compile a workflow app using an existing checkpointer.
    """
    workflow_def = to_workflow_def(workflow_def)
    workflow_def = apply_default_provider_model(workflow_def)
    app_or_graph = build_graph(
        workflow_def,
        enable_parallel=enable_parallel,
        event_callback=event_callback,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        skip_cache=skip_cache,
    )
    if hasattr(app_or_graph, "compile"):
        return app_or_graph.compile(checkpointer=checkpointer)
    return app_or_graph


def build_initial_state(
    inputs: dict[str, Any],
    *,
    library_path: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical initial state shape for workflow execution.
    """
    state: dict[str, Any] = {
        **inputs,
        "library_path": library_path,
        # Explicitly declare so LangGraph preserves this as a typed channel.
        # Without this, selected_doc_ids gets dropped when LangGraph initialises
        # channels from the State TypedDict.
        "selected_doc_ids": inputs.get("selected_doc_ids") or [],
    }
    if metadata:
        state["metadata"] = metadata
    return state


def apply_default_provider_model(workflow_def: WorkflowDef) -> WorkflowDef:
    """
    Populate provider/model from app defaults when workflow values are empty.
    """
    if workflow_def.provider and workflow_def.model:
        return workflow_def

    # Node workflows resolve model selection per-node in the builder. Backfilling
    # the workflow-level generic default here masks category defaults like the
    # configured vision slot, so transcribe-style presets would silently run on
    # the generic LLM instead of default_vision_provider/default_vision_model.
    if workflow_def.nodes:
        return workflow_def

    try:
        from fichero.db.app import get_app_db

        default = get_app_db().get_default_model()
        if default:
            if not workflow_def.provider:
                workflow_def.provider = default[0]
            if not workflow_def.model:
                workflow_def.model = default[1]
    except Exception:
        # Non-fatal: leave workflow-level values unchanged if defaults are unavailable.
        pass

    return workflow_def
