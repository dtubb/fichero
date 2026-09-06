"""A down oMLX sidecar must not slow the model picker (#4 / Daniel).

The installed models come from the STORE (disk); the live GET /v1/models only
ADDS server-reported ones. When the managed sidecar is down — its normal state
until a run starts it — that live query used to wait out a 5s total timeout
before the endpoint fell back to the store, so "loading models" hung for
seconds. These tests pin that (a) a down server still returns the store list,
and (b) the live probe uses a short CONNECT timeout so it fails fast.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest


def _installed_entry():
    return SimpleNamespace(
        installed=True,
        model_id="mlx-community/Qwen3-VL-8B",
        display_name="Qwen3-VL 8B",
        capabilities=["text", "vision"],
    )


class _DownClient:
    """An httpx.AsyncClient stand-in whose GET fails as if the server is down."""

    captured: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        _DownClient.captured["timeout"] = kwargs.get("timeout")
        raise httpx.ConnectError("connection refused")


class _FakeStore:
    def list_catalog_entries(self):
        return [_installed_entry()]


def test_down_omlx_still_lists_store_models_and_fails_fast(client, monkeypatch):
    _DownClient.captured = {}
    monkeypatch.setattr(
        "fichero_server.llm.mlx_model_store.get_mlx_model_store", lambda: _FakeStore()
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _DownClient())

    r = client.get("/api/providers/models/omlx")
    assert r.status_code == 200
    model_ids = {m["model_id"] for m in r.json()["items"]}
    # The installed store model is returned despite the live query failing.
    assert "mlx-community/Qwen3-VL-8B" in model_ids

    # The live probe used a short connect timeout, not the old 5s total.
    timeout = _DownClient.captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect is not None and timeout.connect <= 1.0
