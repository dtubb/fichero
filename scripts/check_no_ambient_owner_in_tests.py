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


def count() -> int:
    total = 0
    for path in scan_rglob(ROOT / "fichero-server" / "tests", "*.py"):
        if path.name == "signed_in.py":
            continue
        total += sum(1 for line in path.read_text(errors="ignore").splitlines() if PATTERN.search(line))
    return total


def main() -> int:
    now = count()
    stored = json.loads(BASELINE.read_text())["count"] if BASELINE.exists() else None
    if "--update-baseline" in sys.argv:
        if stored is not None and now > stored:
            print(f"refusing to RAISE the baseline ({stored} -> {now}); sign in with tests/signed_in.py instead")
            return 2
        BASELINE.write_text(json.dumps({"count": now}, indent=2) + "\n")
        print(f"baseline set to {now}")
        return 0
    if stored is None:
        print("no baseline yet: run with --update-baseline")
        return 1
    if now > stored:
        print(f"FAIL: {now} tests act as the ambient owner, baseline {stored}. Use tests/signed_in.py::signed_in_client.")
        return 1
    if now < stored:
        print(f"FAIL: down to {now} (baseline {stored}): lower it with --update-baseline.")
        return 1
    print(f"OK check_no_ambient_owner_in_tests: {now} tests still use the ambient owner (baseline, slice 10 takes it to 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
