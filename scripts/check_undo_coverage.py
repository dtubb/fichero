#!/usr/bin/env python3
"""Completeness-matrix guardrail for undo coverage (#1925).

Every mutating endpoint that participates in user-facing state changes should have a
corresponding undo registration in the Swift undo system. The script passes because the
current gaps are seeded in KNOWN_GAPS and fails when a new mutating endpoint appears
without undo wiring.

Read the number this prints as what it is (#5109). Of 393 mutating operations, ZERO are
named in an undo-registering file by a strict match. Undo in this app is a view-level
`UndoManager` concern — eight files register it, for canvas moves, sidebar actions and
workflow edits — so there is no endpoint-to-undo relationship for this axis to measure,
and there will not be until the parked undo/trash/rollback design lands.

Until 2026-09-27 it reported six endpoints as covered, and all six were artefacts of
substring matching on paths whose `/api/` prefix had been stripped: `POST /api/library`
passed because a comment in UndoRouting.swift reads "document/library undo", so the text
contained `/library`. `POST /api/pair` passed on the word "pairing". Those six now match
strictly and are seeded with that as their reason, which is the honest state: the guard is
holding a line at zero, not at six. The substring, comment and brace-collapse defects
behind them are #5108; this script uses the repaired reader.

The zero was then partly the guard's own blindness (#5144): it looked only for PATH strings,
and the house rule sends nearly every call through the generated client, whose methods are
named for the operationId. An undo-registering file that names an operation's generated method
now counts -- for an operation whose answer carries `audit_id`, since an app-side registration
of a server edit reverses that audit row (`ActionUndo.register`). The audit-row condition keeps
the witness at the code's granularity: without it, every call in a file that registers undo
for something else read as covered. Found covered on 2026-09-27: `POST /api/actions/invoke`
and `PUT /api/artifacts/{artifact_id}/regions`.

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
    dialled_paths,
    normalize_path,
    read_swift_code_blob,
    source_identifiers,
    swift_operation_name,
)
from _scan_files import scan_rglob

UNDO_TOKENS = ("UndoManager", "registerUndo", "undoAction", "canUndo")


def undo_sources(paths) -> list[Path]:
    """The Swift files that register undo: those naming one of `UNDO_TOKENS`."""
    return sorted(
        path
        for path in paths
        if any(token in path.read_text(encoding="utf-8", errors="ignore") for token in UNDO_TOKENS)
    )


UNDO_SOURCES = undo_sources(scan_rglob(ROOT.joinpath("fichero", "fichero"), "*.swift"))
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


def _schema_properties(schema: object, components: dict, depth: int = 0) -> set[str]:
    """The property names a response schema declares, through `$ref` and `allOf`/`anyOf`."""
    if not isinstance(schema, dict) or depth > 6:
        return set()
    if "$ref" in schema:
        return _schema_properties(components.get(schema["$ref"].rsplit("/", 1)[-1]), components, depth + 1)
    found = set(schema.get("properties") or {})
    for key in ("allOf", "anyOf", "oneOf"):
        for part in schema.get(key) or []:
            found |= _schema_properties(part, components, depth + 1)
    return found


def answers_with_an_audit_row(operation: dict, spec: dict) -> bool:
    """Whether the operation's success answer carries `audit_id`.

    An app-side registration of a SERVER edit is `ActionUndo.register(auditId: ...)`: ⌘Z
    reverses the audit row the edit wrote. An operation whose answer carries no audit row
    cannot be registered that way, however close to an undo call it sits. This is what keeps
    the operation-name witness at the granularity of the code (#5144): an undo-registering
    FILE also calls operations it never registers -- `createArtifact` beside the region edits,
    `share` beside `invokeAction` -- and a file-level match counted them as covered.
    """
    components = (spec.get("components") or {}).get("schemas") or {}
    for status, response in (operation.get("responses") or {}).items():
        if not str(status).startswith("2") or not isinstance(response, dict):
            continue
        for media in (response.get("content") or {}).values():
            if "audit_id" in _schema_properties(media.get("schema"), components):
                return True
    return False


def _label(source: Path) -> str:
    try:
        return str(source.relative_to(ROOT))
    except ValueError:
        return str(source)


def scan(spec: dict | None = None, sources: list[Path] | None = None) -> list[Row]:
    """One row per mutating operation. `spec` and `sources` default to the contract and the
    app's undo-registering files; the tests pass fixtures."""
    if spec is None:
        _, spec = load_openapi()
    if sources is None:
        sources = UNDO_SOURCES
    # One read per undo file, not one per file per endpoint: the old evidence loop read all
    # 17 sources twice for each of 393 operations (2026-09-27). Each file answers two
    # questions: which paths it dials, and which identifiers it names -- the house rule sends
    # nearly every call through the GENERATED client, whose method is named for the
    # operationId and carries no path string at all (#5144). Counting paths only, every
    # generated-client call read as a gap, however much undo it registered.
    per_source: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for source in sources:
        blob = read_swift_code_blob([source])
        per_source[_label(source)] = (dialled_paths(blob), source_identifiers(blob))
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
            # Strictly: the path, in code, at both its ends. The old test was a substring
            # of `normalize_path(file_text)`, which collapsed Swift braces as if the file
            # were an OpenAPI path and let a comment stand in for a registration (#5108).
            operation_name = (
                swift_operation_name(operation.get("operationId", ""))
                if answers_with_an_audit_row(operation, spec)
                else ""
            )
            evidence: tuple[str, ...] = tuple(
                name
                for name, (paths, identifiers) in per_source.items()
                if normalized in paths or (operation_name and operation_name in identifiers)
            )
            rows.append(
                Row(
                    endpoint=endpoint,
                    undo_registered=bool(evidence),
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
