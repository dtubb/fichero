"""A folder import a quit or crash cut off is remembered in the project and offered at the next open (#6829).

The import route writes one job row for the import when it starts (`begin`), keeps its request and its file count on
the row (`record_progress`), and ends it (`end`). A row left running by a dead engine is held at open like every
other (`jobs.resume`: "Stopped when Fichero quit"), listed by the launch alert, and Continue runs the import again
from its stored request: files already in are skipped by the import's own checksum test, so no page is made twice.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

IMPORT_KIND = "import-folder"

#: The row's count is written every this many files, and at the last one.
PROGRESS_EVERY = 25


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if IMPORT_KIND not in jobs.KINDS:
        # ponytail: one lane thread holds the "database" lane for the whole import when Continue runs it.
        jobs.register_kind(IMPORT_KIND, run_again, model=None, lane="database", name="Import a folder", names=_name)


def _name(db: Any, subject: str, detail: dict[str, Any]) -> str | None:
    folder = detail.get("name") or Path(subject).name
    total = int(detail.get("total") or 0)
    done = int(detail.get("done") or 0)
    return f"Import of {folder} · {done:,} of {total:,} files" if total else f"Import of {folder}"


def begin(db: Any, request: dict[str, Any]) -> str:
    """The import's own row, running. A row an earlier cut-off import of this folder left held is ended: dropping the
    folder again does the work it was waiting to do."""
    from fichero_server.execution import jobs

    register_job_kinds()
    folder = str(request["path"])
    detail = {"request": request, "name": Path(folder).name, "done": 0, "total": 0}
    return jobs.start_own_row(db, IMPORT_KIND, folder, json.dumps(detail), replaces_held="Imported again")


def record_progress(db: Any, job_id: str, done: int, total: int) -> None:
    from fichero_server.execution import jobs

    if done % PROGRESS_EVERY and done < total:
        return
    detail = json.loads(jobs.detail_text(db, job_id) or "{}")
    detail.update(done=done, total=total)
    jobs.save_detail(db, job_id, json.dumps(detail))


def end(db: Any, job_id: str, state: str, reason: str | None = None) -> None:
    from fichero_server.execution import jobs

    jobs.end_own_row(db, job_id, state, reason)


def run_again(db: Any, subject: str) -> None:
    """Continue on the launch alert: the import runs again from its stored request."""
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.execution import jobs

    row = jobs.running_row_of(db, IMPORT_KIND, subject)
    if row is None or not row[1]:
        raise RuntimeError(f"no stored import of {subject}")
    job_id = row[0]
    request = json.loads(row[1])["request"]
    ctx = ActionContext(
        actor="person",
        library_path=str(Path(db.path).parent),
        is_bootstrap=True,
        on_progress=lambda current, total, fetching=0.0: record_progress(db, job_id, current, total),
    )
    registry.invoke(db, "import.folder", request, ctx)
