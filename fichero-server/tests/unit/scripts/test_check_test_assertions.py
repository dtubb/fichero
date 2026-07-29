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


def test_known_vacuous_entry_is_suppressed(monkeypatch):
    vacuous = check_test_assertions.TestEntry("fichero-server/tests/unit/test_dummy.py::test_known", False)
    monkeypatch.setattr(check_test_assertions, "scan", lambda: [vacuous])
    monkeypatch.setattr(check_test_assertions, "KNOWN_VACUOUS", {vacuous.key})
    monkeypatch.setattr(check_test_assertions.sys, "argv", ["check_test_assertions.py"])
    assert check_test_assertions.main() == 0


def test_new_vacuous_entry_returns_nonzero(monkeypatch):
    vacuous = check_test_assertions.TestEntry("fichero-server/tests/unit/test_dummy.py::test_unknown", False)
    monkeypatch.setattr(check_test_assertions, "scan", lambda: [vacuous])
    monkeypatch.setattr(check_test_assertions, "KNOWN_VACUOUS", set())
    monkeypatch.setattr(check_test_assertions.sys, "argv", ["check_test_assertions.py"])
    assert check_test_assertions.main() == 1
