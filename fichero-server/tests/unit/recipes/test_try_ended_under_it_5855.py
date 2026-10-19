"""A try whose job ended before it wrote its end (the engine was stopped under it) reads as ended, per column, with a why
(`source.onboard.stages.try-progress-in-place`; the M4 TRYPROGRESS runs eade48d9a and d020f9f05)."""
from __future__ import annotations

from fichero_server.recipes import samples


def test_a_running_column_of_an_ended_try_is_failed_with_the_sentence_and_a_final_progress(monkeypatch):
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "failed", "reason": None})
    result = {"stage": "find-lines", "state": "running", "job_id": "j", "pages": ["p1", "p2", "p3", "p4", "p5"],
              "candidates": [{"card": "blla", "state": "running", "why": None,
                              "progress": {"state": "running", "done": 0, "total": 5},
                              "per_page": [{"id": "p1", "segments": {"line": 20}}, {"id": "p2", "segments": {"line": 29}}]}]}
    out = samples._following_its_job(object(), result)
    (column,) = out["candidates"]
    assert out["state"] == "failed" and out["error"]
    assert column["state"] == "failed" and column["why"] == out["error"]
    assert column["progress"]["state"] == "failed" and column["progress"]["done"] == 2 and column["progress"]["total"] == 5


def test_a_column_that_already_ended_is_left_as_it_was(monkeypatch):
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "cancelled", "reason": "Stopped"})
    done = {"card": "a", "state": "done", "why": None}
    out = samples._following_its_job(object(), {"stage": "names", "state": "waiting", "job_id": "j", "pages": ["p"],
                                                "candidates": [done]})
    assert out["candidates"] == [done]


def test_stop_reads_stopped_not_failed(monkeypatch):
    """Review 337 LOW: a try the person stopped is `stopped` on the try and on each column."""
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "read_job", lambda db, job_id: {"state": "cancelled", "reason": "Stopped by you"})
    out = samples._following_its_job(object(), {"stage": "find-lines", "state": "running", "job_id": "j", "pages": ["p1", "p2"],
                                                "candidates": [{"card": "a", "state": "running", "per_page": [{"id": "p1", "segments": {"line": 1}}]}]})
    (column,) = out["candidates"]
    assert out["state"] == "stopped" and column["state"] == "stopped" and column["progress"]["state"] == "stopped"
    assert column["progress"]["done"] == 1
