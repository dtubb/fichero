"""GET /api/health reports LIVE dependency versions for the About box.

Daniel wants the "Built with" list DERIVED from the engine env, never
hard-typed. The Mac app has no in-process Python, so the engine is the only
live source. This pins that /api/health carries a `dependencies` map of
lowercased pip distribution name → installed version, populated for the
notable frameworks and omitting anything not installed (so the box shows a
lib with no version rather than a wrong one).
"""

from __future__ import annotations


def test_health_carries_live_dependency_versions(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    deps = response.json()["dependencies"]
    assert isinstance(deps, dict)
    # Core frameworks are always installed in the engine env.
    assert deps.get("fastapi"), deps
    assert deps.get("pydantic"), deps
    # Keys are lowercased distribution names (the UI looks up by that).
    assert all(key == key.lower() for key in deps)
    # A present key always carries a real version — never an empty/None value.
    assert all(value for value in deps.values())


def test_static_versions_omit_absent_libraries():
    # A distribution that is not installed is simply absent — never a wrong or
    # blank version.
    from fichero_server.api.main import _static_dependency_versions

    versions = _static_dependency_versions()
    assert "fastapi" in versions
    assert "definitely-not-a-real-distribution" not in versions
    assert all(v for v in versions.values())
