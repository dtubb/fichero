"""A run held behind thumbnails says what the thumbnails wait for and which pages failed, with why (#5818).

Spec: `importer.missing-original-fails-in-words`, `activity.waiting-says-why`. The owner saw only
'Waiting: thumbnails are made first' for 30 minutes while the thumbnails waited on the Mac and four pages had failed.
"""
from __future__ import annotations

from fichero_server.execution import jobs

KIND = "derivatives.thumbnail"


def _row(db, id, state, reason, at):
    db.execute("INSERT INTO jobs (id, kind, subject, state, reason, attempts, started_by, created_at, finished_at) "
               "VALUES (?, ?, ?, ?, ?, 0, 'automatic', ?, ?)",
               [id, KIND, id, state, reason, at, at if state == "failed" else None])


def test_bare_when_nothing_failed(db):
    jobs._ensure(db)
    assert jobs.first_reason(db, [KIND], "2026-10-19 08:00:00") == jobs.FIRST_REASON


def test_names_the_pages_that_failed_since_the_held_job_was_queued_newest_first(db):
    jobs._ensure(db)
    _row(db, "old", "failed", "OLD.jpg isn't where it was imported from: Locate Originals…", "2026-10-18 08:00:00")
    _row(db, "b", "failed", "IMG_1.jpg isn't where it was imported from: Locate Originals…", "2026-10-19 08:00:01")
    _row(db, "c", "failed", "IMG_2.jpg isn't where it was imported from: Locate Originals…", "2026-10-19 08:00:02")
    said = jobs.first_reason(db, [KIND], "2026-10-19 08:00:00")
    assert said.startswith(jobs.FIRST_REASON)
    assert said.index("IMG_2.jpg") < said.index("IMG_1.jpg")
    assert "OLD.jpg" not in said
