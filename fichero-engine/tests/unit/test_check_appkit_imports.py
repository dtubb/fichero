"""Unit tests for scripts/check_appkit_imports.py (§6b guardrail suite)."""
from __future__ import annotations

import importlib.util
import sys
import pytest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_appkit_imports.py"
_SPEC = importlib.util.spec_from_file_location("check_appkit_imports", _SCRIPT)
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


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_flags_appkit_import(tmp_path):
    _write(tmp_path, "A.swift", "import SwiftUI\nimport AppKit\n")
    found = scan(tmp_path)
    assert "A.swift" in found


def test_flags_uikit_import(tmp_path):
    _write(tmp_path, "B.swift", "import UIKit\n")
    found = scan(tmp_path)
    assert "B.swift" in found


def test_pure_swiftui_not_flagged(tmp_path):
    _write(tmp_path, "C.swift", "import SwiftUI\nstruct V: View { var body: some View { Text(\"hi\") } }\n")
    found = scan(tmp_path)
    assert "C.swift" not in found


def test_appkit_in_comment_not_flagged(tmp_path):
    _write(tmp_path, "D.swift", "// import AppKit  (historical note)\nimport SwiftUI\n")
    found = scan(tmp_path)
    assert "D.swift" not in found


def test_block_comment_appkit_not_flagged(tmp_path):
    _write(tmp_path, "E.swift", "/*\nimport AppKit\n*/\nimport SwiftUI\n")
    found = scan(tmp_path)
    assert "E.swift" not in found


def test_substring_import_not_flagged(tmp_path):
    # `import AppKitShim` must not match `AppKit` due to the word boundary.
    _write(tmp_path, "F.swift", "import AppKitShim\n")
    found = scan(tmp_path)
    assert "F.swift" not in found


def test_preview_named_file_still_scanned(tmp_path):
    # A real view whose name contains "Preview" must NOT be skipped.
    _write(tmp_path, "QuickLookPreviewViews.swift", "import AppKit\n")
    found = scan(tmp_path)
    assert "QuickLookPreviewViews.swift" in found


def test_appkit_audit_doc_covers_every_known_importer():
    audit = (_SCRIPT.parents[1] / _mod.RULE_DOC).read_text(encoding="utf-8")
    missing = [
        path for path in _mod.KNOWN_VIOLATIONS
        if f"`{path}`" not in audit
    ]
    assert not missing


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="#2713: real new AppKit/UIKit importers; guardrail correctly red until migrated/justified (see #2101)", strict=False)
def test_repo_appkit_importers_have_no_new_violations():
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New AppKit/UIKit importer(s) found (add to KNOWN_VIOLATIONS or migrate "
        "to cross-platform SwiftUI):\n" + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


@pytest.mark.xfail(reason="#2713: stale AppKit allowlist entries; refresh tracked in issue", strict=False)
def test_appkit_known_violations_are_not_stale():
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (file no longer imports AppKit/UIKit — "
        f"remove them): {stale}"
    )
