#!/usr/bin/env python3
"""Every `swiftc` that builds a helper shipped inside the app names the deployment floor (spec:
platform.27-only-api-gated, #5730).

The Mac app target is built at macOS 26.0, so the compiler refuses a 27-only API used without an availability check.
A helper compiled by a bare `swiftc` is built for the HOST's OS instead (27 here), so the same mistake compiles and
then crashes or refuses to launch on a 26 Mac (the fm-bridge was staged with minos 27.0 once, 2026-09-04). This
checks that every `swiftc`/`clang` command (also via `xcrun`, or after `&&` / `;`) in the build scripts passes
`-target arm64-apple-macos26.0`.

Run: python scripts/check_swiftc_floor.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `_scan_files` beside this script, however it is loaded
from _scan_files import scan_rglob  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIRS = ("scripts", "fichero-server/scripts", "fichero-server/bin")
FLOOR_TARGET = "-target arm64-apple-macos26.0"
# a command (line start, or after && ; | ||, optionally via `xcrun`), not `command -v swiftc`
_SWIFTC = re.compile(r"(?:^|&&|\|\||[;|])\s*(?:xcrun\s+(?:-\S+\s+\S+\s+)*)?(?:swiftc|clang(?:\+\+)?)\s")
# whole words: `-parse-as-library` is a flag of a real build (the fm-bridge's), not swiftc's `-parse`, which builds nothing
_BUILDS_NOTHING = frozenset({"-parse", "-fsyntax-only", "-typecheck", "-E", "--version"})


def invocations(text: str) -> list[tuple[int, str]]:
    """(first line number, the whole command) for every `swiftc` command, continuation lines joined."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.lstrip().startswith("#") and _SWIFTC.search(line):
            start, command = i + 1, line
            while command.rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                command = command.rstrip()[:-1] + " " + lines[i].strip()
            out.append((start, command))
        i += 1
    return out


def scan(root: Path = ROOT) -> list[str]:
    problems, scanned = [], 0
    for folder in SCRIPT_DIRS:
        # a folder a checkout may lack is skipped here; a scan that read NO script at all fails below
        for path in sorted(scan_rglob(root / folder, "*.sh", optional=True)):
            scanned += 1
            for line_no, command in invocations(path.read_text(encoding="utf-8", errors="ignore")):
                if _BUILDS_NOTHING & set(command.split()):
                    continue  # a parse-only check builds nothing
                if FLOOR_TARGET not in command and "--target arm64-apple-macos26.0" not in command:
                    problems.append(f"{path.relative_to(root)}:{line_no}: compiler without `{FLOOR_TARGET}`")
    if not scanned:
        problems.append(f"no .sh script under {', '.join(SCRIPT_DIRS)} in {root}: the scan read nothing, so it proves nothing")
    return problems


def main() -> int:
    problems = scan()
    if problems:
        print("FAIL: a helper built for the host's OS can use a 27-only API unflagged:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print("OK check_swiftc_floor: every swiftc/clang that builds a helper targets macOS 26.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
