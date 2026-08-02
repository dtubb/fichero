"""Which server the CLI dials, and which credential it sends (#4227).

Everything here goes through a real `FicheroClient` over an
`httpx.MockTransport`, so the assertions are about the request the CLI would
actually put on the wire — base URL, `Authorization`, and the
`X-Fichero-Library-Path` header — with no live server involved.

Transport note verified against the code, not assumed: this client has exactly
one transport, an HTTP(S) base URL. There is no Unix-domain-socket client path
here — `engine_manager.start` can *launch* the server on a UDS
(`FICHERO_UDS_PATH`, see `test_cli_engine_transport.py`), and the Swift app
dials one, but `FicheroClient` always speaks HTTP(S) to `base_url`.
"""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from fichero_cli import FicheroClient
from fichero_cli import __main__ as cli_main
from fichero_cli import client as client_module

runner = CliRunner()


def _capturing_transport(requests: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    return httpx.MockTransport(handler)


@pytest.fixture
def captured_requests(monkeypatch):
    """Route every CLI-built client through a recording mock transport."""
    requests: list[httpx.Request] = []
    transport = _capturing_transport(requests)
    real_client = FicheroClient

    def factory(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(cli_main, "FicheroClient", factory)
    return requests


# -- base URL selection ----------------------------------------------------


def test_default_base_url_is_https_loopback_8765():
    """#4468: the engine mandates TLS on TCP, so an http:// default could
    never work against the engine we ship — a default that cannot work is a
    trap. Fail-closed loopback/HTTPS is the standing transport rule."""
    with FicheroClient(token="", transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client:
        assert client.base_url == "https://127.0.0.1:8765"
        assert client.base_url == client_module.DEFAULT_BASE_URL


def test_env_api_url_overrides_the_default(monkeypatch):
    monkeypatch.setenv("FICHERO_API_URL", "https://engine.example:9443")

    with FicheroClient(token="") as client:
        assert client.base_url == "https://engine.example:9443"


def test_explicit_base_url_beats_the_env(monkeypatch):
    monkeypatch.setenv("FICHERO_API_URL", "https://from-env.example:9443")

    with FicheroClient(base_url="https://explicit.example:8765", token="") as client:
        assert client.base_url == "https://explicit.example:8765"


def test_trailing_slash_is_stripped_so_paths_do_not_double_up(captured_requests):
    result = runner.invoke(
        cli_main.app, ["--base-url", "https://remote.example:8765/", "health"]
    )

    assert result.exit_code == 0, result.output
    assert str(captured_requests[0].url) == "https://remote.example:8765/api/health"


def test_cli_dials_the_selected_base_url(captured_requests):
    result = runner.invoke(
        cli_main.app, ["--base-url", "https://remote.example:8765", "health"]
    )

    assert result.exit_code == 0, result.output
    assert captured_requests[0].url.host == "remote.example"
    assert captured_requests[0].url.scheme == "https"


# -- auth token sourcing ---------------------------------------------------


def test_token_flag_is_sent_as_bearer(captured_requests):
    result = runner.invoke(cli_main.app, ["--token", "flag-token", "health"])

    assert result.exit_code == 0, result.output
    assert captured_requests[0].headers["Authorization"] == "Bearer flag-token"


def test_session_token_env_is_used_when_no_flag(monkeypatch, captured_requests):
    monkeypatch.setenv("FICHERO_SESSION_TOKEN", "session-env-token")

    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 0, result.output
    assert captured_requests[0].headers["Authorization"] == "Bearer session-env-token"


def test_bootstrap_key_file_is_used_on_loopback(isolated_cli_env, captured_requests):
    isolated_cli_env.write_text("key-file-token\n", encoding="utf-8")

    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 0, result.output
    assert captured_requests[0].headers["Authorization"] == "Bearer key-file-token"


def test_remote_base_url_never_sends_the_loopback_bootstrap_key(
    isolated_cli_env, captured_requests
):
    """A loopback-only bootstrap secret must not leak to a remote host."""
    isolated_cli_env.write_text("loopback-only-secret\n", encoding="utf-8")

    result = runner.invoke(
        cli_main.app, ["--base-url", "https://remote.example:8765", "health"]
    )

    assert result.exit_code == 0, result.output
    assert "Authorization" not in captured_requests[0].headers


def test_no_credential_anywhere_sends_no_authorization_header(captured_requests):
    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 0, result.output
    assert "Authorization" not in captured_requests[0].headers


# -- library scoping -------------------------------------------------------


def test_library_flag_becomes_the_library_path_header(captured_requests, tmp_path):
    library = tmp_path / "Marshall Diaries.fichero"
    result = runner.invoke(cli_main.app, ["--library", str(library), "health"])

    assert result.exit_code == 0, result.output
    header = captured_requests[0].headers["X-Fichero-Library-Path"]
    assert "Marshall%20Diaries.fichero" in header


def test_library_env_var_is_honoured(monkeypatch, captured_requests, tmp_path):
    library = tmp_path / "FromEnv.fichero"
    monkeypatch.setenv("FICHERO_LIBRARY_PATH", str(library))

    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 0, result.output
    assert captured_requests[0].headers["X-Fichero-Library-Path"].endswith(
        "FromEnv.fichero"
    )


class TestLoopbackTrustFailsClosed:
    """#4468: loopback https anchors the engine's OWN cert; a missing cert
    is a refusal that NAMES the path searched — never a silent fallback to
    unverified, never verify=False."""

    def test_missing_material_fails_closed_naming_the_path(self, monkeypatch, tmp_path):
        from fichero_cli import client as client_module
        from fichero_cli.client import FicheroError

        import fichero_server.security.remote_access_tls as tls

        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
        monkeypatch.setattr(tls, "DEFAULT_STORAGE_ROOT", tmp_path / "Remote Access")
        with pytest.raises(FicheroError) as caught:
            client_module._loopback_trust("https://127.0.0.1:8765")
        message = str(caught.value)
        assert "Remote Access" in message and "server.crt" in message, (
            "the refusal must name the path it looked for"
        )
        assert "unverified" in message

    def test_existing_material_becomes_a_trust_anchor(self, monkeypatch, tmp_path):
        """A real self-signed cert on disk loads as an anchor (no
        verify=False anywhere)."""
        import ssl

        from fichero_cli import client as client_module

        import fichero_server.security.remote_access_tls as tls

        root = tmp_path / "Remote Access"
        material = tls.prepare_remote_access_tls(
            "https://127.0.0.1:8765", storage_root=root, allow_loopback=True
        )
        monkeypatch.setattr(tls, "DEFAULT_STORAGE_ROOT", root)
        context = client_module._loopback_trust("https://127.0.0.1:8765")
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        stats = context.cert_store_stats()
        assert stats["x509_ca"] >= 1 or stats["x509"] >= 1, (
            f"the engine cert at {material.certificate_path} did not load "
            "as a trust anchor"
        )

    def test_explicit_ssl_cert_file_env_bypasses_discovery(self, monkeypatch):
        """FICHERO_API_URL/SSL_CERT_FILE overrides still win (additive)."""
        import httpx

        from fichero_cli.client import FicheroClient

        monkeypatch.setenv("SSL_CERT_FILE", "/tmp/nonexistent.pem")
        # Construction must not call _loopback_trust (which would raise on a
        # machine with no material); it defers to httpx's env handling. Use a
        # mock transport so no real dial happens either.
        client = FicheroClient(
            token="", transport=httpx.MockTransport(lambda r: httpx.Response(200))
        )
        client.close()
