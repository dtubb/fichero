"""A try that waits on a download nothing is running gives up in words (#6320)."""

from fichero_server.execution import jobs
from fichero_server.recipes import samples


def test_a_download_that_never_lands_ends_the_wait_in_words(monkeypatch):
    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "queued", "reason": None})
    monkeypatch.setattr(jobs, "current_job_id", lambda: None)
    plan = {"downloads": [{"name": "Reader X", "job_id": "d1"}]}
    said = samples._await_downloads(None, plan, every=0.01, limit=0.05)
    assert said is not None and "Reader X" in said and "Activity" in said
