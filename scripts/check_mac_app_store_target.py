#!/usr/bin/env python3
"""Guard the Mac App Store channel's invariants (#3748/#3749).

Every rule below is one an App Store upload is REJECTED for, and every one is a
single careless edit away — open the project in Xcode, tick the wrong box, and the
breakage is invisible until an ingestion error comes back hours later. They are
cheap to assert and expensive to discover, so assert them.

The Developer ID / DMG channel is checked too, in the negative: it must KEEP Sparkle
and must NOT define FICHERO_APP_STORE. The two channels diverge on purpose, and a
"fix" that quietly converges them is a regression in the other direction.

Run: python3 scripts/check_mac_app_store_target.py
"""

from __future__ import annotations

import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJ = REPO / "fichero/fichero.xcodeproj/project.pbxproj"
SCHEME = REPO / "fichero/fichero.xcodeproj/xcshareddata/xcschemes/Fichero (App Store).xcscheme"
ENGINE_ENTITLEMENTS = REPO / "fichero/fichero/FicheroEngineAppStore.entitlements"

MAS_TARGET = "Fichero (App Store)"
DMG_TARGET = "Fichero"

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def load_project() -> dict:
    """project.pbxproj is an old-style plist; plutil converts it to JSON for us."""
    raw = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", str(PROJ)],
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(raw)["objects"]


def targets(objects: dict) -> dict[str, dict]:
    return {
        t["name"]: t
        for t in objects.values()
        if t.get("isa") == "PBXNativeTarget" and t.get("name") in (MAS_TARGET, DMG_TARGET)
    }


def spm_products(objects: dict, target: dict) -> list[str]:
    return [objects[p].get("productName") for p in target.get("packageProductDependencies", [])]


def configs(objects: dict, target: dict) -> dict[str, dict]:
    lst = objects[target["buildConfigurationList"]]["buildConfigurations"]
    return {objects[c]["name"]: objects[c]["buildSettings"] for c in lst}


def phase_named(objects: dict, target: dict, name: str) -> dict | None:
    for p in target["buildPhases"]:
        if objects[p].get("name") == name:
            return objects[p]
    return None


def shell_of(phase: dict) -> str:
    script = phase.get("shellScript", "")
    # The repo stores shellScript as a list of lines, not one string.
    return "\n".join(script) if isinstance(script, list) else script


def main() -> int:
    objects = load_project()
    found = targets(objects)

    for name in (MAS_TARGET, DMG_TARGET):
        if name not in found:
            fail(f"target {name!r} is missing from project.pbxproj")
    if failures:
        return report()

    mas, dmg = found[MAS_TARGET], found[DMG_TARGET]

    # 1. Sparkle: absent from MAS at the LINK level, present in the DMG.
    # A #if does not help — a linked framework still ships, and the reviewer sees it.
    if any(p == "Sparkle" for p in spm_products(objects, mas)):
        fail(f"{MAS_TARGET} links Sparkle. The App Store prohibits third-party self-updaters (2.4.5(vii)).")
    if not any(p == "Sparkle" for p in spm_products(objects, dmg)):
        fail(f"{DMG_TARGET} no longer links Sparkle — the DMG channel needs it. Do not converge the channels.")

    # 2. Both app targets compile the SAME sources. A file added to one and not the
    #    other fails to compile in the channel nobody builds by default.
    def source_count(t: dict) -> int:
        for p in t["buildPhases"]:
            if objects[p].get("isa") == "PBXSourcesBuildPhase":
                return len(objects[p]["files"])
        return -1

    if source_count(mas) != source_count(dmg):
        fail(
            f"source lists diverge: {MAS_TARGET} has {source_count(mas)}, {DMG_TARGET} has {source_count(dmg)}. "
            "Add app sources with scripts/add-swift-file.rb, which registers BOTH."
        )

    # 3. Entitlements. MAS uses the sandboxed set; the engine's set is EXACTLY two keys —
    #    com.apple.security.inherit is incompatible with any other App Sandbox key and
    #    the system aborts the child if one is present.
    mas_cfgs = configs(objects, mas)
    for cfg_name, settings in mas_cfgs.items():
        ent = settings.get("CODE_SIGN_ENTITLEMENTS", "")
        if "FicheroAppStore.entitlements" not in ent:
            fail(f"{MAS_TARGET}/{cfg_name} must use FicheroAppStore.entitlements, got {ent!r}")
        if "FICHERO_APP_STORE" not in settings.get("SWIFT_ACTIVE_COMPILATION_CONDITIONS", ""):
            fail(f"{MAS_TARGET}/{cfg_name} is missing the FICHERO_APP_STORE compilation condition")

    for cfg_name, settings in configs(objects, dmg).items():
        if "FICHERO_APP_STORE" in settings.get("SWIFT_ACTIVE_COMPILATION_CONDITIONS", ""):
            fail(f"{DMG_TARGET}/{cfg_name} defines FICHERO_APP_STORE — that condition is the MAS channel's alone")

    if ENGINE_ENTITLEMENTS.is_file():
        keys = set(plistlib.loads(ENGINE_ENTITLEMENTS.read_bytes()))
        expected = {"com.apple.security.app-sandbox", "com.apple.security.inherit"}
        if keys != expected:
            fail(
                f"{ENGINE_ENTITLEMENTS.name} must hold EXACTLY {sorted(expected)}, got {sorted(keys)}. "
                "Any other App Sandbox key alongside `inherit` makes the system abort the engine."
            )
    else:
        fail(f"{ENGINE_ENTITLEMENTS.name} is missing — the nested engine would ship unsandboxed (ITMS-90296)")

    # 4. The engine embed phase: Helpers (a designated code location), signed with the
    #    two-key entitlements, and never --deep (which re-signs nested code with the
    #    PARENT's entitlements and silently breaks the inherit rule).
    embed = phase_named(objects, mas, "Embed Fichero Engine")
    if embed is None:
        fail(f"{MAS_TARGET} has no 'Embed Fichero Engine' phase — the archive would ship without an engine")
    else:
        body = shell_of(embed)
        if "Contents/Helpers/Fichero Engine.app" not in body:
            fail("the MAS engine must be embedded in Contents/Helpers — Resources is not a designated code location")
        if "Contents/Resources/Fichero Engine.app" in body:
            fail("the MAS engine must NOT be embedded in Contents/Resources (invalid bundle structure at ingestion)")
        if "FicheroEngineAppStore.entitlements" not in body:
            fail("the MAS embed phase must sign the engine with FicheroEngineAppStore.entitlements")

        # Both of these are REJECTIONS THIS APP HAS TAKEN. They are asserted on the
        # phase's text because the phase is the only thing standing between Briefcase's
        # bundle and App Store Connect.
        #
        # 90284 — Python.framework ships Tcl/Tk link-time stubs (.a). A static archive
        # cannot be signed at all, so it must not ship.
        if '-name "*.a" -type f -delete' not in body:
            fail(
                "the MAS embed phase must DELETE static archives (.a) from the engine. Ingestion rejects "
                "unsigned nested archives (90284), and a .a cannot be signed — it is an ar archive, not a "
                "Mach-O image. Briefcase's Python.framework ships Tcl/Tk stubs."
            )
        # 90296 — entitlements must be chosen by what a file IS. The first upload was
        # rejected because they were chosen by PATH, so fm-bridge (an executable the
        # engine spawns, buried under Contents/Resources/app/...) signed plain.
        if "is_macho_executable" not in body:
            fail(
                "the MAS embed phase must decide entitlements by Mach-O TYPE, not by path. A path rule "
                "misses nested executables like fm-bridge and ships them without com.apple.security."
                "app-sandbox (90296)."
            )
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # a comment WARNING about --deep is the point, not a violation
            if "codesign" in stripped and "--deep" in stripped:
                fail(f"the MAS embed phase runs `codesign --deep`: {stripped!r}. It re-signs nested code with the "
                     "PARENT's entitlements, replacing the engine's two-key set.")

    # 5. The scheme must ARCHIVE a configuration that actually embeds the engine.
    #    "Release Local" builds against an EXTERNAL engine — archiving it ships an app
    #    with no backend at all, which looks fine at build time and is dead on launch.
    if not SCHEME.is_file():
        fail(f"{SCHEME.name} is missing")
    else:
        text = SCHEME.read_text()
        match = re.search(r"<ArchiveAction[^>]*buildConfiguration = \"([^\"]+)\"", text)
        if not match:
            fail(f"{SCHEME.name} has no ArchiveAction buildConfiguration")
        else:
            archive_cfg = match.group(1)
            embeds = mas_cfgs.get(archive_cfg, {}).get("FICHERO_EMBED_ENGINE")
            if embeds != "YES":
                fail(
                    f"{SCHEME.name} archives with {archive_cfg!r}, whose FICHERO_EMBED_ENGINE is {embeds!r}. "
                    "The App Store build must embed the engine — archive a config with FICHERO_EMBED_ENGINE=YES."
                )
        if "Sparkle" in text:
            fail(f"{SCHEME.name} references Sparkle")

    # 6. Sparkle's Info.plist keys must not reach the App Store bundle. The plist is
    #    shared with the DMG target, so a build phase strips them; if that phase goes,
    #    the binary silently starts advertising an update feed again.
    strip = phase_named(objects, mas, "Strip Sparkle Info.plist Keys")
    if strip is None:
        fail(
            f"{MAS_TARGET} has no 'Strip Sparkle Info.plist Keys' phase. Info.plist is SHARED with the DMG target "
            "and declares SUFeedURL/SUPublicEDKey — an App Store app must not advertise a self-updater (2.4.5(vii))."
        )
    else:
        body = shell_of(strip)
        for key in ("SUFeedURL", "SUPublicEDKey"):
            if key not in body:
                fail(f"the Sparkle-strip phase does not remove {key}")

    return report()


def report() -> int:
    if failures:
        print("Mac App Store target check FAILED:\n")
        for f in failures:
            print(f"  ✗ {f}")
        print(f"\n{len(failures)} problem(s). Each is an App Store rejection or a dead build.")
        return 1
    print("✓ Mac App Store target OK — Sparkle excluded at link level, engine sandboxed in Contents/Helpers,")
    print("  two-key engine entitlements, no --deep, archive config embeds the engine, DMG channel intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
