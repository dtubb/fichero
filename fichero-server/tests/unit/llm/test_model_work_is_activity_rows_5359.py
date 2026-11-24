"""`activity.model-work-visible` (#5359): a model download, a Kraken model fetch and the MLX runtime's setup are `download-model` rows
the jobs list names, not only a bar in Settings."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime, local_models


@pytest.fixture
def held(monkeypatch):
    """The scheduler holds what is queued, so a test reads the row before it runs."""
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


def _first_kraken_reader() -> str:
    for name in ("blla", "kraken-zenodo-21788410"):
        if kraken_runtime.recognition_spec(name) is not None:
            return name
    pytest.skip("no Kraken reader in the catalogue")  # ponytail: a catalogue with none has nothing to fetch


def test_a_whisper_and_an_embedding_model_download_is_a_row(db, held):
    for runtime, name in (("whisper", next(iter(local_models.WHISPER_MODELS))),
                          ("embeddings", next(iter(local_models.EMBEDDINGS_MODELS)))):
        job_id = local_models.enqueue_download(db, runtime, name)
        row = jobs.read_job(db, job_id)
        assert row["kind"] == local_models.DOWNLOAD_KIND and row["subject"] == f"{runtime}:{name}"


def test_the_mlx_runtime_setup_is_a_row_and_asking_twice_is_one_row(db, held):
    first = local_models.enqueue_download(db, local_models.MLX_RUNTIME, "mlx")
    assert jobs.read_job(db, first)["subject"] == f"{local_models.MLX_RUNTIME}:mlx"
    assert local_models.enqueue_download(db, local_models.MLX_RUNTIME, "mlx") == first


def test_a_kraken_model_fetch_is_a_row(db, held):
    name = _first_kraken_reader()
    job_id = local_models.enqueue_download(db, "kraken", name)
    assert jobs.read_job(db, job_id)["subject"] == f"kraken:{name}"
