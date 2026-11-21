"""The line finder's convolutions run a band of rows at a time (runner.measured, perf-1): the same output, a smaller im2col buffer."""
import sys
import types

import pytest

torch = pytest.importorskip("torch")

from fichero_server.llm import kraken_runtime  # noqa: E402


class _Layer(torch.nn.Module):
    def __init__(self, co):
        super().__init__()
        self.co = co

    def forward(self, x):
        return self.co(x)


class _Model:
    def __init__(self, layers):
        self.nn = torch.nn.Sequential(*layers)


def _model():
    torch.manual_seed(0)
    return _Model([
        _Layer(torch.nn.Conv2d(3, 4, 7, stride=(2, 2), padding=3)),
        _Layer(torch.nn.Conv2d(4, 5, 3, padding=1)),
        _Layer(torch.nn.Conv2d(5, 5, 1)),
        _Layer(torch.nn.Conv2d(5, 5, 3, padding=2, dilation=2)),
    ])


def test_banded_convolutions_give_the_same_output_and_skip_1x1_and_dilated():
    model = _model()
    x = torch.randn(1, 3, 101, 77)
    with torch.no_grad():
        want = model.nn(x)
    wrapped = kraken_runtime._band_convolutions(model, rows=8)
    assert wrapped == 2
    with torch.no_grad():
        got = model.nn(x)
    assert got.shape == want.shape
    assert torch.allclose(got, want, atol=1e-5)


def test_the_segmenter_is_banded_at_32_rows(monkeypatch):
    model = _model()
    seen = {}
    monkeypatch.setattr(kraken_runtime, "_band_convolutions", lambda m, rows: seen.update(rows=rows) or 0)
    monkeypatch.setattr(kraken_runtime, "_resident", lambda kind, key, load: load())
    vgsl = types.SimpleNamespace(TorchVGSLModel=types.SimpleNamespace(load_model=lambda path: model))
    monkeypatch.setitem(sys.modules, "kraken", types.ModuleType("kraken"))
    monkeypatch.setitem(sys.modules, "kraken.lib", types.SimpleNamespace(vgsl=vgsl))
    monkeypatch.setitem(sys.modules, "kraken.lib.vgsl", vgsl)
    monkeypatch.setattr("importlib.resources.files", lambda name: types.SimpleNamespace(joinpath=lambda p: p))
    assert kraken_runtime._segmenter() is model
    assert seen == {"rows": 32}


def test_the_newer_segmentation_base_loads_through_the_task_model_and_is_banded_too(monkeypatch):
    inner = _model()
    task_model = types.SimpleNamespace(model=inner)
    loaded, kinds = [], []
    tasks = types.ModuleType("kraken.tasks")
    tasks.SegmentationTaskModel = types.SimpleNamespace(load_model=lambda path: loaded.append(path) or task_model)
    monkeypatch.setitem(sys.modules, "kraken", types.ModuleType("kraken"))
    monkeypatch.setitem(sys.modules, "kraken.tasks", tasks)
    monkeypatch.setattr(kraken_runtime, "_resident", lambda kind, key, load: kinds.append(key) or load())
    x = torch.randn(1, 3, 101, 77)
    with torch.no_grad():
        want = inner.nn(x)
    assert kraken_runtime._segmenter("/models/base-2026.safetensors") is task_model
    assert loaded == ["/models/base-2026.safetensors"] and kinds == ["/models/base-2026.safetensors"]
    assert sum(isinstance(layer.co, torch.nn.Module) and not isinstance(layer.co, torch.nn.Conv2d) for layer in inner.nn) == 2
    with torch.no_grad():
        assert torch.allclose(inner.nn(x), want, atol=1e-5)


def test_blla_and_the_newer_base_are_resident_under_different_keys(monkeypatch):
    kinds = []
    monkeypatch.setattr(kraken_runtime, "_resident", lambda kind, key, load: kinds.append(key))
    kraken_runtime._segmenter()
    kraken_runtime._segmenter("/models/base-2026.safetensors")
    assert kinds == ["blla", "/models/base-2026.safetensors"]
