"""Tests for local AI model management routes.

Local models (Whisper speech-to-text, embedding models) are downloaded to
~/Library/Application Support/Fichero/models/. Routes list,
download, and delete models without external calls (LocalModelManager mocked).
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_entry(
    model_id: str = "base",
    model_type: str = "whisper",
    is_downloaded: bool = False,
) -> MagicMock:
    m = MagicMock()
    m.model_id = model_id
    m.model_type = model_type
    m.is_downloaded = is_downloaded
    m.size_bytes = 0
    m.to_dict.return_value = {
        "model_id": model_id,
        "model_type": model_type,
        "display_name": model_id,
        "size_bytes": 0,
        "is_downloaded": is_downloaded,
        "expected_size_mb": 0,
        "path": None,
        "metadata": {},
    }
    return m


# ---------------------------------------------------------------------------
# GET /api/local-models
# ---------------------------------------------------------------------------


class TestListLocalModels:
    def test_models_base_uses_shared_server_state_dir(self):
        from fichero_server.llm.local_models import MODELS_BASE
        from fichero_server.db.paths import server_state_dir

        assert MODELS_BASE == server_state_dir() / "models"
        assert "com.fichero.fichero" not in str(MODELS_BASE)

    def test_returns_all_models(self, client):
        models = [_make_model_entry("base"), _make_model_entry("small")]
        with patch("fichero_server.llm.local_models.LocalModelManager") as MockMgr:
            MockMgr.return_value.list_all.return_value = models
            r = client.get("/api/local-models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert len(data["models"]) == 2

    def test_filter_by_whisper(self, client):
        models = [_make_model_entry("base", "whisper")]
        with patch("fichero_server.llm.local_models.LocalModelManager") as MockMgr:
            MockMgr.return_value.list_whisper_models.return_value = models
            r = client.get("/api/local-models?model_type=whisper")
        assert r.status_code == 200
        assert len(r.json()["models"]) == 1

    def test_filter_by_embeddings(self, client):
        models = [_make_model_entry("intfloat/e5-large", "embeddings")]
        with patch("fichero_server.llm.local_models.LocalModelManager") as MockMgr:
            MockMgr.return_value.list_embeddings_models.return_value = models
            r = client.get("/api/local-models?model_type=embeddings")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/local-models/disk-usage
# ---------------------------------------------------------------------------


class TestDiskUsage:
    def test_returns_disk_usage(self, client):
        with patch("fichero_server.llm.local_models.LocalModelManager") as MockMgr:
            MockMgr.return_value.total_disk_usage.return_value = {
                "whisper": 500_000,
                "embeddings": 1_000_000,
                "total": 1_500_000,
            }
            r = client.get("/api/local-models/disk-usage")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/local-models/download/{model_type}/{model_id}
# ---------------------------------------------------------------------------


def _audio_runtime(ready: bool) -> dict:
    return {
        "ready": ready,
        "mlx_whisper_version": "0.4.3" if ready else None,
        "reason": None if ready else "The MLX runtime has no transcriber yet. Provision it in Settings.",
    }


class TestDownloadModel:
    def test_download_valid_whisper_model(self, client):
        with patch("fichero_server.llm.local_models.LocalModelManager"):
            with patch("fichero_server.llm.local_models.WHISPER_MODELS", {"base": {}}):
                with patch(
                    "fichero_server.llm.whisper_runtime.audio_runtime_status",
                    return_value=_audio_runtime(True),
                ):
                    r = client.post("/api/local-models/download/whisper/base")
        assert r.status_code == 200
        assert r.json()["status"] == "downloading"

    def test_whisper_download_is_refused_when_no_transcriber_is_installed(self, client):
        """Queueing work that cannot run is how this surface failed silently.

        The download happens in a BackgroundTask, so an unprovisioned runtime
        used to get a 200 "downloading" and a failure nobody ever saw.
        """
        with patch("fichero_server.llm.local_models.LocalModelManager"):
            with patch("fichero_server.llm.local_models.WHISPER_MODELS", {"base": {}}):
                with patch(
                    "fichero_server.llm.whisper_runtime.audio_runtime_status",
                    return_value=_audio_runtime(False),
                ):
                    r = client.post("/api/local-models/download/whisper/base")
        assert r.status_code == 409
        assert "Provision" in r.json()["detail"]

    def test_download_invalid_model_type_returns_400(self, client):
        r = client.post("/api/local-models/download/unknown-type/model-id")
        assert r.status_code == 400

    def test_download_unknown_whisper_model_returns_400(self, client):
        with patch("fichero_server.llm.local_models.WHISPER_MODELS", {"base": {}, "small": {}}):
            r = client.post("/api/local-models/download/whisper/no-such-model")
        assert r.status_code == 400
