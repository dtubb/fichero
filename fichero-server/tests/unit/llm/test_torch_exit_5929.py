"""`runtime.torch.exits-cleanly` (#5929): a process that imported torch must exit as its program says. On macOS 27 the M4
reports show torch's MPS shader-library destructor aborting in `exit()` (SIGABRT, or SIGSEGV), not in Kraken's threads.
M4 2026-10-20: importing torch, asking whether MPS exists, leaving by `SystemExit`, `empty_cache`, a tensor, a matmul, a conv2d
and a bidirectional LSTM on mps ALL exit 0 (plain cases here, kept as proof). The one that aborts (exit -6) is Kraken's own
segmenter loaded (vgsl builds a Core ML model; coremltools warns "Error compiling model") and run on mps (`mps-kraken-blla`,
strict xfail). Which half matters is open: `cpu-kraken-blla` and `kraken-load-only` report XFAIL or XPASS without failing the
run. The fix is the engine's exit (`fichero_server.core.fast_exit.leave`: every database closed, logs flushed, then
`os._exit`), and its case runs the trigger and leaves through it. One tiny process per case; M4 only."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("torch") is None, reason="macOS with torch only (the M4)")

TRIGGER = pytest.mark.xfail(reason="#5929: loading Kraken's model (vgsl builds a Core ML model) aborts the process at exit on "
                                   "macOS 27 (SIGABRT, MetalShaderLibrary destructor), on mps or the CPU; the engine's way out "
                                   "(`core.fast_exit.leave`) is the fix, so the bare process stays an expected failure", strict=True)
BLLA = ("import torch; from importlib import resources; from kraken.lib import vgsl; "
        "m = vgsl.TorchVGSLModel.load_model(resources.files('kraken').joinpath('blla.mlmodel')); ")
BLLA_FORWARD = "m.nn.eval(); torch.no_grad().__enter__(); m.nn(torch.zeros(1, 3, 512, 512, device={device!r}))"
SRC = Path(__file__).resolve().parents[3] / "src"  # this tree's code, not the venv's installed (older) copy
FAST_EXIT = f"; sys.path.insert(0, {str(SRC)!r}); from fichero_server.core.fast_exit import leave; leave(0)"
CASES = [
    ("import-only", "import torch", 0),
    ("mps-asked", "import torch; torch.backends.mps.is_available()", 0),
    ("system-exit", "import torch; raise SystemExit(0)", 0),
    ("uncaught-error", "import torch; raise RuntimeError('boom')", 1),  # a Python error is exit 1, never a signal
    # M4 2026-10-20: none of these touches the trigger (they all exit 0); kept as the proof that plain MPS work is not it.
    ("mps-empty-cache", "import torch; torch.mps.empty_cache()", 0),
    ("mps-tensor", "import torch; torch.zeros(1, device='mps')", 0),
    ("mps-matmul", "import torch; a = torch.randn(256, 256, device='mps'); (a @ a).sum().item()", 0),
    ("mps-conv2d", "import torch; c = torch.nn.Conv2d(1, 8, 3).to('mps'); c(torch.randn(1, 1, 64, 64, device='mps')).sum().item()", 0),
    ("mps-lstm", "import torch; l = torch.nn.LSTM(16, 16, bidirectional=True).to('mps'); "
                 "l(torch.randn(10, 1, 16, device='mps'))[0].sum().item()", 0),
    # The trigger: Kraken's own segmenter loaded and run on mps, as the engine does when the person chose the GPU (exit -6).
    pytest.param("mps-kraken-blla", BLLA + "m.nn.to('mps'); " + BLLA_FORWARD.format(device="mps"), 0, marks=TRIGGER),
    # M4 2026-10-20: the same load with the forward on the CPU (the engine's default device), and the load alone, abort too:
    # the trigger is the model load (vgsl + coremltools), not mps.
    pytest.param("cpu-kraken-blla", BLLA + BLLA_FORWARD.format(device="cpu"), 0, marks=TRIGGER),
    pytest.param("kraken-load-only", BLLA.rstrip("; "), 0, marks=TRIGGER),
    # The fix: the engine's way out (`fichero_server.core.fast_exit.leave`: every database closed, logs flushed, then
    # `os._exit`) leaves the process that took the trigger with its own status. Red until the module exists.
    ("mps-kraken-blla-left-by-the-engines-exit", "import sys; " + BLLA + "m.nn.to('mps'); " + BLLA_FORWARD.format(device="mps") + FAST_EXIT, 0),
]


@pytest.mark.parametrize(("name", "code", "expected"), CASES)
def test_a_process_that_imported_torch_exits_as_its_program_says(name, code, expected):
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=120)
    assert done.returncode == expected, f"{name}: exit {done.returncode} (negative = signal)\n{done.stderr.decode()[-400:]}"
