"""A recipe step on a provider's batch API (spec: recipe-steps-at-scale, #5940).

`compute.recipe.cloud-batch-above-threshold`, `.cloud-batch-retries-failed-requests-only`: one client per API shape,
each driven here against a fake of the provider's own SDK surface (no network, no key): the requests the client
builds, the states it reads, the lines it lands.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace as NS

import pytest

from fichero_server.llm import provider_batch as pb

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8page").decode()


def _requests(n=3):
    return [pb.BatchRequest(key=f"{i:064x}", prompt="Read the lines.", images=(JPEG,)) for i in range(n)]


# --- which pages go as a batch ----------------------------------------------------------------------------------

def test_a_step_goes_as_a_batch_from_the_threshold_and_never_when_a_person_waits():
    """WHY (`compute.recipe.cloud-batch-above-threshold`, ruling 4): 100 pages of one step on one cloud model in a run
    nobody waits on go as a batch; fewer, or a press a person waits on, are plain calls."""
    assert pb.goes_as_batch(100, waiting=False) and not pb.goes_as_batch(99, waiting=False)
    assert not pb.goes_as_batch(5000, waiting=True)


def test_a_recipe_batch_past_the_providers_byte_cap_is_cut_into_batches_that_fit():
    """WHY: a provider refuses a batch over its cap (256 MB Anthropic); the pages are cut into as many as fit, in order."""
    reqs = _requests(5)
    cut = pb.cut_to_cap(reqs, cap_bytes=2 * pb.request_bytes(reqs[0]))
    assert [len(c) for c in cut] == [2, 2, 1] and [r.key for c in cut for r in c] == [r.key for r in reqs]


# --- Anthropic Message Batches: inline -----------------------------------------------------------------------------

class NotFound(Exception):
    """What each SDK raises for an id it no longer knows: an error carrying the HTTP 404."""

    status_code = 404


class FakeAnthropic:
    """The surface of `anthropic.Anthropic().messages.batches` the client uses."""

    def __init__(self):
        self.created, self.cancelled, self.state = [], [], "in_progress"
        self.messages = NS(batches=self)

    def create(self, *, requests):
        self.created.append(requests)
        return NS(id="msgbatch_1", processing_status="in_progress")

    def retrieve(self, batch_id):
        if batch_id != "msgbatch_1":
            raise NotFound(batch_id)
        return NS(id=batch_id, processing_status=self.state,
                  request_counts=NS(processing=0, succeeded=2, errored=1, canceled=0, expired=0))

    def results(self, batch_id):
        keys = [r["custom_id"] for r in self.created[0]]
        usage = NS(input_tokens=1200, output_tokens=80)
        return [NS(custom_id=keys[0], result=NS(type="succeeded", message=NS(
                    content=[NS(type="text", text="En la ciudad")], usage=usage))),
                NS(custom_id=keys[1], result=NS(type="errored", error=NS(error=NS(type="overloaded_error",
                                                                                   message="Overloaded")))),
                NS(custom_id=keys[2], result=NS(type="expired"))]

    def cancel(self, batch_id):
        self.cancelled.append(batch_id)


def test_anthropic_sends_one_inline_batch_keyed_by_the_cache_key_and_lands_each_line_by_its_key():
    """WHY (`.cloud-batch-above-threshold`, `.cloud-batch-retries-failed-requests-only`): one request per page, its
    `custom_id` the result-cache key, the image as base64; a succeeded line lands with its usage, an errored or expired
    one is that page's failure in the provider's words, whatever the others did."""
    fake = FakeAnthropic()
    client = pb.AnthropicBatches(fake)
    ids = client.submit("claude-opus-5-5", _requests(), max_tokens=2048)

    assert ids == {"batch_id": "msgbatch_1"}
    (sent,) = fake.created
    assert [r["custom_id"] for r in sent] == [r.key for r in _requests()]
    params = sent[0]["params"]
    assert params["model"] == "claude-opus-5-5" and params["max_tokens"] == 2048
    image, text = params["messages"][0]["content"]
    assert image == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                   "data": JPEG.split(",", 1)[1]}}
    assert text == {"type": "text", "text": "Read the lines."}

    assert client.poll(ids)["state"] == "open"
    fake.state = "ended"
    assert client.poll(ids) == {"state": "ended", "counts": {"succeeded": 2, "failed": 1, "open": 0}}
    ok, errored, expired = client.lines(ids)
    assert (ok.ok, ok.text, ok.usage) == (True, "En la ciudad", {"input_tokens": 1200, "output_tokens": 80})
    assert (errored.ok, errored.why) == (False, "Anthropic: overloaded_error: Overloaded")
    assert (expired.ok, expired.why) == (False, "Anthropic: expired before it was answered")

    client.cancel(ids)
    assert fake.cancelled == ["msgbatch_1"]


def test_a_batch_the_provider_no_longer_knows_reads_gone():
    """WHY (`compute.recipe.cloud-batch-adopted-by-id`): past retention the id is dropped and its unlanded pages replanned."""
    assert pb.AnthropicBatches(FakeAnthropic()).poll({"batch_id": "msgbatch_old"})["state"] == "gone"


def test_a_request_with_no_image_or_a_key_the_provider_refuses_is_refused_here():
    with pytest.raises(ValueError, match="custom_id"):
        pb.AnthropicBatches(FakeAnthropic()).submit("m", [pb.BatchRequest(key="a b", prompt="x", images=())],
                                                    max_tokens=10)


# --- OpenAI Batch: a file -----------------------------------------------------------------------------------------

class FakeOpenAI:
    """The surface of `openai.OpenAI()` the client uses: `files.create/content`, `batches.create/retrieve/cancel`."""

    def __init__(self, status="in_progress"):
        self.uploaded, self.made, self.cancelled, self.status = [], [], [], status
        self.files, self.batches = NS(create=self._upload, content=self._content), NS(
            create=self._create, retrieve=self._retrieve, cancel=self.cancelled.append)

    def _upload(self, *, file, purpose):
        self.uploaded.append((file, purpose))
        return NS(id="file-in")

    def _create(self, **kw):
        self.made.append(kw)
        return NS(id="batch_1", status="validating")

    def _retrieve(self, batch_id):
        if batch_id != "batch_1":
            raise NotFound(batch_id)
        return NS(id=batch_id, status=self.status, output_file_id="file-out", error_file_id="file-err",
                  request_counts=NS(total=3, completed=1, failed=2), errors=None)

    def _content(self, file_id):
        keys = [json.loads(line)["custom_id"] for line in self.uploaded[0][0][1].decode().splitlines()]
        body = {"choices": [{"message": {"content": "En la ciudad"}}], "usage": {"prompt_tokens": 900,
                                                                                 "completion_tokens": 60}}
        rows = {"file-out": [{"custom_id": keys[0], "response": {"status_code": 200, "body": body}, "error": None},
                             {"custom_id": keys[1], "response": {"status_code": 429, "body": {
                                 "error": {"message": "Rate limit"}}}, "error": None}],
                "file-err": [{"custom_id": keys[2], "response": None,
                              "error": {"code": "batch_expired", "message": "not done in 24h"}}]}[file_id]
        return NS(text="\n".join(json.dumps(r) for r in rows))


def test_openai_sends_one_file_of_one_model_and_lands_answers_and_errors_by_custom_id():
    """WHY (`.cloud-batch-above-threshold`, `.cloud-batch-retries-failed-requests-only`): OpenAI takes a `.jsonl` file of
    chat requests, the image as an `image_url`; answers and failures come back in two files, in any order, matched by
    `custom_id`; a failed line is that page's failure in OpenAI's words."""
    fake = FakeOpenAI()
    client = pb.OpenAIBatches(fake)
    ids = client.submit("gpt-5", _requests(), max_tokens=2048)

    assert ids == {"batch_id": "batch_1", "input_file_id": "file-in"}
    ((name, data), purpose), = fake.uploaded
    assert purpose == "batch" and name.endswith(".jsonl")
    first = json.loads(data.decode().splitlines()[0])
    assert (first["custom_id"], first["method"], first["url"]) == (_requests()[0].key, "POST", "/v1/chat/completions")
    assert first["body"]["model"] == "gpt-5" and first["body"]["max_completion_tokens"] == 2048
    assert first["body"]["messages"][0]["content"] == [{"type": "text", "text": "Read the lines."},
                                                        {"type": "image_url", "image_url": {"url": JPEG}}]
    assert fake.made == [{"input_file_id": "file-in", "endpoint": "/v1/chat/completions", "completion_window": "24h"}]

    assert client.poll(ids)["state"] == "open"
    fake.status = "expired"
    assert client.poll(ids) == {"state": "ended", "counts": {"succeeded": 1, "failed": 2, "open": 0}}
    ok, limited, expired = sorted(client.lines(ids), key=lambda line: line.key)
    assert (ok.text, ok.usage) == ("En la ciudad", {"input_tokens": 900, "output_tokens": 60})
    assert (limited.ok, limited.why) == (False, "OpenAI: 429: Rate limit")
    assert (expired.ok, expired.why) == (False, "OpenAI: batch_expired: not done in 24h")
    assert pb.OpenAIBatches(fake).poll({"batch_id": "gone"})["state"] == "gone"


# --- Gemini Batch Mode: by file, so each answer comes back under its key --------------------------------------------

class FakeGemini:
    """The surface of `google.genai.Client()` the client uses: `files.upload/download`, `batches.create/get/cancel`."""

    def __init__(self):
        self.uploaded, self.made, self.cancelled, self.state = [], [], [], "JOB_STATE_RUNNING"
        self.files = NS(upload=self._upload, download=self._download)
        self.batches = NS(create=self._create, get=self._get, cancel=lambda *, name: self.cancelled.append(name))

    def _upload(self, *, file, config):
        self.uploaded.append((file.read(), config))
        return NS(name="files/in")

    def _create(self, *, model, src, config=None):
        self.made.append((model, src))
        return NS(name="batches/1", state=NS(name="JOB_STATE_PENDING"))

    def _get(self, *, name):
        if name != "batches/1":
            raise NotFound(name)
        return NS(name=name, state=NS(name=self.state), dest=NS(file_name="files/out"))

    def _download(self, *, file):
        keys = [json.loads(line)["key"] for line in self.uploaded[0][0].decode().splitlines()]
        rows = [{"key": keys[0], "response": {"candidates": [{"content": {"parts": [{"text": "En la ciudad"}]}}],
                                              "usageMetadata": {"promptTokenCount": 700, "candidatesTokenCount": 40}}},
                {"key": keys[1], "error": {"code": 400, "message": "Image too large"}}]
        return "\n".join(json.dumps(r) for r in rows).encode()


def test_gemini_sends_a_file_of_keyed_requests_and_lands_each_answer_under_its_key():
    """WHY (`.cloud-batch-above-threshold`): a batch with images goes to Gemini as a FILE (its inline batches answer by
    position, not key); the answer file's lines land under their keys, a failed one in Gemini's words, and a request
    with no line at all is left for the caller to call failed."""
    fake = FakeGemini()
    client = pb.GeminiBatches(fake)
    ids = client.submit("gemini-3-pro", _requests(), max_tokens=2048)

    assert ids == {"batch_id": "batches/1", "input_file_id": "files/in"}
    data, config = fake.uploaded[0]
    first = json.loads(data.decode().splitlines()[0])
    assert first["key"] == _requests()[0].key and config["mime_type"] == "jsonl"
    assert first["request"]["contents"][0]["parts"] == [
        {"text": "Read the lines."}, {"inline_data": {"mime_type": "image/jpeg", "data": JPEG.split(",", 1)[1]}}]
    assert first["request"]["generation_config"] == {"max_output_tokens": 2048}
    assert fake.made == [("gemini-3-pro", "files/in")]

    assert client.poll(ids)["state"] == "open"
    fake.state = "JOB_STATE_SUCCEEDED"
    assert client.poll(ids)["state"] == "ended"
    ok, refused = client.lines(ids)
    assert (ok.text, ok.usage) == ("En la ciudad", {"input_tokens": 700, "output_tokens": 40})
    assert (refused.ok, refused.why) == (False, "Gemini: 400: Image too large")
    assert client.poll({"batch_id": "batches/old"})["state"] == "gone"
    client.cancel(ids)
    assert fake.cancelled == ["batches/1"]


# --- the seam in llm.vision: the step's own calls, captured, then answered from the batch --------------------------

def test_the_steps_own_vision_calls_are_captured_and_then_answered_from_the_batch(monkeypatch):
    """WHY (`compute.recipe.cloud-batch-above-threshold`, `ai.where.batch-results-land-once`): the requests a batch sends
    are the step's own calls, captured under their cache keys (nothing is called); the step run again is answered from
    the batch's lines under the same keys, so each lands as the pass a plain call writes; a call with no answer (a line
    that failed) goes as a plain call."""
    import asyncio

    from fichero_server import llm

    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda config, kind: None)
    plain = []

    def no_plain_call(config):
        plain.append(config.model)
        raise RuntimeError("a plain call")

    monkeypatch.setattr(llm, "get_langchain_model", no_plain_call)
    config = llm.LLMConfig(provider="anthropic", model="claude-opus-5-5")
    with pb.capturing(answer=lambda prompt: '["x"]') as captured:
        said = asyncio.run(llm.vision([JPEG], "Read the line.", config))
    key = llm._vision_cache_key(config, "Read the line.", [JPEG])
    assert said == '["x"]' and plain == []
    assert captured == [pb.BatchRequest(key=key, prompt="Read the line.", images=(JPEG,))]

    with pb.answering({key: '["En la ciudad"]'}):
        assert asyncio.run(llm.vision([JPEG], "Read the line.", config)) == '["En la ciudad"]'
        with pytest.raises(RuntimeError, match="a plain call"):
            asyncio.run(llm.vision([JPEG], "Another prompt.", config))
    assert plain == ["claude-opus-5-5"]


def test_the_answers_are_kept_on_disk_so_a_resume_or_rerun_sends_no_answered_page_again(tmp_path):
    """WHY (`compute.recipe.cloud-batch-adopted-by-id`, never rerun a model pass #6127): each answered line is written to
    the run's answers file as it lands; after a restart the book is read back, its keys are left out of the next batch,
    and the step run again is answered from it. A failed line is not kept: it is asked again."""
    book = pb.AnswerBook(tmp_path / "answers.jsonl")
    reqs = _requests(3)
    book.keep([pb.BatchLine(reqs[0].key, True, text="uno"), pb.BatchLine(reqs[1].key, False, why="Overloaded")])
    again = pb.AnswerBook(tmp_path / "answers.jsonl")  # the engine restarted
    assert again.answers() == {reqs[0].key: "uno"}
    assert [r.key for r in again.still_to_send(reqs)] == [reqs[1].key, reqs[2].key]
    again.keep([pb.BatchLine(reqs[0].key, True, text="uno")])  # landed twice: kept once
    assert len((tmp_path / "answers.jsonl").read_text().splitlines()) == 1


# --- what a batch costs, and the cap --------------------------------------------------------------------------------

def test_a_batch_is_priced_at_the_listed_batch_price_else_half_the_listed_price():
    """WHY (`compute.recipe.cloud-batch-consent-and-cost`): a model whose price list has a batch price is booked at it;
    one with no batch price at half its listed price, as the providers bill; a model with no price at all is None."""
    from fichero_server.llm import spend
    from fichero_server.llm.usage import price_call

    listed = price_call({"provider": "openai", "model": "gpt-4o", "input_tokens": 1000, "output_tokens": 100}).cost_usd
    assert spend.batch_cost_usd("openai", "gpt-4o", 1000, 100) == pytest.approx(listed / 2)
    half = price_call({"provider": "anthropic", "model": "claude-sonnet-4-5", "input_tokens": 1000,
                       "output_tokens": 100})
    if half.priced:
        assert spend.batch_cost_usd("anthropic", "claude-sonnet-4-5", 1000, 100) == pytest.approx(half.cost_usd / 2)
    assert spend.batch_cost_usd("openai", "no-such-model-xyz", 1000, 100) is None


def test_a_batch_that_could_pass_the_cap_is_refused_before_it_is_sent_and_one_that_fits_is_held_then_booked(tmp_path):
    """WHY (`compute.recipe.cloud-batch-consent-and-cost`, `ai.where.cloud-spend-cap`): the cap holds the batch's worst
    case at the batch price from submission (it may answer a day later); when it ends, the hold is let go and what its
    lines were billed is booked."""
    from fichero_server.llm import spend

    library = str(tmp_path)
    (tmp_path / ".fichero").mkdir()  # no setup: the default cap
    worst_one = spend.batch_worst_usd("openai", "gpt-4o", max_tokens=2048)
    with pytest.raises(spend.CloudSpendRefusedError, match="capped"):
        spend.reserve_batch(library, "openai", "gpt-4o", requests=int(spend.DEFAULT_CAP_USD / worst_one) + 10,
                            max_tokens=2048)
    held = spend.reserve_batch(library, "openai", "gpt-4o", requests=3, max_tokens=2048)
    assert held == pytest.approx(3 * worst_one) and spend.booked_usd(library) == 0
    spend.settle_batch(library, held, 0.012)
    assert spend.booked_usd(library) == pytest.approx(0.012)
    assert spend._RESERVED.get(library, 0) == pytest.approx(0)
