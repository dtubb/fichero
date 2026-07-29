"""Unit tests for scripts/check_localization.py (#2287)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_localization.py"
_SPEC = importlib.util.spec_from_file_location("check_localization", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _w(tmp_path: Path, body: str) -> Path:
    (tmp_path / "V.swift").write_text(body)
    return tmp_path


def test_flags_verbatim_prose(tmp_path):
    assert scan(_w(tmp_path, 'Text(verbatim: "Delete project")\n')), "prose verbatim must flag"


def test_allows_localizable_text(tmp_path):
    # Plain Text is LocalizedStringKey-backed -> not a hard-coded escape.
    assert not scan(_w(tmp_path, 'Text("Delete project")\n'))


def test_allows_verbatim_data(tmp_path):
    # A filename / token is legitimate verbatim data, not prose.
    assert not scan(_w(tmp_path, 'Text(verbatim: fileName)\nText(verbatim: "report.pdf")\n'))


def test_allow_comment_escape(tmp_path):
    body = 'Text(verbatim: "Fichero Server")  // localization:allow brand name\n'
    assert not scan(_w(tmp_path, body))


def test_real_tree_clean():
    assert not scan(), "SwiftUI surface must hold a clean zero verbatim-prose baseline"
