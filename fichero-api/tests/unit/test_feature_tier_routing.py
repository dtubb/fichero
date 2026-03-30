"""Tests for API feature-tier route registration."""

from fichero.api.main import get_route_specs_for_tier, resolve_feature_tier


def _route_prefixes_for(tier: str) -> set[str]:
    return {prefix for _, prefix, _ in get_route_specs_for_tier(tier)}


def test_release_tier_exposes_001_routes():
    prefixes = _route_prefixes_for("release")

    assert "/api/documents" in prefixes
    assert "/api/search" in prefixes
    assert "/api/ingest" in prefixes
    assert "/api/storage" in prefixes
    assert "/api/folders" in prefixes
    assert "/api/artifacts" in prefixes

    assert "/api/providers" in prefixes
    assert "/api/models" in prefixes
    assert "/api/chat" in prefixes
    assert "/api/workflows" in prefixes
    assert "/api/workflow-execution" in prefixes


def test_dev_tier_matches_release_until_dev_routes_added():
    assert _route_prefixes_for("dev") == _route_prefixes_for("release")


def test_invalid_tier_defaults_to_release(monkeypatch):
    monkeypatch.setenv("FICHERO_FEATURE_TIER", "invalid-tier")
    assert resolve_feature_tier() == "release"
