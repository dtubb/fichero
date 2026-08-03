#!/usr/bin/env python3
"""One selection grammar across every library view mode (#4436).

Selection in a Finder-like browser is a set of rules — click, ⇧-range,
⌘-toggle, marquee, ⌘A, and an ANCHOR they all move together — that a second
implementation never reproduces by accident. `SelectionGrammar` states them
once. The failure this guards against is not "a mode has a bug"; it is a mode
being ADDED that never delegates, which is how the app arrived at six
implementations of one concept (see
docs/contributor/architecture/fichero/library_selection_inventory.md).

The rule: inside the library view-mode tree, a write to the selection set or to
the anchor/cursor must go through the grammar — `apply(...)`,
`SelectionGrammar.…`, or `CanvasTapSelection.…`. A raw `selection = [id]` or
`selectedNodeIds = [id]` is a fifth (sixth, seventh) copy of the rules.

A second rule, added by #4377: hand-constructing `SelectionGrammar.Result(...)`
is a bypass, not a delegation. It is the grammar's own OUTPUT type filled in
manually — it names the grammar, so the window rule above scored it as
delegation, and three call sites used it to express "select exactly this one
row" four different times in four places. `SelectionGrammar.select(_:)` says
that now, and constructing a `Result` outside the grammar is forbidden.

WHAT THIS CHECK CANNOT SEE, stated plainly because it was GREEN throughout the
period when #4377's last two gaps were open, and a guardrail nobody can bound is
worse than one nobody has:

This is a DELEGATION check. It asks whether a selection write is accompanied by
the grammar's name; it cannot read the ARGUMENTS. Both surviving #4377 defects
were argument-level and both sat in code this file scores as perfect:

  * The Table passed `filteredDocuments.map(\\.id)` as its ordered list while
    rendering an expandable OUTLINE whose child rows are not documents. The
    delegation was flawless and the list was the wrong list.
  * Miller-columns mutated `columnsPath` / `columnsActiveDepth` — changing the
    ordered list itself — immediately BEFORE calling the grammar with it.

No line-oriented regex reaches either; both are properties of what a value IS at
a call site. They belong to `SelectionSurfaceParityTests`, which drives each
surface through its real entry point and can therefore catch exactly this class.
The division of labour is deliberate: this file stops a NEW mode from skipping
the grammar, and the parity suite stops an EXISTING one from feeding it garbage.

Deliberate exemptions are NAMED here rather than pattern-holed, so adding one
is a visible decision:

  * `Table(selection: $selection)` — the native table owns its own clicks
    because `NSTableView` already implements these exact rules; what it does
    not own is the anchor, which it reconciles via `SelectionGrammar.reconcile`.
  * Bindings that FORWARD the shared set to a child view rather than deciding
    anything (`selection: $selectedNodeIds`, `state.selection = …`).

Exit codes:
    0  every selection write in the view-mode tree goes through the grammar
    1  a mode writes selection by hand
    2  BLIND — the scan roots moved, or the population collapsed (#4487/#4382)
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEW_MODES = ROOT / "fichero" / "fichero" / "Views" / "Library" / "ViewModes"
LIBRARY_VIEWS = ROOT / "fichero" / "fichero" / "Views" / "Library"

# The names that ARE the selection state. `selection` and `selectedNodeIds` are
# the sets; the other two are the state that must move WITH them — a mode that
# writes only the set and leaves these stale is the #4436 columns defect.
#
# NOT anchored to the start of the line: `.onTapGesture { selectedNodeIds =
# [node.id] }` is the exact shape both legacy canvas renderers shipped, and a
# `^\s*` anchor walks straight past it. The lookbehind excludes `.selection =`
# (a property on something else) and `$selection` (a binding being forwarded);
# `=(?!=)` excludes a comparison.
_SELECTION_WRITE = re.compile(
    r"(?<![\w.$])(?:self\.)?(selection|selectedNodeIds|selectionAnchor|selectionCursor)"
    r"\s*(?:=(?!=)|\.removeAll\(\)|\.insert\(|\.remove\()"
)

# The delegating forms. A line that mentions one of these is routing, not
# deciding, so it is not a second implementation — and it opens the window
# below, because committing a Result takes three more lines.
#
# DELIBERATELY NOT `apply(`: that word appears on renderer methods that have
# nothing to do with selection (`CanvasOrtho2DRenderer.apply(_ op:)`), and a
# token that generic silently disables the check for whatever follows it. The
# real call sites all name the grammar within a line or two anyway.
_DELEGATES = (
    "SelectionGrammar",
    "CanvasTapSelection",
)

# Forwarding a binding to a child view, or an init storing it, decides nothing.
_FORWARDING = re.compile(
    r"selection:\s*\$"
    r"|state\.selection\s*="
    r"|\.selection\s*=\s*selectedNodeIds"
    r"|self\.selection\s*=\s*selection\s*$"
    # The canvas↔library id ADAPTER: the setter half of
    # `LibraryView.canvasSelectedNodeIds`, which maps node ids back to document
    # ids. It translates, it does not decide — the grammar already ran, on the
    # controller, before the binding was written.
    r"|librarySelection\(forCanvasNodeIds"
)

# A comment is prose, not code. This file's own docstring quotes the very shape
# it forbids, and a check that flags its neighbours' comments is a check people
# turn off.
_COMMENT = re.compile(r"^\s*(?://|/\*|\*)")

# How many lines a `SelectionGrammar.…` call keeps its statement block exempt
# for. Committing a `Result` is three assignments — `selection = result.selection`
# and friends — and those are the grammar being APPLIED, not bypassed. A window
# rather than a name match, because the local is variously `result`, `cleared`
# and `reconciled`, and pinning the guardrail to a variable name is how it stops
# firing the day someone renames one.
_GRAMMAR_WINDOW = 12

# NAMED exemptions, one per file, each with the reason it is not a second
# implementation. A list, not a pattern, so adding one is a visible decision.
_EXEMPT_FILES = {
    # The RealityKit renderers keep a MIRROR of the selection to know which
    # cards to reskin (`case .setSelection`). It is derived display state fed by
    # the controller, decides nothing, and must be a plain assignment for the
    # symmetric-difference reskin to work.
    "CanvasOrtho2DRenderer.swift",
    "CanvasScene3DRenderer.swift",
}

# Post-mutation pruning is not a gesture: after a delete, ids that no longer
# exist must leave the selection. There is no anchor rule to obey — the rows are
# gone. Matched narrowly so a genuine gesture in the same file still fires.
_PRUNE = re.compile(r"selection\s*(?:\.remove\(|=\s*selection\.filter)")

# #4377: filling in the grammar's OUTPUT type by hand. Maximally disguised as
# delegation — the token `SelectionGrammar` is right there on the line, so the
# `_GRAMMAR_WINDOW` rule above waves it through — while being a private copy of
# whichever rule it spells out. Every real caller wants `select(_:)`, `click`,
# `extend`, `clear`, `marquee` or `reconcile`; a surface that needs a shape none
# of those produce needs a new grammar METHOD, so the rule lands in the rulebook
# with the rest.
_HAND_BUILT_RESULT = re.compile(r"SelectionGrammar\.Result\s*\(")


def _swift_files() -> list[Path]:
    """The library view-mode tree, plus the shared LibraryView+*Selection files.

    Only source that actually ships: no `.build`, no vendored trees, no files
    that exist solely inside a working worktree.
    """
    files: list[Path] = []
    for path in sorted(VIEW_MODES.rglob("*.swift")):
        if any(part in {".build", "Pods", "DerivedData"} for part in path.parts):
            continue
        files.append(path)
    for name in ("LibraryView+Selection.swift", "LibraryView+ArrowNavigation.swift",
                 "LibraryView+DeleteActions.swift"):
        candidate = LIBRARY_VIEWS / name
        if candidate.exists():
            files.append(candidate)
    return files


def violations(files: list[Path] | None = None, root: Path = ROOT) -> list[tuple[str, int, str]]:
    bad: list[tuple[str, int, str]] = []
    for path in (files if files is not None else _swift_files()):
        if path.name in _EXEMPT_FILES:
            continue
        since_grammar = _GRAMMAR_WINDOW + 1
        for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if _COMMENT.match(line):
                continue
            # Checked BEFORE the delegation window, which this shape would
            # otherwise open for itself (#4377).
            if _HAND_BUILT_RESULT.search(line):
                bad.append((path.relative_to(root).as_posix(), lineno, line.strip()))
                continue
            if any(token in line for token in _DELEGATES):
                since_grammar = 0
            else:
                since_grammar += 1
            if not _SELECTION_WRITE.search(line):
                continue
            if since_grammar <= _GRAMMAR_WINDOW:
                continue
            if _FORWARDING.search(line) or _PRUNE.search(line):
                continue
            bad.append((path.relative_to(root).as_posix(), lineno, line.strip()))
    return bad


def main() -> int:
    files = _swift_files()
    # #4487 scan floor on the POPULATION EXAMINED, not on findings: a zero-file
    # scan means the view-mode tree moved, not that every mode delegates.
    # 73 Swift files under Views/Library/ViewModes on 2026-08-03; floor is
    # half, a tripwire for "the scan collapsed", not a ratchet.
    require_scan_floor(len(files), 36, "library view-mode Swift files (73 on 2026-08-03)")

    bad = violations()
    if not bad:
        print(f"selection-grammar guardrail: {len(files)} view-mode files, "
              "every selection write goes through SelectionGrammar.")
        return 0
    print("selection-grammar guardrail FAILED — a library view mode writes "
          "selection by hand instead of delegating to SelectionGrammar (#4436). "
          "Four modes already did this and disagreed about the anchor; a fifth "
          "must not. Route the write through apply(...), SelectionGrammar.… or "
          "CanvasTapSelection.…:\n")
    for rel, lineno, text in bad:
        print(f"  {rel}:{lineno}  {text}")
    return 1


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so."""
    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        print(
            "check_selection_grammar.py: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(VIEW_MODES, LIBRARY_VIEWS)
    raise SystemExit(main())
