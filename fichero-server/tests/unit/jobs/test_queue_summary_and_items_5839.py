"""The whole queue in one line, and a kind's row expanding to its pages (#5839, `activity.window.queue-summary`,
`activity.window.expands-to-pages`)."""
from __future__ import annotations

from fichero_server.execution import jobs


def _done(db, kind: str, seconds: float, n: int = 3) -> None:
    for i in range(n):
        job_id = jobs._insert(db, kind, f"d{i}", None, "automatic")
        db.execute("UPDATE jobs SET state = 'done', started_at = now() - to_seconds(?), finished_at = now() "
                   "WHERE id = ?", [seconds, job_id])


def _queued(db, kind: str, n: int) -> None:
    for i in range(n):
        jobs._insert(db, kind, f"q{i}", None, "automatic")


def test_the_summary_counts_done_and_left_and_says_about_how_long_from_measured_items(db):
    jobs._ensure(db)
    _done(db, "thumb-5839", 2.0)
    _queued(db, "thumb-5839", 5)

    said = jobs.queue_summary(db, jobs.snapshot(db))

    assert said["left"] == 5 and said["done"] == 3
    assert said["seconds_left"] == 10  # 5 left at a measured 2 s each


def test_with_nothing_measured_the_summary_leaves_the_time_out(db):
    jobs._ensure(db)
    _queued(db, "unmeasured-5839", 4)

    said = jobs.queue_summary(db, jobs.snapshot(db))

    assert said["left"] == 4 and said["seconds_left"] is None


def test_an_empty_queue_has_no_summary(db):
    jobs._ensure(db)
    assert jobs.queue_summary(db, jobs.snapshot(db)) is None


def test_a_kinds_row_expands_to_its_pages_in_pick_order_and_pages_through(db):
    jobs._ensure(db)
    _queued(db, "pages-5839", 5)

    first = jobs.items_of_kind(db, "pages-5839", limit=3)
    rest = jobs.items_of_kind(db, "pages-5839", limit=3, offset=3)

    assert [i["subject"] for i in first] == ["q0", "q1", "q2"]
    assert [i["subject"] for i in rest] == ["q3", "q4"]
    assert {i["state"] for i in first + rest} == {"waiting"}
