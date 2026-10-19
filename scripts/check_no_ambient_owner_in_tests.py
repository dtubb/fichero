#!/usr/bin/env python3
"""Pins `multiuser.ambient-owner-leaves-the-tests` (spec: transport/multiuser-always-on): tests stop relying on the
ambient owner (loopback plus the bootstrap token) so slice 10 can remove it.

WARN-MODE RATCHET: it counts the lines in `fichero-server/tests` that act as the owner through the bootstrap token
(`Bearer {bootstrap...}`, `Bearer {initialize_token()}`, `harness.host()`), compares with
`scripts/ambient_owner_in_tests_baseline.json`, and fails ONLY when the count grows. A smaller count asks for
`--update-baseline` (lower-only). New tests sign in with `tests/signed_in.py::signed_in_client` instead. Slice 10
turns the baseline to 0 and the check blocking.

Run:
    python scripts/check_no_ambient_owner_in_tests.py
    python scripts/check_no_ambient_owner_in_tests.py --update-baseline
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from _scan_files import scan_rglob

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "ambient_owner_in_tests_baseline.json"
PATTERN = re.compile(r"Bearer \{[^}]*(bootstrap|initialize_token)|\.host\(\)")


# Tests allowed to act as the ambient owner, by id ("path relative to the repo::test name"). Each is one named
# exception; the ratchet counts it in the total but a NEW unnamed offender cannot hide behind it.
NAMED = {
    "fichero-server/tests/unit/security/test_embedded_set_up_end_to_end_to_spec.py::"
    "test_the_shipped_embedded_path_with_the_bootstrap_bearer": (
        "shipped embedded path (bootstrap bearer, first-run 409 -> migrate-owner -> sign-in -> Set Up/Start); "
        "delete at slice 10"
    ),
}


def _named_lines(root: pathlib.Path) -> tuple[int, list[str]]:
    """Pattern lines inside the named tests, and the named ids that no longer exist."""
    lines, missing = 0, []
    for test_id in NAMED:
        path, name = test_id.split("::")
        file = root / path
        body: list[str] = []
        inside = False
        for line in file.read_text(errors="ignore").splitlines() if file.exists() else []:
            if inside and line and not line[0].isspace():
                break
            if line.startswith(f"def {name}("):
                inside = True
            if inside:
                body.append(line)
        if not body:
            missing.append(test_id)
        lines += sum(1 for line in body if PATTERN.search(line))
    return lines, missing


def scan(root: pathlib.Path = ROOT) -> tuple[int, int, list[str]]:
    """(all pattern lines, those outside the named tests, named ids that vanished)."""
    total = 0
    for path in scan_rglob(root / "fichero-server" / "tests", "*.py"):
        if path.name == "signed_in.py":
            continue
        total += sum(1 for line in path.read_text(errors="ignore").splitlines() if PATTERN.search(line))
    named, missing = _named_lines(root)
    return total, total - named, missing


def verdict(total: int, unnamed: int, missing: list[str], stored: int) -> str | None:
    """None when it passes, else why not. `stored` counts the named tests too; unnamed offenders get the rest."""
    if missing:
        return f"FAIL: named exception no longer exists, drop it from NAMED and lower the baseline: {missing}"
    if total > stored or unnamed > stored - len(NAMED):
        return (
            f"FAIL: {unnamed} unnamed tests act as the ambient owner (allowed {stored - len(NAMED)}; {total} in all, "
            f"baseline {stored}). Use tests/signed_in.py::signed_in_client."
        )
    if total < stored:
        return f"FAIL: down to {total} (baseline {stored}): lower it with --update-baseline."
    return None


def main() -> int:
    total, unnamed, missing = scan()
    stored = json.loads(BASELINE.read_text())["count"] if BASELINE.exists() else None
    if "--update-baseline" in sys.argv:
        if stored is not None and total > stored:
            print(f"refusing to RAISE the baseline ({stored} -> {total}); sign in with tests/signed_in.py instead")
            return 2
        BASELINE.write_text(json.dumps({"count": total}, indent=2) + "\n")
        print(f"baseline set to {total}")
        return 0
    if stored is None:
        print("no baseline yet: run with --update-baseline")
        return 1
    why = verdict(total, unnamed, missing, stored)
    if why:
        print(why)
        return 1
    print(
        f"OK check_no_ambient_owner_in_tests: {total} tests use the ambient owner ({len(NAMED)} named, "
        "baseline; slice 10 takes it to 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
