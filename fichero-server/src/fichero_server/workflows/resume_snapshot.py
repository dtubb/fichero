"""A resumed run keeps the graph it started with (#5373, `activity.run.resume-from-snapshot`): its nodes and edges come
from the run's own snapshot, so an edit made while it was paused does not change the graph under the checkpoint."""
from __future__ import annotations

from typing import Any

from fichero_server.models import Workflow


def as_started(workflow: Workflow, snapshot: dict[str, Any] | None) -> Workflow:
    """`workflow` with the nodes and edges its run started with. Each snapshot node overlays the stored node of the same
    id (a field the snapshot does not keep, such as a position, stays); a node the edit added is dropped, one it deleted
    comes back from the snapshot. A run with no snapshot resumes on the workflow as stored."""
    nodes, edges = (snapshot or {}).get("nodes"), (snapshot or {}).get("edges")
    if not nodes:
        return workflow
    current = {n.get("id"): n for n in workflow.nodes}
    return workflow.model_copy(update={
        "nodes": [{**current.get(n["id"], {}), **n} for n in nodes],
        "edges": list(edges or []),
    })
