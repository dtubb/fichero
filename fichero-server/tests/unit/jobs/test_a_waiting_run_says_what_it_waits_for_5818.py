"""A run held behind thumbnails says what the thumbnails wait for and which pages failed, with why (#5818).

Spec: `importer.missing-original-fails-in-words`, `activity.waiting-says-why`. The owner saw only
'Waiting: thumbnails are made first' for 30 minutes while the thumbnails waited on the Mac and four pages had failed.
"""
from __future__ import annotations

from fichero_server.execution import jobs

KIND = "derivatives.thumbnail"


def _row(db, id, state, reason, at):
    db.execute("INSERT INTO jobs (id, kind, subject, state, reason, attempts, started_by, created_at) "
               "VALUES (?, ?, ?, ?, ?, 0, 'automatic', ?)", [id, KIND, id, state, reason, at])


def test_bare_when_there_is_nothing_more_to_say(db):
    jobs._ensure(db)
    _row(db, "a", "waiting", None, "2026-10-19 08:00:00")
    assert jobs.first_reason(db, [KIND]) == jobs.FIRST_REASON


def test_names_the_mode_and_the_failed_pages(db):
    jobs._ensure(db)
    _row(db, "a", "waiting", "Waiting: you're using the Mac: running slower", "2026-10-19 08:00:00")
    _row(db, "b", "failed", "IMG_1.jpg isn't where it was imported from: Locate Originals…", "2026-10-19 08:00:01")
    said = jobs.first_reason(db, [KIND])
    assert "thumbnails are made first" in said
    assert "you're using the Mac: running slower" in said
    assert "IMG_1.jpg isn't where it was imported from" in said
