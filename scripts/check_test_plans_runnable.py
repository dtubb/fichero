#!/usr/bin/env python3
"""A test plan must be able to run, on the platform it claims, with tests in it (#4472).

`fichero/fichero-ipad.xctestplan` existed for a month and never once ran. It was
created deliberately EMPTY — zero testTargets — as a build/install/launch smoke
gate, which reports TEST SUCCEEDED having executed nothing. A later commit noticed
"a plan with no targets can never fail" and put `FicheroTests` in it. That target
inherits SDKROOT=macosx from the project and declares no SUPPORTED_PLATFORMS, so
the plan went from silently-green to hard-refusing to run:

    Cannot test target "FicheroTests" on "iPad Pro 13-inch (M5)":
    FicheroTests does not support iPad Pro 13-inch (M5)

Both states are the same defect wearing different clothes: a mechanism that looks
like assurance and measures nothing. Nothing in the repo could tell you either
one was true, because a `.xctestplan` is inert JSON — it names a target by UUID
and nobody checks the UUID resolves, that the name beside it is the target's real
name, that the target's platforms include the plan's, or that any test survives
the plan's own selectedTests/skippedTests filtering.

This check reads the plans and `project.pbxproj` and asserts all four. It is
static: it proves a plan is CAPABLE of running. Only a real device or simulator
run proves the tests pass.

BLOCKED is not an excuse list. An entry means "known unrunnable, filed, and the
guard is watching it" — and the guard fails just as loudly when a BLOCKED plan
starts passing (stale entry) as when an unlisted plan breaks. An allowlist that
cannot go stale is a record; one that can is a mute button.

Run: python3 scripts/check_test_plans_runnable.py [--self-test]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _check_floor import require_scan_floor  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PLAN_DIR = REPO / "fichero"
PROJ = REPO / "fichero/fichero.xcodeproj/project.pbxproj"

# Which platforms each plan claims to run on. A plan that is not listed FAILS:
# a new plan must be classified, because "we forgot to say" and "macOS" must not
# share a verdict — that assumption is exactly how the iPad plan went unnoticed.
PLAN_PLATFORMS: dict[str, set[str]] = {
    "fichero.xctestplan": {"macosx"},
    "fichero-tests.xctestplan": {"macosx"},
    "fichero-embedded.xctestplan": {"macosx"},
    "fichero-ipad.xctestplan": {"iphonesimulator"},
}

# Plans known to be unrunnable, keyed to the issue that must land first.
#
# EMPTY, and that is the point of the entry that used to be here. The iPad plan
# was blocked on #4472 because no test target in the project supported iPadOS —
# FicheroTests and FicheroUITests both inherit SDKROOT=macosx and declare no
# SUPPORTED_PLATFORMS. `FicheroIPadTests` now does, so the entry is gone rather
# than kept "just in case": this guard fails just as loudly on a stale BLOCKED
# entry as on an unlisted broken plan, because an allowlist that cannot go stale
# is a record and one that can is a mute button.
BLOCKED: dict[str, str] = {}

# An SDKROOT with no SUPPORTED_PLATFORMS override implies this platform set.
SDK_PLATFORMS: dict[str, set[str]] = {
    "macosx": {"macosx"},
    "iphoneos": {"iphoneos", "iphonesimulator"},
    "appletvos": {"appletvos", "appletvsimulator"},
    "watchos": {"watchos", "watchsimulator"},
}


def load_objects(proj: Path) -> dict:
    """project.pbxproj is an old-style plist; plutil converts it to JSON for us."""
    raw = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", str(proj)],
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(raw)["objects"]


def project_settings(objects: dict) -> dict:
    """Build settings on the PBXProject itself — what every target inherits."""
    project = next(o for o in objects.values() if o.get("isa") == "PBXProject")
    lst = objects[project["buildConfigurationList"]]["buildConfigurations"]
    merged: dict = {}
    for cfg in lst:
        merged.update(objects[cfg].get("buildSettings", {}))
    return merged


def target_configs(objects: dict, target: dict) -> dict[str, dict]:
    lst = objects[target["buildConfigurationList"]]["buildConfigurations"]
    return {objects[c]["name"]: objects[c].get("buildSettings", {}) for c in lst}


def platforms_of(settings: dict, inherited: dict) -> set[str] | None:
    """Effective platform set for one build configuration, or None if unknowable."""
    supported = settings.get("SUPPORTED_PLATFORMS") or inherited.get("SUPPORTED_PLATFORMS")
    if supported:
        return set(str(supported).split())
    sdk = settings.get("SDKROOT") or inherited.get("SDKROOT")
    if not sdk:
        return None
    return SDK_PLATFORMS.get(str(sdk))


def native_targets(objects: dict) -> dict[str, dict]:
    """Native targets by their pbxproj object id — the id a test plan stores."""
    return {k: v for k, v in objects.items() if v.get("isa") == "PBXNativeTarget"}


def audit_plan(name: str, plan: dict, objects: dict) -> list[str]:
    """Everything wrong with one plan. Empty list means it is capable of running."""
    problems: list[str] = []
    targets = native_targets(objects)
    inherited = project_settings(objects)

    wanted = PLAN_PLATFORMS.get(name)
    if wanted is None:
        return [
            f"{name} is not classified in PLAN_PLATFORMS — say which platform(s) it "
            "runs on. A plan nobody classified is a plan nobody has run."
        ]

    entries = [t for t in plan.get("testTargets", []) if t.get("enabled", True)]
    if not entries:
        problems.append(
            f"{name} has no enabled test targets. `xcodebuild test` still builds, "
            "installs and launches the app, then reports TEST SUCCEEDED having "
            "executed zero tests — use a `build` action if that is what you want."
        )

    for entry in entries:
        ref = entry.get("target", {})
        ident, claimed = ref.get("identifier"), ref.get("name")
        target = targets.get(ident)
        if target is None:
            problems.append(
                f"{name} names target {claimed!r} ({ident}) which is not a native "
                "target in project.pbxproj — Xcode resolves by identifier, so this "
                "plan cannot run at all."
            )
            continue
        real = target.get("name")
        if real != claimed:
            problems.append(
                f"{name} calls {ident} {claimed!r} but the project calls it {real!r} "
                "— the human-readable half of the reference is a lie."
            )
        # Configurations are grouped by the platform set they resolve to: a target
        # with eight configurations that are all macOS-only is one defect, not eight.
        by_platforms: dict[tuple[str, ...] | None, list[str]] = {}
        for cfg_name, settings in sorted(target_configs(objects, target).items()):
            got = platforms_of(settings, inherited)
            key = None if got is None else tuple(sorted(got))
            by_platforms.setdefault(key, []).append(cfg_name)
        for key, cfgs in by_platforms.items():
            where = ", ".join(cfgs)
            if key is None:
                problems.append(
                    f"{name}: target {real!r} configuration(s) {where} declare "
                    "neither SUPPORTED_PLATFORMS nor a resolvable SDKROOT — their "
                    "platform support cannot be established."
                )
            elif not wanted <= set(key):
                problems.append(
                    f"{name} runs on {sorted(wanted)} but target {real!r} supports "
                    f"{list(key)} in configuration(s) {where} — missing "
                    f"{sorted(wanted - set(key))}. The plan cannot run on the "
                    "platform it is named for."
                )
        if "selectedTests" in entry and not entry["selectedTests"]:
            problems.append(
                f"{name}: target {real!r} has an empty selectedTests list, which "
                "selects nothing — the plan resolves to zero tests and passes."
            )
    return problems


def reconcile(
    results: dict[str, list[str]], blocked: dict[str, str]
) -> tuple[list[tuple[str, str, list[str]]], list[str]]:
    """Split audit results into (still-blocked, hard failures).

    This is where BLOCKED earns its keep or becomes a mute button, so it is a
    pure function with a fixture: a listed plan that passes, and a listed plan
    that has vanished, are BOTH failures.
    """
    known: list[tuple[str, str, list[str]]] = []
    hard: list[str] = []
    for name, problems in sorted(results.items()):
        issue = blocked.get(name)
        if problems and issue:
            known.append((name, issue, problems))
        elif problems:
            hard.extend(problems)
        elif issue:
            hard.append(
                f"{name} is listed in BLOCKED for {issue} but now passes every check — "
                "remove the entry and close the issue. A stale allowlist is how a fixed "
                "defect keeps its exemption forever."
            )
    for name in blocked:
        if name not in results:
            hard.append(f"BLOCKED lists {name}, which no longer exists — drop the entry.")
    return known, hard


def _self_test() -> None:
    """Prove each rule FIRES. A guard never observed to fail is not a guard."""
    objects = {
        "P": {"isa": "PBXProject", "buildConfigurationList": "PL"},
        "PL": {"buildConfigurations": ["PC"]},
        "PC": {"name": "Release", "buildSettings": {"SDKROOT": "macosx"}},
        "MAC": {"isa": "PBXNativeTarget", "name": "MacOnly", "buildConfigurationList": "ML"},
        "ML": {"buildConfigurations": ["MC"]},
        "MC": {"name": "Release", "buildSettings": {}},
        "ANY": {"isa": "PBXNativeTarget", "name": "Portable", "buildConfigurationList": "AL"},
        "AL": {"buildConfigurations": ["AC"]},
        "AC": {
            "name": "Release",
            "buildSettings": {"SUPPORTED_PLATFORMS": "iphonesimulator macosx"},
        },
    }

    def plan(*entries: dict) -> dict:
        return {"testTargets": list(entries)}

    mac_ref = {"target": {"identifier": "MAC", "name": "MacOnly"}}
    any_ref = {"target": {"identifier": "ANY", "name": "Portable"}}
    saved = dict(PLAN_PLATFORMS)
    PLAN_PLATFORMS["ipad.xctestplan"] = {"iphonesimulator"}
    PLAN_PLATFORMS["mac.xctestplan"] = {"macosx"}
    try:
        cases = [
            ("unclassified", "nope.xctestplan", plan(any_ref), "not classified"),
            ("empty plan", "mac.xctestplan", plan(), "no enabled test targets"),
            (
                "all targets disabled",
                "mac.xctestplan",
                plan({**any_ref, "enabled": False}),
                "no enabled test targets",
            ),
            (
                "dangling identifier",
                "mac.xctestplan",
                plan({"target": {"identifier": "GONE", "name": "Ghost"}}),
                "not a native target",
            ),
            (
                "name disagrees with the project",
                "mac.xctestplan",
                plan({"target": {"identifier": "ANY", "name": "Stale"}}),
                "the project calls it",
            ),
            ("wrong platform", "ipad.xctestplan", plan(mac_ref), "cannot run on the platform"),
            (
                "selects nothing",
                "mac.xctestplan",
                plan({**any_ref, "selectedTests": []}),
                "resolves to zero tests",
            ),
        ]
        for label, name, body, needle in cases:
            found = audit_plan(name, body, objects)
            assert any(needle in p for p in found), (
                f"self-test {label!r}: expected a problem mentioning {needle!r}, got {found}"
            )
        clean = audit_plan("ipad.xctestplan", plan(any_ref), objects)
        assert not clean, f"self-test: a runnable plan was flagged: {clean}"
        clean = audit_plan("mac.xctestplan", plan(mac_ref, any_ref), objects)
        assert not clean, f"self-test: a runnable macOS plan was flagged: {clean}"

        # BLOCKED must not be able to become a mute button.
        known, hard = reconcile({"a": ["broken"]}, {"a": "#1"})
        assert known and not hard, f"a filed, still-broken plan must not fail: {hard}"
        _, hard = reconcile({"a": []}, {"a": "#1"})
        assert any("now passes" in h for h in hard), "a fixed BLOCKED plan must fail as stale"
        _, hard = reconcile({}, {"a": "#1"})
        assert any("no longer exists" in h for h in hard), "a vanished BLOCKED plan must fail"
        _, hard = reconcile({"b": ["broken"]}, {})
        assert hard == ["broken"], "an unlisted broken plan must fail"
    finally:
        PLAN_PLATFORMS.clear()
        PLAN_PLATFORMS.update(saved)


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    _self_test()
    if "--self-test" in argv:
        print("check_test_plans_runnable self-test: OK — all eleven rules fire.")
        return 0

    plans = sorted(p for p in PLAN_DIR.glob("*.xctestplan")) if PLAN_DIR.is_dir() else []
    # #4487 scan floor on the PLAN population, not on the problems found: four
    # plans on 2026-08-03, and the goal state is zero problems, so a collapsed
    # glob must not look like success.
    require_scan_floor(len(plans), 2, "xctestplan files under fichero/ (4 on 2026-08-03)")
    if not PROJ.is_file():
        print(f"BLIND: {PROJ} is missing — no targets to resolve against.", file=sys.stderr)
        return 2

    objects = load_objects(PROJ)
    require_scan_floor(len(native_targets(objects)), 2, "native targets in project.pbxproj")

    print(f"Test plans: {len(plans)} plan(s) checked against {PROJ.name}.")

    results = {
        path.name: audit_plan(path.name, json.loads(path.read_text()), objects)
        for path in plans
    }
    blocked, broken = reconcile(results, BLOCKED)

    for name, issue, problems in blocked:
        print(f"  ~ {name}: known unrunnable, {issue} — {len(problems)} problem(s):")
        for p in problems:
            print(f"      {p}")

    if broken:
        print(f"\nTest plan check FAILED — {len(broken)} problem(s):\n")
        for b in broken:
            print(f"  ✗ {b}")
        return 1

    runnable = len(plans) - len(blocked)
    print(f"  ✓ {runnable} plan(s) name real targets that support their platform and hold tests.")
    if blocked:
        print(f"  ~ {len(blocked)} plan(s) known-unrunnable and filed; this guard watches them.")
    print(INVOCATIONS)
    return 0


#: How to actually RUN each plan. Printed on success because this is where
#: somebody checking "can the iPad plan run" is already looking, and the first
#: person to try had to find the working invocation by trial: the plan was
#: associated with the MAC schemes only, so `-scheme "…iOS"` failed outright and
#: the only way through was borrowing a Mac scheme with an iPad destination
#: (#4505). A plan that is runnable and undiscoverable is barely better than one
#: that is not runnable.
INVOCATIONS = """
  To run them:
    iPad   xcodebuild test -project fichero/fichero.xcodeproj \\
             -scheme 'Fichero (Dev Local iOS)' -testPlan fichero-ipad \\
             -destination 'platform=iOS Simulator,name=iPad Pro 13-inch (M5)'
    Mac    xcodebuild test -project fichero/fichero.xcodeproj \\
             -scheme 'Fichero (Dev Local)' -testPlan fichero-tests \\
             -destination 'platform=macOS'

  The simulator NAME is machine-specific and goes stale with every Xcode
  release — this one was verified against `xcrun simctl list devices available
  | grep iPad` rather than guessed, because the first draft of this line said
  M4 and no such device exists here. If the destination is rejected, list them
  again; do not assume the plan is broken.

  The iOS schemes' TEST action builds Debug, not Alpha: `@testable import`
  needs ENABLE_TESTABILITY, which only Debug and Dev Embedded set. Alpha, Beta
  and Release are distribution configurations and must stay untestable."""


if __name__ == "__main__":
    raise SystemExit(main())
