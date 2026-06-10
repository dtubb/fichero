#!/usr/bin/env python3
"""Ratchet guardrail for mutating backend endpoints that touch observed domains.

A violation is any top-level POST/PUT/PATCH/DELETE handler in a route module whose
store-observed domain does not call emit_change().

The current gaps are seeded in KNOWN_GAPS so this script passes on the current tree
and fails only when a new mutating route appears without emit coverage.

Usage:
    scripts/check_emit_change_coverage.py
    scripts/check_emit_change_coverage.py --list
    scripts/check_emit_change_coverage.py --help
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "fichero" / "fichero" / "Models"
ROUTES_DIR = ROOT / "fichero-engine" / "src" / "fichero" / "api" / "routes"

METHODS = {"post", "put", "patch", "delete"}

ROUTE_DOMAIN_MAP: dict[str, str] = {
    "annotations": "annotation",
    "notes": "note",
    "research_notes": "note",
    "actions": "action",
    "research_crud": "research",
    "projects": "research",
    "entities": "entity",
    "claims": "claim",
    "claim_curation": "claim",
    "claim_links": "claim",
    "documents": "document",
    "workflows": "workflow",
}

CHANGE_DOMAIN_RE = re.compile(r"changeDomains:\s*Set<String>\s*\{\s*\[(.*?)\]\s*\}", re.S)
STRING_RE = re.compile(r'\"([^\"]+)\"')

# Seeds this script at the current tree.
KNOWN_GAPS: set[str] = {
    "fichero-engine/src/fichero/api/routes/claims.py::assign_time_period",
    "fichero-engine/src/fichero/api/routes/claims.py::assign_time_period_from_metadata",
    "fichero-engine/src/fichero/api/routes/claims.py::resolve_claim_source",
    "fichero-engine/src/fichero/api/routes/documents.py::assign_document_prototype",
    "fichero-engine/src/fichero/api/routes/documents.py::backfill_pdf_pages",
    "fichero-engine/src/fichero/api/routes/documents.py::batch_exclude_documents",
    "fichero-engine/src/fichero/api/routes/documents.py::cleanup_orphan_documents",
    "fichero-engine/src/fichero/api/routes/documents.py::create_document",
    "fichero-engine/src/fichero/api/routes/documents.py::delete_document_note",
    "fichero-engine/src/fichero/api/routes/documents.py::move_document",
    "fichero-engine/src/fichero/api/routes/documents.py::patch_workspace_items",
    "fichero-engine/src/fichero/api/routes/documents.py::put_document_note",
    "fichero-engine/src/fichero/api/routes/documents.py::reorder_documents",
    "fichero-engine/src/fichero/api/routes/documents.py::upsert_page_ranges",
    "fichero-engine/src/fichero/api/routes/entities.py::add_entity_aliases",
    "fichero-engine/src/fichero/api/routes/entities.py::delete_entity",
    "fichero-engine/src/fichero/api/routes/notes.py::create_note_link",
    "fichero-engine/src/fichero/api/routes/notes.py::delete_note_link",
    "fichero-engine/src/fichero/api/routes/research_notes.py::create_checklist",
    "fichero-engine/src/fichero/api/routes/research_notes.py::create_search_source",
    "fichero-engine/src/fichero/api/routes/research_notes.py::toggle_checklist_item",
    "fichero-engine/src/fichero/api/routes/workflows.py::create_node",
    "fichero-engine/src/fichero/api/routes/workflows.py::create_workflow",
    "fichero-engine/src/fichero/api/routes/workflows.py::delete_workflow",
    "fichero-engine/src/fichero/api/routes/workflows.py::duplicate_workflow",
    "fichero-engine/src/fichero/api/routes/workflows.py::estimate_workflow_cost",
    "fichero-engine/src/fichero/api/routes/workflows.py::get_tool_prompt",
    "fichero-engine/src/fichero/api/routes/workflows.py::import_workflow",
    "fichero-engine/src/fichero/api/routes/workflows.py::patch_workflow",
    "fichero-engine/src/fichero/api/routes/workflows.py::reinstall_default_workflows",
    "fichero-engine/src/fichero/api/routes/workflows.py::reorder_workflows",
    "fichero-engine/src/fichero/api/routes/workflows.py::update_workflow",
}


@dataclass(frozen=True)
class Row:
    file: str
    handler: str
    method: str
    domain: str
    emit_change: bool

    @property
    def key(self) -> str:
        return f"{self.file}::{self.handler}"

    @property
    def gap(self) -> bool:
        return not self.emit_change


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _observed_domains() -> set[str]:
    observed: set[str] = set()
    for path in sorted(MODELS_DIR.glob("*Store.swift")):
        text = _read_text(path)
        match = CHANGE_DOMAIN_RE.search(text)
        if not match:
            continue
        observed.update(STRING_RE.findall(match.group(1)))
    return observed


def _mutating_method(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "router":
        return None
    if func.attr not in METHODS:
        return None
    return func.attr


def _has_emit_change(function_node: ast.AST) -> bool:
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "emit_change":
            return True
        if isinstance(callee, ast.Attribute) and callee.attr == "emit_change":
            return True
    return False


def scan() -> list[Row]:
    observed_domains = _observed_domains()
    rows: list[Row] = []

    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        domain = ROUTE_DOMAIN_MAP.get(path.stem)
        if not domain or domain not in observed_domains:
            continue
        source = _read_text(path)
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue

        rel_path = path.relative_to(ROOT).as_posix()
        for statement in module.body:
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            methods = {_mutating_method(decorator) for decorator in statement.decorator_list}
            methods.discard(None)
            if not methods:
                continue
            rows.append(
                Row(
                    file=rel_path,
                    handler=statement.name,
                    method=next(iter(sorted(methods))),
                    domain=domain,
                    emit_change=_has_emit_change(statement),
                )
            )

    return rows


def _print_rows(rows: list[Row]) -> None:
    for row in rows:
        status = "known" if row.key in KNOWN_GAPS else "NEW" if row.gap else "ok"
        print(
            f"  [{status}] {row.key} | method={row.method.upper():5} domain={row.domain:8} "
            f"emit_change={'Y' if row.emit_change else 'N'}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    gaps = {row.key: row for row in rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"Emit-change coverage ({len(rows)} mutating routes):\n")
        _print_rows(rows)
        return 0

    new = sorted(set(gaps) - known)
    stale = sorted(known - set(gaps))
    covered = len(rows) - len(gaps)

    print("emit-change coverage:")
    print(f"  {len(rows)} mutating route(s) checked")
    print(f"  emit-change coverage: {len(known)} known gaps, {covered} routes covered")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new gaps:")
        for key in new:
            row = gaps[key]
            print(f"      {key}  (method={row.method.upper()}, domain={row.domain})")
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ No emit_change coverage regressions beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
