"""Regression + security coverage for the workflow condition evaluator.

``fichero_server.workflows.safe_condition.safe_eval_expression`` is the allowlist AST
evaluator that gates workflow / chaining conditions (callers in
execution/chaining.py and workflows/resolver.py substitute repr'd literals into
the expression string, then eval + bool()). It had NO direct test coverage.

The security contract these tests pin: any non-allowlisted construct MUST raise
(callers turn every exception into a safe ``False``) — it must never execute
arbitrary code. Plus the arithmetic / comparison / boolean semantics that real
conditions rely on.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.safe_condition import safe_eval_expression as se


# ===========================================================================
# Correctness — comparisons
# ===========================================================================


def test_equality_and_inequality():
    assert se("1 == 1") is True
    assert se("1 == 2") is False
    assert se("1 != 2") is True
    assert se("'a' == 'a'") is True


def test_ordering_operators():
    assert se("1 < 2") is True
    assert se("2 <= 2") is True
    assert se("3 > 2") is True
    assert se("2 >= 3") is False


def test_chained_comparison_matches_python():
    assert se("1 < 2 < 3") is True
    assert se("1 < 3 < 2") is False  # short-circuits on the failing link


def test_membership_operators():
    assert se("'a' in ['a', 'b']") is True
    assert se("'z' in ['a', 'b']") is False
    assert se("'z' not in ['a', 'b']") is True


def test_identity_operators():
    assert se("None is None") is True
    assert se("None is not None") is False


# ===========================================================================
# Correctness — boolean / unary / arithmetic
# ===========================================================================


def test_boolean_ops():
    assert se("True and False") is False
    assert se("True or False") is True
    # `or` returns the first truthy operand value (Python semantics), not a bool.
    assert se("0 or 'x' or 5") == "x"
    assert se("True and 7") == 7


def test_not_operator():
    assert se("not True") is False
    assert se("not False") is True
    assert se("not (1 == 2)") is True


def test_unary_signs():
    assert se("-5") == -5
    assert se("+5") == 5


def test_arithmetic_precedence():
    assert se("2 + 3 * 4") == 14
    assert se("(2 + 3) * 4") == 20
    assert se("10 % 3") == 1
    assert se("10 / 4") == 2.5
    assert se("10 - 3 - 2") == 5


# ===========================================================================
# Correctness — literals / containers
# ===========================================================================


def test_container_literals():
    assert se("[1, 2, 3] == [1, 2, 3]") is True
    assert se("(1, 2) == (1, 2)") is True
    assert se("{1, 2} == {2, 1}") is True


def test_bare_constant_and_bools():
    assert se("42") == 42
    assert se("'hello'") == "hello"
    assert se("True") is True
    assert se("False") is False
    assert se("None") is None


# ===========================================================================
# SECURITY — every dangerous construct must RAISE, never execute
# ===========================================================================


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",          # Call
        "len([1, 2])",               # Call
        "os.system('ls')",           # Call on Attribute
        "'a'.upper()",               # method Call
        "(1).__class__",             # Attribute (dunder walk)
        "[1, 2][0]",                 # Subscript
        "{'a': 1}",                  # Dict literal
        "lambda: 1",                 # Lambda
        "1 if True else 2",          # IfExp
        "(x := 5)",                  # NamedExpr (walrus)
        "[i for i in [1]]",          # comprehension
        "f'{1}'",                    # f-string (JoinedStr)
    ],
)
def test_dangerous_constructs_raise_value_error(expr):
    with pytest.raises(ValueError):
        se(expr)


def test_unknown_variable_raises_not_resolves():
    # A bare name is not a backdoor to globals — it raises.
    with pytest.raises(ValueError):
        se("os")
    with pytest.raises(ValueError):
        se("some_undefined_name")


def test_unsupported_comparison_operator_message():
    # `1 <> 2` isn't valid py3; use an unsupported-in-allowlist path instead:
    # attribute access already covered. Assert the error type is ValueError for
    # a construct the parser accepts but the evaluator rejects (subscript).
    with pytest.raises(ValueError) as exc:
        se("[1, 2][0]")
    assert "Unsupported" in str(exc.value)


# ===========================================================================
# Edge cases — bad input surfaces as an exception (callers catch -> False)
# ===========================================================================


def test_empty_expression_raises_syntax_error():
    with pytest.raises(SyntaxError):
        se("")


def test_malformed_expression_raises_syntax_error():
    with pytest.raises(SyntaxError):
        se("1 ==")


def test_division_by_zero_propagates():
    # Not swallowed here — callers wrap in try/except and log -> False.
    with pytest.raises(ZeroDivisionError):
        se("1 / 0")
    with pytest.raises(ZeroDivisionError):
        se("1 % 0")


def test_realistic_workflow_conditions():
    # The shape callers actually produce after substituting repr'd values.
    assert se("'done' == 'done'") is True
    assert se("5 > 3 and 'ok' in ['ok', 'fail']") is True
    assert se("(2 + 2) == 4 and not False") is True
    assert se("10 >= 20 or 'a' == 'a'") is True
