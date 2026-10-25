"""Tests read the vendored price list, never the upstream refresh (#6108): the conftest stops the background refresh."""
from __future__ import annotations

from fichero_server.llm import model_types


def test_a_price_lookup_starts_no_upstream_refresh(monkeypatch):
    started = []
    monkeypatch.setattr(model_types, "_PRICE_TABLE", None)
    monkeypatch.setattr(model_types, "_refresh_registry_cache", lambda cache: started.append(cache) or True)
    model_types._price_table()
    model_types._schedule_registry_refresh(model_types._cached_registry_path())
    assert not started and model_types._REFRESH_STARTED
