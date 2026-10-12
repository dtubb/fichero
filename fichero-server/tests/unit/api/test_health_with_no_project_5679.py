"""`contract.health-with-no-project` and `contract.dev-engine-version-is-its-source` (#5679).

Spec: docs/contributor_manual/specs/harness/version-and-contract-integrity.md. WHY (2026-10-11, the MCP onboarding
walk): with no project chosen, fichero_health said "unhealthy", named a stale container path and told an agent to
POST /api/library; and backend_version read 2026.9.20 beside contract 2026.10.11 (the dev venv's old install).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from fichero_server.api.main import app


def test_a_project_that_is_not_here_leaves_the_engine_healthy_and_is_not_echoed(tmp_path):
    stale = tmp_path / "Library" / "Containers" / "app.fichero.fichero" / "EAP 1740.fichero"
    body = TestClient(app).get("/api/health", headers={"X-Fichero-Library-Path": str(stale)}).json()
    assert body["status"] == "healthy"
    assert body["project_note"] == "The project this caller names is not on this Mac; choose one."
    assert "EAP 1740" not in str(body) and "/api/" not in str(body)
    assert not stale.parent.exists(), "nothing is created (#5136)"


def test_no_project_named_says_none_is_selected():
    body = TestClient(app).get("/api/health").json()
    assert body["status"] == "healthy" and body["project_note"] == "No project is selected."


def test_a_dev_engine_reports_its_source_version():
    source = Path(__file__).resolve().parents[3] / "pyproject.toml"
    expected = tomllib.loads(source.read_text(encoding="utf-8"))["project"]["version"]
    assert TestClient(app).get("/api/health").json()["backend_version"] == expected
