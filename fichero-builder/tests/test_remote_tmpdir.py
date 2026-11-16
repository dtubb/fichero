"""The remote test run does not carry the runner's own TMPDIR through its `env -i` (#6589 item 14).

WHY: on the M4, TMPDIR points at the Dev Disk, whose name holds spaces. Passing it through (3285dc366) made 38 builder
tests red (they build shell lines from unquoted tmp paths) and engine tests answer 403 (a tmp_path project outside the
engine's built-in library roots). Until those are quoted, the run keeps the system's default temp.
"""
from __future__ import annotations

import subprocess
import sys

from fichero_builder import check_tool


def test_the_remote_script_does_not_carry_the_runners_tmpdir(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(check_tool, "_ship", lambda root, cfg, remote="": str(tmp_path))
    monkeypatch.setattr(check_tool, "_gate_python", lambda cfg, gate: sys.executable)
    monkeypatch.setattr(check_tool, "_remote_heavy", lambda py, lock, script: script)
    monkeypatch.setattr(check_tool, "_remote_back", lambda remote: None)
    monkeypatch.setattr(check_tool, "run_command", lambda name, argv, *a, **k: seen.setdefault("script", argv[-1]) and {"exit_code": 0, "stderr_tail": ""})
    check_tool._remote_run("t", [sys.executable, "-c", "import os; print(os.environ.get('TMPDIR', '-'))"], tmp_path, 60,
                           check_tool.Config(remote="m4:/gate"), None, None)
    spaced = tmp_path / "Fichero Dev Disk" / "tmp"
    spaced.mkdir(parents=True)
    out = subprocess.run(["sh", "-c", seen["script"]], capture_output=True, text=True, env={"HOME": str(tmp_path), "TMPDIR": str(spaced), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "-", "the runner's spaced TMPDIR stays out of the test run"
