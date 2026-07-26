"""Tests for app integration routes.

Integration routes bridge Fichero with external macOS apps (DEVONthink,
Bookends, Tinderbox). Routes live at /api/integrations/... (router
prefix="/integrations" mounted at "/api"). The integration registry is
mocked to avoid requiring installed Mac applications.
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_integration(
    name: str = "DEVONthink",
    bundle_id: str = "com.devon-technologies.think3",
    status: str = "available",
) -> MagicMock:
    integration = MagicMock()
    integration.name = name
    integration.bundle_id = bundle_id

    info = MagicMock()
    info.status = MagicMock(value=status)
    info.version = "3.0"
    info.path = None
    info.error_message = None

    integration.app_info = info
    return integration


def _make_registry(integrations: list | None = None, available: list | None = None) -> MagicMock:
    registry = MagicMock()
    registry.list_all.return_value = integrations or []
    registry.list_available.return_value = available or []
    registry.get.return_value = None
    return registry


# ---------------------------------------------------------------------------
# GET /api/integrations
# ---------------------------------------------------------------------------


class TestListIntegrations:
    def test_empty_registry(self, client):
        registry = _make_registry()
        with patch("fichero.api.routes.integrations.get_integration_registry", return_value=registry):
            r = client.get("/api/integrations")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_integrations(self, client):
        devonthink = _make_integration("DEVONthink")
        registry = _make_registry([devonthink])

        with patch("fichero.api.routes.integrations.get_integration_registry", return_value=registry):
            r = client.get("/api/integrations")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["name"] == "DEVONthink"
        assert data["items"][0]["bundle_id"] == "com.devon-technologies.think3"


# ---------------------------------------------------------------------------
# GET /api/integrations/available
# ---------------------------------------------------------------------------


class TestListAvailableIntegrations:
    def test_returns_available_only(self, client):
        available = _make_integration("Tinderbox", "com.eastgate.tinderbox", "available")
        registry = _make_registry(available=[available])

        with patch("fichero.api.routes.integrations.get_integration_registry", return_value=registry):
            r = client.get("/api/integrations/available")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["status"] == "available"


# ---------------------------------------------------------------------------
# GET /api/integrations/{app_name}
# ---------------------------------------------------------------------------


class TestGetIntegration:
    def test_get_existing_integration(self, client):
        devonthink = _make_integration("DEVONthink")
        registry = _make_registry()
        registry.get.return_value = devonthink

        with patch("fichero.api.routes.integrations.get_integration_registry", return_value=registry):
            r = client.get("/api/integrations/devonthink")
        assert r.status_code == 200
        assert r.json()["name"] == "DEVONthink"

    def test_get_missing_integration_returns_404(self, client):
        registry = _make_registry()
        registry.get.return_value = None

        with patch("fichero.api.routes.integrations.get_integration_registry", return_value=registry):
            r = client.get("/api/integrations/no-such-app")
        assert r.status_code == 404
