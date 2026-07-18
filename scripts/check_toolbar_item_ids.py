#!/usr/bin/env python3
"""Window toolbar item-id guardrail (#3203)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOW_TOOLBAR_FILES = (ROOT / "fichero" / "fichero" / "Views" / "Shell" / "ContentView" / "ContentView.swift",)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")
_IDLESS_TOOLBAR_ITEM = re.compile(r"\bToolbarItem(?:Group)?\(\s*(?!id\s*:)")


def code_lines(text: str) -> list[str]:
    text = _BLOCK_COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def violations() -> list[str]:
    hits: list[str] = []
    for path in WINDOW_TOOLBAR_FILES:
        rel = path.relative_to(ROOT)
        for line_no, line in enumerate(code_lines(path.read_text(errors="ignore")), start=1):
            if _IDLESS_TOOLBAR_ITEM.search(line):
                hits.append(f"{rel}:{line_no}: {line.strip()}")
    return hits


def _self_test() -> None:
    assert _IDLESS_TOOLBAR_ITEM.search("ToolbarItem(placement: .primaryAction) {")
    assert _IDLESS_TOOLBAR_ITEM.search("ToolbarItemGroup(placement: .automatic) {")
    assert not _IDLESS_TOOLBAR_ITEM.search('ToolbarItem(id: "fichero.x", placement: .automatic) {')
    assert not _IDLESS_TOOLBAR_ITEM.search("ToolbarItemGroup(id: ToolbarID.x, placement: .automatic) {")


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    if "--self-test" in sys.argv:
        _self_test()
        print("check_toolbar_item_ids self-test: OK")
        return 0

    _self_test()
    hits = violations()
    print(f"Toolbar item-id guardrail: scanned {len(WINDOW_TOOLBAR_FILES)} window toolbar file(s).")
    if not hits:
        print("OK: every window ToolbarItem/ToolbarItemGroup has an explicit id.")
        return 0

    print("\nFAILED: window toolbar contribution(s) missing explicit id:")
    for hit in hits:
        print(f"  {hit}")
    print("\nFix: use ToolbarItem(id: ...) / ToolbarItemGroup(id: ...) for window toolbar items.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
