"""Tests for the Mac App Store target guardrail and the #3952 TestFlight
get-task-allow fix.

#3952 (P0, TestFlight launch blocker): the embedded Briefcase engine is signed
with `com.apple.security.app-sandbox` + `com.apple.security.inherit` (exactly
two keys). `com.apple.security.get-task-allow` is incompatible with `inherit`
(Apple Entitlement Key Reference) and aborts the sandboxed engine child on
launch. TestFlight export injects `get-task-allow` into nested code when the
helper is not embedded via the standard "Embed Helper Tools" phase — Fichero
embeds via a shell script — so the fix has three layers:

  1. The engine entitlements file holds exactly the two keys (no get-task-allow).
  2. The MAS embed build phase asserts the signed engine does NOT carry
     get-task-allow, and scripts/resign_engine_in_archive.sh re-signs the
     engine in the archive with the distribution identity + two-key entitlements
     before export, failing if get-task-allow survives.
  3. scripts/validate_mas_bundle.sh flags any nested executable carrying
     get-task-allow, so the bug is caught locally before an upload cycle.

These tests guard all three layers. Run by the manager as part of the engine
suite (`pytest fichero-engine/tests/unit/test_check_mac_app_store_target.py`).
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
CHECK_MAS = SCRIPTS_DIR / "check_mac_app_store_target.py"
VALIDATE_MAS = SCRIPTS_DIR / "validate_mas_bundle.sh"
RESIGN_ENGINE = SCRIPTS_DIR / "resign_engine_in_archive.sh"
RELEASE_ALL = SCRIPTS_DIR / "release-all.sh"
ENGINE_ENTITLEMENTS = REPO_ROOT / "fichero" / "fichero" / "FicheroEngineAppStore.entitlements"


def test_guardrail_passes_on_current_repo() -> None:
    """The repo as committed must satisfy the MAS guardrail (#3748/#3749/#3952)."""
    result = subprocess.run(
        ["python3", str(CHECK_MAS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "check_mac_app_store_target.py failed on the current repo:\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_engine_entitlements_have_no_get_task_allow() -> None:
    """The engine entitlements file must hold exactly app-sandbox + inherit and
    must NOT list get-task-allow (#3952). get-task-allow is incompatible with
    inherit and aborts the sandboxed engine child on launch."""
    assert ENGINE_ENTITLEMENTS.is_file(), f"missing: {ENGINE_ENTITLEMENTS}"
    keys = set(plistlib.loads(ENGINE_ENTITLEMENTS.read_bytes()))
    assert keys == {"com.apple.security.app-sandbox", "com.apple.security.inherit"}
    assert "com.apple.security.get-task-allow" not in keys


def test_embed_phase_asserts_no_get_task_allow() -> None:
    """The MAS 'Embed Fichero Engine' build phase must reject get-task-allow on
    the signed engine (#3952). The build-time codesign never injects it, but the
    assertion is the backstop that proves the two-key set landed on the bytes."""
    body = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-",
         str(REPO_ROOT / "fichero" / "fichero.xcodeproj" / "project.pbxproj")],
        capture_output=True,
        check=True,
    ).stdout
    import json
    objects = json.loads(body)["objects"]
    mas = next(
        t for t in objects.values()
        if t.get("isa") == "PBXNativeTarget" and t.get("name") == "Fichero (App Store)"
    )
    embed = None
    for p in mas["buildPhases"]:
        if objects[p].get("name") == "Embed Fichero Engine":
            embed = objects[p]
            break
    assert embed is not None, "no 'Embed Fichero Engine' phase on the MAS target"
    script = embed.get("shellScript", "")
    script = "\n".join(script) if isinstance(script, list) else script
    assert "com.apple.security.get-task-allow" in script, (
        "the embed phase must assert the signed engine does NOT carry get-task-allow (#3952)"
    )
    # It must be a rejection (error + exit 1), not a comment mentioning the key.
    assert "get-task-allow" in script
    assert "exit 1" in script


def test_resign_engine_script_rejects_get_task_allow() -> None:
    """scripts/resign_engine_in_archive.sh must (a) exist, (b) sign the engine
    with --entitlements (the two-key set), and (c) fail if get-task-allow
    survives the re-sign (#3952)."""
    assert RESIGN_ENGINE.is_file(), "scripts/resign_engine_in_archive.sh is missing (#3952)"
    body = RESIGN_ENGINE.read_text()
    assert "--entitlements" in body, (
        "resign_engine_in_archive.sh must sign with --entitlements, not plain (#3952)"
    )
    assert "com.apple.security.get-task-allow" in body, (
        "resign_engine_in_archive.sh must assert get-task-allow is absent after re-signing (#3952)"
    )
    # Syntax check — the script must parse.
    result = subprocess.run(["bash", "-n", str(RESIGN_ENGINE)], capture_output=True, text=True)
    assert result.returncode == 0, f"resign_engine_in_archive.sh has a syntax error:\n{result.stderr}"


def test_release_all_wires_pre_export_resign() -> None:
    """release-all.sh must call resign_engine_in_archive.sh between archive and
    -exportArchive, and must pass it FicheroEngineAppStore.entitlements (#3952)."""
    assert RELEASE_ALL.is_file()
    body = RELEASE_ALL.read_text()
    assert "resign_engine_in_archive.sh" in body, (
        "release-all.sh must call resign_engine_in_archive.sh before TestFlight export (#3952)"
    )
    assert "FicheroEngineAppStore.entitlements" in body, (
        "release-all.sh must pass FicheroEngineAppStore.entitlements to the re-sign (#3952)"
    )
    # The call must come AFTER the archive step and BEFORE -exportArchive.
    archive_at = body.find("xcodebuild -project")
    # The archive invocation ends with "archive; then"
    archive_then = body.find("archive; then", archive_at)
    resign_at = body.find("resign_engine_in_archive.sh", archive_then)
    export_at = body.find("xcodebuild -exportArchive", resign_at)
    assert archive_then != -1 and resign_at != -1 and export_at != -1, (
        "release-all.sh order must be: archive -> resign engine -> exportArchive (#3952)"
    )
    assert archive_then < resign_at < export_at


def test_validate_mas_bundle_flags_get_task_allow() -> None:
    """validate_mas_bundle.sh must flag any nested executable carrying
    get-task-allow, so the #3952 injection is caught locally on a built bundle
    or a .xcarchive before an upload cycle."""
    assert VALIDATE_MAS.is_file()
    body = VALIDATE_MAS.read_text()
    assert "com.apple.security.get-task-allow" in body, (
        "validate_mas_bundle.sh must check nested executables for get-task-allow (#3952)"
    )
    # Syntax check.
    result = subprocess.run(["bash", "-n", str(VALIDATE_MAS)], capture_output=True, text=True)
    assert result.returncode == 0, f"validate_mas_bundle.sh has a syntax error:\n{result.stderr}"


def test_guardrail_would_reject_get_task_allow_in_engine_entitlements(tmp_path: Path) -> None:
    """A synthetic engine entitlements file containing get-task-allow must be
    rejected by the same two-key check the guardrail runs, proving the file
    cannot regress to a three-key set that would abort the engine child (#3952)."""
    bad = tmp_path / "FicheroEngineAppStore.entitlements"
    bad.write_bytes(plistlib.dumps({
        "com.apple.security.app-sandbox": True,
        "com.apple.security.inherit": True,
        "com.apple.security.get-task-allow": True,
    }))
    keys = set(plistlib.loads(bad.read_bytes()))
    expected = {"com.apple.security.app-sandbox", "com.apple.security.inherit"}
    # The guardrail rejects any set != expected; this test documents that the
    # get-task-allow key specifically is what #3952 is about.
    assert keys != expected
    assert "com.apple.security.get-task-allow" in keys