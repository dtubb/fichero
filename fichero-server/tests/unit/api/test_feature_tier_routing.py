"""Tests for API feature-tier route registration."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fichero_server.api.main as main_module
from fichero_server.api.feature_tiers_generated import CUMULATIVE_ROUTE_PREFIXES, ROUTE_PREFIX_TIERS
from fichero_server.api.main import get_route_specs_for_tier, register_tiered_routes, resolve_feature_tier


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


def _tiered_public_prefixes_for(tier: str) -> set[str]:
    return {
        main_module._route_spec_public_prefix(route_spec)
        for route_spec in get_route_specs_for_tier(tier)
        if main_module._route_spec_public_prefix(route_spec) in ROUTE_PREFIX_TIERS
    }


def test_tiered_route_prefixes_match_generated_cumulative_map():
    for tier in ("release", "beta", "alpha", "dev"):
        assert _tiered_public_prefixes_for(tier) == set(CUMULATIVE_ROUTE_PREFIXES[tier])


def test_release_tier_keeps_core_routes_and_hides_beta_routes():
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

    assert "/api/providers" not in prefixes
    assert "/api/models" not in prefixes
    assert "/api/workflows" not in prefixes
    assert "/api/workflow-execution" not in prefixes


def _kg_router_count(tier: str) -> int:
    """Count routers tagged 'knowledge-graph' for a tier."""
    specs = get_route_specs_for_tier(tier)
    return sum(1 for _, _, tags in specs if "knowledge-graph" in tags)


def test_higher_tiers_do_not_lose_kg_surface():
    assert _kg_router_count("beta") >= _kg_router_count("release")
    assert _kg_router_count("alpha") == _kg_router_count("beta")
    assert _kg_router_count("dev") >= _kg_router_count("alpha")


def test_iiif_server_mode_is_dev_tier_only():
    assert not _spec_exists("release", "/api/iiif", "iiif")
    assert not _spec_exists("beta", "/api/iiif", "iiif")
    assert not _spec_exists("alpha", "/api/iiif", "iiif")
    assert _spec_exists("dev", "/api/iiif", "iiif")


def test_alpha_and_beta_routes_are_cumulative():
    assert not _spec_exists("release", "/api/chat", "chat")
    assert _spec_exists("beta", "/api/chat", "chat")
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
        assert _spec_exists(tier, "/api/search", "search")
        assert _spec_exists(tier, "/api/ingest", "ingest")

    for tier in ("beta", "alpha", "dev"):
        assert _spec_exists(tier, "/api/workflows", "workflows")
        assert _spec_exists(tier, "/api/workflow-execution", "workflow-execution")


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
    assert client.post("/api/chat").status_code != 404
    assert client.get("/api/research/projects").status_code != 404
    assert client.get("/api/activity").status_code != 404


def test_alpha_build_404s_dev_routes_only(monkeypatch):
    client = _tier_client(monkeypatch, "alpha")

    assert client.get("/api/iiif/iiif/test/info.json").status_code == 404
    assert client.post("/api/chat").status_code != 404
    assert client.get("/api/research/projects").status_code != 404
    assert client.get("/api/activity").status_code != 404


def test_dev_build_serves_release_beta_and_dev_routes(monkeypatch):
    client = _tier_client(monkeypatch, "dev")

    assert client.get("/api/iiif/iiif/test/info.json").status_code != 404
    assert client.post("/api/chat").status_code != 404
    assert client.get("/api/research/projects").status_code != 404
    assert client.get("/api/activity").status_code != 404
