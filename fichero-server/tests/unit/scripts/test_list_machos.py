"""The Mach-O sweep behind the MAS signing phase sees every binary, even when file(1) echoes bytes that are not UTF-8 (#6132).

The 2026.10.24 Mac TestFlight archive failed ITMS-90296: the embed phase signed 8 of ~871 Mach-Os. Its awk had no
LC_ALL=C and died in a UTF-8 locale ("towc: multibyte conversion failure", record 2360) on bytes file(1) echoed that
are not valid UTF-8, so only the records before it were listed (retry2.log, lines 38820-38826).
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
    return subprocess.run(["bash", str(LIST), str(engine), *args], env=env, capture_output=True, text=True, errors="replace")


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


OLD_PIPELINE = (
    'find "$1" -type f -exec file {} + 2>/dev/null | awk -F": " \'/Mach-O/ && !/for architecture/ {print $1}\' | sort -u'
)


def _with_a_file_that_echoes_bad_bytes(tmp_path: Path) -> dict[str, str]:
    """`file` first prints a record that is not valid UTF-8 (as it did at record 2360 of the engine), then the real ones."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "file").write_text('#!/bin/bash\nprintf "junk\\xe5\\x8a: data\\n"\nexec /usr/bin/file "$@"\n')
    (stub / "file").chmod(0o755)
    return {"PATH": f"{stub}:/usr/bin:/bin", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}


@pytest.mark.skipif(not Path("/usr/bin/file").exists() or not Path("/usr/bin/true").exists(), reason="needs file(1)")
def test_the_old_awk_pipeline_loses_the_list_to_a_non_utf8_record_and_the_helper_does_not(tmp_path):
    engine = _tree(tmp_path)
    protoc = str(engine / "Contents/Resources/app_packages/torch/bin/protoc")
    env = _with_a_file_that_echoes_bad_bytes(tmp_path)

    old = subprocess.run(["bash", "-c", OLD_PIPELINE, "_", str(engine)], env=env, capture_output=True, text=True, errors="replace")
    assert protoc not in old.stdout.splitlines(), "the old pipeline lost the executable: this is the 8-of-871 bug"
    assert "towc" in old.stderr or old.stdout == ""

    new = subprocess.run(["bash", str(LIST), str(engine)], env=env, capture_output=True, text=True, errors="replace")
    assert new.returncode == 0, new.stderr
    assert protoc in new.stdout.splitlines()
