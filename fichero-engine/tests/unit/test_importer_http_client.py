from __future__ import annotations

from pathlib import Path

from fichero.importers import http_client


def test_resolve_http_token_uses_session_resolution_for_default_token(monkeypatch):
    monkeypatch.setattr(http_client, "_read_token", lambda: "session-token")
    assert http_client.resolve_http_token() == "session-token"


def test_resolve_http_token_reads_explicit_token_file(monkeypatch, tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token", encoding="utf-8")
    monkeypatch.setattr(http_client, "_read_token", lambda: "session-token")
    assert http_client.resolve_http_token(Path(token_file)) == "file-token"
