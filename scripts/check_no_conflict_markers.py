#!/usr/bin/env python3
"""No committed file carries an unresolved merge-conflict marker.

WHY THIS EXISTS, and it is not hypothetical: on 2026-08-03 a merge left
conflict markers in ``fichero-mcp/tests/test_mcp_server.py`` and the file was
COMMITTED that way. Python cannot parse ``<<<<<<< HEAD``, so collection of
that module failed and **the entire MCP suite silently stopped running**. The
run stayed green. Nobody noticed until a lane read the file for another
reason, days later.

That is the #4487 shape wearing different clothes: a mechanism reporting
success while measuring nothing. The usual defence -- "the tests would have
caught it" -- is exactly what fails here, because the broken thing IS the
tests, and a suite that cannot load reports no failures.

THE CHEAP MISTAKE THIS GUARDS: ``git merge`` conflicts are resolved by hand,
under time pressure, often in files nobody re-reads. ``git status`` shows
``UU`` at the moment of conflict, but once ``git add`` runs the evidence is
gone and the markers look like ordinary lines in a diff nobody scrolls
through. A structural check costs milliseconds and never forgets to look.

SCOPE: every text file under version control, whatever its name. Binary files, and files whose
own subject matter is conflict markers (this script, and the test that proves
it fires), are exempt -- an exemption list of two, both named explicitly,
rather than a pattern that could quietly grow.

Text is decided by the bytes, not the name: a list of suffixes once read `.pbxproj` but never `.xcfilelist`, and markers
from the cb732e67c merge sat in `FicheroEngineEmbedInputs.xcfilelist` for a day while this passed (#5796). A file is
read when it has no NUL byte and decodes as UTF-8 (git's own test for binary, plus a strict decode).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _check_floor import require_scan_floor  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# Observed 2026-08-03: 3,185 tracked text files. Tripwire at half, per the
# _check_floor contract -- this catches "the scan collapsed", not "the repo
# shrank a bit".
#
# The first draft of this line said 6,847 from nothing at all, and the floor
# derived from it sat ABOVE the true population, so the check exited 2 BLIND
# on a clean tree. Left on the record because it is the argument for the
# floor in miniature: an invented constant produced a check that could not
# pass, and the only reason that was visible in seconds is that "I could not
# measure" and "I measured and found nothing" have different exit codes.
SCAN_FLOOR = 1590

# The three markers git writes. `=======` alone is deliberately NOT one of
# them: it is ordinary reStructuredText and Markdown underlining, and matching
# it would make this check cry wolf on documentation until someone disabled it.
# A guardrail that fires on innocent files gets switched off, and a switched-off
# guardrail is worse than none because it still looks present.
MARKERS = ("<<<<<<< ", ">>>>>>> ", "|||||||")

# Files that legitimately contain marker text: this script, and the fixture
# proving it fires. Named individually on purpose -- a glob here would be a
# hole that widens.
EXEMPT = {
    "scripts/check_no_conflict_markers.py",
    "fichero-server/tests/unit/scripts/test_check_no_conflict_markers.py",
}



def tracked_text_files() -> list[Path]:
    """Every tracked file git knows about (whether it is text is decided when it is read, `_text`).

    Uses ``git ls-files`` rather than rglob so the scan matches what is
    actually COMMITTED -- an untracked scratch file with markers in it is not
    the failure this guards against, and would only produce noise.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = []
    for rel in out.split("\0"):
        if not rel or rel in EXEMPT:
            continue
        paths.append(Path(rel))
    return paths


def _text(rel: Path) -> str | None:
    """The file's text, or None when it is binary (a NUL byte) or not UTF-8: a conflict marker inside a PNG is not a
    thing anyone can act on. Unreadable is not an offence -- but not proof of cleanliness either, so it does not count
    toward the scanned population."""
    try:
        raw = (REPO_ROOT / rel).read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


def offenders(files: list[Path]) -> list[tuple[str, int, str]]:
    found = []
    for rel in files:
        text = _text(rel)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.startswith(MARKERS):
                found.append((str(rel), lineno, line[:60]))
    return found


def main() -> int:
    files = tracked_text_files()

    readable = sum(1 for rel in files if _text(rel) is not None)

    # Floor on what was READ, not on what was found wrong. If this collapses,
    # the check is blind and must say so rather than reporting a clean tree.
    blind = require_scan_floor(readable, SCAN_FLOOR, "tracked text files")
    if blind:
        return blind

    bad = offenders(files)
    if bad:
        print("unresolved merge-conflict markers are COMMITTED:\n")
        for rel, lineno, snippet in bad:
            print(f"  {rel}:{lineno}: {snippet}")
        print(
            "\nA source file with conflict markers does not parse. If it is a "
            "test module, its whole suite stops running AND STAYS GREEN -- "
            "that is how this went unnoticed before (fichero-mcp suite, "
            "2026-08-03). Resolve the conflict; do not delete one side blindly."
        )
        return 1

    print(f"conflict markers: OK ({readable} tracked text files read)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
