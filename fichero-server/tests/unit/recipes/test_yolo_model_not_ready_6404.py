"""A layout model whose weights are not on this Mac is ONE visible "model not ready" state, not a page that finds nothing (#6404).

Spec: docs/contributor_manual/specs/source/image-preparation.md (`prep.yolo.regions-card`); the run fails before any page with the
typed missing-model error, which the run's failure classification words as `model_missing` with the download in Settings.
"""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.llm import yolo_runtime
from fichero_server.llm.local_inference import LocalModelNotInstalledError
from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import regions

MODEL = next(iter(yolo_runtime.YOLO_MODELS))


def _page(db, tmp_path) -> Document:
    path = tmp_path / "1_page.png"
    Image.new("RGB", (200, 300), (235, 230, 220)).save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def test_a_missing_model_stops_the_run_before_any_page_as_not_ready(db, tmp_path, monkeypatch):
    doc = _page(db, tmp_path)
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    seen = []
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda *a, **k: seen.append(a) or [])
    with pytest.raises(LocalModelNotInstalledError, match="not downloaded"):
        regions.find_regions(db, [doc.id], "run-1", MODEL, provider="yolo", person=True)
    assert seen == []  # no page was looked at


def test_the_loader_raises_the_same_typed_error(monkeypatch):
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    with pytest.raises(LocalModelNotInstalledError):
        yolo_runtime._model(MODEL)


def test_a_missing_model_is_worded_as_model_missing(monkeypatch):
    from fichero_server.execution.runner import _typed_failure

    assert _typed_failure(LocalModelNotInstalledError("x"))["category"] == "model_missing"


def test_no_pages_is_not_a_failure(db, monkeypatch):
    monkeypatch.setattr(yolo_runtime, "model_path", lambda model_id: None)
    assert regions.find_regions(db, [], "run-1", MODEL, provider="yolo", person=True)["pages"] == 0
