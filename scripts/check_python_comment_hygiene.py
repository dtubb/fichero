#!/usr/bin/env python3
"""Python comment hygiene guardrail (#1915).

Flags three categories in the Python backend source:

1. Commented-out code blocks — 3+ consecutive ``# `` lines that each begin with
   a Python keyword (``def``, ``class``, ``import``, ``return``, ``if``, …).
   Legitimate prose comments that happen to mention a keyword are ignored by
   the conservative keyword-at-start rule.

2. TODO / FIXME comments without a tracked issue reference (#NNN).

3. Banner / divider comments — 8+ consecutive ``# `` lines whose body consists
   entirely of repeated punctuation (``---``, ``===``, ``###``, ``***``).

Real doc-comments, module-level ``#: `` attribute docs, and type-comment
``# type: ignore`` lines are always exempt.

``KNOWN_VIOLATIONS`` is the ratchet: the script passes today and fails only
when a *new* violation is introduced.

Usage:
    scripts/check_python_comment_hygiene.py
    scripts/check_python_comment_hygiene.py --list
    scripts/check_python_comment_hygiene.py --help
"""
from __future__ import annotations

import hashlib
import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "fichero-server" / "src" / "fichero_server"
RULE_DOC = "AGENTS.md"

# Baseline violations filed as #1915 backlog.
# Keys are `relative/path.py#content-hash` — stable across line-number changes.
KNOWN_VIOLATIONS: dict[str, str] = {
    "knowledge/probabilistic_scorer.py#c2da862492": "TODO without issue ref (#1915 baseline)",
}

# Patterns
_TODO = re.compile(r"\b(?:TODO|FIXME)\b")
_ISSUE_REF = re.compile(r"#\d+")
_BANNER_BODY = re.compile(r"^[-=*#]{3,}$")

# Python keywords that strongly indicate a commented-out statement when they
# appear at the start of a ``# `` comment body.
_PY_KEYWORD_START = re.compile(
    r"^(?:def |class |import |from |return |if |elif |else:|for |while |try:|"
    r"except|raise |async |await |yield |with |pass$|break$|continue$|@\w)"
)

_EXEMPT = re.compile(r"^#:\s|^# type:\s|^#!")


def _comment_body(line: str) -> str | None:
    """Return the comment body if ``line`` is an ordinary ``# `` comment, else None."""
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    if _EXEMPT.match(stripped):
        return None
    return stripped[1:].lstrip()


def _sig(rel: str, body: str) -> str:
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def scan(src_dir: Path = SRC_DIR) -> dict[str, str]:
    found: dict[str, str] = {}

    for path in sorted(src_dir.rglob("*.py")):
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except OSError:
            continue

        rel = path.relative_to(src_dir).as_posix()

        # State for block detectors
        code_block: list[tuple[int, str]] = []  # (lineno, body)
        banner_block: list[tuple[int, str]] = []

        def flush_code() -> None:
            if len(code_block) >= 3:
                start_lineno, first_body = code_block[0]
                key = _sig(rel, first_body)
                found[key] = (
                    f"commented-out code block ({len(code_block)} lines "
                    f"starting at line {start_lineno})"
                )
            code_block.clear()

        def flush_banner() -> None:
            if len(banner_block) >= 8:
                start_lineno, first_body = banner_block[0]
                key = _sig(rel, first_body)
                found[key] = (
                    f"banner/divider comment block ({len(banner_block)} lines "
                    f"starting at line {start_lineno})"
                )
            banner_block.clear()

        for lineno, line in enumerate(lines, 1):
            body = _comment_body(line)
            if body is None:
                flush_code()
                flush_banner()
                continue

            # TODO / FIXME check
            if _TODO.search(body) and not _ISSUE_REF.search(body):
                found[_sig(rel, body)] = f"TODO/FIXME without issue ref: {body.strip()}"

            # Commented-out code block accumulator
            if _PY_KEYWORD_START.match(body):
                code_block.append((lineno, body))
                banner_block.clear()  # mutually exclusive with banner
            else:
                flush_code()

            # Banner/divider accumulator (only when not a code line)
            if not _PY_KEYWORD_START.match(body) and _BANNER_BODY.match(body.strip()):
                banner_block.append((lineno, body))
            else:
                flush_banner()

        flush_code()
        flush_banner()

    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Python comment hygiene violations ({len(found)}):\n")
        for key, reason in found.items():
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    # #4487 scan floor: 423 server .py files on 2026-08-02.
    require_scan_floor(
        sum(1 for _ in SRC_DIR.rglob("*.py")), 211, "server Python files (423 on 2026-08-02)"
    )
    print(f"Python comment hygiene guardrail: scanned {SRC_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} violation(s); {len(known)} known.")

    if stale:
        print(f"\n  {len(stale)} KNOWN_VIOLATIONS entries now clean — remove them:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  {len(new)} new Python comment hygiene violation(s):")
        for key in new:
            print(f"      {key}  <-  {found[key]}")
        print(
            "\nFix: delete commented-out code, annotate TODOs with a tracked issue "
            f"(#NNN), or remove decorative banner comments. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
    print("\nOK: no new Python comment hygiene violations.")
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
    _require_scan_roots_4382(SRC_DIR)
    raise SystemExit(main())
