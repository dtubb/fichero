"""Deployment floor: macOS 26 (Tahoe and 27 both supported), iOS 27 only.

spec: xcode-build-configs (platform.deployment-floor-26, #5730)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_xcode_config_invariants.py"
_SPEC = importlib.util.spec_from_file_location("check_xcode_config_invariants", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _real_pbx() -> str:
    return _mod.PBXPROJ.read_text(encoding="utf-8")


def _run_against(tmp_path: Path, pbx_text: str) -> list[str]:
    mutated = tmp_path / "project.pbxproj"
    mutated.write_text(pbx_text, encoding="utf-8")
    original = _mod.PBXPROJ
    _mod.PBXPROJ = mutated
    try:
        return _mod.check()
    finally:
        _mod.PBXPROJ = original


@pytest.mark.build_config
def test_real_project_floor_is_26():
    pbx = _real_pbx()
    assert "MACOSX_DEPLOYMENT_TARGET = 27" not in pbx
    assert "IPHONEOS_DEPLOYMENT_TARGET = 26" not in pbx
    assert _mod.check() == []


@pytest.mark.build_config
def test_a_mac_target_left_at_27_is_caught(tmp_path):
    pbx = _real_pbx().replace("MACOSX_DEPLOYMENT_TARGET = 26.0", "MACOSX_DEPLOYMENT_TARGET = 27.0", 1)
    assert any("MACOSX_DEPLOYMENT_TARGET floor is 26" in p for p in _run_against(tmp_path, pbx))


@pytest.mark.build_config
def test_an_ios_target_at_26_is_caught(tmp_path):
    pbx = _real_pbx().replace("IPHONEOS_DEPLOYMENT_TARGET = 27.0", "IPHONEOS_DEPLOYMENT_TARGET = 26.0", 1)
    assert any("IPHONEOS_DEPLOYMENT_TARGET floor is 27" in p for p in _run_against(tmp_path, pbx))
