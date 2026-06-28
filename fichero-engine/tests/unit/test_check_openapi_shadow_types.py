"""Unit tests for scripts/check_openapi_shadow_types.py (§6b guardrail suite)."""
from __future__ import annotations

import importlib.util
import json
import sys
import pytest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_openapi_shadow_types.py"
_SPEC = importlib.util.spec_from_file_location("check_openapi_shadow_types", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _contract(tmp_path: Path, names: list[str]) -> Path:
    c = tmp_path / "openapi.json"
    c.write_text(json.dumps({"components": {"schemas": {n: {} for n in names}}}))
    return c


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_flags_struct_shadowing_schema(tmp_path):
    swift = tmp_path / "swift"
    _write(swift, "Models/M.swift", "struct Document { let id: String }\n")
    found = scan(swift, _contract(tmp_path, ["Document"]))
    assert "Models/M.swift::Document" in found


def test_flags_enum_shadowing_schema(tmp_path):
    swift = tmp_path / "swift"
    _write(swift, "Models/M.swift", "public enum DocType: String { case pdf }\n")
    found = scan(swift, _contract(tmp_path, ["DocType"]))
    assert "Models/M.swift::DocType" in found


def test_non_shadow_type_not_flagged(tmp_path):
    swift = tmp_path / "swift"
    _write(swift, "Models/M.swift", "struct LocalOnlyViewModel { let x: Int }\n")
    found = scan(swift, _contract(tmp_path, ["Document"]))
    assert not found


def test_shadow_in_comment_not_flagged(tmp_path):
    swift = tmp_path / "swift"
    _write(swift, "Models/M.swift", "// struct Document { }  (was here once)\n")
    found = scan(swift, _contract(tmp_path, ["Document"]))
    assert not found


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="#2712: real Swift OpenAPI shadow-type drift (SpatialModels.swift); guardrail correctly red until fixed", strict=False)
def test_repo_has_no_new_shadow_types():
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New manual type(s) shadowing a generated Components.Schemas.* (consume "
        "the generated type, or add to KNOWN_VIOLATIONS):\n"
        + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


@pytest.mark.xfail(reason="#2712: stale shadow-type allowlist entries; refresh tracked in issue", strict=False)
def test_shadow_known_violations_are_not_stale():
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (shadow removed — drop them): {stale}"
    )
