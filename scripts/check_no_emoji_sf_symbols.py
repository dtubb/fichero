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

KNOWN_VIOLATIONS: dict[str, str] = {}
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


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(SWIFT_DIR)
    raise SystemExit(main())
