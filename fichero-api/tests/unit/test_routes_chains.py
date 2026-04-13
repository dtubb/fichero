"""Tests for workflow chain routes.

Chains compose multiple workflows into sequenced pipelines with output mapping
between steps. Uses an in-memory store. Dev-tier feature.
"""

import pytest
from unittest.mock import patch

from fichero.workflows.chaining import chain_store


@pytest.fixture(autouse=True)
def clear_chain_store():
    """Reset the in-memory chain store between tests."""
    chain_store._chains.clear()
    yield
    chain_store._chains.clear()


def _chain_payload(name: str = "Test Chain") -> dict:
    return {
        "name": name,
        "description": "A test chain",
        "steps": [
            {
                "id": "step-1",
                "workflow_id": "wf-abc",
                "name": "First Step",
                "input_mappings": [],
                "static_inputs": {},
                "continue_on_error": False,
                "timeout_seconds": 300,
            }
        ],
        "entry_step": "step-1",
        "initial_inputs": {},
    }


class TestListChains:
    def test_empty_list(self, client):
        r = client.get("/api/chains")
        assert r.status_code == 200
        assert r.json()["chains"] == []

    def test_returns_created_chains(self, client):
        client.post("/api/chains", json=_chain_payload("Chain A"))
        client.post("/api/chains", json=_chain_payload("Chain B"))
        r = client.get("/api/chains")
        assert r.status_code == 200
        assert r.json()["total"] == 2


class TestCreateChain:
    def test_create_chain(self, client):
        r = client.post("/api/chains", json=_chain_payload("My Chain"))
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Chain"
        assert "id" in data

    def test_missing_name_rejected(self, client):
        payload = _chain_payload()
        payload["name"] = ""
        r = client.post("/api/chains", json=payload)
        assert r.status_code == 422


class TestGetChain:
    def test_get_existing_chain(self, client):
        created = client.post("/api/chains", json=_chain_payload()).json()
        r = client.get(f"/api/chains/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/chains/nonexistent-id")
        assert r.status_code == 404


class TestUpdateChain:
    def test_update_name(self, client):
        created = client.post("/api/chains", json=_chain_payload("Old Name")).json()
        update = _chain_payload("New Name")
        r = client.put(f"/api/chains/{created['id']}", json=update)
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/chains/no-such-id", json=_chain_payload())
        assert r.status_code == 404


class TestDeleteChain:
    def test_delete_chain(self, client):
        created = client.post("/api/chains", json=_chain_payload()).json()
        r = client.delete(f"/api/chains/{created['id']}")
        assert r.status_code == 200
        r2 = client.get(f"/api/chains/{created['id']}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/chains/no-such-id")
        assert r.status_code == 404
