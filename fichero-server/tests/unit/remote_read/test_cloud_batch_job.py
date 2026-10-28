"""A recipe step sent as a provider batch: one `cloud-batch` row under the step (spec: recipe-steps-at-scale, #5940).

`compute.recipe.cloud-batch-adopted-by-id`, `.cloud-batch-retries-failed-requests-only`, `.cloud-batch-stop-cancels`.
The provider is a fake with the batch clients' four calls; the capture is a fake returning the step's calls. The row,
its detail and the answers file are real.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import provider_batch as pb
from fichero_server.remote_read import cloud_batch

REQS = [pb.BatchRequest(key=f"{i:064x}", prompt="Read.", images=()) for i in range(4)]


class FakeProvider:
    name, cap_bytes = "Anthropic", 10**9

    def __init__(self, db=None, job_id=None, polls_open=1):
        self.db, self.job_id, self.polls_open = db, job_id, polls_open
        self.sent, self.cancelled, self.polls, self.seen_ids_on_row = [], [], 0, None

    def submit(self, model, requests, *, max_tokens):
        self.sent.append([r.key for r in requests])
        return {"batch_id": f"b{len(self.sent)}"}

    def poll(self, ids):
        self.polls += 1
        if self.seen_ids_on_row is None and self.db is not None:  # what a restart now would find on the row
            detail = json.loads(jobs.read_job(self.db, self.job_id)["detail"])
            self.seen_ids_on_row = [b["ids"] for b in detail["batches"]]
        if ids["batch_id"] == "gone":
            return {"state": "gone"}
        return {"state": "open"} if self.polls <= self.polls_open and not self.cancelled else {"state": "ended"}

    def lines(self, ids):
        sent = self.sent[int(ids["batch_id"][1:]) - 1]
        return [pb.BatchLine(sent[0], True, text="uno"), *(pb.BatchLine(k, False, why="Anthropic: overloaded") for k in sent[1:2]),
                *(pb.BatchLine(k, True, text="más") for k in sent[2:])]

    def cancel(self, ids):
        self.cancelled.append(ids["batch_id"])


@pytest.fixture
def row(db, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    job_id = jobs.enqueue_remote(db, cloud_batch.KIND, "batch:t", target="anthropic", reason="Waiting",
                                 started_by="owner", detail=json.dumps({"provider": "anthropic", "model": "claude-opus-5-5",
                                                                        "max_tokens": 2048}))
    return job_id


def _run(db, job_id, provider, capture=lambda db, detail: REQS):
    return cloud_batch.run(db, "batch:t", client=provider, capture=capture, sleep=lambda s: None)


def test_the_steps_calls_go_as_one_batch_its_ids_on_the_row_before_the_first_poll_and_its_answers_kept(db, row):
    """WHY (`.cloud-batch-adopted-by-id`, `.cloud-batch-retries-failed-requests-only`): the batch id is on the row the
    moment the provider acknowledges it (a restart finds it); answered lines go to the answers file; a failed line is
    not kept, so it is asked again, alone."""
    provider = FakeProvider(db, row)
    out = _run(db, row, provider)
    assert provider.sent == [[r.key for r in REQS]] and provider.seen_ids_on_row == [{"batch_id": "b1"}]
    book = pb.AnswerBook(cloud_batch._work_dir(row) / "answers.jsonl").answers()
    assert set(book) == {REQS[0].key, REQS[2].key, REQS[3].key}
    assert out == {"answered": 3, "failed": 1}
    assert "1 failed" in jobs.read_job(db, row)["reason"]


def test_a_resumed_run_adopts_its_open_batch_by_id_and_a_rerun_sends_only_what_was_not_answered(db, row):
    """WHY (`.cloud-batch-adopted-by-id`, #6127): a run whose batch is on its row polls that batch and never submits
    again; run again after it ended, only the line that failed is sent."""
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail["batches"] = [{"ids": {"batch_id": "b1"}, "state": "open"}]
    jobs.save_detail(db, row, json.dumps(detail))
    provider = FakeProvider()
    provider.sent = [[r.key for r in REQS]]  # what b1 held, as the provider still has it
    _run(db, row, provider)
    assert provider.sent == [[r.key for r in REQS]], "adopted by its id: nothing submitted"

    again = FakeProvider()
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail.pop("batches")
    jobs.save_detail(db, row, json.dumps(detail))
    _run(db, row, again)
    assert again.sent == [[REQS[1].key]], "only the failed line is asked again"


def test_a_batch_the_provider_forgot_is_dropped_and_its_pages_are_left_to_be_asked_again(db, row):
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail["batches"] = [{"ids": {"batch_id": "gone"}, "state": "open"}]
    jobs.save_detail(db, row, json.dumps(detail))
    out = _run(db, row, FakeProvider())
    assert out == {"answered": 0, "failed": 0}
    assert json.loads(jobs.read_job(db, row)["detail"])["batches"][0]["state"] == "gone"


def test_stop_cancels_the_batch_polls_it_to_its_end_and_keeps_what_was_answered(db, row):
    """WHY (`.cloud-batch-stop-cancels`, #5946): Stop reaches the provider; the lines answered before it are billed, so
    they are kept; only then does the row read Stopped."""
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [row])  # the lane claimed it, as in a run
    provider = FakeProvider(polls_open=10)
    original_poll = provider.poll

    def poll_then_stop(ids):
        if provider.polls == 0:
            cloud_batch.request_cancel(db, row)
        return original_poll(ids)

    provider.poll = poll_then_stop
    with pytest.raises(jobs.JobCancelled, match="Stopped"):
        _run(db, row, provider)
    assert provider.cancelled == ["b1"]
    assert len(pb.AnswerBook(cloud_batch._work_dir(row) / "answers.jsonl").answers()) == 3
