#!/usr/bin/env python3
"""Completeness-matrix guardrail for undo coverage (#1925).

Every mutating endpoint that participates in user-facing state changes should
have a corresponding undo registration in the Swift undo system. The script
passes today because the current gaps are seeded in KNOWN_GAPS and fails only
when a new mutating endpoint appears without undo wiring.

Usage:
    scripts/check_undo_coverage.py
    scripts/check_undo_coverage.py --list
    scripts/check_undo_coverage.py --help
"""
from __future__ import annotations

import sys

from _check_floor import require_scan_floor
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

UNDO_SOURCES = sorted(
    path
    for path in ROOT.joinpath("fichero", "fichero").rglob("*.swift")
    if any(
        token in path.read_text(encoding="utf-8", errors="ignore")
        for token in ("UndoManager", "registerUndo", "undoAction", "canUndo")
    )
)
KNOWN_GAPS = load_known_gaps(Path(__file__).with_name("check_undo_coverage_known_gaps.json"))
REVERSE_MARKERS = ("undo", "rollback", "restore")
NON_UNDO_MUTATIONS = {
    "POST /api/sandbox/security-scoped-access": "process-local capability grant; no persisted user state",
}


@dataclass(frozen=True)
class Row:
    endpoint: str
    undo_registered: bool
    evidence: tuple[str, ...]

    @property
    def gap(self) -> bool:
        return not self.undo_registered


def _is_candidate(path: str) -> bool:
    lower = path.lower()
    return not any(marker in lower for marker in REVERSE_MARKERS)


def scan() -> list[Row]:
    _, spec = load_openapi()
    undo_blob = read_normalized_blob(UNDO_SOURCES)
    rows: list[Row] = []
    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not _is_candidate(path) or not isinstance(path_item, dict):
            continue
        normalized = normalize_path(path)
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            if method.lower() not in {"post", "put", "patch", "delete"}:
                continue
            endpoint = endpoint_key(method, path)
            if endpoint in NON_UNDO_MUTATIONS:
                continue
            evidence: tuple[str, ...] = tuple(
                str(source.relative_to(ROOT))
                for source in UNDO_SOURCES
                if normalize_path(path) in normalize_path(source.read_text(encoding="utf-8", errors="ignore"))
                or normalized in normalize_path(source.read_text(encoding="utf-8", errors="ignore"))
            )
            rows.append(
                Row(
                    endpoint=endpoint,
                    undo_registered=bool(evidence) or normalized in undo_blob,
                    evidence=evidence,
                )
            )
    return rows


def _print_matrix(rows: list[Row]) -> None:
    for row in rows:
        status = "known" if row.endpoint in KNOWN_GAPS else "NEW" if row.gap else "ok"
        evidence = ", ".join(row.evidence) if row.evidence else "-"
        print(
            f"  [{status}] {row.endpoint} | undo={'Y' if row.undo_registered else 'N'} | "
            f"evidence={evidence}"
        )


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    rows = scan()
    # #4487 scan floor: on the SCANNED population (mutating operations from
    # the OpenAPI spec), never the gap count. 351 observed on 2026-08-02.
    require_scan_floor(len(rows), 175, "mutating operations (351 on 2026-08-02)")
    found = {row.endpoint: row for row in rows if row.gap}
    known = set(KNOWN_GAPS)

    if "--list" in sys.argv[1:]:
        print(f"Undo coverage matrix ({len(rows)} mutating operations):\n")
        _print_matrix(rows)
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print("Undo coverage guardrail:")
    print(f"  scanned {len(rows)} mutating operation(s)")
    print(f"  undo surface files: {len(UNDO_SOURCES)}")
    print(f"  current gaps: {len(found)}; known baseline: {len(known)}")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for endpoint in stale:
            print(f"      {endpoint}")

    if new:
        print(f"\n  {len(new)} new undo gap(s):")
        for endpoint in new:
            print(f"      {endpoint}")
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ No mutating endpoint gaps beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
