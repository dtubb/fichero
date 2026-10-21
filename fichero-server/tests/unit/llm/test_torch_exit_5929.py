"""`runtime.torch.exits-cleanly` (#5929): a process that imported torch must exit as its program says. On macOS 27 the M4
reports show torch's MPS shader-library destructor faulting in `exit()` (SIGSEGV or SIGABRT), not in Kraken's threads. The
M4 run of the first three cases passed 3/3: importing torch, asking whether MPS exists and leaving by `SystemExit` do NOT
crash, so the trigger is a process that actually USED the GPU. The `mps-*` cases are the suspects (the engine's
`release_resident_models` calls `torch.mps.empty_cache()` whenever MPS exists); expected to fail until the clean-exit fix,
and STRICT: a suspect that exits 0 (XPASS) fails the run, and that is the evidence it is not the trigger (drop its xfail
then). `uncaught-error` was added after the M4 run and has not run there; the kernel cases (`mps-matmul`, `mps-conv2d`, `mps-lstm`, `mps-kraken-blla`) are the next suspects, added 2026-10-20 after `mps-empty-cache` and `mps-tensor` came back XPASS. One tiny process per case; M4 only."""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("torch") is None, reason="macOS with torch only (the M4)")

SUSPECT = pytest.mark.xfail(reason="#5929: torch's MPS destructor faults at exit on macOS 27 after the GPU was used; "
                                   "red until the clean-exit fix (trigger unconfirmed)",
                           strict=True)
CASES = [
    ("import-only", "import torch", 0),
    ("mps-asked", "import torch; torch.backends.mps.is_available()", 0),
    ("system-exit", "import torch; raise SystemExit(0)", 0),
    ("uncaught-error", "import torch; raise RuntimeError('boom')", 1),  # a Python error is exit 1, never a signal
    pytest.param("mps-empty-cache", "import torch; torch.mps.empty_cache()", 0, marks=SUSPECT),
    pytest.param("mps-tensor", "import torch; torch.zeros(1, device='mps')", 0, marks=SUSPECT),
    # M4 2026-10-20: both cases above exit 0 (XPASS): a tensor and an empty_cache compile no kernel. The destructor needs real
    # compiled MPS kernels, so these run some (`.item()` waits for the result, so the kernel really ran).
    pytest.param("mps-matmul", "import torch; a = torch.randn(256, 256, device='mps'); (a @ a).sum().item()", 0, marks=SUSPECT),
    pytest.param("mps-conv2d", "import torch; c = torch.nn.Conv2d(1, 8, 3).to('mps'); "
                 "c(torch.randn(1, 1, 64, 64, device='mps')).sum().item()", 0, marks=SUSPECT),
    pytest.param("mps-lstm", "import torch; l = torch.nn.LSTM(16, 16, bidirectional=True).to('mps'); "
                 "l(torch.randn(10, 1, 16, device='mps'))[0].sum().item()", 0, marks=SUSPECT),
    # Kraken's own segmenter (conv + LSTM, the bundled blla model) forward on mps, as the engine would run it: 512 px square.
    pytest.param("mps-kraken-blla", "import torch; from importlib import resources; from kraken.lib import vgsl; "
                 "m = vgsl.TorchVGSLModel.load_model(resources.files('kraken').joinpath('blla.mlmodel')); "
                 "m.nn.to('mps').eval(); torch.no_grad().__enter__(); m.nn(torch.zeros(1, 3, 512, 512, device='mps'))", 0,
                 marks=SUSPECT),
]


@pytest.mark.parametrize(("name", "code", "expected"), CASES)
def test_a_process_that_imported_torch_exits_as_its_program_says(name, code, expected):
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=120)
    assert done.returncode == expected, f"{name}: exit {done.returncode} (negative = signal)\n{done.stderr.decode()[-400:]}"
