#!/usr/bin/env python3
"""The non-MAS embed phase SIGNS the engine with the sandbox pair (D rung 1).

Until 2026-08-08 that phase copied the engine without signing it, so the
entitlements file existed and applied to nothing: the engine ran outside the
app's sandbox identity (every app-scoped bookmark unresolvable, 259) and
under Briefcase's hardened-runtime signature with no entitlements (pdfium
dlopen refused, #4555). This check pins the signing line so a phase rewrite
cannot silently drop it again.

Exit codes: 0 pass · 1 the signing line is gone · 2 BLIND (phase not found —
the parser cannot judge, which must never read as success).

Usage: python3 scripts/check_embedded_engine_signing.py [--self-test]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PBXPROJ = REPO_ROOT / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
PHASE_ID = "CC0011223344556677889903"  # the non-MAS "Embed Fichero Server"
REQUIRED = [
    # The sign itself, with the pair file, on the copied engine bundle.
    'codesign --force --sign \\"$IDENTITY\\" --entitlements \\"$ENGINE_ENTITLEMENTS\\" \\"$ENGINE_DST\\"',
    "FicheroEngineAppStore.entitlements",
    # The two assertions that make a bad signature fail the BUILD.
    "com.apple.security.inherit",
    "com.apple.security.get-task-allow",
]


def phase_text(pbxproj_text: str) -> str | None:
    start = pbxproj_text.find(f"{PHASE_ID} /* Embed Fichero Server */ = {{")
    if start < 0:
        return None
    end = pbxproj_text.find("/* End PBXShellScriptBuildPhase section */", start)
    return pbxproj_text[start : end if end > 0 else start + 40000]


def missing_requirements(text: str) -> list[str]:
    return [needle for needle in REQUIRED if needle not in text]


def self_test() -> None:
    signed = (
        f"{PHASE_ID} /* Embed Fichero Server */ = {{\n"
        '  "codesign --force --sign \\"$IDENTITY\\" --entitlements \\"$ENGINE_ENTITLEMENTS\\" \\"$ENGINE_DST\\"",\n'
        '  "ENGINE_ENTITLEMENTS=${SRCROOT}/fichero/FicheroEngineAppStore.entitlements",\n'
        '  "grep com.apple.security.inherit",\n'
        '  "grep com.apple.security.get-task-allow",\n'
    )
    assert missing_requirements(phase_text(signed) or "") == []

    unsigned = f'{PHASE_ID} /* Embed Fichero Server */ = {{\n  "cp -R engine",\n'
    fired = missing_requirements(phase_text(unsigned) or "")
    assert fired, "check failed to fire on a phase with the signing removed"

    assert phase_text("no such phase here") is None, "blindness must be detectable"
    print("[ok] self-test: fires when the signing line is removed; blind is distinct")


def main() -> None:
    if "--self-test" in sys.argv[1:]:
        self_test()
        return

    text = phase_text(PBXPROJ.read_text())
    if text is None:
        print(f"BLIND: phase {PHASE_ID} not found in {PBXPROJ} — cannot judge")
        sys.exit(2)
    missing = missing_requirements(text)
    if missing:
        print("FAIL: the non-MAS embed phase no longer signs the engine correctly (D rung 1).")
        print("An unsigned engine cannot resolve app-scoped bookmarks (259) and cannot")
        print("load runtime dylibs under its inherited hardened signature (#4555).")
        for needle in missing:
            print(f"  missing: {needle}")
        sys.exit(1)
    print("[ok] non-MAS embed phase signs the engine with the sandbox pair and asserts it")


if __name__ == "__main__":
    main()
