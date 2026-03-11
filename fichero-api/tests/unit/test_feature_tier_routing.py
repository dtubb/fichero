"""Tests for API feature-tier route registration."""

from fichero.api.main import get_route_specs_for_tier, resolve_feature_tier


def _route_prefixes_for(tier: str) -> set[str]:
    return {prefix for _, prefix, _ in get_route_specs_for_tier(tier)}


def test_release_tier_exposes_only_core_routes():
    prefixes = _route_prefixes_for("release")

    assert "/api/documents" in prefixes
    assert "/api/search" in prefixes
    assert "/api/ingest" in prefixes
    assert "/api/storage" in prefixes
    assert "/api/folders" in prefixes
    assert "/api/artifacts" in prefixes

    assert "/api/providers" not in prefixes
    assert "/api/models" not in prefixes
    assert "/api/chat" not in prefixes
    assert "/api/workflows" not in prefixes
    assert "/api/workflow-execution" not in prefixes


def test_dev_tier_adds_provider_routes():
    prefixes = _route_prefixes_for("dev")

    assert "/api/providers" in prefixes
    assert "/api/models" in prefixes


def test_invalid_tier_defaults_to_release(monkeypatch):
    monkeypatch.setenv("FICHERO_FEATURE_TIER", "invalid-tier")
    assert resolve_feature_tier() == "release"
