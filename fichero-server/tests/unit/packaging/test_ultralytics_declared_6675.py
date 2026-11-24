"""Ultralytics is a declared engine dependency, in the lock, at the pin the bundle installs (#6675, #5525).

Spec: docs/contributor_manual/specs/ai/local-runtimes.md (`runtime.yolo.imports-wherever-the-engine-runs`). Before this,
only the bundle step (`[tool.fichero.mlx_bundle]`) installed it, so an environment made from the lock alone lacked it.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

SERVER_ROOT = Path(__file__).resolve().parents[3]


def _pyproject() -> dict:
    return tomllib.loads((SERVER_ROOT / "pyproject.toml").read_text())


def _bundle_pin() -> str:
    pins = [Requirement(p) for p in _pyproject()["tool"]["fichero"]["mlx_bundle"]["no_deps_packages"]]
    (pin,) = [str(r.specifier) for r in pins if r.name == "ultralytics"]
    return pin


def _lock_packages() -> dict[str, dict]:
    lock = tomllib.loads((SERVER_ROOT / "uv.lock").read_text())
    return {p["name"]: p for p in lock["package"]}


def test_ultralytics_is_a_project_dependency_floored_at_the_bundle_pin():
    # A floor, never `==` (tests/unit/test_dependency_floors.py); the lock test below holds the exact version.
    declared = [Requirement(d) for d in _pyproject()["project"]["dependencies"]]
    found = [str(r.specifier) for r in declared if r.name == "ultralytics"]
    assert found == [_bundle_pin().replace("==", ">=")]


def test_the_lock_holds_ultralytics_at_the_bundle_pin():
    packages = _lock_packages()
    assert "ultralytics" in packages, "uv.lock has no ultralytics: run `uv lock` in fichero-server"
    assert f"=={packages['ultralytics']['version']}" == _bundle_pin()
    engine_deps = {d["name"] for d in packages["fichero-server"]["dependencies"]}
    assert "ultralytics" in engine_deps


def test_the_lock_keeps_one_cv2_and_no_linux_gpu_package():
    # Ultralytics declares opencv-python (a second cv2 beside the engine's headless build) and nvidia-ml-py (Linux GPUs):
    # the bundle installs it --no-deps for that reason, and the lock leaves both out the same way.
    packages = _lock_packages()
    assert "ultralytics" in packages, "uv.lock has no ultralytics: run `uv lock` in fichero-server"
    ultralytics_deps = {d["name"] for d in packages["ultralytics"].get("dependencies", [])}
    assert not ultralytics_deps & {"opencv-python", "nvidia-ml-py"}
    assert "opencv-python" not in packages
    assert "nvidia-ml-py" not in packages
    assert "opencv-python-headless" in packages


def test_the_locked_torchvision_is_the_one_the_kraken_step_installs():
    # Ultralytics brings torchvision into the lock; the Kraken step pins it --no-deps to match torch, and a second
    # version in the lock would make that step fail in an environment made from the lock (scripts/setup_venv.sh).
    pins = [Requirement(p) for p in _pyproject()["tool"]["fichero"]["kraken_bundle"]["no_deps_packages"]]
    (pin,) = [str(r.specifier) for r in pins if r.name == "torchvision"]
    assert f"=={_lock_packages()['torchvision']['version']}" == pin
