"""`recipes-run.memory.no-onnx-telemetry-thread`: onnxruntime starts a telemetry worker when it is imported, and
`disable_telemetry_events()` leaves it running, so the switch has to be set before the import, by the engine's first module."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).parents[3] / "src"
THREADS_ADDED = """
{first}
import psutil
before = psutil.Process().num_threads()
import onnxruntime
print(psutil.Process().num_threads() - before)
"""


def _threads_added(first: str, tmp_path: Path) -> int:
    env = {k: v for k, v in os.environ.items() if k != "ORT_DISABLE_TELEMETRY"}
    env.update(HOME=str(tmp_path), FICHERO_BASE_PATH=str(tmp_path), PYTHONPATH=str(SRC))
    done = subprocess.run([sys.executable, "-c", THREADS_ADDED.format(first=first)], env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-800:]
    return int(done.stdout.split()[-1])


def test_a_process_that_starts_with_the_engine_has_no_telemetry_thread(tmp_path):
    assert _threads_added("import fichero_server", tmp_path) == 0


def test_without_the_engine_the_import_starts_threads(tmp_path):
    """The control: this onnxruntime still starts the worker, so the count above can see it. If an upgrade stops it, this
    fails: check the switch still means what `fichero_server/__init__.py` says, then drop both."""
    assert _threads_added("", tmp_path) > 0
