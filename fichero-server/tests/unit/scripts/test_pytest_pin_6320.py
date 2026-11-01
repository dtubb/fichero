"""The gate's pytest pin refuses only a pytest that fails the suite (9.2.0) or a venv missing pytest-asyncio, and every pytest the gate runs
goes through it (#6320). 9.0.3 is on the Air and runs the suite; refusing it made `gate engine` unusable there."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PIN = ROOT / "scripts" / "check_pytest_pin.sh"


def _fake_python(tmp_path: Path, pytest_version: str | None, asyncio: bool = True) -> str:
    """A `python` that answers the two imports the pin makes."""
    script = tmp_path / "python"
    script.write_text(
        "#!/bin/bash\n"
        f'case "$2" in\n  *pytest.__version__*) {"echo " + pytest_version if pytest_version else "exit 1"} ;;\n'
        f'  *pytest_asyncio*) exit {0 if asyncio else 1} ;;\nesac\n')
    script.chmod(0o755)
    return str(script)


def _pin(py: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(PIN), py], capture_output=True, text=True, env={**os.environ, "GATE_ALLOW_PYTEST": "", **env})


def test_a_pytest_that_runs_the_suite_passes_whatever_its_patch(tmp_path):
    for version in ("9.0.3", "9.1.1"):
        assert _pin(_fake_python(tmp_path, version)).returncode == 0, version


def test_9_2_0_is_refused_with_the_line_to_fix_it(tmp_path):
    got = _pin(_fake_python(tmp_path, "9.2.0"))
    assert got.returncode == 2 and "9.1.1" in got.stderr and "GATE_ALLOW_PYTEST" in got.stderr


def test_a_venv_without_pytest_asyncio_or_pytest_is_refused(tmp_path):
    assert _pin(_fake_python(tmp_path, "9.1.1", asyncio=False)).returncode == 2
    assert _pin(_fake_python(tmp_path, None)).returncode == 2


def test_the_override_runs_anyway(tmp_path):
    assert _pin(_fake_python(tmp_path, "9.2.0"), GATE_ALLOW_PYTEST="1").returncode == 0


def test_the_gate_engine_and_perf_legs_and_the_m4_script_all_ask_it_and_fail_the_leg_not_the_process():
    gate = (ROOT / "scripts" / "gate").read_text()
    assert gate.count("check_pytest_pin.sh") >= 2 and "|| return 2" in gate
    assert "check_pytest_pin.sh" in (ROOT / "scripts" / "m4_suite_by_dir.sh").read_text()
    assert "die \"pytest is" not in gate  # `die` is `exit 2` inside run_leg: verify-all ended with no summary table
