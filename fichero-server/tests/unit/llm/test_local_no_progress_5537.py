"""A call to a model served on this Mac is judged by progress, not wall time (#5537).

Spec: `compute.memory.local-call-judged-by-progress` in
docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md. Evidence: on a 16 GB MBP (2026-10-07) the
Paleographer Review's long prompt failed 9 pages "ReadTimeout" under normal memory pressure; on the 8 GB
Air slow pages failed "vision exceeded 75.0s — provider hang". A slow answer is not a hung one.

The model server is a stub on 127.0.0.1 speaking the OpenAI streaming shape (no real model). The
no-progress window is shrunk to a second; the old wall-clock cap is shrunk below the answer's length, so
an answer that outlives it proves the cap no longer applies to a local call.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import BaseModel

from fichero_server import llm
from fichero_server.api.routes.ai import local_inference as routes
from fichero_server.llm import LLMConfig, local_inference
from fichero_server.workflows import page_retry
from fichero_server.workflows.tools.vision_base import (
    VISION_ERROR_TIMEOUT,
    classify_vision_failure,
)

WINDOW = 1.0


class _StubServer:
    """An OpenAI-compatible chat server. `script` is a list of (delay_before_piece, piece) per request;
    a request whose script ends in `None` goes quiet (holds the connection, sends nothing more)."""

    def __init__(self):
        self.scripts: list[list] = []
        self.requests: list[dict] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append(body)
                script = stub.scripts.pop(0) if stub.scripts else [(0.0, "ok")]
                if not body.get("stream"):
                    text = "".join(p for _, p in script if p)
                    payload = json.dumps({
                        "id": "x", "object": "chat.completion", "created": 0, "model": "stub",
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": text}}],
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                self._event({"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
                for delay, piece in script:
                    time.sleep(delay)
                    if piece is None:
                        time.sleep(WINDOW * 4)  # quiet well past the window, then hang up
                        return
                    self._event({"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
                self._event({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                self._event({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": len(script),
                                                      "total_tokens": 7 + len(script)}})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def _event(self, data):
                data = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "stub", **data}
                self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def stub(monkeypatch):
    server = _StubServer()

    async def ready(config, capability="text"):
        return None

    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    monkeypatch.setattr(local_inference, "LOCAL_NO_PROGRESS_SECONDS", WINDOW)
    # The old wall-clock cap, shrunk below every answer here: a local call must not be bound by it.
    monkeypatch.setattr(llm, "_compute_timeout", lambda *a, **k: 0.5)
    # Nothing here is an engine-started server that died: a quiet stream is the stub's own.
    monkeypatch.setattr(routes, "engine_started_servers", lambda: [])
    monkeypatch.setattr(llm, "_SERVER_EXIT_GRACE_SECONDS", 0.0)
    with llm._LLM_RESULT_CACHE_LOCK:
        llm._LLM_RESULT_CACHE.clear()
    yield server
    server.close()


def _config(stub, provider="omlx"):
    return LLMConfig(provider=provider, model="stub-vlm", api_base=f"http://127.0.0.1:{stub.port}/v1",
                     timeout=15, max_tokens=1024)


def _steady(pieces=12, gap=0.25):
    """An answer that keeps coming: a piece every `gap` s, 3 s in all — past the shrunk cap and three
    times the no-progress window, never quiet for a whole window."""
    return [(gap, f"w{i} ") for i in range(pieces)]


@pytest.mark.asyncio
async def test_a_slow_but_steady_answer_runs_past_the_old_cap(stub):
    for local_provider in ("omlx", "lmstudio", "ollama"):
        stub.scripts.append(_steady())
        started = time.monotonic()
        text = await llm.vision(images=["data:image/png;base64,AAAA"], prompt=f"review this page ({local_provider})",
                                config=_config(stub, local_provider))
        took = time.monotonic() - started
        assert text == "".join(f"w{i} " for i in range(12)), local_provider
        assert took > 2.5 > WINDOW, local_provider  # past the window and the old cap: progress kept it going
        assert stub.requests[-1]["stream"] is True


@pytest.mark.asyncio
async def test_chat_and_structured_local_calls_stream_too(stub):
    """One code path: text and structured calls to the local server stream and run on while it answers."""
    stub.scripts.append(_steady())
    assert await llm.chat("hello", _config(stub)) == "".join(f"w{i} " for i in range(12))

    class Verdict(BaseModel):
        reading: str

    answer = json.dumps({"reading": "vecino de la ciudad"})
    stub.scripts.append([(0.25, answer[i:i + 4]) for i in range(0, len(answer), 4)])
    result = await llm.chat_structured("read", Verdict, _config(stub))
    parsed = result[0] if isinstance(result, tuple) else result
    assert parsed.reading == "vecino de la ciudad"
    assert all(r["stream"] is True for r in stub.requests)


@pytest.mark.asyncio
async def test_a_stream_that_goes_quiet_fails_after_the_window_with_its_reason(stub):
    stub.scripts.append([(0.1, "Item "), (0.1, "primero "), (0.0, None)])
    started = time.monotonic()
    with pytest.raises(local_inference.LocalModelStoppedAnsweringError) as caught:
        await llm.vision(images=["data:image/png;base64,AAAA"], prompt="review this page", config=_config(stub))
    took = time.monotonic() - started
    assert WINDOW <= took < WINDOW * 3
    cause = str(caught.value)
    assert cause == "the model stopped answering for 1 s (no new text arrived)"
    assert "ReadTimeout" not in cause and "provider hang" not in cause
    # A passing cause: the page is read once more (`page_retry`), and a timeout-shaped vision failure.
    assert page_retry.is_passing_cause(cause)
    assert classify_vision_failure(caught.value) == VISION_ERROR_TIMEOUT
    assert len(stub.requests) == 1  # no silent client-side retries: the page's retry is the one retry


@pytest.mark.asyncio
async def test_a_server_that_never_starts_answering_fails_the_same_way(stub):
    """Reading the prompt before the first token is inside the window too."""
    stub.scripts.append([(0.0, None)])
    with pytest.raises(local_inference.LocalModelStoppedAnsweringError):
        await llm.chat("hello", _config(stub, "lmstudio"))


@pytest.mark.asyncio
async def test_one_quiet_answer_then_a_good_one_reads_on_the_second_try(stub):
    """What the page's one retry sees: the first request goes quiet, the second answers."""
    stub.scripts.extend([[(0.0, None)], _steady(pieces=4, gap=0.1)])
    with pytest.raises(local_inference.LocalModelStoppedAnsweringError):
        await llm.vision(images=["data:image/png;base64,AAAA"], prompt="p", config=_config(stub))
    assert await llm.vision(images=["data:image/png;base64,AAAA"], prompt="p", config=_config(stub)) == "w0 w1 w2 w3 "


def test_a_cloud_call_keeps_its_wall_clock_cap():
    config = LLMConfig(provider="openrouter", model="x", timeout=15, max_tokens=1024)
    assert llm._call_budget(config) == llm._compute_timeout(config, "langchain") == 75.0
    assert llm._call_budget(LLMConfig(provider="omlx", model="x", timeout=15, max_tokens=1024)) is None
