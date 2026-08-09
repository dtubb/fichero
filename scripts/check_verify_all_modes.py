#!/usr/bin/env python3
"""Guardrail for the top-level verification gate and manual smoke docs.

This stays intentionally cheap: it checks that `scripts/verify_all.sh` keeps the
documented fast/standard/full tiers, exposes opt-in macOS/iOS platform legs, and
advertises the environment overrides that let callers request those legs without
switching the whole gate to `--full`.

It also verifies that the manual remote-pairing and capture smoke checklists
exist and still cover the expected end-to-end steps.

Usage:
    scripts/check_verify_all_modes.py
    scripts/check_verify_all_modes.py --list
    scripts/check_verify_all_modes.py --help
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY_ALL = ROOT / "scripts" / "verify_all.sh"
CHECKLIST = ROOT / "docs" / "contributor" / "qa" / "remote-pairing-smoke-checklist.md"
CAPTURE_MATRIX = ROOT / "docs" / "contributor" / "qa" / "capture-smoke-matrix.md"


def _read(path: Path) -> str:
    """Non-optional (#4487 Phase 3): every path handed here is a NAMED,
    COMMITTED file. `"" if missing` turned a moved file into a wall of
    'missing needle' violations — false accusations, not blindness."""
    if not path.exists():
        print(
            f"BLIND: named source missing: {path} (#4487 Phase 3)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return path.read_text(errors="ignore")


def _require_all(haystack: str, needles: list[str], label: str) -> list[str]:
    missing = [needle for needle in needles if needle not in haystack]
    if missing:
        return [f"{label}: missing {needle!r}" for needle in missing]
    return []


def scan() -> dict[str, str]:
    issues: dict[str, str] = {}

    verify_all_text = _read(VERIFY_ALL)
    checklist_text = _read(CHECKLIST).lower()

    verify_all_checks = [
        'tier="fast"',
        "--fast|--standard|--full",
        "--macos",
        "--ios",
        "VERIFY_ALL_MACOS",
        "VERIFY_ALL_IOS",
        'if [[ "$tier" == "full" && "$run_macos" -eq 0 && "$run_ios" -eq 0 ]]; then',
        "run_platform_checks",
        # A skipped Swift leg must be STATED in the summary, not silent —
        # otherwise a routine bare run reads as a whole one (#42 gate audit).
        "Swift (macOS) test leg NOT RUN",
        "iOS compile leg NOT RUN",
    ]
    for issue in _require_all(verify_all_text, verify_all_checks, "scripts/verify_all.sh"):
        issues[f"verify_all::{issue}"] = issue

    checklist_checks = [
        "mac host app opens, backend connected",
        "remote access enabled",
        "qr shown directly in settings",
        "ipad/iphone scans qr",
        "pairing succeeds",
        "reconnect works",
        "content loads from configured remote host",
        "no silent localhost fallback",
    ]
    if not CHECKLIST.exists():
        issues["docs/contributor/qa/remote-pairing-smoke-checklist.md"] = "manual smoke checklist file is missing"
    else:
        for phrase in checklist_checks:
            if phrase not in checklist_text:
                issues[f"docs/contributor/qa/remote-pairing-smoke-checklist.md::{phrase}"] = (
                    f"missing checklist step: {phrase}"
                )

    if not CAPTURE_MATRIX.exists():
        issues["docs/contributor/qa/capture-smoke-matrix.md"] = "capture smoke matrix file is missing"
    else:
        capture_text = _read(CAPTURE_MATRIX).lower()
        capture_checks = [
            "offline photo capture",
            "reconnect upload",
            "watched-folder or dslr intake",
            "provenance",
            "citation",
            "no backend at launch",
        ]
        for phrase in capture_checks:
            if phrase not in capture_text:
                issues[f"docs/contributor/qa/capture-smoke-matrix.md::{phrase}"] = (
                    f"missing capture smoke step: {phrase}"
                )

    return issues


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    issues = scan()

    if "--list" in sys.argv[1:]:
        print(f"verify_all + smoke checklist issues ({len(issues)}):\n")
        for key, reason in sorted(issues.items()):
            print(f"  {key}  <-  {reason}")
        return 0

    print("verify_all mode/configuration guardrail")
    print(f"  scripts/verify_all.sh: {VERIFY_ALL.relative_to(ROOT)}")
    print(f"  smoke checklist: {CHECKLIST.relative_to(ROOT)}")
    print(f"  capture matrix: {CAPTURE_MATRIX.relative_to(ROOT)}")
    print(f"  {len(issues)} issue(s) found.")

    if issues:
        print("\nFAIL Verification gate or smoke checklist drift detected:")
        for key, reason in sorted(issues.items()):
            print(f"  {key}  <-  {reason}")
        return 1

    print("\nPASS verify_all modes and manual smoke checklists are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
