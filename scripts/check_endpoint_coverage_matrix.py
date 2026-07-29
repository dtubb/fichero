#!/usr/bin/env python3
"""Completeness-matrix guardrail for endpoint wiring (#1925).

Every OpenAPI operation must be reachable from the Swift service/store layer
and from the Python CLI. The script passes today because the current gaps are
seeded in KNOWN_GAPS and fails only when a new endpoint is added without the
corresponding wiring.

Usage:
    scripts/check_endpoint_coverage_matrix.py
    scripts/check_endpoint_coverage_matrix.py --list
    scripts/check_endpoint_coverage_matrix.py --help
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from matrix_guardrail_common import (
    ROOT,
    HTTP_METHODS,
    endpoint_key,
    load_known_gaps,
    load_openapi,
    normalize_path,
    read_normalized_blob,
)

SWIFT_SOURCES = [
    # `*Service*.swift` (not `*Service.swift`) so per-concern extension files like
    # EntityService+Claims.swift are scanned too — endpoint wiring lives in them
    # after the service splits (#1943).
    *sorted((ROOT / "fichero" / "fichero" / "Services").rglob("*Service*.swift")),
    *sorted((ROOT / "fichero" / "fichero" / "Models").glob("*Store*.swift")),
]
CLI_SOURCES = sorted((ROOT / "fichero-server" / "src" / "fichero" / "cli").rglob("*.py"))
KNOWN_GAPS = load_known_gaps(
    Path(__file__).with_name("check_endpoint_coverage_matrix_known_gaps.json")
)
SWIFT_OPERATION_WITNESSES = {
    "GET /api/citation-usages": "listCitationUsagesApiCitationUsagesGet",
    "GET /api/libraries/{lib}/entity-types": "listLibraryEntityTypesApiLibrariesLibEntityTypesGet",
    "POST /api/libraries/{lib}/entity-types": "addLibraryEntityTypeApiLibrariesLibEntityTypesPost",
    "DELETE /api/libraries/{lib}/entity-types/{entity_type_key}": (
        "removeLibraryEntityTypeApiLibrariesLibEntityTypesEntityTypeKeyDelete"
    ),
}


@dataclass(frozen=True)
class Row:
    endpoint: str
    store: bool
    cli: bool

    @property
    def gap(self) -> bool:
        return not (self.store and self.cli)


def scan() -> list[Row]:
    openapi_path, spec = load_openapi()
    del openapi_path
    swift_blob = read_normalized_blob(SWIFT_SOURCES)
    cli_blob = read_normalized_blob(CLI_SOURCES)
    rows: list[Row] = []
    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            endpoint = endpoint_key(method, path)
            normalized = normalize_path(path)
            swift_witness = SWIFT_OPERATION_WITNESSES.get(endpoint)
            rows.append(
                Row(
                    endpoint=endpoint,
                    store=normalized in swift_blob
                    or (swift_witness is not None and swift_witness in swift_blob),
                    cli=normalized in cli_blob,
                )
            )
    return rows


def _print_matrix(rows: list[Row]) -> None:
    for row in rows:
        status = "known" if row.endpoint in KNOWN_GAPS else "NEW" if row.gap else "ok"
        print(
            f"  [{status}] {row.endpoint} | store={'Y' if row.store else 'N'} | "
            f"cli={'Y' if row.cli else 'N'}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    found = {row.endpoint: row for row in rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"Endpoint coverage matrix ({len(rows)} operations):\n")
        _print_matrix(rows)
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))
    store_missing = sum(not row.store for row in rows)
    cli_missing = sum(not row.cli for row in rows)
    both_missing = sum((not row.store) and (not row.cli) for row in rows)

    print("Endpoint coverage matrix guardrail:")
    print(f"  scanned {len(rows)} operation(s)")
    print(f"  store missing: {store_missing}")
    print(f"  cli missing: {cli_missing}")
    print(f"  missing from both: {both_missing}")
    print(f"  current gaps: {len(found)}; known baseline: {len(known)}")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for endpoint in stale:
            print(f"      {endpoint}")

    if new:
        print(f"\n  {len(new)} new endpoint wiring gap(s):")
        for endpoint in new:
            row = found[endpoint]
            print(
                f"      {endpoint}  <-  store={'Y' if row.store else 'N'}, "
                f"cli={'Y' if row.cli else 'N'}"
            )
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ No endpoint wiring gaps beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
