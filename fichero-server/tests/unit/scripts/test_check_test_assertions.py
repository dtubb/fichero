from __future__ import annotations

import ast
import sys
import importlib.util

from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_test_assertions.py"
_SPEC = importlib.util.spec_from_file_location("check_test_assertions", _SCRIPT)
assert _SPEC and _SPEC.loader
check_test_assertions = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_test_assertions  # register so @dataclass can resolve its module
_SPEC.loader.exec_module(check_test_assertions)  # type: ignore[attr-defined]


def _as_function(source: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            return node
    raise AssertionError("source did not contain a test function")


def test_python_assertion_detects_assert_and_pytest_raises():
    assert check_test_assertions._python_asserts(
        _as_function(
            """
def test_has_assert():
    assert True
"""
        )
    )
    assert check_test_assertions._python_asserts(
        _as_function(
            """
def test_has_pytest_raises():
    import pytest
    with pytest.raises(ValueError):
        int("x")
"""
        )
    )


def test_python_assertion_detects_self_assert_methods():
    assert check_test_assertions._python_asserts(
        _as_function(
            """
class TestSuite:
    def test_has_self_assert(self):
        self.assertEqual(1, 1)
"""
        )
    )


def test_python_assertion_does_not_match_vacuous_body():
    assert not check_test_assertions._python_asserts(
        _as_function(
            """
def test_vacuous():
    value = 1 + 1
    return value
"""
        )
    )


def test_swift_assertions_and_expect_count_as_assertions(tmp_path):
    source = """
func test_with_xctassert() {
    XCTAssertEqual(1, 1)
}

func test_with_expect() {
    #expect(true)
}

func test_without_assertion() {
    let value = 1 + 1
}
"""
    swift_root = tmp_path / "fichero" / "fichero" / "Tests"
    swift_root.mkdir(parents=True)
    test_file = swift_root / "GuardrailTests.swift"
    test_file.write_text(source, encoding="utf-8")

    entries = check_test_assertions._scan_swift(root=tmp_path, paths=[test_file])
    by_name = {entry.key.split("::")[-1]: entry.has_assertion for entry in entries}

    assert by_name["test_with_xctassert"] is True
    assert by_name["test_with_expect"] is True
    assert by_name["test_without_assertion"] is False


# These two stub scan() to a SINGLE entry to isolate the allowlist logic —
# which trips the #4487 scan floor by construction. The floor is neutralized
# here because it is not the property under test; that it FIRES on a starved
# scan is proven separately in test_guardrails_scan_floor.py.


def test_known_vacuous_entry_is_suppressed(monkeypatch):
    vacuous = check_test_assertions.TestEntry("fichero-server/tests/unit/test_dummy.py::test_known", False)
    monkeypatch.setattr(check_test_assertions, "scan", lambda: [vacuous])
    monkeypatch.setattr(check_test_assertions, "KNOWN_VACUOUS", {vacuous.key})
    monkeypatch.setattr(check_test_assertions, "require_scan_floor", lambda *a, **k: None)
    monkeypatch.setattr(check_test_assertions.sys, "argv", ["check_test_assertions.py"])
    assert check_test_assertions.main() == 0


def test_new_vacuous_entry_returns_nonzero(monkeypatch):
    vacuous = check_test_assertions.TestEntry("fichero-server/tests/unit/test_dummy.py::test_unknown", False)
    monkeypatch.setattr(check_test_assertions, "scan", lambda: [vacuous])
    monkeypatch.setattr(check_test_assertions, "KNOWN_VACUOUS", set())
    monkeypatch.setattr(check_test_assertions, "require_scan_floor", lambda *a, **k: None)
    monkeypatch.setattr(check_test_assertions.sys, "argv", ["check_test_assertions.py"])
    assert check_test_assertions.main() == 1


class TestAnAssertionHelperCounts:
    """A call to an `assert_*` function is an assertion, wherever it lives.

    Added 2026-09-27. The detector knew `self.assertX` and the exact string `assert_called`,
    and nothing else, so six tests were reported vacuous that all do assert:

        assert_known_direction(direction)                        # module-level helper
        assert_known_script(library, code)                        # same, imported
        kraken_runtime.assert_memory_available_for_kraken(...)    # reached through a module
        mock_clone.assert_called_once()                            # a mock, past `assert_called`

    Three of those were already sitting in KNOWN_VACUOUS, i.e. the blind spot had already been
    recorded as permissions rather than fixed. That is the failure mode #5095 and #5108 both
    name, and it is why this is a detector change and not six annotations.
    """

    def test_a_module_level_assert_helper_counts(self):
        assert check_test_assertions._python_asserts(
            _as_function(
                """
def test_direction():
    assert_known_direction("rtl")
"""
            )
        )

    def test_a_helper_reached_through_a_module_counts(self):
        assert check_test_assertions._python_asserts(
            _as_function(
                """
def test_memory():
    kraken_runtime.assert_memory_available_for_kraken(available_bytes=lambda: 1)
"""
            )
        )

    def test_any_mock_assert_method_counts_not_only_assert_called(self):
        """`assert_called_once`, `assert_called_with`, `assert_not_called`, `assert_awaited`."""
        for call in (
            "m.assert_called_once()",
            "m.assert_called_with(1)",
            "m.assert_not_called()",
            "m.assert_awaited_once_with(2)",
        ):
            assert check_test_assertions._python_asserts(
                _as_function(f"def test_x():\n    {call}\n")
            ), call

    def test_a_name_that_merely_starts_with_assert_does_not_count(self):
        """`assert_` with the underscore: a variable or a value is not a check.

        Without the underscore, `assertion_count += 1` or a call to `asserted_value()` would
        pass for an assertion, and the guard would go quiet exactly where it is needed.
        """
        assert not check_test_assertions._python_asserts(
            _as_function(
                """
def test_x():
    asserted_value()
    assertions = collect()
"""
            )
        )

    def test_the_predicate_itself_is_exact(self):
        helper = check_test_assertions._is_assertion_helper
        assert helper("assert_known_script")
        assert helper("assert_called_once")
        assert helper("assert")
        assert not helper("asserted_value")
        assert not helper("assertions")
        assert not helper("reassert_something")
