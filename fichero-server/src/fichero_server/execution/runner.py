"""Background workflow execution engine.

Contains:
- In-memory workflow state tracking
- Python code generation for workflows
- Background runner that streams SSE events
"""

import logging
import queue
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from fichero_server.db import Database
from fichero_server.models import Workflow
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.registry import get_tool_def

from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest, SSEEvent

logger = logging.getLogger(__name__)

# NOTE: builder / runtime are imported at CALL time, not here (#3950). Between
# them they pull langgraph (via workflows.checkpointer) and every tool. This
# module is reachable from api/routes/workflow_execution at engine startup, so
# those imports ran before the HTTP socket was ever bound.
if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero_server.workflows.builder import SystemicErrorDetected


def build_graph(*args, **kwargs):
    """Build a workflow graph, importing the builder on first call.

    A passthrough wrapper, NOT a deferred import inside the caller, and that is
    deliberate: tests do `monkeypatch.setattr(runner, "build_graph", fake)` and
    the call site resolves `build_graph` as a module global. Importing it
    locally inside `_run_workflow_in_background` would bind a LOCAL name that
    shadows the patched global — the fake would be silently ignored and those
    tests would still pass while exercising the real builder. Keeping the name
    a module attribute preserves that seam exactly (#3950).
    """
    from fichero_server.workflows.builder import build_graph as _build_graph  # noqa: PLC0415

    return _build_graph(*args, **kwargs)


# Passthrough wrappers for the runtime entry points (#3950).
#
# Deferring these imports must not remove them as MODULE ATTRIBUTES: tests
# patch `fichero_server.execution.runner.<name>`, which requires (1) the attribute to exist for
# mock.patch to find, and (2) the call site to resolve it as a module GLOBAL so
# the patch actually takes effect. A function-local import at the call site
# satisfies neither — it would let those tests pass while silently running the
# real runtime. A module __getattr__ satisfies only (1), since LOAD_GLOBAL
# inside this module never consults it. Hence wrappers.


def to_workflow_def(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.to_workflow_def; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import to_workflow_def as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def create_compiled_app(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.create_compiled_app; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import create_compiled_app as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def build_initial_state(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.build_initial_state; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import build_initial_state as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


__all__ = [
    "WorkflowEventHub",
    "_classify_provider_error",
    "_detect_empty_text_output",
    "_generate_workflow_python_code",
    "_get_workflow_state",
    "_is_internal_langchain_node",
    "_missing_exit_nodes",
    "_remove_workflow_state",
    "_run_workflow_in_background",
    "_set_workflow_state",
    "_systemic_failure_message",
]

# =============================================================================
# Background Task State
# =============================================================================

# Key: thread_id, Value: dict with workflow state and a WorkflowEventHub
# for events (the workflow runs on a worker thread — #1000)
_running_workflows: dict[str, dict[str, Any]] = {}
_RUNNING_WORKFLOWS_LIMIT = 100
_EXITED_WORKFLOW_STATUSES = {"completed", "failed", "cancelled"}


class WorkflowEventHub:
    """Fan-out pub/sub for a single workflow thread's SSE events (#2546).

    Previously ``state["events"]`` was a bare ``queue.Queue`` and the SSE
    endpoint drained it with a destructive ``.get()``. That made the stream
    **single-consumer**: whichever subscriber drained first stole the events,
    so a *second* concurrent subscriber (e.g. the Workflow editor that
    launched the run AND the Activity panel watching it) was starved — its
    live progress sat at 0%% and its log stayed empty. A subscriber that
    connected *late* (after the producer had pushed early events that another
    consumer already drained) likewise got nothing.

    This hub keeps the producer interface identical — the runner still calls
    ``.put(event)`` from its worker thread — but every SSE subscriber gets its
    OWN queue via ``.subscribe()`` and receives EVERY event. A bounded replay
    buffer lets a late subscriber catch up on what it missed. ``put(None)``
    (the existing end-of-stream sentinel) closes the hub; subscribers that
    connect after close still receive the full replay followed by the
    sentinel so their generator terminates cleanly.

    Thread-safe: the producer runs on a dedicated worker thread (#1000) and
    subscribers drain from the API event loop via ``run_in_executor``.
    """

    # Cap the replay buffer so a thousands-of-files run (each file emits
    # file_start/file_complete + log lines) can't grow it without bound. A
    # late subscriber still gets file_total/progress from recent file events,
    # which is what the live progress bar needs.
    _REPLAY_LIMIT = 2000

    def __init__(self, replay_limit: int | None = None) -> None:
        self._lock = threading.Lock()
        self._subscribers: list["queue.Queue"] = []
        self._buffer: list[Any] = []
        self._closed = False
        self._replay_limit = (
            replay_limit if replay_limit is not None else self._REPLAY_LIMIT
        )

    def put(self, event: Any) -> None:
        """Publish an event to every subscriber and the replay buffer.

        ``None`` is the end-of-stream sentinel: it closes the hub and is
        broadcast so active subscribers terminate, but it is NOT retained in
        the replay buffer (it is re-appended on subscribe-after-close).
        """
        with self._lock:
            if event is None:
                self._closed = True
            else:
                self._buffer.append(event)
                if len(self._buffer) > self._replay_limit:
                    # Drop oldest; keep the most recent window.
                    del self._buffer[: -self._replay_limit]
            for subscriber in self._subscribers:
                subscriber.put(event)

    def subscribe(self) -> "queue.Queue":
        """Register a new subscriber and return its private queue.

        The queue is pre-loaded with the replay buffer so a late subscriber
        catches up on events it missed. If the run already finished, the
        end-of-stream sentinel is appended after the replay.
        """
        sub: "queue.Queue" = queue.Queue()
        with self._lock:
            for event in self._buffer:
                sub.put(event)
            if self._closed:
                sub.put(None)
            else:
                self._subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: "queue.Queue") -> None:
        """Remove a subscriber (on SSE disconnect) so we stop feeding it."""
        with self._lock:
            try:
                self._subscribers.remove(sub)
            except ValueError:
                pass

    def snapshot(self) -> list[Any]:
        """Return the currently buffered replay events."""
        with self._lock:
            return list(self._buffer)


def _get_workflow_state(thread_id: str) -> dict[str, Any] | None:
    """Get the current state of a running workflow."""
    return _running_workflows.get(thread_id)


def _workflow_event_timeline(events: WorkflowEventHub) -> list[dict[str, Any]]:
    """Serialize the buffered SSE events for run replay."""
    timeline: list[dict[str, Any]] = []
    for event in events.snapshot():
        if event is None:
            continue
        timeline.append(event.model_dump(mode="json"))
    return timeline


def _set_workflow_state(thread_id: str, state: dict[str, Any]) -> None:
    """Update the state of a running workflow."""
    _running_workflows[thread_id] = state
    _cap_workflow_state_registry()


def _cap_workflow_state_registry() -> None:
    """Bound the in-memory workflow state registry."""
    while len(_running_workflows) > _RUNNING_WORKFLOWS_LIMIT:
        evict_id = next(
            (
                tid
                for tid, state in _running_workflows.items()
                if state.get("status") in _EXITED_WORKFLOW_STATUSES
            ),
            next(iter(_running_workflows)),
        )
        _running_workflows.pop(evict_id, None)


def _remove_workflow_state(thread_id: str) -> None:
    """Remove a workflow from tracking (after completion)."""
    _running_workflows.pop(thread_id, None)


# Internal LangChain LCEL runnables whose on_chain_start / on_chain_end
# events should NOT surface to the SSE workflow stream. (#1002)
#
# LangChain composes a single user-authored "Catalogue / Extract All"
# node out of ~10 internal Runnable nodes (RunnableSequence,
# RunnableLambda, RunnableParallel<…>, RunnableAssign<…>,
# RunnableWithFallbacks). Each fires its own start/end event ~doubling
# (with the paired log SSE) the wire volume per user node. The frontend
# already filters them out via ``activityHumanNodeName()``; we drop
# them at the source so we're not paying for the round trip.
_INTERNAL_LANGCHAIN_NAME_PREFIXES: tuple[str, ...] = ("Runnable",)


def _is_internal_langchain_node(name: str) -> bool:
    """Return True for framework-internal LCEL runnables.

    Catches ``RunnableSequence``, ``RunnableLambda``,
    ``RunnableParallel<parsed,parsing_error>``,
    ``RunnableAssign<parsed,parsing_error>``, and
    ``RunnableWithFallbacks`` — every Runnable subclass LangChain
    composes inside a single user-authored workflow node. (#1002)
    """
    return name.startswith(_INTERNAL_LANGCHAIN_NAME_PREFIXES)


def _classify_provider_error(error_text: str) -> dict[str, str]:
    """Classify provider-facing failures into stable UI categories (#732)."""
    text = (error_text or "").lower()

    if any(token in text for token in ("402", "429", "insufficient_quota", "quota", "rate limit", "rate_limit")):
        return {
            "category": "quota",
            "message": "Provider quota or rate limit reached.",
            "action": "Top up account or switch provider/model.",
        }
    if any(token in text for token in ("401", "403", "unauthorized", "invalid api key", "forbidden", "api key")):
        return {
            "category": "auth",
            "message": "Provider authentication failed.",
            "action": "Update API key in Settings.",
        }
    if any(token in text for token in ("404", "model_not_found", "model not found", "unknown model")):
        return {
            "category": "model_not_found",
            "message": "Requested model is unavailable on this provider.",
            "action": "Choose a different model.",
        }
    if any(token in text for token in ("dns", "connection", "timeout", "timed out", "network", "unreachable")):
        return {
            "category": "network",
            "message": "Could not reach provider service.",
            "action": "Check connectivity and provider status.",
        }
    if re.search(r"\b5\d\d\b", text) or "internal server error" in text:
        return {
            "category": "server",
            "message": "Provider service error.",
            "action": "Retry later or switch provider.",
        }
    return {
        "category": "unknown",
        "message": "Provider call failed.",
        "action": "Inspect detailed error and retry.",
    }


def _systemic_failure_message(e: "SystemicErrorDetected") -> tuple[str, dict[str, str]]:
    """Build a user-facing workflow failure message from a systemic error.

    #2612: provider/auth/quota failures (e.g. 402 out of credits) must
    surface a clear, actionable message in the Activity / workflow_failed
    payload, not just the generic systemic summary.
    """
    raw = str(e)
    cls = _classify_provider_error(raw)
    if cls["category"] == "unknown":
        return raw, cls
    return (
        f"{cls['message']} {cls['action']} Details: {raw}",
        cls,
    )


def _missing_exit_nodes(
    exit_node_ids: set[str],
    completed_exit_nodes: set[str],
) -> set[str]:
    """Return graph exit nodes that never completed.

    LangGraph can end the event stream without raising even when a downstream
    user node started but never produced an ``on_chain_end`` event. Treating
    that as success hides missing artifacts/KG rows from SwiftUI, so the
    runner must fail loud before recording workflow_completed.
    """
    if not exit_node_ids:
        return set()
    return set(exit_node_ids) - set(completed_exit_nodes)


# Marker the runner uses to escalate an empty run to status="failed" when the
# emptiness is caused by every file erroring (#4283) — kept as one constant so
# the reason string and the status escalation can't drift apart.
_ALL_FILES_FAILED_MARKER = "every file failed"


def _detect_empty_text_output(final_state: dict) -> tuple[bool, str]:
    """Return (is_empty, reason) when a workflow ran files but produced no text.

    Only fires when files were actually processed — a no-input workflow
    legitimately produces nothing and must not be flagged (#2244/#2245).
    """
    if not isinstance(final_state, dict):
        return False, ""
    files = final_state.get("files", [])
    if not files:
        return False, ""
    outputs = final_state.get("outputs", {})
    if not outputs:
        return True, f"Workflow processed {len(files)} file(s) but produced no output"
    node_errors: list[str] = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        if (node_output.get("text") or "").strip():
            return False, ""
        if node_output.get("artifacts"):
            return False, ""
        if node_output.get("page_records"):
            return False, ""
        results = node_output.get("results")
        if results:
            # #4283: vision tools append a {"file", "error"} result row for
            # every FAILED file (error isolation) — a results list made
            # entirely of error rows is a run where nothing happened, not
            # output. Only an entry without an error counts as real output.
            if any(
                not entry.get("error")
                for entry in results
                if isinstance(entry, dict)
            ):
                return False, ""
        if node_output.get("error"):
            node_errors.append(str(node_output["error"]))
    reason = f"Workflow processed {len(files)} file(s) but produced no text output"
    if node_errors:
        # Name the failure so a paleography run where every page failed
        # (non-vision provider, missing key, open circuit breaker) reads as
        # WHAT went wrong instead of a silent green "completed" (#4283).
        reason += f" — {_ALL_FILES_FAILED_MARKER}: {node_errors[0]}"
    return True, reason


# =============================================================================
# Python Code Generation
# =============================================================================


def _generate_workflow_python_code(workflow: Workflow) -> str:
    """
    Generate Python code for a workflow.

    Creates runnable Python code that builds and executes the workflow
    using LangGraph primitives.
    """
    # Build code
    lines = [
        '"""',
        f"Workflow: {workflow.name}",
        f"Description: {workflow.description or 'No description'}",
        f"Generated from Fichero workflow ID: {workflow.id}",
        '"""',
        "",
        "from typing import Any, TypedDict",
        "from langgraph.graph import StateGraph, START, END",
        "",
        "# Import Fichero tools (adjust imports for your environment)",
        "from fichero_server.workflows.registry import get_tool",
        "from fichero_server.llm import LLMConfig",
        "",
        "",
        "# =============================================================================",
        "# State Definition",
        "# =============================================================================",
        "",
        "class State(TypedDict, total=False):",
        '    """Workflow state passed between nodes."""',
        "    files: list[str]  # Input files",
        "    results: list[Any]  # Processing results",
        "    artifacts: list[dict]  # Generated artifacts",
        "    errors: list[str]  # Error messages",
        "    library_path: str  # Library database path",
        "",
        "",
        "# =============================================================================",
        "# Node Functions",
        "# =============================================================================",
        "",
    ]

    # Generate node functions
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        tool_name = node.get("tool", "unknown")
        label = node.get("label", tool_name)
        config = node.get("config", {})

        # Create safe function name
        func_name = f"node_{node_id.replace('-', '_')[:20]}"

        lines.extend(
            [
                f"def {func_name}(state: State) -> dict[str, Any]:",
                '    """',
                f"    Node: {label}",
                f"    Tool: {tool_name}",
                '    """',
                f'    tool_fn = get_tool("{tool_name}")',
                "    if tool_fn is None:",
                f'        return {{"errors": state.get("errors", []) + ["Tool not found: {tool_name}"]}}',
                "    ",
                "    # Get inputs from state",
                "    inputs = {",
                '        "files": state.get("files", []),',
                '        "results": state.get("results", []),',
            ]
        )

        # Add config values
        for key, value in config.items():
            if isinstance(value, str):
                lines.append(f'        "{key}": "{value}",')
            else:
                lines.append(f'        "{key}": {value!r},')

        lines.extend(
            [
                "    }",
                "    ",
                "    # Execute tool",
                "    try:",
                "        result = tool_fn(inputs)",
                "        return result",
                "    except Exception as e:",
                '        return {"errors": state.get("errors", []) + [str(e)]}',
                "",
                "",
            ]
        )

    # Build graph
    lines.extend(
        [
            "# =============================================================================",
            "# Build Graph",
            "# =============================================================================",
            "",
            "def build_workflow() -> StateGraph:",
            f'    """Build the {workflow.name} workflow graph."""',
            "    graph = StateGraph(State)",
            "    ",
            "    # Add nodes",
        ]
    )

    # Add nodes
    for node in workflow.nodes:
        node_id = node.get("id", "unknown")
        func_name = f"node_{node_id.replace('-', '_')[:20]}"
        lines.append(f'    graph.add_node("{node_id}", {func_name})')

    lines.append("    ")
    lines.append("    # Add edges")

    # Determine entry nodes (nodes with no incoming edges)
    target_nodes = set(
        e.get("target") or e.get("target_node_id", "") for e in workflow.edges
    )
    source_nodes = set(
        e.get("source") or e.get("source_node_id", "") for e in workflow.edges
    )
    all_node_ids = set(n.get("id", "") for n in workflow.nodes)
    entry_nodes = all_node_ids - target_nodes

    # Add START edges
    for entry_node in entry_nodes:
        if entry_node:
            lines.append(f'    graph.add_edge(START, "{entry_node}")')

    # Add workflow edges
    for edge in workflow.edges:
        source = edge.get("source") or edge.get("source_node_id", "")
        target = edge.get("target") or edge.get("target_node_id", "")
        if source and target:
            lines.append(f'    graph.add_edge("{source}", "{target}")')

    # Determine exit nodes (nodes with no outgoing edges)
    exit_nodes = all_node_ids - source_nodes

    # Add END edges
    for exit_node in exit_nodes:
        if exit_node:
            lines.append(f'    graph.add_edge("{exit_node}", END)')

    lines.extend(
        [
            "    ",
            "    return graph",
            "",
            "",
            "# =============================================================================",
            "# Main Execution",
            "# =============================================================================",
            "",
            'if __name__ == "__main__":',
            "    # Build and compile the graph",
            "    graph = build_workflow()",
            "    app = graph.compile()",
            "    ",
            "    # Example execution",
            "    initial_state = {",
            '        "files": [],  # Add your input files here',
            '        "results": [],',
            '        "artifacts": [],',
            '        "errors": [],',
            '        "library_path": "",  # Set your library path',
            "    }",
            "    ",
            "    # Run the workflow",
            "    final_state = app.invoke(initial_state)",
            "    ",
            "    # Print results",
            '    print("Results:", final_state.get("results", []))',
            '    print("Artifacts:", final_state.get("artifacts", []))',
            '    if final_state.get("errors"):',
            '        print("Errors:", final_state["errors"])',
        ]
    )

    return "\n".join(lines)


# =============================================================================
# Background Execution
# =============================================================================


async def _run_workflow_in_background(
    thread_id: str,
    workflow: Workflow,
    request: ExecuteWorkflowRequest,
    db: Database,
) -> None:
    """
    Run a workflow in the background, publishing events to the event hub.

    Runs on a dedicated worker thread with its own event loop (#1000),
    spawned from the /execute route. Events go into
    ``_running_workflows[thread_id]["events"]`` — a thread-safe
    :class:`WorkflowEventHub` that fans them out to every SSE subscriber
    (#2546). The producer interface is unchanged: ``.put(event)``.
    """
    # SystemicErrorDetected is caught below; an `except` clause is a global
    # lookup, so it must be bound in this scope. The runtime entry points are
    # NOT imported here — they are module-level passthroughs above, because
    # tests patch them (#3950).
    from fichero_server.workflows.builder import SystemicErrorDetected  # noqa: PLC0415

    # Re-acquire the Database on THIS worker thread. The `db` passed in
    # belongs to the API thread, and a DuckDB Connection is not
    # thread-safe — db_manager keys connections by thread, so this
    # returns a fresh connection to the same file for the worker. Tool
    # nodes likewise get their own connection via db_manager. (#1000)
    if hasattr(db, "path"):
        from fichero_server.db.manager import db_manager
        db = db_manager.get_database(db.path.parent)

    # Get the event hub for this thread
    state = _get_workflow_state(thread_id)
    if not state:
        logger.error(f"No workflow state found for thread {thread_id}")
        return

    event_queue: "WorkflowEventHub" = state["events"]
    workflow_id = request.workflow_id

    # Activity tracking
    activity_tracker = get_activity_tracker(str(db.path))
    start_time = datetime.now(timezone.utc)
    node_start_times: dict[str, datetime] = {}
    execution_log_lines: list[str] = []  # Collect execution logs
    progress_timeline: dict[str, Any] = {
        "nodes": {},
        "steps": [],
    }  # Capture progress for historical viewing

    async def log_execution(message: str) -> None:
        """Log a message to both console and execution log, and stream via SSE."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        execution_log_lines.append(log_line)
        print(log_line)
        # Stream log line to frontend
        event_queue.put(
            SSEEvent(
                event="log",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"line": log_line},
            )
        )

    # Predeclared so the terminal-path document finalizer (#4315) can reach the
    # checkpointer/config even when the failure happened before graph build.
    checkpointer = None
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": request.checkpoint_ns,
        }
    }

    async def _finalize_documents(final_status: str, **result_extra: Any) -> None:
        """Settle this run's documents on a non-success terminal path (#4315).

        Cancelled/failed runs used to skip complete_run_documents entirely,
        stranding every touched document at Status.processing forever.
        Best-effort: a finalize failure must never mask the terminal outcome.
        """
        try:
            from fichero_server.workflows.completion import (  # noqa: PLC0415
                collect_processed_document_ids,
                finalize_run_documents,
            )

            terminal_state: dict[str, Any] = {}
            if checkpointer is not None:
                try:
                    tup = await checkpointer.aget_tuple(config)
                    if tup:
                        terminal_state = (
                            tup.checkpoint.get("channel_values") or {}
                        )
                except Exception as ckpt_exc:
                    logger.warning(
                        "finalize(%s): checkpoint read failed for %s: %s",
                        final_status,
                        thread_id,
                        ckpt_exc,
                    )
            doc_ids = collect_processed_document_ids(terminal_state)
            settled = finalize_run_documents(
                db,
                doc_ids,
                final_status,
                workflow_run={
                    "thread_id": thread_id,
                    "workflow_id": workflow_id,
                    "workflow_name": workflow.name,
                    "provider": workflow.provider,
                    "model": workflow.model,
                    "result": {"status": final_status, **result_extra},
                    "started_at": start_time,
                    "completed_at": datetime.now(timezone.utc),
                },
            )
            if settled:
                logger.info(
                    "Run %s %s: settled %d document(s) out of processing",
                    thread_id,
                    final_status,
                    settled,
                )
        except Exception as finalize_exc:  # pragma: no cover - defensive
            logger.warning(
                "Terminal document finalize (%s) failed for %s: %s",
                final_status,
                thread_id,
                finalize_exc,
            )

    try:
        # Mark as running
        state["status"] = "running"

        await log_execution(f"Starting workflow '{workflow.name}'")

        # Log activity: workflow started
        activity_tracker.workflow_started(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            input_count=len(request.inputs),
        )
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="running",
        )

        # Send start event
        event_queue.put(
            SSEEvent(
                event="start",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={"workflow_name": workflow.name, "inputs": request.inputs},
            )
        )

        # Optional run-level provider/model override from UI context menus (#797).
        # Applied only to LLM-using nodes so source/logic nodes remain unchanged.
        if request.provider_override or request.model_override:
            provider_override = (request.provider_override or "").strip()
            model_override = (request.model_override or "").strip()
            for node in workflow.nodes:
                tool_name = node.get("tool", "")
                tool_def = get_tool_def(tool_name) if tool_name else None
                uses_llm = bool(tool_def and tool_def.uses_llm)
                if not uses_llm:
                    continue
                if provider_override:
                    node["provider_name"] = provider_override
                if model_override:
                    node["model_name"] = model_override

        # Build workflow using the shared runtime conversion path.
        workflow_def = to_workflow_def(workflow)

        # Generate and save Python code
        await log_execution("Generating Python code for workflow")
        python_code = _generate_workflow_python_code(workflow)

        # Create workflow snapshot for historical visualization (even if workflow is deleted)
        await log_execution("Creating workflow snapshot")
        # #4314: persist the FULL node shape, not a trimmed {id, tool, label}
        # projection. This snapshot upserts over the one /execute saved (via
        # COALESCE), and it is the only durable record of the per-node
        # config/prompt and the provider/model actually used (run-level
        # overrides were applied to workflow.nodes above, so these are the
        # effective values) — editing the live Workflow later must not change
        # what the run record reports.
        workflow_snapshot = {
            "nodes": [
                {
                    "id": n["id"],
                    "tool": n["tool"],
                    "label": n.get("label", ""),
                    "config": n.get("config", {}) or {},
                    "inputs": n.get("inputs", {}) or {},
                    "provider_name": (
                        n.get("provider_name") or n.get("providerName") or ""
                    ),
                    "model_name": n.get("model_name") or n.get("modelName") or "",
                }
                for n in workflow.nodes
            ],
            "edges": [
                {
                    "source": e.get("source") or e.get("source_node_id", ""),
                    "target": e.get("target") or e.get("target_node_id", ""),
                }
                for e in workflow.edges
            ],
            "inputs": request.inputs,
        }

        # Build node name mapping (UUID → readable name)
        await log_execution("Building node name mapping")
        node_name_map = {}
        name_counts = {}
        for node in workflow.nodes:
            node_id = node["id"]
            base_name = node.get("label") or node["tool"].replace("_", " ").title()

            # Handle duplicate names with numbering
            if base_name in name_counts:
                name_counts[base_name] += 1
                unique_name = f"{base_name} {name_counts[base_name]}"
            else:
                name_counts[base_name] = 1
                unique_name = base_name

            node_name_map[node_id] = unique_name

        # Generate Mermaid diagram for historical viewing
        await log_execution("Generating workflow diagram")
        try:
            app_preview = build_graph(
                workflow_def, enable_parallel=True, checkpointer=None
            )
            diagram_mermaid = app_preview.get_graph().draw_mermaid()
        except Exception as e:
            logger.warning(f"Could not generate diagram: {e}")
            diagram_mermaid = None

        # Save workflow run with all metadata
        await activity_tracker.store.save_workflow_run(
            thread_id=thread_id,
            workflow_id=workflow_id,
            workflow_name=workflow.name,
            python_code=python_code,
            workflow_snapshot=workflow_snapshot,
            node_name_map=node_name_map,
            diagram_mermaid=diagram_mermaid,
            started_at=start_time,
        )
        await log_execution("Saved workflow run record with snapshot")

        # Create event callback for parallel processing events
        async def emit_parallel_event(event_type: str, data: dict) -> None:
            """Callback to emit SSE events from parallel node processing."""
            if event_type == "log":
                await log_execution(str(data.get("message") or data.get("line") or ""))
                return

            event_payload = {
                k: v
                for k, v in data.items()
                if k
                not in {
                    "node_id",
                    "file_path",
                    "file_index",
                    "file_total",
                    "progress",
                    "document_id",
                    "page_id",
                    "display_name",
                    "sequence",
                }
            }
            if event_type == "file_error":
                cls = _classify_provider_error(str(data.get("error", "")))
                event_payload["error_category"] = cls["category"]
                event_payload["error_hint"] = cls["message"]
                event_payload["error_action"] = cls["action"]

            # Emit SSE event (existing behavior)
            event_queue.put(
                SSEEvent(
                    event=event_type,
                    thread_id=thread_id,
                    workflow_id=workflow_id,
                    node_id=data.get("node_id", ""),
                    file_path=data.get("file_path"),
                    file_index=data.get("file_index"),
                    file_total=data.get("file_total"),
                    progress=data.get("progress"),
                    document_id=data.get("document_id"),
                    page_id=data.get("page_id"),
                    display_name=data.get("display_name"),
                    sequence=data.get("sequence"),
                    data=event_payload,
                )
            )

            # Capture file-level timeline for historical viewing and log to console
            if event_type == "file_start":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                # Extract just the filename for cleaner logging
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                await log_execution(
                    f"  Processing file {file_index}/{file_total}: {file_name}"
                )

                progress_timeline["steps"].append(
                    {
                        "type": "file",
                        "node_id": data.get("node_id", ""),
                        "file_path": file_path,
                        "document_id": data.get("document_id"),
                        "page_id": data.get("page_id"),
                        "file_index": file_index,
                        "file_total": file_total,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "status": "running",
                    }
                )
            elif event_type == "file_complete":
                file_index = data.get("file_index", 0)
                file_total = data.get("file_total", 0)
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"

                # Find and update the matching file entry
                duration_ms = 0
                for entry in reversed(progress_timeline["steps"]):
                    if (
                        entry.get("type") == "file"
                        and entry.get("node_id") == data.get("node_id", "")
                        and entry.get("page_id") == data.get("page_id")
                        and entry.get("file_path") == file_path
                        and entry.get("status") == "running"
                    ):
                        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                        entry["status"] = "success"
                        # Calculate duration
                        start = datetime.fromisoformat(entry["started_at"])
                        duration_ms = (
                            datetime.now(timezone.utc) - start
                        ).total_seconds() * 1000
                        entry["duration_ms"] = duration_ms
                        break

                await log_execution(
                    f"  File {file_index}/{file_total} completed: {file_name} ({duration_ms:.0f}ms)"
                )
            elif event_type == "file_error":
                file_path = data.get("file_path", "")
                file_name = file_path.split("/")[-1] if file_path else "unknown"
                error_msg = data.get("error", "Unknown error")
                cls = _classify_provider_error(str(error_msg))
                await log_execution(
                    f"  ERROR processing {file_name}: {error_msg} [{cls['category']}]"
                )

                # Find and update the matching file entry
                for entry in reversed(progress_timeline["steps"]):
                    if (
                        entry.get("type") == "file"
                        and entry.get("node_id") == data.get("node_id", "")
                        and entry.get("page_id") == data.get("page_id")
                        and entry.get("file_path") == file_path
                        and entry.get("status") == "running"
                    ):
                        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                        entry["status"] = "error"
                        entry["error"] = error_msg
                        entry["error_category"] = cls["category"]
                        break
            elif event_type == "parallel_complete":
                # Save aggregate stats for the node
                progress_timeline["nodes"][data.get("node_id", "")] = {
                    "total_files": data.get("total", 0),
                    "success_count": data.get("success_count", 0),
                    "error_count": data.get("error_count", 0),
                }

        # Build graph with shared runtime path (same engine used by batch execution).
        app, checkpointer = create_compiled_app(
            workflow_def,
            db_path=db.path,
            # Graph-level parallel fan-out is now ON for the live run path
            # (#2532/#2541 C3). The #1665/#1668 fear — the Send fan-out
            # checkpointing a completed aggregate but never scheduling the
            # downstream node under astream_events — is covered by a
            # checkpointer-backed regression suite that drives the REAL fan-out
            # through the SAME astream_events v2 entry point this runner uses:
            # tests/unit/workflows/test_parallel_checkpointer_resume.py proves
            # downstream scheduling (minimal + real Catalogue topology),
            # mid-fan-out resume (each branch exactly once), and the per-page
            # save contract. Peak heavy memory is bounded by the vision
            # semaphore (builder._get_vision_semaphore, cap 4), so this scales
            # to thousands of files. (model_comparison.py is intentionally left
            # sequential — out of scope for this flip.)
            enable_parallel=True,
            event_callback=emit_parallel_event,
            interrupt_before=request.interrupt_before or None,
            interrupt_after=request.interrupt_after or None,
            skip_cache=request.skip_cache,
        )

        # Execute with streaming
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": request.checkpoint_ns,
            }
        }

        # Build initial state with library_path. Include workflow_id so it
        # survives into checkpoint["channel_values"] — CheckpointMetadata is
        # LangGraph-internal (source/step/parents/run_id) and never carries
        # user data, so this is the only durable place for it (#1079).
        initial_state = build_initial_state(
            request.inputs,
            library_path=str(db.path.parent) if hasattr(db, "path") else "",
        )
        initial_state["workflow_id"] = request.workflow_id
        # #4313: the run's thread_id IS the run id. Tools read task_id from
        # state when saving artifacts (Artifact.run_id), and the fan-out Send
        # payloads already propagate it — so every artifact a live run
        # produces is traceable via GET /threads/{id}/run.run_artifacts.
        initial_state["task_id"] = thread_id

        # Identify exit nodes (nodes with no outgoing edges). Workflow edges
        # use raw node IDs, but LangGraph events use the display label when one
        # exists, so completion tracking must compare against event names.
        exit_node_event_names = set()
        all_source_nodes = {
            e.get("source") or e.get("source_node_id", "") for e in workflow.edges
        }
        for node in workflow.nodes:
            node_id = node.get("id", "")
            if node_id and node_id not in all_source_nodes:
                exit_node_event_names.add(node.get("label") or node_id)

        def _normalize_node_name(name: str) -> str:
            """Strip LangGraph internal suffixes to get the original node ID."""
            if name.endswith("_aggregate"):
                return name[: -len("_aggregate")]
            if name.endswith("_process"):
                return name[: -len("_process")]
            return name


        logger.debug(f"Exit nodes for completion: {exit_node_event_names}")
        completed_exit_nodes = set()

        # Stream execution events
        async for event in app.astream_events(
            initial_state,
            config=config,
            version="v2",
        ):
            if state.get("pause_requested"):
                state["status"] = "paused"
                await log_execution(
                    f"Workflow '{workflow.name}' paused by user "
                    f"(thread_id={thread_id})"
                )
                event_queue.put(
                    SSEEvent(
                        event="pause",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        data={"reason": "user_requested"},
                    )
                )
                activity_tracker.workflow_paused(
                    workflow_id=workflow_id,
                    thread_id=thread_id,
                    workflow_name=workflow.name,
                )
                progress_timeline["events"] = _workflow_event_timeline(event_queue)
                await activity_tracker.store.update_workflow_run(
                    thread_id=thread_id,
                    status="paused",
                    execution_log="\n".join(execution_log_lines),
                    progress_timeline=progress_timeline,
                )
                return

            # #1127 — cancellation check. If the user POSTed
            # /threads/{id}/cancel, the cancel endpoint sets
            # state["cancel_requested"]=True. Break out of the stream;
            # the LangGraph checkpointer has already persisted partial
            # results (per the issue invariant: "partial results are
            # NOT rolled back"), and the activity tracker emits a
            # workflow_cancelled event in the surrounding finally.
            if state.get("cancel_requested"):
                state["status"] = "cancelled"
                await log_execution(
                    f"Workflow '{workflow.name}' cancelled by user "
                    f"(thread_id={thread_id}) — partial results "
                    f"preserved"
                )
                event_queue.put(
                    SSEEvent(
                        event="cancelled",
                        thread_id=thread_id,
                        workflow_id=workflow_id,
                        data={"reason": "user_requested"},
                    )
                )
                activity_tracker.workflow_cancelled(
                    workflow_id=workflow_id,
                    thread_id=thread_id,
                    workflow_name=workflow.name,
                    duration_ms=(
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds()
                    * 1000,
                    partial_results_preserved=True,
                )
                progress_timeline["events"] = _workflow_event_timeline(event_queue)
                await activity_tracker.store.update_workflow_run(
                    thread_id=thread_id,
                    status="cancelled",
                    execution_log="\n".join(execution_log_lines),
                    progress_timeline=progress_timeline,
                    duration_ms=(
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds()
                    * 1000,
                    completed_at=datetime.now(timezone.utc),
                )
                # #4315: cancelled runs must not strand documents at
                # Status.processing — revert them to pending with provenance.
                await _finalize_documents("cancelled", reason="user_requested")
                return

            event_kind = event.get("event", "")

            if event_kind == "on_chain_start" and event.get("name"):
                node_name = event.get("name", "")
                if (
                    node_name not in ("__start__", "LangGraph")
                    and not _is_internal_langchain_node(node_name)
                ):
                    node_start_times[node_name] = datetime.now(timezone.utc)
                    original_id = _normalize_node_name(node_name)

                    # Skip node_begin for _aggregate (internal — the node already started with _process)
                    if node_name.endswith("_aggregate"):
                        continue

                    if node_name.endswith("_process"):
                        # Each parallel invocation fires its own on_chain_start.
                        # Extract context from state so the log shows subject + progress.
                        input_state = event.get("data", {}).get("input", {})
                        parallel_file = input_state.get("parallel_file", "")
                        parallel_index = input_state.get("parallel_index")
                        parallel_total = input_state.get("parallel_total")
                        filename = Path(parallel_file).name if parallel_file else ""

                        # Detect entity-based processing: entity names lack "/" (file paths have them).
                        is_entity = parallel_file and "/" not in parallel_file and filename

                        if filename and parallel_index is not None and parallel_total is not None:
                            if is_entity:
                                await log_execution(
                                    f"Node '{original_id}' — Extracting claims: {filename} ({parallel_index + 1}/{parallel_total})"
                                )
                            else:
                                await log_execution(
                                    f"Node '{original_id}' — {filename} ({parallel_index + 1}/{parallel_total})"
                                )
                        else:
                            await log_execution(f"Node '{original_id}' started")
                    else:
                        await log_execution(f"Node '{original_id}' started")

                    # Log activity: node started
                    activity_tracker.node_started(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=original_id,
                        node_name=original_id,
                    )

                    # Capture node start to progress timeline
                    progress_timeline["steps"].append(
                        {
                            "node_id": original_id,
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "status": "running",
                        }
                    )

                    event_queue.put(
                        SSEEvent(
                            event="node_begin",
                            thread_id=thread_id,
                            workflow_id=workflow_id,
                            node_id=original_id,
                            data={"node": original_id},
                        )
                    )

            elif event_kind == "on_chain_end" and event.get("name"):
                node_name = event.get("name", "")
                output = event.get("data", {}).get("output", {})

                if (
                    node_name not in ("__start__", "LangGraph")
                    and not _is_internal_langchain_node(node_name)
                ):
                    original_id = _normalize_node_name(node_name)

                    # Skip node_end for _process (node isn't done until _aggregate finishes)
                    if node_name.endswith("_process"):
                        continue

                    # Calculate node duration (use _process start time if this is _aggregate)
                    process_name = (
                        f"{original_id}_process"
                        if node_name.endswith("_aggregate")
                        else node_name
                    )
                    node_start = node_start_times.get(
                        process_name,
                        node_start_times.get(node_name, datetime.now(timezone.utc)),
                    )
                    node_duration_ms = (
                        datetime.now(timezone.utc) - node_start
                    ).total_seconds() * 1000

                    # Build activity metadata from output
                    activity_metadata = {}
                    node_status = "success"
                    node_end_data = {
                        "node": original_id,
                        "duration_ms": node_duration_ms,
                    }

                    # Check for parallel processing completion
                    if isinstance(output, dict) and "parallel_results" in output:
                        results = output.get("parallel_results", {})
                        for node_id, file_results in results.items():
                            success_count = sum(
                                1 for r in file_results if r.get("success")
                            )
                            error_count = len(file_results) - success_count
                            event_queue.put(
                                SSEEvent(
                                    event="parallel_complete",
                                    thread_id=thread_id,
                                    workflow_id=workflow_id,
                                    node_id=node_id,
                                    data={
                                        "success_count": success_count,
                                        "error_count": error_count,
                                        "total": len(file_results),
                                    },
                                )
                            )
                            # Add to activity metadata
                            activity_metadata["success_count"] = success_count
                            activity_metadata["error_count"] = error_count
                            activity_metadata["total_files"] = len(file_results)

                    # Extract useful metadata from output
                    if isinstance(output, dict):
                        # Files processed
                        if "files" in output:
                            files = output["files"]
                            if isinstance(files, list):
                                activity_metadata["files_processed"] = len(files)

                        # Artifacts created
                        if "artifacts" in output:
                            artifacts = output["artifacts"]
                            if isinstance(artifacts, list):
                                activity_metadata["artifacts_created"] = len(artifacts)

                        # Text/results count
                        if "results" in output:
                            results = output["results"]
                            if isinstance(results, list):
                                activity_metadata["results_count"] = len(results)

                        # Output files
                        if "output_files" in output:
                            output_files = output["output_files"]
                            if isinstance(output_files, list):
                                activity_metadata["output_files"] = len(output_files)

                        # Error from output
                        if "error" in output and output["error"]:
                            activity_metadata["error"] = str(output["error"])[:200]

                        # #2613: a node that intentionally skipped (e.g. empty-query
                        # reference search) should surface a clear skipped status.
                        if isinstance(output, dict) and output.get("skipped"):
                            node_status = "skipped"
                            skip_reason = str(output.get("skip_reason", "skipped"))
                            activity_metadata["skipped"] = True
                            activity_metadata["skip_reason"] = skip_reason
                            node_end_data["status"] = "skipped"
                            node_end_data["skip_reason"] = skip_reason
                            await log_execution(
                                f"Node '{original_id}' skipped — {skip_reason} "
                                f"({node_duration_ms:.0f}ms)"
                            )
                        else:
                            await log_execution(
                                f"Node '{original_id}' completed in {node_duration_ms:.0f}ms"
                            )

                    # Log activity: node completed/skipped
                    activity_tracker.node_completed(
                        workflow_id=workflow_id,
                        thread_id=thread_id,
                        node_id=original_id,
                        node_name=original_id,
                        duration_ms=node_duration_ms,
                        **activity_metadata,
                    )

                    # Update progress timeline with node completion
                    for entry in reversed(progress_timeline["steps"]):
                        if (
                            entry.get("node_id") == original_id
                            and entry.get("status") == "running"
                            and entry.get("type") is None
                        ):  # Only update node steps, not file steps
                            entry["completed_at"] = datetime.now(
                                timezone.utc
                            ).isoformat()
                            entry["status"] = node_status
                            entry["duration_ms"] = node_duration_ms
                            # Add metadata
                            if "files_processed" in activity_metadata:
                                entry["files_processed"] = activity_metadata[
                                    "files_processed"
                                ]
                            if "artifacts_created" in activity_metadata:
                                entry["artifacts_created"] = activity_metadata[
                                    "artifacts_created"
                                ]
                            if node_status == "skipped":
                                entry["skip_reason"] = activity_metadata.get(
                                    "skip_reason", ""
                                )
                            break

                    event_queue.put(
                        SSEEvent(
                            event="node_end",
                            thread_id=thread_id,
                            workflow_id=workflow_id,
                            node_id=original_id,
                            data=node_end_data,
                        )
                    )

                    # #4314: flush the timeline at every node boundary, not
                    # only at terminal transitions — a crash/kill mid-run used
                    # to lose the WHOLE timeline. Best-effort: a flush failure
                    # must never fail the run.
                    try:
                        await activity_tracker.store.update_workflow_run(
                            thread_id=thread_id,
                            progress_timeline=progress_timeline,
                            execution_log="\n".join(execution_log_lines),
                        )
                    except Exception as flush_exc:
                        logger.warning(
                            "progress_timeline node-boundary flush failed for "
                            "%s: %s",
                            thread_id,
                            flush_exc,
                        )

                    # Track exit node completion (using normalized ID)
                    if original_id in exit_node_event_names:
                        completed_exit_nodes.add(original_id)
                        logger.info(
                            f"Exit node completed: {original_id}, {len(completed_exit_nodes)}/{len(exit_node_event_names)}"
                        )

        # Get final state
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        final_state = (
            checkpoint_tuple.checkpoint.get("channel_values")
            if checkpoint_tuple
            else {}
        )

        missing_exit_nodes = _missing_exit_nodes(
            exit_node_event_names,
            completed_exit_nodes,
        )
        if missing_exit_nodes:
            missing_list = ", ".join(sorted(missing_exit_nodes))
            raise RuntimeError(
                "Workflow stream ended before exit node(s) completed: "
                f"{missing_list}"
            )

        # Store final state
        state["status"] = "completed"
        state["final_state"] = final_state

        # Calculate total duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        # Build completion metadata from final state
        completion_metadata = {
            "nodes_completed": len(completed_exit_nodes),
        }

        # Extract stats from final state
        if isinstance(final_state, dict):
            # Count files processed
            if "files" in final_state:
                files = final_state["files"]
                if isinstance(files, list):
                    completion_metadata["total_files"] = len(files)

            # Count artifacts
            if "artifacts" in final_state:
                artifacts = final_state["artifacts"]
                if isinstance(artifacts, list):
                    completion_metadata["total_artifacts"] = len(artifacts)

            # Count results
            if "results" in final_state:
                results = final_state["results"]
                if isinstance(results, list):
                    completion_metadata["total_results"] = len(results)

        # #2244/#2245: detect runs that processed files but produced no text output
        _empty, _empty_reason = _detect_empty_text_output(final_state or {})
        # #4283: an every-file-failed run (non-vision provider, missing key,
        # open circuit breaker…) used to be recorded status="completed" — the
        # green checkmark for a run that did NOTHING. Record it failed with
        # the aggregated per-file error so every activity surface shows it.
        _all_files_failed = _empty and _ALL_FILES_FAILED_MARKER in _empty_reason
        if _empty:
            completion_metadata["empty_output"] = True
            completion_metadata["empty_output_reason"] = _empty_reason
            await log_execution(f"Warning: {_empty_reason}")

        # Now that the WHOLE workflow has finished, flip the documents this run
        # processed (and their page children) from processing → completed. Tool
        # nodes leave docs in `processing` mid-pipeline so the per-page green
        # check no longer appears after just transcription (#1282). Scoped to
        # this run's own documents so it can't complete a concurrent run's
        # still-in-progress pages.
        try:
            from fichero_server.workflows.completion import (
                collect_processed_document_ids,
                complete_run_documents,
            )

            run_doc_ids = collect_processed_document_ids(final_state)
            completed_count = complete_run_documents(
                db,
                run_doc_ids,
                workflow_run={
                    "thread_id": thread_id,
                    "workflow_id": workflow_id,
                    "workflow_name": workflow.name,
                    "provider": workflow.provider,
                    "model": workflow.model,
                    "result": {
                        "status": "completed",
                        **completion_metadata,
                    },
                    "started_at": start_time,
                    "completed_at": datetime.now(timezone.utc),
                },
            )
            if completed_count:
                await log_execution(
                    f"Marked {completed_count} document(s) completed"
                )
            # The document.updated change-stream broadcast lives inside
            # complete_run_documents (centralised so both the main and batch
            # paths emit) — see completion.py (#2518).
        except Exception as completion_exc:  # pragma: no cover - defensive
            logger.warning(
                f"Per-document completion failed for workflow {workflow_id}: "
                f"{completion_exc}"
            )

        # Log activity: workflow completed
        activity_tracker.workflow_completed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            duration_ms=total_duration_ms,
            **completion_metadata,
        )

        await log_execution(
            f"Workflow completed successfully in {total_duration_ms:.0f}ms"
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        complete_data: dict = {
            "checkpoint_id": checkpoint_tuple.checkpoint["id"]
            if checkpoint_tuple
            else None,
            "final_state": final_state,
            "duration_ms": total_duration_ms,
        }
        if completion_metadata.get("empty_output"):
            complete_data["empty_output"] = True
            complete_data["empty_output_reason"] = completion_metadata.get(
                "empty_output_reason", ""
            )
        if _all_files_failed:
            complete_data["error"] = _empty_reason
        event_queue.put(
            SSEEvent(
                event="complete",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data=complete_data,
            )
        )
        progress_timeline["events"] = _workflow_event_timeline(event_queue)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            # #4283: every-file-failed runs are FAILURES in the activity
            # record — never a green "completed" for a run that did nothing.
            status="failed" if _all_files_failed else "completed",
            error=_empty_reason if _all_files_failed else None,
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            completed_at=datetime.now(timezone.utc),
        )

    except SystemicErrorDetected as e:
        logger.error(f"Systemic error in background workflow {workflow_id}: {e}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        await log_execution(
            f"SYSTEMIC ERROR: {e.error_count}/{e.total_count} consecutive failures"
        )
        await log_execution(f"Sample errors: {e.errors[:3] if e.errors else []}")

        # #2612: surface the underlying provider/auth/quota message in Activity.
        failure_message, failure_cls = _systemic_failure_message(e)

        # Log activity: workflow failed (systemic error)
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=failure_message,
            duration_ms=total_duration_ms,
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        event_queue.put(
            SSEEvent(
                event="systemic_error",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={
                    "error": str(e),
                    "error_count": e.error_count,
                    "total_count": e.total_count,
                    "sample_errors": e.errors[:5] if e.errors else [],
                    "error_category": failure_cls["category"],
                    "error_message": failure_cls["message"],
                    "error_action": failure_cls["action"],
                },
            )
        )
        progress_timeline["events"] = _workflow_event_timeline(event_queue)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="failed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            error=failure_message,
            completed_at=datetime.now(timezone.utc),
        )
        # #4315: failed runs revert their processing documents to pending.
        await _finalize_documents("failed", error=str(e)[:500])

    except Exception as e:
        logger.exception(f"Background workflow error for {workflow_id}")
        state["status"] = "failed"
        state["error"] = str(e)

        # Calculate duration
        total_duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        await log_execution(f"ERROR: {str(e)}")

        # Log activity: workflow failed
        activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name=workflow.name,
            error=str(e),
            duration_ms=total_duration_ms,
        )

        # Save execution log and progress timeline to workflow run
        execution_log = "\n".join(execution_log_lines)
        event_queue.put(
            SSEEvent(
                event="error",
                thread_id=thread_id,
                workflow_id=workflow_id,
                data={
                    "error": str(e),
                    "error_category": _classify_provider_error(str(e))["category"],
                },
            )
        )
        progress_timeline["events"] = _workflow_event_timeline(event_queue)
        await activity_tracker.store.update_workflow_run(
            thread_id=thread_id,
            status="failed",
            execution_log=execution_log,
            progress_timeline=progress_timeline,
            duration_ms=total_duration_ms,
            error=str(e),
            completed_at=datetime.now(timezone.utc),
        )
        # #4315: failed runs revert their processing documents to pending.
        await _finalize_documents("failed", error=str(e)[:500])

    finally:
        # Signal end of stream
        event_queue.put(None)  # Sentinel to signal stream end

        # No-op under the single shared connection model (#2508): the worker
        # thread does not own a per-thread connection to release. Kept for the
        # daemon-thread teardown seam; close_current_thread() is a no-op.
        try:
            from fichero_server.db.manager import db_manager
            db_manager.close_current_thread()
        except Exception as exc:
            logger.warning("worker-thread db cleanup failed: %s", exc)
