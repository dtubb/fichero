"""Guardrail: mutating library routes must use the write-authorized DB dependency."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTES_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "fichero"
    / "api"
    / "routes"
)
MUTATING_METHODS = {"post", "put", "patch", "delete"}

# Mutating HTTP verbs are sometimes used for read-only compute/export operations.
# They may keep the read dependency only when listed here with a reason.
READ_ONLY_MUTATING_VERB_ALLOWLIST: dict[str, str] = {}


def _decorated_methods(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    methods: set[str] = set()
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        func = call.func if call else decorator
        if isinstance(func, ast.Attribute) and func.attr in MUTATING_METHODS:
            methods.add(func.attr.upper())
    return methods


def _mutating_handlers_with_read_dependency() -> list[str]:
    offenders: list[str] = []
    for path in sorted(ROUTES_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = path.relative_to(ROUTES_ROOT).as_posix()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            methods = _decorated_methods(node)
            if not methods:
                continue
            body = ast.get_source_segment(source, node) or ""
            if "Depends(get_library_database)" in body:
                offenders.append(f"{rel}:{node.lineno}:{node.name}:{','.join(sorted(methods))}")
    return offenders


def test_mutating_library_routes_use_write_authorized_db_dependency() -> None:
    offenders = _mutating_handlers_with_read_dependency()
    unexpected = [
        offender
        for offender in offenders
        if offender not in READ_ONLY_MUTATING_VERB_ALLOWLIST
    ]
    if unexpected:
        lines = [
            "Mutating route handlers must depend on get_library_database_for_write, "
            "not the read-only get_library_database. This keeps viewers read-only "
            "when FICHERO_MULTIUSER is enabled.",
            "",
            "Unexpected read-only dependencies:",
            *[f"  {offender}" for offender in unexpected],
            "",
            "If the route uses POST/PUT/PATCH/DELETE for a genuinely read-only "
            "operation, add it to READ_ONLY_MUTATING_VERB_ALLOWLIST with a reason.",
        ]
        pytest.fail("\n".join(lines))


def test_write_dependency_guardrail_allowlist_is_not_stale() -> None:
    offenders = set(_mutating_handlers_with_read_dependency())
    stale = sorted(
        offender
        for offender in READ_ONLY_MUTATING_VERB_ALLOWLIST
        if offender not in offenders
    )
    assert not stale, (
        "Remove stale READ_ONLY_MUTATING_VERB_ALLOWLIST entries:\n  "
        + "\n  ".join(stale)
    )


def test_write_dependency_guardrail_allowlist_entries_have_reasons() -> None:
    missing_reasons = sorted(
        offender
        for offender, reason in READ_ONLY_MUTATING_VERB_ALLOWLIST.items()
        if not reason.strip()
    )
    assert not missing_reasons, (
        "Every write-authz guardrail allowlist entry needs a justification:\n  "
        + "\n  ".join(missing_reasons)
    )
