"""Unit tests for scripts/check_xcode_config_invariants.py.

spec: xcode-build-configs

Proves the guardrail (a) passes on the real project and (b) actually CATCHES each drift it
claims to — a detector that can't see the bad case is worse than none (the transport-harness
lesson). Drift cases mutate a copy of the real pbxproj so the block structure stays realistic.
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
def test_real_project_is_clean():
    assert _mod.check() == [], "the real project should satisfy every config invariant"


@pytest.mark.build_config
def test_debug_sandbox_flip_is_caught(tmp_path):
    pbx = _real_pbx()
    body = _mod._app_config_block(pbx, "Debug")
    assert body is not None
    mutated = pbx.replace(body, body.replace("ENABLE_APP_SANDBOX = NO;", "ENABLE_APP_SANDBOX = YES;"))
    problems = _run_against(tmp_path, mutated)
    assert any("Debug" in p and "ENABLE_APP_SANDBOX" in p for p in problems)


@pytest.mark.build_config
def test_missing_excluded_archs_is_caught(tmp_path):
    pbx = _real_pbx().replace("EXCLUDED_ARCHS = x86_64", "EXCLUDED_ARCHS = ")
    problems = _run_against(tmp_path, pbx)
    assert any("EXCLUDED_ARCHS" in p for p in problems)


@pytest.mark.build_config
def test_wrong_deployment_floor_is_caught(tmp_path):
    pbx = _real_pbx().replace("MACOSX_DEPLOYMENT_TARGET = 26.0", "MACOSX_DEPLOYMENT_TARGET = 25.0")
    problems = _run_against(tmp_path, pbx)
    assert any("DEPLOYMENT_TARGET" in p or "macOS 26" in p for p in problems)


@pytest.mark.build_config
def test_missing_mainactor_isolation_is_caught(tmp_path):
    pbx = _real_pbx().replace("SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor", "SWIFT_DEFAULT_ACTOR_ISOLATION = nonisolated")
    problems = _run_against(tmp_path, pbx)
    assert any("ACTOR_ISOLATION" in p or "MainActor" in p for p in problems)


@pytest.mark.build_config
def test_mainactor_dropped_from_ficherotests_only_is_caught(tmp_path):
    """The scoping win: dropping the isolation from FicheroTests' OWN config blocks
    is caught even though the setting still appears elsewhere in the file (e.g. on
    FicheroUITests). A whole-file substring check would miss this exact drift — the
    one that causes the ~575 off-main SIGTRAPs — because the string is still present.
    """
    pbx = _real_pbx()
    blocks = _mod._config_blocks_for_product(pbx, "FicheroTests")
    assert blocks, "fixture precondition: FicheroTests config blocks must exist"
    for _cfg, body in blocks:
        neutered = body.replace(
            "SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor;",
            "SWIFT_DEFAULT_ACTOR_ISOLATION = nonisolated;",
        )
        pbx = pbx.replace(body, neutered)
    # Precondition: the string still exists elsewhere (so a substring check would pass).
    assert "SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor" in pbx
    problems = _run_against(tmp_path, pbx)
    assert any("FicheroTests" in p and "ACTOR_ISOLATION" in p for p in problems), problems
