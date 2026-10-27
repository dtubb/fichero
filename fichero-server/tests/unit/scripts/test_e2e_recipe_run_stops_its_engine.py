"""scripts/e2e_recipe_run.py stops its temp engine when it is killed with SIGTERM (Part of #6087).
WHY: the manager's M4 run (2026-10-26) killed the script and its uvicorn engine stayed up: SIGTERM ended Python without
running the `finally` that stops the engine."""
from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

DRIVER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
import e2e_recipe_run
MARKER = sys.argv[2]
made = []
_mkdtemp = e2e_recipe_run.tempfile.mkdtemp
e2e_recipe_run.tempfile.mkdtemp = lambda *a, **k: made.append(_mkdtemp(*a, **k)) or made[-1]

class Engine:
    @property
    def token(self):
        print("started", flush=True)
        time.sleep(60)
    def stop(self):
        open(MARKER, "w").write("\n".join(made))

e2e_recipe_run.start_engine = lambda **_k: Engine()
sys.argv = ["e2e_recipe_run.py", "--out", sys.argv[3]]
e2e_recipe_run.main()
"""


def test_sigterm_stops_the_temp_engine(tmp_path):
    marker = tmp_path / "stopped"
    proc = subprocess.Popen([sys.executable, "-c", DRIVER, str(SCRIPTS), str(marker), str(tmp_path / "out")],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "started"
        proc.send_signal(signal.SIGTERM)
        proc.wait(10)
    finally:
        proc.kill()
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    made = marker.read_text().split()
    assert made, "the engine was not stopped"
    assert not any(Path(folder).exists() for folder in made), "the temp base folder was left behind (pass --keep to keep it)"
