#!/usr/bin/env python3
"""No committed project file under fichero/ carries a home-folder path (#6663).

A shared .xcscheme, .xcconfig or .plist that names a user's home folder breaks every other Mac account and leaks a
personal path from a public repo. Reads `git ls-files`; a failed or empty listing FAILS, never passes.

Usage: scripts/check_no_home_paths_in_project.py [--root DIR]
Exit codes: 0 clean, 1 a home path found, 2 nothing to scan (not a git tree, or no matching files)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = (".xcscheme", ".xcconfig", ".plist")
NEEDLE = "/Users/"


def violations(root: Path) -> list[str] | None:
    done = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "fichero"], capture_output=True, text=True)
    files = [f for f in done.stdout.split("\0") if f.endswith(SUFFIXES)] if done.returncode == 0 else []
    if not files:
        return None
    out = []
    for f in files:
        for n, line in enumerate((root / f).read_text(errors="replace").splitlines(), 1):
            if NEEDLE in line:
                out.append(f"{f}:{n}: home path {NEEDLE!r}; drop it or derive it at run time")
    return out


def main(argv: list[str]) -> int:
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    found = violations(root)
    if found is None:
        print("BLIND: no tracked .xcscheme/.xcconfig/.plist under fichero/ to scan")
        return 2
    print("\n".join(found) or "ok: no home paths in committed project files")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
