#!/usr/bin/env python3
"""AppleScript dictionary (sdef) coverage guardrail (#2286).

Rule (reform master plan §6d 'Quality gates'):

    > The AppleScript scripting dictionary (`Fichero.sdef`) and its Swift
    > implementation must stay in lock-step. Every `<cocoa class="Fichero…">`
    > the dictionary advertises must have a matching Swift class, and every
    > `NSScriptCommand` subclass implemented in Swift must be advertised in the
    > dictionary. Either gap is a silent break: a dictionary command with no
    > class no-ops at runtime; an implemented command absent from the .sdef is
    > unreachable from AppleScript.

Two checks (both directions), pure static analysis:

  (A) Every `<cocoa class="Fichero*">` in the .sdef resolves to a
      `class Fichero*` defined under fichero/fichero/.
  (B) Every `class Fichero*Command: NSScriptCommand` in Swift is referenced as
      a `<cocoa class>` somewhere in the .sdef.

Baseline is CLEAN (KNOWN_VIOLATIONS empty): the dictionary and implementation
agree today. The script fails the moment they drift.

Usage:
    scripts/check_applescript_coverage.py
    scripts/check_applescript_coverage.py --list
    scripts/check_applescript_coverage.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
SDEF = APP_DIR / "Fichero.sdef"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

_COCOA_CLASS_RE = re.compile(r'cocoa\s+class="(Fichero[A-Za-z0-9_]+)"')
_SWIFT_CLASS_RE = re.compile(r"\bclass\s+(Fichero[A-Za-z0-9_]+)")
_SCRIPT_CMD_RE = re.compile(r"\bclass\s+(Fichero[A-Za-z0-9_]+)\s*:\s*NSScriptCommand\b")

# Drift baseline. Empty: the .sdef and Swift agree today.
KNOWN_VIOLATIONS: dict[str, str] = {}


def sdef_cocoa_classes(sdef: Path = SDEF) -> set[str]:
    return set(_COCOA_CLASS_RE.findall(sdef.read_text(errors="ignore")))


def _swift_sources(app_dir: Path) -> str:
    return "\n".join(
        p.read_text(errors="ignore") for p in sorted(app_dir.rglob("*.swift"))
    )


def swift_classes(app_dir: Path = APP_DIR) -> set[str]:
    return set(_SWIFT_CLASS_RE.findall(_swift_sources(app_dir)))


def swift_script_commands(app_dir: Path = APP_DIR) -> set[str]:
    return set(_SCRIPT_CMD_RE.findall(_swift_sources(app_dir)))


def violations(*, sdef: Path = SDEF, app_dir: Path = APP_DIR) -> dict[str, str]:
    advertised = sdef_cocoa_classes(sdef)
    defined = swift_classes(app_dir)
    commands = swift_script_commands(app_dir)

    bad: dict[str, str] = {}
    for name in sorted(advertised - defined):
        bad[f"sdef::{name}"] = f".sdef advertises cocoa class '{name}' with no Swift class"
    for name in sorted(commands - advertised):
        bad[f"swift::{name}"] = (
            f"NSScriptCommand '{name}' is not advertised in the .sdef dictionary"
        )
    return bad


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    if not SDEF.exists():
        print(f"✗ AppleScript dictionary not found: {SDEF}")
        return 1

    advertised = sdef_cocoa_classes()
    commands = swift_script_commands()
    bad = violations()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"sdef cocoa classes ({len(advertised)}): {', '.join(sorted(advertised))}")
        print(f"Swift NSScriptCommands ({len(commands)}): {', '.join(sorted(commands))}")
        for key, reason in sorted(bad.items()):
            tag = "known" if key in known else "GAP"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(bad) - known)
    stale = sorted(known - set(bad))

    print("AppleScript dictionary coverage guardrail (#2286):")
    print(f"  {len(advertised)} advertised cocoa class(es); "
          f"{len(commands)} Swift NSScriptCommand(s); {len(bad)} gap(s).")

    if new:
        print(f"\n  ✗ {len(new)} coverage gap(s):")
        for key in new:
            print(f"      {key}  ←  {bad[key]}")
        print(
            "\nFix: keep Fichero.sdef and the Swift NSScriptCommand/object classes "
            f"in lock-step. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now clean — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ AppleScript dictionary and Swift implementation are in lock-step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
