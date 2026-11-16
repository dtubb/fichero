"""The remote test run keeps the runner's TMPDIR through its `env -i` (#6589 item 14).

WHY: the M4's internal disk was full (466 MiB free); its ~/.zshenv points TMPDIR at the Dev Disk, but `env -i` wiped it, so
pytest's tmp_path went to /private/tmp and test_measure read "imac has 0 GiB free" (perf-sweep-3, 2026-11-16).
"""
from __future__ import annotations

import subprocess
import sys

from fichero_builder import check_tool


def test_the_remote_script_passes_tmpdir_through_env_i_even_with_spaces(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(check_tool, "_ship", lambda root, cfg, remote="": str(tmp_path))
    monkeypatch.setattr(check_tool, "_gate_python", lambda cfg, gate: sys.executable)
    monkeypatch.setattr(check_tool, "_remote_heavy", lambda py, lock, script: script)
    monkeypatch.setattr(check_tool, "_remote_back", lambda remote: None)
    monkeypatch.setattr(check_tool, "run_command", lambda name, argv, *a, **k: seen.setdefault("script", argv[-1]) and {"exit_code": 0, "stderr_tail": ""})
    cfg = check_tool.Config(remote="m4:/gate")
    check_tool._remote_run("t", [sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"], tmp_path, 60, cfg, None, None)
    disk = tmp_path / "Fichero Dev Disk" / "tmp"
    disk.mkdir(parents=True)
    out = subprocess.run(["sh", "-c", seen["script"]], capture_output=True, text=True, env={"HOME": str(tmp_path), "TMPDIR": str(disk), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(disk), "tmp_path follows the runner's TMPDIR, never /tmp"
    # no TMPDIR on the runner: the run still works, under /tmp
    out = subprocess.run(["sh", "-c", seen["script"]], capture_output=True, text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0 and out.stdout.strip() in ("/tmp", "/private/tmp"), out
