from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_action_surface_matrix.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("check_action_surface_matrix", _SCRIPT)
assert _SPEC and _SPEC.loader
check_action_surface_matrix = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_action_surface_matrix
_SPEC.loader.exec_module(check_action_surface_matrix)  # type: ignore[attr-defined]


def test_show_ruler_has_menu_and_keyboard_surfaces():
    rows = {row.action: row for row in check_action_surface_matrix.scan()}
    row = rows["Show Ruler"]

    assert row.menu is True
    assert row.keyboard is True
    assert row.missing == ()
