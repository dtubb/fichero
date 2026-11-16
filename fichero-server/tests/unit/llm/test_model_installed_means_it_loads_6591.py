"""A model is installed when it LOADS (#6591): `activity.download.installed-means-it-loads` (spec
docs/contributor_manual/specs/ui/activity-pane.md, "Ruled 2026-11-14").

The Hugging Face cache's sharded blob store put bge-m3's `model.onnx` and `model.onnx_data` in different real
folders and onnxruntime refused ("External data path escapes model directory"). The download now fetches the
files as plain files into ONE folder, loads the model once before it says installed, and reports a model whose
files exist but does not load as `broken`. Nothing here touches the network or loads a real model.
"""

from __future__ import annotations

import os
import shutil
from types import SimpleNamespace

import pytest

from fichero_server.db import embed_process
from fichero_server.db.embeddings import BGE_M3_FASTEMBED_MODEL, BGE_M3_MODEL
from fichero_server.llm import local_models

FILES = ["onnx/model.onnx", "onnx/model.onnx_data", "config.json", "tokenizer.json"]


class _FakeTextEmbedding:
    @staticmethod
    def list_supported_models():
        return [{"model": BGE_M3_FASTEMBED_MODEL, "sources": {"hf": BGE_M3_MODEL}}]

    loads: list[dict] = []
    fail = False

    def __init__(self, **kwargs):
        if _FakeTextEmbedding.fail:
            raise RuntimeError("External data path escapes model directory")
        _FakeTextEmbedding.loads.append(kwargs)

    @staticmethod
    def _list_supported_models():
        return [SimpleNamespace(model=BGE_M3_FASTEMBED_MODEL, model_file="onnx/model.onnx",
                                additional_files=["onnx/model.onnx_data"], sources=SimpleNamespace(hf=BGE_M3_MODEL))]


@pytest.fixture
def world(tmp_path, monkeypatch):
    _FakeTextEmbedding.loads, _FakeTextEmbedding.fail = [], False
    monkeypatch.setattr("fastembed.TextEmbedding", _FakeTextEmbedding)
    hub = tmp_path / "hub"

    def snapshot_download(repo_id, local_dir, allow_patterns):
        """The new sharded store: the snapshot's two ONNX files are links into two different real folders; a
        `local_dir` download writes real files (what huggingface_hub does)."""
        (hub / "blobs-a").mkdir(parents=True, exist_ok=True)
        (hub / "blobs-b").mkdir(parents=True, exist_ok=True)
        for i, rel in enumerate(FILES):
            blob = hub / ("blobs-a" if i % 2 else "blobs-b") / f"blob{i}"
            blob.write_bytes(b"x" * (i + 1))
            link = hub / "snap" / rel
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.is_symlink():
                link.symlink_to(blob)
            dest = os.path.join(local_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(link, dest)  # follows the link: a plain file

    monkeypatch.setattr("huggingface_hub.snapshot_download", snapshot_download)
    manager = local_models.LocalModelManager.__new__(local_models.LocalModelManager)
    manager.embeddings_path = tmp_path / "embeddings"
    manager.embeddings_path.mkdir()
    return manager, hub


def test_the_new_layout_has_real_files_in_one_folder_and_the_loader_is_handed_it(world):
    manager, _hub = world
    manager.download_embeddings_model(BGE_M3_MODEL)
    folder = manager.embeddings_path / "BAAI--bge-m3"
    for rel in FILES:
        path = folder / rel
        assert path.is_file() and not path.is_symlink()
        assert os.path.realpath(path).startswith(os.path.realpath(folder) + os.sep)
    assert _FakeTextEmbedding.loads[-1]["specific_model_path"] == str(folder)
    listed = {m.model_id: m for m in manager.list_embeddings_models()}[BGE_M3_MODEL]
    assert listed.is_downloaded and listed.download_state == "installed"


def test_a_model_whose_files_exist_but_does_not_load_is_broken_not_installed(world):
    manager, _hub = world
    _FakeTextEmbedding.fail = True
    with pytest.raises(RuntimeError, match="does not load"):
        manager.download_embeddings_model(BGE_M3_MODEL)
    listed = {m.model_id: m for m in manager.list_embeddings_models()}[BGE_M3_MODEL]
    assert not listed.is_downloaded
    assert listed.download_state == "broken"
    assert "escapes model directory" in (listed.download_error or "")
    _FakeTextEmbedding.fail = False
    manager.download_embeddings_model(BGE_M3_MODEL)  # a fresh download clears the mark
    assert {m.model_id: m for m in manager.list_embeddings_models()}[BGE_M3_MODEL].download_state == "installed"


def test_an_older_cache_layout_still_loads_by_the_old_path(world):
    manager, _hub = world
    cache = manager.embeddings_path
    snap = cache / "models--BAAI--bge-m3" / "snapshots" / "abc"
    for rel in FILES:
        (snap / rel).parent.mkdir(parents=True, exist_ok=True)
        (snap / rel).write_bytes(b"x")
    embed_process.load_text_embedding(BGE_M3_FASTEMBED_MODEL, str(cache), 1)
    assert "specific_model_path" not in _FakeTextEmbedding.loads[-1]
    assert embed_process._cached(BGE_M3_FASTEMBED_MODEL, str(cache))


def test_size_on_disk_counts_a_link_and_its_blob_once(tmp_path):
    blob = tmp_path / "blobs" / "b"
    blob.parent.mkdir()
    blob.write_bytes(b"x" * 100)
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "model.onnx").symlink_to(blob)
    assert local_models.bytes_once(tmp_path) == 100
