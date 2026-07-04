"""Guardrail: mutating library routes must use the write-authorized DB dependency."""

from __future__ import annotations

import ast
from pathlib import Path

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
READ_ONLY_MUTATING_VERB_ALLOWLIST: dict[str, str] = {
    "annotations.py:crop_ephemeral:POST": "POST body selects a transient region; handler builds an in-memory Annotation, reads only the source document, and returns a crop — persists nothing (#2256).",
    "bibliography.py:export_bibtex:POST": "POST body selects document IDs; handler only reads metadata and returns BibTeX.",
    "hermeneutics.py:suggest_interpretations:POST": "POST body contains suggestion parameters; handler only reads active frameworks.",
    "kg_predictions.py:generate_heuristic_predictions:POST": "POST body contains prediction parameters; handler only reads claims and vector index.",
    "kg_render.py:render_paragraph:POST": "POST body contains claim IDs/style; handler only reads claims and renders text.",
    "kg_sparql.py:sparql_query:POST": "POST body contains SPARQL; validator rejects mutating verbs and handler only queries RDF graph.",
    "kg_sparql.py:sparql_query_legacy:POST": "Deprecated read-only alias that delegates to sparql_query; same RDF-query-only behavior.",
    "search.py:enhanced_search:POST": "POST /api/search is read-only search/query compute.",
    "search_explain.py:explain_search:POST": "POST body contains explanation request; handler only reads search inputs and returns attribution.",
    "workflows.py:estimate_workflow_cost:POST": "POST body contains estimate inputs; handler only reads workflow pricing context.",
}


def _decorated_methods(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    methods: set[str] = set()
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        func = call.func if call else decorator
        if isinstance(func, ast.Attribute) and func.attr in MUTATING_METHODS:
            methods.add(func.attr.upper())
    return methods


def _mutating_handlers_with_read_dependency() -> list[tuple[str, str]]:
    offenders: list[tuple[str, str]] = []
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
                method_list = ",".join(sorted(methods))
                offenders.append(
                    (
                        f"{rel}:{node.name}:{method_list}",
                        f"{rel}:{node.lineno}:{node.name}:{method_list}",
                    )
                )
    return offenders


def test_mutating_library_routes_use_write_authorized_db_dependency() -> None:
    offenders = _mutating_handlers_with_read_dependency()
    unexpected = [
        offender_with_line
        for offender_key, offender_with_line in offenders
        if offender_key not in READ_ONLY_MUTATING_VERB_ALLOWLIST
    ]
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
    assert not unexpected, "\n".join(lines)


def test_write_dependency_guardrail_allowlist_is_not_stale() -> None:
    offenders = {offender_key for offender_key, _ in _mutating_handlers_with_read_dependency()}
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


def test_write_dependency_guardrail_keys_are_line_independent() -> None:
    offenders = [offender_key for offender_key, _ in _mutating_handlers_with_read_dependency()]
    assert "bibliography.py:168:export_bibtex:POST" not in offenders
    assert "bibliography.py:export_bibtex:POST" in offenders
