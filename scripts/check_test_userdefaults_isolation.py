#!/usr/bin/env python3
"""Guardrail: tests must never touch the developer's real preference domain.

In a test host, `UserDefaults.standard` IS `app.fichero.fichero` — the domain
the running app reads. Tests writing it repointed a live app at
`https://second.tailnet.example`, a reserved name that can never resolve, so the
user saw "Couldn't Load Documents" and blamed the engine. It happened twice in
one day before anyone connected it to the test suite (#4221).

Snapshot-and-restore in `tearDown` did NOT prevent it and is not accepted here:
a killed process never reaches teardown, and on a loaded machine most runs die
that way. Tests go through `EngineConfig.defaults`, which resolves to a
throwaway suite inside a test process.

SCOPE — deliberately `fichero-tests/` and `fichero-ui-tests/` ONLY, and that
scope has a KNOWN HOLE worth stating plainly.

This check reports 0 violations while a test can still write the real domain,
because the write may come from PRODUCTION code the test drives. That is not
hypothetical: `RemoteClientPairing.rollbackFailedHostSwitch` wrote
`previousHost` to `UserDefaults.standard`, a test exercised the rollback path,
and Daniel's engine host was clobbered — with this check green throughout.

So a pass here means "no test file writes the real domain directly". It does
NOT mean "a test run leaves the real domain untouched". The only thing that
demonstrates the latter is running the suite and diffing the keys afterwards.


The 105 production sites reading `UserDefaults.standard` are correct: the app
SHOULD read its own domain. The defect is tests writing it, because a test host
shares that domain with the running app. Do not widen this into a production
sweep — it would flag the intended behaviour and get the check disabled.

Usage:
    scripts/check_test_userdefaults_isolation.py
    scripts/check_test_userdefaults_isolation.py --selftest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "fichero" / "fichero-tests"
UI_TESTS = ROOT / "fichero" / "fichero-ui-tests"

# Per-entry, with a reason. A file here is a decision, not an oversight.
ALLOWLIST: dict[str, str] = {
    # Documents the hazard in prose; the string appears only in comments.
    "TestDefaults.swift": "defines the isolation seam and explains it in comments",
}

PATTERN = re.compile(r"UserDefaults\s*\.\s*standard")
COMMENT = re.compile(r"^\s*(//|///|\*|/\*)")


def offending_lines(path: Path) -> list[tuple[int, str]]:
    """Non-comment lines touching UserDefaults.standard."""
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if COMMENT.match(line):
            continue
        if PATTERN.search(line):
            hits.append((number, line.strip()))
    return hits


def scan() -> dict[Path, list[tuple[int, str]]]:
    found: dict[Path, list[tuple[int, str]]] = {}
    for directory in (TESTS, UI_TESTS):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.swift")):
            if path.name in ALLOWLIST:
                continue
            hits = offending_lines(path)
            if hits:
                found[path] = hits
    return found


def selftest() -> int:
    """Prove the check FIRES. A guardrail nobody has seen fail is a guess."""
    probe = TESTS / "__guardrail_selftest__.swift"
    probe.write_text("let x = UserDefaults.standard.string(forKey: \"k\")\n", encoding="utf-8")
    try:
        found = scan()
        if probe not in found:
            print("SELFTEST FAILED: planted violation was not detected")
            return 1
        # A commented occurrence must NOT trip it, or every explanatory note
        # becomes a violation and the check gets disabled.
        probe.write_text("// UserDefaults.standard is what this file must avoid\n", encoding="utf-8")
        if probe in scan():
            print("SELFTEST FAILED: a comment was reported as a violation")
            return 1
    finally:
        probe.unlink(missing_ok=True)
    print("SELFTEST PASSED: detects a real write, ignores a comment")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    found = scan()
    print(f"UserDefaults isolation: scanned {TESTS.name} + {UI_TESTS.name}")
    if not found:
        print(f"  0 violations; {len(ALLOWLIST)} allowlisted.")
        print("\nPASS tests do not touch the real preference domain.")
        return 0

    total = sum(len(v) for v in found.values())
    print(f"\n{total} test line(s) touch UserDefaults.standard:")
    for path, hits in found.items():
        for number, text in hits:
            print(f"  {path.relative_to(ROOT)}:{number}: {text}")
    print(
        "\nIn a test host this IS the app's own domain, so these writes reach the "
        "developer's running app (#4221). Use `EngineConfig.defaults`, which "
        "resolves to a throwaway suite under test."
    )
    return 1


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(TESTS, UI_TESTS)
    raise SystemExit(main())
