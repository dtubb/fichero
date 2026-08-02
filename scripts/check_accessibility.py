#!/usr/bin/env python3
"""Accessibility / VoiceOver guardrail (#2285).

Rule (reform master plan §6d 'Quality gates'):

    > Every interactive control must be labeled for VoiceOver. An icon-only
    > control (a `Button`/`Toggle` whose content is just an `Image` with no
    > text `Label`/`Text`) is invisible to a screen reader unless it carries an
    > explicit `.accessibilityLabel(...)`. Text-labeled controls and
    > `Label("text", systemImage:)` controls are already announced and are not
    > flagged.

This scanner is intentionally conservative — it only flags clear icon-only
`Button` controls that lack an `.accessibilityLabel(...)`. A `Label(...)` with a
visible text title, a `Text(...)`, or a `Button("literal", ...)` is announced by
VoiceOver automatically and is skipped. `#Preview {}` blocks and comments are
stripped before scanning.

`KNOWN_VIOLATIONS` (seeded in check_accessibility_known_violations.json) is the
current migration backlog. The script passes today and fails only when a NEW
icon-only control appears without an accessibility label. Regenerate the baseline
with `--update` after you have legitimately added new controls (review the diff!).

Usage:
    scripts/check_accessibility.py
    scripts/check_accessibility.py --list
    scripts/check_accessibility.py --update   # rewrite the baseline JSON
    scripts/check_accessibility.py --help
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero"
BASELINE = Path(__file__).resolve().parent / "check_accessibility_known_violations.json"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

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


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _bracket_delta(line: str) -> int:
    """Net unclosed brackets on one line — parens, squares AND BRACES.

    Braces matter as much as parens here: `.contextMenu { ... }`,
    `.overlay { ... }` and `.background { ... }` are trailing modifiers whose
    bodies span lines and do not begin with ".". Counting only `(` and `[` left
    those truncating the chain exactly as the original bug did — found by this
    scanner's own self-test before it shipped, which is the entire argument for
    having one.
    """
    return (
        (line.count("(") - line.count(")"))
        + (line.count("[") - line.count("]"))
        + (line.count("{") - line.count("}"))
    )


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

    # Trailing modifiers, tracking BRACKET DEPTH across continuation lines
    # (#4479).
    #
    # This used to stop at the first continuation line not beginning with ".",
    # so a MULTI-LINE modifier truncated the chain and everything below was
    # invisible:
    #
    #     .disabled(isEditing == nil)
    #     .help(isEditing == nil
    #         ? "Not available"          <- stopped here
    #         : "Edit image")
    #     .accessibilityLabel("Edit")    <- never seen; reported MISSING
    #
    # It produced a false positive on `ReaderToolbar+Controls.editButton`, which
    # HAD a label three lines below a multi-line `.help`. Worse, that button
    # already sat in KNOWN_VIOLATIONS — so the allowlist had been silencing a
    # SCANNER BUG rather than a real violation, invisibly, until an unrelated
    # edit changed its content hash. An exemption that documents a broken tool
    # is worse than no tool: it makes the defect reviewed and permanent.
    #
    # A modifier now continues while its own brackets are unbalanced, so its
    # wrapped arguments cannot end the chain.
    open_brackets = 0
    for idx in range(end + 1, len(lines)):
        line = lines[idx]
        stripped = line.strip()

        if open_brackets > 0:
            # Inside a modifier's wrapped arguments — consume unconditionally.
            open_brackets += _bracket_delta(line)
            end = idx
            continue

        if not stripped:
            if idx == end + 1:
                end = idx
                continue
            break

        if stripped.startswith(".") and _line_indent(line) >= start_indent:
            open_brackets = _bracket_delta(line)
            end = idx
            continue
        break

    return end, "\n".join(lines[start : end + 1])


def _is_text_labeled_button(snippet: str) -> bool:
    # Button("text", ...) — string title is announced.
    if re.search(r"\bButton\s*\(\s*\"", snippet):
        return True
    # A visible Text(...) in the label is announced.
    if re.search(r"\bText\s*\(", snippet):
        return True
    # Label(title, systemImage:) provides a spoken title unless icon-only.
    #
    # The title may be a VARIABLE, not only a string literal (#4479 follow-up).
    # This used to require `Label("`, so `Label(label, systemImage: icon)` — a
    # menu row whose title is passed in — was classified icon-only and reported
    # as unlabeled, though VoiceOver announces it perfectly well.
    #
    # Both those buttons sat in KNOWN_VIOLATIONS, so this second scanner bug was
    # ALSO being silenced by the allowlist, and only surfaced when the chain-walk
    # fix above changed their content hashes. Two distinct detector defects,
    # both preserved as reviewed exceptions, both invisible until something
    # unrelated moved.
    if re.search(r"\bLabel\s*\(", snippet) and ".labelStyle(.iconOnly)" not in snippet:
        return True
    return False


def _is_icon_only_button(snippet: str) -> bool:
    if _is_text_labeled_button(snippet):
        return False
    # Already labeled for VoiceOver — fine.
    if ".accessibilityLabel(" in snippet or ".accessibilityHidden(true)" in snippet:
        return False
    # An icon: explicit Image(...) or Label(.iconOnly) or systemImage-only.
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
        if "Button" not in source:
            continue
        lines = code_lines(source)
        for idx, line in enumerate(lines):
            if "Button" not in line:
                continue
            end, snippet = _collect_button_chain(lines, idx)
            if not _is_icon_only_button(snippet):
                continue
            found[_snippet_key(path, snippet, views_dir)] = (
                f"icon-only Button missing .accessibilityLabel(...) "
                f"(lines {idx + 1}-{end + 1})"
            )
    return found


def _load_baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text())


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    found = scan()

    if "--update" in argv:
        BASELINE.write_text(json.dumps(dict(sorted(found.items())), indent=2) + "\n")
        print(f"Wrote {len(found)} known violations to {BASELINE.name}")
        return 0

    known = set(_load_baseline())

    if "--list" in argv:
        print(f"Icon-only Buttons missing accessibility label ({len(found)}):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print("Accessibility / VoiceOver guardrail (#2285):")
    print(f"  scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} icon-only Button(s) without an accessibility label; "
          f"{len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} NEW icon-only control(s) missing .accessibilityLabel(...):")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: add `.accessibilityLabel(\"...\")` so VoiceOver announces the "
            f"control. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now clean — run --update to drop:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ No new unlabeled icon-only controls.")
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
