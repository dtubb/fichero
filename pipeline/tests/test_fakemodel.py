"""The fake model server streams scripted steps like the real API and records requests (stage 0)."""
import json
import urllib.error
import urllib.request

import pytest

from pipeline.fakemodel import FakeModel


def post(fm, body=None):
    req = urllib.request.Request(fm.url + "/chat/completions", json.dumps(body or {"model": "m"}).encode(), {"content-type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


def events(resp):
    return [json.loads(line[6:]) for line in resp.read().decode().splitlines() if line.startswith("data: {")]


@pytest.fixture
def fm():
    m = FakeModel()
    yield m
    m.close()


def test_steps_come_in_order_then_idle(fm):
    fm.script({"text": "one", "tools": [("bash", {"command": "ls"})], "usage": {"prompt": 900, "cached": 400, "out": 7}})
    ev = events(post(fm))
    assert ev[0]["choices"][0]["delta"]["content"] == "one"
    call = ev[1]["choices"][0]["delta"]["tool_calls"][0]["function"]
    assert call["name"] == "bash" and json.loads(call["arguments"]) == {"command": "ls"}
    assert ev[-1]["usage"]["prompt_tokens"] == 900 and ev[-1]["usage"]["prompt_tokens_details"]["cached_tokens"] == 400
    assert events(post(fm))[0]["choices"][0]["delta"]["content"] == "Nothing left to do."
    assert len(fm.requests) == 2


def test_a_callable_step_reads_the_request(fm):
    fm.script(lambda body: {"text": body["messages"][-1]["content"].upper()})
    assert events(post(fm, {"messages": [{"role": "user", "content": "hi"}]}))[0]["choices"][0]["delta"]["content"] == "HI"


def test_failures(fm):
    fm.script({"fail": "500"}, {"fail": "error:context length exceeded"})
    for code in (500, 400):
        with pytest.raises(urllib.error.HTTPError) as e:
            post(fm)
        assert e.value.code == code
