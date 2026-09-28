"""scripts/check_name_truncation.py: a one-line name loses its middle, never its end (2026-09-28).

The negative fixtures are the two shapes the sidebar actually had: a row name held to one line with
no truncation mode (so the end was cut: "Acceptance 202…"), and the library header's name with no
modifiers at all. Both must be caught; the fixed shapes and a two-line reading must not."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
_SPEC = importlib.util.spec_from_file_location("check_name_truncation", _SCRIPTS / "check_name_truncation.py")
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "Row.swift"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_sidebar_rows_old_shape_is_caught(tmp_path):
    path = _file(tmp_path, "Text(name)\n    .lineLimit(1)\n    .foregroundStyle(color)\n")
    assert len(_mod.violations([path])) == 1


def test_the_library_headers_old_shape_is_caught(tmp_path):
    path = _file(tmp_path, "Text(libraryName)\n    .foregroundStyle(.primary)\nlocationBadge\n")
    assert len(_mod.violations([path])) == 1


def test_a_middle_truncated_name_passes(tmp_path):
    path = _file(tmp_path, "Text(crumb.title)\n    .lineLimit(1)\n    // Finder's rule\n    .truncationMode(.middle)\n")
    assert _mod.violations([path]) == []


def test_a_name_allowed_two_lines_is_not_a_one_line_name(tmp_path):
    path = _file(tmp_path, "Text(rowTitle)\n    .lineLimit(2)\n")
    assert _mod.violations([path]) == []


def test_a_heading_that_is_not_a_name_opts_out_visibly(tmp_path):
    path = _file(tmp_path, "Text(title)\n    // not a name: a banner's heading\n    .font(.caption)\n")
    assert _mod.violations([path]) == []


def test_the_repo_is_clean():
    assert _mod.main() == 0
