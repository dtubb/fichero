"""A long image operation as a job (`image.ops.long-operation-is-a-job`, #6384).

An image operation on a big scan can take longer than a client waits. Asked as a job, the request returns a job id at once and the
operation runs on the images lane (two at a time, one while memory is tight), so the engine keeps answering health and reads, the
row shows in Activity, and Cancel is the job's own. The job runs the SAME audited action (`image.<op>`) the route calls, so the
chain row, the audit entry and Undo are exactly those of the direct call; nothing here does a picture's work.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

KIND = "image-operation"
_kinds_registered = False


def queue_image_operation(db: Any, action: str, params: dict[str, Any], *, started_by: str = "ui") -> str:
    """Queue `action` (an `image.<op>` that takes a `document_id`) with `params`; returns the job id. Each request is its own job:
    the subject is unique, so two asks of the same page are two jobs, not one (a waiting job of a subject is otherwise reused)."""
    from fichero_server.execution import jobs

    register_job_kinds()
    return jobs.enqueue(db, KIND, f"{params.get('document_id', '')}:{uuid.uuid4().hex}", started_by=started_by,
                        detail=json.dumps({"action": action, "params": params}), watched=True)


def _run(db: Any, subject: str) -> None:
    from fichero_server.actions.registry import ActionContext, registry

    row = db.execute_fetchone("SELECT detail, started_by FROM jobs WHERE kind = ? AND subject = ?", [KIND, subject])
    if row is None or not row[0]:
        raise ValueError("the image operation job has no request")
    request = json.loads(row[0])
    ctx = ActionContext(actor=row[1] or "ui", library_path=str(db.path.parent))
    registry.invoke(db, request["action"], request["params"], ctx)


def register_job_kinds() -> None:
    global _kinds_registered
    if _kinds_registered:
        return
    _kinds_registered = True
    from fichero_server.execution import jobs

    jobs.register_kind(KIND, _run, model=None, lane="images", name="Image operation")
