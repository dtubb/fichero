"""Corrections to one page make one re-embed job that waits for a quiet period; each new correction pushes it
later (#5360, `activity.derived.coalesced`)."""
from __future__ import annotations

import time

from fichero_server.actions.page_text_cache import QUIET_SECONDS, queue_reembed
from fichero_server.execution import jobs
from fichero_server.models import DocType, Document


def _run_after(db, doc_id):
    row = db.execute_fetchone(
        "SELECT run_after FROM jobs WHERE kind = 'make-a-vector' AND subject = ? AND state = 'waiting'", [doc_id]
    )
    return row[0]


def test_a_run_of_corrections_is_one_job_held_back_and_pushed_later_by_each(db):
    doc = Document(name="Page", doc_type=DocType.file, page_content="x")
    db.save(doc)
    jobs.set_paused(True)
    try:
        queue_reembed(db, [doc.id])
        first = _run_after(db, doc.id)
        time.sleep(0.05)
        queue_reembed(db, [doc.id])
        second = _run_after(db, doc.id)
        count = db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'make-a-vector' AND subject = ?", [doc.id])[0]
    finally:
        jobs.set_paused(False)
    assert count == 1
    assert first is not None and second > first, "each correction pushes the quiet period later"
    assert QUIET_SECONDS > 0
