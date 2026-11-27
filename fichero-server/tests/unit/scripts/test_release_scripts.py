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

import os
import shutil
import subprocess
import plistlib
from pathlib import Path

import pytest

# Root of the repo (two levels up from fichero-server/tests/unit/)
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

BUILD_RELEASE = SCRIPTS_DIR / "build-release.sh"
BUILD_AND_VALIDATE = SCRIPTS_DIR / "build-and-validate.sh"
NOTARIZE = SCRIPTS_DIR / "notarize.sh"
CREATE_RELEASE = SCRIPTS_DIR / "create-github-release.sh"
NIGHTLY_RELEASE = SCRIPTS_DIR / "nightly-release.sh"
RELEASE_ALL = SCRIPTS_DIR / "release-all.sh"
START_BACKEND = REPO_ROOT / "fichero-server" / "scripts" / "start_fichero_server.sh"
BUILD_BACKEND_BUNDLE = REPO_ROOT / "fichero-server" / "scripts" / "build_backend_bundle.sh"
BUNDLE_PYTHON_BACKEND = REPO_ROOT / "fichero-server" / "scripts" / "bundle_python_backend.sh"
BUILD_FM_BRIDGE = REPO_ROOT / "fichero-server" / "scripts" / "build_fm_bridge.sh"
# The entry point the RELEASE uses (release-all.sh), as distinct from
# build_backend_bundle.sh which it never calls.
PREFLIGHT_EMBEDDED_ENGINE = SCRIPTS_DIR / "preflight-embedded-engine.sh"
CLEAN_EMBEDDED_ENGINE = SCRIPTS_DIR / "clean-embedded-engine.sh"

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
    assert "preflight-embedded-engine.sh" in text


@pytest.mark.macos_only(reason="the guard reads the engine app's Info.plist with PlistBuddy")
def test_embedded_engine_version_guard_rejects_stale_bundle(tmp_path: Path) -> None:
    expected = next(
        line.split('"')[1]
        for line in (REPO_ROOT / "fichero-server" / "pyproject.toml").read_text().splitlines()
        if line.startswith('version = "')
    )
    app = tmp_path / "Fichero Server.app"
    contents = app / "Contents"
    metadata = contents / "Resources" / "app" / f"fichero_server-{expected}.dist-info" / "METADATA"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(f"Name: engine\nVersion: {expected}\n")
    plist = contents / "Info.plist"
    with plist.open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": expected}, handle)

    current = subprocess.run(
        [str(CLEAN_EMBEDDED_ENGINE), "--check-version", str(app)],
        capture_output=True,
        text=True,
    )
    assert current.returncode == 0, current.stderr

    with plist.open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": "2026.7.17.2"}, handle)
    stale = subprocess.run(
        [str(CLEAN_EMBEDDED_ENGINE), "--check-version", str(app)],
        capture_output=True,
        text=True,
    )
    assert stale.returncode == 1
    assert f"expected={expected} bundle=2026.7.17.2 package={expected}" in stale.stderr


def test_release_all_always_rebuilds_engine_before_packaging() -> None:
    text = _script_text(RELEASE_ALL)
    rebuild = text.index('preflight-embedded-engine.sh" --rebuild')
    # Anchor on the packaging block itself (`CURRENT_PART="DMG"`). Every `if [ "$SKIP_DMG" = false ]; then` before it
    # is something else that runs BEFORE the rebuild by design: the build-number choice, the build check and the
    # credentials preflight. Matching any of those made this test fail while the script was correct, and read as
    # "a release can package a stale engine" (#3956).
    packaging = text.index('CURRENT_PART="DMG"')

    assert rebuild < packaging
    assert '--skip-backend) SKIP_BACKEND=true' not in text


def test_release_all_checks_closed_issues_strictly_before_signing() -> None:
    """A release stops when check_closed_issues_landed cannot check (no origin, no gh): on dev machines and the
    M4 that is a plain SKIP, so only `--strict` keeps the release from shipping on a check that saw nothing."""
    text = _script_text(RELEASE_ALL)
    check = text.index('check_closed_issues_landed.py" --strict')
    assert check < text.index("── Preflight: codesign keychain access ──")
    assert check < text.index('preflight-embedded-engine.sh" --rebuild')


def test_release_all_cleans_only_macos_archive_before_macos_archive() -> None:
    text = _script_text(RELEASE_ALL)
    cleanup = text.index('rm -rf "$MAC_ARCHIVE_PATH"')
    archive = text.index('xcodebuild -project "$ROOT_DIR/fichero/fichero.xcodeproj"')
    ios_cleanup = text.index('rm -rf "$IOS_ARCHIVE_PATH"')

    assert cleanup < archive < ios_cleanup
    assert 'MAC_ARCHIVE_PATH="$RELEASE_DIR/Fichero-macOS.xcarchive"' in text
    assert 'rm -rf "$RELEASE_DIR"' not in text
    assert 'rm -rf "$ROOT_DIR/build"' not in text


def test_preflight_accepts_distribution_signed_fm_bridge() -> None:
    text = _script_text(REPO_ROOT / "scripts" / "preflight-embedded-engine.sh")

    assert "--exclude=.DS_Store" in text
    assert "--exclude=fm-bridge" in text
    assert text.count("dwarfdump --uuid") == 2


def test_build_and_validate_uses_current_paths() -> None:
    text = _script_text(BUILD_AND_VALIDATE)
    assert "fichero/fichero.xcodeproj" in text
    assert "fichero/build/xcode" in text
    assert "build/server" in text
    assert "briefcase build macOS --app fichero_server" in text
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


def test_release_all_preflight_falls_back_to_direct_notary_key() -> None:
    """The preflight must accept the SAME direct-key fallback notarize.sh
    uses at submit time (2026-08-15: a non-interactive session validated
    store-credentials and still could not read the item back — an unreadable
    keychain profile must not block a release the submit step can finish)."""
    text = _script_text(RELEASE_ALL)
    profile_check = text.index('notarytool history --keychain-profile')
    fallback = text.index('notarytool history --key "$APP_STORE_CONNECT_KEY_PATH"')
    assert profile_check < fallback
    # The fallback validates against Apple, not just file existence.
    assert '--issuer "$APP_STORE_CONNECT_ISSUER_ID"' in text


def test_create_release_references_sparkle_tools() -> None:
    text = _script_text(CREATE_RELEASE)
    assert "sign_update" in text
    assert "SPARKLE_BIN" in text


def test_create_release_updates_appcast() -> None:
    text = _script_text(CREATE_RELEASE)
    assert "appcast.xml" in text


def test_start_fichero_server_defaults_to_dev_feature_tier() -> None:
    text = _script_text(START_BACKEND)

    assert 'export FICHERO_FEATURE_TIER="${FICHERO_FEATURE_TIER:-dev}"' in text


def test_start_fichero_server_makes_multiuser_default_explicit_for_local_and_remote() -> None:
    text = _script_text(START_BACKEND)

    assert 'FICHERO_MULTIUSER="${FICHERO_MULTIUSER:-1}"' in text
    assert 'export FICHERO_MULTIUSER="${FICHERO_MULTIUSER:-0}"' in text


def test_start_fichero_server_syncs_bootstrap_token_into_debug_sandbox() -> None:
    text = _script_text(START_BACKEND)

    assert 'FICHERO_DEBUG_APP_BUNDLE_ID="${FICHERO_DEBUG_APP_BUNDLE_ID:-app.fichero.fichero}"' in text
    assert "prepare_app_bootstrap_token_for_launch" in text


def test_backend_bundle_builds_fm_bridge_into_package_resources() -> None:
    """The CONTRACT is that this entry point stages fm-bridge — not that it
    runs swiftc with its own hands.

    The compile moved into fichero-server/scripts/build_fm_bridge.sh
    (2026-09-02) so that the release's own entry point,
    scripts/preflight-embedded-engine.sh, could share it. Only one of the two
    used to build the binary, which is how the shipped 2026.09.01.2 app got an
    EMPTY resources/bin/ and answered "fm-bridge binary not found" for every
    Apple Intelligence call.

    So: assert the delegation here, and assert the swiftc invocation and the
    destination in the builder that now owns them. No prebuilt binary is
    required on disk — it is gitignored, so demanding one would fail in every
    fresh worktree while proving nothing about the packaging contract.
    """
    text = _script_text(BUILD_BACKEND_BUNDLE)
    assert "build_fm_bridge.sh" in text, (
        "build_backend_bundle.sh no longer stages fm-bridge at all"
    )

    builder = _script_text(BUILD_FM_BRIDGE)
    assert "bin/fm-bridge/FmBridge.swift" in builder
    assert "src/fichero_server/resources/bin/fm-bridge" in builder
    assert "swiftc -O -parse-as-library" in builder


def test_the_release_engine_entry_point_also_builds_fm_bridge() -> None:
    """The half that was missing. release-all.sh calls the preflight, never
    build_backend_bundle.sh, so a builder wired only into the latter never
    ran for a release."""
    text = PREFLIGHT_EMBEDDED_ENGINE.read_text()
    assert "build_fm_bridge.sh" in text


def test_python_bundle_builds_fm_bridge_into_site_packages() -> None:
    text = _script_text(BUNDLE_PYTHON_BACKEND)

    assert "bin/fm-bridge/FmBridge.swift" in text
    # fichero_server, not fichero — the package rename (#2566) left this path
    # pointing at a directory nothing imports from.
    assert "site-packages/fichero_server/resources/bin/fm-bridge" in text
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


def test_a_public_release_posts_only_the_dev_build_as_fichero_dev_dmg() -> None:
    """Owner 2026-11-18: only the dev build is posted, named Fichero-dev.dmg; the appcast enclosure names it too."""
    result = subprocess.run(
        ["bash", str(CREATE_RELEASE), "--dry-run"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env={**os.environ, "FICHERO_RELEASE_PUBLIC": "1"},
    )
    assert result.returncode == 0, f"rc={result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "would post the DMG as Fichero-dev.dmg: " in result.stdout
    assert "/Fichero.dmg" not in result.stdout.split("would post the DMG as ", 1)[1].splitlines()[0]


def test_create_release_dry_run_needs_no_git_checkout(tmp_path: Path) -> None:
    """The gate runs the suite from a copy of the tree with no .git: the dry run only prints, so it must still end 0."""
    shutil.copytree(SCRIPTS_DIR, tmp_path / "scripts")
    shutil.copytree(REPO_ROOT / "fichero", tmp_path / "fichero", ignore=shutil.ignore_patterns("*.xcassets", "*.swift"))
    result = subprocess.run(
        ["bash", str(tmp_path / "scripts" / "create-github-release.sh"), "--dry-run"],
        capture_output=True, text=True, cwd=str(tmp_path), env={**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)},
    )
    assert result.returncode == 0, f"rc={result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
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


def test_the_xcode_pre_action_engine_is_not_tied_to_its_throwaway_shell() -> None:
    """#5298: ⌘R in Xcode said the app could not reach the server.

    The Dev Local pre-action (`dev-uds-engine.sh`) starts the engine from a subshell that exits at
    once. `start_fichero_server.sh` made that subshell the engine's owner (FICHERO_PARENT_PID), so
    the engine's parent watchdog killed it within 5 s and left a socket nothing answered. The
    pre-action now opts out with FICHERO_PARENT_PID=none, which the start script turns into "no
    owner". Checked live 2026-09-30: the engine still answered /api/health 40 s after the
    pre-action exited. If this goes red, ⌘R stops working again.
    """
    pre_action = (REPO_ROOT / "fichero-server" / "scripts" / "dev-uds-engine.sh").read_text()
    start = START_BACKEND.read_text()
    assert pre_action.count("( FICHERO_PARENT_PID=none ") == 2, "both detached launches (uds and https) opt out"
    assert 'if [ "${FICHERO_PARENT_PID:-}" = "none" ]; then\n  unset FICHERO_PARENT_PID' in start
    assert 'export FICHERO_PARENT_PID="${FICHERO_PARENT_PID:-$PPID}"' in start, "every other launch is still owned"


def test_verify_all_gives_the_engine_imports_check_the_staged_bundle() -> None:
    """The fast tier loops over every scripts/check_*.py with no argument; check_engine_imports_bundled.py needs the
    staged bundle's app_packages (no argument is usage exit 2)."""
    text = _script_text(SCRIPTS_DIR / "verify_all.sh")
    assert '"$guardrail" \\\n        "fichero-server/build/fichero_server/macos/app/Fichero Server.app/Contents/Resources/app_packages"' in text


def _publish_part_body() -> str:
    text = (SCRIPTS_DIR / "release-all.sh").read_text()
    start = text.index("publish_part() {")
    return text[start:text.index("\n}\n", start) + 3]


@pytest.mark.parametrize("public", [False, True])
def test_publish_deploys_the_appcast_with_the_netlify_cli_after_writing_it_and_before_verifying(tmp_path: Path, public: bool) -> None:
    """2026-11-27: the dev publish committed appcast.xml into the tubb.ca repo, but Netlify ignores git pushes on this account, so the
    live feed never moved and verify-appcast failed after 10 minutes. The order is: appcast write, eleventy build, netlify deploy,
    verify, on the dev channel too; FICHERO_SKIP_SITE skips only the docs site."""
    log = tmp_path / "order.log"
    site = tmp_path / "site"
    (site / "apps" / "fichero").mkdir(parents=True)
    root, bin_ = tmp_path / "root", tmp_path / "bin"
    (root / "scripts").mkdir(parents=True)
    bin_.mkdir()
    shutil.copy(SCRIPTS_DIR / "deploy-appcast.sh", root / "scripts" / "deploy-appcast.sh")

    def stub(path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\n" + body + "\n")
        path.chmod(0o755)
    stub(root / "scripts" / "create-github-release.sh", f'echo "<rss/>" > "{site}/apps/fichero/appcast.xml"; echo appcast-write >> "{log}"')
    stub(root / "scripts" / "deploy-site.sh", f'echo docs-site >> "{log}"')
    stub(bin_ / "npx", f'[ "$1" = "@11ty/eleventy" ] && [ "$PWD" = "{site}" ] && echo eleventy-build >> "{log}"')
    stub(bin_ / "netlify", f'[ "$*" = "deploy --prod --dir _site" ] && echo netlify-deploy >> "{log}"')
    harness = "\n".join([
        "set -uo pipefail",
        f'ROOT_DIR="{root}"; DMG_PATH="{tmp_path}/x.dmg"; DEV_DMG_PATH="{tmp_path}/none.dmg"; GITHUB_ARGS=()',
        f"PUBLIC_RELEASE={'true' if public else 'false'}",
        f'guard() {{ [ "$1" = verify-appcast ] && echo verify >> "{log}"; return 0; }}',
        "fail_part() { echo \"FAIL: $*\"; exit 1; }",
        "project_setting() { echo 1; }",
        _publish_part_body(),
        "publish_part",
    ])
    r = subprocess.run(["bash", "-c", harness], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FICHERO_SITE_DIR": str(site)})
    assert r.returncode == 0, r.stdout + r.stderr
    want = ["appcast-write", *(["docs-site"] if public else []), "eleventy-build", "netlify-deploy", "verify"]
    assert log.read_text().split() == want


def _run_update_main(tmp_path: Path, in_main: bool) -> tuple[subprocess.CompletedProcess, list[str]]:
    log, merged = tmp_path / "calls.log", tmp_path / "merged"
    if in_main:
        merged.touch()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, body in {
        "git": f'echo "git $*" >> "{log}"; [ "$1" = merge-base ] && {{ [ -f "{merged}" ]; exit; }}; exit 0',
        "gh": f'echo "gh $*" >> "{log}"; [ "$2" = view ] && exit 1; [ "$2" = merge ] && touch "{merged}"; exit 0',
    }.items():
        (bin_ / name).write_text("#!/usr/bin/env bash\n" + body + "\n")
        (bin_ / name).chmod(0o755)
    r = subprocess.run(["bash", str(SCRIPTS_DIR / "update-main.sh"), "abc123", "2026.11.27"], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FICHERO_REPO_DIR": str(tmp_path)})
    return r, log.read_text().splitlines()


def test_a_release_updates_main_by_a_release_branch_and_a_merged_pr_never_a_push_to_main(tmp_path: Path) -> None:
    """Owner 2026-11-16, done by hand on 2026-11-27 (#7099): push release/<version> at the released sha, open the PR into main,
    merge it with --merge, verify the sha is in origin/main. main is protected: nothing pushes to it, and no v* tag is touched."""
    r, calls = _run_update_main(tmp_path, in_main=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert calls == [
        "git fetch -q origin main",
        "git merge-base --is-ancestor abc123 origin/main",
        "git push origin abc123:refs/heads/release/2026.11.27",
        "gh pr view release/2026.11.27 --json url -q .url",
        "gh pr create --base main --head release/2026.11.27 --title Release 2026.11.27 --body "
        "Release 2026.11.27 at abc123, opened by scripts/update-main.sh after the publish.",
        "gh pr merge release/2026.11.27 --merge",
        "git fetch -q origin main",
        "git merge-base --is-ancestor abc123 origin/main",
    ]
    pushes = [c for c in calls if c.startswith("git push")]
    assert pushes == ["git push origin abc123:refs/heads/release/2026.11.27"] and not any("tag" in c for c in calls)


def test_a_release_whose_sha_is_already_in_main_updates_nothing(tmp_path: Path) -> None:
    r, calls = _run_update_main(tmp_path, in_main=True)
    assert r.returncode == 3 and calls == ["git fetch -q origin main", "git merge-base --is-ancestor abc123 origin/main"]


def test_a_failed_main_update_is_its_own_row_and_never_fails_the_release() -> None:
    text = (SCRIPTS_DIR / "release-all.sh").read_text()
    assert text.index('"$ROOT_DIR/scripts/update-main.sh"') > text.index("run_part Publish publish_part")
    assert 'grep -q "^Publish	OK	"' in text and 'grep -v "^Main updated	" "$FICHERO_RELEASE_SUMMARY" | grep -q "	FAILED	"' in text
