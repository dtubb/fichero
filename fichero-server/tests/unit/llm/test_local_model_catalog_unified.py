"""spaCy/Kraken/Whisper fold into the one local-inference catalog (Shape A).

The UI renders and installs every local runtime through a single catalog +
download/progress/delete flow. These tests pin that the coordinator (1) emits
LocalModelCatalogEntry rows tagged by provider_type, (2) dispatches installs to
the right runtime returning the one job shape the UI polls, and (3) deletes
honestly — Whisper weights go, spaCy refuses (pip's job), Kraken removes its
venv.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm import local_model_catalog as cat
from fichero_server.llm.providers import ProviderType


@pytest.fixture(autouse=True)
def _fresh_coordinator(monkeypatch, tmp_path):
    # Isolate Kraken to a temp runtime dir so nothing reads/writes the real one.
    monkeypatch.setenv("FICHERO_KRAKEN_RUNTIME_DIR", str(tmp_path / "kraken-runtime"))
    monkeypatch.setattr(cat, "_COORDINATOR", None)
    yield


class TestCatalog:
    def test_every_row_is_tagged_by_provider(self):
        entries = cat.catalog_entries()
        providers = {e.provider_type for e in entries}
        assert ProviderType.spacy in providers
        assert ProviderType.kraken in providers
        assert ProviderType.whisper in providers

    def test_kraken_is_one_entry_for_the_runtime(self):
        kraken = [e for e in cat.kraken_catalog_entries()]
        assert len(kraken) == 1
        assert kraken[0].model_id == cat.KRAKEN_MODEL_ID
        assert kraken[0].capabilities == ["segmentation"]
        assert kraken[0].download_size_bytes == cat.KRAKEN_DOWNLOAD_SIZE_BYTES

    def test_spacy_rows_include_the_medium_default(self):
        ids = {e.model_id for e in cat.spacy_catalog_entries()}
        assert "es_core_news_md" in ids
        assert "es_core_news_sm" in ids

    def test_whisper_rows_include_turbo(self):
        ids = {e.model_id for e in cat.whisper_catalog_entries()}
        assert "turbo" in ids

    def test_a_row_carries_installed_and_size(self):
        for e in cat.catalog_entries():
            assert isinstance(e.installed, bool)
            # download_size_bytes may be None for user-configured, but every
            # curated row here declares one.
            assert e.download_size_bytes is None or e.download_size_bytes > 0


class TestOwnership:
    def test_owns_the_three_runtimes_not_mlx(self):
        assert cat.owns("es_core_news_md")
        assert cat.owns("turbo")
        assert cat.owns(cat.KRAKEN_MODEL_ID)
        # An MLX curated id belongs to the MLX store, not the coordinator.
        assert not cat.owns("Qwen2.5-VL-3B")


class TestInstallDispatch:
    @pytest.mark.asyncio
    async def test_spacy_install_runs_and_completes(self, monkeypatch):
        called = {}

        def fake_download(self, model_id):
            called["model"] = model_id

        monkeypatch.setattr(
            "fichero_server.llm.local_models.LocalModelManager.download_spacy_model",
            fake_download,
        )
        coord = cat.get_local_model_coordinator()
        job = await coord.start_install("es_core_news_md")
        await coord.wait_for_job(job.job_id)

        done = coord.job(job.job_id)
        assert done.state == "completed"
        assert called["model"] == "es_core_news_md"

    @pytest.mark.asyncio
    async def test_whisper_install_refused_without_a_transcriber(self, monkeypatch):
        monkeypatch.setattr(
            "fichero_server.llm.whisper_runtime.audio_runtime_status",
            lambda: {"ready": False, "reason": "Provision the MLX runtime."},
        )
        coord = cat.get_local_model_coordinator()
        with pytest.raises(RuntimeError, match="Provision"):
            await coord.start_install("turbo")

    @pytest.mark.asyncio
    async def test_a_failed_spacy_install_surfaces_on_the_job(self, monkeypatch):
        def boom(self, model_id):
            raise RuntimeError("no runtime")

        monkeypatch.setattr(
            "fichero_server.llm.local_models.LocalModelManager.download_spacy_model",
            boom,
        )
        coord = cat.get_local_model_coordinator()
        job = await coord.start_install("es_core_news_md")
        await coord.wait_for_job(job.job_id)
        failed = coord.job(job.job_id)
        assert failed.state == "failed"
        assert "no runtime" in failed.error

    @pytest.mark.asyncio
    async def test_kraken_install_dispatches_to_its_manager(self, monkeypatch):
        from fichero_server.llm import kraken_runtime

        # Inject a Kraken manager with fake venv/pip so NO real ~1 GB install
        # runs — the coordinator delegates to whatever get_kraken_runtime()
        # returns, so patch that.
        def _fake_venv(target):
            (target / "bin").mkdir(parents=True, exist_ok=True)
            (target / "bin" / "python").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

        fake = kraken_runtime.KrakenRuntimeManager(
            create_venv=_fake_venv, run_command=lambda argv: None
        )
        monkeypatch.setattr(kraken_runtime, "get_kraken_runtime", lambda: fake)

        job = await cat.get_local_model_coordinator().start_install(cat.KRAKEN_MODEL_ID)
        await fake.wait_for_current_job()
        # The job id is namespaced so the poll route can route it back.
        assert job.job_id.startswith("kraken:")
        assert job.model_id == cat.KRAKEN_MODEL_ID


class TestDelete:
    def test_spacy_delete_refuses_with_pip_guidance(self):
        with pytest.raises(RuntimeError, match="pip uninstall"):
            cat.get_local_model_coordinator().delete("es_core_news_sm")

    def test_whisper_delete_frees_bytes(self, monkeypatch):
        monkeypatch.setattr(
            "fichero_server.llm.local_models.LocalModelManager.delete_whisper_model",
            lambda self, model_id: 123,
        )
        assert cat.get_local_model_coordinator().delete("turbo") == 123

    def test_kraken_delete_removes_the_runtime(self, monkeypatch):
        removed = {}
        from fichero_server.llm import kraken_runtime

        monkeypatch.setattr(
            kraken_runtime.KrakenRuntimeManager,
            "remove",
            lambda self: removed.setdefault("done", True),
        )
        cat.get_local_model_coordinator().delete(cat.KRAKEN_MODEL_ID)
        assert removed["done"] is True
