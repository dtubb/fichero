"""builder.client.scripts-live-with-the-package: the harness scripts are in fichero_builder/scripts/, the old scripts/ paths are thin
wrappers with the same argv and exit code, and an install outside a checkout finds its own copy."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "fichero-builder" / "fichero_builder"
MOVED = sorted(p.name for p in (PKG / "scripts").iterdir() if p.suffix in (".py", ".sh"))
PY_ARGS = {"harness_handoff_hook.py": ["--test"]}  # the others are argparse scripts: --help


def test_every_old_path_has_a_wrapper_and_the_package_has_the_script():
    assert "harness_start.py" in MOVED and "lane_ready_check.sh" in MOVED and len(MOVED) == 9
    for name in MOVED:
        assert (ROOT / "scripts" / name).is_file() and len((ROOT / "scripts" / name).read_text().splitlines()) < 12, f"scripts/{name} is a thin wrapper"


@pytest.mark.parametrize("name", [n for n in MOVED if n.endswith(".py")])
def test_a_python_wrapper_gives_what_its_target_gives(name):
    args = PY_ARGS.get(name, ["--help"])
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "fichero-builder")}
    run = lambda p: subprocess.run([sys.executable, str(p), *args], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)  # noqa: E731
    a, b = run(ROOT / "scripts" / name), run(PKG / "scripts" / name)
    assert (a.returncode, a.stdout, a.stderr) == (b.returncode, b.stdout, b.stderr) and a.returncode == 0, a.stderr


def test_the_ready_check_wrapper_passes_argv_and_exit_code_through(tmp_path):
    run = lambda p: subprocess.run(["bash", str(p), "--no-such-flag"], cwd=tmp_path, capture_output=True, text=True)  # noqa: E731
    a, b = run(ROOT / "scripts" / "lane_ready_check.sh"), run(PKG / "scripts" / "lane_ready_check.sh")
    assert (a.returncode, a.stdout, a.stderr) == (b.returncode, b.stdout, b.stderr)


def test_the_package_finds_its_scripts_when_installed_outside_a_checkout(tmp_path):
    site = tmp_path / "site"
    shutil.copytree(PKG, site / "fichero_builder", ignore=shutil.ignore_patterns("__pycache__"))
    code = "from fichero_builder import client; print(client.scripts_dir())"
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site)})
    assert r.stdout.strip() == str(site / "fichero_builder" / "scripts"), r.stderr
    for name in MOVED:
        assert (site / "fichero_builder" / "scripts" / name).is_file()
    h = subprocess.run([sys.executable, str(site / "fichero_builder" / "scripts" / "harness_check.py"), "--help"], cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""})
    assert h.returncode == 0, h.stderr  # the script imports the copy beside it, not a checkout
