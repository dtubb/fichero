"""Coverage for PyKEEN training and stored-prediction routes."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_pykeen as routes
from fichero.pykeen_inference import PredictionResult, PredictionType, StoredPrediction, TrainingResult, TrainingStatus


def _prediction() -> StoredPrediction:
    return StoredPrediction(
        prediction_id="prediction-1",
        model_id="model-1",
        created_at="2026-01-01T00:00:00",
        prediction_type=PredictionType.tail_prediction,
        predictions=[
            PredictionResult(rank=1, score=0.9, entity_id="entity-2", entity_name="Target", confidence=0.9)
        ],
    )


class FakeInference:
    def __init__(self):
        self.prediction = _prediction()
        self.stored = []

    def get_training_jobs(self):
        return [TrainingResult(
            model_id="model-1", status=TrainingStatus.completed, model_type="TransE",
            epochs_completed=2, training_time_ms=3.0, entity_count=2,
            relation_count=1, triple_count=1,
        )]

    def get_training_job(self, model_id):
        return self.get_training_jobs()[0] if model_id == "model-1" else None

    def list_predictions(self, *, model_id=None, verified=None):
        assert model_id == "model-1"
        assert verified is True
        return [self.prediction]

    def get_prediction(self, prediction_id):
        return self.prediction if prediction_id == self.prediction.prediction_id else None

    def delete_model(self, model_id):
        return model_id == "model-1"

    def store_prediction(self, prediction):
        self.stored.append(prediction)


def test_training_job_list_and_lookup(monkeypatch):
    inference = FakeInference()
    monkeypatch.setattr(routes, "get_inference", lambda: inference)

    listed = asyncio.run(routes.list_training_jobs())
    found = asyncio.run(routes.get_training_job("model-1"))

    assert listed.count == 1
    assert listed.items[0].model_id == "model-1"
    assert found.status is TrainingStatus.completed


def test_training_job_lookup_raises_for_unknown_model(monkeypatch):
    monkeypatch.setattr(routes, "get_inference", lambda: FakeInference())

    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.get_training_job("missing"))

    assert caught.value.status_code == 404


def test_stored_prediction_list_and_verify(monkeypatch):
    inference = FakeInference()
    monkeypatch.setattr(routes, "get_inference", lambda: inference)

    listed = asyncio.run(routes.list_stored_predictions(model_id="model-1", verified=True))
    verified = asyncio.run(
        routes.verify_prediction(
            "prediction-1",
            routes.VerifyPredictionRequest(verified=True, notes="reviewed"),
        )
    )

    assert listed.count == 1
    assert verified.notes == "reviewed"
    assert inference.stored == [inference.prediction]


def test_delete_model_and_missing_prediction_errors(monkeypatch):
    monkeypatch.setattr(routes, "get_inference", lambda: FakeInference())

    deleted = asyncio.run(routes.delete_trained_model("model-1"))
    assert deleted.model_dump() == {"deleted": True, "model_id": "model-1"}

    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.delete_trained_model("missing"))
    assert caught.value.status_code == 404

    with pytest.raises(HTTPException) as caught:
        asyncio.run(routes.get_stored_prediction("missing"))
    assert caught.value.status_code == 404
