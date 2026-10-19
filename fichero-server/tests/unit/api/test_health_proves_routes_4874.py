"""`engine.readiness-probe-proves-routes` (#4874): health says the engine is ready only when the route table has
the route groups the app needs, not merely when the process answers.

WHY: a missing dependency made every workflow run-status read 500 while health stayed green. This pins the
cheap half: the routes exist. No database or library is touched.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import fichero_server.api.main as main


def test_a_complete_route_table_is_healthy():
    body = TestClient(main.app).get("/api/health").json()
    assert body["status"] == "healthy"
    assert body["error"] is None


def test_a_missing_route_group_makes_health_unhealthy_and_names_it(monkeypatch):
    monkeypatch.setattr(main, "_REQUIRED_ROUTES", main._REQUIRED_ROUTES + ("/api/not-a-real-route-group",))
    body = TestClient(main.app).get("/api/health").json()
    assert body["status"] == "unhealthy"
    assert "/api/not-a-real-route-group" in body["error"]
