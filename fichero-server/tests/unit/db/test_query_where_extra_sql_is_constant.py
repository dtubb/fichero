"""Guardrail: every `Database._query_where` call passes a CONSTANT `extra_sql`.

`_query_where` (db/__init__.py, beside its sibling `query_in`) is a general
raw-WHERE-fragment door with one caller today (the segments route's
area-by-rectangle read, #4921). Its own docstring's rule is that `extra_sql`
must be a module-level string literal with no interpolation -- every value,
including a whole list, binds through `params` (`$name` placeholders) -- and
an f-string built per call is exactly the shape this rule forbids (it was
this method's own first shape, caught in review). A rule stated in a
docstring and never checked erodes the first time someone is in a hurry;
this scan makes it a build failure instead.

METHOD. AST over `src/fichero_server`, no text matching: every `ast.Call`
whose function is an attribute named `_query_where` is found, and its
`extra_sql` argument (second positional, or the `extra_sql` keyword) must be
either a string literal (`ast.Constant`) or a bare name (`ast.Name` -- a
module-level constant, e.g. `_AREA_CANDIDATE_SQL`). Anything else (an
f-string, a `.format()` call, string concatenation, a computed expression)
fails, naming the file and line.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "fichero_server"


def _extra_sql_arg(call: ast.Call) -> ast.expr | None:
    if len(call.args) >= 2:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg == "extra_sql":
            return kw.value
    return None


def _is_allowed_constant(node: ast.expr) -> bool:
    # A string literal, or a bare name (a module-level constant reference).
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Name):
        return True
    return False


def test_every_query_where_call_passes_a_constant_extra_sql():
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "_query_where"):
                continue
            arg = _extra_sql_arg(node)
            if arg is None or not _is_allowed_constant(arg):
                violations.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")

    assert not violations, (
        "_query_where's extra_sql must be a string literal or a module-level "
        f"constant name, never a computed expression: {violations}"
    )
