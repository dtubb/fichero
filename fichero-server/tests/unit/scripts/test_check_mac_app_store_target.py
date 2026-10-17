"""The Mac App Store guard checks an `App Store` CONFIGURATION of the one Fichero target (#5730).

spec: xcode-build-configs: config.mas-is-a-configuration
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_mac_app_store_target.py"
_SPEC = importlib.util.spec_from_file_location("check_mac_app_store_target", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _run_against(tmp_path: Path, pbx_text: str) -> list[str]:
    mutated = tmp_path / "project.pbxproj"
    mutated.write_text(pbx_text, encoding="utf-8")
    original = _mod.PROJ
    _mod.PROJ = mutated
    try:
        return _mod.check()
    finally:
        _mod.PROJ = original


@pytest.mark.build_config
def test_the_guard_does_not_ask_for_a_second_target():
    problems = _mod.check()
    assert not any("is missing from project.pbxproj" in p for p in problems)


@pytest.mark.build_config
def test_a_project_without_an_app_store_configuration_is_caught(tmp_path):
    pbx = _mod.PROJ.read_text(encoding="utf-8")
    problems = _run_against(tmp_path, pbx)
    assert any("no 'App Store' build configuration" in p for p in problems)


@pytest.mark.build_config
def test_the_real_project_has_an_app_store_configuration():
    # [GAP] #5730: red until the maintainer adds the configuration in Xcode.
    assert not any("no 'App Store' build configuration" in p for p in _mod.check())
