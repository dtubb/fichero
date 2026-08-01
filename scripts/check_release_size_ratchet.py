#!/usr/bin/env python3
"""Release-artifact size ratchet (#4444): the shipped binary, app bundle, and
DMG may never grow past their own best-ever size.

Every Sparkle update is a download — a build that silently doubled in size
should never reach a user's machine. A byte count does not vary with machine
load the way a timing does, so — like the query-count ratchet (#4443) — this
is held EXACTLY: no tolerance, no jitter allowance. A real increase (a new
dependency, an embedded model) is accepted by rerunning with
--update-baseline and committing the baseline with a note saying what it
bought — exactly the conversation worth having before shipping a bigger
download.

Wired into scripts/release-all.sh right after the DMG is notarized and
stapled — the one point the real, final artifact exists — and BEFORE the
TestFlight archive/upload steps, which are the expensive, slow part of a
release. A size blowup must abort a release before spending 10+ minutes
archiving and uploading, not after.

Measures three things from one signed, staged build:
  release.app_binary  — the main executable Mach-O inside the .app
  release.app_bundle  — every byte inside the .app bundle (files only, no
                         symlinks — Frameworks' Versions/Current etc. would
                         otherwise double-count)
  release.dmg          — the final, stapled .dmg file

Usage:
    check_release_size_ratchet.py --app PATH/Fichero.app --dmg PATH/Fichero.dmg
    check_release_size_ratchet.py --app ... --dmg ... --update-baseline
    check_release_size_ratchet.py            # no args: scripts/verify_all.sh's
                                              # --fast sweep runs every
                                              # scripts/check_*.py with none.
                                              # Looks at the standard
                                              # build/releases/ location; if no
                                              # release was just built there,
                                              # prints NOT ARMED and exits 0 —
                                              # a normal dev gate run has
                                              # nothing to measure, and that is
                                              # not the same claim as "blind".
                                              # --app/--dmg passed explicitly
                                              # (as release-all.sh does) are
                                              # held to full BLIND/FAIL rigor.

Exit codes:
    0  every measurement is at or below its best-ever size (or NOT ARMED)
    1  a measurement GREW past its best-ever size — the ratchet FIRED
    2  BLIND — asked to check a specific build that could not be measured
       (missing app/DMG/executable). Distinct from 1: "I could not measure"
       is not "no regression".
"""

from __future__ import annotations

import argparse
import json
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "release_size_baseline.json"
# The layout release-all.sh actually builds (build-release-dmg.sh stages the
# signed app at build/releases/dmg-stage/Fichero.app; notarize.sh staples
# build/releases/Fichero.dmg in place). Referenced by NAME inside main() —
# not baked into argparse defaults — so a test can monkeypatch either
# constant and see main() honor the new value.
DEFAULT_APP_PATH = ROOT / "build" / "releases" / "dmg-stage" / "Fichero.app"
DEFAULT_DMG_PATH = ROOT / "build" / "releases" / "Fichero.dmg"

BLIND_EXIT_CODE = 2


class Blind(Exception):
    """Raised when the artifact to measure cannot be found at all."""


def _app_binary_path(app_path: Path) -> Path:
    """Resolve the main executable inside a .app bundle via its Info.plist.

    Not hardcoded to the app name — CFBundleExecutable is the actual
    contract, so a rename of the target doesn't silently start measuring a
    stale or missing path.
    """
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.is_file():
        raise Blind(f"no Info.plist at {plist_path}")
    with plist_path.open("rb") as fh:
        plist = plistlib.load(fh)
    executable = plist.get("CFBundleExecutable")
    if not executable:
        raise Blind(f"{plist_path} has no CFBundleExecutable")
    binary_path = app_path / "Contents" / "MacOS" / executable
    if not binary_path.is_file():
        raise Blind(f"main executable missing at {binary_path}")
    return binary_path


def _bundle_bytes(app_path: Path) -> int:
    """Sum of actual file byte sizes under the bundle — NOT `du` disk usage.

    `du` reports space in filesystem blocks, which varies with the volume's
    block size; two machines building the identical bundle could then report
    different "sizes" for a reason that has nothing to do with the artifact.
    Summing `st_size` over every regular file is exact and machine-independent
    — the same property that lets this ratchet skip a jitter allowance.
    """
    total = 0
    for path in app_path.rglob("*"):
        if path.is_symlink():
            continue  # e.g. Framework/Versions/Current — would double-count
        if path.is_file():
            total += path.stat().st_size
    return total


def measure(app_path: Path, dmg_path: Path) -> dict[str, int]:
    if not app_path.is_dir():
        raise Blind(f"app bundle not found at {app_path}")
    if not dmg_path.is_file():
        raise Blind(f"DMG not found at {dmg_path}")
    binary_path = _app_binary_path(app_path)
    return {
        "release.app_binary": binary_path.stat().st_size,
        "release.app_bundle": _bundle_bytes(app_path),
        "release.dmg": dmg_path.stat().st_size,
    }


def _load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise Blind(
            f"{path} is not valid JSON — restore it from git rather than "
            f"deleting it, or the ratchet silently starts over at whatever "
            f"today's build happens to be."
        ) from None


def _write_baseline(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    """Repo-relative when possible (the normal case), absolute otherwise —
    e.g. a test pointing --baseline at a tmp_path is not under ROOT."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def run(app: Path, dmg: Path, baseline_path: Path, update_baseline: bool) -> int:
    measured = measure(app, dmg)  # raises Blind
    baseline = _load_baseline(baseline_path)  # raises Blind

    if update_baseline:
        for name, size in measured.items():
            baseline[name] = {"bytes": size, "note": "manually updated"}
        _write_baseline(baseline_path, baseline)
        print(f"check_release_size_ratchet: baseline updated -> {baseline_path}")
        for name, size in sorted(measured.items()):
            print(f"  {name}: {_human(size)} ({size} bytes)")
        return 0

    fired = False
    changed = False
    print()
    for name, size in sorted(measured.items()):
        entry = baseline.get(name)
        if entry is None:
            baseline[name] = {"bytes": size, "note": "first recorded run"}
            changed = True
            print(f"  {name}: {_human(size)} ({size} bytes) — baseline set")
            continue
        best = int(entry["bytes"])
        if size > best:
            fired = True
            print(
                f"  {name}: {_human(size)} ({size} bytes) vs best "
                f"{_human(best)} ({best} bytes) -> GREW"
            )
        elif size < best:
            baseline[name] = {"bytes": size, "note": f"tightened from {best} bytes"}
            changed = True
            print(
                f"  {name}: {_human(size)} ({size} bytes) — SMALLER than best "
                f"{_human(best)}. Ratchet tightened."
            )
        else:
            print(f"  {name}: {_human(size)} ({size} bytes) (best {_human(best)})")

    if changed:
        _write_baseline(baseline_path, baseline)

    if fired:
        print(
            "\nrelease-size ratchet FAILED: at least one artifact grew past its "
            "best-ever size.\n"
            "\n"
            "Held EXACTLY, no tolerance — unlike a timing, a byte count does not "
            "vary with machine load, so any growth is real.\n"
            "\n"
            "If this is a REAL and accepted increase (a new dependency, an "
            "embedded model), rerun with --update-baseline and commit "
            f"{_display_path(baseline_path)} — say what it bought."
        )
        return 1

    print("\nrelease-size ratchet: OK (nothing grew past its best-ever size)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--app", type=Path, default=None,
        help=f"Path to the signed .app bundle (default: {DEFAULT_APP_PATH})",
    )
    parser.add_argument(
        "--dmg", type=Path, default=None,
        help=f"Path to the notarized+stapled .dmg (default: {DEFAULT_DMG_PATH})",
    )
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help=f"Baseline JSON to compare/update (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Accept every measured size as the new baseline, no comparison",
    )
    args = parser.parse_args(argv)

    # The DEFAULT baseline is REPO CONTENT (committed, unlike the app/DMG,
    # which are gitignored build output) and must exist — checked FIRST,
    # exactly like check_coverage_ratchet.py's baseline check. That is what
    # makes a MOVED tree distinguishable from an ordinary dev machine with no
    # fresh release built: scripts/verify_all.sh's guardrail-blindness sweep
    # (test_guardrails_fail_on_missing_input.py, #4382) runs every
    # scripts/check_*.py alone in an empty directory, where this default
    # baseline is also absent — so it fails loudly (BLIND) there. Two
    # exemptions: an EXPLICITLY passed --baseline (the legitimate "no
    # baseline yet" first-run case, also how this script's own tests exercise
    # a fresh baseline) and --update-baseline (whose entire point is to
    # CREATE a missing baseline).
    baseline_path = args.baseline if args.baseline is not None else DEFAULT_BASELINE
    if args.baseline is None and not args.update_baseline and not baseline_path.is_file():
        print(
            f"check_release_size_ratchet: BLIND — baseline missing at "
            f"{_display_path(baseline_path)} (the tree moved; restore it from git)",
            file=sys.stderr,
        )
        return BLIND_EXIT_CODE

    # Explicit --app/--dmg (release-all.sh always passes both) are held to
    # full rigor: a missing artifact is BLIND. Falling back to the DEFAULT_*
    # paths (the argless gate-sweep case) is different — most gate runs have
    # not just built a release, so a missing default is NOT ARMED, not blind.
    explicit = args.app is not None or args.dmg is not None
    app_path = args.app if args.app is not None else DEFAULT_APP_PATH
    dmg_path = args.dmg if args.dmg is not None else DEFAULT_DMG_PATH

    if not explicit and not (app_path.is_dir() and dmg_path.is_file()):
        print(
            "release-size ratchet: NOT ARMED — no release build at "
            f"{_display_path(app_path)} / {_display_path(dmg_path)}. "
            "release-all.sh passes --app/--dmg explicitly after building one; "
            "pass them here too to check a specific build."
        )
        return 0

    try:
        return run(app_path, dmg_path, baseline_path, args.update_baseline)
    except Blind as exc:
        print(f"check_release_size_ratchet: BLIND — {exc}", file=sys.stderr)
        return BLIND_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
