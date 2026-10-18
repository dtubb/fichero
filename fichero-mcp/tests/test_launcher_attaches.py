"""`openapi.mcp.attaches-never-starts` (#5512): the MCP launcher attaches to the running engine and never starts
one; with none running it says so in one sentence."""

import os
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_with_no_engine_the_launcher_says_so_and_starts_none(tmp_path):
    env = {
        **os.environ,
        "FICHERO_RUN_MODULE": "fichero_mcp.server",
        "FICHERO_API_URL": f"http://127.0.0.1:{_closed_port()}",
        "FICHERO_API_KEY": "",
        "HOME": str(tmp_path),
        "PYTHONPATH": os.pathsep.join(str(REPO / p) for p in ("fichero-mcp/src", "fichero-cli/src", "fichero-server/src")),
    }
    run = subprocess.run(
        [sys.executable, "-m", "fichero_server"], env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=60, cwd=tmp_path,
    )
    said = run.stderr
    assert "No Fichero engine is running" in said, said[-600:]
    assert "open Fichero" in said.lower() or "Open Fichero" in said
    # It attached or gave up: it never bound a server of its own.
    assert "Uvicorn running" not in said and "Application startup complete" not in said
