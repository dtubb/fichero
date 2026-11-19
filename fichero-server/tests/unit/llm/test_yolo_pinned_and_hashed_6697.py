"""The YOLO layout weights are a pickle: they are fetched at a pinned commit and loaded only when their sha256 matches (#6697).

Spec: docs/contributor_manual/specs/compute/runner-reliability.md (`runner.security.yolo-weights-pinned`).
"""
from __future__ import annotations

import hashlib
import sys
import types

import pytest

from fichero_server.llm import yolo_runtime
from fichero_server.llm.failure import ModelBrokenError

MODEL = yolo_runtime.DEFAULT_MODEL


def _fake_ultralytics(monkeypatch, loaded):
    mod = types.ModuleType("ultralytics")
    mod.YOLO = lambda path: loaded.append(path) or object()
    monkeypatch.setitem(sys.modules, "ultralytics", mod)
    monkeypatch.setattr(yolo_runtime, "_quiet", lambda: None)
    monkeypatch.setattr(yolo_runtime, "_LOADED", {})


def test_a_file_whose_hash_differs_is_refused_and_never_reaches_yolo(tmp_path, monkeypatch):
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"not the pinned weights")
    loaded = []
    _fake_ultralytics(monkeypatch, loaded)
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: weights)
    with pytest.raises(ModelBrokenError, match="sha256"):
        yolo_runtime._model(MODEL)
    assert loaded == []


def test_a_file_with_the_pinned_hash_is_loaded(tmp_path, monkeypatch):
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"pinned weights")
    loaded = []
    _fake_ultralytics(monkeypatch, loaded)
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: weights)
    monkeypatch.setitem(yolo_runtime.YOLO_SHA256, MODEL, hashlib.sha256(b"pinned weights").hexdigest())
    yolo_runtime._model(MODEL)
    assert loaded == [str(weights)]


def test_the_download_names_a_commit_revision(tmp_path, monkeypatch):
    import huggingface_hub

    seen = {}
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda **kw: seen.update(kw) or str(tmp_path / "x.pt"))
    monkeypatch.setattr(yolo_runtime, "_models_path", lambda: tmp_path)
    yolo_runtime.download(MODEL)
    assert len(seen["revision"]) == 40 and seen["revision"] == yolo_runtime.YOLO_REVISIONS[MODEL]


def test_every_catalogue_model_has_a_revision_and_a_hash():
    assert set(yolo_runtime.YOLO_REVISIONS) == set(yolo_runtime.YOLO_SHA256) == set(yolo_runtime.YOLO_MODELS)
