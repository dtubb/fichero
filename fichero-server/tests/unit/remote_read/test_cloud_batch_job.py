"""A recipe step sent as a provider batch: one `cloud-batch` row under the step (spec: recipe-steps-at-scale, #5940).

`compute.recipe.cloud-batch-adopted-by-id`, `.cloud-batch-retries-failed-requests-only`, `.cloud-batch-stop-cancels`.
The provider is a fake with the batch clients' four calls; the capture is a fake returning the step's calls. The row,
its detail and the answers file are real.
"""
from __future__ import annotations

import json
from pathlib import Path

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
        return [pb.BatchLine(sent[0], True, text="uno", usage={"input_tokens": 1000, "output_tokens": 100}), *(pb.BatchLine(k, False, why="Anthropic: overloaded") for k in sent[1:2]),
                *(pb.BatchLine(k, True, text="más") for k in sent[2:])]

    def cancel(self, ids):
        self.cancelled.append(ids["batch_id"])


@pytest.fixture
def row(db, tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    job_id = jobs.enqueue_remote(db, cloud_batch.KIND, "batch:t", target="anthropic", reason="Waiting",
                                 started_by="owner", detail=json.dumps({"provider": "openai", "model": "gpt-4o",
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
    book = cloud_batch.book_for(db).answers()
    assert set(book) == {REQS[0].key, REQS[2].key, REQS[3].key}
    assert out == {"answered": 3, "failed": 1}
    assert "1 failed" in jobs.read_job(db, row)["reason"]


def test_a_resumed_run_adopts_its_open_batch_by_id_and_a_rerun_sends_only_what_was_not_answered(db, row):
    """WHY (`.cloud-batch-adopted-by-id`, #6127): a run whose batch is on its row polls that batch and never submits
    again; run again after it ended, only the line that failed is sent."""
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail.update(batches=[{"ids": {"batch_id": "b1"}, "state": "open"}], submitted=True)
    jobs.save_detail(db, row, json.dumps(detail))
    provider = FakeProvider()
    provider.sent = [[r.key for r in REQS]]  # what b1 held, as the provider still has it
    _run(db, row, provider)
    assert provider.sent == [[r.key for r in REQS]], "adopted by its id: nothing submitted"

    again = FakeProvider()
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail.pop("batches"), detail.pop("submitted")  # the step run again: a new submission over the same pages
    jobs.save_detail(db, row, json.dumps(detail))
    _run(db, row, again)
    assert again.sent == [[REQS[1].key]], "only the failed line is asked again"


def test_a_batch_the_provider_forgot_is_dropped_and_its_pages_are_left_to_be_asked_again(db, row):
    detail = json.loads(jobs.read_job(db, row)["detail"])
    detail.update(batches=[{"ids": {"batch_id": "gone"}, "state": "open"}], submitted=True)
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
    assert len(cloud_batch.book_for(db).answers()) == 3


# --- starting one: the gates, the client ------------------------------------------------------------------------

def _card(provider="anthropic"):
    return {"steps": ["read"], "card": "workflow", "job": "read-a-line", "runs_on": f"cloud:{provider}",
            "provider_override": provider, "model_override": "claude-opus-5-5"}


def _parent(db):
    from fichero_server.recipes import runner

    return runner.enqueue(db, {"runs": [_card()], "skipped": []}, documents=None, started_by="owner")


def test_a_batch_needs_the_persons_yes_the_projects_yes_and_the_apps_cloud_place(db, monkeypatch, project_says_yes):
    """WHY (`compute.recipe.cloud-batch-consent-and-cost`, `ai.where.one-egress-gate`): a provider batch is a package
    that is SENT: the request's yes, the project's own yes and the app's cloud place, each refusing in words with
    nothing queued."""
    from fichero_server.recipes import places

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    with pytest.raises(cloud_batch.PagesMayNotLeave, match="yes"):
        cloud_batch.start(db, card=_card(), documents=["p1"], parent_job_id=parent, started_by="owner",
                          pages_may_leave=False)
    monkeypatch.setattr(places, "allows", lambda place, _p=None: place != "cloud")
    with pytest.raises(cloud_batch.PagesMayNotLeave, match="places"):
        cloud_batch.start(db, card=_card(), documents=["p1"], parent_job_id=parent, started_by="owner",
                          pages_may_leave=True)
    monkeypatch.setattr(places, "allows", lambda place, _p=None: True)
    with pytest.raises(ValueError, match="no batch API"):
        cloud_batch.start(db, card=_card("openrouter"), documents=["p1"], parent_job_id=parent, started_by="owner",
                          pages_may_leave=True)
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [cloud_batch.KIND])[0] == 0

    child = cloud_batch.start(db, card=_card(), documents=["p1", "p2"], parent_job_id=parent, started_by="owner",
                              pages_may_leave=True)
    row = jobs.read_job(db, child)
    detail = json.loads(row["detail"])
    assert (row["kind"], jobs.parent_of(db, child)) == (cloud_batch.KIND, parent)
    assert (detail["provider"], detail["model"], detail["documents"]) == ("anthropic", "claude-opus-5-5", ["p1", "p2"])
    assert cloud_batch.out_under(db, parent) == child


def test_a_project_that_keeps_its_pages_here_never_sends_a_batch(db, monkeypatch):
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    from fichero_server.llm import egress

    monkeypatch.setattr(egress, "project_allows_leaving", lambda library: False)
    with pytest.raises(cloud_batch.PagesMayNotLeave, match="keeps its pages"):
        cloud_batch.start(db, card=_card(), documents=["p1"], parent_job_id=_parent(db), started_by="owner",
                          pages_may_leave=True)


def test_the_client_is_made_with_the_providers_own_key_and_refused_by_name_without_one(monkeypatch):
    from fichero_server import llm

    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda config, *, kind: None)  # a project that said yes
    monkeypatch.setattr(llm, "get_api_key", lambda provider: None)
    with pytest.raises(ValueError, match="no Anthropic key"):
        cloud_batch.client_for("anthropic")
    monkeypatch.setattr(llm, "get_api_key", lambda provider: "test-key-not-real")
    assert isinstance(cloud_batch.client_for("anthropic"), pb.AnthropicBatches)
    assert isinstance(cloud_batch.client_for("openai"), pb.OpenAIBatches)
    assert isinstance(cloud_batch.client_for("google"), pb.GeminiBatches)

    def refused(config, *, kind):
        raise PermissionError(f"{config.provider} {kind}: this project keeps its pages here")

    monkeypatch.setattr(llm, "_enforce_local_only_provider", refused)  # the one egress gate, met before the client
    with pytest.raises(PermissionError, match="anthropic batch: this project keeps its pages here"):
        cloud_batch.client_for("anthropic")


def test_each_batch_records_its_wait_and_tokens_and_a_batch_past_twelve_hours_logs_one_line(db, row, caplog):
    """WHY (`compute.recipe.cloud-batch-slow-path-record`, #6251): a provider batch's record is its wait (sent to
    answered) and what it was billed; a batch still out past twelve hours says so once in the log, not every poll."""
    import logging
    from datetime import datetime, timedelta, timezone

    clock = iter(datetime(2026, 10, 28, tzinfo=timezone.utc) + timedelta(hours=h) for h in (0, 13, 14, 15, 16, 17))
    provider = FakeProvider(polls_open=3)
    with caplog.at_level(logging.WARNING, logger="fichero_server.remote_read.cloud_batch"):
        cloud_batch.run(db, "batch:t", client=provider, capture=lambda db, detail: REQS, sleep=lambda s: None,
                        now=lambda: next(clock))
    (batch,) = json.loads(jobs.read_job(db, row)["detail"])["batches"]
    assert batch["sent_at"].startswith("2026-10-28T00:00") and batch["waited_hours"] > 12
    assert batch["tokens"] == {"input_tokens": 1000, "output_tokens": 100}
    slow = [r for r in caplog.records if "twelve hours" in r.getMessage()]
    assert len(slow) == 1 and "Anthropic" in slow[0].getMessage()


def test_the_cap_holds_each_batch_from_submission_and_books_what_its_lines_were_billed(db, row):
    """WHY (`compute.recipe.cloud-batch-consent-and-cost`, `ai.where.cloud-spend-cap`): the hold is on the row (a restart
    holds it again), let go when the batch ends, and what its answered lines cost at the batch price is booked."""
    from pathlib import Path

    from fichero_server.llm import spend

    library = str(Path(db.path).parent)
    _run(db, row, FakeProvider())
    (batch,) = json.loads(jobs.read_job(db, row)["detail"])["batches"]
    assert batch["held_usd"] > 0 and batch["cost_usd"] == pytest.approx(spend.batch_cost_usd("openai", "gpt-4o", 1000, 100))
    assert spend.booked_usd(library) == pytest.approx(batch["cost_usd"])
    assert spend._RESERVED.get(library, 0) == pytest.approx(0)


def test_a_batch_that_would_pass_the_cap_is_never_sent(db, row, monkeypatch):
    from fichero_server.llm import spend

    monkeypatch.setattr(spend, "cap_usd", lambda library: 0.0001)
    provider = FakeProvider()
    with pytest.raises(spend.CloudSpendRefusedError):
        _run(db, row, provider)
    assert provider.sent == []


def test_the_kind_is_a_remote_row_whose_stop_cancels_at_the_provider():
    cloud_batch.register_job_kinds()
    kind = jobs.KINDS[cloud_batch.KIND]
    assert (kind.lane, kind.cancel, kind.run is not None) == ("remote", cloud_batch.request_cancel, True)


def _ended(db, child, answers):
    """The row as the batch leaves it: its answers kept, the row done."""
    cloud_batch.book_for(db).keep([pb.BatchLine(k, True, text=t) for k, t in answers.items()])
    db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [child])
    return child, "done", None


def test_the_step_sends_one_batch_waits_on_it_and_lands_its_pages_through_the_replay(db, monkeypatch, tmp_path,
                                                                                      project_says_yes):
    """WHY (`compute.recipe.cloud-batch-above-threshold`, design A): the step queues one batch row under itself, waits
    on it as on any child, then runs once more with each call answered from the batch's lines, so its pages land
    through the step's own path; a resumed step adopts the row and never queues another."""
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    waited, answered_in_replay = [], []

    def wait(db, child, parent):
        waited.append(child)
        return _ended(db, child, {REQS[0].key: "En la villa"})

    def replay():
        answered_in_replay.append(pb.through_the_seam(REQS[0].key, "Read.", []).text)
        return "thread-replay", "done", None

    out = cloud_batch.run_step(db, _card(), ["p1", "p2"], parent, "owner", wait=wait, replay=replay)
    assert out == ("thread-replay", "done", None) and answered_in_replay == ["En la villa"]
    assert len(waited) == 1 and jobs.parent_of(db, waited[0]) == parent
    assert pb.through_the_seam(REQS[0].key, "Read.", []) is None, "the answers reach the replay only"

    db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [waited[0]])  # a restart mid-wait
    cloud_batch.run_step(db, _card(), ["p1", "p2"], parent, "owner", wait=wait, replay=replay)
    assert waited[1] == waited[0]
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [cloud_batch.KIND])[0] == 1


def test_a_batch_that_failed_or_stopped_ends_the_step_with_no_replay(db, monkeypatch, tmp_path, project_says_yes):
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    out = cloud_batch.run_step(db, _card(), ["p1"], _parent(db), "owner",
                               wait=lambda db, child, parent: (child, "failed", "Anthropic: no key"),
                               replay=lambda: pytest.fail("a failed batch replays nothing"))
    assert out[1:] == ("failed", "Anthropic: no key")


def test_a_step_whose_pages_may_not_leave_fails_in_words_with_nothing_queued(db, monkeypatch):
    """WHY (`.cloud-batch-consent-and-cost`): the project's no is read when the step runs, not when it was planned."""
    from fichero_server.recipes import places

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(places, "project_says_cloud", lambda answers: False)
    out = cloud_batch.run_step(db, _card(), ["p1"], _parent(db), "owner", wait=lambda *a: pytest.fail("no wait"),
                               replay=lambda: pytest.fail("no replay"))
    assert out[0] is None and out[1] == "failed" and "Anthropic" in out[2]
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [cloud_batch.KIND])[0] == 0


def test_the_plan_sends_a_cloud_read_of_a_hundred_pages_or_more_as_a_batch_and_a_smaller_one_as_plain_calls():
    """WHY (`compute.recipe.cloud-batch-above-threshold`): from 100 pages a cloud reader whose provider has a batch API
    goes as one batch at the batch price; under it, or a provider without one, or a reader per material, plain calls."""
    from fichero_server.recipes.start import place_runs

    def runs(provider="anthropic", **more):
        return [{"steps": ["read"], "job": "read-a-page", "card": "workflow", "provider_override": provider, **more}]

    (big,) = place_runs(runs(), 100, cloud_allowed=False)
    assert big["place"] == "batch" and big["target"] == "anthropic" and "batch" in big["why"]
    for small in (place_runs(runs(), 99, cloud_allowed=False), place_runs(runs("openrouter"), 5_000, cloud_allowed=False),
                  place_runs(runs(readers={"print": {}}), 5_000, cloud_allowed=False),
                  place_runs(runs("kraken"), 5_000, cloud_allowed=False)):
        assert small[0].get("place") != "batch"



def test_the_recipe_runner_sends_a_batch_step_to_the_batch_and_every_other_place_as_before(monkeypatch):
    """WHY (`compute.recipe.cloud-batch-above-threshold`): the plan's `batch` place reaches the batch step, whose
    replay is the step's own run; a step on this Mac (or with no place) runs its workflow as it always has."""
    from fichero_server.recipes import runner

    seen = []
    monkeypatch.setattr(runner, "_run_workflow", lambda db, card, documents, parent, adopt=None:
                        (seen.append(("workflow", card.get("place"))), ("thread-1", "done", None))[1])

    def run_step(db, card, documents, parent, started_by, *, wait, replay):
        seen.append(("batch", parent, started_by, wait is runner._wait))
        return replay()

    monkeypatch.setattr(cloud_batch, "run_step", run_step)
    card = {**_card(), "card": "workflow"}
    assert runner._run_card(None, {**card, "place": "batch"}, ["p1"], {}, "recipe-1", {}, "owner") == ("thread-1", "done", None)
    assert seen == [("batch", "recipe-1", "owner", True), ("workflow", "batch")]
    seen.clear()
    for place in ("this-mac", None):
        runner._run_card(None, {**card, "place": place}, ["p1"], {}, "recipe-1", {}, "owner")
    assert seen == [("workflow", "this-mac"), ("workflow", None)]


def test_the_estimate_prices_a_step_that_goes_as_a_batch_at_the_batch_price(monkeypatch):
    """WHY (`compute.recipe.cloud-batch-consent-and-cost`): the sheet shows what the person will be billed: a step the
    plan sends as a batch at the batch price, said so; under 100 pages, the listed rate, as before."""
    from fichero_server.recipes import start

    # A page read sends the page image (`source.onboard.estimate-counts-the-image`, #6265), batch or not: Claude's capped
    # image is 3,600 tokens in and 400 out a page. 100 pages: 360,000 in, 40,000 out; Sonnet 4.5 lists $3 / $15 a million
    # tokens, so $1.08 + $0.60 = $1.68 at the list rate, and exactly half of it, $0.84, at the batch price.
    step = {"workflow": "Transcribe HTR", "steps": ["read"], "job": "read-a-page", "runs_on": "cloud:anthropic",
            "provider_override": "anthropic", "model_override": "claude-sonnet-4-5"}
    (batch,) = start.estimate([step], 100)["runs"]
    assert batch["basis"] == "the batch price, answered within a day"
    assert batch["cost_usd"] == pytest.approx(0.84, abs=1e-9)
    (plain,) = start.estimate([step], 99)["runs"]
    assert plain["basis"] == "the model's listed rate"
    assert plain["cost_usd"] == pytest.approx(99 * 0.0168, abs=1e-9)
    assert batch["cost_usd"] < plain["cost_usd"] * 100 / 99


def test_a_batch_keeps_the_sheets_estimate_and_its_billed_cost_and_says_once_when_it_cost_more(db, monkeypatch, caplog,
                                                                                               project_says_yes):
    """WHY (`compute.recipe.cloud-batch-slow-path-record`, #6251): the row carries what the sheet said the batch would
    cost (the same rule `start.estimate` prices by) and what its lines were billed; over the estimate, one log line."""
    import logging

    from fichero_server.llm import spend
    from fichero_server.recipes import start

    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    child = cloud_batch.start(db, card=_card(), documents=["p1", "p2"], parent_job_id=_parent(db), started_by="owner",
                              pages_may_leave=True)
    detail = json.loads(jobs.read_job(db, child)["detail"])
    assert detail["estimate_usd"] == pytest.approx(spend.batch_cost_usd("anthropic", "claude-opus-5-5",
                                                                       2 * start._TOKENS_IN, 2 * start._TOKENS_OUT))
    detail["estimate_usd"] = 1e-9  # the sheet guessed low
    jobs.save_detail(db, child, json.dumps(detail))
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: db.path.parent / job_id)
    subject = jobs.read_job(db, child)["subject"]
    with caplog.at_level(logging.WARNING, logger="fichero_server.remote_read.cloud_batch"):
        cloud_batch.run(db, subject, client=FakeProvider(polls_open=0), capture=lambda db, d: REQS, sleep=lambda s: None)
    detail = json.loads(jobs.read_job(db, child)["detail"])
    assert detail["cost_usd"] == pytest.approx(sum(b["cost_usd"] for b in detail["batches"])) and detail["cost_usd"] > 0
    over = [r for r in caplog.records if "over its estimate" in r.getMessage()]
    assert len(over) == 1 and "Anthropic" in over[0].getMessage()


def test_a_batch_step_adopts_only_the_batch_out_for_its_own_pages(db, monkeypatch, tmp_path, project_says_yes):
    """WHY (#6127, pipelined batches): a recipe row with one batch out for pages p1..p2 starts the next batch's step on
    p3: it sends its own batch, never waits on the other's."""
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    first = cloud_batch.start(db, card=_card(), documents=["p1", "p2"], parent_job_id=parent, started_by="owner",
                              pages_may_leave=True)
    waited = []
    cloud_batch.run_step(db, _card(), ["p3"], parent, "owner", wait=lambda db, child, p: (waited.append(child),
                         (child, "failed", "x"))[1], replay=lambda: pytest.fail("no replay"))
    assert waited and waited[0] != first
    assert cloud_batch.out_under(db, parent, ["p2", "p1"]) == first


def test_a_rerun_after_a_failed_replay_adopts_the_ended_batch_and_never_pays_twice(db, monkeypatch, tmp_path,
                                                                                 project_says_yes):
    """WHY (review 3, HIGH; #6127): the batch ended and its replay failed (or was parked); Start again adopts the ended
    batch's answers and replays, never queuing a second batch for pages already answered and paid for."""
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    waits = []

    def wait(db, child, parent):
        waits.append(child)
        return _ended(db, child, {REQS[0].key: "x"})

    cloud_batch.run_step(db, _card(), ["p1"], parent, "o", wait=wait, replay=lambda: ("t", "failed", "boom"))
    replayed = []
    cloud_batch.run_step(db, _card(), ["p1"], parent, "o", wait=wait,
                         replay=lambda: (replayed.append(pb.through_the_seam(REQS[0].key, "", []).text), ("t", "done", None))[1])
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [cloud_batch.KIND])[0] == 1
    assert len(waits) == 1 and replayed == ["x"], "the ended batch is not waited on again; its answers replay"


def test_a_new_batch_after_a_failed_one_sends_only_what_was_never_answered(db, row, tmp_path):
    """WHY (review 3, HIGH): the answers are the project's, by content key, not one row's: a batch row queued after a
    failed one leaves out every page an earlier batch answered."""
    _run(db, row, FakeProvider())  # answers REQS 0, 2, 3; 1 failed
    second = jobs.enqueue_remote(db, cloud_batch.KIND, "batch:t2", target="anthropic", reason="Waiting",
                                 started_by="owner", detail=json.dumps({"provider": "openai", "model": "gpt-4o",
                                                                        "max_tokens": 2048}))
    provider = FakeProvider()
    cloud_batch.run(db, "batch:t2", client=provider, capture=lambda db, d: REQS, sleep=lambda s: None)
    assert provider.sent == [[REQS[1].key]] and second


def test_a_poll_that_raises_lets_go_of_the_hold_so_a_retry_does_not_hold_it_twice(db, row):
    """WHY (review 3, MED): the hold lives in this process; a run that raised mid-poll leaves it held, and the Retry
    holds it again on adoption, until the cap refuses batches that would fit."""
    from fichero_server.llm import spend

    library = str(Path(db.path).parent)

    class Boom(FakeProvider):
        def poll(self, ids):
            raise ConnectionError("net")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            _run(db, row, Boom())
        assert spend._RESERVED.get(library, 0) == 0


def test_a_crash_mid_submit_sends_the_rest_as_a_batch_on_resume(db, row):
    """WHY (review 3, LOW): the engine stopped after the first of two chunks was submitted; the resume submits the
    second as a batch (at the batch price), not leaving its pages to go as plain calls at the full one."""
    class Cap(FakeProvider):
        cap_bytes = 2 * pb.request_bytes(REQS[0])

    class Crash(Cap):
        def submit(self, model, requests, *, max_tokens):
            if self.sent:
                raise SystemExit("the engine went away")
            self.sent.append([r.key for r in requests])
            return {"batch_id": "first"}

    class Resumed(Cap):
        def lines(self, ids):
            if ids["batch_id"] == "first":
                return [pb.BatchLine(r.key, True, text="uno") for r in REQS[:2]]
            return super().lines(ids)

    with pytest.raises(SystemExit):
        _run(db, row, Crash(polls_open=0))
    provider = Resumed(polls_open=0)
    _run(db, row, provider)
    assert provider.sent == [[REQS[2].key, REQS[3].key]], "only the chunk never submitted, as one batch"


def test_a_batch_row_set_aside_as_failed_with_a_batch_still_open_is_followed_never_sent_twice(db, monkeypatch, tmp_path,
                                                                                            project_says_yes):
    """WHY (review 4 MED): a restart-worn row failed while its batch is open at the provider; the step's rerun adopts it
    and waits on it, never queuing a second batch that bills the same pages again."""
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    first = cloud_batch.start(db, card=_card(), documents=["p1"], parent_job_id=parent, started_by="owner",
                              pages_may_leave=True)
    detail = json.loads(jobs.read_job(db, first)["detail"])
    detail["batches"] = [{"ids": ["b1"], "state": "open", "requests": 1}]
    jobs.save_detail(db, first, json.dumps(detail))
    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [first])
    waited = []
    cloud_batch.run_step(db, _card(), ["p1"], parent, "o", wait=lambda db, child, p: (waited.append(child), (child, "failed", "x"))[1],
                         replay=lambda: pytest.fail("no replay"))
    assert waited == [first] and jobs.read_job(db, first)["state"] == "waiting"
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [cloud_batch.KIND])[0] == 1


def test_a_failed_batch_row_with_nothing_open_is_not_adopted(db, monkeypatch, tmp_path, project_says_yes):
    monkeypatch.setattr(cloud_batch, "_work_dir", lambda job_id: tmp_path / job_id)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    parent = _parent(db)
    first = cloud_batch.start(db, card=_card(), documents=["p1"], parent_job_id=parent, started_by="owner",
                              pages_may_leave=True)
    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [first])
    assert cloud_batch._ended_under(db, parent, ["p1"]) is None


def test_resume_leaves_a_batch_and_a_recipe_with_one_out_running_after_every_restart(db, monkeypatch, tmp_path):
    """WHY (#5540, review 4 MED): a cloud batch is far-side like a read; a recipe run with one out is not set aside."""
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    recipe = jobs.enqueue(db, "run-a-recipe", "r1", started_by="owner")
    lone = jobs.enqueue(db, "run-a-recipe", "r2", started_by="owner")
    batch = jobs.enqueue_remote(db, cloud_batch.KIND, "batch:1", target="anthropic", detail="{}", reason="x",
                                started_by="owner")
    jobs.set_parent(db, batch, recipe)
    db.execute("UPDATE jobs SET state = 'running', attempts = ? WHERE id IN (?, ?, ?)",
               [jobs.MAX_ATTEMPTS + 2, recipe, lone, batch])
    jobs.resume(db)
    states = {i: jobs.read_job(db, i)["state"] for i in (recipe, lone, batch)}
    assert states == {recipe: "waiting", lone: "failed", batch: "waiting"}  # picked up again, not set aside
