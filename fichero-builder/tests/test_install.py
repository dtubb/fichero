"""builder.client.installs-as-a-package: `pip install -e fichero-builder` in a scratch venv gives `python -m fichero_builder` and `builder`.
Slow (it builds a venv and fetches the build backend): `-m slow`, not part of the quick run."""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]


def test_the_console_script_names_a_real_entry_function_and_the_package_data_exists():
    meta = tomllib.loads((PKG / "pyproject.toml").read_text())
    mod, _, fn = meta["project"]["scripts"]["builder"].partition(":")
    assert mod == "fichero_builder.__main__" and callable(getattr(__import__(mod, fromlist=[fn]), fn))
    assert meta["project"]["dependencies"] == []
    for f in meta["tool"]["setuptools"]["package-data"]["fichero_builder"]:
        assert (PKG / "fichero_builder" / f).is_file()


def test_help_runs_from_the_folder_with_pythonpath_as_the_live_loop_runs_it():
    r = subprocess.run([sys.executable, "-m", "fichero_builder", "--help"], cwd=PKG, env={"PYTHONPATH": ".", "PATH": ""}, capture_output=True, text=True)
    assert r.returncode == 0 and "usage:" in r.stdout


@pytest.mark.slow
def test_pip_install_e_in_a_scratch_venv_gives_the_module_and_the_script(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py, builder = venv / "bin" / "python", venv / "bin" / "builder"
    r = subprocess.run([str(py), "-m", "pip", "install", "-e", str(PKG)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    other = tmp_path / "elsewhere"
    other.mkdir()
    for argv in ([str(py), "-m", "fichero_builder", "--help"], [str(builder), "--help"]):
        r = subprocess.run(argv, cwd=other, capture_output=True, text=True)
        assert r.returncode == 0 and "usage:" in r.stdout, r.stderr[-800:]
