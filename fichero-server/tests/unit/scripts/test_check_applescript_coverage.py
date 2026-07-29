"""Unit tests for scripts/check_applescript_coverage.py (#2286)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_applescript_coverage.py"
_SPEC = importlib.util.spec_from_file_location("check_applescript_coverage", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

violations = _mod.violations


def _setup(tmp_path: Path, sdef_body: str, swift_body: str):
    sdef = tmp_path / "Fichero.sdef"
    sdef.write_text(sdef_body)
    (tmp_path / "Commands.swift").write_text(swift_body)
    return sdef, tmp_path


def test_clean_when_matched(tmp_path):
    sdef, app = _setup(
        tmp_path,
        '<command><cocoa class="FicheroRunWorkflowCommand"/></command>',
        "class FicheroRunWorkflowCommand: NSScriptCommand { }\n",
    )
    assert not violations(sdef=sdef, app_dir=app)


def test_flags_sdef_class_without_swift(tmp_path):
    sdef, app = _setup(
        tmp_path,
        '<command><cocoa class="FicheroGhostCommand"/></command>',
        "class FicheroRunWorkflowCommand: NSScriptCommand { }\n",
    )
    bad = violations(sdef=sdef, app_dir=app)
    assert any("FicheroGhostCommand" in k for k in bad), "sdef class with no Swift must be flagged"


def test_flags_swift_command_not_in_sdef(tmp_path):
    sdef, app = _setup(
        tmp_path,
        "<dictionary></dictionary>",
        "class FicheroImportFileCommand: NSScriptCommand { }\n",
    )
    bad = violations(sdef=sdef, app_dir=app)
    assert any("FicheroImportFileCommand" in k for k in bad), "unadvertised command must be flagged"


def test_object_class_advertised_and_defined(tmp_path):
    # A scriptable object class (NSObject, not a command) must still resolve.
    sdef, app = _setup(
        tmp_path,
        '<class><cocoa class="FicheroScriptDocument"/></class>',
        "class FicheroScriptDocument: NSObject { }\n",
    )
    assert not violations(sdef=sdef, app_dir=app)


def test_real_tree_clean():
    assert not violations(), "shipped .sdef and Swift must be in lock-step"
