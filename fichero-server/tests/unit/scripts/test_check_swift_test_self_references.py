"""The cheap stand-in for a typecheck nobody runs (#5093).

`BuildProject` builds the APP target and never the test bundle, so a Swift test file
can reference a helper under a name it does not have and a green 46-second build says
nothing. That happened: four call sites said `Self.makeStore()` and the helper was
`Self.storeWithMockTransport()`.

These tests pin the two halves that make the guard worth having: it FIRES on that
exact mistake, and it stays quiet on the three shapes that are not references —
a string literal a source-scanning test searches for, a doc comment quoting code, and
a URL whose `//` must not swallow the line after it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_swift_test_self_references.py"
_SPEC = importlib.util.spec_from_file_location("check_swift_test_self_references", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)


def _unresolved(source: str) -> list[str]:
    return guard.unresolved(Path("Fixture.swift"), source)


def test_it_fires_on_the_exact_mistake_that_shipped():
    """`Self.makeStore()` where the file declares `storeWithMockTransport`. If this
    stops failing, the guard has gone blind to the one error class a lane that cannot
    compile Swift will keep producing."""
    source = """
final class SegmentStoreTests: XCTestCase {
    private static func storeWithMockTransport() -> SegmentStore { fatalError() }

    func testSomething() {
        let store = Self.makeStore()
    }
}
"""
    problems = _unresolved(source)
    assert len(problems) == 1
    assert "Self.makeStore" in problems[0]


def test_a_declared_helper_is_not_reported():
    source = """
final class T: XCTestCase {
    private static func storeWithMockTransport() -> Int { 0 }
    func testA() { _ = Self.storeWithMockTransport() }
}
"""
    assert _unresolved(source) == []


def test_a_reference_inside_a_string_is_not_a_reference():
    """Several tests scan production SOURCE for a string. Those four were this
    guard's first false positives: `source.range(of: "try Self.validateResponseSize")`
    is a search, not a call."""
    source = 'func testA() { _ = source.range(of: "try Self.validateResponseSize") }'
    assert _unresolved(source) == []


def test_a_reference_quoted_in_a_doc_comment_is_not_a_reference():
    """Prose counted as code, which is the trap that has now appeared in three
    different guards in one night. A `///` line explaining
    `if Self.shouldUseCompactNavigationFlow(...)` calls nothing."""
    source = """
/// The shape under test: `if Self.shouldUseCompactNavigationFlow(x) { }`.
func testA() {}
"""
    assert _unresolved(source) == []


def test_a_url_in_a_string_does_not_swallow_the_code_after_it():
    """Strings are blanked BEFORE comments so `//` inside "https://…" cannot start a
    comment. A stripper that got this order wrong removed 74% of a Swift tree when I
    measured it in a throwaway script, and would silently stop scanning most files."""
    source = """
final class T: XCTestCase {
    let host = "https://127.0.0.1:8765"
    func testA() { _ = Self.absent() }
}
"""
    problems = _unresolved(source)
    assert len(problems) == 1, "the line after a URL string must still be scanned"
    assert "Self.absent" in problems[0]


def test_line_numbers_survive_the_blanking():
    """A reported line must be the real one, or the guard's output cannot be acted on:
    blanking replaces matches with spaces rather than deleting them."""
    source = '\n'.join([
        'final class T: XCTestCase {',
        '    let s = "a string"',
        '    // a comment',
        '    func testA() { _ = Self.absent() }',
        '}',
    ])
    problems = _unresolved(source)
    assert len(problems) == 1
    assert ":4" in problems[0], problems[0]


def test_the_real_test_tree_is_clean():
    """The repo passes its own guard. This is the row that fails when somebody lands
    the mistake again."""
    assert guard.main([]) == 0
