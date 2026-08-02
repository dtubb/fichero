#!/usr/bin/env python3
"""Toolbar tooltip guardrail.

Rule: icon-only toolbar controls should expose a `.help(...)` tooltip so the
hover affordance is discoverable. This scanner is intentionally conservative:
it only flags clear icon-only `Button` controls in toolbar-focused surfaces
(`.toolbar {}` blocks and `*Toolbar.swift` files), and it skips text-labeled
buttons.

`KNOWN_VIOLATIONS` is the current migration backlog. The script passes today and
fails only when a new icon-only toolbar control is missing a tooltip.

Usage:
    scripts/check_tooltips.py
    scripts/check_tooltips.py --list
    scripts/check_tooltips.py --help
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "agents/ROADMAP.md"

# Current toolbar-tooltip backlog. Keys are `relative/path.swift#signature`.
#: Empty, and that is the finished state of the #1954 migration backlog.
#:
#: Both former entries were fixed rather than re-hashed: `WorkflowExecutionView`
#: got `.help("Refresh runs")` and `NewChainSheet`'s remove-step button got
#: `.help("Remove this step from the chain")`. The gate reported them as "now
#: clean" only because a hash drifted — the same control was still untooltipped
#: under a new content hash, which is what a content-addressed allowlist looks
#: like when the code changes around a violation.
#:
#: That is the trap to remember if this dict ever fills again: a stale entry
#: plus a new entry for the same file is usually ONE unfixed control, not a
#: fixed one and a fresh one.
KNOWN_VIOLATIONS: dict[str, str] = {}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")


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
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = _strip_preview_blocks(text)
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def is_toolbar_surface(path: Path, source: str) -> bool:
    return "Toolbar" in path.name or ".toolbar" in source or "ToolbarItem" in source


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _collect_button_chain(lines: list[str], start: int) -> tuple[int, str]:
    """Return the end line and snippet for a button plus its trailing modifiers."""
    depth = 0
    saw_open = False
    end = start
    start_indent = _line_indent(lines[start])

    for idx in range(start, len(lines)):
        line = lines[idx]
        depth += line.count("{")
        if "{" in line:
            saw_open = True
        depth -= line.count("}")
        end = idx
        if saw_open and depth <= 0:
            break

    for idx in range(end + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            if idx == end + 1:
                end = idx
                continue
            break
        if stripped.startswith(".") and _line_indent(lines[idx]) >= start_indent:
            end = idx
            continue
        break

    return end, "\n".join(lines[start : end + 1])


def _is_text_labeled_button(snippet: str) -> bool:
    if re.search(r"\bButton\s*\(\s*\"", snippet):
        return True
    if re.search(r"\bText\s*\(", snippet):
        return True
    return bool(re.search(r"\bLabel\s*\(", snippet)) and ".labelStyle(.iconOnly)" not in snippet


def _is_icon_only_button(snippet: str) -> bool:
    if _is_text_labeled_button(snippet):
        return False
    if ".help(" in snippet:
        return False
    if ".labelStyle(.iconOnly)" in snippet:
        return True
    return bool(re.search(r"\bImage\s*\(", snippet))


def _snippet_key(path: Path, snippet: str, base_dir: Path = VIEWS_DIR) -> str:
    normalized = re.sub(r"\s+", " ", snippet.strip())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{path.relative_to(base_dir).as_posix()}#{digest}"


def scan(views_dir: Path = VIEWS_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(views_dir.rglob("*.swift")):
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        if not is_toolbar_surface(path, source):
            continue
        lines = code_lines(source)

        for idx, line in enumerate(lines):
            if "Button" not in line:
                continue
            end, snippet = _collect_button_chain(lines, idx)
            if not _is_icon_only_button(snippet):
                continue
            found[_snippet_key(path, snippet, views_dir)] = (
                f"missing .help(...) on icon-only toolbar button (lines {idx + 1}-{end + 1})"
            )
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Toolbar tooltip offenders ({len(found)} location(s)):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Toolbar tooltip guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} icon-only toolbar control(s) missing a tooltip; {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new icon-only toolbar control(s) missing .help(...):")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: add a `.help(...)` tooltip to the icon-only toolbar control. "
            f"Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No new icon-only toolbar controls are missing tooltips.")
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
    _require_scan_roots_4382(VIEWS_DIR)
    raise SystemExit(main())
