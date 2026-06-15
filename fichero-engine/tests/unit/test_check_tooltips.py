"""Unit tests for scripts/check_tooltips.py (#1953)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_tooltips.py"
_SPEC = importlib.util.spec_from_file_location("check_tooltips", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan
is_toolbar_surface = _mod.is_toolbar_surface
code_lines = _mod.code_lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Toolbar surface detection
# ---------------------------------------------------------------------------

def test_toolbar_surface_by_filename(tmp_path):
    path = tmp_path / "MainToolbar.swift"
    assert is_toolbar_surface(path, "")


def test_toolbar_surface_by_content(tmp_path):
    path = tmp_path / "SomeView.swift"
    assert is_toolbar_surface(path, ".toolbar { ToolbarItem { } }")


def test_non_toolbar_file_ignored(tmp_path):
    path = tmp_path / "DocumentView.swift"
    assert not is_toolbar_surface(path, 'Text("hello")')


# ---------------------------------------------------------------------------
# Icon-only button without .help() — should be flagged
# ---------------------------------------------------------------------------

def test_flags_icon_only_button_missing_help(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button(action: doSomething) {
        Image(systemName: "plus")
    }
}
""")
    found = scan(tmp_path)
    assert found, "icon-only button without .help() should be flagged"


def test_does_not_flag_button_with_help(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button(action: doSomething) {
        Image(systemName: "plus")
    }
    .help("Add document")
}
""")
    found = scan(tmp_path)
    assert not found, "button with .help() should not be flagged"


def test_does_not_flag_text_labeled_button(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button("Add") {
        doSomething()
    }
}
""")
    found = scan(tmp_path)
    assert not found, "text-labeled button needs no .help() tooltip"


def test_does_not_flag_label_button_without_icon_only_style(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button(action: doSomething) {
        Label("Share", systemImage: "square.and.arrow.up")
    }
}
""")
    found = scan(tmp_path)
    assert not found, "Label button (shows text+icon) does not need .help()"


def test_flags_icon_only_label_button(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button(action: doSomething) {
        Label("Share", systemImage: "square.and.arrow.up")
    }
    .labelStyle(.iconOnly)
}
""")
    found = scan(tmp_path)
    assert found, "Label with .labelStyle(.iconOnly) and no .help() should be flagged"


# ---------------------------------------------------------------------------
# Preview blocks must be stripped before scanning
# ---------------------------------------------------------------------------

def test_does_not_flag_buttons_inside_preview_blocks(tmp_path):
    _write(tmp_path, "T.swift", """\
.toolbar {
    Button(action: go) {
        Image(systemName: "play")
    }
    .help("Run")
}

#Preview {
    Button(action: {}) {
        Image(systemName: "nosuchicon")
    }
}
""")
    found = scan(tmp_path)
    assert not found, "buttons inside #Preview blocks must be ignored"


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

def test_repo_swift_views_have_no_new_tooltip_violations():
    """The real SwiftUI views must have no unallowlisted tooltip violations."""
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New icon-only toolbar controls missing .help() found (add to "
        "KNOWN_VIOLATIONS or fix the source):\n"
        + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


def test_tooltip_known_violations_are_not_stale():
    """Every KNOWN_VIOLATIONS entry must still appear in the real scan."""
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (tooltip fixed — remove them): {stale}"
    )
