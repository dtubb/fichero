"""Unit tests for scripts/check_accessibility.py (#2285)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_accessibility.py"
_SPEC = importlib.util.spec_from_file_location("check_accessibility", _SCRIPT)
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


def test_flags_icon_only_button(tmp_path):
    _write(tmp_path, "T.swift", """\
Button(action: send) {
    Image(systemName: "arrow.up")
}
""")
    assert scan(tmp_path), "icon-only button without accessibilityLabel should be flagged"


def test_accepts_accessibility_label(tmp_path):
    _write(tmp_path, "T.swift", """\
Button(action: send) {
    Image(systemName: "arrow.up")
}
.accessibilityLabel("Send")
""")
    assert not scan(tmp_path), "labeled button must not be flagged"


def test_accepts_text_labeled_button(tmp_path):
    _write(tmp_path, "T.swift", 'Button("Send") { send() }\n')
    assert not scan(tmp_path)


def test_accepts_label_with_text(tmp_path):
    _write(tmp_path, "T.swift", """\
Button(action: share) {
    Label("Share", systemImage: "square.and.arrow.up")
}
""")
    assert not scan(tmp_path), "Label shows text -> announced -> not flagged"


def test_flags_icon_only_label_style(tmp_path):
    _write(tmp_path, "T.swift", """\
Button(action: share) {
    Label("Share", systemImage: "square.and.arrow.up")
}
.labelStyle(.iconOnly)
""")
    assert scan(tmp_path), "iconOnly label hides text -> needs accessibilityLabel"


def test_ignores_preview_blocks(tmp_path):
    _write(tmp_path, "T.swift", """\
Button(action: go) { Image(systemName: "play") }.accessibilityLabel("Go")

#Preview {
    Button(action: {}) { Image(systemName: "x") }
}
""")
    assert not scan(tmp_path), "buttons inside #Preview must be ignored"
