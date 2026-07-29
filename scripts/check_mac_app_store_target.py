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
ENGINE_EMBED_INPUTS = REPO / "fichero/fichero.xcodeproj/xcshareddata/FicheroEngineEmbedInputs.xcfilelist"

MAS_TARGET = "Fichero (App Store)"
DMG_TARGET = "Fichero"
ENGINE_EMBED_OUTPUT_PATH = "$(FICHERO_ENGINE_EMBED_OUTPUT_PATH)"
ENGINE_EMBED_NOOP_PATH = "$(DERIVED_FILE_DIR)/FicheroEngineEmbed.noop"

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

    # Both macOS channels copy the Briefcase bundle during their Xcode build.
    # Xcode must refresh that Briefcase input first: the embed phase is a plain
    # copy, and `briefcase build` does not re-copy Python source unless the
    # update step has run. Without this preflight, a direct Xcode build can ship
    # the newest Swift app with an hours-old engine bundle (#3956).
    for target in (mas, dmg):
        embed_phase = phase_named(objects, target, "Embed Fichero Engine")
        if embed_phase is None:
            fail(f"{target['name']} has no 'Embed Fichero Engine' phase")
            continue
        embed_script = shell_of(embed_phase)
        preflight_at = embed_script.find("preflight-embedded-engine.sh")
        copy_at = embed_script.find('cp -R "$ENGINE_SRC" "$ENGINE_DST"')
        cleanup_at = embed_script.find("clean-embedded-engine.sh")
        if copy_at < 0:
            fail(f"{target['name']} must copy the Briefcase engine into the app bundle")
        if preflight_at < 0 or copy_at < preflight_at:
            fail(
                f"{target['name']} must run preflight-embedded-engine.sh before copying the engine. "
                "The preflight rebuilds or fails when the staged Briefcase bundle is stale (#3956)."
            )
        if cleanup_at < copy_at:
            fail(
                f"{target['name']} must precompile the copied engine after `cp -R` and before signing. "
                "Briefcase updates replace earlier .pyc files."
            )

        if str(embed_phase.get("alwaysOutOfDate", "0")) == "1":
            fail(
                f"{target['name']} Embed Fichero Engine must not set alwaysOutOfDate=1. "
                "Use conservative input/output metadata so Xcode can skip unchanged engine embeds (#3991)."
            )
        input_paths = set(embed_phase.get("inputPaths", []))
        input_file_lists = set(embed_phase.get("inputFileListPaths", []))
        output_paths = set(embed_phase.get("outputPaths", []))
        input_list = "$(SRCROOT)/fichero.xcodeproj/xcshareddata/FicheroEngineEmbedInputs.xcfilelist"
        if input_list not in input_file_lists:
            fail(f"{target['name']} Embed Fichero Engine must use {input_list!r} as an inputFileListPath")
        if "$(SRCROOT)/../fichero-server/build/engine/macos/app/Fichero Engine.app" not in input_paths:
            fail(f"{target['name']} Embed Fichero Engine must list the staged Briefcase app as an inputPath")
        expected_macos_output = (
            "$(TARGET_BUILD_DIR)/$(WRAPPER_NAME)/Contents/Helpers/Fichero Engine.app"
            if target["name"] == MAS_TARGET
            else "$(BUILT_PRODUCTS_DIR)/$(PRODUCT_NAME).app/Contents/Resources/Fichero Engine.app"
        )
        if output_paths != {ENGINE_EMBED_OUTPUT_PATH}:
            fail(
                f"{target['name']} Embed Fichero Engine must use {ENGINE_EMBED_OUTPUT_PATH!r} as its only "
                "outputPath so non-macOS builds do not track a macOS app-bundle path"
            )
        for cfg_name, settings in configs(objects, target).items():
            if settings.get("FICHERO_ENGINE_EMBED_OUTPUT_PATH") != ENGINE_EMBED_NOOP_PATH:
                fail(
                    f"{target['name']}/{cfg_name} must use {ENGINE_EMBED_NOOP_PATH!r} as the default "
                    "engine embed output path"
                )
            if settings.get("FICHERO_ENGINE_EMBED_OUTPUT_PATH[sdk=macosx*]") != expected_macos_output:
                fail(
                    f"{target['name']}/{cfg_name} must resolve FICHERO_ENGINE_EMBED_OUTPUT_PATH for macOS "
                    f"to {expected_macos_output!r}"
                )
        if target["name"] == MAS_TARGET and "$(SRCROOT)/fichero/FicheroEngineAppStore.entitlements" not in input_paths:
            fail("the MAS Embed Fichero Engine phase must list FicheroEngineAppStore.entitlements as an input")

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
        if settings.get("CODE_SIGN_INJECT_BASE_ENTITLEMENTS") != "NO":
            fail(f"{MAS_TARGET}/{cfg_name} must set CODE_SIGN_INJECT_BASE_ENTITLEMENTS=NO so the helper keeps its two-key inherit contract")
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
        # Explicit because of #3952: get-task-allow is the key TestFlight export
        # injects into nested code, and it is incompatible with inherit. The
        # two-key check above already rejects it; this names the failure so a
        # future editor who widens the set sees the specific reason, not a
        # generic "wrong key set" message.
        if "com.apple.security.get-task-allow" in keys:
            fail(
                f"{ENGINE_ENTITLEMENTS.name} carries com.apple.security.get-task-allow. It is incompatible "
                "with com.apple.security.inherit and aborts the sandboxed engine child on launch (#3952). "
                "TestFlight export injects it into nested code; the engine's entitlements must never list it."
            )
    else:
        fail(f"{ENGINE_ENTITLEMENTS.name} is missing — the nested engine would ship unsandboxed (ITMS-90296)")

    if ENGINE_EMBED_INPUTS.is_file():
        entries = {
            line.strip()
            for line in ENGINE_EMBED_INPUTS.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        required_file_list_entries = {
            "$(SRCROOT)/../fichero-server/pyproject.toml",
            "$(SRCROOT)/../scripts/clean-embedded-engine.sh",
            "$(SRCROOT)/../scripts/preflight-embedded-engine.sh",
            "$(SRCROOT)/../fichero-server/src/fichero_server/api/main.py",
            "$(SRCROOT)/../fichero-server/src/fichero_server/resources/bin/.gitignore",
        }
        missing_entries = sorted(required_file_list_entries - entries)
        if missing_entries:
            fail(
                f"{ENGINE_EMBED_INPUTS.name} is missing conservative engine inputs: "
                + ", ".join(missing_entries)
            )
        if not any(entry.startswith("$(SRCROOT)/../fichero-server/src/fichero_server/") for entry in entries):
            fail(f"{ENGINE_EMBED_INPUTS.name} must list engine source files, not just scripts")
    else:
        fail(f"{ENGINE_EMBED_INPUTS.name} is missing — Xcode cannot track engine source dependencies (#3991)")

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
        # 90277/90278 — Briefcase ships PyObjCTest extensions with their .dSYM bundles
        # beside them. A .dSYM's identifier is com.apple.xcode.dsym.*, which is Apple's
        # and can never match our provisioning profile — and it is detached DWARF, not
        # runtime code, so there is nothing to fix by re-signing it.
        if '-name "*.dSYM" -type d -exec rm -rf {} +' not in body:
            fail(
                "the MAS embed phase must DELETE debug-symbol bundles (.dSYM) from the engine. They carry "
                "com.apple.xcode.dsym identifiers that cannot match the provisioning profile (90277/90278), "
                "and they are not runtime code."
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
        # 3952: the embed phase must reject get-task-allow on the engine after
        # signing. The build-time codesign does not inject it (the CLI never
        # does; CODE_SIGN_INJECT_BASE_ENTITLEMENTS=NO keeps Xcode's phase from
        # doing so), but the assertion is the cheap backstop that proves the
        # two-key set actually landed on the signed bytes, not just in the file.
        if "com.apple.security.get-task-allow" not in body:
            fail(
                "the MAS embed phase must assert the signed engine does NOT carry "
                "com.apple.security.get-task-allow. get-task-allow is incompatible with "
                "com.apple.security.inherit and aborts the sandboxed engine child on launch (#3952); "
                "TestFlight export can inject it into nested code, so the build phase must fail the "
                "build if it appears on the engine after signing."
            )

    # 4a-bis. The TestFlight export re-signs nested code, and a shell-script
    # embed is not a recognised "Embed Helper Tools" phase, so the export can
    # stamp the parent's distribution entitlements (which include get-task-allow
    # for TestFlight) onto the engine. release-all.sh must re-sign the engine in
    # the archive with the distribution identity + the two-key entitlements
    # BEFORE export, and that re-sign must fail if get-task-allow survives (#3952).
    resign = REPO / "scripts" / "resign_engine_in_archive.sh"
    if not resign.is_file():
        fail("scripts/resign_engine_in_archive.sh is missing — the TestFlight export is not guarded against "
             "get-task-allow injection into the engine (#3952).")
    else:
        rbody = resign.read_text()
        if "com.apple.security.get-task-allow" not in rbody:
            fail("scripts/resign_engine_in_archive.sh must assert the re-signed engine does NOT carry "
                 "com.apple.security.get-task-allow (#3952).")
        if "--entitlements" not in rbody:
            fail("scripts/resign_engine_in_archive.sh must sign the engine with --entitlements (the two-key "
                 "FicheroEngineAppStore set), not plain signing (#3952).")
    release = REPO / "scripts" / "release-all.sh"
    if release.is_file():
        rtext = release.read_text()
        if "resign_engine_in_archive.sh" not in rtext:
            fail("scripts/release-all.sh must call resign_engine_in_archive.sh between archive and export so the "
                 "engine enters the TestFlight export distribution-signed with clean two-key entitlements (#3952).")
        if "FicheroEngineAppStore.entitlements" not in rtext:
            fail("scripts/release-all.sh must pass FicheroEngineAppStore.entitlements to resign_engine_in_archive.sh "
                 "so the engine is re-signed with the two-key set, not the parent's entitlements (#3952).")

    # 4b. The strips must run against a REAL path, and must be able to fail.
    #
    # This is the R2 lesson. ${BUILT_PRODUCTS_DIR}/<app> is a SYMLINK in an
    # archive/install build, and `find` does not descend into a symlinked starting
    # point — it reports zero matches. So the strips deleted nothing, and the
    # assertions that no .a/.dSYM "remained" also found nothing and PASSED. A vacuous
    # find is indistinguishable from a clean bundle, and an archive full of .dSYMs
    # shipped with a green build.
    if embed is not None:
        body = shell_of(embed)
        if 'APP_DST="${TARGET_BUILD_DIR}/${WRAPPER_NAME}"' not in body:
            fail(
                "the MAS embed phase must resolve the app bundle via TARGET_BUILD_DIR/WRAPPER_NAME. "
                "BUILT_PRODUCTS_DIR/<app> is a SYMLINK in an archive build, and `find` does not descend "
                "into a symlinked start point — the strips silently no-op and their checks vacuously pass."
            )
        if "pwd -P" not in body:
            fail("the MAS embed phase must resolve APP_DST to a physical path (cd && pwd -P) before any find")
        if "traverses nothing" not in body:
            fail(
                "the MAS embed phase must assert that find TRAVERSES the bundle before trusting a 'found "
                "nothing' result. Without it, a broken walk reads as a clean bundle — which is exactly how "
                "the .dSYM archive shipped green."
            )

    # 4c. The build must be judged by the same validator that judges the archive.
    validate = phase_named(objects, mas, "Validate App Store Bundle")
    if validate is None:
        fail(
            f"{MAS_TARGET} has no 'Validate App Store Bundle' phase. Bespoke in-phase assertions have now "
            "passed vacuously twice; the build must be checked by scripts/validate_mas_bundle.sh — the same "
            "tool that judges the .xcarchive."
        )
    else:
        body = shell_of(validate)
        if "validate_mas_bundle.sh" not in body:
            fail("the 'Validate App Store Bundle' phase must invoke scripts/validate_mas_bundle.sh")
        if "--structure-only" not in body:
            fail(
                "the validation phase must pass --structure-only: it runs before Xcode signs the outer app, "
                "so the whole-app signature check cannot pass yet"
            )
        # Order matters: validating before the strip would validate the wrong bytes.
        names = [objects[p].get("name") for p in mas["buildPhases"]]
        if "Embed Fichero Engine" in names and names.index("Validate App Store Bundle") < names.index(
            "Embed Fichero Engine"
        ):
            fail("'Validate App Store Bundle' must run AFTER 'Embed Fichero Engine', not before")

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
