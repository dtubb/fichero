"""Where models run, slice 1 (docs/contributor_manual/specs/ai/where-models-run.md):

- `ai.where.place-is-by-address` (#5586): a model's place is worked out from its address, not its
  provider type. An Ollama row at an address off this Mac is refused by the local-only gate, runs
  on the network lane, is not priced as free, and is shown as the person's own machine.
- `ai.where.row-address-reaches-runs` (#5587): a provider row's Server URL is the address a
  workflow run's calls use.
- `ai.where.no-first-provider-fallback` (#5368): a step with no model refuses, naming what to set.

No network: the "remote" Ollama is a stub server on 127.0.0.1 reached through a name that is not
loopback (`ollama-box.example`, resolved to the stub by a patched resolver), so the engine sees an
address off this Mac while the bytes never leave it.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

import fichero_server.workflows.tools  # noqa: F401  (registers the tools a run uses)
from fichero_server import llm
from fichero_server.execution import jobs
from fichero_server.llm import LLMConfig, LocalOnlyViolationError
from fichero_server.llm.places import OWN_MACHINE, PROVIDER, THIS_MAC, place_of, server_address
from fichero_server.llm.usage import price_call
from fichero_server.llm.providers import ProviderType
from fichero_server.models import Model, Provider
from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import build_initial_state
from fichero_server.workflows.types import NodeDef, WorkflowDef

REMOTE_NAME = "ollama-box.example"
STUB_REPLY = "A stub summary from the Ollama box."


# ---------------------------------------------------------------------------
# A stub OpenAI-compatible model server
# ---------------------------------------------------------------------------


class _StubHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args):  # quiet
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append({"path": self.path, "host": self.headers.get("Host"),
                                    "model": body.get("model")})
        payload = {
            "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
            "model": body.get("model") or "stub",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": STUB_REPLY}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def stub_server(monkeypatch):
    """A stub model server on 127.0.0.1, also reachable as `ollama-box.example`."""
    _StubHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host in (REMOTE_NAME, REMOTE_NAME.encode()):  # httpcore passes bytes
            host = "127.0.0.1"
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    try:
        yield SimpleNamespace(port=server.server_address[1], requests=_StubHandler.requests)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def _not_local_only(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")


def _ollama_row(app_db, url: str) -> None:
    app_db.save_provider(Provider(name="Ollama box", provider_type=ProviderType.ollama, api_base=url))


# ---------------------------------------------------------------------------
# ai.where.place-is-by-address
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "api_base", "place"),
    [
        ("ollama", "http://10.0.0.5:11434", OWN_MACHINE),
        ("ollama", f"http://{REMOTE_NAME}:11434", OWN_MACHINE),
        ("ollama", "http://studio.local:11434", OWN_MACHINE),
        ("lmstudio", "https://gpu.example.org/v1", OWN_MACHINE),
        ("ollama", "http://localhost:11434", THIS_MAC),
        ("ollama", "http://127.0.0.1:11434", THIS_MAC),
        ("ollama", "http://[::1]:11434", THIS_MAC),
        ("ollama", "/tmp/ollama.sock", THIS_MAC),
        ("ollama", None, THIS_MAC),  # no row URL: the default localhost server
        ("omlx", None, THIS_MAC),
        ("apple", None, THIS_MAC),
        ("mock", None, THIS_MAC),
        # A cloud type stays the provider's even through a loopback proxy, which may forward on.
        ("openai", "http://127.0.0.1:4000/v1", PROVIDER),
        ("openrouter", None, PROVIDER),
    ],
)
def test_place_is_worked_out_from_the_address(app_db, provider, api_base, place):
    assert place_of(LLMConfig(provider=provider, model="m", api_base=api_base)) == place


def test_a_row_server_url_decides_the_place_of_a_config_that_names_none(app_db):
    _ollama_row(app_db, "http://10.0.0.5:11434")
    config = LLMConfig(provider="ollama", model="llama3.2")
    assert place_of(config) == OWN_MACHINE
    assert server_address(config) == "http://10.0.0.5:11434/v1"


def test_local_only_refuses_an_ollama_off_this_mac(app_db, monkeypatch):
    """The egress gate meets a remote Ollama like any cloud model: refused before any request."""
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    _ollama_row(app_db, "http://10.0.0.5:11434")

    with pytest.raises(LocalOnlyViolationError):
        asyncio.run(llm.chat("Hello", LLMConfig(provider="ollama", model="llama3.2")))


def test_local_only_allows_an_ollama_on_this_mac(app_db, monkeypatch, stub_server):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    _ollama_row(app_db, f"http://127.0.0.1:{stub_server.port}")

    answer = asyncio.run(llm.chat("Hello", LLMConfig(provider="ollama", model="llama3.2")))

    assert answer == STUB_REPLY
    assert stub_server.requests and stub_server.requests[0]["path"] == "/v1/chat/completions"


def test_an_own_machine_call_is_not_priced_free():
    remote = price_call({"provider": "ollama", "model": "llama3.2", "input_tokens": 10,
                         "output_tokens": 5, "place": OWN_MACHINE})
    here = price_call({"provider": "ollama", "model": "llama3.2", "input_tokens": 10,
                       "output_tokens": 5, "place": THIS_MAC})
    assert remote.free is False and remote.cost_usd is None and remote.priced is False
    assert here.free is True and here.cost_usd == 0.0


@pytest.mark.parametrize(
    ("provider_type", "api_base", "place"),
    [
        ("ollama", "http://10.0.0.5:11434", OWN_MACHINE),
        ("ollama", "http://localhost:11434", THIS_MAC),
        ("lmstudio", None, THIS_MAC),
    ],
)
def test_providers_route_names_the_place(client, provider_type, api_base, place):
    created = client.post("/api/providers", json={"provider_type": provider_type,
                                                  "api_base": api_base})
    assert created.status_code in (200, 201), created.text
    assert created.json()["place"] == place

    listed = {p["id"]: p for p in client.get("/api/providers").json()["items"]}
    assert listed[created.json()["id"]]["place"] == place


# ---------------------------------------------------------------------------
# ai.where.row-address-reaches-runs (+ the run's lane and price, by place)
# ---------------------------------------------------------------------------


def _summarize_workflow(**node_fields) -> WorkflowDef:
    return WorkflowDef(
        name="Where models run",
        provider="",
        model="",
        nodes=[NodeDef(id="sum", tool="summarize",
                       config={"text": "The ledger was signed in Mockton.", "save_to_db": False},
                       **node_fields)],
        edges=[],
    )


def test_a_run_reaches_the_row_server_url_off_this_mac(app_db, stub_server, monkeypatch, tmp_path):
    _ollama_row(app_db, f"http://{REMOTE_NAME}:{stub_server.port}")

    lanes: list[str] = []
    real_lane_slot = jobs.lane_slot

    def spy_lane_slot(*args, **kwargs):
        lanes.append(kwargs.get("lane"))
        return real_lane_slot(*args, **kwargs)

    monkeypatch.setattr(jobs, "lane_slot", spy_lane_slot)

    workflow = _summarize_workflow(provider_name="ollama", model_name="llama3.2")
    state = build_initial_state({}, library_path=str(tmp_path / "lib.fichero"))
    with llm.collect_usage() as usage:
        result = asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    # The call went to the row's Server URL, not the default localhost:11434.
    assert stub_server.requests, result.get("error") or result
    assert stub_server.requests[0]["host"] == f"{REMOTE_NAME}:{stub_server.port}"
    assert stub_server.requests[0]["path"] == "/v1/chat/completions"
    assert result["outputs"]["sum"]["summary"] == STUB_REPLY
    # An Ollama on another machine waits on the network lane, not this Mac's model lane.
    assert lanes and set(lanes) == {"network"}
    # And its tokens are recorded as spent off this Mac: unpriced, never a free $0.
    assert usage and usage[0]["place"] == OWN_MACHINE
    priced = price_call(usage[0])
    assert priced.free is False and priced.cost_usd is None


def test_a_run_on_a_loopback_row_holds_the_local_model_lane(app_db, stub_server, monkeypatch,
                                                            tmp_path):
    _ollama_row(app_db, f"http://127.0.0.1:{stub_server.port}")
    lanes: list[str] = []
    real_lane_slot = jobs.lane_slot

    def spy_lane_slot(*args, **kwargs):
        lanes.append(kwargs.get("lane"))
        return real_lane_slot(*args, **kwargs)

    monkeypatch.setattr(jobs, "lane_slot", spy_lane_slot)

    workflow = _summarize_workflow(provider_name="ollama", model_name="llama3.2")
    state = build_initial_state({}, library_path=str(tmp_path / "lib.fichero"))
    with llm.collect_usage() as usage:
        asyncio.run(build_graph(workflow, skip_cache=True).ainvoke(state))

    assert stub_server.requests
    assert lanes and set(lanes) == {"local-ml"}
    assert usage and usage[0]["place"] == THIS_MAC
    assert price_call(usage[0]).free is True


# ---------------------------------------------------------------------------
# ai.where.no-first-provider-fallback
# ---------------------------------------------------------------------------


def test_a_step_with_no_model_refuses_rather_than_take_the_first_provider(app_db):
    """No model on the step, the workflow or Settings: the run refuses, naming what to set. An
    enabled cloud provider with a model is never picked for it."""
    for key in [k for k in app_db.get_ai_defaults() if k.endswith(("_provider", "_model"))]:
        app_db.delete_setting(key)
    provider = app_db.save_provider(Provider(name="OpenAI", provider_type=ProviderType.openai))
    app_db.save_model(Model(provider_id=provider.id, name="GPT", model_id="gpt-4o-mini"))

    with pytest.raises(ValueError, match="No model is set for this step.*Settings > AI"):
        build_graph(_summarize_workflow(), skip_cache=True)
