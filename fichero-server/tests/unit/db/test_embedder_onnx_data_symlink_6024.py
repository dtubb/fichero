"""#6024: the HF cache links model files into blobs/; ONNX refuses external data that resolves outside the model folder."""

import os

from fichero_server.db import embed_process


def _snapshot(tmp_path):
    repo = tmp_path / "models--x--y"
    blob = repo / "blobs" / "abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"weights")
    snap = repo / "snapshots" / "rev" / "onnx"
    snap.mkdir(parents=True)
    (snap / "model.onnx_data").symlink_to(os.path.relpath(blob, snap))
    return snap / "model.onnx_data", blob


def test_symlinked_onnx_data_becomes_a_real_file_in_the_model_folder(tmp_path):
    link, blob = _snapshot(tmp_path)
    assert os.path.realpath(link) == str(blob.resolve())
    embed_process.materialise_model_links(str(tmp_path))
    assert not link.is_symlink()
    assert link.read_bytes() == b"weights"
    assert blob.exists()  # the cache keeps its blob, so a later download still finds it


def test_materialising_twice_is_harmless(tmp_path):
    link, _ = _snapshot(tmp_path)
    embed_process.materialise_model_links(str(tmp_path))
    embed_process.materialise_model_links(str(tmp_path))
    assert link.read_bytes() == b"weights"


def test_a_link_that_leads_out_of_the_cache_is_left_alone(tmp_path):
    outside = tmp_path / "elsewhere" / "blob"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    cache = tmp_path / "cache"
    snap = cache / "models--x--y" / "snapshots" / "rev"
    snap.mkdir(parents=True)
    (snap / "f").symlink_to(outside)
    embed_process.materialise_model_links(str(cache))
    assert (snap / "f").is_symlink()


def test_a_load_that_escapes_is_retried_after_the_links_are_made_real(tmp_path, monkeypatch):
    import sys
    import types

    link, _ = _snapshot(tmp_path)
    calls = []

    class FakeEmbedding:
        def __init__(self, **_kw):
            calls.append(link.is_symlink())
            if link.is_symlink():
                raise ValueError("External data path escapes model directory")

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeEmbedding))
    embed_process.load_text_embedding("m", str(tmp_path), 1)
    assert calls == [True, False]


def test_a_load_that_works_never_rewrites_the_cache(tmp_path, monkeypatch):
    import sys
    import types

    link, _ = _snapshot(tmp_path)
    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=lambda **_kw: object()))
    embed_process.load_text_embedding("m", str(tmp_path), 1)
    assert link.is_symlink()
