"""The MLX bundle step installs what the lock also knows at the lock's versions (#6675).

Ultralytics is in uv.lock now, and with it matplotlib, polars, psutil and torchvision; the MLX step installs those into
the bundle, and `bundle_matches_lock.py` fails the build on a version the lock does not hold. The step is given the
lock's exported constraints (`build/lock-constraints.txt`) and adds them to every pip call.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import install_mlx_into_engine_bundle as mlx  # noqa: E402


def _bundle(tmp_path: Path) -> Path:
    packages = tmp_path / "app_packages"
    info = packages / "numpy-2.5.2.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Name: numpy\nVersion: 2.5.2\n")
    return packages


def _record(monkeypatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(mlx, "_bundle_python_version", lambda _p: sys.version_info[:2])

    def pip(packages: Path, _args, *, constraints: Path) -> None:
        seen.append(constraints.read_text())
        for name in mlx.NEEDED:  # what a real install leaves, so the step's own after-check passes
            info = packages / f"{name}-1.0.dist-info"
            info.mkdir(exist_ok=True)
            (info / "METADATA").write_text(f"Name: {name}\nVersion: 1.0\n")

    monkeypatch.setattr(mlx, "_run_pip", pip)
    monkeypatch.setattr(mlx, "_table", lambda: {"missing_packages": ["matplotlib>=3.3.0"],
                                                "no_deps_packages": ["ultralytics==8.4.175"]})
    return seen


def test_every_pip_call_carries_the_lock_constraints(tmp_path, monkeypatch):
    seen = _record(monkeypatch)
    lock = tmp_path / "lock-constraints.txt"
    lock.write_text("matplotlib==3.11.2\npolars==2.1.0\n")
    assert mlx.main(["install_mlx_into_engine_bundle.py", str(_bundle(tmp_path)), str(lock)]) == 0
    assert len(seen) == 2
    for text in seen:
        assert "numpy==2.5.2" in text  # the bundle's own pins stay
        assert "matplotlib==3.11.2" in text and "polars==2.1.0" in text


def test_without_a_lock_file_only_the_bundle_pins_apply(tmp_path, monkeypatch):
    seen = _record(monkeypatch)
    assert mlx.main(["install_mlx_into_engine_bundle.py", str(_bundle(tmp_path))]) == 0
    assert seen and all("matplotlib==" not in text for text in seen)
