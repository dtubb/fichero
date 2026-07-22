"""Regression tests for #1359 typed delete wrappers in AppDatabase."""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero.db.app import AppDatabase
from fichero.models import MCPServer, Model, Provider
from fichero.llm.providers import ProviderType


@pytest.fixture
def app_db(tmp_path: Path) -> AppDatabase:
    return AppDatabase(tmp_path / "app-delete-test.duckdb")


def test_delete_provider_uses_typed_delete_and_cascades_models(app_db: AppDatabase):
    provider = app_db.save_provider(
        Provider(name="OpenAI", provider_type=ProviderType.openai)
    )
    other_provider = app_db.save_provider(
        Provider(name="Anthropic", provider_type=ProviderType.anthropic)
    )
    model_a = app_db.save_model(
        Model(provider_id=provider.id, name="A", model_id="model-a")
    )
    model_b = app_db.save_model(
        Model(provider_id=provider.id, name="B", model_id="model-b")
    )
    other_model = app_db.save_model(
        Model(provider_id=other_provider.id, name="C", model_id="model-c")
    )

    app_db.delete_provider(provider.id)

    assert app_db.get_provider(provider.id) is None
    assert app_db.get_model(model_a.id) is None
    assert app_db.get_model(model_b.id) is None
    assert app_db.get_model(other_model.id) is not None


def test_delete_setting_uses_typed_delete_path(app_db: AppDatabase, monkeypatch):
    app_db.set_setting("my-key", "value")
    calls: list[tuple[str, str]] = []
    original = app_db._delete_typed

    def _spy(obj, **kwargs):
        calls.append((type(obj).__name__, kwargs.get("key_field", "id")))
        return original(obj, **kwargs)

    monkeypatch.setattr(app_db, "_delete_typed", _spy)

    app_db.delete_setting("my-key")

    assert app_db.get_setting("my-key") is None
    assert calls == [("AppSetting", "key")]


def test_delete_model_uses_typed_delete_path(app_db: AppDatabase, monkeypatch):
    provider = app_db.save_provider(
        Provider(name="OpenAI", provider_type=ProviderType.openai)
    )
    model = app_db.save_model(Model(provider_id=provider.id, name="4o", model_id="gpt-4o"))
    calls: list[str] = []
    original = app_db._delete_typed

    def _spy(obj, **kwargs):
        calls.append(type(obj).__name__)
        return original(obj, **kwargs)

    monkeypatch.setattr(app_db, "_delete_typed", _spy)

    app_db.delete_model(model.id)

    assert app_db.get_model(model.id) is None
    assert calls == ["Model"]


def test_delete_mcp_server_uses_typed_delete_path(app_db: AppDatabase, monkeypatch):
    server = app_db.save_mcp_server(
        MCPServer(
            name="Time",
            transport="stdio",
            command="python",
            args=["-m", "mcp_server_time"],
        )
    )
    calls: list[str] = []
    original = app_db._delete_typed

    def _spy(obj, **kwargs):
        calls.append(type(obj).__name__)
        return original(obj, **kwargs)

    monkeypatch.setattr(app_db, "_delete_typed", _spy)

    app_db.delete_mcp_server(server.id)

    assert app_db.get_mcp_server(server.id) is None
    assert calls == ["MCPServer"]
