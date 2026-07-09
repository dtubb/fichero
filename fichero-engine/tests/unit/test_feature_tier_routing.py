"""Tests for API feature-tier route registration."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fichero.api.main as main_module
from fichero.api.main import get_route_specs_for_tier, register_tiered_routes, resolve_feature_tier


def _route_prefixes_for(tier: str) -> set[str]:
    return {prefix for _, prefix, _ in get_route_specs_for_tier(tier)}


def _spec_exists(tier: str, prefix: str, tag: str) -> bool:
    return any(
        spec_prefix == prefix and tag in tags
        for _, spec_prefix, tags in get_route_specs_for_tier(tier)
    )


def _tier_client(monkeypatch, tier: str) -> TestClient:
    test_app = FastAPI()
    monkeypatch.setattr(main_module, "app", test_app)
    register_tiered_routes(tier)
    return TestClient(test_app)


def test_release_tier_exposes_001_routes():
    prefixes = _route_prefixes_for("release")

    assert "/api/documents" in prefixes
    assert "/api/search" in prefixes
    assert "/api/ingest" in prefixes
    assert any(
        prefix == "/api" and "export" in tags
        for _, prefix, tags in get_route_specs_for_tier("release")
    )
    assert "/api/storage" in prefixes
    assert "/api/folders" in prefixes
    assert "/api/artifacts" in prefixes

    assert "/api/providers" in prefixes
    assert "/api/models" in prefixes
    assert any(
        prefix == "/api" and "model-comparison" in tags
        for _, prefix, tags in get_route_specs_for_tier("release")
    )
    assert "/api/workflows" in prefixes
    assert "/api/workflow-execution" in prefixes
    # Chains promoted from dev to core for 0.0.2 (#1151)
    chain_tags = [
        tags for _, _, tags in get_route_specs_for_tier("release") if "chains" in tags
    ]
    assert chain_tags, "chains router must be in release tier (#1151)"


def _kg_router_count(tier: str) -> int:
    """Count routers tagged 'knowledge-graph' for a tier."""
    specs = get_route_specs_for_tier(tier)
    return sum(1 for _, _, tags in specs if "knowledge-graph" in tags)


def test_release_tier_includes_consolidated_kg_surface():
    """Release tier exposes the full consolidated KG surface — the post-
    1587a1b6 \"all KG ships in release\" decision (#832) + the #997
    promotion that moved hermeneutics from dev to release too. Dev no
    longer needs to add KG routers.
    """
    assert _kg_router_count("release") >= 15
    # Dev tier should still have at least as much KG surface as release
    # (no regression: dev == release for KG today, but the test reads
    # as \"dev never has fewer\" so a future dev-only KG router slots in
    # without test breakage).
    assert _kg_router_count("dev") >= _kg_router_count("release")


def test_iiif_server_mode_is_dev_tier_only():
    assert not _spec_exists("release", "/api/iiif", "iiif")
    assert not _spec_exists("beta", "/api/iiif", "iiif")
    assert not _spec_exists("alpha", "/api/iiif", "iiif")
    assert _spec_exists("dev", "/api/iiif", "iiif")


def test_alpha_and_beta_routes_are_cumulative():
    assert not _spec_exists("release", "/api/chat", "chat")
    assert not _spec_exists("beta", "/api/chat", "chat")
    assert _spec_exists("alpha", "/api/chat", "chat")
    assert _spec_exists("dev", "/api/chat", "chat")

    assert not _spec_exists("release", "/api/research", "research")
    assert _spec_exists("beta", "/api/research", "research")
    assert _spec_exists("alpha", "/api/research", "research")
    assert _spec_exists("dev", "/api/research", "research")

    assert not _spec_exists("release", "/api", "activity")
    assert _spec_exists("beta", "/api", "activity")
    assert _spec_exists("alpha", "/api", "activity")
    assert _spec_exists("dev", "/api", "activity")


def test_release_routes_remain_visible_in_all_tiers():
    for tier in ("release", "beta", "alpha", "dev"):
        assert _spec_exists(tier, "/api/workflows", "workflows")
        assert _spec_exists(tier, "/api/search", "search")


def test_invalid_tier_defaults_to_release(monkeypatch):
    monkeypatch.setenv("FICHERO_FEATURE_TIER", "invalid-tier")
    with patch.object(main_module, "logger") as mock_logger:
        assert resolve_feature_tier() == "release"
    assert any(
        "Unknown FICHERO_FEATURE_TIER" in str(call)
        for call in mock_logger.warning.call_args_list
    )


def test_valid_tiers_resolve_from_environment(monkeypatch):
    for tier in ("release", "beta", "alpha", "dev"):
        monkeypatch.setenv("FICHERO_FEATURE_TIER", tier)
        assert resolve_feature_tier() == tier


def test_release_build_404s_dev_alpha_and_beta_routes(monkeypatch):
    client = _tier_client(monkeypatch, "release")

    assert client.get("/api/iiif/iiif/test/info.json").status_code == 404
    assert client.post("/api/chat").status_code == 404
    assert client.get("/api/research/projects").status_code == 404
    assert client.get("/api/activity").status_code == 404


def test_beta_build_404s_dev_and_alpha_routes(monkeypatch):
    client = _tier_client(monkeypatch, "beta")

    assert client.get("/api/iiif/iiif/test/info.json").status_code == 404
    assert client.post("/api/chat").status_code == 404
    assert client.get("/api/research/projects").status_code != 404
    assert client.get("/api/activity").status_code != 404


def test_alpha_build_404s_dev_routes_only(monkeypatch):
    client = _tier_client(monkeypatch, "alpha")

    assert client.get("/api/iiif/iiif/test/info.json").status_code == 404
    assert client.post("/api/chat").status_code != 404
    assert client.get("/api/research/projects").status_code != 404
    assert client.get("/api/activity").status_code != 404
