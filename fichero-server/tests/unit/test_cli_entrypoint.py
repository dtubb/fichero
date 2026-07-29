from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _cli_env(root: Path) -> dict[str, str]:
    # #4227: the CLI lives in the sibling fichero-cli/ product; the server
    # models it imports stay in this tree, so the subprocess needs both.
    src = root / "src"
    cli_src = root.parent / "fichero-cli" / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    parts = [str(cli_src), str(src)] + ([existing] if existing else [])
    env["PYTHONPATH"] = ":".join(parts)
    return env


def test_python_module_help_imports_cleanly():
    root = Path(__file__).resolve().parents[2]
    env = _cli_env(root)

    result = subprocess.run(
        [sys.executable, "-m", "fichero_cli", "--help"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        # `-m fichero_cli --help` cold-imports the whole app (FastAPI/langchain/duckdb/…);
        # it runs ~4-6s solo but can spike under a fully-parallel suite. 30s was flaky
        # under load; 120s stays load-safe while still catching a genuine import hang.
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "Fichero CLI" in result.stdout
    # CLI surface must include the #3860 device-enrollment + user-management groups.
    assert "pair" in result.stdout
    assert "users" in result.stdout


def test_python_module_entity_help_imports_cleanly():
    root = Path(__file__).resolve().parents[2]
    env = _cli_env(root)

    result = subprocess.run(
        [sys.executable, "-m", "fichero_cli", "entity", "--help"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,  # load-safe: heavy cold import, flaky at 30s under a parallel suite
    )

    assert result.returncode == 0, result.stderr
    assert "Inspect and curate knowledge entities." in result.stdout
