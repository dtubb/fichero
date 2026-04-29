"""Tests for PyKEEN prediction routes.

Predictions train knowledge graph embedding models and generate link predictions.
Dev-tier feature. Tests verify the route contract using mocked pykeen_inference.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_inference():
    """Mock the pykeen inference engine."""
    inference = MagicMock()
    inference.get_status.return_value = {
        "enabled": False,
        "models_trained": 0,
        "training_jobs": 0,
        "stored_predictions": 0,
    }
    inference.get_all_predictions.return_value = []
    inference.get_prediction.return_value = None
    inference.store_prediction.return_value = MagicMock(
        id="pred-1",
        prediction_type=MagicMock(value="head"),
        source_entity_id=None,
        target_entity_id=None,
        relation=None,
        predictions=[],
        notes=None,
        verified=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    with patch("fichero.api.routes.predictions.get_inference", return_value=inference):
        yield inference


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPredictionStatus:
    def test_returns_status(self, client):
        r = client.get("/api/predictions/status")
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "models_trained" in data


class TestEnablePredictions:
    def test_enable(self, client):
        with patch("fichero.api.routes.predictions.set_inference_enabled"):
            r = client.post("/api/predictions/enable", json={"enabled": True})
        assert r.status_code == 200
        assert r.json()["enabled"] is True

    def test_disable(self, client):
        with patch("fichero.api.routes.predictions.set_inference_enabled"):
            r = client.post("/api/predictions/enable", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False


class TestGetModels:
    def test_returns_models_list(self, client, mock_inference):
        mock_inference.list_trained_models.return_value = []
        r = client.get("/api/predictions/models")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestGetStoredPredictions:
    def test_returns_empty_list(self, client, mock_inference):
        mock_inference.get_all_predictions.return_value = []
        r = client.get("/api/predictions/stored")
        assert r.status_code == 200
        assert r.json() == []


class TestStorePrediction:
    def test_store_prediction(self, client, mock_inference):
        payload = {
            "prediction_type": "head_prediction",
            "source_entity_id": None,
            "target_entity_id": "entity-1",
            "relation": "knows",
            "predictions": [{"entity_id": "ent-2", "entity_name": "Entity 2", "score": 0.9, "rank": 1, "confidence": 0.9}],
        }
        r = client.post("/api/predictions/store?model_id=test-model", json=payload)
        assert r.status_code == 200
