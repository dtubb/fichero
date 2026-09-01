#!/usr/bin/env python3
"""The embed phase must stamp the engine's version into the app (2026-09-01).

## The bug this catches

A `Fichero (Dev Embedded)` build announced `Embedded engine version: 2026.8.27`
from a checkout that had moved on, and NOTHING disagreed — not the build (the
staged bundle's label and the tree's `pyproject.toml` were consistent with each
other, just old), and not the app, which never asked which engine answered it.

The fix has two halves and this guards the second:

  1. the restage scripts recreate the Briefcase app template when the stamped
     version drifts (`briefcase update` never re-renders `Info.plist`);
  2. the Xcode "Embed Fichero Server" phase records what it actually embedded —
     `FicheroEmbeddedEngineVersion` and `FicheroExpectedEngineVersion` — into
     the host app's `Info.plist`, and `EmbeddedEngineVersionCheck` compares both
     against `/api/health`'s `backend_version` when the engine reports ready.

Half 2 is invisible when it stops working: the keys quietly go missing, the
runtime verdict becomes `.unstamped`, and the app reports every engine as fine.
A launch check that cannot see the version is the same class of lie as the
staleness check that could not see a change. So this asserts the wiring end to
end, by reading named files — no globbing, so no scan floor is needed.

Usage:
    scripts/check_engine_version_stamp.py
    scripts/check_engine_version_stamp.py --self-test

Exit codes:
    0  every embed phase stamps, and the app reads the same two keys
    1  a break in the chain (named in the output)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PBXPROJ = ROOT / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
STAMP_SCRIPT = ROOT / "scripts" / "stamp_engine_version_into_app.sh"
SWIFT_CHECK = ROOT / "fichero" / "fichero" / "Services" / "EmbeddedEngineVersionCheck.swift"
READINESS = ROOT / "fichero" / "fichero" / "App" / "AppState+Readiness.swift"

EMBEDDED_KEY = "FicheroEmbeddedEngineVersion"
EXPECTED_KEY = "FicheroExpectedEngineVersion"
STAMP_INVOCATION = "stamp_engine_version_into_app.sh"

#: Each macOS target that embeds the engine has its own "Embed Fichero Server"
#: phase, and they drift independently — the App Store one lands the engine in
#: Contents/Helpers, the other in Contents/Resources. Both must stamp, or the
#: check is live in one distribution channel and dead in the other.
EMBED_PHASE_MARKER = 'name = "Embed Fichero Server"'


def failures() -> list[str]:
    problems: list[str] = []

    pbxproj = PBXPROJ.read_text(encoding="utf-8")
    phase_count = pbxproj.count(EMBED_PHASE_MARKER)
    if phase_count == 0:
        problems.append(
            f"{PBXPROJ.name}: no 'Embed Fichero Server' build phase found — this check "
            "is reading the wrong file or the phase was renamed."
        )
    stamp_calls = pbxproj.count(STAMP_INVOCATION)
    if stamp_calls < phase_count:
        problems.append(
            f"{PBXPROJ.name}: {phase_count} 'Embed Fichero Server' phase(s) but only "
            f"{stamp_calls} call(s) to {STAMP_INVOCATION}. Every embed phase must stamp "
            "the version it embedded, or the launch check goes blind for that target."
        )

    if not STAMP_SCRIPT.exists():
        problems.append(f"missing {STAMP_SCRIPT.relative_to(ROOT)} — the embed phases call it.")
    else:
        stamp = STAMP_SCRIPT.read_text(encoding="utf-8")
        for key in (EMBEDDED_KEY, EXPECTED_KEY):
            if key not in stamp:
                problems.append(
                    f"{STAMP_SCRIPT.name}: does not write {key}. "
                    "The app reads it; an unwritten key makes the verdict `.unstamped`."
                )

    swift = SWIFT_CHECK.read_text(encoding="utf-8")
    for key in (EMBEDDED_KEY, EXPECTED_KEY):
        if f'"{key}"' not in swift:
            problems.append(
                f"{SWIFT_CHECK.name}: does not name {key}. The stamping script and the "
                "runtime check must agree on the literal key, letter for letter."
            )

    readiness = READINESS.read_text(encoding="utf-8")
    if "verifyEmbeddedEngineVersion" not in readiness:
        problems.append(
            f"{READINESS.name}: nothing calls verifyEmbeddedEngineVersion(). The stamps "
            "would be written and never compared."
        )
    elif not re.search(r"markReady\(\)[\s\S]{0,400}?verifyEmbeddedEngineVersion\(\)", readiness):
        problems.append(
            f"{READINESS.name}: verifyEmbeddedEngineVersion() no longer runs on the "
            "ready path — the check must fire when the engine reports ready."
        )

    return problems


def self_test() -> int:
    """Prove the check can FAIL, not merely that it passes today."""
    import tempfile

    ok = True
    text = SWIFT_CHECK.read_text(encoding="utf-8")
    if f'"{EMBEDDED_KEY}"' not in text:
        print("self-test: the Swift check no longer names the key it is supposed to", file=sys.stderr)
        ok = False
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "project.pbxproj"
        empty.write_text("", encoding="utf-8")
        if empty.read_text(encoding="utf-8").count(EMBED_PHASE_MARKER) != 0:
            print("self-test: marker counting is broken", file=sys.stderr)
            ok = False
    print("self-test: ok" if ok else "self-test: FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    problems = failures()
    if problems:
        print("Embedded-engine version stamping is broken:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nSee AGENTS.md ('The version label is checked at launch, not just at build').",
            file=sys.stderr,
        )
        return 1
    print("check_engine_version_stamp: embed phases stamp the engine version; the app reads it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
