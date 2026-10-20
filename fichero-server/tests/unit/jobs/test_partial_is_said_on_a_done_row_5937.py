"""A run or batch that finished with pages lost says "Partial" in its row's reason; its state stays `done` until a real partial
state exists (#5937, `activity.run.partial-said-on-a-done-row`)."""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.workflows.run_account import partial_words


def test_a_run_with_failed_pages_says_how_many_were_read():
    state = {"files": ["/a", "/b", "/c", "/d"], "parallel_results": {"read": [
        {"index": 0, "file": "/a", "success": True, "result": {}}, {"index": 1, "file": "/b", "success": True, "result": {}},
        {"index": 2, "file": "/c", "success": True, "result": {}}, {"index": 3, "file": "/d", "success": False, "error": "boom"}]}}
    assert partial_words(state) == "Partial: 3 of 4 pages read"


def test_a_run_that_lost_no_page_says_nothing():
    state = {"files": ["/a"], "parallel_results": {"read": [{"index": 0, "file": "/a", "success": True, "result": {}}]}}
    assert partial_words(state) is None


def test_a_partly_failed_batch_is_done_with_partial_in_its_reason(db):
    jobs.record_batch(db, "batch-5937", status="partial_failure")
    row = jobs.read_job(db, "batch-5937")
    assert row["state"] == "done" and row["reason"].startswith("Partial")
