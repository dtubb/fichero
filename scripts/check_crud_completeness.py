#!/usr/bin/env python3
"""Completeness-matrix guardrail for CRUD symmetry (#1925).

For the core domain entities, the OpenAPI surface should expose a consistent
create/read/list/update/delete set. The current tree is complete, so the
baseline is empty; the script fails only when a new CRUD gap appears.

Usage:
    scripts/check_crud_completeness.py
    scripts/check_crud_completeness.py --list
    scripts/check_crud_completeness.py --help
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

from matrix_guardrail_common import HTTP_METHODS, endpoint_key, load_openapi, normalize_path

ENTITY_RULES: dict[str, tuple[str, ...]] = {
    "Document": ("/api/documents",),
    "Entity": ("/api/entities",),
    "Claim": ("/api/claims",),
    "Note": ("/api/notes",),
    "Annotation": ("/api/annotations",),
    "Action": ("/api/actions",),
    "Research": ("/api/research",),
    "Workflow": ("/api/workflows",),
}
CRUD_ORDER = ("create", "read", "list", "update", "delete")
KNOWN_GAPS: dict[str, str] = {}


@dataclass(frozen=True)
class Row:
    entity: str
    create: bool
    read: bool
    list: bool
    update: bool
    delete: bool
    unclassified: tuple[str, ...] = ()

    @property
    def gap(self) -> bool:
        return not all((self.create, self.read, self.list, self.update, self.delete))

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, value in (
                ("create", self.create),
                ("read", self.read),
                ("list", self.list),
                ("update", self.update),
                ("delete", self.delete),
            )
            if not value
        )


def _is_item_path(path: str) -> bool:
    return bool(re.search(r"\{[^}]+\}", path))


def _matches_entity(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def scan() -> list[Row]:
    _, spec = load_openapi()
    rows: list[Row] = []
    for entity, prefixes in ENTITY_RULES.items():
        verbs = {name: False for name in CRUD_ORDER}
        unclassified: list[str] = []
        for path, path_item in sorted(spec.get("paths", {}).items()):
            if not isinstance(path_item, dict) or not _matches_entity(path, prefixes):
                continue
            normalized = normalize_path(path)
            if not normalized.startswith("/"):
                unclassified.append(endpoint_key("GET", path))
                continue
            item_path = _is_item_path(path)
            for method, operation in sorted(path_item.items()):
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                if method.lower() == "post" and not item_path:
                    verbs["create"] = True
                elif method.lower() == "get" and item_path:
                    verbs["read"] = True
                elif method.lower() == "get" and not item_path:
                    verbs["list"] = True
                elif method.lower() in {"put", "patch"} and item_path:
                    verbs["update"] = True
                elif method.lower() == "delete" and item_path:
                    verbs["delete"] = True
        rows.append(
            Row(
                entity=entity,
                create=verbs["create"],
                read=verbs["read"],
                list=verbs["list"],
                update=verbs["update"],
                delete=verbs["delete"],
                unclassified=tuple(unclassified),
            )
        )
    return rows


def _print_matrix(rows: list[Row]) -> None:
    for row in rows:
        missing = ", ".join(row.missing) if row.missing else "-"
        print(
            f"  [{ 'known' if row.entity in KNOWN_GAPS else 'ok' }] {row.entity} | "
            f"create={'Y' if row.create else 'N'} | read={'Y' if row.read else 'N'} | "
            f"list={'Y' if row.list else 'N'} | update={'Y' if row.update else 'N'} | "
            f"delete={'Y' if row.delete else 'N'} | missing={missing}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    found = {row.entity: row for row in rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"CRUD completeness matrix ({len(rows)} entities):\n")
        _print_matrix(rows)
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))
    unclassified = sorted(
        {
            endpoint
            for row in rows
            for endpoint in row.unclassified
        }
    )

    print("CRUD completeness guardrail:")
    print(f"  scanned {len(rows)} domain entity group(s)")
    print(f"  current gaps: {len(found)}; known baseline: {len(known)}")

    if unclassified:
        print(f"  unclassified endpoint(s): {len(unclassified)}")
        for endpoint in unclassified:
            print(f"      {endpoint}")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for entity in stale:
            print(f"      {entity}")

    if new:
        print(f"\n  {len(new)} new CRUD gap(s):")
        for entity in new:
            row = found[entity]
            print(f"      {entity}  <-  missing {', '.join(row.missing)}")
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ All tracked domain entities have complete CRUD coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
