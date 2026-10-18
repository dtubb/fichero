"""`openapi.mcp.attaches-never-starts` (#5512): the installed `fichero-mcp` launcher attaches to the running app's
engine and never starts a second one; with none running it says so in one sentence, in words.

WHY (2026-10-05 night): two sub-agents each left a packaged `Fichero Server` running, parented to the agent
processes, started on agent start while the Dev Local engine already served the socket: two engines on one DuckDB.
The launcher is the bundled engine binary run with FICHERO_RUN_MODULE=fichero_mcp.server (what the Install Tools
window writes), so this runs it the same way, with nothing listening.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _engines() -> set[str]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    return {line.split(None, 1)[0] for line in out.splitlines()
            if "fichero_server" in line and "FICHERO_RUN_MODULE" not in line and "pytest" not in line
            and "ps -axo" not in line}


def test_with_no_engine_the_launcher_says_so_and_starts_none():
    before = _engines()
    env = {**os.environ, "FICHERO_RUN_MODULE": "fichero_mcp.server", "FICHERO_API_URL": "http://127.0.0.1:9",
           "FICHERO_UDS": "0", "FICHERO_API_KEY": "test"}
    done = subprocess.run([sys.executable, "-m", "fichero_server"], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=60)
    assert "not running" in done.stderr, done.stderr
    assert "open the Fichero app" in done.stderr
    assert _engines() <= before, "the launcher started an engine"
