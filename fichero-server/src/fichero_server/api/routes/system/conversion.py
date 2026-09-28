"""`GET /api/conversion/status` -- what the whole-library conversion is doing (#5222).

The conversion starts by itself when a library opens (`maintenance/conversion_on_open.py`) and
is announced ONLY here: the app's pill reads this. The report is the kept `ConversionRun` of the
latest run plus what is left, asked of the database now -- progress is the markers, never a
counter, so this cannot drift from the truth.

Nothing converted is left unsaid: every page that could not convert is named with its reason,
and results this engine does not convert (the old `segmentation` artifact, whose boxes no engine
producer ever wrote) are counted and named as left as they were.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Artifact
from fichero_server.models.conversion import ConversionRun

router = APIRouter(prefix="/api/conversion", tags=["conversion"])

#: Artifact types that carry boxes in a form no engine producer wrote and the conversion does not
#: read: listed in the report, never converted and never guessed at.
NOT_CONVERTED = {
    "segmentation": "boxes in `data.segments` from before the page model; no engine producer ever "
                    "wrote them, so they are not converted and still read as before",
}


class PageNotConverted(BaseModel):
    document_id: str
    reason: str


class LeftAsItWas(BaseModel):
    artifact_type: str
    count: int
    reason: str


class ConversionStatus(BaseModel):
    """The latest run and what is left. `run_id` is None when no run has ever been needed."""

    running: bool
    run_id: str | None = None
    verdict: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    seconds: float | None = None
    pages_converted: int = 0
    pages_skipped: int = 0
    #: pages this run could not convert, each with its reason; they still read as before
    pages_not_converted: list[PageNotConverted] = []
    #: pages and results still holding stored geometry, asked of the database now
    pages_remaining: int = 0
    results_remaining: int = 0
    snapshot_path: str | None = None
    #: why a run refused to start (disk short), in bytes
    disk_required_bytes: int | None = None
    disk_available_bytes: int | None = None
    left_as_they_were: list[LeftAsItWas] = []
    seen: bool = False


def _latest(db: Database) -> ConversionRun | None:
    runs = list(db.query(ConversionRun))
    return max(runs, key=lambda run: run.started_at) if runs else None


@router.get("/status", response_model=ConversionStatus)
async def conversion_status(db: Database = Depends(get_library_database)) -> ConversionStatus:
    """What the library's conversion has done, is doing, and has left."""
    scope = db.unconverted_geometry_scope()
    left = [
        LeftAsItWas(artifact_type=kind, count=count, reason=reason)
        for kind, reason in NOT_CONVERTED.items()
        if (count := len(db.query(Artifact, artifact_type=kind)))
    ]
    run = _latest(db)
    if run is None:
        return ConversionStatus(
            running=False, pages_remaining=scope.documents, results_remaining=scope.results,
            left_as_they_were=left,
        )
    return ConversionStatus(
        running=run.is_running,
        run_id=run.run_id,
        verdict=run.verdict.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        seconds=run.seconds,
        pages_converted=run.pages_converted,
        pages_skipped=run.pages_skipped,
        pages_not_converted=[
            PageNotConverted(document_id=f.document_id, reason=f.reason) for f in run.failures
        ],
        pages_remaining=scope.documents,
        results_remaining=scope.results,
        snapshot_path=run.snapshot_path,
        disk_required_bytes=run.disk_required_bytes,
        disk_available_bytes=run.disk_available_bytes,
        left_as_they_were=left,
        seen=run.seen_at is not None,
    )


@router.post("/{run_id}/seen", response_model=ConversionStatus)
async def conversion_seen(
    run_id: str, db: Database = Depends(get_library_database_for_write)
) -> ConversionStatus:
    """A person has seen this run's report. A RUNNING one cannot be: its snapshot is
    kept out of the ordinary tidy-up until then (`ConversionRun.snapshot_may_be_unpinned`)."""
    run = next((r for r in db.query(ConversionRun) if r.run_id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No conversion run {run_id}")
    if run.is_running:
        raise HTTPException(status_code=409, detail="the run has not finished; its report is not final")
    if run.seen_at is None:
        db.save(run.model_copy(update={"seen_at": utc_now()}))
    return await conversion_status(db)
