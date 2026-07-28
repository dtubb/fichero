"""Tests for the two #4201 SwiftUI crash-class guardrails.

Both check real, previously-shipped crash shapes, so each rule is tested with a
POSITIVE fixture (it fires) and the near-miss NEGATIVES it must not fire on. A
guardrail that silently matches nothing is worse than none — it reads as proof
of safety.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


isolation = _load("check_mainactor_view_statics")
stacked = _load("check_stacked_presentation_modifiers")


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# MainActor View statics — the proven whole-process kill
# ---------------------------------------------------------------------------

_VIEW_WITH_STATIC = """
struct LibraryView: View {
    static func helper(_ x: Int) -> Bool { x > 0 }
    var body: some View { Text("hi") }
}
"""

_SWIFT_TESTING_SUITE = """
struct LibraryContentStateTests {
    @Test("it works")
    func itWorks() { #expect(LibraryView.helper(1)) }
}
"""


def _isolation_scan(tmp_path: Path, view_src: str, test_src: str) -> dict:
    app = tmp_path / "app"
    tests = tmp_path / "tests"
    _write(app, "LibraryView.swift", view_src)
    _write(tests, "LibraryContentStateTests.swift", test_src)
    return isolation.scan(app, tests)


def test_flags_view_static_called_from_non_mainactor_swift_testing_suite(tmp_path):
    found = _isolation_scan(tmp_path, _VIEW_WITH_STATIC, _SWIFT_TESTING_SUITE)

    assert "LibraryView.helper" in found
    assert "LibraryContentStateTests" in found["LibraryView.helper"]


def test_nonisolated_static_is_not_flagged(tmp_path):
    """The applied fix must clear the finding, or the guardrail never goes green."""
    found = _isolation_scan(
        tmp_path,
        _VIEW_WITH_STATIC.replace("static func helper", "nonisolated static func helper"),
        _SWIFT_TESTING_SUITE,
    )

    assert found == {}


def test_mainactor_suite_is_not_flagged(tmp_path):
    """@MainActor on the suite is the other valid fix — equally clearing."""
    found = _isolation_scan(
        tmp_path,
        _VIEW_WITH_STATIC,
        "@MainActor\n" + _SWIFT_TESTING_SUITE,
    )

    assert found == {}


def test_xctest_caller_is_immune(tmp_path):
    """XCTest runs main-thread, so it cannot trip the isolation check.

    This is the filter that took the real sweep from 87 candidates to 1.
    """
    found = _isolation_scan(
        tmp_path,
        _VIEW_WITH_STATIC,
        """
        final class LibraryContentStateTests: XCTestCase {
            func testItWorks() { XCTAssertTrue(LibraryView.helper(1)) }
        }
        """,
    )

    assert found == {}


def test_non_view_type_is_not_flagged(tmp_path):
    """Only View/Scene types inherit MainActor this way."""
    found = _isolation_scan(
        tmp_path,
        "struct LibraryView: Codable {\n    static func helper(_ x: Int) -> Bool { x > 0 }\n}\n",
        _SWIFT_TESTING_SUITE,
    )

    assert found == {}


def test_transitive_same_type_statics_are_reported(tmp_path):
    """The proven case needed three sibling statics marked too; a partial fix
    does not compile, so the report has to name them."""
    found = _isolation_scan(
        tmp_path,
        """
        struct LibraryView: View {
            private static let pattern = "x"
            static func helper(_ x: Int) -> Bool { pattern.isEmpty || x > 0 }
            var body: some View { Text("hi") }
        }
        """,
        _SWIFT_TESTING_SUITE,
    )

    assert "pattern" in found["LibraryView.helper"]


# ---------------------------------------------------------------------------
# Stacked presentation modifiers
# ---------------------------------------------------------------------------


def _stacked_scan(tmp_path: Path, src: str) -> dict:
    views = tmp_path / "Views"
    _write(views, "SomeView.swift", src)
    return stacked.scan(views)


def test_flags_two_presentation_modifiers_on_one_node(tmp_path):
    found = _stacked_scan(
        tmp_path,
        """
        var body: some View {
            content
                .sheet(isPresented: $a) { A() }
                .alert("t", isPresented: $b) { B() }
        }
        """,
    )

    assert len(found) == 1
    assert "sheet+alert" in next(iter(found))


def test_flags_the_3163_duplicate_shape(tmp_path):
    """#3163 was literally the same modifier twice on one node."""
    found = _stacked_scan(
        tmp_path,
        """
        var body: some View {
            content
                .searchable(text: $a)
                .searchable(text: $b)
        }
        """,
    )

    assert "searchable+searchable" in next(iter(found))


def test_single_presentation_modifier_is_clean(tmp_path):
    found = _stacked_scan(
        tmp_path,
        """
        var body: some View {
            content
                .sheet(isPresented: $a) { A() }
                .padding()
                .foregroundStyle(.red)
        }
        """,
    )

    assert found == {}


def test_modifiers_on_separate_nodes_are_clean(tmp_path):
    """The FIX shape must not still be flagged, or nobody can go green."""
    found = _stacked_scan(
        tmp_path,
        """
        var body: some View {
            VStack {
                inner
                    .sheet(isPresented: $a) { A() }
            }
            Spacer()
            other
                .alert("t", isPresented: $b) { B() }
        }
        """,
    )

    assert found == {}


def test_flags_optional_viewbuilder_feeding_safe_area_inset(tmp_path):
    """#4189: a bare `if let` @ViewBuilder under .safeAreaInset."""
    found = _stacked_scan(
        tmp_path,
        """
        @ViewBuilder private var banner: some View {
            if let message = errorMessage {
                Text(message)
            }
        }

        var body: some View {
            content.safeAreaInset(edge: .bottom) { banner }
        }
        """,
    )

    assert any("optional-content:banner" in key for key in found), found


def test_optional_viewbuilder_with_else_is_clean(tmp_path):
    """An else branch gives it a stable concrete root — that is the fix."""
    found = _stacked_scan(
        tmp_path,
        """
        @ViewBuilder private var banner: some View {
            if let message = errorMessage {
                Text(message)
            } else {
                EmptyView()
            }
        }

        var body: some View {
            content.safeAreaInset(edge: .bottom) { banner }
        }
        """,
    )

    assert found == {}


def test_optional_viewbuilder_not_used_by_presentation_is_clean(tmp_path):
    """Plain body content re-types harmlessly; only presentation content bites."""
    found = _stacked_scan(
        tmp_path,
        """
        @ViewBuilder private var banner: some View {
            if let message = errorMessage {
                Text(message)
            }
        }

        var body: some View {
            VStack { banner }
        }
        """,
    )

    assert found == {}
