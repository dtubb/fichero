"""check_engine_imports_bundled.py (#6658 #6659): no staged bundle is a `not run:` row, never a crash or a pass in silence."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_engine_imports_bundled.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120)


def test_an_absent_bundle_is_a_not_run_row(tmp_path):
    result = _run(str(tmp_path / "no-such-app_packages"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("not run: check_engine_imports_bundled")


def test_no_argument_is_still_a_usage_error():
    assert _run().returncode == 2


def test_an_empty_bundle_still_fails_naming_the_missing_modules(tmp_path):
    result = _run(str(tmp_path))
    assert result.returncode == 1
    assert "the engine imports modules the app does not bundle" in result.stderr
