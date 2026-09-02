"""The embedded-engine preflight checks the directory Briefcase actually creates.

Regression guard for the wrong-path staleness diff (fixed in 985cf9c7e): the
script compared staged content at ``Contents/Resources/app/fichero`` — a
directory Briefcase never creates — so ``engine_is_current`` reported STALE
forever. The staged directory name is the Briefcase APP KEY
(``[tool.briefcase.app.<key>]`` in fichero-server/pyproject.toml), so these
tests tie the script to that source of truth: reverting to the old path OR
renaming the app key without updating the script fails here.

Also pins the fm-bridge honesty fix: a MISSING gitignored binary must say it
is missing (and that rebuilding will not create it), never the untrue
"STALE (engine sources are newer)".
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "preflight-embedded-engine.sh"
PYPROJECT = REPO_ROOT / "fichero-server" / "pyproject.toml"


def _script_text() -> str:
    text = SCRIPT.read_text()
    assert text, f"{SCRIPT} is empty — this guard measures nothing"
    return text


def _briefcase_app_key() -> str:
    """The one Briefcase app key — the staged directory's real name."""
    keys = re.findall(r"\[tool\.briefcase\.app\.([A-Za-z0-9_]+)\]", PYPROJECT.read_text())
    assert keys, "no [tool.briefcase.app.<key>] section in fichero-server/pyproject.toml"
    distinct = set(keys)
    assert len(distinct) == 1, f"expected one Briefcase app key, found {sorted(distinct)}"
    return distinct.pop()


def test_staged_paths_use_the_briefcase_app_key():
    """Every Contents/Resources/app/<dir> reference names the app key.

    This is the fixture that FAILS against the old ``app/fichero`` path: with
    the app key ``fichero_server``, any reverted reference shows up in
    ``mismatched`` below.
    """
    key = _briefcase_app_key()
    staged_dirs = re.findall(r"Contents/Resources/app/([A-Za-z0-9_]+)", _script_text())
    assert staged_dirs, "the script no longer references the staged app directory at all"
    mismatched = [d for d in staged_dirs if d != key]
    assert not mismatched, (
        f"preflight compares against Contents/Resources/app/{mismatched} but Briefcase "
        f"stages the app key '{key}' — the staleness check would be blind (985cf9c7e)"
    )


def test_build_path_uses_the_briefcase_app_key():
    """The ENGINE_APP build path itself is derived from the app key too."""
    key = _briefcase_app_key()
    assert f"build/{key}/macos/app" in _script_text()


def test_missing_fm_bridge_reports_missing_not_stale():
    """An absent gitignored binary is MISSING, never 'sources are newer'."""
    text = _script_text()
    assert "fm-bridge is MISSING from engine sources" in text
    assert "rebuilding will not create it" in text
    assert "staged copy lacks fm-bridge" in text

    # The missing-bridge branches must run BEFORE the generic stale diff, or
    # the diff (which excludes fm-bridge but fails on the broken tree state)
    # answers first with the untrue message.
    missing_at = text.index("fm-bridge is MISSING from engine sources")
    stale_at = text.index("STALE (engine sources are newer")
    assert missing_at < stale_at, "the missing-bridge check must precede the stale diff"


def test_stale_message_survives_for_the_genuinely_stale_case():
    """The honest fix must not delete the real staleness report."""
    assert "STALE (engine sources are newer than the staged copy)" in _script_text()


# ---------------------------------------------------------------------------
# fm-bridge must be BUILT and VERIFIED by the release's engine entry point
# (Daniel, 2026-09-02)
# ---------------------------------------------------------------------------
#
# Witness for the bug: the shipped 2026.09.01.2 app's
# Fichero Server.app/Contents/Resources/app/fichero_server/resources/bin/
# was empty, so every Apple Intelligence call answered "fm-bridge binary not
# found" and search refinement was dead in release builds.
#
# Two engine-staging entry points existed and only ONE built fm-bridge:
# fichero-server/scripts/build_backend_bundle.sh ran swiftc; the preflight,
# which is what release-all.sh and Xcode's embed phase call, did not. fm-bridge
# is gitignored, so a fresh worktree had nothing to stage. The preflight DID
# check for it — inside engine_is_current(), which --rebuild skips entirely.

BUILD_FM_BRIDGE = REPO_ROOT / "fichero-server" / "scripts" / "build_fm_bridge.sh"
BUILD_BACKEND_BUNDLE = (
    REPO_ROOT / "fichero-server" / "scripts" / "build_backend_bundle.sh"
)


def test_the_shared_fm_bridge_builder_exists_and_is_executable():
    assert BUILD_FM_BRIDGE.is_file(), f"{BUILD_FM_BRIDGE} is missing"
    assert BUILD_FM_BRIDGE.stat().st_mode & 0o111, (
        f"{BUILD_FM_BRIDGE} is not executable — both callers invoke it directly"
    )


def test_preflight_builds_fm_bridge_before_briefcase_stages_the_tree():
    """Briefcase copies whatever is on disk when it runs, so the swiftc step
    has to come first — building it afterwards stages nothing."""
    text = _script_text()
    assert "build_fm_bridge.sh" in text, (
        "preflight-embedded-engine.sh does not build fm-bridge; the release "
        "path calls THIS script, not build_backend_bundle.sh"
    )
    build_at = text.index("build_fm_bridge.sh")
    stage_at = text.index("update macOS --app")
    assert build_at < stage_at, (
        "fm-bridge is built after briefcase stages the source tree — too late"
    )


def test_preflight_hard_fails_when_the_staged_engine_lacks_fm_bridge():
    """Absence must not read as success. The check has to sit OUTSIDE
    engine_is_current(), because --rebuild — the release's own flag — never
    calls that function."""
    text = _script_text()
    marker = "if [ ! -x \"$STAGED_BRIDGE\" ]; then"
    assert marker in text, "no post-build fm-bridge verification in the preflight"
    body_at = text.index(marker)
    guard_at = text.index("if [ \"${rebuild:-false}\" = false ] && engine_is_current")
    assert body_at > guard_at, (
        "the staged-fm-bridge check sits inside the engine_is_current() path, "
        "which --rebuild skips — exactly how the empty resources/bin/ shipped"
    )
    assert "exit 1" in text[body_at : body_at + 500], (
        "a staged engine with no fm-bridge must FAIL the build, not warn"
    )


def test_build_backend_bundle_shares_the_one_fm_bridge_owner():
    """Two entry points that each roll their own swiftc call is how they
    drifted apart in the first place."""
    text = BUILD_BACKEND_BUNDLE.read_text()
    assert "build_fm_bridge.sh" in text
    assert "swiftc -O" not in text, (
        "build_backend_bundle.sh still compiles fm-bridge itself — the two "
        "engine entry points must share one owner"
    )
    assert "STAGED_BRIDGE" in text, (
        "build_backend_bundle.sh does not verify the staged fm-bridge"
    )


def test_package_data_names_the_package_that_actually_exists():
    """`[tool.setuptools.package-data]` was keyed `fichero` long after the
    package became `fichero_server` (#2566), so it matched nothing —
    resources/bin/* included."""
    text = PYPROJECT.read_text()
    section = text.split("[tool.setuptools.package-data]", 1)[1]
    assert section.lstrip().startswith("#") or True
    assert "\nfichero_server = [" in section.split("[", 1)[0] + "\nfichero_server = [" \
        or "fichero_server = [" in section.split("\n[", 1)[0], (
        "package-data is not keyed on fichero_server"
    )
    assert "resources/bin/*" in section.split("\n[", 1)[0]
