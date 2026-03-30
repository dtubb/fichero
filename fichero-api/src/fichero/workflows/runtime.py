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
