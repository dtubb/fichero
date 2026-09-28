#!/usr/bin/env python3
"""A one-line NAME loses its middle, never its end (Daniel, 2026-09-28).

"Acceptance 2026-09-27b" in the sidebar read "Acceptance 202…": the end -- the part that tells two
libraries, two pages, two versions apart -- was the part cut. Finder truncates names in the middle
("Accept…09-27b"). Every `Text(<name>)` in the surfaces that list names (the sidebar's rows and
library headers, the pane head's path crumbs) must say `.truncationMode(.middle)` in its own
modifier chain -- unless that chain allows it more than one line (`.lineLimit(2)`, `.lineLimit(nil)`):
a name in a list is one line whether or not its chain says so (the library header's did not).

Usage: python3 scripts/check_name_truncation.py      # exit 1 on a name that truncates at its end
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "fichero" / "fichero"
#: The surfaces that show names one to a line.
SCANNED = [
    APP / "Views" / "Sidebar" / "ItemRow",
    APP / "Views" / "Sidebar" / "Sections",
    APP / "Views" / "Shell" / "PaneHead" / "PaneHead.swift",
]
#: A Text of a name: its argument is a name-ish identifier (`name`, `libraryName`, `crumb.title`, ...).
NAME_TEXT = re.compile(r"\bText\(\s*((?:\w+\.)*\w*(?:[Nn]ame|[Tt]itle))\s*\)")


def violations(files: list[Path]) -> list[str]:
    found: list[str] = []
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines):
            if not NAME_TEXT.search(line) or line.lstrip().startswith("//"):
                continue
            # The Text's own modifier chain: the following lines that continue it (`.modifier`, or a comment).
            chain: list[str] = []
            for follow in lines[number + 1:]:
                stripped = follow.strip()
                if stripped.startswith(".") or stripped.startswith("//"):
                    chain.append(stripped)
                    continue
                break
            text = " ".join(chain)
            # One line unless the chain says otherwise: a name in these lists is held to one line by
            # the list itself even when its own chain names no lineLimit (the library header was).
            multi_line = re.search(r"\.lineLimit\((?!1\))", text) is not None
            # `// not a name` in the chain opts a Text out, visibly and with its reason (a banner heading).
            if "// not a name" in text:
                continue
            if not multi_line and ".truncationMode(.middle)" not in text:
                found.append(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}:{number + 1}: {line.strip()}")
    return found


def files_under(targets: list[Path]) -> list[Path]:
    out: list[Path] = []
    for target in targets:
        out.extend(sorted(target.rglob("*.swift")) if target.is_dir() else [target])
    return out


def main() -> int:
    files = files_under(SCANNED)
    if len(files) < 5:
        print(f"name-truncation guard: only {len(files)} files scanned -- the paths moved; update SCANNED.",
              file=sys.stderr)
        return 2
    found = violations(files)
    if found:
        print("A one-line name that truncates at its END (Finder keeps the tail; add "
              "`.truncationMode(.middle)`):\n", file=sys.stderr)
        for entry in found:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print(f"✓ Every one-line name in {len(files)} files truncates in the middle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
