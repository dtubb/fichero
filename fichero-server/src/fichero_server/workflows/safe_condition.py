"""Shared safe expression evaluator for workflow conditions."""

from __future__ import annotations

import ast
import operator
from typing import Any


SAFE_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
    ast.Not: operator.not_,
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}


def safe_eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an allowlisted AST node."""

    if isinstance(node, ast.Expression):
        return safe_eval_node(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [safe_eval_node(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(safe_eval_node(elt) for elt in node.elts)
    if isinstance(node, ast.Set):
        return {safe_eval_node(elt) for elt in node.elts}
    if isinstance(node, ast.Compare):
        left = safe_eval_node(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            op_func = SAFE_OPERATORS.get(type(op))
            if op_func is None:
                raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")
            right = safe_eval_node(comparator)
            if not op_func(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        op_func = SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")
        result = safe_eval_node(node.values[0])
        for value in node.values[1:]:
            result = op_func(result, safe_eval_node(value))
        return result
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not safe_eval_node(node.operand)
        if isinstance(node.op, ast.USub):
            return -safe_eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +safe_eval_node(node.operand)
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        op_func = SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = safe_eval_node(node.left)
        right = safe_eval_node(node.right)
        return op_func(left, right)
    if isinstance(node, ast.Name):
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
        raise ValueError(f"Unknown variable: {node.id}")
    raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def safe_eval_expression(expression: str) -> Any:
    """Parse and safely evaluate a condition expression."""

    tree = ast.parse(expression, mode="eval")
    return safe_eval_node(tree)
