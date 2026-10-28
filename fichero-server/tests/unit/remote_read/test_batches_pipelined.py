"""Recipe batches pipelined on a remote place (spec: recipe-steps-at-scale, `compute.recipe.step-major-batches-pipelined`,
#5642; the manager's ruling, 2026-10-28).

While batch b runs here, batch b+1's first step, placed on Hugging Face or a cluster, is sent ahead (at most two reads
in flight per place) by the step's own send half, and adopted by its pages at its turn. The read's row is real; the
place, the project's answers and the pages a step works out are stand-ins.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import clear_cancellation, clear_pause, request_cancellation, request_pause
from fichero_server.recipes import runner
from fichero_server.remote_read import job as read_job
from fichero_server.remote_read import pipeline

CARD = {"place": "huggingface", "target": "huggingface-jobs", "model_override": "catmus", "job": "read-a-line",
        "steps": ["read"], "card": "workflow"}


@pytest.fixture
def recipe(db, monkeypatch):
    """A recipe row with a read on Hugging Face as its first step; each read sent is a real row under it."""
    from fichero_server.recipes import places, project, train_offers

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(runner, "_library", lambda _db: "lib")
    monkeypatch.setattr(project, "read_project_setup", lambda _lib: {"answers": {"cloud_allowed": True,
                                                                                 "hf_spend_cap_usd": 10}})
    monkeypatch.setattr(places, "allows", lambda place, _p=None: True)
    spent = {"usd": 0.0}
    monkeypatch.setattr(train_offers, "spend_this_month", lambda _db, *, cap: {"spent_at_most_usd": spent["usd"]})
    monkeypatch.setattr(runner, "_step_pages", lambda db, card, step, batch, tree, detail: (batch["units"], {}, {}))
    sent = []

    def start(db, request, *, started_by, stage):
        job_id = jobs.enqueue_remote(db, read_job.KIND, f"read:{len(sent)}", target=request.target, reason="x",
                                     started_by=started_by, detail=json.dumps({"request": request.model_dump()}))
        jobs.set_parent(db, job_id, request.parent_job_id)
        sent.append(request.scope_ids)
        return {"job_id": job_id}

    monkeypatch.setattr(read_job, "start", start)
    parent = jobs.enqueue(db, "batch", "recipe-under-test", started_by="owner")
    yield {"id": parent, "detail": {"runs": [CARD], "steps": [{}]}, "sent": sent, "spent": spent}
    clear_cancellation(parent)
    clear_pause(parent)


def _batch(*units):
    return {"units": list(units)}


def test_the_next_batch_goes_ahead_and_its_turn_adopts_it_by_its_pages_never_sending_it_twice(db, recipe, monkeypatch):
    """WHY: the place reads batch b+1 while this Mac works on batch b; a resume (or the batch's own turn) finds the read
    sent ahead by its pages, even once some of them have landed, and never sends it again."""
    ahead = pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p3", "p4"), None, "owner")
    assert ahead and recipe["sent"] == [["p3", "p4"]] and jobs.parent_of(db, ahead) == recipe["id"]
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p3", "p4"), None, "owner") == ahead
    monkeypatch.setattr(runner, "_wait", lambda db, child, parent: (child, "done", None))
    recipe["spent"]["usd"] = 10.0  # the read sent ahead took the month to its cap: it is adopted, not refused
    assert runner._run_at_scale(db, CARD, ["p4"], recipe["id"], "owner") == (ahead, "done", None)  # p3 has landed
    assert recipe["sent"] == [["p3", "p4"]], "sent once"


def test_no_more_than_two_reads_are_in_flight_per_place(db, recipe):
    for pages in (("p1",), ("p2",)):
        pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch(*pages), None, "owner")
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p3"), None, "owner") is None
    assert recipe["sent"] == [["p1"], ["p2"]]


def test_nothing_goes_ahead_while_paused_or_stopping_or_with_no_next_batch_or_a_local_first_step(db, recipe):
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], None, None, "owner") is None
    local = {"runs": [{**CARD, "place": "this-mac"}], "steps": [{}]}
    assert pipeline.send_ahead(db, recipe["id"], local, _batch("p1"), None, "owner") is None
    request_pause(recipe["id"])
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p1"), None, "owner") is None
    clear_pause(recipe["id"])
    request_cancellation(recipe["id"])
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p1"), None, "owner") is None
    assert recipe["sent"] == []


def test_the_cap_is_asked_before_a_read_goes_ahead_and_counts_it_before_its_batch(db, recipe):
    """WHY: a read sent ahead is a read sent: the Hugging Face cap is asked before it goes, and once it is out it is
    counted in the month's spend that the next send (its own batch's turn, or the one after) is asked against."""
    recipe["spent"]["usd"] = 10.0  # the month's cap reached
    assert pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p1"), None, "owner") is None
    assert recipe["sent"] == []


def test_the_month_counts_a_read_sent_ahead_by_its_jobs_before_its_batch_starts(db):
    """WHY: the month's Hugging Face spend counts a read by the Jobs it has sent, sent ahead or not."""
    from fichero_server.recipes.train_offers import spend_this_month

    request = {"scope_ids": ["p1"], "reader": "kraken", "card": "catmus", "target": "huggingface-jobs",
               "pages_may_leave": True, "timeout": "1h"}
    jobs.enqueue_remote(db, read_job.KIND, "read:ahead", target="huggingface-jobs", reason="x", started_by="owner",
                        detail=json.dumps({"request": request, "price_per_hour_usd": 0.4,
                                           "shards": {"0": {"state": "submitted", "tries": 1}}}))
    assert spend_this_month(db, cap=10)["spent_at_most_usd"] > 0


def test_a_stop_reaches_the_read_sent_ahead_before_anything_is_sent_and_while_it_runs(db, recipe):
    """WHY: Stop on the recipe ends the read sent for its next batch too, never left reading (and billing) alone: a
    queued one sends nothing; a running one cancels its Jobs."""
    ahead = pipeline.send_ahead(db, recipe["id"], recipe["detail"], _batch("p1"), None, "owner")
    subject = jobs.read_job(db, ahead)["subject"]
    request_cancellation(recipe["id"])

    class Place:
        cancelled: list[str] = []

        def send(self, *a):
            pytest.fail("the package was sent after the recipe stopped")

        def cancel(self, far_id):
            self.cancelled.append(far_id)

    with pytest.raises(jobs.JobCancelled):
        read_job.run(db, subject, target=Place(), sleep=lambda s: None)
    detail = json.loads(jobs.read_job(db, ahead)["detail"])
    detail["shards"] = {"0": {"state": "submitted", "far_id": "job-0", "tries": 1}}
    detail["request"].update(reader="kraken")
    jobs.save_detail(db, ahead, json.dumps(detail))
    place = Place()
    with pytest.raises(jobs.JobCancelled):
        read_job.run(db, subject, target=place, sleep=lambda s: None)
    assert place.cancelled == ["job-0"]


def test_the_recipe_runner_sends_the_second_batch_ahead_while_it_runs_the_first(db, monkeypatch, tmp_path):
    """WHY (the hook in `_run_the_plan`): a two-batch plan whose first step is on Hugging Face sends the second batch's
    read before the first batch runs, on that batch's own pages; the last batch sends nothing ahead."""
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    ids = []
    for i in range(2):
        image = tmp_path / f"p{i}.png"
        Image.new("RGB", (32, 32), "white").save(image)
        doc = Document(name=image.name, doc_type=DocType.file, file_type=FileType.image, path=str(image))
        db.save(doc)
        ids.append(doc.id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)
    monkeypatch.setattr(runner, "_step_pages", lambda db, card, step, batch, tree, detail: (list(batch["units"]), {}, {}))
    events = []
    monkeypatch.setattr(runner, "_send_at_scale", lambda db, card, documents, parent, started_by:
                        (events.append(("ahead", list(documents))), (None, "refused here"))[1])
    monkeypatch.setattr(runner, "_run_card", lambda db, card, documents, *a, **k:
                        (events.append(("run", list(documents))), (None, "done", None))[1])
    job_id = runner.enqueue(db, {"runs": [CARD], "skipped": []}, documents=ids, started_by="owner")
    out = runner._run_the_plan(db, job_id)
    runs = [e for e in events if e[0] == "run"]
    assert len(runs) == 2 and events[0] == ("ahead", runs[1][1]), (events, out)
    assert [e for e in events if e[0] == "ahead"] == [events[0]], "the last batch sends nothing ahead"
