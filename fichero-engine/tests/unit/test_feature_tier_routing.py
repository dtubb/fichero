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


def _kg_router_count(tier: str) -> int:
    """Count routers tagged 'knowledge-graph' for a tier."""
    specs = get_route_specs_for_tier(tier)
    return sum(1 for _, _, tags in specs if "knowledge-graph" in tags)


def test_dev_tier_adds_knowledge_graph_routes():
    """Dev tier should expose at least as much KG surface as release,
    plus at least one extra dev-only KG router. Post-1587a1b6 (#832),
    the KG namespace was consolidated under /api/kg/* and most of it
    ships in release; only a small dev-only delta remains.
    """
    assert _kg_router_count("dev") > _kg_router_count("release")
    # Sanity: release still has the consolidated KG surface available
    # (claim-search, entity-curation, etc.).
    assert _kg_router_count("release") >= 5


def test_invalid_tier_defaults_to_release(monkeypatch):
    monkeypatch.setenv("FICHERO_FEATURE_TIER", "invalid-tier")
    assert resolve_feature_tier() == "release"
