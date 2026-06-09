#!/usr/bin/env python3
"""Swift visual-language guardrail.

Rule: Swift source must use SF Symbols and system text styles; see docs/ROADMAP.md.

Flags emoji codepoints in Swift code and hardcoded custom fonts such as
`.font(.custom(...))` or `Font(name: ...)`. The current backlog lives in
KNOWN_VIOLATIONS, so this script passes today and fails only when a new offender
appears. Remove entries as the SwiftUI surface migrates to SF Symbols/system
fonts.

Usage:
    scripts/check_no_emoji_sf_symbols.py
    scripts/check_no_emoji_sf_symbols.py --list
    scripts/check_no_emoji_sf_symbols.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/ROADMAP.md"

KNOWN_VIOLATIONS: dict[str, str] = {
    'fichero/fichero/Models/LibraryManager+Helpers.swift:161:emoji': '#1913 baseline',
    'fichero/fichero/Models/LibraryManager+Helpers.swift:170:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:70:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:88:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:110:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:133:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:144:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:159:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:168:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:175:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:177:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:185:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:186:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:267:emoji': '#1913 baseline',
    'fichero/fichero/Services/EmbeddedBackendService.swift:272:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/ArtifactEntityViews.swift:65:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/ArtifactEntityViews.swift:66:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/ArtifactEntityViews.swift:67:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/ArtifactEntityViews.swift:68:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/ArtifactEntityViews.swift:69:emoji': '#1913 baseline',
    'fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorAnnotationsTab.swift:353:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Drop.swift:8:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Drop.swift:91:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:25:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:28:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:51:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:90:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:97:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:101:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:114:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:131:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:134:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:138:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:218:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:224:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:249:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:252:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:267:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:290:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:306:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:311:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:323:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:325:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:347:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:364:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:369:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:374:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+DropHandlers.swift:378:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Helpers.swift:230:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Helpers.swift:233:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Helpers.swift:235:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Helpers.swift:251:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Helpers.swift:253:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarItemRow+Rename.swift:44:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarSectionHeader.swift:76:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarView+UnifiedRows.swift:21:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarView+UnifiedRows.swift:43:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarView+UnifiedRows.swift:48:emoji': '#1913 baseline',
    'fichero/fichero/Views/Sidebar/SidebarView+UnifiedRows.swift:52:emoji': '#1913 baseline',
}
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")
_EMOJI = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "]"
)
_CUSTOM_FONT = re.compile(r"\.font\s*\(\s*\.custom\s*\(|\bFont\s*\(\s*name\s*:")


def _strip_preview_blocks(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = text.find("#Preview", i)
        if m == -1:
            out.append(text[i:])
            break
        out.append(text[i:m])
        brace = text.find("{", m)
        if brace == -1:
            out.append(text[m:])
            break
        depth = 0
        j = brace
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        out.append("\n" * text[m:j].count("\n"))
        i = j
    return "".join(out)


def code_lines(text: str) -> list[str]:
    text = _strip_preview_blocks(_BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text))
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def scan() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(SWIFT_DIR.rglob("*.swift")):
        try:
            lines = code_lines(path.read_text(errors="ignore"))
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(lines, 1):
            if _EMOJI.search(line):
                found[f"{rel}:{line_no}:emoji"] = line.strip()
            if _CUSTOM_FONT.search(line):
                found[f"{rel}:{line_no}:custom-font"] = line.strip()
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"No-emoji/SF-Symbols guardrail offenders ({len(found)} locations):\n")
        for key, line in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {line}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"No-emoji/SF-Symbols guardrail: scanned {SWIFT_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} offender location(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new emoji/custom-font offender(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: use Image(systemName:) / Label systemImage and SwiftUI system text styles. "
            f"Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries; clean them up when convenient.)")
    print("\nOK: no new emoji or custom-font offenders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
