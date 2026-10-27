"""`activity.lane.kraken-threads-exit-clean` (#5929): a process that loaded Kraken's segmenter and read pages on threads, as the
engine does, exits 0 when it leaves by the engine's way out (`core.fast_exit.leave`). The bare exit aborts on the M4 (torch's
MetalShaderLibrary destructor at `exit()`), not in the threads; on the Pro it exits 0 either way, so this pins the way out
rather than reproducing the abort here."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or importlib.util.find_spec("kraken") is None, reason="macOS with Kraken only")

SRC = Path(__file__).resolve().parents[3] / "src"
TWO_PAGES_ON_THREADS = f"""
import sys, threading
sys.path.insert(0, {str(SRC)!r})
import torch
from importlib import resources
from kraken.lib import vgsl
m = vgsl.TorchVGSLModel.load_model(resources.files('kraken').joinpath('blla.mlmodel'))
m.nn.eval()
done = []
def page():
    with torch.no_grad():
        m.nn(torch.zeros(1, 3, 256, 256))
    done.append(1)
pages = [threading.Thread(target=page) for _ in range(2)]
[t.start() for t in pages]
[t.join() for t in pages]
assert len(done) == 2
from fichero_server.core.fast_exit import leave
leave(0)
raise SystemExit(3)  # leave() returned: torch was not seen, so the way out never ran
"""


def test_two_pages_read_on_threads_then_the_engines_way_out_exits_0(tmp_path):
    done = subprocess.run([sys.executable, "-I", "-c", TWO_PAGES_ON_THREADS], capture_output=True, timeout=180,
                          env={"FICHERO_BASE_PATH": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert done.returncode == 0, f"exit {done.returncode} (negative = signal)\n{done.stderr.decode()[-600:]}"
