#!/usr/bin/env python3
"""Swift visual-language guardrail.

Rule: Swift source must use SF Symbols and system text styles; see agents/ROADMAP.md.

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

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "agents/ROADMAP.md"

KNOWN_VIOLATIONS: dict[str, str] = {
    "fichero/fichero/Models/LibraryManager+Helpers.swift#998f025dc1": "#1913 baseline",
    "fichero/fichero/Models/LibraryManager+Helpers.swift#e7e9bf57a1": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#250d04df8f": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#454091be88": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#22159b57a5": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#23a822622f": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#88f9ebd730": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#9658490640": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#3c1bd504e8": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#cae8e7ae47": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#eaab792d1e": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#8ff7a98841": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#d7dc7e1435": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#db45421877": "#1913 baseline",
    "fichero/fichero/Services/EmbeddedBackendService.swift#0186ffbd87": "#1913 baseline",
    "fichero/fichero/Views/Library/ArtifactEntityViews.swift#00765d227e": "#1913 baseline",
    "fichero/fichero/Views/Library/ArtifactEntityViews.swift#761c2f0c16": "#1913 baseline",
    "fichero/fichero/Views/Library/ArtifactEntityViews.swift#843f4a532a": "#1913 baseline",
    "fichero/fichero/Views/Library/ArtifactEntityViews.swift#50d0228821": "#1913 baseline",
    "fichero/fichero/Views/Library/ArtifactEntityViews.swift#d1e408277f": "#1913 baseline",
    "fichero/fichero/Views/Inspector/Document/Notes/DocumentInspectorAnnotationsTab.swift#074340dfc5": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift#28d9eccb0f": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Drop.swift#1b97ffd731": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#48776b4383": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#34b86466ce": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#d6e6802761": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#608a0ac4c7": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#cfc4119f1d": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#561985c7c5": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#b71beb96fd": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#687138d915": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#f18a1d2a94": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#d98a903978": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#42fe92e145": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#75ccc654cd": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#32f744d6e8": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#92f00f3f9a": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#635b8bb6e0": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#bbb00320af": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#ac59dea688": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#db6b9b6432": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#30363524da": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#2f16a682db": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#f2f03cf46b": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#171066f586": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#e8a0dc4030": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#b69868dc56": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift#e5a80c4f76": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift#f1b40702ab": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift#47eff589b2": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift#7a391923fd": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift#b49f947ddf": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Helpers.swift#7e557f9e65": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Rename.swift#b4f0b7ab00": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/Sections/SidebarSectionHeader.swift#2bb83366b0": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/Sections/SidebarView+UnifiedRows.swift#b51da1152b": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/Sections/SidebarView+UnifiedRows.swift#7ea19d65a1": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/Sections/SidebarView+UnifiedRows.swift#b0818da9cc": "#1913 baseline",
    "fichero/fichero/Views/Sidebar/Sections/SidebarView+UnifiedRows.swift#592a54e784": "#1913 baseline",
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


def _normalized_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()


def _signature_key(rel: str, snippet: str) -> str:
    digest = hashlib.sha1(_normalized_snippet(snippet).encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def _window_snippet(lines: list[str], line_no: int, radius: int = 2) -> str:
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end])


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
                found[_signature_key(rel, _window_snippet(lines, line_no))] = line.strip()
            if _CUSTOM_FONT.search(line):
                found[_signature_key(rel, _window_snippet(lines, line_no))] = line.strip()
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
