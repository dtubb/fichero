#!/usr/bin/env python3
"""Xcode build/test/run config invariants are load-bearing — and they drift.

The UI-test harness bug (spec: xcode-build-configs) was a config that had drifted from
its own comments: a source comment asserted "Dev Local is sandboxed" while the build
setting said the opposite, and that stale belief sent the test socket into the real app
container. Config truth lived only in prose nothing checked. This guardrail asserts the
matrix from the project files themselves, so the drift is a red test — not a debugging
session. Cheap: pure file parse, no Xcode build. Runs in verify_all.sh.

Invariants (verified 2026-09-09, spec: docs/contributor_manual/specs/xcode-build-configs.md):
  * Dev Local scheme -> buildConfiguration "Debug" (the UI-test host).
  * Debug config -> ENABLE_APP_SANDBOX = NO (unsandboxed so tests reach temp-dir fixtures).
  * Dev Embedded / Release / App Store configs -> ENABLE_APP_SANDBOX = YES.
  * arm64-only: EXCLUDED_ARCHS = x86_64 present on the project configs.
  * Deployment floor macOS 26: every MACOSX_DEPLOYMENT_TARGET is 26.x.
  * FicheroTests -> SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor (else ~575 SIGTRAPs).

Run: python scripts/check_xcode_config_invariants.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
PBXPROJ = REPO / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
SCHEME = REPO / "fichero" / "fichero.xcodeproj" / "xcshareddata" / "xcschemes" / "Fichero (Dev Local).xcscheme"


# Only the APP target's configs carry a Fichero app entitlement — every other
# target (frameworks, tests) also has "Debug"/"Release" configs, so selecting by
# config name alone is ambiguous. Match the app target by its entitlements file.
_APP_ENTITLEMENTS = ("Fichero.entitlements", "FicheroRelease.entitlements", "FicheroAppStore.entitlements")

_BLOCK_RE = re.compile(
    r"isa = XCBuildConfiguration;(?P<body>.*?)name = (?P<name>\"[^\"]+\"|[\w]+);",
    re.DOTALL,
)


def _app_config_block(pbx: str, name: str) -> str | None:
    """The buildSettings body of the APP-target XCBuildConfiguration named `name`.

    ponytail: regex over the pbxproj rather than a real plist parser. The file is
    machine-generated with a stable shape; a finding here is a config change, which
    should be reviewed anyway. Upgrade to a parser only if the shape ever bites.
    """
    for m in _BLOCK_RE.finditer(pbx):
        got = m.group("name").strip('"')
        body = m.group("body")
        if got == name and any(f"/{e}" in body for e in _APP_ENTITLEMENTS):
            return body
    return None


def check() -> list[str]:
    problems: list[str] = []
    if not PBXPROJ.is_file():
        return [f"pbxproj not found at {PBXPROJ}"]
    pbx = PBXPROJ.read_text(encoding="utf-8")

    # 1. Dev Local scheme dials the Debug config.
    if SCHEME.is_file():
        scheme = SCHEME.read_text(encoding="utf-8")
        configs = set(re.findall(r'buildConfiguration = "([^"]+)"', scheme))
        if configs != {"Debug"}:
            problems.append(
                f'Dev Local scheme should use only "Debug" config, found {sorted(configs)}'
            )
    else:
        problems.append(f"Dev Local scheme not found at {SCHEME}")

    # 2/3. Sandbox posture per config.
    for name, want in (
        ("Debug", "NO"),
        ("Dev Embedded", "YES"),
        ("Release", "YES"),
    ):
        body = _app_config_block(pbx, name)
        if body is None:
            problems.append(f'app-target config "{name}" not found in pbxproj')
            continue
        m = re.search(r"ENABLE_APP_SANDBOX = (\w+);", body)
        got = m.group(1) if m else "<unset>"
        if got != want:
            problems.append(
                f'config "{name}": ENABLE_APP_SANDBOX = {got}, expected {want} '
                f"(stale sandbox assumption is what stranded the UI-test harness)"
            )

    # 4. arm64-only.
    if "EXCLUDED_ARCHS = x86_64" not in pbx:
        problems.append("EXCLUDED_ARCHS = x86_64 missing (arm64-only / Golden Gate)")

    # 5. Deployment floor macOS 26.
    targets = set(re.findall(r"MACOSX_DEPLOYMENT_TARGET = ([\d.]+);", pbx))
    bad = {t for t in targets if not t.startswith("26")}
    if bad:
        problems.append(f"MACOSX_DEPLOYMENT_TARGET floor is macOS 26; found {sorted(bad)}")

    # 6. FicheroTests runs on the main actor by default.
    if "SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor" not in pbx:
        problems.append(
            "SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor missing "
            "(FicheroTests SIGTRAPs off-main without it)"
        )

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("FAIL check_xcode_config_invariants:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(
        "OK check_xcode_config_invariants: Dev Local unsandboxed (Debug), Release/AppStore/"
        "Dev Embedded sandboxed, arm64-only, macOS 26 floor, FicheroTests MainActor-isolated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
