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


# --- `wide.output.stale-says-so`: the try result carries the answers' revision, the listing the current one ---

def test_wide_a_try_carries_the_answers_revision_and_a_changed_answer_makes_it_stale(client, db, tmp_path):
    from tests.unit.recipes.test_stage_try_words_5687 import _pages, _set_up

    _pages(db, tmp_path)
    _set_up(client, ["prepare-the-image"])

    def stage():
        return next(s for s in client.get("/api/recipes/stages").json()["items"] if s["id"] == "prepare-images")

    started = client.post("/api/recipes/stages/prepare-images/try", json={})
    assert started.status_code == 200, started.text
    ran_with = started.json()["answers_revision"]
    assert ran_with and ran_with == stage()["answers_revision"], "a fresh try is current"
    assert client.get("/api/recipes/stages/prepare-images/try").json()["answers_revision"] == ran_with

    saved = client.get("/api/recipes/project").json()
    answers = {**saved["answers"], "job_answers": {**(saved["answers"].get("job_answers") or {}), "the_paper": ["faded"]}}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": saved["recipe"]}).status_code == 200
    assert stage()["answers_revision"] != ran_with, "the try ran with the earlier answers: it is stale"
    assert client.get("/api/recipes/stages/prepare-images/try").json()["answers_revision"] == ran_with, "never rewritten as current"


def test_wide_the_revision_follows_the_stages_own_answers_and_model_only():
    from fichero_server.recipes.stages import answers_revision, get_stage

    prepare, read = get_stage("prepare-images"), get_stage("read")
    recipe = {"steps": [{"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}},
                        {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}]}
    base = answers_revision(prepare, {"job_answers": {}}, recipe)
    assert answers_revision(prepare, {"job_answers": {"the_paper": ["faded"]}}, recipe) != base
    assert answers_revision(prepare, {"job_answers": {"prepare_operations": ["crop"]}}, recipe) != base
    assert answers_revision(prepare, {"job_answers": {"entity_kinds": ["people"]}}, recipe) == base, "another stage's answer"
    other = {"steps": [recipe["steps"][0], {**recipe["steps"][1], "model": {"zenodo": "10.5281/zenodo.12743230"}}]}
    assert answers_revision(prepare, {"job_answers": {}}, other) == base, "another stage's model"
    assert answers_revision(read, {"job_answers": {}}, other) != answers_revision(read, {"job_answers": {}}, recipe)
