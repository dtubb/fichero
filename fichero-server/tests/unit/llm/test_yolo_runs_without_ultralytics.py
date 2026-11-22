"""A page of Find Regions through `yolo_runtime` runs on the device it measured, against a fake `ultralytics`.

Spec: docs/contributor_manual/specs/ai/local-runtimes.md (`runtime.yolo.imports-wherever-the-engine-runs`).

The check runners have no ultralytics, so a fake module (settings, and a YOLO that returns fixed boxes) stands in
for it in `sys.modules`; the engine's own import, load and detect path runs against it. The real model is
`test_yolo_real_model.py` (`-m real_model`).
"""
from __future__ import annotations

import sys
import types

from fichero_server.llm import yolo_runtime

MODEL = yolo_runtime.DEFAULT_MODEL
FILE = yolo_runtime.YOLO_MODELS[MODEL][1]


class _Box:
    def __init__(self, cls, conf, xyxy):
        self.cls, self.conf = cls, conf
        self.xyxy = [types.SimpleNamespace(tolist=lambda: xyxy)]


class _FakeYolo:
    loaded: list[str] = []
    devices: list[str] = []

    def __init__(self, path):
        _FakeYolo.loaded.append(path)

    def predict(self, path, *, device, **_kwargs):
        _FakeYolo.devices.append(device)
        boxes = [_Box(1, 0.9, [100, 400, 300, 500]), _Box(0, 0.8, [100, 100, 300, 200])]
        return [types.SimpleNamespace(orig_shape=(1000, 500), names={0: "Text", 1: "Title"}, boxes=boxes)]


def test_a_page_runs_against_a_fake_ultralytics_on_the_device_it_measured(tmp_path, monkeypatch):
    settings = {}
    fake = types.ModuleType("ultralytics")
    fake.settings = types.SimpleNamespace(update=settings.update)
    fake.YOLO = _FakeYolo
    monkeypatch.setitem(sys.modules, "ultralytics", fake)
    store = tmp_path / "yolo"
    store.mkdir()
    (store / FILE).write_bytes(b"weights")
    _FakeYolo.loaded, _FakeYolo.devices = [], []
    monkeypatch.setattr(yolo_runtime, "_models_path", lambda: store)
    monkeypatch.setattr(yolo_runtime, "YOLO_SHA256", {})
    monkeypatch.setattr(yolo_runtime, "_LOADED", {})
    monkeypatch.setattr(yolo_runtime, "_DEVICES", {})
    monkeypatch.setattr(yolo_runtime, "_mps_available", lambda: False)

    regions = yolo_runtime.detect_regions(tmp_path / "page.png")

    assert _FakeYolo.loaded == [str(store / FILE)] and settings["sync"] is False
    assert yolo_runtime._DEVICES[MODEL] == "cpu" and _FakeYolo.devices == ["cpu"]  # the device it measured (#5370)
    assert [(r.kind_raw, r.rect, r.confidence) for r in regions] == [
        ("Text", [0.2, 0.1, 0.4, 0.1], 0.8), ("Title", [0.2, 0.4, 0.4, 0.1], 0.9)]
