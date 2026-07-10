"""Self-test for release pipeline scripts (#1358).

Verifies:
- scripts/build-release.sh, scripts/build-and-validate.sh, scripts/notarize.sh,
  scripts/create-github-release.sh
  all pass `bash -n` (syntax check)
- Each script contains the expected step markers in order
- --help exits 0 on scripts that support it
- --dry-run exits 0 without any real credentials or build tools

These are pure filesystem + subprocess tests — no Python imports required.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Root of the repo (two levels up from fichero-engine/tests/unit/)
REPO_ROOT = Path(__file__).parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

BUILD_RELEASE = SCRIPTS_DIR / "build-release.sh"
BUILD_AND_VALIDATE = SCRIPTS_DIR / "build-and-validate.sh"
NOTARIZE = SCRIPTS_DIR / "notarize.sh"
CREATE_RELEASE = SCRIPTS_DIR / "create-github-release.sh"
NIGHTLY_RELEASE = SCRIPTS_DIR / "nightly-release.sh"
START_BACKEND = REPO_ROOT / "fichero-engine" / "scripts" / "start_backend.sh"
BUILD_BACKEND_BUNDLE = REPO_ROOT / "fichero-engine" / "scripts" / "build_backend_bundle.sh"
BUNDLE_PYTHON_BACKEND = REPO_ROOT / "fichero-engine" / "scripts" / "bundle_python_backend.sh"

ALL_SCRIPTS = [BUILD_RELEASE, BUILD_AND_VALIDATE, NOTARIZE, CREATE_RELEASE, NIGHTLY_RELEASE]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _script_text(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=[s.name for s in ALL_SCRIPTS])
def test_script_exists(script: Path) -> None:
    assert script.exists(), f"{script.name} not found at {script}"


# ---------------------------------------------------------------------------
# Syntax (bash -n)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=[s.name for s in ALL_SCRIPTS])
def test_bash_syntax(script: Path) -> None:
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"bash -n {script.name} failed:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Expected step markers
# ---------------------------------------------------------------------------


def test_build_release_steps() -> None:
    text = _script_text(BUILD_RELEASE)
    for marker in ("[0/4]", "[1/4]", "[2/4]", "[3/4]"):
        assert marker in text, f"build-release.sh missing step {marker!r}"


def test_build_and_validate_steps() -> None:
    text = _script_text(BUILD_AND_VALIDATE)
    for marker in ("[1/8]", "[2/8]", "[3/8]", "[4/8]", "[5/8]", "[6/8]", "[7/8]", "[8/8]"):
        assert marker in text, f"build-and-validate.sh missing step {marker!r}"


def test_notarize_steps() -> None:
    text = _script_text(NOTARIZE)
    for marker in ("[1/3]", "[2/3]", "[3/3]"):
        assert marker in text, f"notarize.sh missing step {marker!r}"


def test_create_github_release_steps() -> None:
    text = _script_text(CREATE_RELEASE)
    for marker in ("[1/5]", "[2/5]", "[3/5]", "[4/5]", "[5/5]"):
        assert marker in text, f"create-github-release.sh missing step {marker!r}"


def test_nightly_release_tracks_daily_prerelease_flow() -> None:
    text = _script_text(NIGHTLY_RELEASE)
    assert 'TAG="daily-$TODAY"' in text
    assert 'TITLE="Nightly $TAG"' in text
    assert "gh release view" in text
    assert "gh release edit" in text
    assert "gh release create" in text
    assert "--prerelease" in text
    assert "--clobber" in text


# ---------------------------------------------------------------------------
# Key features present
# ---------------------------------------------------------------------------


def test_build_release_has_dry_run_flag() -> None:
    text = _script_text(BUILD_RELEASE)
    assert "--dry-run" in text
    assert "run_or_dry" in text


def test_build_and_validate_uses_current_paths() -> None:
    text = _script_text(BUILD_AND_VALIDATE)
    assert "fichero/fichero.xcodeproj" in text
    assert "fichero/build/xcode" in text
    assert "build/engine" in text
    assert "briefcase build macOS --app engine" in text
    assert "fichero-swiftui" not in text


def test_notarize_has_dry_run_flag() -> None:
    text = _script_text(NOTARIZE)
    assert "--dry-run" in text
    assert "run_or_dry" in text


def test_create_release_has_dry_run_flag() -> None:
    text = _script_text(CREATE_RELEASE)
    assert "--dry-run" in text
    assert "run_or_dry" in text


def test_nightly_release_builds_changelog_from_merged_prs() -> None:
    text = _script_text(NIGHTLY_RELEASE)
    assert "gh pr list --state merged" in text
    assert 'merged:>=$TODAY' in text
    assert "## Merged today" in text
    assert "_No PRs merged on $TODAY._" in text


def test_nightly_release_has_dry_run_and_skip_build_flags() -> None:
    text = _script_text(NIGHTLY_RELEASE)
    assert "--dry-run" in text
    assert "--skip-build" in text
    assert "run()" in text
    assert 'run "$DEV" build-all' in text


def test_build_release_guards_openapi_skip() -> None:
    text = _script_text(BUILD_RELEASE)
    assert "--skip-openapi-sync" in text, (
        "build-release.sh must reject --skip-openapi-sync with a helpful error"
    )


def test_notarize_references_keychain_profile() -> None:
    text = _script_text(NOTARIZE)
    assert "FICHERO_NOTARIZE_PROFILE" in text


def test_create_release_references_sparkle_tools() -> None:
    text = _script_text(CREATE_RELEASE)
    assert "sign_update" in text
    assert "SPARKLE_BIN" in text


def test_create_release_updates_appcast() -> None:
    text = _script_text(CREATE_RELEASE)
    assert "appcast.xml" in text


def test_start_backend_defaults_to_dev_feature_tier() -> None:
    text = _script_text(START_BACKEND)

    assert 'export FICHERO_FEATURE_TIER="${FICHERO_FEATURE_TIER:-dev}"' in text


def test_start_backend_makes_multiuser_default_explicit_for_local_and_remote() -> None:
    text = _script_text(START_BACKEND)

    assert 'FICHERO_MULTIUSER="${FICHERO_MULTIUSER:-1}"' in text
    assert 'export FICHERO_MULTIUSER="${FICHERO_MULTIUSER:-0}"' in text


def test_start_backend_syncs_bootstrap_token_into_debug_sandbox() -> None:
    text = _script_text(START_BACKEND)

    assert 'FICHERO_DEBUG_APP_BUNDLE_ID="${FICHERO_DEBUG_APP_BUNDLE_ID:-app.fichero.fichero}"' in text
    assert "prepare_app_bootstrap_token_for_launch" in text


def test_backend_bundle_builds_fm_bridge_into_package_resources() -> None:
    text = _script_text(BUILD_BACKEND_BUNDLE)

    assert "bin/fm-bridge/FmBridge.swift" in text
    assert "src/fichero/resources/bin/fm-bridge" in text
    assert "swiftc -O -parse-as-library" in text


def test_python_bundle_builds_fm_bridge_into_site_packages() -> None:
    text = _script_text(BUNDLE_PYTHON_BACKEND)

    assert "bin/fm-bridge/FmBridge.swift" in text
    assert "site-packages/fichero/resources/bin/fm-bridge" in text
    assert "swiftc -O -parse-as-library" in text


# ---------------------------------------------------------------------------
# --help exits 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=[s.name for s in ALL_SCRIPTS])
def test_help_exits_zero(script: Path) -> None:
    result = subprocess.run(
        ["bash", str(script), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{script.name} --help returned {result.returncode}:\n{result.stderr}"
    )
    assert "Usage" in result.stdout, (
        f"{script.name} --help output missing 'Usage':\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# --dry-run exits 0 (no real credentials / build tools needed)
# ---------------------------------------------------------------------------


def test_build_release_dry_run() -> None:
    result = subprocess.run(
        ["bash", str(BUILD_RELEASE), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"build-release.sh --dry-run failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "[DRY RUN]" in result.stdout


def test_notarize_dry_run() -> None:
    result = subprocess.run(
        ["bash", str(NOTARIZE), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"notarize.sh --dry-run failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "[DRY RUN]" in result.stdout


def test_create_release_dry_run() -> None:
    result = subprocess.run(
        ["bash", str(CREATE_RELEASE), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"create-github-release.sh --dry-run failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "[DRY RUN]" in result.stdout


# ---------------------------------------------------------------------------
# -n alias works the same as --dry-run
# ---------------------------------------------------------------------------


def test_notarize_short_flag_n() -> None:
    result = subprocess.run(
        ["bash", str(NOTARIZE), "-n"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    assert "[DRY RUN]" in result.stdout
