"""A try waits for a download while it moves, and gives up in words when nothing moves (#6320)."""

from fichero_server.execution import jobs
from fichero_server.recipes import samples


def test_a_download_that_never_moves_ends_the_wait_in_words(monkeypatch):
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "queued", "reason": None})
    monkeypatch.setattr(jobs, "current_job_id", lambda: None)
    plan = {"downloads": [{"name": "Reader X", "job_id": "d1"}]}
    said = samples._await_downloads(None, plan, every=0.01, limit=0.05)
    assert said is not None and "Reader X" in said and "may be stuck" in said and "Activity" in said


def test_a_slow_download_that_keeps_reporting_progress_is_waited_for(monkeypatch):
    """Far longer than `limit` in total, but every poll shows more bytes: the try must not fail it."""
    polls = iter(range(40))

    def read(db, job_id):
        n = next(polls, None)
        return {"state": "done"} if n is None or n >= 39 else {"state": "running", "reason": f"{n} MB of 900"}

    monkeypatch.setattr(jobs, "read_job", read)
    monkeypatch.setattr(jobs, "current_job_id", lambda: None)
    plan = {"downloads": [{"name": "Reader X", "job_id": "d1"}]}
    assert samples._await_downloads(None, plan, every=0.01, limit=0.05) is None  # ~0.4 s of polling against a 0.05 s limit
