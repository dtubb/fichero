"""An edited line is read again by itself (`segment-actions.automatic-rerun-after-an-edit`, #6069).

The reading on a line records the workflow tool that wrote it (`producer_tool`) and the model that made it (`producer_model`,
"provider/model"). After the line's shape changes, that step runs again on that line alone with that model, if
the model runs on this Mac; a paid cloud model is never called unasked and the line is reported as out of date.
"""
from __future__ import annotations

from typing import Any

#: The workflow tool that writes a line's own words (a reading's `producer_tool`), and the recipe job whose step runs it.
LINE_READ_TOOL, LINE_READ_JOB = "transcribe", "read-a-line"


def _is_cloud(provider: str) -> bool:
    """A provider the person pays for. ponytail: a provider this build has no row for (Kraken, a Hugging Face
    model on this Mac) is taken as local; a remote Hugging Face run is not told apart."""
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info(provider.strip().lower())
    return info is not None and not info.is_builtin and not info.is_local


def _last_reading(db: Any, segment_id: str) -> Any | None:
    from fichero_server.models import ContentRepresentation

    rows = [r for r in db.query(ContentRepresentation, segment_id=segment_id)
            if r.kind == "transcription" and not r.retracted_at and r.producer_tool == LINE_READ_TOOL]
    return max(rows, key=lambda r: r.created_at, default=None)


def _already_queued(db: Any, segment_id: str) -> bool:
    import json

    from fichero_server.execution import jobs
    from fichero_server.recipes.runner import KIND

    return any(json.loads(row.get("detail") or "{}").get("reread_of") == segment_id
               for row in jobs.find_jobs(db, kinds=[KIND], states=["waiting", "running", "paused"]))


def reread_edited(db: Any, segment_ids: list[str], *, started_by: str) -> dict[str, list[dict[str, Any]]]:
    """Queue one re-read for each edited line that a local step read. `started`: the run each got; `stale`: lines
    whose reading came from a cloud model, not run; `skipped`: the rest, each with why."""
    from fichero_server.api.routes.system.recipes import _start_plan
    from fichero_server.models import Document
    from fichero_server.models.segments import Segment
    from fichero_server.recipes import runner

    out: dict[str, list[dict[str, Any]]] = {"started": [], "stale": [], "skipped": []}
    for segment_id in dict.fromkeys(segment_ids):
        def skip(why: str, segment_id: str = segment_id) -> None:
            out["skipped"].append({"segment_id": segment_id, "why": why})

        row = db.get(Segment, segment_id)
        if row is None or row.deleted_at is not None:
            skip("no such line")
            continue
        reading = _last_reading(db, segment_id)
        if reading is None:
            skip("no reading of it came from a step")
            continue
        provider, _, model = (reading.producer_model or "").partition("/")
        if provider and model and _is_cloud(provider):
            out["stale"].append({"segment_id": segment_id, "model": reading.producer_model})
            continue
        if _already_queued(db, segment_id):
            skip("already being read again")
            continue
        from fichero_server.recipes.project import read_project_setup

        steps = [s for s in ((read_project_setup(runner._library(db))["recipe"] or {}).get("steps") or [])
                 if s.get("job") == LINE_READ_JOB]
        if not steps:
            skip(f"the recipe has no {LINE_READ_JOB} step")
            continue
        step_id = str(steps[0]["id"])
        plan = _start_plan(db, None, steps=[step_id], documents=[row.document_id])
        if plan["refusals"]:
            skip("; ".join(plan["refusals"]))
            continue
        if provider and model:
            for card in plan["runs"]:
                card["provider_override"], card["model_override"] = provider, model
        page = db.get(Document, row.document_id)
        label = f"{row.kind} on {page.name if page else row.document_id}"
        job_id = runner.enqueue(db, plan, documents=[row.document_id], started_by=started_by, redo=[step_id],
                                segments=[segment_id], reread_of={"segment_id": segment_id, "label": label})
        out["started"].append({"segment_id": segment_id, "job_id": job_id})
    return out
