#!/usr/bin/env python3
"""Reader icon buttons must carry the house touch target (#4479).

## The defect

`.buttonStyle(.plain)` removes a button's default padding and background. With a
bare `Image(systemName:)` label and no `.frame`, the clickable area is the
GLYPH'S DRAWN PIXELS — roughly 13x13pt for a default SF Symbol — against a house
policy of `MiniToolbar.touchTargetSide`, which is 28pt on Mac and 44pt on touch.

That is Daniel's "you can't PROPERLY click on an icon": the buttons work when
hit. They are a fifth of the area they look, so aiming fails, not clicking.

24 of 26 such buttons in `Views/Reader/` had no target. The inconsistency lived
INSIDE one toolbar — `ReaderToolbar.swift` applied the policy while
`ReaderToolbar+Controls.swift`, the same toolbar's controls, applied it to none
of its thirteen. Two implementations of one rule with nothing forcing them to
agree.

## Why a guardrail rather than a comment

The fix is uniform and mechanical, which is exactly the kind that decays: the
next button added to that toolbar will be written the way its thirteen
neighbours were, and nothing would notice. `impossible > checked`.

## Blindness

This is a sweep for an ABSENCE, so it must know when it is measuring nothing.
Finding zero `.buttonStyle(.plain)` buttons in the whole Reader tree means the
detector broke or the tree moved, NOT that everything is fine — my first
version of this returned "0 offenders" immediately after an edit that had
half-applied the fix, which would have reported success over a broken pass.

Exit codes:
    0   every plain icon button in Views/Reader carries a touch target
    1   at least one does not
    2   BLIND -- scan root missing, or no plain buttons found at all

Usage:
    scripts/check_reader_touch_targets.py
    scripts/check_reader_touch_targets.py --list
    scripts/check_reader_touch_targets.py --root PATH   # tests only
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READER_DIR = ROOT / "fichero" / "fichero" / "Views" / "Reader"
RULE_DOC = "#4479"

PLAIN = ".buttonStyle(.plain)"
# `readerIconTarget()` is the canonical form (it applies both of the others);
# the raw tokens stay accepted so a button that spells the frame out by hand —
# as `ReaderToolbar.swift` did before the modifier existed — is not a false red.
TARGET_TOKENS = ("readerIconTarget()", "touchTargetSide", "contentShape(")


def _button_block(source: str, plain_index: int) -> str | None:
    """The `Button ... }` block immediately preceding a `.buttonStyle(.plain)`.

    Walks BACKWARDS from the modifier, brace-matching, rather than pattern
    matching forwards. The regex version of this broke the moment a button had
    modifiers between its `Image` and its `.buttonStyle` — which is most of
    them — and silently matched nothing at all afterwards.
    """
    close = source.rfind("}", 0, plain_index)
    if close == -1:
        return None

    depth = 0
    for cursor in range(close, -1, -1):
        char = source[cursor]
        if char == "}":
            depth += 1
        elif char == "{":
            depth -= 1
            if depth == 0:
                start = source.rfind("Button", 0, cursor)
                if start == -1:
                    return None
                # A `label:` closure means the opening brace we found is the
                # label's, not the action's — keep walking out to the Button.
                head = source[start:cursor]
                if "label:" in head or "(" in head or head.strip() == "Button":
                    return source[start : close + 1]
                return source[start : close + 1]
    return None


def scan(reader_dir: Path) -> tuple[list[dict], int]:
    """Return (offenders, total_plain_buttons)."""
    offenders: list[dict] = []
    total = 0

    for path in sorted(reader_dir.rglob("*.swift")):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        cursor = 0
        while True:
            found = source.find(PLAIN, cursor)
            if found == -1:
                break
            cursor = found + len(PLAIN)
            total += 1

            block = _button_block(source, found)
            if block is None or "Image(systemName:" not in block:
                # Not an icon button (text label, or unparseable) — a text
                # button already has a target the width of its text.
                continue
            if any(token in block for token in TARGET_TOKENS):
                continue
            offenders.append(
                {
                    "file": _rel(path),
                    "line": source[:found].count("\n") + 1,
                }
            )

    return offenders, total


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _root_from(argv: list[str]) -> Path:
    if "--root" in argv:
        index = argv.index("--root")
        if index + 1 >= len(argv):
            print("--root needs a path", file=sys.stderr)
            raise SystemExit(2)
        return Path(argv[index + 1])
    return READER_DIR


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    reader_dir = _root_from(argv)
    if not reader_dir.exists():
        print(
            f"check_reader_touch_targets: BLIND -- scan root missing: {reader_dir}",
            file=sys.stderr,
        )
        return 2

    offenders, total = scan(reader_dir)

    if total == 0:
        print(
            "check_reader_touch_targets: BLIND -- found no .buttonStyle(.plain) "
            "buttons at all. The detector broke or the tree moved; zero "
            "offenders here would be a measurement of nothing.",
            file=sys.stderr,
        )
        return 2

    print(f"Reader touch-target guardrail: swept {_rel(reader_dir)}")
    print(
        f"  {total} plain button(s); {len(offenders)} icon button(s) without a target."
    )

    if "--list" in argv:
        for record in offenders:
            print(f"      {record['file']}:{record['line']}")
        return 0

    if offenders:
        print(f"\n  {len(offenders)} icon button(s) clickable only on the glyph:")
        for record in offenders:
            print(f"      {record['file']}:{record['line']}")
        print(
            "\n`.buttonStyle(.plain)` strips the default padding, so a bare\n"
            "`Image(systemName:)` label is clickable only where it is drawn — about\n"
            "13pt, against the house 28pt/44pt. Give the label:\n"
            "    .frame(\n"
            "        minWidth: MiniToolbar<EmptyView, EmptyView>.touchTargetSide,\n"
            "        minHeight: MiniToolbar<EmptyView, EmptyView>.touchTargetSide\n"
            "    )\n"
            f"as ReaderToolbar.swift already does. Rule pointer: {RULE_DOC}."
        )
        return 1

    print("\nPASS every reader icon button carries the house touch target.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
