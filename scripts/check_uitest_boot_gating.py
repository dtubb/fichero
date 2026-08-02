#!/usr/bin/env python3
"""Guardrail: boot side effects must not be gated on the bare UI-test flag (#3968).

## The failure this exists for

`isUITesting()` is true in BOTH UI-test modes — the embedded-engine mode is
literally *defined* as `isUITesting() && hasFlag`. So gating a boot side effect
on the bare predicate switches it off in the one mode whose entire purpose is
to run the real engine.

That is #3968. The embedded launch tests polled four accessibility identifiers
once a second for 120 seconds and found none of them, because the engine was
never spawned at all — `~/Library/Logs/Fichero/engine.log` was 137 minutes old
after three consecutive runs. A test that measured nothing reported a failure
whose cause was in the harness's own gating.

The fix names the intent once, in `suppressesBootSideEffectsForUITesting()`.
This guard keeps it named: the hand-written conjunction
`isUITesting() && !isEmbeddedEngineUITesting()` must not reappear, because two
copies of a predicate are two things nothing forces to agree, and the version
that omits the carve-out looks completely reasonable in review.

## What it does NOT flag

Bare `isUITesting()` is legitimate wherever BOTH modes want the same answer —
the disposable support directory, the seeded library fixture, an explicitly
owned transport. Flagging those would make this guard cry wolf, and a guard
that cries wolf gets deleted. So the rule is narrow and structural: only the
open-coded conjunction is banned, plus the definition of the named predicate
itself must survive.

Exit codes:
    0   no hand-rolled carve-out, and the named predicate exists and is used
    1   a hand-rolled carve-out reappeared, or the named predicate vanished
    2   BLIND -- the scan root is missing (the tree moved; fix these paths)

Usage:
    scripts/check_uitest_boot_gating.py
    scripts/check_uitest_boot_gating.py --app-dir PATH   # tests only
    scripts/check_uitest_boot_gating.py --help
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "#3968"

PREDICATE = "suppressesBootSideEffectsForUITesting"

# The banned shape, tolerant of whitespace and of `(isUITesting() && ...)`
# wrapping. Matches the conjunction only -- never a bare `isUITesting()`.
_HAND_ROLLED = re.compile(
    r"isUITesting\s*\(\s*\)\s*&&\s*!\s*isEmbeddedEngineUITesting\s*\(\s*\)"
)
# Reversed spelling of the same idea; a future edit could equally write this.
_HAND_ROLLED_REVERSED = re.compile(
    r"!\s*isEmbeddedEngineUITesting\s*\(\s*\)\s*&&\s*isUITesting\s*\(\s*\)"
)

_LINE_COMMENT = re.compile(r"^\s*(//|///)")


def scan(app_dir: Path) -> tuple[list[dict], int, int]:
    """Return (violations, predicate_definitions, predicate_uses).

    The two counts are what let this guard tell "clean" apart from "did not
    look". Zero violations means nothing only if the predicate it points at is
    actually there and actually called; delete both and a naive checker would
    call the tree spotless while the P0 was live again.
    """
    violations: list[dict] = []
    definitions = 0
    uses = 0

    for path in sorted(app_dir.rglob("*.swift")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        # The predicate's OWN body is the one place the conjunction belongs —
        # it is the single definition every other site now defers to. Exempt a
        # short window after its `func` line rather than the whole file, so a
        # second hand-rolled copy further down UITestSupport.swift is still
        # caught.
        exempt: set[int] = set()
        for index, line in enumerate(lines):
            if f"func {PREDICATE}(" in line:
                exempt.update(range(index, index + 4))

        for index, line in enumerate(lines):
            # Comments explaining the banned shape (this file's own rationale
            # is quoted in UITestSupport.swift) are documentation, not gating.
            if _LINE_COMMENT.match(line):
                continue
            if index not in exempt and (
                _HAND_ROLLED.search(line) or _HAND_ROLLED_REVERSED.search(line)
            ):
                violations.append(
                    {"file": _rel(path), "line": index + 1, "text": line.strip()}
                )
            if f"func {PREDICATE}(" in line:
                definitions += 1
            elif f"{PREDICATE}()" in line:
                uses += 1

    return violations, definitions, uses


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _app_dir_from(argv: list[str]) -> Path:
    """`--app-dir PATH` overrides the scan root, for the self-test."""
    if "--app-dir" in argv:
        index = argv.index("--app-dir")
        if index + 1 >= len(argv):
            print("--app-dir needs a path", file=sys.stderr)
            raise SystemExit(2)
        return Path(argv[index + 1])
    return APP_DIR


def main() -> int:
    argv = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in argv):
        print(__doc__)
        return 0

    app_dir = _app_dir_from(argv)
    _require_scan_roots_4382(app_dir)
    violations, definitions, uses = scan(app_dir)

    print(f"UI-test boot-gating guardrail: swept {_rel(app_dir)}")
    print(f"  {definitions} definition(s) of {PREDICATE}, {uses} use(s).")

    failed = False

    if violations:
        failed = True
        print(f"\n  {len(violations)} hand-rolled embedded carve-out(s):")
        for record in violations:
            print(f"      {record['file']}:{record['line']}  {record['text']}")
        print(
            f"\nUse {PREDICATE}() instead. Two copies of this predicate are two\n"
            "things nothing forces to agree, and the copy that omits\n"
            "`&& !isEmbeddedEngineUITesting()` reads as perfectly reasonable while\n"
            "silently disabling the engine spawn the embedded launch tests exist to\n"
            f"exercise ({RULE_DOC})."
        )

    if definitions != 1:
        failed = True
        print(f"\n  Expected exactly 1 definition of {PREDICATE}, found {definitions}.")

    if uses < 2:
        failed = True
        print(
            f"\n  Only {uses} call site(s) use {PREDICATE}; 2 boot gates depend on it\n"
            "  (the interactive-launch decision and the engine-provisioning inputs).\n"
            "  A guard that passes because the thing it protects was deleted is the\n"
            "  failure it exists to prevent."
        )

    if failed:
        return 1

    print(
        "\nPASS boot side effects are gated on the named predicate, not the bare flag."
    )
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so."""
    import sys as _sys

    missing = [str(root) for root in roots if not root.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    raise SystemExit(main())
