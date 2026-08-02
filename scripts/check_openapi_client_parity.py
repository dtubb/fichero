#!/usr/bin/env python3
"""OpenAPI client parity guardrail (#1921).

Asserts that the committed Swift client OpenAPI input files match the canonical
contract, and that the generated Python CLI command surface exposes every
OpenAPI operation except the seeded streaming/debug baseline.

Usage:
    scripts/check_openapi_client_parity.py
    scripts/check_openapi_client_parity.py --list
    scripts/check_openapi_client_parity.py --help
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from matrix_guardrail_common import HTTP_METHODS, ROOT, endpoint_key, load_known_gaps


CANONICAL_OPENAPI = ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"
SWIFT_OPENAPI_INPUTS = (
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "FicheroAPIClient" / "openapi.json",
)
CLI_SURFACE = ROOT / "fichero-cli" / "src" / "fichero_cli" / "openapi_surface_generated.py"
KNOWN_GAPS = load_known_gaps(Path(__file__).with_name("check_openapi_client_parity_known_gaps.json"))


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str

    @property
    def endpoint(self) -> str:
        return endpoint_key(self.method, self.path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _operations(spec: dict[str, Any]) -> list[Operation]:
    operations: list[Operation] = []
    for path, path_item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method, operation in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operations.append(
                Operation(
                    method=method.upper(),
                    path=path,
                    operation_id=str(operation.get("operationId") or ""),
                )
            )
    return operations


def _copy_mismatches(canonical: dict[str, Any]) -> list[Path]:
    mismatches: list[Path] = []
    for path in SWIFT_OPENAPI_INPUTS:
        if not path.exists() or _load_json(path) != canonical:
            mismatches.append(path)
    return mismatches


def _cli_exposes(operation: Operation, cli_text: str) -> bool:
    endpoint_marker = f"({operation.method} {operation.path})"
    if endpoint_marker in cli_text:
        return True
    if operation.operation_id and re.search(rf"\b{re.escape(operation.operation_id)}\b", cli_text):
        return True
    return False


def scan() -> tuple[list[Operation], list[Path], list[Operation], list[str]]:
    canonical = _load_json(CANONICAL_OPENAPI)
    operations = _operations(canonical)
    mismatches = _copy_mismatches(canonical)
    if not CLI_SURFACE.exists():
        # #4487 Phase 3: a missing NAMED input used to read as "" — every
        # operation then looked CLI-missing, a wall of false accusations
        # begging to be baselined. Blind, said out loud, is exit 2.
        print(
            f"BLIND: named source missing: {CLI_SURFACE} (#4487 Phase 3)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    cli_text = CLI_SURFACE.read_text(encoding="utf-8", errors="ignore")
    missing_cli = [operation for operation in operations if not _cli_exposes(operation, cli_text)]
    stale = sorted(set(KNOWN_GAPS) - {operation.endpoint for operation in missing_cli})
    return operations, mismatches, missing_cli, stale


def _print_list(operations: list[Operation], missing_cli: list[Operation]) -> None:
    missing = {operation.endpoint for operation in missing_cli}
    for operation in operations:
        if operation.endpoint in missing:
            status = "known" if operation.endpoint in KNOWN_GAPS else "NEW"
        else:
            status = "ok"
        print(f"  [{status}] {operation.endpoint} | operationId={operation.operation_id}")


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    operations, mismatches, missing_cli, stale = scan()
    found = {operation.endpoint: operation for operation in missing_cli}
    known = set(KNOWN_GAPS)
    new = sorted(set(found) - known)

    if "--list" in sys.argv[1:]:
        print(f"OpenAPI client parity matrix ({len(operations)} operations):\n")
        _print_list(operations, missing_cli)
        return 0

    print("OpenAPI client parity guardrail:")
    print(f"  scanned {len(operations)} operation(s)")
    print(f"  Swift OpenAPI inputs checked: {len(SWIFT_OPENAPI_INPUTS)}")
    print(f"  CLI missing: {len(missing_cli)}; known baseline: {len(known)}")

    if mismatches:
        print("\n  Swift OpenAPI copy drift:")
        for path in mismatches:
            print(f"      {path.relative_to(ROOT)}")

    if stale:
        print(f"\n  {len(stale)} KNOWN_GAPS entries are now clean; remove them:")
        for endpoint in stale:
            print(f"      {endpoint}")

    if new:
        print(f"\n  {len(new)} new CLI/OpenAPI parity gap(s):")
        for endpoint in new:
            print(f"      {endpoint}")

    if mismatches or new:
        return 1

    if stale:
        print("\n(KNOWN_GAPS has stale entries; clean them up when convenient.)")

    print("\n✓ OpenAPI copies match and CLI parity has no gaps beyond the seeded baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
