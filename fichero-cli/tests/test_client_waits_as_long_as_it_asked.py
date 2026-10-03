"""A comparison waits as long as it asked the engine to work (#5388).

WHY: `compare workflow` asks the engine for up to 300 s, but the CLI's HTTP client gave up after its
60 s default ("The read operation timed out") while the engine kept running the comparison, so a
local model run always looked like a failure. A request can now carry its own timeout, and the
comparison passes the time it asked for plus a margin.
"""
import httpx

from fichero_cli import FicheroClient


def test_compare_workflow_reads_for_as_long_as_the_engine_was_asked_to_work():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["read_timeout"] = request.extensions["timeout"]["read"]
        return httpx.Response(200, json={"id": "c", "status": "completed", "results": []})

    client = FicheroClient(base_url="http://127.0.0.1:8765", token="t", library_path="/tmp/lib.fichero",
                           transport=httpx.MockTransport(handler))
    try:
        client.compare_workflow(workflow_id="w", doc_id="d", models=[], timeout_seconds=300)
    except Exception:  # noqa: BLE001 -- the stub's body may not validate; the timeout is what is tested
        pass
    assert seen["read_timeout"] == 330


def test_a_plain_request_keeps_the_default_timeout():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["read_timeout"] = request.extensions["timeout"]["read"]
        return httpx.Response(200, json={})

    client = FicheroClient(base_url="http://127.0.0.1:8765", token="t", library_path="/tmp/lib.fichero",
                           transport=httpx.MockTransport(handler))
    client.request("GET", "/api/health")
    assert seen["read_timeout"] == 60.0
