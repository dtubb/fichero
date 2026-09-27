#!/usr/bin/env python3
"""Completeness-matrix guardrail for endpoint wiring (#1925).

Every OpenAPI operation must be reachable from the Swift service/store layer. The script
passes because the current gaps are seeded in KNOWN_GAPS, and fails when a new endpoint is
added without the corresponding wiring.

What the store axis counts, and why it changed (measured 2026-09-27, #5105/#5108). It used to
look for the endpoint's PATH STRING in the Swift file text, which is wrong twice over:

  * The house rule forbids hand-rolled URLs, so a call through the generated client spells
    the operation NAME and never the path. 490 of 742 operations were reported as gaps; the
    honest number is 278. Ten hand-written SWIFT_OPERATION_WITNESSES entries had accumulated
    patching this case one endpoint at a time, and matching the operation name generally made
    all ten redundant on the same day it was added.
  * File text includes comments, so a `///` line naming a path counted as calling it. Of the
    284 operations whose path appeared in Swift, only 104 appeared in code — 180 were
    witnessed by prose alone. One of them is `POST /api/segments/passes`, the same endpoint
    #5105 records a false "adopted" claim for.

So an endpoint is reached if the generated operation name appears in the scanned code, OR the
path appears in code that is not a comment — the second clause is not redundant: SSE streams
and the `endpointData(path:)` helper genuinely dial paths by hand.

The CLI axis is NOT part of the gap definition, because it cannot fail for a real reason:
738 of 742 operations satisfy it through `openapi_surface_generated.py`, which is generated
from the same schema this script reads, so the axis mostly compares the spec with itself. Only
123 operations appear in hand-written CLI code. Both numbers are printed — the generated one
as a generator-freshness signal, the hand-written one as the honest adoption figure.

Usage:
    scripts/check_endpoint_coverage_matrix.py
    scripts/check_endpoint_coverage_matrix.py --list
    scripts/check_endpoint_coverage_matrix.py --help
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
    read_normalized_blob,
    read_swift_code_blob,
    source_identifiers,
    swift_operation_name,
)
from _scan_files import scan_rglob

# The whole app target. This check asks whether an endpoint is REACHED, not where the call
# lives — the "wiring belongs in a store" rule is a different guardrail's business, which the
# old scope already had to concede for PairingTypes.swift (2026-08-28). It scanned only
# `Services/*Service*.swift` and `Models/*Store*.swift`, and once comments stopped standing in
# for calls that scope reported `GET /api/health` as unreached while three files call
# `healthCheckApiHealthGet` — from App/AppState and RemoteClientPairing (2026-09-27).
SWIFT_SOURCES = sorted(scan_rglob((ROOT / "fichero" / "fichero"), "*.swift"))
CLI_SOURCES = sorted(scan_rglob((ROOT / "fichero-cli" / "src" / "fichero_cli"), "*.py"))
KNOWN_GAPS = load_known_gaps(
    Path(__file__).with_name("check_endpoint_coverage_matrix_known_gaps.json")
)
# SWIFT_OPERATION_WITNESSES is gone. It listed ten endpoints reached through the generated
# client, whose path string therefore never appeared in Swift, and each had been added by hand
# as the gap was noticed. Matching the generated operation name for EVERY operation covers all
# ten, and 151 more the table had never caught up with (measured 2026-09-27).

# The generated CLI surface is derived from the same schema, so it is not evidence of CLI
# adoption; it is only evidence the generator is current. Hand-written CLI files are.
GENERATED_CLI_SURFACE = ROOT / "fichero-cli" / "src" / "fichero_cli" / "openapi_surface_generated.py"
HANDWRITTEN_CLI_SOURCES = [path for path in CLI_SOURCES if path != GENERATED_CLI_SURFACE]


@dataclass(frozen=True)
class Row:
    endpoint: str
    store: bool
    cli: bool
    handwritten_cli: bool

    @property
    def gap(self) -> bool:
        # Store only. `cli` is satisfied by a generated file for 738 of 742 operations, so
        # folding it in would mean a gap definition one of whose halves cannot fail.
        return not self.store


def scan() -> list[Row]:
    openapi_path, spec = load_openapi()
    del openapi_path
    # Tokenised once, not searched 742 times: the per-endpoint regex scans over a 10 MB blob
    # made this the guardrail suite's slowest script by minutes (2026-09-27).
    swift_blob = read_swift_code_blob(SWIFT_SOURCES)
    swift_names = source_identifiers(swift_blob)
    swift_paths = dialled_paths(swift_blob)
    cli_paths = dialled_paths(read_normalized_blob(CLI_SOURCES))
    handwritten_cli_paths = dialled_paths(read_normalized_blob(HANDWRITTEN_CLI_SOURCES))
    rows: list[Row] = []
    for path, path_item in sorted(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            endpoint = endpoint_key(method, path)
            normalized = normalize_path(path)
            operation_name = swift_operation_name(operation.get("operationId", ""))
            rows.append(
                Row(
                    endpoint=endpoint,
                    # The generated client first, a hand-dialled path second. Both are whole-token
                    # lookups, so `listClaims` cannot answer for `listClaimsFor` and `/links`
                    # cannot answer for `/links/types`.
                    store=operation_name in swift_names or normalized in swift_paths,
                    cli=normalized in cli_paths,
                    handwritten_cli=normalized in handwritten_cli_paths,
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
    handwritten_cli = sum(row.handwritten_cli for row in rows)

    print("Endpoint coverage matrix guardrail:")
    print(f"  scanned {len(rows)} operation(s)")
    # #4487 scan floor: on the SCANNED population. 664 ops on 2026-08-02.
    require_scan_floor(len(rows), 332, "OpenAPI operations (664 on 2026-08-02)")
    print(f"  store missing: {store_missing}")
    print(f"  absent from the GENERATED cli surface: {cli_missing} "
          "(a generator-freshness signal, not CLI adoption — see the module docstring)")
    print(f"  reached from HAND-WRITTEN cli code: {handwritten_cli} of {len(rows)}")
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
