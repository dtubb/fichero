#!/usr/bin/env python3
"""Fail when the engine's ROUTES differ from the committed OpenAPI contracts.

`check_openapi_version_current.py` compares `info.version` only. On 2026-09-27 three engine
route changes (GET/PATCH /api/segments, a changed PUT regions response) sat outside all three
committed contracts all day while it printed "All 3 contracts match the code". The real
freshness check — regenerate and `git diff` — lives only in `scripts/verify_python.sh`, which
lanes do not run, so no `check_*.py` could see route drift.

A full regeneration is slow and writes files. The operation set alone — every (METHOD, path)
the app serves — is cheap, read-only, and would have caught that day's drift. It does NOT
compare schemas: a changed response body with an unchanged path is still only caught by the
full regeneration. It says so in its own success line.

The app is built with the SAME settings the exporter uses (`FICHERO_FEATURE_TIER=dev`, a
throwaway `FICHERO_BASE_PATH`), with THIS checkout's `fichero-server/src` first on sys.path so
an editable install pointing at another checkout cannot answer for this one (#4699).

Exit codes:
    0  every contract lists exactly the operations the app serves
    1  a contract is missing an operation, or lists one the app no longer serves
    2  BLIND: the app could not be built, or a contract could not be read
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = (
    "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json",
    "fichero-server/tests/contracts/openapi.json",
    "docs/contributor_manual/api-reference/openapi.json",
)
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class Blind(Exception):
    """An input could not be read or built. The check has gone blind; it has not passed."""


def operations(paths: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in paths.items()
        if isinstance(item, dict)
        for method in item
        if method in HTTP_METHODS
    }


def contract_operations(path: Path) -> set[tuple[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return operations(payload["paths"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise Blind(f"cannot read the operations of {path}: {exc}") from exc


def code_operations(root: Path = ROOT) -> set[tuple[str, str]]:
    os.environ["FICHERO_FEATURE_TIER"] = "dev"
    os.environ.setdefault("FICHERO_BASE_PATH", tempfile.mkdtemp(prefix="fichero-route-set-"))
    sys.path.insert(0, str(root / "fichero-server" / "src"))
    try:
        from fichero_server.api.main import app
        return operations(app.openapi()["paths"])
    except Exception as exc:  # noqa: BLE001 — any failure to build is blindness, never a pass
        raise Blind(f"cannot build the engine app to read its routes: {exc!r}") from exc


def drift(code: set, contract: set) -> tuple[list, list]:
    """(served but not in the contract, in the contract but no longer served)."""
    return sorted(code - contract), sorted(contract - code)


def check(root: Path = ROOT, code: set | None = None) -> int:
    code = code_operations(root) if code is None else code
    if not code:
        raise Blind("the app served zero operations — the build is not the engine")
    failed = False
    for relative in CONTRACTS:
        added, removed = drift(code, contract_operations(root / relative))
        if not added and not removed:
            print(f"  [ok] {relative}")
            continue
        failed = True
        print(f"  [STALE] {relative}")
        for method, path in added:
            print(f"      + {method} {path}   (served, not in the contract)")
        for method, path in removed:
            print(f"      - {method} {path}   (in the contract, no longer served)")
    if failed:
        print(
            "\nRegenerate the contracts — never hand-edit them (AGENTS.md rule 3):\n"
            "  FICHERO_PYTHON_BIN=/path/to/a/.venv/bin/python \\\n"
            "    ./fichero-server/scripts/sync_openapi_schema.sh"
        )
        return 1
    print(
        f"\nThe route set ({len(code)} operations) matches all {len(CONTRACTS)} contracts. "
        "Schemas are NOT compared here; a changed body on an unchanged path needs the "
        "full regeneration (scripts/verify_python.sh)."
    )
    return 0


def main() -> int:
    try:
        return check()
    except Blind as exc:
        print(f"BLIND: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
