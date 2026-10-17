"""`source.recipe.pinned-model-gone` (#5364, how it is known ruled 2026-10-17).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: a recipe pinned to a Hugging Face model that
was later taken down said nothing until Start failed. The model store records why the last fetch of a repository failed (not
a dropped connection: the repository is gone or refuses), clears it when the model lands, and the check reads that record
and names the step. The check makes no network call. The store's own download path with Hugging Face's fetch stubbed.
"""
from __future__ import annotations

import asyncio
import socket

import huggingface_hub

from fichero_server.llm.mlx_model_store import ManagedModelDownloadJob, MLXModelStore
from fichero_server.recipes.recipe import check_recipe
from tests.unit.llm.test_a_download_survives_a_broken_connection import quick  # noqa: F401  (no waiting between tries)

STEP = {"id": "read", "job": "read-a-page", "model": {"hf": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
                                                      "revision": "main"}, "runs_on": "this-mac"}


def _recipe() -> dict:
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [STEP]}


def _download(store: MLXModelStore, spec, monkeypatch, fetch) -> ManagedModelDownloadJob:
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fetch)
    job = ManagedModelDownloadJob(job_id="j", model_id=spec.model_id, state="running", current=0, total=1, message="")
    asyncio.run(store._run_download_in_process(job, spec))
    return job


def test_a_failed_fetch_is_recorded_a_landed_one_clears_it_and_the_check_names_the_step(tmp_path, monkeypatch, quick):
    """source.recipe.pinned-model-gone: "a pinned model that can no longer be fetched is reported by the check, naming
    the step"; known from the store's record of the last failed fetch."""
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    store = get_mlx_model_store()
    spec = store.spec("Qwen2.5-VL-3B")
    assert spec.repo_id == STEP["model"]["hf"]
    assert check_recipe(_recipe()) == [] or not any("fetched" in m for m in check_recipe(_recipe()))

    def gone(**kwargs):
        raise RuntimeError("404 Client Error: Repository Not Found")

    assert _download(store, spec, monkeypatch, gone).state == "failed"

    def no_network(*a, **k):
        raise AssertionError("the check must not touch the network")

    with monkeypatch.context() as offline:
        offline.setattr(socket.socket, "connect", no_network)
        said = [m for m in check_recipe(_recipe()) if "step 1 (read)" in m and "can no longer be fetched" in m]
    assert said and "Repository Not Found" in said[0], check_recipe(_recipe())

    assert _download(store, spec, monkeypatch, lambda **kw: str(tmp_path)).state == "completed"
    assert not any("can no longer be fetched" in m for m in check_recipe(_recipe()))


def test_a_dropped_connection_is_not_a_model_gone(tmp_path, monkeypatch, quick):
    """source.recipe.pinned-model-gone: only a repository that is gone or refuses is recorded, never a dropped connection."""
    import requests

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    store = get_mlx_model_store()
    spec = store.spec("Qwen2.5-VL-3B")

    def dropped(**kwargs):
        raise requests.exceptions.ConnectionError("Connection reset by peer")

    _download(store, spec, monkeypatch, dropped)

    assert not any("can no longer be fetched" in m for m in check_recipe(_recipe()))
