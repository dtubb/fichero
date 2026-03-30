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

    return WorkflowDef(
        id=workflow.id,
        name=workflow.name,
        description=getattr(workflow, "description", "") or "",
        provider=getattr(workflow, "provider", "") or "",
        model=getattr(workflow, "model", "") or "",
        nodes=[
            NodeDef(
                id=n["id"],
                tool=n["tool"],
                label=n.get("label", ""),
                inputs=n.get("inputs", {}),
                config=n.get("config", {}),
                provider_name=n.get("provider_name", ""),
                model_name=n.get("model_name", ""),
            )
            for n in workflow.nodes
        ],
        edges=[
            EdgeDef(
                source=e.get("source") or e.get("source_node_id", ""),
                target=e.get("target") or e.get("target_node_id", ""),
                source_port=e.get("source_port", "output"),
                target_port=e.get("target_port", "input"),
            )
            for e in workflow.edges
        ],
    )


def create_compiled_app(
    workflow_def: Any,
    *,
    db_path: str | Path,
    enable_parallel: bool = True,
    event_callback: Callable | None = None,
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

    try:
        from fichero.app_db import get_app_db

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
