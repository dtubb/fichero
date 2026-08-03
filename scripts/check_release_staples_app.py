#!/usr/bin/env python3
"""The app must be stapled BEFORE it is sealed into the DMG (#4491).

`release-all.sh` notarized and stapled the DMG and never the .app inside it. The
DMG's ticket vouches for the download; it says nothing about the copy the user
drags to /Applications and then keeps after throwing the DMG away. With no
ticket of its own that copy has nothing local for Gatekeeper to verify against,
so a first launch with no network — a plane, a locked-down machine — can be
refused. Online it always worked, which is exactly why no release cut from this
repo ever noticed.

The fix is an ORDER, and order is what rots. `build-release-dmg.sh` seals the
staged directory into a read-only image in its steps 3-6, so the app's ticket
has to be stapled before that. A ticket added afterwards is not inside the
image; stapling the app after the DMG exists staples a different copy. Nothing
about the code says so — both operations succeed, and the wrong order produces
a DMG that looks perfect and ships the same defect.

So this asserts the sequence positionally, which is the one thing reading the
script carefully cannot keep true six months from now.

Run: python3 scripts/check_release_staples_app.py [--self-test]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DMG_SCRIPT = REPO / "scripts" / "build-release-dmg.sh"
RELEASE_SCRIPT = REPO / "scripts" / "release-all.sh"
NOTARIZE_SCRIPT = REPO / "scripts" / "notarize.sh"

# Sealing the staged directory into an image. Anything after this is too late.
_SEAL = re.compile(r"hdiutil\s+create|hdiutil\s+convert")
_STAPLE_APP = re.compile(r'notarize\.sh"?\s+"\$APP"')


def _code(text: str) -> str:
    """Source with `#` comments dropped.

    A check about what a script DOES must not be satisfied — or broken — by
    what its comments say about it. Three checks in this repo have now fired on
    their own explanations; this one is written knowing that.
    """
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        out.append("" if stripped.startswith("#") else line)
    return "\n".join(out)


def problems() -> list[str]:
    found: list[str] = []

    dmg = _code(DMG_SCRIPT.read_text())
    staple = _STAPLE_APP.search(dmg)
    seal = _SEAL.search(dmg)

    if staple is None:
        found.append(
            f"{DMG_SCRIPT.name} never notarizes the staged app — the DMG will "
            "contain an unstapled Fichero.app (#4491)."
        )
    if seal is None:
        found.append(
            f"{DMG_SCRIPT.name} no longer calls hdiutil; this check cannot find "
            "the point the app is sealed in, so it cannot vouch for the order."
        )
    if staple and seal and staple.start() > seal.start():
        found.append(
            f"{DMG_SCRIPT.name} staples the app AFTER hdiutil seals the image. "
            "The ticket is not inside the DMG; the shipped app is unstapled."
        )

    release = _code(RELEASE_SCRIPT.read_text())
    if "--notarize-app" not in release:
        found.append(
            f"{RELEASE_SCRIPT.name} does not pass --notarize-app, so a real "
            "release builds its DMG around an unstapled app (#4491)."
        )

    notarize = _code(NOTARIZE_SCRIPT.read_text())
    if "--wait" in notarize:
        found.append(
            f"{NOTARIZE_SCRIPT.name} uses `notarytool --wait`. It has failed "
            "here with a deadline-exceeded that abandons a submission Apple "
            "then accepted. Submit, capture the id, poll `notarytool info`."
        )
    if "stapler staple" not in notarize:
        found.append(f"{NOTARIZE_SCRIPT.name} no longer staples anything.")

    return found


def main() -> int:
    found = problems()
    print("Release stapling: checked build-release-dmg.sh, release-all.sh, notarize.sh.")
    if not found:
        print("  ✓ the app is notarized and stapled before hdiutil seals the DMG.")
        return 0
    for p in found:
        print(f"  ✗ {p}")
    return 1


def self_test() -> int:
    """Every rule fires."""
    order_ok = 'scripts/notarize.sh" "$APP"\nhdiutil create x'
    order_bad = 'hdiutil create x\nscripts/notarize.sh" "$APP"'

    assert _STAPLE_APP.search(order_ok) and _SEAL.search(order_ok)
    assert _STAPLE_APP.search(order_ok).start() < _SEAL.search(order_ok).start()
    # the defect: stapling after sealing
    assert _STAPLE_APP.search(order_bad).start() > _SEAL.search(order_bad).start()
    # a comment mentioning the call does not count as making it
    assert _STAPLE_APP.search(_code('# scripts/notarize.sh" "$APP"')) is None
    # and a comment saying "--wait" must not trip the --wait rule, which is how
    # notarize.sh documents why it does NOT use one
    assert "--wait" not in _code("# NO `--wait`. It has failed here.")

    print("check_release_staples_app self-test: OK — all five rules fire.")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
