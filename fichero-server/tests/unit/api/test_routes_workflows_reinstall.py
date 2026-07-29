"""
Tests for POST /api/workflows/reinstall-defaults.

The route calls seed_default_workflows(db, force=True). The force-flag
semantics are covered in test_default_workflows.py; here we just
confirm the route is wired, returns 200 with a count, and surfaces
backend errors as 500s.
"""

from __future__ import annotations

from unittest.mock import patch


class TestReinstallDefaults:
    def test_returns_count_of_seeded_workflows(self, client):
        # Empty library → both presets get seeded.
        response = client.post("/api/workflows/reinstall-defaults")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["seeded"] >= 2  # Transcribe + Catalogue minimum

    def test_idempotent_second_call_after_force(self, client):
        # First call seeds. Second call force-deletes and re-seeds the same
        # number. The endpoint does NOT short-circuit when workflows exist
        # because its whole purpose is to push the latest preset version.
        first = client.post("/api/workflows/reinstall-defaults").json()
        second = client.post("/api/workflows/reinstall-defaults").json()
        assert first["seeded"] == second["seeded"]

    def test_backend_failure_returns_500(self, client):
        with patch(
            "fichero_server.workflows.default_workflows.seed_default_workflows",
            side_effect=RuntimeError("db offline"),
        ):
            response = client.post("/api/workflows/reinstall-defaults")
        assert response.status_code == 500
