"""A recipe step on a provider's batch API (spec: recipe-steps-at-scale, #5940).

`compute.recipe.cloud-batch-above-threshold`, `.cloud-batch-retries-failed-requests-only`: one client per API shape,
each driven here against a fake of the provider's own SDK surface (no network, no key): the requests the client
builds, the states it reads, the lines it lands.
"""
from __future__ import annotations

import base64
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
