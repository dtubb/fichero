from __future__ import annotations

from pathlib import Path

import httpx

from fichero.cli import client as cli_client
from fichero.importers import http_client


def test_resolve_http_token_uses_session_resolution_for_default_token(monkeypatch):
    monkeypatch.setattr(cli_client, "_read_token", lambda: "session-token")
    assert http_client.resolve_http_token() == "session-token"


def test_resolve_http_token_reads_explicit_token_file(monkeypatch, tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token", encoding="utf-8")
    monkeypatch.setattr(cli_client, "_read_token", lambda: "session-token")
    assert http_client.resolve_http_token(Path(token_file)) == "file-token"


def test_http_manifest_client_reuses_fichero_client_transport():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client = http_client.HttpManifestClient(
        "http://engine.test/api",
        "token-123",
        "/tmp/library.fichero",
    )
    client._client = cli_client.FicheroClient(
        base_url="http://engine.test",
        token="token-123",
        library_path="/tmp/library.fichero",
        transport=httpx.MockTransport(handler),
    )

    body = {"path": "/tmp/library.fichero"}
    assert client.request("POST", "/library", body) == {"ok": True}
    assert calls[0].url == "http://engine.test/api/library"
    assert calls[0].headers["authorization"] == "Bearer token-123"
    assert calls[0].headers["x-fichero-library-path"] == "/tmp/library.fichero"
    assert calls[0].read().decode("utf-8") == '{"path":"/tmp/library.fichero"}'
