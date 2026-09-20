"""spaCy/Kraken/Whisper fold into the one local-inference catalog (Shape A).

The UI renders and installs every local runtime through a single catalog +
download/progress/delete flow. These tests pin that the coordinator (1) emits
LocalModelCatalogEntry rows tagged by provider_type, (2) dispatches installs to
the right runtime returning the one job shape the UI polls, and (3) deletes
honestly — Whisper weights go, spaCy refuses (pip's job), Kraken removes its
venv.
"""

from __future__ import annotations


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

    def test_kraken_lists_the_segmenter_and_recognition_models(self):
        entries = cat.kraken_catalog_entries()
        by_id = {e.model_id: e for e in entries}
        # Segmenter (built-in) + the two known-good HTR models — no empty picker.
        assert cat.KRAKEN_MODEL_ID in by_id
        assert by_id[cat.KRAKEN_MODEL_ID].capabilities == ["segmentation"]
        assert "kraken-mccatmus" in by_id
        assert "kraken-catmus-medieval" in by_id
        assert by_id["kraken-mccatmus"].capabilities == ["recognition"]
        assert by_id["kraken-mccatmus"].download_size_bytes > 0

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
            # download_size_bytes may be None for user-configured, 0 for a
            # BUNDLED row that downloads nothing (#4959: the Kraken segmenter
            # itself), but every other curated row here declares a real size.
            assert e.download_size_bytes is None or e.download_size_bytes >= 0


class TestOwnership:
    def test_owns_the_three_runtimes_not_mlx(self):
        assert cat.owns("es_core_news_md")
        assert cat.owns("turbo")
        assert cat.owns(cat.KRAKEN_MODEL_ID)
        assert cat.owns("kraken-mccatmus")  # recognition model
        # An MLX curated id belongs to the MLX store, not the coordinator.
        assert not cat.owns("Qwen2.5-VL-3B")

    def test_kraken_recognition_delete_is_a_noop_when_absent(self):
        # Deleting an un-downloaded HTR model just drops a marker that isn't
        # there — freed bytes 0, no error.
        assert cat.get_local_model_coordinator().delete("kraken-mccatmus") == 0


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
    async def test_kraken_install_reports_bundled_status_synchronously(self, monkeypatch):
        """#4959: Kraken is bundled at build time, not installed on demand —
        "install" just answers whether the bundle actually carries it, with
        no job to await."""
        from fichero_server.llm import kraken_runtime

        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)

        job = await cat.get_local_model_coordinator().start_install(cat.KRAKEN_MODEL_ID)

        assert job.job_id.startswith("kraken:")
        assert job.model_id == cat.KRAKEN_MODEL_ID
        assert job.state == "completed"

    @pytest.mark.asyncio
    async def test_kraken_install_reports_a_packaging_problem_when_absent(self, monkeypatch):
        from fichero_server.llm import kraken_runtime

        monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)

        job = await cat.get_local_model_coordinator().start_install(cat.KRAKEN_MODEL_ID)

        assert job.state == "failed"
        assert "not bundled" in job.error.lower()


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

    def test_kraken_delete_refuses_its_bundled_with_the_app(self):
        """#4959: Kraken ships INSIDE the signed bundle — there is nothing a
        runtime delete could remove, so this must refuse, not silently no-op."""
        with pytest.raises(RuntimeError, match="bundled with the app"):
            cat.get_local_model_coordinator().delete(cat.KRAKEN_MODEL_ID)
