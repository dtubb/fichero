#!/usr/bin/env python3
"""Stacked SwiftUI presentation modifiers on one view node (#4201).

Two confirmed launch crashes came from presentation machinery piled onto a
SINGLE view node:

* **#3163** — two `.searchable` modifiers registered `com.apple.SwiftUI.search`
  twice, crashing at launch.
* **#4189** — a `@ViewBuilder` returning a bare `if let` (an OPTIONAL view)
  under `.safeAreaInset`: the inset content alternated empty<->populated across
  a state flip, the attribute graph re-typed live attributes mid-update, and it
  hit a precondition failure.

Both were non-deterministic, so a green gate does not clear this class — #4189
reproduced for Daniel while the suite stayed green. The cost asymmetry is what
justifies a check: the fix is always trivial (give it its own node), the failure
is always a launch crash.

Two rules:
1. Two or more presentation modifiers applied to the SAME chained expression.
2. A `@ViewBuilder` member whose body is a bare `if`/`if let` with no `else` —
   an Optional view — referenced by `.safeAreaInset`/`.sheet`/`.popover`. A
   stable concrete root is the fix (#4189's exact signature).

False positives are acceptable: stacking is nearly always avoidable, so the
nudge to split costs little even when a given instance is safe.

Usage:
    scripts/check_stacked_presentation_modifiers.py
    scripts/check_stacked_presentation_modifiers.py --list
    scripts/check_stacked_presentation_modifiers.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "#4201"

PRESENTATION = (
    "sheet",
    "alert",
    "confirmationDialog",
    "popover",
    "fullScreenCover",
    "searchable",
    "safeAreaInset",
    "inspector",
)
# Modifiers whose CONTENT must have a stable concrete root (#4189).
OPTIONAL_CONTENT_SENSITIVE = ("safeAreaInset", "sheet", "popover")

# Keyed "path#firstModifier+secondModifier@line" — today's backlog, in the same
# sense as check_native_controls.py. Entries are NOT certified safe; they exist
# so the check can land green and fail on anything NEW. Empty is the goal state:
# the two founding entries were fixed within the hour of being recorded.
KNOWN_VIOLATIONS: dict[str, str] = {}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*$")
_MODIFIER = re.compile(r"^\s*\.(\w+)\s*[({]")
_VIEWBUILDER_MEMBER = re.compile(
    r"@ViewBuilder\s+(?:private\s+|public\s+)?(?:var|func)\s+(\w+)"
)


def _rel(path: Path) -> str:
    """Repo-relative when possible; absolute under a test's tmp dir."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def code_lines(text: str) -> list[str]:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return [_LINE_COMMENT.sub("", line) for line in text.splitlines()]


def _chain_runs(lines: list[str]) -> list[list[int]]:
    """Consecutive `.modifier` lines — one Swift modifier chain each.

    A blank line, or any line that is not a `.modifier` continuation, ends the
    chain. This deliberately under-reaches on chains broken across closures
    rather than guessing and producing noise.
    """
    runs: list[list[int]] = []
    current: list[int] = []
    for idx, line in enumerate(lines):
        if _MODIFIER.match(line):
            current.append(idx)
            continue
        if current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def stacked_modifiers(path: Path, lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    rel = _rel(path)
    for run in _chain_runs(lines):
        hits = [
            (idx, _MODIFIER.match(lines[idx]).group(1))
            for idx in run
            if _MODIFIER.match(lines[idx]).group(1) in PRESENTATION
        ]
        if len(hits) < 2:
            continue
        names = "+".join(name for _, name in hits)
        key = f"{rel}#{names}@{hits[0][0] + 1}"
        found[key] = (
            f"{len(hits)} presentation modifiers on one node "
            f"(lines {hits[0][0] + 1}-{hits[-1][0] + 1}) — give each its own node"
        )
    return found


def optional_viewbuilder_content(path: Path, text: str, lines: list[str]) -> dict[str, str]:
    """@ViewBuilder members that return a bare optional view, used as presentation content."""
    found: dict[str, str] = {}
    rel = _rel(path)
    for match in _VIEWBUILDER_MEMBER.finditer(text):
        name = match.group(1)
        start = text[: match.start()].count("\n")
        body = lines[start : start + 25]
        # First statement is a bare if/if-let and nothing else returns a view.
        opener = next((ln for ln in body[1:] if ln.strip()), "")
        if not re.match(r"^\s*if\b", opener):
            continue
        if any(re.match(r"^\s*}?\s*else\b", ln) for ln in body):
            continue
        # The content usually arrives as a TRAILING closure —
        # `.safeAreaInset(edge: .bottom) { banner }` — so the name sits outside
        # the parens. Scan a window after the modifier instead of inside them.
        used_by = [
            m
            for m in OPTIONAL_CONTENT_SENSITIVE
            if any(
                re.search(rf"\b{name}\b", text[hit.start() : hit.start() + 300])
                for hit in re.finditer(rf"\.{m}\b", text)
            )
        ]
        if not used_by:
            continue
        found[f"{rel}#optional-content:{name}@{start + 1}"] = (
            f"@ViewBuilder `{name}` returns a bare optional view and feeds "
            f".{'/.'.join(used_by)} — give it a stable concrete root (#4189)"
        )
    return found


def scan(views_dir: Path = VIEWS_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(views_dir.rglob("*.swift")):
        if "Tests" in path.parts or ".build" in path.parts:
            continue
        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            continue
        lines = code_lines(raw)
        text = "\n".join(lines)
        found.update(stacked_modifiers(path, lines))
        found.update(optional_viewbuilder_content(path, text, lines))
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"Stacked presentation modifiers ({len(found)}):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Presentation-modifier guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} stacked site(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries are now clean; remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new stacked presentation site(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: attach each presentation modifier to its own view node, and give\n"
            "optional @ViewBuilder content a stable concrete root. Both shapes have\n"
            f"caused launch crashes. Rule pointer: {RULE_DOC}."
        )
        return 1

    print("\nPASS no stacked presentation modifiers.")
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
