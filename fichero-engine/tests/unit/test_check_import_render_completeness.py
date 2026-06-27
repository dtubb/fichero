"""Unit tests for scripts/check_import_render_completeness.py (#2270)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "check_import_render_completeness.py"
)
_SPEC = importlib.util.spec_from_file_location("check_import_render_completeness", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

violations = _mod.violations
_py = _mod._python_enum_cases
_sw = _mod._swift_enum_cases

_PY = """
class FileType(str, Enum):
    image = "image"
    pdf = "pdf"
    weird = "weird"
"""
_SWIFT = """
enum FileType: String, Codable, CaseIterable {
    case image
    case pdf
    case extra

    var icon: String { "" }
}
"""


def test_parses_python_cases():
    assert _py(_PY, "FileType") == {"image", "pdf", "weird"}


def test_parses_swift_cases():
    assert _sw(_SWIFT, "FileType") == {"image", "pdf", "extra"}


def test_flags_python_only_case(tmp_path):
    py = tmp_path / "models.py"
    py.write_text(_PY)
    sw = tmp_path / "Document.swift"
    sw.write_text(_SWIFT)
    bad = violations(py_models=py, swift_models=sw)
    assert "FileType.weird" in bad, "importable type with no Swift case must be flagged"
    # Swift-only `extra` is NOT a violation (client may render more than imported).
    assert "FileType.extra" not in bad


def test_real_tree_only_seeded_drift():
    # The shipped tree must have no UNSEEDED import/render gaps.
    bad = set(violations())
    known = set(_mod.KNOWN_VIOLATIONS)
    assert bad <= known, f"unseeded import/render gaps: {bad - known}"
