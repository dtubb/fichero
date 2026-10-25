"""The Mach-O sweep behind the MAS signing phase sees every binary, even under xcodebuild's huge environment (#6132).

The 2026.10.24 Mac TestFlight archive failed ITMS-90296: the embed phase signed 8 of ~871 Mach-Os because its
`find -exec file {} +` overflowed the argument list under the inherited environment, with the errors hidden.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
LIST = ROOT / "scripts" / "list_machos.sh"
SWEEPS = ["resign_engine_in_archive.sh", "validate_mas_bundle.sh", "clean-embedded-engine.sh", "build-release-dmg.sh"]


def _tree(tmp_path: Path) -> Path:
    engine = tmp_path / "Fichero Server.app"
    deep = engine / "Contents/Resources/app_packages/torch/bin"
    deep.mkdir(parents=True)
    shutil.copy("/usr/bin/true", deep / "protoc")  # an executable nobody thought to look for
    lib = engine / "Contents/Resources/app_packages/torch/lib"
    lib.mkdir(parents=True)
    shutil.copy("/usr/bin/true", lib / "libtorch.dylib")
    for i in range(300):
        (engine / f"Contents/Resources/readme{i}: note.txt").write_text("not a binary")
    return engine


def _run(engine: Path, *args: str, big_env: int = 0) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin"}
    if big_env:
        env["FICHERO_PADDING"] = "x" * big_env
    return subprocess.run(["bash", str(LIST), str(engine), *args], env=env, capture_output=True, text=True)


@pytest.mark.skipif(not Path("/usr/bin/file").exists() or not Path("/usr/bin/true").exists(), reason="needs file(1)")
def test_lists_a_deep_executable_under_a_large_environment(tmp_path):
    engine = _tree(tmp_path)
    got = _run(engine, big_env=200_000)
    assert got.returncode == 0, got.stderr
    lines = got.stdout.splitlines()
    assert str(engine / "Contents/Resources/app_packages/torch/bin/protoc") in lines
    assert str(engine / "Contents/Resources/app_packages/torch/lib/libtorch.dylib") in lines
    execs = _run(engine, "--executables", big_env=200_000).stdout.splitlines()
    assert str(engine / "Contents/Resources/app_packages/torch/bin/protoc") in execs


@pytest.mark.skipif(not Path("/usr/bin/file").exists(), reason="needs file(1)")
def test_a_dylib_that_is_not_a_macho_fails_the_sweep(tmp_path):
    engine = tmp_path / "e"
    engine.mkdir()
    (engine / "libfake.dylib").write_text("not a binary")
    got = _run(engine)
    assert got.returncode != 0
    assert "holds 1 .so/.dylib" in got.stderr


@pytest.mark.parametrize("script", SWEEPS)
def test_no_signing_sweep_uses_the_batched_exec_that_overflowed(script):
    assert "-exec file {} +" not in (ROOT / "scripts" / script).read_text(), script
    assert "list_machos.sh" in (ROOT / "scripts" / script).read_text(), script


def test_the_embed_phases_use_the_same_sweep():
    pbx = (ROOT / "fichero/fichero.xcodeproj/project.pbxproj").read_text()
    assert "-exec file {} +" not in pbx
    assert pbx.count("scripts/list_machos.sh") >= 2
