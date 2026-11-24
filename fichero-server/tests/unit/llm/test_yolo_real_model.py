"""A real-model run (needs ultralytics and the stock weights; run with `-m real_model`, not part of the ladder).

Ultralytics imports in the Python the tests run under, and the stock layout model finds regions on a real page
(#5525, #6675).

Spec: docs/contributor_manual/specs/ai/local-runtimes.md (`runtime.yolo.imports-wherever-the-engine-runs`).

No stand-ins: the real import, the real weights, one fixture page. Skipped, with its reason, only where the stock
weights are not in this Mac's model store; an import failure fails the test, never skips. The weights are read
from the real store and copied into the test's own store, so nothing is written to the real one.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fichero_server.llm import yolo_runtime
from tests._real_state_guard import ROOTS

pytestmark = pytest.mark.real_model

_FILE = yolo_runtime.YOLO_MODELS[yolo_runtime.DEFAULT_MODEL][1]
#: The stock weights in this Mac's real model store (the test base's own store is always empty).
STOCK = Path(ROOTS[0]) / "models" / "yolo" / _FILE
PAGE = Path(__file__).resolve().parents[4] / "test-fixtures" / "files" / "sample_text_page1.png"


def test_the_stock_model_finds_regions_on_a_real_page(tmp_path, monkeypatch):
    yolo_runtime._quiet()  # the engine's own import path: settings under the (test) store, offline (an ImportError fails)
    if not STOCK.is_file():
        pytest.skip(f"the stock layout weights are not in this Mac's model store ({STOCK}); "
                    f"download {yolo_runtime.DEFAULT_MODEL} in Fichero first")
    store = tmp_path / "yolo"
    store.mkdir()
    shutil.copyfile(STOCK, store / _FILE)
    monkeypatch.setattr(yolo_runtime, "_models_path", lambda: store)
    monkeypatch.setattr(yolo_runtime, "_LOADED", {})
    monkeypatch.setattr(yolo_runtime, "_DEVICES", {})

    regions = yolo_runtime.detect_regions(PAGE)

    assert yolo_runtime._DEVICES[yolo_runtime.DEFAULT_MODEL] in {"mps", "cpu"}  # the device it measured (#5370)
    assert regions, "the stock model found no region on a printed text page"
    labels = set(yolo_runtime._LOADED[yolo_runtime.DEFAULT_MODEL].names.values())  # DocLayNet's: Text, Title, ...
    for r in regions:
        assert r.kind_raw in labels
        x, y, w, h = r.rect
        assert 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1
        assert 0.25 <= r.confidence <= 1
