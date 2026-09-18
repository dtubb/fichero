"""Pins `ui-testing.preview-coverage-gate` (spec: ui-testing-strategy): a SwiftUI file
declaring a `View` with no `#Preview` is flagged; one with a `#Preview` is not; a
`ViewModifier`/plain-helper file is never required to have one.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
import check_preview_coverage  # noqa: E402


def test_view_without_preview_is_flagged(tmp_path):
    (tmp_path / "NoPreview.swift").write_text(
        "struct NoPreview: View {\n    var body: some View { Text(\"hi\") }\n}\n"
    )
    missing = check_preview_coverage.scan(tmp_path)
    assert "NoPreview.swift" in missing


def test_view_with_preview_is_not_flagged(tmp_path):
    (tmp_path / "HasPreview.swift").write_text(
        "struct HasPreview: View {\n"
        "    var body: some View { Text(\"hi\") }\n"
        "}\n\n"
        "#Preview {\n    HasPreview()\n}\n"
    )
    missing = check_preview_coverage.scan(tmp_path)
    assert "HasPreview.swift" not in missing


def test_non_view_struct_is_never_required_to_have_a_preview(tmp_path):
    (tmp_path / "PlainModifier.swift").write_text(
        "struct PlainModifier: ViewModifier {\n"
        "    func body(content: Content) -> some View { content }\n"
        "}\n"
    )
    missing = check_preview_coverage.scan(tmp_path)
    assert missing == {}
