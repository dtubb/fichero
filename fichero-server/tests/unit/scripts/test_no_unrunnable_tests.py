"""Tests that can never run, and inputs whose absence turns tests green.

A test whose body is an unconditional ``pytest.skip(...)`` reports SKIPPED
forever. It contributes a line of reassurance to every run and can never fail,
no matter what the product does. Same for an unconditional
``@pytest.mark.skip`` decorator. These are worse than no test: a reviewer
scanning for coverage of a behaviour finds a test named after it and moves on.

The sharpest variant is a test that skips *because the thing it asserts is
missing*. ``test_security_headers_present`` is the specimen — it loops over
required headers and calls ``pytest.skip`` on the first one absent, so its
only failure mode is routed into a skip. The real contract is pinned
separately in ``test_security_headers_contract.py``.

This module scans the test tree with the AST rather than trusting a grep of
message text: what matters is the control flow, never the wording of a skip
reason.

Both failing tests below list their offenders by file and line. They are
reported, not fixed — repairing them means editing existing test files, which
this lane does not do.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = TESTS_ROOT / "contracts"


def _iter_test_files() -> list[Path]:
    return sorted(TESTS_ROOT.rglob("test_*.py"))


def _is_test_function(node: ast.AST) -> bool:
    return isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)
    ) and node.name.startswith("test_")


def _body_without_docstring(node) -> list[ast.stmt]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _is_pytest_skip_call(stmt: ast.stmt) -> bool:
    """`pytest.skip(...)` as a bare statement."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "skip"
        and isinstance(func.value, ast.Name)
        and func.value.id == "pytest"
    )


def _is_unconditional_skip_marker(decorator: ast.expr) -> bool:
    """``@pytest.mark.skip`` — with or without a reason, but NOT skipif.

    ``skipif`` is legitimate: it names a condition, and when the condition is
    false the test runs for real.
    """
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not isinstance(node, ast.Attribute) or node.attr != "skip":
        return False
    owner = node.value
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "mark"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "pytest"
    )


def _rel(path: Path) -> str:
    return str(path.relative_to(TESTS_ROOT))


def _scan() -> tuple[list[str], list[str]]:
    always_skipped: list[str] = []
    marked_skip: list[str] = []

    for path in _iter_test_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # a test file that cannot parse never runs
            always_skipped.append(f"{_rel(path)} (unparseable: {exc})")
            continue

        for node in ast.walk(tree):
            if not _is_test_function(node):
                continue
            if any(_is_unconditional_skip_marker(d) for d in node.decorator_list):
                marked_skip.append(f"{_rel(path)}:{node.lineno} {node.name}")
            body = _body_without_docstring(node)
            if body and all(_is_pytest_skip_call(stmt) for stmt in body):
                always_skipped.append(f"{_rel(path)}:{node.lineno} {node.name}")

    return always_skipped, marked_skip


def test_the_scan_actually_reads_test_files():
    """Guard the guard — an empty scan would make both tests below vacuous."""
    files = _iter_test_files()
    assert len(files) >= 100, (
        f"only {len(files)} test files found under {TESTS_ROOT} — the scans "
        "below are measuring nothing"
    )


def test_no_test_body_is_an_unconditional_skip():
    """A test whose entire body is `pytest.skip(...)` can never fail."""
    always_skipped, _ = _scan()
    assert always_skipped == [], (
        "these tests are skipped unconditionally on every run — they can "
        "never fail, and they occupy the name of a behaviour nobody is "
        "checking:\n  " + "\n  ".join(always_skipped)
    )


def test_no_test_is_disabled_with_an_unconditional_skip_marker():
    """`@pytest.mark.skip` disables a test permanently; `skipif` does not."""
    _, marked_skip = _scan()
    assert marked_skip == [], (
        "these tests are disabled by an unconditional @pytest.mark.skip and "
        "have never run since the marker was added:\n  "
        + "\n  ".join(marked_skip)
    )


def test_committed_contract_inputs_exist():
    """`test_contract_models.py` skips whenever these files are absent.

    Its assertions — that Python can parse the Swift-generated workflow
    fixtures, that nulls round-trip, that the schemas match — all sit behind
    ``if not fixture_path.exists(): pytest.skip(...)``. The fixtures are
    committed, so those tests do run today; but deleting or relocating this
    directory turns the entire cross-language contract suite green and silent
    instead of red. Pin the inputs so that deletion is a failure.
    """
    fixtures = CONTRACTS_DIR / "fixtures"
    schemas = CONTRACTS_DIR / "schemas"
    for required in (
        fixtures / "workflow_complete.json",
        fixtures / "workflow_with_nulls.json",
        fixtures / "tool_response.json",
        schemas / "WorkflowDef.json",
        schemas / "NodeDef.json",
        schemas / "EdgeDef.json",
    ):
        assert required.is_file(), (
            f"committed contract input missing: {required} — the tests that "
            "read it skip silently when it is absent, so the whole "
            "cross-language contract suite would go green"
        )
