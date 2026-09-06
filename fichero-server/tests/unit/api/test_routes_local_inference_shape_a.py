"""The one download endpoint installs every local runtime (Shape A).

/api/local-inference/catalog now lists MLX + spaCy + Kraken + Whisper, and
/api/local-inference/models/{id}/download dispatches by model_id to the right
installer while returning the one job shape the UI polls. These tests pin the
dispatch and the honest delete behaviour without touching a real runtime.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fichero_server.llm.mlx_model_store import ManagedModelDownloadJob


class TestUnifiedCatalog:
    def test_catalog_lists_all_four_runtimes(self, client):
        r = client.get("/api/local-inference/catalog")
        assert r.status_code == 200
        providers = {item["provider_type"] for item in r.json()["items"]}
        # MLX is "omlx"; the three folded-in runtimes carry their own types.
        assert {"spacy", "kraken", "whisper"} <= providers

    def test_kraken_appears_as_a_single_entry(self, client):
        r = client.get("/api/local-inference/catalog")
        kraken = [i for i in r.json()["items"] if i["provider_type"] == "kraken"]
        assert len(kraken) == 1
        assert kraken[0]["model_id"] == "kraken-blla"


class TestDownloadDispatch:
    def test_a_spacy_model_downloads_through_the_shared_endpoint(self, client):
        job = ManagedModelDownloadJob(
            job_id="spacy:es_core_news_md:1",
            model_id="es_core_news_md",
            state="running",
            current=1,
            total=2,
            message="Installing es_core_news_md",
        )
        coord = MagicMock()
        coord.start_install = AsyncMock(return_value=job)
        with patch(
            "fichero_server.llm.local_model_catalog.get_local_model_coordinator",
            return_value=coord,
        ):
            r = client.post("/api/local-inference/models/es_core_news_md/download")
        assert r.status_code == 200
        body = r.json()
        assert body["model_id"] == "es_core_news_md"
        assert body["state"] == "running"
        assert coord.start_install.await_count == 1

    def test_whisper_without_a_transcriber_is_a_409(self, client):
        coord = MagicMock()
        coord.start_install = AsyncMock(side_effect=RuntimeError("Provision the MLX runtime."))
        with patch(
            "fichero_server.llm.local_model_catalog.get_local_model_coordinator",
            return_value=coord,
        ):
            r = client.post("/api/local-inference/models/turbo/download")
        assert r.status_code == 409
        assert "Provision" in r.json()["detail"]


class TestDeleteDispatch:
    def test_deleting_a_spacy_model_refuses_with_pip_guidance(self, client):
        # No patch: spaCy delete honestly refuses (pip package), which the route
        # surfaces as a 409 rather than a fake success.
        r = client.delete("/api/local-inference/models/es_core_news_sm")
        assert r.status_code == 409
        assert "pip uninstall" in r.json()["detail"]
