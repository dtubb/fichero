"""How the MCP server resolves its connection, and how it fails (#4227).

Every tool is one `FicheroClient` HTTP call, so "connection resolution" here
means: which base URL the client gets, which credential it attaches, and what
happens when the credential or the server is missing. Nothing dials a real
server — an `httpx.MockTransport` stands in at the transport seam.

Transport reality, verified in the code rather than assumed: this product has
one transport, HTTP(S) to a base URL (`--api-url` / `$FICHERO_API_URL`, default
`http://127.0.0.1:8765`). Unix-domain sockets are the embedded Mac app's
transport, not this one; there is no UDS branch in `FicheroClient` to test.
"""

from __future__ import annotations

import httpx
import pytest

from fichero_cli import FicheroClient, FicheroError
from fichero_cli import client as client_module
from fichero_mcp import server as mcp_server


@pytest.fixture
def recorded(monkeypatch):
    """Give every `_client()` a recording transport; return the request log."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    real_client = FicheroClient

    def factory(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(mcp_server, "FicheroClient", factory)
    return requests


# -- base URL resolution ---------------------------------------------------


def test_default_target_is_loopback_8765(recorded):
    mcp_server.fichero_health()

    # https (#4468): the engine mandates TLS on TCP; the MCP server inherits
    # the CLI client's fail-closed loopback/HTTPS default.
    assert str(recorded[0].url) == "https://127.0.0.1:8765/api/health"


def test_config_base_url_is_used(recorded, monkeypatch):
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", "https://remote.example:8765")

    mcp_server.fichero_health()

    assert recorded[0].url.host == "remote.example"
    assert recorded[0].url.scheme == "https"


def test_env_api_url_is_used_when_config_is_unset(recorded, monkeypatch):
    monkeypatch.setenv("FICHERO_API_URL", "https://from-env.example:9443")

    mcp_server.fichero_health()

    assert recorded[0].url.host == "from-env.example"


def test_main_populates_config_from_args(monkeypatch, tmp_path):
    """`--api-url` / `--library-path` must beat the environment for the process."""
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)
    library = tmp_path / "Library.fichero"
    monkeypatch.setattr(
        "sys.argv",
        [
            "fichero-mcp",
            "--api-url",
            "https://cli-arg.example:8765",
            "--library-path",
            str(library),
        ],
    )

    mcp_server.main()

    assert mcp_server._CONFIG["base_url"] == "https://cli-arg.example:8765"
    assert mcp_server._CONFIG["library_path"] == str(library)


# -- credentials -----------------------------------------------------------


def test_library_path_config_becomes_a_header(recorded, monkeypatch, tmp_path):
    library = tmp_path / "Marshall Diaries.fichero"
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", str(library))

    mcp_server.fichero_health()

    assert "Marshall%20Diaries.fichero" in recorded[0].headers["X-Fichero-Library-Path"]


def test_loopback_bootstrap_token_is_attached(recorded, isolated_mcp_env):
    isolated_mcp_env.write_text("bootstrap-token\n", encoding="utf-8")

    mcp_server.fichero_health()

    assert recorded[0].headers["Authorization"] == "Bearer bootstrap-token"


def test_remote_target_never_receives_the_loopback_bootstrap_token(
    recorded, isolated_mcp_env, monkeypatch
):
    isolated_mcp_env.write_text("loopback-only-secret\n", encoding="utf-8")
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", "https://remote.example:8765")

    mcp_server.fichero_health()

    assert "Authorization" not in recorded[0].headers


def test_missing_credential_sends_no_authorization_header(recorded):
    mcp_server.fichero_health()

    assert "Authorization" not in recorded[0].headers


# -- fail-closed on missing auth ------------------------------------------


def test_agent_client_refuses_to_build_without_a_stored_session(monkeypatch):
    """The audited-write path is fail-closed: no agent session, no client.

    Falling back to the loopback bootstrap credential here would attribute an
    agent's write to the owner account, which is the one thing the
    "model is a user" design forbids.
    """
    monkeypatch.setattr(client_module, "_read_token", lambda **_kwargs: None)

    with pytest.raises(RuntimeError) as excinfo:
        mcp_server._agent_client()

    assert "fichero auth login agent" in str(excinfo.value)


def test_agent_client_does_not_fall_back_to_the_owner_bootstrap_token(
    isolated_mcp_env,
):
    """A bootstrap key file on disk must not satisfy the agent account."""
    isolated_mcp_env.write_text("owner-bootstrap-token\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        mcp_server._agent_client()


def test_workspace_action_requires_the_agent_session(monkeypatch):
    monkeypatch.setattr(client_module, "_read_token", lambda **_kwargs: None)

    with pytest.raises(RuntimeError):
        mcp_server._workspace_action("reveal_location", {"document_id": "doc-1"})


def test_unauthenticated_tool_call_raises_rather_than_returning_empty(monkeypatch):
    """A 401 must surface as an error tool result, never as "no results"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Not authenticated"})

    transport = httpx.MockTransport(handler)
    real_client = FicheroClient
    monkeypatch.setattr(
        mcp_server, "FicheroClient", lambda **kw: real_client(transport=transport, **kw)
    )

    with pytest.raises(FicheroError) as excinfo:
        mcp_server.fichero_docs_list()

    assert excinfo.value.status_code == 401


def test_unreachable_server_raises_a_typed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    transport = httpx.MockTransport(handler)
    real_client = FicheroClient
    monkeypatch.setattr(
        mcp_server, "FicheroClient", lambda **kw: real_client(transport=transport, **kw)
    )

    with pytest.raises(FicheroError) as excinfo:
        mcp_server.fichero_health()

    assert excinfo.value.status_code is None
    assert "Cannot connect to the Fichero backend" in str(excinfo.value)
