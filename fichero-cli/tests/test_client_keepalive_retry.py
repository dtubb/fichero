"""A dropped keep-alive connection retries GETs once, never non-GETs.

Found live 2026-09-03 exercising workflow presets: uvicorn expires idle
keep-alive connections (~5s, sooner when the engine loop is blocked by local
inference), and httpx surfaces the reuse of such a connection as
``RemoteProtocolError("Server disconnected without sending a response.")``.
Every ``workflow run --wait`` poll then died with a cli_error even though the
run completed. The request never reached a handler, so a GET is safe to retry
exactly once; a POST is not (the write may or may not have been processed).
"""

import httpx
import pytest

from fichero_cli import FicheroClient
from fichero_cli.client import FicheroError


def _flaky_transport(calls: list[str], *, fail_first_n: int) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if len(calls) <= fail_first_n:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response."
            )
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


def _client(transport: httpx.MockTransport) -> FicheroClient:
    return FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=transport,
    )


def test_get_retries_once_on_server_disconnect():
    calls: list[str] = []
    client = _client(_flaky_transport(calls, fail_first_n=1))
    assert client.request("GET", "/api/activity") == {"ok": True}
    assert calls == ["GET", "GET"]


def test_get_does_not_retry_twice():
    calls: list[str] = []
    client = _client(_flaky_transport(calls, fail_first_n=2))
    with pytest.raises(FicheroError, match="after retrying"):
        client.request("GET", "/api/activity")
    assert calls == ["GET", "GET"]


def test_post_is_never_retried_on_disconnect():
    calls: list[str] = []
    client = _client(_flaky_transport(calls, fail_first_n=1))
    with pytest.raises(FicheroError, match="Server disconnected"):
        client.request("POST", "/api/workflow-execution/execute", json={})
    assert calls == ["POST"]
