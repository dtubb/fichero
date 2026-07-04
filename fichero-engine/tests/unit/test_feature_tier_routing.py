"""Tests for API feature-tier route registration."""

from fichero.api.main import get_route_specs_for_tier, resolve_feature_tier


def _route_prefixes_for(tier: str) -> set[str]:
    return {prefix for _, prefix, _ in get_route_specs_for_tier(tier)}


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
    assert "/api/chat" in prefixes
    assert any(
        prefix == "/api" and "model-comparison" in tags
        for _, prefix, tags in get_route_specs_for_tier("release")
    )
    assert "/api/workflows" in prefixes
    assert "/api/workflow-execution" in prefixes
    assert any(
        prefix == "/api" and "activity" in tags
        for _, prefix, tags in get_route_specs_for_tier("release")
    )
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


def test_release_tier_promotes_research_agents():
    """Research routes must not disappear in release builds."""
    release_specs = get_route_specs_for_tier("release")

    assert any(
        prefix == "/api/research" and "research" in tags
        for _, prefix, tags in release_specs
    )


def test_iiif_server_mode_is_dev_tier_only():
    assert not any(
        prefix == "/api/iiif" and "iiif" in tags
        for _, prefix, tags in get_route_specs_for_tier("release")
    )
    assert any(
        prefix == "/api/iiif" and "iiif" in tags
        for _, prefix, tags in get_route_specs_for_tier("dev")
    )


def test_invalid_tier_defaults_to_release(monkeypatch):
    monkeypatch.setenv("FICHERO_FEATURE_TIER", "invalid-tier")
    assert resolve_feature_tier() == "release"
