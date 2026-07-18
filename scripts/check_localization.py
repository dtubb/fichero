#!/usr/bin/env python3
r"""Localization guardrail (#2287).

Rule (reform master plan §6d 'Quality gates'):

    > No hard-coded user-facing strings — they go through the localization
    > machinery (`String(localized:)` / `LocalizedStringKey` / string catalog).

In SwiftUI the localization machinery is `LocalizedStringKey`: `Text("Save")`,
`Button("Save")`, `Label("Save", …)`, `.navigationTitle("…")` and interpolated
`Text("Found \(n)")` ALL participate automatically — they produce catalog keys
(`"Save"`, `"Found %lld"`). They are NOT hard-coded escapes.

The ONE SwiftUI escape hatch that bypasses localization is `Text(verbatim:)`
(and the matching `LocalizedStringKey`-free `verbatim:` initialisers). A
`Text(verbatim: "Delete project")` ships an untranslatable user-facing string.
Legitimate verbatim use is for *data* (a filename, a number, a code token) — not
prose. This guardrail bans verbatim strings that contain prose (two+ consecutive
letters / a space between words) so the escape hatch can't silently reintroduce
hard-coded UI copy.

Scope note: enforcing that *non-View* user-facing strings (alerts/errors built in
stores/services) go through `String(localized:)` is deferred until the
localization infrastructure #1396 lands a string catalog — flagged in
WORKER-REPORT.md. This check holds the SwiftUI surface at a CLEAN zero baseline
today (no verbatim prose) so it never regresses.

Escape: append `// localization:allow <reason>` on the line for a legitimate
verbatim prose string (e.g. a fixed brand string that must never translate).

Usage:
    scripts/check_localization.py
    scripts/check_localization.py --list
    scripts/check_localization.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_VERBATIM_RE = re.compile(r'\bText\(\s*verbatim:\s*"([^"]*)"')
_ALLOW_RE = re.compile(r"//\s*localization:allow")
# Prose = two consecutive letters AND a space-separated word pair, i.e. real
# copy rather than a filename/number/token.
_PROSE_RE = re.compile(r"[A-Za-z]{2,}\s+\S")

KNOWN_VIOLATIONS: dict[str, str] = {}


def _is_prose(literal: str) -> bool:
    return bool(_PROSE_RE.search(literal))


def scan(app_dir: Path = APP_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(app_dir.rglob("*.swift")):
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        if "verbatim:" not in source:
            continue
        source = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
        rel = path.relative_to(app_dir).as_posix()
        for idx, line in enumerate(source.splitlines(), start=1):
            if _ALLOW_RE.search(line):
                continue
            for literal in _VERBATIM_RE.findall(line):
                if _is_prose(literal):
                    found[f"{rel}:{idx}"] = f'Text(verbatim: "{literal[:40]}")'
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"Verbatim prose strings ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print("Localization guardrail (#2287):")
    print(f"  scanned {APP_DIR.relative_to(ROOT)} for Text(verbatim:) prose")
    print(f"  {len(found)} verbatim prose string(s); {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} hard-coded user-facing verbatim string(s):")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: drop `verbatim:` so the string localizes via LocalizedStringKey, "
            "or add `// localization:allow <reason>` if it must never translate. "
            f"Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now clean — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ No hard-coded user-facing verbatim strings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
