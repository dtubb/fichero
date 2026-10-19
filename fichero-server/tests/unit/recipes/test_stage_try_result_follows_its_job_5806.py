"""#5806: a stage's try result follows its job, so the app's spinner stops and a failure has a sentence; and the
result file exists before the job that reads it can run.

WHY: the owner's 2026-10-19 07:51 failure "No such file .../recipe/samples/find-lines.json": `start_try` enqueued the
try job first and wrote the result file after, so a job picked up at once read a file that was not there yet. And a
Find Lines / Read comparison's result kept `state: waiting` for ever (its state lives on the comparison's job), so
Compare on These Pages stayed disabled and spun.
"""
from __future__ import annotations

from pathlib import Path

from fichero_server.execution import jobs
from fichero_server.recipes import samples

RECIPE = {"steps": [{"id": "lines", "job": "find-lines"}]}


def _result(db, job_id, state="waiting"):
    library = Path(db.path).parent
    samples._write(library, "find-lines", {"stage": "find-lines", "pages": ["p1"], "state": state, "job_id": job_id})


def _job(db, state, reason=None):
    job_id = jobs.enqueue(db, "compare-line-finders", "r1", started_by="test", watched=True)
    db.execute("UPDATE jobs SET state = ?, reason = ? WHERE id = ?", [state, reason, job_id])
    return job_id


def test_a_result_whose_job_is_done_reads_done(db):
    _result(db, _job(db, "done"))
    assert samples.read_result(db, "find-lines", RECIPE)["state"] == "done"


def test_a_result_whose_job_failed_reads_failed_with_the_jobs_sentence(db):
    _result(db, _job(db, "failed", "No line finder can be compared on this Mac yet."))
    got = samples.read_result(db, "find-lines", RECIPE)
    assert got["state"] == "failed" and got["error"] == "No line finder can be compared on this Mac yet."


def test_a_result_whose_job_is_gone_reads_failed_and_says_to_try_again(db):
    _result(db, "no-such-job")
    got = samples.read_result(db, "find-lines", RECIPE)
    assert got["state"] == "failed" and "try it again" in got["error"]


def test_a_result_whose_job_is_running_reads_under_way(db):
    _result(db, _job(db, "running"))
    assert samples.read_result(db, "find-lines", RECIPE)["state"] in ("waiting", "running")


def test_the_result_file_exists_before_the_try_job_is_queued(client, db, tmp_path, monkeypatch):
    """A job picked up the moment it is queued reads its result file: it must be there."""
    from tests.unit.recipes.test_stage_try_words_5687 import _pages, _set_up

    _pages(db, tmp_path)
    _set_up(client, ["find-regions"])
    library = Path(db.path).parent
    seen = []
    real = jobs.enqueue

    def enqueue(db_, kind, subject, **kw):
        if kind == samples.TRY_KIND:
            seen.append(samples._result_path(library, subject.split(":", 1)[0]).exists())
        return real(db_, kind, subject, **kw)

    monkeypatch.setattr(jobs, "enqueue", enqueue)
    assert client.post("/api/recipes/stages/find-regions/try", json={}).status_code == 200
    assert seen == [True]
