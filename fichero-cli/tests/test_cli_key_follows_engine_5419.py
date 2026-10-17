"""The CLI's credential follows the engine it dials (`transport.cli-key-file-belongs-to-the-engine-it-dials`, #5419).

Two engines on one Mac write two key files (plain path, app container). The newest file is not
always the dialed engine's: a dev engine on 8765 got 401 stale_bootstrap_token because the app's
container key was newer. A 401 from a loopback engine must move the client on to the other key
file, and a key the engine refused is never sent again.
"""
from __future__ import annotations

import os

import httpx

from fichero_cli import FicheroClient
from fichero_cli import client as client_module


def _engine_accepting(good: str, seen: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization", "")
        seen.append(auth)
        if auth == f"Bearer {good}":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(401, json={"detail": "local bootstrap token is stale", "code": "stale_bootstrap_token"})

    return httpx.MockTransport(handler)


def _two_key_files(monkeypatch, tmp_path, *, plain: str, container: str):
    plain_p, container_p = tmp_path / "plain-key", tmp_path / "container-key"
    plain_p.write_text(plain + "\n")
    container_p.write_text(container + "\n")
    os.utime(plain_p, (1, 1))  # the dialed engine's key is the OLDER file
    monkeypatch.setattr(client_module, "_TOKEN_PATH", plain_p)
    monkeypatch.setattr(client_module, "_CONTAINER_TOKEN_PATH", container_p)
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_a_stale_newest_key_falls_back_to_the_other_engines_file(monkeypatch, tmp_path):
    _two_key_files(monkeypatch, tmp_path, plain="dev-engine-key", container="app-engine-key")
    seen: list[str] = []
    with FicheroClient(base_url="https://127.0.0.1:8765", transport=_engine_accepting("dev-engine-key", seen)) as c:
        response = c.request("GET", "/health")
    assert response == {"status": "ok"}
    assert seen == ["Bearer app-engine-key", "Bearer dev-engine-key"]


def test_a_refused_key_is_not_sent_again(monkeypatch, tmp_path):
    _two_key_files(monkeypatch, tmp_path, plain="a", container="b")
    seen: list[str] = []
    with FicheroClient(base_url="https://127.0.0.1:8765", transport=_engine_accepting("neither", seen)) as c:
        try:
            c.request("GET", "/health")
        except Exception:
            pass
    assert sorted(seen) == ["Bearer a", "Bearer b"]
