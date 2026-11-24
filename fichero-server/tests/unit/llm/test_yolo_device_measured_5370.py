"""A YOLO detector runs on the device it measures faster on, MPS or the CPU; nothing hard-codes MPS (#5370).

Spec: docs/contributor_manual/specs/ai/local-runtimes.md (`runtime.pytorch.device-chosen`).
"""
from __future__ import annotations

import time
import types

import pytest

from fichero_server.llm import yolo_runtime

MODEL = yolo_runtime.DEFAULT_MODEL


class _StandIn:
    """A model whose predict takes a set time on each device, and records the devices it was asked for."""

    def __init__(self, seconds: dict[str, float]):
        self.seconds = seconds
        self.calls: list[str] = []

    def predict(self, path, *, device, **_kwargs):
        self.calls.append(device)
        time.sleep(self.seconds[device])
        return [types.SimpleNamespace(orig_shape=(100, 200), names={0: "Text"}, boxes=[])]


@pytest.fixture
def stand_in(monkeypatch, tmp_path):
    def install(seconds, *, mps):
        model = _StandIn(seconds)
        monkeypatch.setattr(yolo_runtime, "_model", lambda model_id: model)
        monkeypatch.setattr(yolo_runtime, "_mps_available", lambda: mps)
        monkeypatch.setattr(yolo_runtime, "_DEVICES", {})
        return model, tmp_path / "page.png"

    return install


@pytest.mark.parametrize("faster", ["mps", "cpu"])
def test_the_device_that_measures_faster_runs_the_page(stand_in, faster):
    slower = "cpu" if faster == "mps" else "mps"
    model, page = stand_in({faster: 0.0, slower: 0.05}, mps=True)
    yolo_runtime.detect_regions(page, MODEL)
    assert model.calls[-1] == faster
    assert set(model.calls[:-1]) == {"mps", "cpu"}  # each device was measured before the page ran
    assert yolo_runtime._DEVICES[MODEL] == faster


def test_the_choice_is_measured_once_per_model(stand_in):
    model, page = stand_in({"mps": 0.0, "cpu": 0.02}, mps=True)
    yolo_runtime.detect_regions(page, MODEL)
    measured = len(model.calls)
    yolo_runtime.detect_regions(page, MODEL)
    assert model.calls[measured:] == ["mps"]


def test_without_mps_the_cpu_runs_and_nothing_is_measured(stand_in):
    model, page = stand_in({"cpu": 0.0}, mps=False)
    yolo_runtime.detect_regions(page, MODEL)
    assert model.calls == ["cpu"]
