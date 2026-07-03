from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_python_module_help_imports_cleanly():
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}:{existing}" if existing else str(src)

    result = subprocess.run(
        [sys.executable, "-m", "fichero", "--help"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Fichero CLI" in result.stdout
