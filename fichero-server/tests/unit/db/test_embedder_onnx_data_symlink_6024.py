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
