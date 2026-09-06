"""Tests for local AI model management routes.

Local models (Whisper speech-to-text, embedding models) are downloaded to
~/Library/Application Support/Fichero/models/. Routes list,
download, and delete models without external calls (LocalModelManager mocked).
"""

from unittest.mock import AsyncMock, MagicMock, patch


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


# ---------------------------------------------------------------------------
# Kraken install/status (~1 GB user-chosen segmentation runtime)
# ---------------------------------------------------------------------------


def _kraken_manager(installed: bool, job: dict | None = None) -> MagicMock:
    mgr = MagicMock()
    mgr.status.return_value = {
        "installed": installed,
        "kraken_version": "7.1.1" if installed else None,
        "scipy_override": "scipy>=1.16" if installed else None,
        "runtime_dir": "/tmp/kraken-runtime",
        "disk_usage_bytes": 996_000_000 if installed else 0,
        "reason": None if installed else "Kraken is not installed. ~1 GB download.",
        "job": job,
    }
    mgr.start_install = AsyncMock(return_value=mgr.status.return_value)
    return mgr


class TestKrakenRuntime:
    def test_status_reports_uninstalled_with_a_size_note(self, client):
        with patch(
            "fichero_server.llm.kraken_runtime.get_kraken_runtime",
            return_value=_kraken_manager(installed=False),
        ):
            r = client.get("/api/local-models/kraken/status")
        assert r.status_code == 200
        body = r.json()
        assert body["installed"] is False
        assert body["available"] is True
        assert body["size_note"]  # the UI can warn about the ~1 GB cost
        assert body["job"] is None

    def test_install_starts_the_background_job(self, client):
        job = {
            "job_id": "abc",
            "state": "running",
            "current": 2,
            "total": 4,
            "percent": 50.0,
            "message": "Installing kraken==7.1.1",
            "error": None,
        }
        mgr = _kraken_manager(installed=False, job=job)
        with patch(
            "fichero_server.llm.kraken_runtime.get_kraken_runtime",
            return_value=mgr,
        ):
            r = client.post("/api/local-models/kraken/install")
        assert r.status_code == 200
        assert mgr.start_install.await_count == 1
        assert r.json()["job"]["state"] == "running"

    def test_remove_while_installing_returns_409(self, client):
        mgr = _kraken_manager(installed=True)
        mgr.remove.side_effect = RuntimeError("Kraken install is still running")
        with patch(
            "fichero_server.llm.kraken_runtime.get_kraken_runtime",
            return_value=mgr,
        ):
            r = client.delete("/api/local-models/kraken")
        assert r.status_code == 409
        assert "still running" in r.json()["detail"]
