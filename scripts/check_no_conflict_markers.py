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

SCOPE: text source files under version control. Binary files, and files whose
own subject matter is conflict markers (this script, and the test that proves
it fires), are exempt -- an exemption list of two, both named explicitly,
rather than a pattern that could quietly grow.
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

# Extensions worth reading. Anything else is treated as binary and skipped;
# a conflict marker inside a PNG is not a thing anyone can act on.
TEXT_SUFFIXES = {
    ".py", ".swift", ".sh", ".bash", ".zsh", ".js", ".ts", ".json", ".yaml",
    ".yml", ".toml", ".cfg", ".ini", ".md", ".txt", ".html", ".css", ".xml",
    ".plist", ".pbxproj", ".entitlements", ".xcconfig", ".sql", ".rst",
}


def tracked_text_files() -> list[Path]:
    """Every tracked file git knows about, filtered to readable source.

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
        p = Path(rel)
        if p.suffix.lower() in TEXT_SUFFIXES:
            paths.append(p)
    return paths


def offenders(files: list[Path]) -> list[tuple[str, int, str]]:
    found = []
    for rel in files:
        full = REPO_ROOT / rel
        try:
            text = full.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            # Unreadable or not really text. Not an offence -- but not proof
            # of cleanliness either, so it simply does not count toward the
            # scanned population below.
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.startswith(MARKERS):
                found.append((str(rel), lineno, line[:60]))
    return found


def main() -> int:
    files = tracked_text_files()

    readable = 0
    for rel in files:
        try:
            (REPO_ROOT / rel).read_text(encoding="utf-8", errors="strict")
            readable += 1
        except (OSError, UnicodeDecodeError):
            continue

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
