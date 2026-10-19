"""A refusal with an OBJECT detail is declared as one (#5094).

Some routes refuse with a structured body (a stale note's `current_body`, an ingest 403's `code`), not a sentence.
The generated Swift client decodes against the declared body, so a body whose `detail` is only a string throws on
exactly the refusals that carry the information. Two halves are pinned here: `ErrorDetail` accepts an object, and no
module that raises an object detail overrides a refusal status with a body other than `ErrorDetail`.

The raise usually sits in a helper, not in the decorated route, so the check is per module, not per route.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from fichero_server.api.errors import ErrorDetail

ROUTES = Path(__file__).resolve().parents[3] / "src" / "fichero_server" / "api" / "routes"

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)

REFUSAL_STATUSES = {400, 403, 404, 409}
REFUSAL_MODELS = {"ErrorDetail", "_RefusalBody"}  # the module-level alias used by the routes


def _object_detail_statuses(tree: ast.AST) -> set[int]:
    """The statuses this module refuses with an OBJECT detail. An unreadable status counts as every refusal status."""
    statuses: set[int] = set()
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _name(call.func) == "HTTPException"):
            continue
        if not any(kw.arg == "detail" and isinstance(kw.value, ast.Dict) for kw in call.keywords):
            continue
        code = next((kw.value for kw in call.keywords if kw.arg == "status_code"), None)
        if code is None and call.args:
            code = call.args[0]
        if isinstance(code, ast.Constant) and isinstance(code.value, int):
            statuses.add(code.value)
        else:
            statuses |= REFUSAL_STATUSES
    return statuses


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _undeclared_refusal_bodies(tree: ast.AST, statuses: set[int]) -> list[tuple[int, int, str]]:
    """(lineno, status, model name) for each status in `statuses` declared with a body that is not ErrorDetail."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg != "responses" or not isinstance(node.value, ast.Dict):
            continue
        for status, entry in zip(node.value.keys, node.value.values):
            if not (isinstance(status, ast.Constant) and status.value in statuses):
                continue
            if not isinstance(entry, ast.Dict):
                continue
            for key, value in zip(entry.keys, entry.values):
                if isinstance(key, ast.Constant) and key.value == "model":
                    model = _name(value)
                    if model not in REFUSAL_MODELS:
                        found.append((status.lineno, status.value, model or ast.dump(value)))
    return found


def test_error_detail_accepts_an_object_detail():
    body = ErrorDetail(detail={"reason": "stale", "current_body": "x"}).model_dump()
    assert body == {"detail": {"reason": "stale", "current_body": "x"}}
    assert ErrorDetail(detail="a sentence").detail == "a sentence"


def test_modules_raising_an_object_detail_declare_it_as_error_detail():
    raisers = []
    for path in scan_files.scan_rglob(ROUTES, "*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        statuses = _object_detail_statuses(tree)
        if not statuses:
            continue
        raisers.append(str(path.relative_to(ROUTES)))
        problems = _undeclared_refusal_bodies(tree, statuses)
        assert not problems, (
            f"{path.relative_to(ROUTES)} raises an object detail but declares a refusal body that is not "
            f"ErrorDetail (its detail is a string only): {problems}"
        )
    # Non-vacuous: the six known object-detail refusals (notes, documents, content representations, references,
    # reading orders, ingest) must be among the modules this test actually inspected.
    assert raisers, "no object-detail refusals found; the scan is looking at nothing"
