"""The page in view first (`activity.foreground.rank-on-the-row-and-the-pick`, #6442; Step 1.14's engine half).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. Acceptance: page 23 opened with its Find Lines and reading waiting:
both rows get a rank above 0 with Find Lines ahead of the reading, the lane's next pick is page 23's, and the row already
done for the page is not touched; the person opens page 60: page 23's waiting rows return to 0 on the same call; a bulk run
behind it still advances one pick in four. Real lane, real job rows, kinds that record when they start.
"""
from __future__ import annotations

import time

import pytest

from fichero_server.execution import jobs

LINES, READ = "find-lines-6442", "read-a-page-6442"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    """Two kinds on the one-slot recipes lane, Find Lines before the reading in the pipeline's order."""
    started: list[str] = []
    monkeypatch.setattr(jobs, "_FOREGROUND", {})

    def run(db, subject):
        started.append(subject)

    monkeypatch.setitem(jobs.KINDS, LINES, jobs.Kind(run=run, model=None, lane="recipes", name="Find Lines"))
    monkeypatch.setitem(jobs.KINDS, READ, jobs.Kind(run=run, model=None, lane="recipes", name="Read a page"))
    yield started


def _rank(db, job_id):
    return db.execute_fetchone("SELECT COALESCE(foreground_rank, 0) FROM jobs WHERE id = ?", [job_id])[0]


def test_the_waiting_rows_of_the_page_in_view_are_ranked_in_step_order_and_nothing_else_moves(db, lane):
    jobs.set_paused(True)
    try:
        read = jobs.enqueue(db, READ, "page-23")
        lines = jobs.enqueue(db, LINES, "page-23")
        other = jobs.enqueue(db, READ, "page-60")
        done = jobs.enqueue(db, LINES, "page-23:old")
        db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [done])
        rows_before = db.execute_fetchone("SELECT count(*) FROM jobs")[0]

        assert jobs.set_foreground(db, "window-1", [("page-23", 0)]) == 2

        assert _rank(db, lines) > _rank(db, read) > 0, "Find Lines ahead of the reading"
        assert _rank(db, other) == 0 and _rank(db, done) == 0, "a done row is not touched"
        assert db.execute_fetchone("SELECT count(*) FROM jobs")[0] == rows_before, "never a new row"

        jobs.set_foreground(db, "window-1", [("page-60", 0)])
        assert _rank(db, lines) == 0 and _rank(db, read) == 0, "moving on puts page 23 back on the same call"
        assert _rank(db, other) > 0
    finally:
        jobs.set_paused(False)


def test_the_lanes_next_pick_is_the_page_in_view(db, lane):
    jobs.set_paused(True)
    for i in range(3):
        jobs.enqueue(db, READ, f"bulk-{i}")
    jobs.enqueue(db, READ, "page-23")
    jobs.set_foreground(db, "window-1", [("page-23", 0)])
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane) == 4)
    assert lane[0] == "page-23"


def test_a_page_two_windows_name_stays_first_until_both_move_on_and_a_quiet_client_lapses(db, lane, monkeypatch):
    jobs.set_paused(True)
    try:
        read = jobs.enqueue(db, READ, "page-23")
        jobs.set_foreground(db, "window-1", [("page-23", 0)])
        jobs.set_foreground(db, "window-2", [("page-23", 0)])
        jobs.set_foreground(db, "window-1", [("page-60", 0)])
        assert _rank(db, read) > 0, "still named by window 2"

        until, items = jobs._FOREGROUND[jobs._key(db)]["window-2"]
        jobs._FOREGROUND[jobs._key(db)]["window-2"] = (time.monotonic() - 1, items)  # 90 s without a report
        jobs.expire_foreground(db)
        assert _rank(db, read) == 0
    finally:
        jobs.set_paused(False)


def test_a_bulk_run_behind_the_page_in_view_still_advances_one_pick_in_four(db, lane):
    jobs.set_paused(True)
    for i in range(3):
        jobs.enqueue(db, READ, f"bulk-{i}")
    for i in range(6):
        jobs.enqueue(db, READ, f"page-23:{i}")
    jobs.set_foreground(db, "window-1", [("page-23", 0)])
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane) == 9, 8), lane
    assert lane[:8] == ["page-23:0", "page-23:1", "page-23:2", "bulk-0",
                        "page-23:3", "page-23:4", "page-23:5", "bulk-1"]


def test_the_route_ranks_and_answers_how_many(client, db, lane):
    jobs.set_paused(True)
    try:
        jobs.enqueue(db, READ, "page-23")
        answer = client.put("/api/activity/foreground",
                            json={"client": "window-1", "items": [{"subject": "page-23", "rank": 0}]})
        assert answer.status_code == 200, answer.text
        assert answer.json() == {"ranked": 1}
        assert client.put("/api/activity/foreground", json={"client": "window-1", "items": []}).json() == {"ranked": 0}
    finally:
        jobs.set_paused(False)


def test_the_listed_row_counts_its_jobs_for_the_page_in_view_and_lists_them_first(client, db, lane):
    """`activity.foreground.one-glyph-not-words`: the listed row of a kind says how many of its waiting jobs are for the
    page in view, in figures, and its first job is one of them (the lane's pick order)."""
    jobs.set_paused(True)
    try:
        for i in range(3):
            jobs.enqueue(db, READ, f"bulk-{i}")
        jobs.enqueue(db, READ, "page-23")
        jobs.set_foreground(db, "window-1", [("page-23", 0)])
        (row,) = [j for j in jobs.snapshot(db) if j["kind"] == READ]
        assert row["in_view"] == 1 and row["subject"] == "page-23"
        listed = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["task_type"] == READ]
        assert listed and listed[0]["in_view"] == 1
        jobs.set_foreground(db, "window-1", [("page-60", 0)])
        (row,) = [j for j in jobs.snapshot(db) if j["kind"] == READ]
        assert not row.get("in_view"), "moved on: no row is in view"
    finally:
        jobs.set_paused(False)


def test_an_engine_restart_leaves_no_stale_rank(db, lane):
    jobs.set_paused(True)
    try:
        read = jobs.enqueue(db, READ, "page-23")
        jobs.set_foreground(db, "window-1", [("page-23", 0)])
        assert _rank(db, read) > 0

        jobs._FOREGROUND.clear()  # the engine's memory of the view is gone
        db._jobs_columns_on = None  # a new connection reads the jobs table again
        jobs._ensure(db)

        assert _rank(db, read) == 0
    finally:
        jobs.set_paused(False)
