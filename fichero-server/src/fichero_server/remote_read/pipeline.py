"""Recipe batches pipelined on a remote place (`compute.recipe.step-major-batches-pipelined`, #5642).

While a recipe runs batch b here, batch b+1's first step, when it is placed on a cluster or Hugging Face, is sent
now, so the place reads it while this Mac works: at most two reads in flight per place (one running, one queued).
It is sent by the step's own send half (`recipes.runner._send_at_scale`: the project's yes, the place, the cap), on
the pages the step would work out at its turn (`_step_pages`), and adopted by those pages when the turn comes. A
Pause holds it; a Stop reaches it through its own row (`remote_read.job`: a read whose recipe stopped stops).

ponytail: only the plan's first step goes ahead (its pages are the batch's own, no earlier step to wait for); a
remote step after a local one waits for its batch. The upgrade is sending a later step once its inputs have landed.
"""
from __future__ import annotations

from typing import Any

from fichero_server.execution import jobs
from fichero_server.remote_read import job as read_job

#: Reads in flight per place under one recipe run (ruling 2, 2026-10-28): one running, one queued.
IN_FLIGHT = 2
REMOTE_PLACES = ("cluster", "huggingface")


def in_flight(db: Any, recipe_job_id: str, target: str) -> int:
    rows = db.execute_fetchall("SELECT detail FROM jobs WHERE parent_id = ? AND kind = ? AND state IN ('waiting', "
                               "'running', 'paused')", [recipe_job_id, read_job.KIND])
    import json

    return sum(1 for (detail,) in rows if (json.loads(detail or "{}").get("request") or {}).get("target") == target)


def send_ahead(db: Any, job_id: str, detail: dict[str, Any], batch: dict[str, Any] | None, tree: Any,
               started_by: str) -> str | None:
    """Send the next batch's first step to its remote place now, if it goes there and the place has room; the read's
    id, or None (no next batch, a local first step, a Pause or Stop asked, no room, nothing to do, or a refusal, which
    its batch's turn says in words)."""
    from fichero_server.execution.cancellation import pause_requested
    from fichero_server.recipes import runner

    if batch is None or not detail.get("runs") or pause_requested(job_id) or runner._stop_asked(job_id):
        return None
    card, step = detail["runs"][0], detail["steps"][0]
    if card.get("place") not in REMOTE_PLACES or in_flight(db, job_id, card["target"]) >= IN_FLIGHT:
        return None
    documents = runner._step_pages(db, card, step, batch, tree, detail)[0]
    if not documents:
        return None
    child, _why = runner._send_at_scale(db, card, documents, job_id, started_by)
    if child is not None:
        jobs.set_parent(db, child, job_id)
    return child
