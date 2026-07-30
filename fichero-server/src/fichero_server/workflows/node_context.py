"""Per-node execution context for artifact provenance (#4313).

The live workflow runner threads ``task_id`` (the run's thread_id) through
LangGraph state, but the executing NODE's identity never reached
``save_artifact`` — so ``Artifact.step_name`` was always NULL and no artifact
could be traced to the step that made it.

Rather than widening every tool signature, the builder's node wrappers stamp a
:class:`contextvars.ContextVar` on entry. LangGraph runs each node in its own
asyncio task (its own context copy), and ``asyncio.to_thread`` copies the
context into the worker thread, so ``_save_artifact_sync`` reads the correct
node even under parallel fan-out.

Also owns the per-run artifact ``sequence`` counter: a process-local monotonic
counter, lazily seeded from the DB so a resumed run continues numbering instead
of restarting at 1.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class NodeContext:
    """Identity of the workflow node currently executing in this task."""

    node_id: str
    node_label: str = ""
    workflow_id: str = ""


_current_node: ContextVar[NodeContext | None] = ContextVar(
    "fichero_current_workflow_node", default=None
)


def set_current_node(
    node_id: str, node_label: str = "", workflow_id: str = ""
) -> None:
    """Record the node about to execute in this task's context."""
    _current_node.set(NodeContext(node_id, node_label, workflow_id))


def get_current_node() -> NodeContext | None:
    """The node executing in this task/thread context, if any."""
    return _current_node.get()


# ---------------------------------------------------------------------------
# Per-run artifact sequence
# ---------------------------------------------------------------------------

_seq_lock = threading.Lock()
_run_sequences: dict[str, int] = {}
_RUN_SEQUENCES_LIMIT = 200


def next_artifact_sequence(run_id: str, *, seed_fn=None) -> int:
    """Return the next monotonic artifact sequence number for ``run_id``.

    ``seed_fn`` (returning the max existing sequence for the run, from the DB)
    is invoked only on the first call per run in this process, so a resumed run
    continues numbering without a DB query on every save. Thread-safe: called
    from ``asyncio.to_thread`` workers during fan-out.
    """
    with _seq_lock:
        current = _run_sequences.get(run_id)
        if current is None:
            current = int(seed_fn() or 0) if seed_fn is not None else 0
        current += 1
        _run_sequences[run_id] = current
        while len(_run_sequences) > _RUN_SEQUENCES_LIMIT:
            _run_sequences.pop(next(iter(_run_sequences)))
        return current


def artifact_provenance(run_id: str | None, *, seed_fn=None) -> dict[str, object]:
    """The #4313 provenance trio for an ``Artifact`` written by the current node.

    ``llm_base._save_artifact_sync`` grew this inline; every OTHER tool that
    constructs an ``Artifact`` directly (import_artifacts, similarity, …) has
    to stamp the same fields or the artifact is untraceable — the #4345 lane
    caught ``import_receipt`` shipping with a NULL ``workflow_id``. One helper
    so the field set can't drift between call sites.

    ``sequence`` is only assigned when a run id exists; a tool invoked outside
    a run (direct call, test) leaves it NULL rather than inventing a number.
    """
    ctx = get_current_node()
    return {
        "step_name": ctx.node_id if ctx else None,
        "workflow_id": (ctx.workflow_id or None) if ctx else None,
        "sequence": next_artifact_sequence(run_id, seed_fn=seed_fn) if run_id else None,
    }
