#!/usr/bin/env python3
"""No committed project file under fichero/ carries a home-folder path (#6663).

A shared .xcscheme, .xcconfig or .plist that names a user's home folder breaks every other Mac account and leaks a
personal path from a public repo. Walks fichero/ with scan_rglob (no git needed, hidden and build output dirs skipped); a missing
fichero/ raises and no matching file FAILS.

Usage: scripts/check_no_home_paths_in_project.py [--root DIR]
Exit codes: 0 clean, 1 a home path found, 2 nothing to scan (no matching files)."""
from __future__ import annotations

import sys
from pathlib import Path

from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".xcscheme", ".xcconfig", ".plist")
SKIP_DIRS = {"derived", "DerivedData", "build", "SourcePackages"}  # build output, not committed files
NEEDLE = "/Users/"


def violations(root: Path) -> list[str] | None:
    files = [str(p.relative_to(root)) for suffix in SUFFIXES for p in scan_rglob(root / "fichero", "*" + suffix)
             if not SKIP_DIRS.intersection(p.relative_to(root).parts)]
    if not files:
        return None
    out = []
    for f in sorted(files):
        for n, line in enumerate((root / f).read_text(errors="replace").splitlines(), 1):
            if NEEDLE in line:
                out.append(f"{f}:{n}: home path {NEEDLE!r}; drop it or derive it at run time")
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    found = violations(root)
    if found is None:
        print("BLIND: no .xcscheme/.xcconfig/.plist under fichero/ to scan")
        return 2
    print("\n".join(found) or "ok: no home paths in committed project files")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
