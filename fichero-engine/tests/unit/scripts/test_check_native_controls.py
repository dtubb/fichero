from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_native_controls.py"
_SPEC = importlib.util.spec_from_file_location("check_native_controls", _SCRIPT)
assert _SPEC and _SPEC.loader
check_native_controls = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_native_controls
_SPEC.loader.exec_module(check_native_controls)  # type: ignore[attr-defined]


def _signature_for(rel_path: str, start_line: int) -> str:
    path = check_native_controls.VIEWS_DIR / rel_path
    lines = check_native_controls.code_lines(path.read_text(encoding="utf-8"))
    end_idx, snippet = check_native_controls._normalized_snippet(lines, start_line - 1)
    assert end_idx >= start_line - 1
    return check_native_controls._signature_key(rel_path, snippet)


def test_sanctioned_baseline_hashes_match_current_scrollview_snippets():
    expected = {
        "Components/WorkflowPreviewSheet.swift": 40,
        "Library/LibraryView+DisplayModes.swift": 218,
    }

    for rel_path, start_line in expected.items():
        signature = _signature_for(rel_path, start_line)
        assert signature in check_native_controls.KNOWN_VIOLATIONS
