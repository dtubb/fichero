"""The run history's housekeeping (#5711): a run's log kept as one value before #5711 moved into its lines.

Nothing waits for it: a log that is still a value reads as it always did (`db.activity_records.read_log`), and a run
written again moves its own value first. So the move is never on the open path (a big library's history took tens of
seconds there). Opening a library queues one background job when one is needed. That job moves `CHUNK` runs per
transaction, each verified before its value is cleared. Before each chunk it steps aside while the throttle holds
background work or a person is waiting, and it is taken up again later. It records how far it got, and marks the
library done only once no value is left.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fichero_server.execution import jobs

logger = logging.getLogger(__name__)

KIND = "tidy-the-run-history"
SUBJECT = "run-logs"
#: Runs moved per transaction: a log can be megabytes.
CHUNK = 50


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, lane="database",
                           name="Tidy the run history (housekeeping)")


def queue_if_needed(db: Any) -> str | None:
    """At open: nothing proportional to history. If the library is not marked done, either it has no run whose log
    is still a value (marked done now) or the job is queued; an earlier waiting job is reused. Returns the job id."""
    from fichero_server.db import activity_records as records

    if records.logs_as_lines_done(db):
        return None
    if not records.runs_with_values(db, 1):
        records.mark_logs_as_lines_done(db)
        return None
    register_job_kinds()
    return jobs.enqueue(db, KIND, SUBJECT)


def _why_step_aside() -> str | None:
    from fichero_server.execution import throttle

    if jobs.is_paused():
        return "Paused by you"
    if jobs._scheduler.someone_is_waiting("database"):
        return "Stepped aside for work someone is waiting for"
    return throttle.why_wait(person_waiting=False)


def run(db: Any, subject: str) -> dict[str, Any]:
    """Move the logs a chunk at a time; deferred (back to waiting, nothing lost) whenever it should step aside."""
    from fichero_server.db import activity_records as records

    job_id = getattr(jobs._current, "job_id", None)
    moved = 0
    while True:
        why = _why_step_aside()
        if why:
            raise jobs.JobDeferred(why)
        ids = records.runs_with_values(db, CHUNK)
        if not ids:
            records.mark_logs_as_lines_done(db)
            return {"runs_moved": moved}
        with db.transaction():
            records.move_values_into_lines(db, ids)
        moved += len(ids)
        if job_id:
            jobs.save_detail(db, job_id, json.dumps({"runs_moved": moved}),
                             reason=f"Moved {moved} runs' logs into lines")
