"""Fable runner review #3: a try's pages live in a scratch copy that is deleted when it ends, so its Activity row sat at
0 of 1 and then flipped to failed. The try keeps its count on its own row's detail and the tree reads it
(`activity.details.progress-counts`); a failed step run always says why (`recipes.try.says-what-it-waits-for`)."""
from __future__ import annotations

import json

from fichero_server.execution import jobs
from fichero_server.recipes import runner, samples


def _try(db, **fields):
    jobs._ensure(db)
    job_id = jobs._insert(db, samples.TRY_KIND, "stage:find-lines", None, "watcher")
    for key, value in fields.items():
        db.execute(f"UPDATE jobs SET {key} = ? WHERE id = ?", [value, job_id])
    return job_id


def test_a_running_try_counts_the_pages_it_has_made(db):
    job_id = _try(db, state="running")
    samples._count_on_the_row(db, job_id, "find-lines", {"done": 2, "total": 5})
    node = jobs.tree(db, job_id)
    assert (node["done"], node["total"]) == (2, 5)


def test_a_finished_try_counts_all_of_its_pages_and_a_failed_one_those_it_made(db):
    done = _try(db, state="done", detail=json.dumps({"stage": "find-lines", "done": 4, "total": 5}))
    failed = _try(db, state="failed", detail=json.dumps({"stage": "find-lines", "done": 2, "total": 5}))
    assert (jobs.tree(db, done)["done"], jobs.tree(db, done)["total"]) == (5, 5)
    assert (jobs.tree(db, failed)["done"], jobs.tree(db, failed)["total"]) == (2, 5)


def test_a_leaf_that_counts_nothing_is_one_page_as_before(db):
    assert (jobs.tree(db, _try(db, state="running"))["done"], jobs.tree(db, _try(db, state="running"))["total"]) == (0, 1)


def test_a_failed_run_that_recorded_no_error_still_says_why():
    assert runner.outcome_why("failed", None)
