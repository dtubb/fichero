"""The pdfium placement rides EVERY engine staging, not just releases (#4555).

The placement lived only in release-all.sh, applied after `preflight
--rebuild` — so any Briefcase rebuild outside a release wiped it: the engine
then extracted pdfium into the container tmp at runtime and hardened-runtime
library validation refused the dlopen (2026-08-08, live). DMGs got the fix;
every developer build silently didn't.

Two guards here:
1. Structural pins: clean-embedded-engine.sh (which preflight runs on every
   staging) calls the placement, BEFORE its signing section, and release-all
   keeps its now-idempotent call.
2. A firing fixture for the placement script itself: it places, it is
   idempotent, and it FAILS loudly when the wheel's dylib is absent — a
   check never observed to fail is not protection.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
STAGING = REPO_ROOT / "scripts" / "clean-embedded-engine.sh"
PLACER = REPO_ROOT / "scripts" / "place_pdfium_for_kreuzberg.py"
RELEASE = REPO_ROOT / "scripts" / "release-all.sh"
PREFLIGHT = REPO_ROOT / "scripts" / "preflight-embedded-engine.sh"


# ---- structural pins ---------------------------------------------------------


def test_staging_script_places_pdfium_before_signing():
    text = STAGING.read_text()
    placement_at = text.index("place_pdfium_for_kreuzberg.py")
    signing_at = text.index('if [ -n "$SIGN_IDENTITY" ]')
    assert placement_at < signing_at, (
        "the placement must run BEFORE the signing section so the placed "
        "dylib is signed with everything else"
    )


def test_preflight_runs_the_staging_script():
    """The 'every staging' premise: preflight calls clean-embedded-engine.sh."""
    assert "clean-embedded-engine.sh" in PREFLIGHT.read_text()


def test_release_keeps_its_own_placement_call():
    """release-all.sh stays a belt over the staging suspenders — now a no-op
    that finds the file already correct, but never removed silently."""
    assert "place_pdfium_for_kreuzberg.py" in RELEASE.read_text()


# ---- firing fixture for the placement itself ---------------------------------


def _run_placer(app_packages: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PLACER), str(app_packages)],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_bundle(tmp_path: Path, with_wheel_dylib: bool) -> Path:
    app_packages = tmp_path / "app_packages"
    (app_packages / "kreuzberg").mkdir(parents=True)
    raw = app_packages / "pypdfium2_raw"
    raw.mkdir()
    if with_wheel_dylib:
        (raw / "libpdfium.dylib").write_bytes(b"not-a-real-dylib-but-bytes")
    return app_packages


def test_placement_places_and_is_idempotent(tmp_path):
    app_packages = _make_bundle(tmp_path, with_wheel_dylib=True)

    first = _run_placer(app_packages)
    assert first.returncode == 0, first.stderr
    placed = app_packages / "kreuzberg" / "libpdfium.dylib"
    assert placed.read_bytes() == b"not-a-real-dylib-but-bytes"

    second = _run_placer(app_packages)
    assert second.returncode == 0
    assert "already matches" in second.stdout


def test_placement_fails_loudly_when_the_wheel_dylib_is_absent(tmp_path):
    """The fixture that FIRES: no pypdfium2 dylib → non-zero, with the reason."""
    app_packages = _make_bundle(tmp_path, with_wheel_dylib=False)

    result = _run_placer(app_packages)
    assert result.returncode != 0
    assert "libpdfium.dylib" in result.stderr
    assert "requires" in result.stderr  # names the actionable cause


def test_placement_fails_loudly_without_kreuzberg(tmp_path):
    (tmp_path / "app_packages").mkdir()

    result = _run_placer(tmp_path / "app_packages")
    assert result.returncode != 0
    assert "kreuzberg" in result.stderr
