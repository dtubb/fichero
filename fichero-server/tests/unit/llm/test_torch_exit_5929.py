"""`runtime.torch.exits-cleanly` (#5929): a process that imported torch must exit 0. On macOS 27 the M4 reports show torch's
MPS shader-library destructor faulting in `exit()` (SIGSEGV or SIGABRT), in any process with torch loaded, threads or not.
One tiny process per case, a few seconds each; M4 only (skipped without macOS and torch)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("torch") is None, reason="macOS with torch only (the M4)")

CASES = {
    "import-only": "import torch",
    "mps-asked": "import torch; torch.backends.mps.is_available()",
    "uncaught-error": "import torch; raise SystemExit(0)",
}


@pytest.mark.parametrize("name", CASES)
def test_a_process_that_imported_torch_exits_zero(name):
    done = subprocess.run([sys.executable, "-I", "-c", CASES[name]], capture_output=True, timeout=120)
    assert done.returncode == 0, f"{name}: exit {done.returncode} (negative = signal)\n{done.stderr.decode()[-400:]}"
