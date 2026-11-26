"""Pins what the local-models routes and listings do today (`api/routes/ai/local_models.py`).

Characterisation tests: they state the current behaviour, not a spec ruling. The Kraken runtime, the YOLO
weights and the installed-model catalogue are stood in by monkeypatch, so no library is opened, no network
is used, and every file is under tmp_path.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.ai import local_models
from fichero_server.llm import kraken_runtime, yolo_runtime
from fichero_server.models import LocalModelListResponse


def test_install_kraken_reports_the_bundle_it_finds_and_does_no_install(monkeypatch):
    monkeypatch.setattr(kraken_runtime, "runtime_status", lambda: {
        "installed": True, "loads": True, "kraken_version": "5.0.1", "reason": None})

    status = asyncio.run(local_models.install_kraken())
    assert status.installed is True
    assert status.available is True
    assert status.kraken_version == "5.0.1"
    assert status.reason is None

    # Bundled but its native libraries will not load: installed, not available, and the reason says so.
    monkeypatch.setattr(kraken_runtime, "runtime_status", lambda: {
        "installed": True, "loads": False, "kraken_version": "5.0.1", "reason": "libs would not load"})
    status = asyncio.run(local_models.install_kraken())
    assert status.installed is True
    assert status.available is False
    assert status.reason == "libs would not load"


def test_remove_kraken_refuses_with_a_409_because_it_is_bundled():
    # Error case: there is no separate runtime to delete, so the route refuses every time.
    with pytest.raises(HTTPException) as refused:
        asyncio.run(local_models.remove_kraken())
    assert refused.value.status_code == 409
    assert refused.value.detail == "Kraken is bundled with the app and cannot be removed."


def test_yolo_models_lists_the_layout_model_as_idle_when_not_downloaded_and_installed_when_it_is(monkeypatch, tmp_path):
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    (row,) = local_models.yolo_models()
    assert row.model_id == "yolo-doclaynet-11n"
    assert row.is_downloaded is False
    assert row.path is None
    assert row.size_bytes == 0
    assert row.download_state == "idle"
    assert row.expected_size_mb == 6  # 5_558_611 bytes, rounded to megabytes

    weights = tmp_path / "yolov11n-doclaynet.pt"
    weights.write_bytes(b"x" * 1234)
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: weights)
    (row,) = local_models.yolo_models()
    assert row.is_downloaded is True
    assert row.path == str(weights)
    assert row.size_bytes == 1234
    assert row.download_state == "installed"


def test_installed_readers_keeps_only_installed_entries_that_can_read_and_refuses_an_unknown_runtime(monkeypatch):
    seen = []

    def entries(provider: str):
        seen.append(provider)
        return [
            SimpleNamespace(model_id="mlx-a", display_name="A", disk_usage_bytes=10, download_size_bytes=2_000_000,
                            capabilities=["vision"], tested_status="ok", license_label="MIT", note=None,
                            supported=True, unsupported_reason=None),
            # A model that cannot read (no vision capability) is not a reader, so it is left out.
            SimpleNamespace(model_id="mlx-embed", display_name="E", disk_usage_bytes=None, download_size_bytes=None,
                            capabilities=["embeddings"], tested_status="ok", license_label="MIT", note=None,
                            supported=True, unsupported_reason=None),
        ]

    monkeypatch.setattr("fichero_server.api.routes.ai.local_inference.installed_local_model_entries", entries)

    readers = local_models.installed_readers("mlx")
    assert seen == ["omlx"]  # the MLX runtime's provider name
    assert [r.model_id for r in readers] == ["mlx-a"]
    (reader,) = readers
    assert reader.model_type == "mlx"
    assert reader.is_downloaded is True
    assert reader.download_state == "installed"
    assert reader.size_bytes == 10
    assert reader.expected_size_mb == 2
    assert reader.metadata == {"capabilities": ["vision"], "tested_status": "ok", "license": "MIT"}

    # An unknown runtime is not a reader type at all.
    with pytest.raises(KeyError):
        local_models.installed_readers("whisper")


def test_list_local_models_with_type_yolo_lists_only_the_yolo_rows(monkeypatch):
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    listed = local_models.list_local_models(model_type="yolo")
    assert isinstance(listed, LocalModelListResponse)
    assert [m.model_type for m in listed.models] == ["yolo"]
    assert [m.model_id for m in listed.models] == ["yolo-doclaynet-11n"]
